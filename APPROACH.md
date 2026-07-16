# Approach Document

## Data model

- `Document` — one row per named document ("ct200_manual").
- `DocumentVersion` — one row per ingestion, `version_number` auto-increments
  per document. Never deleted.
- `Node` — the **stable logical identity** of a section. Persists across
  versions. Deliberately thin (just an id + which document + which version
  it first appeared in) — everything else is per-version.
- `NodeRevision` — one row per `(Node, DocumentVersion)` it appears in. Holds
  heading text/number, level, document order, parent pointer (to another
  `NodeRevision`, not another `Node` — parent/child structure is per-version
  since a node's position could theoretically move), body text, and a
  content hash.
- `Selection` / `SelectionNode` — a named set of `(node_id, version_id,
  node_revision_id)` triples. Pinning to `node_revision_id` specifically
  (not just `version_id`) means a selection resolves to exact stored text
  even if I later change how text is reconstructed.

Generated test cases live in a separate JSON-file store, linked by
`selection_id` and a list of `{node_id, version_id, content_hash}` — the
content hash *at generation time* is what staleness checks compare against.

## Tree-parsing decisions

I read the file manually first, then wrote a script to print
`(level, heading_number, heading_text, order_in_document)` for every heading
in document order, before writing any tree logic. That surfaced:

1. **Duplicate heading text** ("Error Codes" at both 4.2 and 7.1). Handled
   by never using heading text as an identity key during parsing — every
   `RawNode` gets a key from `order_in_document`, which is unique by
   construction.
2. **Heading-level skip** (`#### 2.1.1.1` directly under `### 2.1`, no
   `2.1.1` heading exists). Handled by nesting on markdown `#` depth alone
   (pop the stack until `stack[-1].level < level`), never assuming every
   intermediate level exists.
3. **Numeric prefixes out of document order** (`3.4 Auto Shutoff` appears
   before `3.3 Result Display` in the file). Found by literally reading the
   file top to bottom — not something a script would flag unless you
   already suspect it. Handled by never sorting by numeric prefix;
   `order_in_document` is the only ordering signal trusted for display.
4. **Inconsistent numeral punctuation** — top-level headings are written
   `## 1. Device Overview` (number + period), sub-headings are
   `### 1.1 Intended Use` (no period). Found this by testing my first regex
   (`^(\d+(?:\.\d+)*)\s+`) against the real file and noticing every
   top-level heading came out with `heading_number=None` and
   `heading_text="1. Device Overview"` — the leftover `1.` was never
   stripped. Fixed by making the trailing period optional in the regex.
   This is a good example of "output that looked wrong" catching a bug I
   wouldn't have found by reading the doc alone.
5. **A genuine heading-level typo**: `#### 3.2 Cuff Inflation Sequence` is
   typed as h4, nesting it as a *child of 3.1* by markdown depth — but its
   own number (`3.2`) implies it should be a *sibling* of 3.1 (both children
   of section `3`). I found this by writing
   `validate_numeric_consistency()`, a post-parse pass that checks whether
   each node's numeric-prefix-implied parent matches its actual structural
   parent, and it flagged exactly this node on first run. I chose **not**
   to auto-correct it (that's outside "no generic markdown parser" scope,
   and inventing structure the source doesn't literally have is exactly the
   "looks clean but is quietly wrong" failure mode the assignment warns
   about) — instead the mismatch is surfaced as a warning string returned
   from the ingestion endpoint, so a human decides what to do with it.
6. **HTML comment before the first heading**: `<!-- TODO: confirm with
   regulatory -->` sits between the H1 title and the first H2 section. It
   attaches as body text of the H1 node (the deepest open node at that
   point in the stack) — not silently dropped, not bled into the first real
   section. Confirmed with a unit test.
7. **Tables as body content**: table rows are just body lines like any
   other line; I don't parse table structure, I just verify (via test) that
   the exact table syntax survives byte-for-byte in `body_text`.

## Version-matching strategy

Priority order: (1) match by identical `heading_number` if unambiguous
against the previous version's revisions, (2) fall back to a full
heading-text-plus-ancestor-chain path match, (3) anything left in the new
tree is a new `Node`; anything left in the old version with no match simply
isn't carried forward (its history stays queryable at its old version, it's
never deleted).

**Known failure mode, stated plainly**: if a section is renumbered *and*
retitled in the same release (e.g. `4.2 Error Codes` → `4.5 Fault Codes`),
neither signal matches, and my matcher treats it as delete+add — the
generation history for that content is severed even though a human would
recognize it as "the same section, moved." Fixing this properly would need
either a human-confirmed remap step or a fuzzier text-similarity match
(e.g. body-text Jaccard/cosine similarity above some threshold), which I
did not implement given the assignment's own instruction not to over-build
a generic matcher.

## LLM prompt design + structured-output/retry strategy

Prompt asks for strict JSON (`{"test_cases": [...]}`, 3–5 items, each with
`title`/`steps`/`expected_result`), explicitly instructing the model to use
exact numeric values from the source text rather than inventing its own.
Response is validated against a Pydantic model. On failure to parse/validate:
one retry with an explicit "your last reply was invalid, return ONLY JSON"
follow-up including the error message. If that also fails, the system does
**not** raise or silently drop the attempt — it persists a record with
`status: "failed"` and the raw text, because a generation attempt that
happened and produced nothing usable is itself a fact worth keeping for
traceability, not something to hide.

**Idempotency policy**: resubmitting the same selection creates a **new**
generation record every time, rather than overwriting. Reasoning: LLM output
isn't deterministic, a user may legitimately want to try again, and
overwriting would destroy the record of exactly what was shown to someone
at a specific point in time — which directly conflicts with the
traceability goal of the whole assignment.

## Staleness detection: what it does, and its honest limits

Mechanism: every `NodeRevision` stores a content hash (heading + body text).
A generation stores the hash of every source node *at generation time*. At
retrieval, `_attach_staleness` recomputes each source node's *current*
latest-revision hash and compares. Any mismatch → `stale: true`, surfaced
per-source in `staleness_detail` so a caller can see exactly which source
node(s) changed, plus the diff endpoint to see *what* changed.

**The honest limit, asked directly by the assignment: does a one-word
wording change get treated the same as a changed pressure threshold?**
Yes — today it does, and I think that's the wrong long-term answer for a
medical device, but I chose it deliberately over the alternative for this
submission. A hash has no concept of *how much* meaning changed; "must"
becoming "should" and "180 mmHg" becoming "220 mmHg" produce equally
binary `stale: true` flags. I considered bolting on a cheap heuristic
(regex-extract numbers from old/new body text, flag "numeric change" vs
"wording only") and deliberately didn't, for a specific reason: a
numeric-diff heuristic would give **false confidence** on exactly the
changes that matter most in this domain — a changed contraindication, a
changed "should" → "must", a removed safety caveat — none of which touch a
number at all, but all of which are more clinically significant than, say,
a pressure value going from 299 to 300. Shipping a severity label that's
silently wrong on the highest-stakes category of change seemed worse than
shipping no severity label and pointing the human at the actual diff
instead. So the diff endpoint (`GET .../nodes/{id}/diff`) is the real
judgment layer in this system, by design — staleness answers "did
anything change," the diff answers "what," and a human decides whether
that "what" matters. That division of labor is a stated design choice,
not an oversight; see "What I'd do differently" below for the narrower,
opt-in version of a severity hint I'd actually be willing to ship.

## PDF ingestion (bonus input path)

Not part of the assignment spec, but the manual is also provided as a
rendered PDF with no accompanying markdown, so `POST
/documents/{name}/versions` also accepts a `file_path` ending in `.pdf`.
`app/pdf_ingestion.py` reconstructs markdown-equivalent heading structure
from the PDF's font size/weight (title/H2/H3 tiers are unambiguous by
size; a genuinely ambiguous tier — bold table headers render at the exact
same size as real level-4 headings — is disambiguated using the same
numeric-prefix pattern the parser already relies on) and feeds the result
into the *same* `parse_markdown`, so there's one tree-building
implementation for both input formats, not two. Its docstring states the
heuristic's limits plainly (a table with a numeric-looking bold header
cell would defeat it) rather than presenting it as a general solution.
`tests/test_pdf_ingestion.py` checks the PDF-derived tree is node-for-node
identical to the markdown-derived one, including preserving the same
heading-level-typo warning for node 3.2.

## Decision log

**1. What's the one part of this system most likely to silently give wrong
results without erroring?**
The version matcher's text-path fallback. If two *different* sections
happen to have the same heading text under parents with the same heading
text (unlikely in this doc, plausible in a larger one), the fallback match
could silently pair the wrong nodes — no error, just wrong lineage. I'd
catch it by adding an assertion that flags (rather than silently accepts)
any fallback match where the resulting body-text similarity is below some
threshold, since a "match" that changes both the heading and the content
almost entirely is more likely a coincidence than a real edit.

**2. Where did I choose simplicity over correctness because of time, and
what would break first in production?**
The JSON-file generation store has no locking and does a full directory
scan per query. It works fine for the scale of this assignment
(dozens/hundreds of generations, one process) and I chose it explicitly to
avoid the setup friction of standing up MongoDB for a take-home. In
production with concurrent writers it would break first — two simultaneous
writes are fine (unique UUID filenames), but the linear-scan reads would
degrade badly past a few thousand records, and there's no transactional
guarantee tying a generation write to the SQLite read that produced its
source hashes. I'd replace this with Mongo (or even just a proper SQL table
with an index on `selection_id`/`node_id`) before any real usage.

**3. Name one input I did not handle, and what the system does when it sees
it.**
A section renumbered *and* retitled in the same version bump (see the
version-matching failure mode above). My system does not detect this case
at all — it silently treats the old section as removed and the new one as
brand new. This is the one limitation I'd flag most strongly to a reviewer,
because unlike the other issues in this doc (which are surfaced as
warnings), this one produces no warning at all; it just quietly severs
lineage. If I had more time, this is the first thing I'd instrument with a
warning (e.g. "N old nodes had no version-2 match; N new nodes had no
version-1 match" printed at ingestion time so a human notices the counts
don't look like a clean edit).

## A deliberate omission: no "requirement" abstraction

I considered adding a `Requirement` layer between sections and test cases
(section → requirement → test case, with structured per-field diffs like
`{"field": "battery cycles", "old": "300", "new": "250"}`) but chose not
to. Populating that layer needs an extraction step -- turning free-form
prose into discrete, labeled requirement statements -- which is either
fragile per-document regex or a *second* LLM extraction pipeline with its
own malformed-output/retry/validation story on top of the test-case
generation pipeline I already have. Traceability in this system is
deliberately **section → test case** (via `node_id`), which is what's
asked for; the requirement layer is real future-work, not something I'd
want to half-build under time pressure.

## A deliberate scope trim: no document-wide views

An earlier version of this API also exposed `GET /documents/{name}/versions`
(list all versions), `GET /documents/{name}/versions/{n}` (version
metadata), `GET /documents/{name}/stale` (every stale generation across a
document), and `GET /documents/{name}/traceability` (a document-wide
node → test case view). These are genuinely useful — the per-selection
and per-node staleness/traceability endpoints require already knowing a
`selection_id` or `node_id`, so there's no way to ask "what across this
whole document needs re-review" without already knowing where to look.

I removed them anyway. None of the four map to a numbered item in the
assignment spec (Browse API, Selection API, Retrieval API); they were my
own additions on top of what was asked. Keeping the API's surface area
matched 1:1 to the spec's numbered requirements makes it easier to defend
in review — every endpoint has a specific line item it answers, and there's
no ambiguity about whether "extra" functionality was actually requested.
If document-wide staleness turned out to matter in practice, it's a small,
well-scoped addition on top of the existing per-node/per-selection logic
(the CRUD helpers were straightforward: filter document node ids, then
scan generations for a source-node match).

## What I'd do differently with more time

- Add the fuzzy-similarity safety net described in decision log #1.
- Make ingestion emit an explicit summary (`X unchanged, Y changed, Z new,
  W removed`) rather than only per-node warnings, so a human reviewing a
  re-ingestion sees the shape of the change at a glance.
- Add a severity hint to the diff endpoint (e.g. "numeric value changed" vs
  "wording only") using a simple regex-based number-diff, while being
  explicit that this is a heuristic, not a judgment of clinical
  significance — that still requires a human.
