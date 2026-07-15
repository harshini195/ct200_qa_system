# CT-200 QA Traceability System

Turns the CardioTrack CT-200 manual into a browsable, versioned tree, and
generates LLM-based QA test-case ideas from selected sections while keeping
staleness/traceability valid as the document changes.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # optional: add GROQ_API_KEY to use a real LLM
```

Without `GROQ_API_KEY` set, the LLM generation endpoint runs in **mock
mode** (deterministic placeholder test cases) so the whole flow — including
staleness detection — is fully demoable offline.

## Run

```bash
uvicorn app.main:app --reload
```

API docs (interactive): http://127.0.0.1:8000/docs

## Run tests

```bash
pytest tests/ -v
```

12 tests: 8 parser unit tests targeting the specific irregularities found in
the manual (duplicate headings, heading-level skip, out-of-order numbering,
inconsistent numeral-period formatting, table body preservation, a
heading-level/number mismatch, a leading HTML comment), plus 4 versioning
integration tests (unchanged-node identity preserved, changed-node hash
detected, new-node handling, v1 not destroyed by v2 ingestion).

## Triggering the v1 → v2 re-ingestion flow specifically

```bash
# 1. Ingest v1
curl -X POST http://127.0.0.1:8000/documents/ct200_manual/versions \
  -H "Content-Type: application/json" \
  -d '{"file_path": "data/ct200_manual.md"}'

# 2. Ingest v2 as a new version of the SAME document (v1 is not deleted)
curl -X POST http://127.0.0.1:8000/documents/ct200_manual/versions \
  -H "Content-Type: application/json" \
  -d '{"file_path": "data/ct200_manual_v2.md"}'
```

Both responses include `parser_warnings` — e.g. a flag that section 3.2 is
nested by markdown depth one level deeper than its own numbering implies
(see APPROACH.md).

## Full walkthrough (versioning + staleness end-to-end, not just happy-path CRUD)

```bash
# Browse: search for a node
curl "http://127.0.0.1:8000/documents/ct200_manual/search?q=Error%20Codes"
# -> note the node_id of "4.2 Error Codes" (the E1-E6 table)

# Fetch that node as it existed in v1
curl "http://127.0.0.1:8000/documents/ct200_manual/nodes/<node_id>?version=1"

# Create a selection pinned to v1 (so it survives future re-ingestion)
curl -X POST "http://127.0.0.1:8000/selections?document_name=ct200_manual" \
  -H "Content-Type: application/json" \
  -d '{"name": "error-code-tests", "node_ids": [<node_id>], "version": 1}'

# Generate QA test cases from that selection
curl -X POST "http://127.0.0.1:8000/selections/1/generate"

# Retrieve generated test cases WITH staleness flags
curl "http://127.0.0.1:8000/selections/1/test-cases"
# -> "stale": true, because v2 changed the E3 deflation time (2s -> 1.5s)
#    and added an E6 row to this exact table, after the generation was made
#    from v1's text.

# See exactly what changed, for a human to judge severity
curl "http://127.0.0.1:8000/documents/ct200_manual/nodes/<node_id>/diff?from_version=1&to_version=2"

# Retrieve by node instead of by selection
curl "http://127.0.0.1:8000/nodes/<node_id>/test-cases"
```

## Dev scripts (not part of the graded API surface)

`scratch/` has two convenience scripts, not new endpoints:
- `print_tree.py` -- recursively walks the existing Browse API
  (`/sections` + `/nodes/{id}`) and prints the whole document tree, for
  eyeballing structure while testing. Run with the server up:
  `python scratch/print_tree.py ct200_manual`
- `capture_llm_example.py` -- runs the real LLM client against a live
  Groq key to capture a genuine request/response transcript, referenced
  in APPROACH.md's LLM section.

## API summary

| Method | Path | Purpose |
|---|---|---|
| POST | `/documents/{name}/versions` | Ingest a markdown file as a new version |
| GET | `/documents/{name}/sections` | List top-level nodes (version param, default latest) |
| GET | `/documents/{name}/nodes/{node_id}` | Get node + children + body + hash |
| GET | `/documents/{name}/search?q=` | Search headings/body text |
| GET | `/documents/{name}/nodes/{node_id}/diff` | Diff a node across two versions |
| POST | `/selections?document_name=` | Create a version-pinned selection |
| GET | `/selections/{id}` | View a selection |
| POST | `/selections/{id}/generate` | Generate test cases via LLM (or mock) |
| GET | `/selections/{id}/test-cases` | Retrieve generations + staleness |
| GET | `/nodes/{node_id}/test-cases` | Retrieve generations by node + staleness |

This list is deliberately limited to endpoints that map to a numbered item
in the assignment spec (Browse API, Selection API, Retrieval API). An
earlier version of this project also had document-wide `/versions`,
`/stale`, and `/traceability` views — useful, but not requested by the
spec, so they were removed to keep the API's scope legible against what
was actually asked. See APPROACH.md for the reasoning.

## Tech stack

- FastAPI + Pydantic + SQLAlchemy + SQLite for the tree/versions/selections
- A local JSON-file store (`generations_store/`) instead of MongoDB for
  generated test cases — justified in APPROACH.md
- Groq (OpenAI-compatible endpoint) for LLM calls, with a mock fallback

See **APPROACH.md** for the data model, parsing decisions, version-matching
strategy and its known failure modes, LLM retry design, and the decision
log.
