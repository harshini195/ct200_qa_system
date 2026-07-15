import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app import models, ingestion

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def load(name):
    with open(os.path.join(DATA_DIR, name)) as f:
        return f.read()


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_reingestion_preserves_unchanged_nodes_as_same_logical_node(db):
    v1 = ingestion.ingest_document(db, "ct200_manual", load("ct200_manual.md"))
    v2 = ingestion.ingest_document(db, "ct200_manual", load("ct200_manual_v2.md"))

    assert v1.version_number == 1
    assert v2.version_number == 2

    # "1.1 Intended Use" is identical text in both files -> same Node.id,
    # and identical content_hash across versions.
    v1_rev = db.query(models.NodeRevision).filter_by(
        version_id=v1.id, heading_number="1.1"
    ).first()
    v2_rev = db.query(models.NodeRevision).filter_by(
        version_id=v2.id, heading_number="1.1"
    ).first()
    assert v1_rev.node_id == v2_rev.node_id
    assert v1_rev.content_hash == v2_rev.content_hash


def test_changed_body_text_flagged_via_different_hash_same_node(db):
    v1 = ingestion.ingest_document(db, "ct200_manual", load("ct200_manual.md"))
    v2 = ingestion.ingest_document(db, "ct200_manual", load("ct200_manual_v2.md"))

    # "2.1.1.1 Battery Life..." changes wording (300->250 cycles etc) between
    # v1 and v2 but keeps the same heading/number -> same node, different hash.
    v1_rev = db.query(models.NodeRevision).filter_by(
        version_id=v1.id, heading_number="2.1.1.1"
    ).first()
    v2_rev = db.query(models.NodeRevision).filter_by(
        version_id=v2.id, heading_number="2.1.1.1"
    ).first()
    assert v1_rev.node_id == v2_rev.node_id
    assert v1_rev.content_hash != v2_rev.content_hash


def test_new_node_in_v2_gets_new_logical_node(db):
    ingestion.ingest_document(db, "ct200_manual", load("ct200_manual.md"))
    v2 = ingestion.ingest_document(db, "ct200_manual", load("ct200_manual_v2.md"))

    v2_new_rev = db.query(models.NodeRevision).filter_by(
        version_id=v2.id, heading_number="5.3"
    ).first()
    assert v2_new_rev is not None

    # confirm no v1 NodeRevision shares that node_id (truly new, not matched)
    v1_ver = db.query(models.DocumentVersion).filter_by(version_number=1).first()
    v1_match = db.query(models.NodeRevision).filter_by(
        version_id=v1_ver.id, node_id=v2_new_rev.node_id
    ).first()
    assert v1_match is None


def test_v1_not_destroyed_by_v2_ingestion(db):
    v1 = ingestion.ingest_document(db, "ct200_manual", load("ct200_manual.md"))
    ingestion.ingest_document(db, "ct200_manual", load("ct200_manual_v2.md"))

    v1_revisions_still_present = db.query(models.NodeRevision).filter_by(version_id=v1.id).count()
    assert v1_revisions_still_present > 0
