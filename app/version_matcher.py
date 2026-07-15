"""
Matches nodes in a newly parsed tree against the NodeRevisions of the most
recent existing version of the same document, so that semantically
unchanged sections keep the same logical Node.id across versions.

Strategy (in priority order), see APPROACH.md for full justification and
known failure modes:

  1. Match by heading_number, if the new node has one and exactly one old
     node in the previous version shares that same heading_number.
     Numeric prefixes are the most stable identity signal in a regulated
     document -- section "4.2" is expected to keep meaning "Error Codes"
     across revisions even if the prose changes.

  2. Fallback: match by path_by_text (heading text + ancestor chain of
     heading text), for nodes with no heading_number, or where the numeric
     match was ambiguous/not found. This catches the (hypothetical) case of
     a renumbered-but-not-retitled section.

  3. Anything in the new tree with no match -> new Node.
     Anything in the old version with no match -> not carried forward
     (we don't delete history, we just don't create a new NodeRevision for
     it in the new version; it remains queryable at its old version).

Known failure mode (stated explicitly, not hidden): if a section is BOTH
renumbered AND retitled in the same release (e.g. "4.2 Error Codes" becomes
"4.5 Fault Codes"), neither signal matches and it will be treated as a
delete + add, i.e. its history is severed. This is a real limitation of a
heuristic matcher and would require a human-confirmed remap to fix.
"""

from .parser import RawNode


def match_nodes(old_revisions: list, new_raw_nodes: list[RawNode]) -> dict:
    """
    old_revisions: list of NodeRevision ORM objects from the previous version
    new_raw_nodes: flattened list of RawNode from the newly parsed document

    Returns: dict mapping RawNode.node_key -> matched NodeRevision (old) or None
    """
    by_number: dict[str, list] = {}
    by_text_path: dict[str, list] = {}

    for rev in old_revisions:
        if rev.heading_number:
            by_number.setdefault(rev.heading_number, []).append(rev)
        text_path = _old_revision_text_path(rev, old_revisions)
        by_text_path.setdefault(text_path, []).append(rev)

    result = {}
    used_old_ids = set()

    for node in new_raw_nodes:
        matched = None

        if node.heading_number and node.heading_number in by_number:
            candidates = [r for r in by_number[node.heading_number] if r.id not in used_old_ids]
            if len(candidates) == 1:
                matched = candidates[0]

        if matched is None:
            text_path = node.path_by_text
            if text_path in by_text_path:
                candidates = [r for r in by_text_path[text_path] if r.id not in used_old_ids]
                if len(candidates) == 1:
                    matched = candidates[0]

        if matched is not None:
            used_old_ids.add(matched.id)

        result[node.node_key] = matched

    return result


def _old_revision_text_path(rev, all_revisions_in_version) -> str:
    """Reconstruct heading-text path for an old NodeRevision by walking
    parent_revision_id pointers within the same version's revision set."""
    by_id = {r.id: r for r in all_revisions_in_version}
    chain = []
    current = rev
    while current is not None:
        chain.append(current.heading_text.strip().lower())
        current = by_id.get(current.parent_revision_id) if current.parent_revision_id else None
    return " > ".join(reversed(chain))
