import os
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pytest

from app.database import Base, get_db
from app.main import app

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def load(name):
    with open(os.path.join(DATA_DIR, name)) as f:
        return f.read()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setenv("CT200_GENERATIONS_DIR", str(tmp_path / "generations"))
    import importlib
    from app import json_store
    importlib.reload(json_store)

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_list_versions_endpoint(client):
    client.post("/documents/ct200_manual/versions", json={"document_name": "ct200_manual", "raw_text": load("ct200_manual.md")})
    client.post("/documents/ct200_manual/versions", json={"document_name": "ct200_manual", "raw_text": load("ct200_manual_v2.md")})

    resp = client.get("/documents/ct200_manual/versions")
    assert resp.status_code == 200
    versions = resp.json()
    assert [v["version_number"] for v in versions] == [1, 2]


def test_version_detail_endpoint(client):
    client.post("/documents/ct200_manual/versions", json={"document_name": "ct200_manual", "raw_text": load("ct200_manual.md")})
    resp = client.get("/documents/ct200_manual/versions/1")
    assert resp.status_code == 200
    assert resp.json()["node_count"] > 0


def test_document_wide_stale_and_traceability(client):
    client.post("/documents/ct200_manual/versions", json={"document_name": "ct200_manual", "raw_text": load("ct200_manual.md")})
    client.post("/documents/ct200_manual/versions", json={"document_name": "ct200_manual", "raw_text": load("ct200_manual_v2.md")})

    search_resp = client.get("/documents/ct200_manual/search", params={"q": "Error Codes"})
    node_id = search_resp.json()[0]["node_id"]

    client.post("/selections", params={"document_name": "ct200_manual"}, json={"name": "t", "node_ids": [node_id], "version": 1})
    client.post("/selections/1/generate")

    stale_resp = client.get("/documents/ct200_manual/stale")
    assert stale_resp.status_code == 200
    assert len(stale_resp.json()) == 1
    assert stale_resp.json()[0]["stale"] is True

    trace_resp = client.get("/documents/ct200_manual/traceability")
    assert trace_resp.status_code == 200
    trace = trace_resp.json()
    matching = [t for t in trace if t["node_id"] == node_id]
    assert len(matching) == 1
    assert matching[0]["test_cases"][0]["stale"] is True
