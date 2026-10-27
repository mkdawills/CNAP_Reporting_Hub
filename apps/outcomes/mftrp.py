"""The NIH annual MFTRP certification, filled in with the person's name (MW's form, 2026-10-27; NOT-OD-26-018).

Wording is MW's NIH_Annual_MFTRP_Certification.docx, word for word, with "[insert name]" replaced. The person
signs it with an Adobe digital signature, flattens it, and uploads it to their NIH documents task.
"""

import io
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

TITLE = [
    "Annual Certification",
    "Regarding Participation or Non-Participation in a",
    "Malign Foreign Talent Recruitment Program",
]
BODY = [
    "For NIH RPPRs submitted on or after January 25, 2026, individuals serving as senior/key personnel must "
    "certify annually to their participation or non-participation in a Malign Foreign Talent Recruitment "
    "Program (MFTRP) by uploading a certification statement in Section G.1 as a flattened PDF.",
    "The file for each senior/key person must be named ‘MFTRPcert_[Name].pdf’ without quotations, where "
    "‘[Name]’ is the name of the senior/key person.",
    "See NOT-OD-26-018 for more information.",
]
STATEMENT = "I, {name}, certify that, at the time of submission, I am not a party to a malign foreign talent recruitment program."


def filename(person):
    from .nihdocs import safe_name

    return f"MFTRPcert_{safe_name(person.last_name)}_{safe_name(person.first_name)}.pdf"


def build(person):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=inch,
        rightMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
        title="Annual MFTRP Certification",
        author=f"{person.first_name} {person.last_name}",
    )
    h = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=14, leading=19, alignment=1)
    p = ParagraphStyle("p", fontName="Helvetica", fontSize=11, leading=16, spaceAfter=10)
    out = [Paragraph(escape(t), h) for t in TITLE] + [Spacer(1, 22)]
    out += [Paragraph(escape(t), p) for t in BODY] + [Spacer(1, 18)]
    name = f"{person.first_name} {person.last_name}".strip()
    out += [Paragraph(escape(STATEMENT.format(name=name)), p), Spacer(1, 48)]
    for label in ("Signature", "Date"):
        out += [Paragraph("_" * 39, p), Paragraph(label, p), Spacer(1, 30)]
    doc.build(out)
    return buf.getvalue()
