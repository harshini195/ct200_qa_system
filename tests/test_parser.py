import os
import pytest
from app.parser import parse_markdown, flatten, validate_numeric_consistency

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def load(name):
    with open(os.path.join(DATA_DIR, name)) as f:
        return f.read()


@pytest.fixture(scope="module")
def v1_tree():
    return parse_markdown(load("ct200_manual.md"))


@pytest.fixture(scope="module")
def v1_nodes(v1_tree):
    return flatten(v1_tree)


def find_all_by_text(nodes, text):
    return [n for n in nodes if n.heading_text.strip().lower() == text.strip().lower()]


def find_by_number(nodes, number):
    for n in nodes:
        if n.heading_number == number:
            return n
    return None


# --- Irregularity 1: duplicate heading text at different locations -----

def test_duplicate_heading_text_produces_distinct_nodes(v1_nodes):
    """'Error Codes' appears twice (4.2 and 7.1). They must be two distinct
    parsed nodes with different parents/keys, not merged into one."""
    matches = find_all_by_text(v1_nodes, "Error Codes")
    assert len(matches) == 2
    assert matches[0].node_key != matches[1].node_key
    numbers = {m.heading_number for m in matches}
    assert numbers == {"4.2", "7.1"}
    # and their parents must differ (different sections)
    assert matches[0].parent.heading_number != matches[1].parent.heading_number


# --- Irregularity 2: heading level skip (#### directly under ###, no h3.1) -

def test_level_skip_nests_under_nearest_ancestor(v1_nodes):
    """#### 2.1.1.1 Battery Life... is a level-4 heading with no level-3.1
    node in between; it must nest directly under ### 2.1, not error out or
    get silently dropped."""
    battery_node = find_by_number(v1_nodes, "2.1.1.1")
    assert battery_node is not None
    assert battery_node.level == 4
    assert battery_node.parent.heading_number == "2.1"


# --- Irregularity 3: numeric prefixes out of document order -------------

def test_out_of_order_numbering_preserves_true_document_order(v1_nodes):
    """3.4 Auto Shutoff physically appears in the file BEFORE 3.3 Result
    Display. The parser must preserve real document order (not silently
    resort by numeric prefix), since order_in_document is a distinct,
    trustworthy field from heading_number.

    Note: 3.2 is NOT a direct child of section 3 here -- it's nested one
    level deeper, under 3.1, because "#### 3.2 Cuff Inflation Sequence" is
    typed as a level-4 heading in the source (see
    test_numeric_consistency_check_flags_the_32_anomaly). That's a separate,
    already-flagged anomaly; this test only checks ordering among 3's
    actual structural children."""
    section_3 = find_by_number(v1_nodes, "3")
    child_numbers_in_doc_order = [c.heading_number for c in section_3.children]
    assert child_numbers_in_doc_order == ["3.1", "3.4", "3.3"]

    n31 = find_by_number(v1_nodes, "3.1")
    assert [c.heading_number for c in n31.children] == ["3.2"]


# --- Irregularity 4: top-level headings use "N." (period), subheadings "N.N" (no period) -

def test_top_level_period_is_stripped_consistently(v1_nodes):
    """Top-level headings are written as '## 1. Device Overview' (number
    followed by a period) while sub-headings are '### 1.1 Intended Use'
    (no period). A regex assuming only one style will fail to extract the
    number from top-level headings. Confirm both styles parse to clean
    heading_number / heading_text with no leftover punctuation."""
    top_level = find_by_number(v1_nodes, "1")
    assert top_level is not None
    assert top_level.heading_text == "Device Overview"
    assert not top_level.heading_text.startswith(".")

    sub = find_by_number(v1_nodes, "1.1")
    assert sub is not None
    assert sub.heading_text == "Intended Use"


# --- Irregularity 5: table content inside a node's body must survive verbatim -

def test_table_body_content_not_corrupted(v1_nodes):
    error_table_node = find_by_number(v1_nodes, "4.2")
    assert error_table_node is not None
    assert "| Code | Meaning | Device Behavior |" in error_table_node.body_text
    assert "| E1 |" in error_table_node.body_text
    assert "| E5 |" in error_table_node.body_text


# --- Irregularity 6: heading-level/number mismatch is flagged, not silently accepted -

def test_numeric_consistency_check_flags_the_32_anomaly(v1_tree):
    """#### 3.2 Cuff Inflation Sequence is typed as level-4 (child of 3.1 by
    markdown depth) but its own number '3.2' implies it should be a sibling
    of 3.1 (both children of section 3). We don't silently 'fix' this --
    we flag it as a warning."""
    warnings = validate_numeric_consistency(v1_tree)
    assert any("3.2" in w and "3.1" in w for w in warnings)


# --- HTML comment before first heading doesn't crash / get misattached ---

def test_leading_html_comment_attaches_to_h1_title_node(v1_tree):
    """The '<!-- TODO: confirm with regulatory -->' comment sits between the
    H1 document title and the first H2 section. It must attach as body text
    of the H1 title node (the deepest open node at that point), not get
    silently dropped or bleed into the first real section (1. Device
    Overview)."""
    h1_title_node = v1_tree.children[0]
    assert h1_title_node.level == 1
    assert "TODO" in h1_title_node.body_text

    first_real_section = h1_title_node.children[0]
    assert first_real_section.heading_number == "1"
    assert "TODO" not in first_real_section.body_text


# --- Cross-doc sanity: v2 has genuinely new content (5.3), not just edits -

def test_v2_has_new_node_not_present_in_v1(v1_nodes):
    v2_nodes = flatten(parse_markdown(load("ct200_manual_v2.md")))
    assert find_by_number(v1_nodes, "5.3") is None
    v2_new = find_by_number(v2_nodes, "5.3")
    assert v2_new is not None
    assert v2_new.heading_text == "Data Export"
