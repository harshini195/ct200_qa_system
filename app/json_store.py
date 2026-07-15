"""
JSON-file-backed store for LLM-generated test cases.

Why JSON instead of MongoDB: this assignment's generation records are
simple, low-volume, single-writer documents with no need for cross-document
queries beyond "by selection_id" or "by node_id" -- both of which are cheap
to do with a linear scan over a directory of JSON files at this scale.
Standing up a real Mongo instance (or an Atlas account) is friction with no
functional payoff for a take-home assignment; if this went to production
with real concurrent writers, THIS is one of the first things to replace
(see APPROACH.md decision log, question 2).

Each generation is stored as one JSON file: generations_store/<id>.json
"""

import json
import os
import uuid
from datetime import datetime, timezone

STORE_DIR = os.environ.get("CT200_GENERATIONS_DIR", "generations_store")


def _ensure_dir():
    os.makedirs(STORE_DIR, exist_ok=True)


def save_generation(record: dict) -> str:
    _ensure_dir()
    gen_id = str(uuid.uuid4())
    record = dict(record)
    record["_id"] = gen_id
    record["generated_at"] = datetime.now(timezone.utc).isoformat()
    path = os.path.join(STORE_DIR, f"{gen_id}.json")
    with open(path, "w") as f:
        json.dump(record, f, indent=2)
    return gen_id


def get_generation(gen_id: str) -> dict | None:
    path = os.path.join(STORE_DIR, f"{gen_id}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def list_generations_by_selection(selection_id: int) -> list[dict]:
    _ensure_dir()
    out = []
    for fname in os.listdir(STORE_DIR):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(STORE_DIR, fname)) as f:
            record = json.load(f)
        if record.get("selection_id") == selection_id:
            out.append(record)
    out.sort(key=lambda r: r.get("generated_at", ""))
    return out


def list_all_generations() -> list[dict]:
    """Used by document-wide stale/traceability views. Linear scan is fine
    at this scale (see APPROACH.md decision log #2 for the production
    caveat)."""
    _ensure_dir()
    out = []
    for fname in os.listdir(STORE_DIR):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(STORE_DIR, fname)) as f:
            out.append(json.load(f))
    out.sort(key=lambda r: r.get("generated_at", ""))
    return out


def list_generations_by_node(node_id: int) -> list[dict]:
    _ensure_dir()
    out = []
    for fname in os.listdir(STORE_DIR):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(STORE_DIR, fname)) as f:
            record = json.load(f)
        node_ids_in_record = {
            src["node_id"] for src in record.get("source_node_revisions", [])
        }
        if node_id in node_ids_in_record:
            out.append(record)
    out.sort(key=lambda r: r.get("generated_at", ""))
    return out
