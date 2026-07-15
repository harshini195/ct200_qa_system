import hashlib
import json
from sqlalchemy.orm import Session
from sqlalchemy import func

from . import models
from .parser import parse_markdown, flatten, content_hash, validate_numeric_consistency
from .version_matcher import match_nodes


def ingest_document(db: Session, document_name: str, raw_text: str) -> models.DocumentVersion:
    doc = db.query(models.Document).filter_by(name=document_name).first()
    if doc is None:
        doc = models.Document(name=document_name)
        db.add(doc)
        db.flush()

    latest_version = (
        db.query(models.DocumentVersion)
        .filter_by(document_id=doc.id)
        .order_by(models.DocumentVersion.version_number.desc())
        .first()
    )
    next_version_number = (latest_version.version_number + 1) if latest_version else 1

    root = parse_markdown(raw_text)
    warnings = validate_numeric_consistency(root)
    raw_nodes = flatten(root)

    file_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    new_version = models.DocumentVersion(
        document_id=doc.id,
        version_number=next_version_number,
        raw_file_hash=file_hash,
        parser_warnings=json.dumps(warnings),
    )
    db.add(new_version)
    db.flush()

    old_revisions = []
    if latest_version is not None:
        old_revisions = (
            db.query(models.NodeRevision)
            .filter_by(version_id=latest_version.id)
            .all()
        )

    matches = match_nodes(old_revisions, raw_nodes) if old_revisions else {}

    # node_key -> newly created NodeRevision, used to wire up parent_revision_id
    key_to_new_revision = {}

    for raw_node in raw_nodes:
        matched_old_revision = matches.get(raw_node.node_key)

        if matched_old_revision is not None:
            node_id = matched_old_revision.node_id
        else:
            new_node = models.Node(document_id=doc.id, first_version_id=new_version.id)
            db.add(new_node)
            db.flush()
            node_id = new_node.id

        parent_revision_id = None
        if raw_node.parent is not None and raw_node.parent.level != 0:
            parent_rev = key_to_new_revision.get(raw_node.parent.node_key)
            if parent_rev is not None:
                parent_revision_id = parent_rev.id

        chash = content_hash(raw_node.heading_text, raw_node.body_text)

        rev = models.NodeRevision(
            node_id=node_id,
            version_id=new_version.id,
            heading_text=raw_node.heading_text,
            heading_number=raw_node.heading_number,
            level=raw_node.level,
            order_in_document=raw_node.order_in_document,
            parent_revision_id=parent_revision_id,
            body_text=raw_node.body_text,
            content_hash=chash,
        )
        db.add(rev)
        db.flush()
        key_to_new_revision[raw_node.node_key] = rev

    db.commit()
    db.refresh(new_version)
    return new_version
