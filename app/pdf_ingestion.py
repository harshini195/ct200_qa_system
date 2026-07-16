"""
PDF -> markdown-equivalent text, for the case where only a rendered PDF of
the CT-200 manual is available (no source .md).

Why this exists: `parser.parse_markdown` builds the document tree from
markdown '#' depth (see parser.py's module docstring for why numeric
prefixes alone can't be trusted for structure in this document family).
A PDF has no '#' characters -- structure has to be re-derived from
typography (font size / bold) before the existing parser can run at all.
Rather than write a second, parallel tree-builder, this module's job is
narrow: reconstruct a markdown string with the right '#' counts and
heading text, then hand it to the *existing* `parse_markdown`. This keeps
one tree-building implementation, one set of parser unit tests, and one
version-matching path for both source formats.

Font-size tiers observed in the CT-200 PDF (see APPROACH.md-style notes
below for how these were derived, not just asserted):

    22.0 pt bold  -> document title              (markdown '#')
    16.5 pt bold  -> top-level section (e.g. "1.") (markdown '##')
    12.9 pt bold  -> sub-section (e.g. "1.1")      (markdown '###')
    11.0 pt bold  -> ambiguous tier, see below      (markdown '####' or body)
    11.0 pt plain -> body text (incl. table rows)

The 11.0pt-bold tier is genuinely ambiguous: bold table header rows
("Parameter Value", "Code Meaning Device Behavior") render at the exact
same size/weight as the two real level-4 headings ("2.1.1.1 Battery Life
Under Typical Use", "3.2 Cuff Inflation Sequence"). Font metadata alone
cannot distinguish them -- this is a real information loss versus the
markdown source, not an extraction bug. The heuristic used here is: a
bold 11.0pt line is treated as a heading only if its text matches the
same numeric-prefix pattern the markdown parser already recognizes
(`NUMBER_PREFIX_RE`); table header rows in this document never start with
a numeric prefix, so this happens to fully disambiguate them *for this
document*. It is a heuristic, not a guarantee -- a future table with a
numeric-looking header cell (e.g. "1. Item") would defeat it, and that
limitation is worth flagging to a reviewer rather than hiding.

Note also that "3.2 Cuff Inflation Sequence" lands in the *same* font-size
tier as "2.1.1.1 Battery Life...", even though its own numeric prefix
("3.2") implies a shallower nesting depth than "2.1.1.1" does. That's not
a bug in this module -- it reflects the same authorial mistake the
markdown source has (see parser.py / APPROACH.md item 5: "3.2" is
formatted one level too deep). Reconstructing both as markdown '####'
faithfully reproduces that mistake instead of papering over it, so
`validate_numeric_consistency` still flags node 3.2 exactly as it does
for the markdown source.

One thing a PDF cannot give back at all: the HTML comment
`<!-- TODO: confirm with regulatory -->` that sits before the first
heading in the markdown source. Comments don't render, so there is
nothing in the PDF to recover it from. That's a genuine, permanent gap
versus the markdown version, not something this module tries to
fake.
"""

import re

import pdfplumber

from .parser import NUMBER_PREFIX_RE

TITLE_SIZE = 22.0
LEVEL2_SIZE = 16.5
LEVEL3_SIZE = 12.9
LEVEL4_SIZE = 11.0

_SIZE_TOL = 0.3  # font sizes are reported as floats; compare with a small tolerance


def _size_matches(actual: float, target: float) -> bool:
    return abs(actual - target) <= _SIZE_TOL


def _group_words_by_line(words: list, tol: float = 3.0) -> list:
    """Cluster words into visual lines using a tolerance window on the
    'top' coordinate, rather than naive rounding.

    Naive rounding (e.g. `round(top)`) can split a single visual line into
    two: this document renders some hyphen glyphs a fraction of a point
    off the surrounding text's baseline (a font-substitution artifact --
    the hyphen comes from a different embedded font than the letters
    around it), which rounds to a different integer and creates a
    spurious extra "line" containing just a stray '-'. That in turn
    desynchronizes this function's line count from
    `page.extract_text()`'s line count, which is what this module uses to
    recover clean (properly dehyphenated) body text. Clustering by
    tolerance instead of exact/rounded position avoids that.
    """
    words = sorted(words, key=lambda w: w["top"])
    lines: list = []
    current: list = []
    current_top = None
    for w in words:
        if current and abs(w["top"] - current_top) > tol:
            lines.append(current)
            current = []
        current.append(w)
        current_top = current[0]["top"]  # anchor to first word so drift doesn't accumulate
    if current:
        lines.append(current)
    for line in lines:
        line.sort(key=lambda w: w["x0"])
    return lines


def _classify_page(page) -> list[tuple[float, bool, str]]:
    """Return (font_size, is_bold, text) for each visual line on a page.

    Text comes from `page.extract_text()` (handles hyphenation/spacing
    correctly); font metadata comes from `page.extract_words()` grouped
    into the same line order. The two are zipped positionally rather than
    matched by content, so a page where the two disagree on line count
    must be caught explicitly -- silently zipping mismatched lists would
    misattribute font metadata to the wrong text.
    """
    words = page.extract_words(extra_attrs=["size", "fontname"])
    meta_lines = _group_words_by_line(words)
    clean_lines = (page.extract_text(x_tolerance=1) or "").split("\n")
    clean_lines = [l for l in clean_lines if l.strip() != ""]
    meta_lines = [l for l in meta_lines if l]

    if len(meta_lines) != len(clean_lines):
        raise ValueError(
            f"Line count mismatch reconstructing heading structure from PDF: "
            f"{len(meta_lines)} font-metadata lines vs {len(clean_lines)} "
            f"text lines. Falling back is unsafe here because it would "
            f"silently mis-tag which lines are headings; this page needs "
            f"manual inspection of the PDF layout."
        )

    out = []
    for meta_words, text in zip(meta_lines, clean_lines):
        size = round(max(w["size"] for w in meta_words), 1)
        bold = any("Bold" in w["fontname"] for w in meta_words)
        out.append((size, bold, text))
    return out


def _heading_prefix(size: float, bold: bool, text: str):
    """Return the markdown '#' prefix for a classified line, or None if it's
    body text."""
    if not bold:
        return None
    if _size_matches(size, TITLE_SIZE):
        return "#"
    if _size_matches(size, LEVEL2_SIZE):
        return "##"
    if _size_matches(size, LEVEL3_SIZE):
        return "###"
    if _size_matches(size, LEVEL4_SIZE) and NUMBER_PREFIX_RE.match(text):
        return "####"
    return None


def pdf_to_markdown(path: str) -> str:
    """Reconstruct a markdown string (heading '#' depth + body text) from
    the CT-200 PDF, suitable for passing straight into
    `parser.parse_markdown`.
    """
    classified: list = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for size, bold, text in _classify_page(page):
                text = text.strip()
                if text:
                    classified.append((size, bold, text))

    # Merge consecutive lines that share the same heading tier into one
    # logical heading. This matters for the document title, which wraps
    # across three physical lines in the PDF ("CardioTrack CT-200 Home
    # Blood" / "Pressure Monitor -- Technical &" / "User Manual") but is a
    # single heading in the markdown source. Body-text wrapping is left
    # alone -- each wrapped body line stays a separate body line, matching
    # how the markdown source itself is line-wrapped.
    md_lines: list = []
    i = 0
    while i < len(classified):
        size, bold, text = classified[i]
        prefix = _heading_prefix(size, bold, text)
        if prefix is None:
            md_lines.append(text)
            i += 1
            continue
        merged_text = text
        j = i + 1
        while j < len(classified):
            nsize, nbold, ntext = classified[j]
            nprefix = _heading_prefix(nsize, nbold, ntext)
            if nprefix == prefix:
                merged_text += " " + ntext
                j += 1
            else:
                break
        md_lines.append(f"{prefix} {merged_text}")
        i = j

    return "\n".join(md_lines) + "\n"
