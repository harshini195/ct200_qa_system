import difflib
from sqlalchemy.orm import Session
from sqlalchemy import or_
from . import models


def resolve_version(db: Session, document_id: int, version: int | None) -> models.DocumentVersion | None:
    q = db.query(models.DocumentVersion).filter_by(document_id=document_id)
    if version is not None:
        return q.filter_by(version_number=version).first()
    return q.order_by(models.DocumentVersion.version_number.desc()).first()


def get_top_level_sections(db: Session, document_id: int, version: int | None):
    ver = resolve_version(db, document_id, version)
    if ver is None:
        return None
    return (
        db.query(models.NodeRevision)
        .filter_by(version_id=ver.id, parent_revision_id=None)
        .order_by(models.NodeRevision.order_in_document)
        .all()
    )


def get_children(db: Session, version_id: int, parent_revision_id: int):
    return (
        db.query(models.NodeRevision)
        .filter_by(version_id=version_id, parent_revision_id=parent_revision_id)
        .order_by(models.NodeRevision.order_in_document)
        .all()
    )


def get_node_revision_by_node_id(db: Session, node_id: int, document_id: int, version: int | None):
    ver = resolve_version(db, document_id, version)
    if ver is None:
        return None, None
    rev = (
        db.query(models.NodeRevision)
        .filter_by(node_id=node_id, version_id=ver.id)
        .first()
    )
    return rev, ver


def search_nodes(db: Session, document_id: int, query: str, version: int | None):
    ver = resolve_version(db, document_id, version)
    if ver is None:
        return []
    like = f"%{query}%"
    return (
        db.query(models.NodeRevision)
        .filter(models.NodeRevision.version_id == ver.id)
        .filter(or_(
            models.NodeRevision.heading_text.ilike(like),
            models.NodeRevision.body_text.ilike(like),
        ))
        .order_by(models.NodeRevision.order_in_document)
        .all()
    )


def get_node_diff(db: Session, node_id: int, document_id: int, from_version: int, to_version: int):
    from_rev, _ = get_node_revision_by_node_id(db, node_id, document_id, from_version)
    to_rev, _ = get_node_revision_by_node_id(db, node_id, document_id, to_version)

    if from_rev is None or to_rev is None:
        return {
            "node_id": node_id,
            "from_version": from_version,
            "to_version": to_version,
            "changed": from_rev is None or to_rev is None,
            "diff": "Node does not exist in one of the requested versions.",
        }

    changed = from_rev.content_hash != to_rev.content_hash
    diff_text = None
    if changed:
        diff_lines = difflib.unified_diff(
            from_rev.body_text.splitlines(),
            to_rev.body_text.splitlines(),
            fromfile=f"v{from_version}",
            tofile=f"v{to_version}",
            lineterm="",
        )
        diff_text = "\n".join(diff_lines)

    return {
        "node_id": node_id,
        "from_version": from_version,
        "to_version": to_version,
        "changed": changed,
        "diff": diff_text,
    }


def get_latest_revision_for_node(db: Session, node_id: int):
    """Used for staleness checks: the current (latest-version) content hash
    for a logical node, regardless of which version a generation was made from."""
    return (
        db.query(models.NodeRevision)
        .join(models.DocumentVersion, models.NodeRevision.version_id == models.DocumentVersion.id)
        .filter(models.NodeRevision.node_id == node_id)
        .order_by(models.DocumentVersion.version_number.desc())
        .first()
    )


def reconstruct_selection_text(db: Session, selection: models.Selection) -> str:
    parts = []
    for item in selection.items:
        rev = db.query(models.NodeRevision).get(item.node_revision_id)
        if rev is None:
            continue
        heading_prefix = f"{rev.heading_number} " if rev.heading_number else ""
        parts.append(f"## {heading_prefix}{rev.heading_text}\n\n{rev.body_text}")
    return "\n\n".join(parts)
