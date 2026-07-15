import os
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from . import models, schemas, crud, ingestion, llm_client, json_store
from .database import engine, get_db, Base

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="CT-200 QA Traceability System",
    description=(
        "Dev tool: [view the parsed document tree in a browser]"
        "(http://127.0.0.1:8001/?document=ct200_manual) "
        "(run `python scratch/tree_view_server.py` in a separate terminal first)."
    ),
)


def _rev_to_dict(rev: models.NodeRevision, include_body: bool = True) -> dict:
    return {
        "id": rev.id,
        "node_id": rev.node_id,
        "heading_text": rev.heading_text,
        "heading_number": rev.heading_number,
        "level": rev.level,
        "order_in_document": rev.order_in_document,
        "content_hash": rev.content_hash,
        "body_text": rev.body_text if include_body else None,
    }


# ---------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------

@app.post("/documents/{document_name}/versions")
def ingest_new_version(document_name: str, req: schemas.IngestRequest, db: Session = Depends(get_db)):
    if req.raw_text is not None:
        raw_text = req.raw_text
    elif req.file_path is not None:
        if not os.path.exists(req.file_path):
            raise HTTPException(404, f"file_path {req.file_path} not found on server")
        with open(req.file_path) as f:
            raw_text = f.read()
    else:
        raise HTTPException(400, "Provide either raw_text or file_path")

    version = ingestion.ingest_document(db, document_name, raw_text)
    import json as _json
    return {
        "document_name": document_name,
        "version_number": version.version_number,
        "version_id": version.id,
        "parser_warnings": _json.loads(version.parser_warnings or "[]"),
    }


# ---------------------------------------------------------------------
# Browse API
# ---------------------------------------------------------------------

@app.get("/documents/{document_name}/sections")
def list_top_level_sections(document_name: str, version: int | None = Query(None), db: Session = Depends(get_db)):
    doc = db.query(models.Document).filter_by(name=document_name).first()
    if doc is None:
        raise HTTPException(404, "document not found")
    revs = crud.get_top_level_sections(db, doc.id, version)
    if revs is None:
        raise HTTPException(404, "version not found")
    return [_rev_to_dict(r, include_body=False) for r in revs]


@app.get("/documents/{document_name}/nodes/{node_id}")
def get_node(document_name: str, node_id: int, version: int | None = Query(None), db: Session = Depends(get_db)):
    doc = db.query(models.Document).filter_by(name=document_name).first()
    if doc is None:
        raise HTTPException(404, "document not found")
    rev, ver = crud.get_node_revision_by_node_id(db, node_id, doc.id, version)
    if rev is None:
        raise HTTPException(404, "node not found in this version")
    children = crud.get_children(db, ver.id, rev.id)
    result = _rev_to_dict(rev)
    result["version_number"] = ver.version_number
    result["children"] = [_rev_to_dict(c, include_body=False) for c in children]
    return result


@app.get("/documents/{document_name}/search")
def search(document_name: str, q: str, version: int | None = Query(None), db: Session = Depends(get_db)):
    doc = db.query(models.Document).filter_by(name=document_name).first()
    if doc is None:
        raise HTTPException(404, "document not found")
    revs = crud.search_nodes(db, doc.id, q, version)
    return [_rev_to_dict(r) for r in revs]


@app.get("/documents/{document_name}/nodes/{node_id}/diff")
def node_diff(document_name: str, node_id: int, from_version: int, to_version: int, db: Session = Depends(get_db)):
    doc = db.query(models.Document).filter_by(name=document_name).first()
    if doc is None:
        raise HTTPException(404, "document not found")
    return crud.get_node_diff(db, node_id, doc.id, from_version, to_version)


# ---------------------------------------------------------------------
# Selections
# ---------------------------------------------------------------------

@app.post("/selections")
def create_selection(req: schemas.CreateSelectionRequest, document_name: str, db: Session = Depends(get_db)):
    doc = db.query(models.Document).filter_by(name=document_name).first()
    if doc is None:
        raise HTTPException(404, "document not found")
    ver = crud.resolve_version(db, doc.id, req.version)
    if ver is None:
        raise HTTPException(404, "version not found")

    selection = models.Selection(name=req.name)
    db.add(selection)
    db.flush()

    for node_id in req.node_ids:
        rev = db.query(models.NodeRevision).filter_by(node_id=node_id, version_id=ver.id).first()
        if rev is None:
            db.rollback()
            raise HTTPException(400, f"node_id {node_id} does not exist in version {ver.version_number}")
        db.add(models.SelectionNode(
            selection_id=selection.id,
            node_id=node_id,
            version_id=ver.id,
            node_revision_id=rev.id,
        ))

    db.commit()
    db.refresh(selection)
    return {"selection_id": selection.id, "name": selection.name, "version_pinned": ver.version_number, "node_ids": req.node_ids}


@app.get("/selections/{selection_id}")
def get_selection(selection_id: int, db: Session = Depends(get_db)):
    selection = db.query(models.Selection).get(selection_id)
    if selection is None:
        raise HTTPException(404, "selection not found")
    items = []
    for item in selection.items:
        rev = db.query(models.NodeRevision).get(item.node_revision_id)
        items.append({"node_id": item.node_id, "version_id": item.version_id, "heading_text": rev.heading_text if rev else None})
    return {"id": selection.id, "name": selection.name, "items": items}


# ---------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------

@app.post("/selections/{selection_id}/generate")
def generate(selection_id: int, db: Session = Depends(get_db)):
    selection = db.query(models.Selection).get(selection_id)
    if selection is None:
        raise HTTPException(404, "selection not found")

    # Policy: every call creates a NEW generation record. LLM output is not
    # deterministic and a user may deliberately want another attempt; silently
    # overwriting a prior generation would destroy traceability to whatever
    # was actually shown to someone at a point in time (see APPROACH.md).
    source_text = crud.reconstruct_selection_text(db, selection)
    result = llm_client.generate_test_cases(source_text)

    source_node_revisions = []
    for item in selection.items:
        rev = db.query(models.NodeRevision).get(item.node_revision_id)
        source_node_revisions.append({
            "node_id": item.node_id,
            "version_id": item.version_id,
            "content_hash": rev.content_hash if rev else None,
        })

    record = {
        "selection_id": selection_id,
        "status": result["status"],
        "test_cases": result.get("test_cases"),
        "raw_response": result.get("raw_response"),
        "error": result.get("error"),
        "source_node_revisions": source_node_revisions,
    }
    gen_id = json_store.save_generation(record)
    record["_id"] = gen_id
    return record


# ---------------------------------------------------------------------
# Retrieval + staleness
# ---------------------------------------------------------------------

def _attach_staleness(db: Session, record: dict) -> dict:
    stale = False
    per_source = []
    for src in record.get("source_node_revisions", []):
        latest_rev = crud.get_latest_revision_for_node(db, src["node_id"])
        current_hash = latest_rev.content_hash if latest_rev else None
        is_stale = current_hash != src["content_hash"]
        stale = stale or is_stale
        per_source.append({
            "node_id": src["node_id"],
            "generated_from_hash": src["content_hash"],
            "current_hash": current_hash,
            "stale": is_stale,
        })
    record["stale"] = stale
    record["staleness_detail"] = per_source
    return record


@app.get("/selections/{selection_id}/test-cases")
def get_test_cases_by_selection(selection_id: int, db: Session = Depends(get_db)):
    records = json_store.list_generations_by_selection(selection_id)
    return [_attach_staleness(db, r) for r in records]


@app.get("/nodes/{node_id}/test-cases")
def get_test_cases_by_node(node_id: int, db: Session = Depends(get_db)):
    records = json_store.list_generations_by_node(node_id)
    return [_attach_staleness(db, r) for r in records]


