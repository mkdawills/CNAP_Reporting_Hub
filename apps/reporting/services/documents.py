"""
Word and PDF copies of forms (Batch 2, MW 2026-11-05).

Three kinds of document, each as PDF or Word:
1. the blank form: every section, direction, question, and answer choice;
2. one completed form: the same sections and answers the person sees on screen;
3. every completed form for a reporting period, one after another.

A document is first built as a short list of blocks (headings, notes, questions with answers,
tables), then written out as PDF (reportlab) or Word (python-docx), so both formats always say the
same thing. Who may download what is decided by the views, with the same rules as reading on
screen; a de-identified copy carries no name, project, core, prefilled detail, or file name.
"""

import io
import re
from xml.sax.saxutils import escape

from django.utils import timezone

from apps.common.enums import QuestionType
from apps.forms_engine.runtime import FormSchema

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _sentences(text):
    """Directions are stored as one paragraph; documents set them one sentence per line, like the screens."""
    out = []
    for para in (text or "").splitlines():
        para = para.strip()
        if not para:
            continue
        out += [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z“\"(])", para) if s.strip()]
    return out


def _choice_text(o):
    return "Not applicable" if o.is_na_option else o.label


# ------------------------------------------------------------------ building blocks
def blank_blocks(version, *, intro=None):
    """The blank form: every question and every answer choice, with room to write."""
    fd = version.form_definition
    schema = FormSchema(version)
    noun = (
        "report"
        if fd.category == "report"
        else ("questionnaire" if "Questionnaire" in fd.name else "survey")
    )
    b = [("title", fd.name), ("meta", [("Blank copy", f"Version {version.version_no}")])]
    lines = _sentences(intro if intro is not None else version.intro_text)
    if lines:
        b.append(("lede", lines))
    optq, followup = schema.optout_question, schema.followup_section
    if optq:
        b += [
            ("h2", "Opt out"),
            ("choice", optq.prompt, [("☐", "Yes")]),
            (
                "note",
                [
                    f"Choosing this replaces the {noun} with a few short questions."
                    if followup
                    else f"Choosing this completes the {noun}."
                ],
            ),
        ]
    for sec in schema.sections:
        if optq and sec.pk == optq.form_section_id:
            continue
        qs = [
            q
            for q in sec.questions.all()
            if q.question_type != QuestionType.INSTRUCTIONS and q.config.get("widget") != "system"
        ]
        if not qs and not sec.instructions:
            continue
        b.append(("h2", sec.title or "Questions"))
        if followup and sec.pk == followup.pk:
            b.append(("note", ["If you opt out, you answer these questions instead."]))
        if sec.instructions:
            b.append(("note", _sentences(sec.instructions)))
        if sec.is_repeatable:
            b.append(
                (
                    "note",
                    [
                        f"Please give one entry for each {(sec.repeat_label or 'entry').replace('Add another ', '').replace('Add an ', '').replace('Add a ', '').lower()}. Add as many as you need."
                    ],
                )
            )
        for q in qs:
            label = q.prompt + ("" if q.is_required else " (optional)")
            if q.answer_set_id:
                opts = list(q.answer_set.options.all())
                mark = "☐" if q.question_type == QuestionType.MULTI_SELECT else "○"
                b.append(("choice", label, [(mark, _choice_text(o)) for o in opts]))
            elif q.question_type == QuestionType.FILE:
                b.append(("blank", label, 1, "Upload a file in the Member Hub."))
            else:
                b.append(
                    (
                        "blank",
                        label,
                        5
                        if q.question_type == QuestionType.LONG_TEXT or q.config.get("narrative")
                        else 1,
                        q.help_text,
                    )
                )
    return b


def _answer_text(view, *, named):
    """What the person chose or wrote, in the words they saw."""
    v = view.get("value") or ""
    if view.get("type") == QuestionType.FILE or view.get("file"):
        f = view.get("file")
        return (f.original_filename if named else "File uploaded") if f else ""
    if not v:
        return ""
    for o in (view.get("pts") or []) + (view.get("na") or []):
        if o["code"] == v:
            return "Not applicable" if o["text"] == "NA" else o["label"]
    m = {o["code"]: o["label"] for o in view.get("options") or []}
    if v in m:
        return m[v]
    parts = [p for p in re.split(r"[;,]\s*", v) if p]
    if parts and all(p in m for p in parts):
        return "; ".join(m[p] for p in parts)
    return v


def response_blocks(ctx, *, named, label=None):
    """One completed form, built from the same page data the screen uses (presenters.form_page)."""
    a, fd = ctx["a"], ctx["fd"]
    meta = [("CNAP reporting session", a.reporting_period.name)]
    if named:
        meta.insert(0, ("Response from", a.person.full_name))
        if ctx.get("context_line"):
            meta.append(("Project or core", ctx["context_line"]))
        meta += [(k, v or "—") for k, v in ctx.get("prefill") or []]
    else:
        meta.insert(0, ("Response", label or "De-identified"))
    status = {
        "submitted": "Submitted",
        "completed_opt_out": "Opted out",
        "in_progress": "In progress",
        "not_started": "Not started",
        "exempt": "Not needed",
    }.get(a.status, a.status)
    meta.append(("Status", status))
    if a.submitted_at:
        meta.append(("Submitted on", timezone.localtime(a.submitted_at).strftime("%B %-d, %Y")))
    b = [("title", fd.name), ("meta", meta)]
    if not named:
        b.append(("note", ["Names and anything that could identify the respondent are not shown."]))
    opted = ctx.get("opted")
    if ctx.get("optout") and opted:
        b += [("h2", "Opt out"), ("qa", ctx["optout"].prompt, "Yes")]
    for sv in ctx["sections"]:
        if not sv["visible"] or (sv.get("is_followup") and not opted):
            continue
        b.append(("h2", sv["s"].title or "Questions"))
        if sv["s"].is_repeatable:
            qs = sv.get("template_row") or (sv["rows"][0] if sv["rows"] else [])
            head = [v["q"].prompt for v in qs]
            rows = [
                [_answer_text(v, named=named) for v in r]
                for r in sv["rows"]
                if any((v.get("value") or v.get("file")) for v in r)
            ]
            b.append(("table", head, rows) if rows else ("note", ["No entries."]))
            continue
        for v in sv["questions"]:
            if v.get("widget") == "system":
                continue
            b.append(("qa", v["q"].prompt, _answer_text(v, named=named) or "No answer"))
    return b


# ------------------------------------------------------------------ PDF
def to_pdf(docs, title):
    """docs: a list of block lists; each starts on a new page."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        KeepTogether,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    ink, muted, brand, line = (
        colors.HexColor("#2a2236"),
        colors.HexColor("#5f5a6b"),
        colors.HexColor("#3b1d66"),
        colors.HexColor("#d3d1da"),
    )
    st = {
        "title": ParagraphStyle(
            "t", fontName="Times-Roman", fontSize=20, leading=25, textColor=ink, spaceAfter=8
        ),
        "h2": ParagraphStyle(
            "h",
            fontName="Times-Roman",
            fontSize=14.5,
            leading=19,
            textColor=brand,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "body": ParagraphStyle("b", fontName="Helvetica", fontSize=10, leading=14.5, textColor=ink),
        "q": ParagraphStyle(
            "q", fontName="Helvetica-Bold", fontSize=10, leading=14, textColor=ink, spaceBefore=7
        ),
        "a": ParagraphStyle(
            "a", fontName="Helvetica", fontSize=10, leading=14, textColor=ink, leftIndent=12
        ),
        "note": ParagraphStyle("n", fontName="Helvetica", fontSize=9, leading=13, textColor=muted),
        "meta": ParagraphStyle(
            "m", fontName="Helvetica", fontSize=9, leading=12.5, textColor=muted
        ),
        "cell": ParagraphStyle("c", fontName="Helvetica", fontSize=8.5, leading=11, textColor=ink),
        "head": ParagraphStyle(
            "hc", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=ink
        ),
    }
    P = lambda t, s: Paragraph(escape(str(t)).replace("\n", "<br/>"), st[s])
    flow = []
    for i, blocks in enumerate(docs):
        if i:
            flow.append(PageBreak())
        for blk in blocks:
            k = blk[0]
            if k == "title":
                flow.append(P(blk[1], "title"))
            elif k == "meta":
                flow.append(
                    Paragraph(
                        "<br/>".join(
                            f"{escape(a)}: <font color='#2a2236'>{escape(str(b))}</font>"
                            for a, b in blk[1]
                        ),
                        st["meta"],
                    )
                )
                flow.append(Spacer(1, 8))
            elif k == "lede":
                t = Table(
                    [[Paragraph("<br/>".join(escape(s) for s in blk[1]), st["body"])]],
                    colWidths=[6.6 * inch],
                )
                t.setStyle(
                    TableStyle(
                        [
                            ("LINEBEFORE", (0, 0), (0, -1), 1.5, line),
                            ("LEFTPADDING", (0, 0), (-1, -1), 10),
                        ]
                    )
                )
                flow += [t, Spacer(1, 6)]
            elif k == "h2":
                flow.append(P(blk[1], "h2"))
            elif k == "note":
                flow.append(Paragraph("<br/>".join(escape(s) for s in blk[1]), st["note"]))
            elif k == "qa":
                flow.append(KeepTogether([P(blk[1], "q"), P(blk[2], "a")]))
            elif k == "choice":
                pdf_mark = {
                    "○": "(&nbsp;&nbsp;)",
                    "☐": "[&nbsp;&nbsp;]",
                }  # the standard PDF fonts have no circle or box
                items = [P(blk[1], "q")] + [
                    Paragraph(f"{pdf_mark.get(m, escape(m))}&nbsp;&nbsp;{escape(t)}", st["a"])
                    for m, t in blk[2]
                ]
                flow.append(KeepTogether(items))
            elif k == "blank":
                items = [P(blk[1], "q")]
                if blk[3]:
                    items.append(P(blk[3], "note"))
                rows = [[""] for _ in range(blk[2])]
                t = Table(rows, colWidths=[6.4 * inch], rowHeights=[18] * blk[2])
                t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.6, line)]))
                items.append(t)
                flow.append(KeepTogether(items))
            elif k == "table":
                head, rows = blk[1], blk[2]
                w = 6.6 * inch / max(1, len(head))
                data = [[Paragraph(escape(h), st["head"]) for h in head]] + [
                    [Paragraph(escape(str(c)), st["cell"]) for c in r] for r in rows
                ]
                t = Table(data, colWidths=[w] * len(head), repeatRows=1)
                t.setStyle(
                    TableStyle(
                        [
                            ("GRID", (0, 0), (-1, -1), 0.5, line),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#efedf5")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ]
                    )
                )
                flow += [t, Spacer(1, 6)]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(muted)
        canvas.drawString(0.9 * inch, 0.55 * inch, f"CNAP Member Hub · {title}")
        canvas.drawRightString(7.6 * inch, 0.55 * inch, f"Page {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.85 * inch,
        title=title,
        author="CNAP Member Hub",
    ).build(flow, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


# ------------------------------------------------------------------ Word
def to_docx(docs, title):
    from docx import Document
    from docx.enum.text import WD_BREAK
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    ink, muted, brand = (
        RGBColor(0x2A, 0x22, 0x36),
        RGBColor(0x5F, 0x5A, 0x6B),
        RGBColor(0x3B, 0x1D, 0x66),
    )
    d = Document()
    d.core_properties.title = title
    d.core_properties.author = "CNAP Member Hub"
    normal = d.styles["Normal"]
    normal.font.name, normal.font.size = "Calibri", Pt(10.5)

    def para(
        text="", *, size=None, bold=False, color=None, serif=False, indent=None, after=4, before=0
    ):
        p = d.add_paragraph()
        p.paragraph_format.space_after, p.paragraph_format.space_before = Pt(after), Pt(before)
        if indent:
            p.paragraph_format.left_indent = Pt(indent)
        lines = str(text).split("\n")
        for i, line in enumerate(lines):
            r = p.add_run(line)
            r.bold = bold
            if size:
                r.font.size = Pt(size)
            if color is not None:
                r.font.color.rgb = color
            if serif:
                r.font.name = "Georgia"
            if i < len(lines) - 1:
                r.add_break()
        return p

    def shade(cell, hex_fill):
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), hex_fill)
        tcPr.append(shd)

    for i, blocks in enumerate(docs):
        if i:
            d.paragraphs[-1].add_run().add_break(WD_BREAK.PAGE)
        for blk in blocks:
            k = blk[0]
            if k == "title":
                para(blk[1], size=20, color=ink, serif=True, after=6)
            elif k == "meta":
                for a, b in blk[1]:
                    p = para("", after=0)
                    r = p.add_run(f"{a}: ")
                    r.font.size, r.font.color.rgb = Pt(9), muted
                    r = p.add_run(str(b))
                    r.font.size = Pt(9)
                d.paragraphs[-1].paragraph_format.space_after = Pt(10)
            elif k == "lede":
                para("\n".join(blk[1]), indent=10, after=8)
            elif k == "h2":
                para(blk[1], size=14, color=brand, serif=True, before=12, after=4)
            elif k == "note":
                para("\n".join(blk[1]), size=9, color=muted, after=4)
            elif k == "qa":
                para(blk[1], bold=True, before=6, after=1)
                para(blk[2], indent=12, after=4)
            elif k == "choice":
                para(blk[1], bold=True, before=6, after=1)
                for m, t in blk[2]:
                    para(f"{m}  {t}", indent=12, after=0)
            elif k == "blank":
                para(blk[1], bold=True, before=6, after=1)
                if blk[3]:
                    para(blk[3], size=9, color=muted, after=1)
                for _ in range(blk[2]):
                    para("_" * 78, color=RGBColor(0xC9, 0xC6, 0xD1), after=0)
            elif k == "table":
                head, rows = blk[1], blk[2]
                t = d.add_table(rows=1, cols=len(head))
                t.style = "Table Grid"
                for j, h in enumerate(head):
                    c = t.rows[0].cells[j]
                    c.text = h
                    c.paragraphs[0].runs[0].bold = True
                    shade(c, "EFEDF5")
                for r in rows:
                    cells = t.add_row().cells
                    for j, v in enumerate(r):
                        cells[j].text = str(v)
                para("", after=4)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def file_response(docs, title, filename_base, fmt):
    from django.http import HttpResponse

    slug = re.sub(r"[^A-Za-z0-9]+", "-", filename_base).strip("-")
    if fmt == "docx":
        resp = HttpResponse(to_docx(docs, title), content_type=DOCX)
        resp["Content-Disposition"] = f'attachment; filename="{slug}.docx"'
    else:
        resp = HttpResponse(to_pdf(docs, title), content_type=PDF)
        resp["Content-Disposition"] = f'attachment; filename="{slug}.pdf"'
    return resp
