"""
One-off script: render data/ct200_manual_v2.md as a PDF whose heading
font sizes match the tiers app/pdf_ingestion.py expects (22 / 16.5 / 12.9 /
11pt bold), so it can stand in for a genuine "v2 PDF" -- i.e. a PDF that
actually differs from ct200_manual.pdf, unlike the byte-identical one that
was removed from data/.

Not part of the shipped app; this is scaffolding for a demo scenario
("what if I only ever had PDFs, no markdown") requested separately from
the assignment itself.
"""

from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import mm

TITLE = ParagraphStyle("Title", fontName="Helvetica-Bold", fontSize=22.0, leading=26, spaceAfter=10)
H2 = ParagraphStyle("H2", fontName="Helvetica-Bold", fontSize=16.5, leading=20, spaceBefore=10, spaceAfter=6)
H3 = ParagraphStyle("H3", fontName="Helvetica-Bold", fontSize=12.9, leading=16, spaceBefore=8, spaceAfter=5)
H4 = ParagraphStyle("H4", fontName="Helvetica-Bold", fontSize=11.0, leading=14, spaceBefore=6, spaceAfter=4)
TABLE_HEADER = ParagraphStyle("TableHeader", fontName="Helvetica-Bold", fontSize=11.0, leading=14, spaceBefore=4, spaceAfter=2)
BODY = ParagraphStyle("Body", fontName="Helvetica", fontSize=11.0, leading=14, spaceAfter=6)


def build(md_path: str, out_path: str):
    with open(md_path) as f:
        raw_lines = [l.rstrip("\n") for l in f.readlines()]

    story = []
    in_table = False
    table_header_done = False

    for line in raw_lines:
        stripped = line.strip()
        stripped = stripped.replace("\u2011", "-")  # non-breaking hyphen has no glyph in default Helvetica

        if not stripped:
            continue
        if stripped.startswith("<!--"):
            continue  # HTML comments never render in a real PDF -- drop, don't fake

        if stripped.startswith("# "):
            story.append(Paragraph(stripped[2:], TITLE))
            continue
        if stripped.startswith("#### "):
            story.append(Paragraph(stripped[5:], H4))
            continue
        if stripped.startswith("### "):
            story.append(Paragraph(stripped[4:], H3))
            continue
        if stripped.startswith("## "):
            story.append(Paragraph(stripped[3:], H2))
            in_table = False
            table_header_done = False
            continue

        if stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if all(set(c) <= {"-"} for c in cells):
                continue  # markdown table separator row (|---|---|), not real content
            text = "  ".join(cells)
            if not table_header_done:
                story.append(Paragraph(text, TABLE_HEADER))
                table_header_done = True
                in_table = True
            else:
                story.append(Paragraph(text, BODY))
            continue

        in_table = False
        table_header_done = False
        story.append(Paragraph(stripped, BODY))

    doc = SimpleDocTemplate(out_path, pagesize=A5,
                             leftMargin=15 * mm, rightMargin=15 * mm,
                             topMargin=12 * mm, bottomMargin=12 * mm)
    doc.build(story)


if __name__ == "__main__":
    import sys
    build(sys.argv[1], sys.argv[2])
