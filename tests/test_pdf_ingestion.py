import os

from app.parser import parse_markdown, flatten, validate_numeric_consistency
from app.pdf_ingestion import pdf_to_markdown

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def _pdf_path():
    return os.path.join(DATA_DIR, "ct200_manual.pdf")


def _md_path():
    return os.path.join(DATA_DIR, "ct200_manual.md")


def test_pdf_reconstruction_matches_markdown_tree_shape():
    """The PDF has no '#' characters -- headings are re-derived from font
    size/weight. This checks the reconstruction lands on the exact same
    (level, heading_number, heading_text) sequence as the hand-authored
    markdown source, not just a similar-looking tree."""
    with open(_md_path()) as f:
        md_root = parse_markdown(f.read())
    pdf_root = parse_markdown(pdf_to_markdown(_pdf_path()))

    md_nodes = flatten(md_root)
    pdf_nodes = flatten(pdf_root)

    assert len(md_nodes) == len(pdf_nodes)
    for a, b in zip(md_nodes, pdf_nodes):
        assert (a.level, a.heading_number, a.heading_text) == (
            b.level,
            b.heading_number,
            b.heading_text,
        )


def test_pdf_reconstruction_preserves_the_heading_level_typo_warning():
    """3.2 Cuff Inflation Sequence renders at the same font tier as the true
    level-4 heading 2.1.1.1 in the PDF -- this is the same authorial
    mistake the markdown source has (see APPROACH.md), not something this
    module should paper over. The structural-consistency warning must
    still fire."""
    pdf_root = parse_markdown(pdf_to_markdown(_pdf_path()))
    warnings = validate_numeric_consistency(pdf_root)
    assert any("3.2" in w for w in warnings)


def test_pdf_bold_table_headers_are_not_misread_as_level4_headings():
    """Bold table header rows ('Parameter Value', 'Code Meaning Device
    Behavior') render at the exact same size/weight as real level-4
    headings. They must stay body text -- disambiguated by the numeric
    prefix check, not swallowed as extra tree nodes."""
    pdf_root = parse_markdown(pdf_to_markdown(_pdf_path()))
    nodes = flatten(pdf_root)
    heading_texts = {n.heading_text for n in nodes}
    assert "Parameter Value" not in heading_texts
    assert "Code Meaning Device Behavior" not in heading_texts


def test_pdf_wrapped_title_merges_into_a_single_level1_node():
    """The document title wraps across three physical lines in the PDF
    render but must collapse to one level-1 heading, matching the
    markdown source's single '# ...' title line."""
    pdf_root = parse_markdown(pdf_to_markdown(_pdf_path()))
    level1_nodes = [n for n in flatten(pdf_root) if n.level == 1]
    assert len(level1_nodes) == 1
    assert level1_nodes[0].heading_text.startswith("CardioTrack CT-200")
