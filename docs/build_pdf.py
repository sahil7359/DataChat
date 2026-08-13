#!/usr/bin/env python3
"""Build the chapter-wise technical PDF from the repo's own Markdown.

    python docs/build_pdf.py

why generate rather than hand-write: every number and claim in the PDF should be
the same one the repo publishes. Generating from README/FLOW/SECURITY/LEARN means
the document cannot drift from the source of truth — regenerate after a change and
it is correct again.

Deliberately a small renderer, not a Markdown library: it needs headings,
paragraphs, lists, fenced code, pipe tables, blockquotes and inline emphasis, and
nothing else. Mermaid diagrams are replaced with a pointer to the source file
rather than dropped silently.
"""

from __future__ import annotations

import html
import re
import sys
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "DataChat-Technical-Overview.pdf"

# Chapters, in reading order. Each is (title, source file, editorial standfirst).
CHAPTERS: list[tuple[str, str, str]] = [
    (
        "Overview",
        "README.md",
        "What the system does, the deliberately narrow scope it runs on, and the "
        "measured numbers it publishes.",
    ),
    (
        "Architecture and Flow",
        "FLOW.md",
        "How a question becomes an answer: the request lifecycle, the agent graph "
        "node by node, and the trust boundaries between governed data, model "
        "output and the web.",
    ),
    (
        "Sequence Diagrams",
        "AppFlow.md",
        "The same flows as message sequences, including human-in-the-loop approval "
        "and the out-of-scope path.",
    ),
    (
        "Data Model",
        "Schema.md",
        "Tables, roles and grants. The read-only executor role is the second layer "
        "of the safety story, independent of the SQL guardrail.",
    ),
    (
        "Security",
        "SECURITY.md",
        "OWASP LLM Top 10 and Agentic Top 10, each mitigation mapped to a passing "
        "test rather than to a claim.",
    ),
    (
        "Change Log and Reasoning",
        "LEARN.md",
        "What changed, why, and what was rejected. Includes the three false claims "
        "found in this repo and how each was fixed.",
    ),
]

# reportlab's built-in fonts have no glyph for these; they render as black boxes.
# Subscripts are handled separately via <sub> markup.
_UNICODE = {
    "→": "->", "←": "<-", "–": "-", "—": " - ",
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "…": "...", "·": "-", "•": "-", "✓": "yes",
    "✗": "no", "✅": "[ok]", "❌": "[x]", "⚠": "[!]",
    "≥": ">=", "≤": "<=", "×": "x", "≈": "~",
    "▶": ">", "⭐": "*", "\U0001f389": "", "─": "-",
    "┌": "+", "┐": "+", "└": "+", "┘": "+",
    "│": "|", "├": "+", "┤": "+", "┬": "+", "┴": "+",
}


def _ascii(text: str) -> str:
    for bad, good in _UNICODE.items():
        text = text.replace(bad, good)
    # Anything still outside Latin-1 would render as a box.
    return text.encode("latin-1", "replace").decode("latin-1")


def _inline(text: str) -> str:
    """Markdown inline -> reportlab markup, escaped."""
    # Subscript digits must become <sub> tags: the built-in fonts have no glyph
    # for U+2082 and friends, so "CO2" would print as a solid black box.
    subs = {"₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4"}
    for uni, digit in subs.items():
        text = text.replace(uni, f"@@SUB{digit}@@")

    text = _ascii(text)
    text = html.escape(text)

    # Code spans are lifted out before emphasis runs. why: they were previously
    # replaced with <font> tags first, so a later bold/italic regex could match
    # across a tag boundary and emit overlapping markup -- `***` inside backticks
    # produced "<font ...></b>*</font>**", which reportlab rejects. It does not
    # merely lose the emphasis: the whole paragraph is dropped from the document,
    # silently, so content disappears without the build failing.
    spans: list[str] = []

    def _stash(m: re.Match[str]) -> str:
        spans.append(m.group(1))
        return f"\x00{len(spans) - 1}\x00"

    text = re.sub(r"`([^`]+)`", _stash, text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", text)
    # Only http(s)/mailto become clickable. A relative path or an in-page anchor
    # has no meaning once the Markdown is out of its repo, and reportlab refuses
    # to build at all on an unresolvable destination -- so render those as plain
    # text, keeping a file reference visible where it helps.
    def _link(m: re.Match[str]) -> str:
        label, target = m.group(1), m.group(2)
        if target.startswith(("http://", "https://", "mailto:")):
            return f'<link href="{target}" color="#1a5fb4">{label}</link>'
        if target.startswith("#"):
            return label
        return f'{label} <font size="8" color="#777777">({target})</font>'

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _link, text)
    text = re.sub(r"@@SUB(\d)@@", r"<sub>\1</sub>", text)
    text = re.sub(
        r"\x00(\d+)\x00",
        lambda m: f'<font face="Courier" size="8.5">{spans[int(m.group(1))]}</font>',
        text,
    )
    return text


def _para(markup: str, style: ParagraphStyle, **kw: object) -> Paragraph:
    """Build a Paragraph, failing loudly if the markup is malformed.

    why: reportlab reports a parse error on stderr and then drops the paragraph,
    so a bad inline conversion silently removes content from the document while
    the build still reports success. A generator that quietly loses pages is worse
    than one that stops.
    """
    try:
        return Paragraph(markup, style, **kw)  # type: ignore[arg-type]
    except Exception as exc:  # pragma: no cover - build-time guard
        raise SystemExit(f"malformed markup in generated PDF:\n  {markup[:300]}\n  {exc}") from exc


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontSize=30, leading=36,
                                spaceAfter=6),
        "subtitle": ParagraphStyle("st", parent=base["Normal"], fontSize=12.5,
                                   leading=18, textColor=colors.HexColor("#555555")),
        "chapter": ParagraphStyle("c", parent=base["Heading1"], fontSize=21, leading=26,
                                  spaceBefore=0, spaceAfter=4,
                                  textColor=colors.HexColor("#0b3d63")),
        "stand": ParagraphStyle("sf", parent=base["Normal"], fontSize=10.5, leading=15,
                                textColor=colors.HexColor("#555555"), spaceAfter=14),
        "h1": ParagraphStyle("h1", parent=base["Heading2"], fontSize=15, leading=19,
                             spaceBefore=14, spaceAfter=5,
                             textColor=colors.HexColor("#0b3d63")),
        "h2": ParagraphStyle("h2", parent=base["Heading3"], fontSize=12.2, leading=16,
                             spaceBefore=11, spaceAfter=4,
                             textColor=colors.HexColor("#22506e")),
        "h3": ParagraphStyle("h3", parent=base["Heading4"], fontSize=10.8, leading=14,
                             spaceBefore=9, spaceAfter=3,
                             textColor=colors.HexColor("#3a3a3a")),
        "body": ParagraphStyle("b", parent=base["BodyText"], fontSize=9.8, leading=14.5,
                               alignment=TA_LEFT, spaceAfter=7),
        "bullet": ParagraphStyle("bu", parent=base["BodyText"], fontSize=9.8, leading=14,
                                 leftIndent=13, bulletIndent=4, spaceAfter=3),
        "quote": ParagraphStyle("q", parent=base["BodyText"], fontSize=9.5, leading=14,
                                leftIndent=12, borderPadding=(5, 5, 5, 9),
                                backColor=colors.HexColor("#f2f6fa"),
                                borderColor=colors.HexColor("#c9d9e8"), borderWidth=0,
                                spaceAfter=8),
        "code": ParagraphStyle("co", parent=base["Code"], fontSize=7.9, leading=10.2,
                               leftIndent=7, backColor=colors.HexColor("#f5f5f5"),
                               borderPadding=(5, 5, 5, 5), spaceAfter=9),
        "note": ParagraphStyle("n", parent=base["BodyText"], fontSize=8.8, leading=12,
                               textColor=colors.HexColor("#7a6000"),
                               backColor=colors.HexColor("#fdf6e3"),
                               borderPadding=(4, 4, 4, 6), spaceAfter=9),
        "toc": ParagraphStyle("tc", parent=base["BodyText"], fontSize=11, leading=20),
    }


def _table(rows: list[list[str]], st: dict[str, ParagraphStyle]) -> Table:
    cell = ParagraphStyle("cell", parent=st["body"], fontSize=8.4, leading=11.4, spaceAfter=0)
    head = ParagraphStyle("hcell", parent=cell, textColor=colors.white, fontName="Helvetica-Bold")
    data = [[Paragraph(_inline(c), head if i == 0 else cell) for c in row]
            for i, row in enumerate(rows)]
    width = (A4[0] - 42 * mm) / max(len(rows[0]), 1)
    t = Table(data, colWidths=[width] * len(rows[0]), repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0b3d63")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f7fa")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d3dc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def render(md: str, st: dict[str, ParagraphStyle]) -> list:
    """Markdown -> flowables. Only the constructs these docs actually use."""
    flow: list = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]

        if line.startswith("```"):
            lang = line[3:].strip().lower()
            i += 1
            block: list[str] = []
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            if lang == "mermaid":
                flow.append(_para(
                    "<b>[ Diagram ]</b> A Mermaid diagram appears here in the source "
                    "Markdown; it renders on GitHub. See the file named at the start "
                    "of this chapter.", st["note"]))
            elif block:
                body = _ascii("\n".join(block))
                flow.append(Preformatted(body, st["code"], maxLineLength=104))
            continue

        if re.match(r"^\s*\|.+\|\s*$", line) and i + 1 < len(lines) and re.match(
            r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]
        ):
            rows = []
            while i < len(lines) and re.match(r"^\s*\|.+\|\s*$", lines[i]):
                if not re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            width = max(len(r) for r in rows)
            rows = [r + [""] * (width - len(r)) for r in rows]
            flow += [_table(rows, st), Spacer(1, 9)]
            continue

        if line.startswith("<!--"):
            while i < len(lines) and "-->" not in lines[i]:
                i += 1
            i += 1
            continue

        if re.match(r"^\s*(---|\*\*\*|___)\s*$", line):
            i += 1
            continue

        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            text = line.lstrip("#").strip()
            if level == 1:                      # chapter title already printed
                i += 1
                continue
            key = {2: "h1", 3: "h2"}.get(level, "h3")
            flow.append(_para(_inline(text), st[key]))
            i += 1
            continue

        if line.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(lines[i].lstrip("> ").rstrip())
                i += 1
            flow.append(_para(_inline(" ".join(b for b in buf if b)), st["quote"]))
            continue

        m = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.*)$", line)
        if m:
            items = []
            while i < len(lines):
                mm_ = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.*)$", lines[i])
                if not mm_:
                    if lines[i].strip() and lines[i].startswith(("  ", "\t")) and items:
                        items[-1] += " " + lines[i].strip()
                        i += 1
                        continue
                    break
                items.append(mm_.group(3))
                i += 1
            for it in items:
                flow.append(_para(_inline(it), st["bullet"], bulletText="-"))
            flow.append(Spacer(1, 5))
            continue

        if not line.strip():
            i += 1
            continue

        para = [line.strip()]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(
            r"^\s*(#|>|```|\||[-*+]\s|\d+\.\s|---)", lines[i]
        ):
            para.append(lines[i].strip())
            i += 1
        flow.append(_para(_inline(" ".join(para)), st["body"]))
    return flow


def build() -> Path:
    st = _styles()
    doc = BaseDocTemplate(
        str(OUT), pagesize=A4,
        leftMargin=21 * mm, rightMargin=21 * mm, topMargin=19 * mm, bottomMargin=19 * mm,
        title="DataChat - Technical Overview", author="Sahil Chakraborty",
        subject="Agentic natural-language analytics: architecture, evaluation and security",
    )

    def decorate(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#8a8a8a"))
        if canvas.getPageNumber() > 1:
            canvas.drawString(21 * mm, 11 * mm, "DataChat - Technical Overview")
            canvas.drawRightString(A4[0] - 21 * mm, 11 * mm, str(canvas.getPageNumber()))
        canvas.restoreState()

    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame], onPage=decorate)])

    story: list = [
        Spacer(1, 52 * mm),
        Paragraph("DataChat", st["title"]),
        Paragraph(
            "Agentic natural-language analytics over public open data.<br/>"
            "Architecture, evaluation, and security.", st["subtitle"]),
        Spacer(1, 14),
        Paragraph(
            'Live demo: <link href="https://data-chat-seven.vercel.app/" '
            'color="#1a5fb4">data-chat-seven.vercel.app</link><br/>'
            'Source: <link href="https://github.com/sahil7359/DataChat" '
            'color="#1a5fb4">github.com/sahil7359/DataChat</link><br/>'
            f"Generated {date.today().isoformat()} from the repository documentation.",
            st["subtitle"]),
        PageBreak(),
        Paragraph("Contents", st["chapter"]),
        Spacer(1, 8),
    ]
    for n, (title, src, _) in enumerate(CHAPTERS, 1):
        story.append(Paragraph(
            f"<b>{n}. {title}</b>   "
            f'<font size="8.5" color="#777777">{src}</font>', st["toc"]))
    story.append(PageBreak())

    for n, (title, src, stand) in enumerate(CHAPTERS, 1):
        path = ROOT / src
        if not path.exists():
            print(f"  skip (missing): {src}", file=sys.stderr)
            continue
        story.append(KeepTogether([
            Paragraph(f"{n}. {title}", st["chapter"]),
            Paragraph(f"{stand} <i>Source: {src}</i>", st["stand"]),
        ]))
        story += render(path.read_text(encoding="utf-8"), st)
        if n < len(CHAPTERS):
            story.append(PageBreak())

    doc.build(story)
    return OUT


if __name__ == "__main__":
    out = build()
    print(f"wrote {out.relative_to(ROOT)} ({out.stat().st_size / 1024:.0f} KB)")
