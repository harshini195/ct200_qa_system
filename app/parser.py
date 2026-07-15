"""
Markdown -> tree parser for the CT-200 manual family of documents.

Design decisions (see APPROACH.md for full writeup):

1. Tree structure is built from markdown '#' depth ONLY. The numeric prefix
   (e.g. "3.4", "2.1.1.1") is extracted and stored as metadata but never used
   to decide nesting or ordering. This is deliberate: this document contains
   out-of-order numeric prefixes (3.4 appears before 3.3 in the file) and a
   level-skip (#### 2.1.1.1 nested directly under ### 2.1, no 2.1.1 exists).
   Trusting the numbers for structure would silently misfile both cases.

2. document order (order_in_document) is preserved separately from numeric
   order, because they are NOT the same thing in this file.

3. A post-parse consistency check (validate_numeric_consistency) flags any
   node whose numeric prefix implies a different parent than the one it was
   actually nested under by markdown depth. This does not "fix" anything
   (out of scope: generic markdown parser) but it means a structural anomaly
   is surfaced as a warning instead of silently accepted. See node 3.2 below.
"""

import re
import hashlib
from dataclasses import dataclass, field
from typing import Optional


HEADING_RE = re.compile(r'^(#{1,6})\s+(.*)$')
# Handles both "1. Device Overview" (top-level, trailing period) and
# "1.1 Intended Use" / "2.1.1.1 Battery Life..." (no trailing period).
# Found this inconsistency by testing the naive no-period regex against
# the real file: it silently failed to strip the number from every
# top-level (##) heading, leaving "1. Device Overview" as heading_text
# with heading_number=None. Caught by test_top_level_period_handling.
NUMBER_PREFIX_RE = re.compile(r'^(\d+(?:\.\d+)*)\.?\s+(.*)$')


@dataclass
class RawNode:
    level: int
    heading_number: Optional[str]
    heading_text: str
    body_lines: list = field(default_factory=list)
    children: list = field(default_factory=list)
    parent: Optional["RawNode"] = None
    order_in_document: int = 0
    node_key: str = ""  # assigned after parse, unique per node in this tree

    @property
    def body_text(self) -> str:
        return "\n".join(self.body_lines).strip("\n")

    @property
    def path_by_number(self) -> Optional[str]:
        """Dot-joined ancestor chain of numeric prefixes, if all ancestors
        (up to but excluding the synthetic root) have numbers."""
        if self.heading_number is None:
            return None
        return self.heading_number

    @property
    def path_by_text(self) -> str:
        """Fallback structural path using heading text + parent chain,
        used to match nodes when numeric prefixes are missing or unreliable."""
        chain = []
        node = self
        while node is not None and node.level != 0:
            chain.append(node.heading_text.strip().lower())
            node = node.parent
        return " > ".join(reversed(chain))


def content_hash(heading_text: str, body_text: str) -> str:
    normalized = (heading_text.strip().lower() + "\n" +
                  "\n".join(line.strip() for line in body_text.splitlines() if line.strip() != ""))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def parse_markdown(text: str) -> RawNode:
    lines = text.split("\n")
    root = RawNode(level=0, heading_number=None, heading_text="__root__")
    stack = [root]
    order_counter = 0

    for line in lines:
        m = HEADING_RE.match(line)
        if not m:
            stack[-1].body_lines.append(line)
            continue

        level = len(m.group(1))
        heading_raw = m.group(2).strip()

        num_match = NUMBER_PREFIX_RE.match(heading_raw)
        if num_match:
            heading_number = num_match.group(1)
            heading_text = num_match.group(2).strip()
        else:
            heading_number = None
            heading_text = heading_raw

        order_counter += 1
        node = RawNode(
            level=level,
            heading_number=heading_number,
            heading_text=heading_text,
            order_in_document=order_counter,
        )

        # Pop back to the nearest ancestor with a strictly smaller level.
        # This is what correctly handles the 2.1 -> 2.1.1.1 level-skip:
        # we don't require every intermediate level to exist, we only
        # require level(parent) < level(child).
        while stack[-1].level >= level and len(stack) > 1:
            stack.pop()

        node.parent = stack[-1]
        stack[-1].children.append(node)
        stack.append(node)

    _assign_node_keys(root)
    return root


def _assign_node_keys(root: RawNode) -> None:
    """Assign a unique key per node within this single parsed tree, so that
    duplicate heading text (e.g. two "Error Codes" sections) never collide.
    Key = order_in_document, which is unique by construction."""
    def walk(node):
        node.node_key = f"n{node.order_in_document}"
        for c in node.children:
            walk(c)
    walk(root)


def validate_numeric_consistency(root: RawNode) -> list[str]:
    """Flag nodes whose numeric prefix implies a parent different from the
    one they were actually nested under by markdown '#' depth.

    Example this catches in the real document: "#### 3.2 Cuff Inflation
    Sequence" is typed as a level-4 heading directly under "### 3.1 Powering
    On..." (level 3), so by markdown depth it nests as a CHILD of 3.1.
    But its own number "3.2" implies it should be a SIBLING of 3.1 (both
    children of section "3"). We do not silently "correct" this (that would
    require inventing structure the document doesn't have) -- we surface it
    as a warning so a human/QA reviewer knows the tree may not match
    authorial intent at this node.
    """
    warnings = []

    def expected_parent_prefix(number: str) -> Optional[str]:
        if "." not in number:
            return None  # top-level section, no numeric parent to check
        return number.rsplit(".", 1)[0]

    def walk(node: RawNode):
        if node.heading_number and node.parent and node.parent.heading_number:
            expected = expected_parent_prefix(node.heading_number)
            actual = node.parent.heading_number
            if expected is not None and not node.heading_number.startswith(actual + "."):
                warnings.append(
                    f"Node '{node.heading_number} {node.heading_text}' "
                    f"(order {node.order_in_document}) is nested under "
                    f"'{actual} {node.parent.heading_text}' by markdown heading "
                    f"depth, but its number implies parent prefix "
                    f"'{expected}'. Possible heading-level typo in source doc."
                )
        for c in node.children:
            walk(c)

    walk(root)
    return warnings


def flatten(root: RawNode) -> list[RawNode]:
    """Pre-order flat list of all non-root nodes."""
    out = []

    def walk(node):
        if node.level != 0:
            out.append(node)
        for c in node.children:
            walk(c)

    walk(root)
    return out
