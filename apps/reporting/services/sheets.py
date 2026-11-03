"""
Excel templates for repeatable sections (MW 2026-11-03: "there needs to be an option to simply
upload an excel sheet instead of hand entering").

Each repeatable section (research team, meetings, core users and so on) offers a template whose
header row is the section's question prompts. Filled-in rows are read back and added to the
section as entries, which the person can check and edit before submitting.
"""

import datetime as dt
import io
import re

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from apps.common.enums import QuestionType

MAX_ROWS = 200
OPTION_TYPES = (QuestionType.SINGLE_SELECT, QuestionType.YES_NO, QuestionType.LIKERT)


class SheetError(Exception):
    pass


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").casefold()).strip()


def _questions(section):
    return [q for q in section.questions.all() if q.question_type != QuestionType.INSTRUCTIONS]


def _options(q):
    return list(q.answer_set.options.all()) if q.answer_set_id else []


def template(section):
    """The .xlsx template for one repeatable section, as bytes."""
    qs = _questions(section)
    wb = Workbook()
    ws = wb.active
    ws.title = (section.title or "Entries")[:31].replace("/", "-")
    head_fill = PatternFill("solid", fgColor="4B2A84")
    for col, q in enumerate(qs, start=1):
        c = ws.cell(row=1, column=col, value=q.prompt)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = head_fill
        c.alignment = Alignment(wrap_text=True, vertical="center")
        letter = get_column_letter(col)
        ws.column_dimensions[letter].width = 44 if q.question_type == QuestionType.LONG_TEXT else 22
        opts = _options(q)
        if opts and q.question_type in OPTION_TYPES:
            labels = ",".join(o.label.replace(",", " ") for o in opts)
            if len(labels) < 250:
                dv = DataValidation(type="list", formula1=f'"{labels}"', allow_blank=True)
                ws.add_data_validation(dv)
                dv.add(f"{letter}2:{letter}{MAX_ROWS + 1}")
        elif q.question_type == QuestionType.DATE:
            for r in range(2, MAX_ROWS + 2):
                ws.cell(row=r, column=col).number_format = "mm/dd/yyyy"
    ws.row_dimensions[1].height = 34
    ws.freeze_panes = "A2"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _date(v):
    if isinstance(v, dt.datetime):
        return v.date().isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    s = str(v).strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return dt.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _cell(q, v):
    """(value to store, problem or None) for one cell."""
    if v is None or str(v).strip() == "":
        return "", None
    if q.question_type == QuestionType.DATE:
        d = _date(v)
        return (d, None) if d else ("", f"“{q.prompt}” needs a date like 09/30/2026.")
    if q.question_type in (QuestionType.NUMBER, QuestionType.CURRENCY):
        try:
            n = float(str(v).replace(",", "").replace("$", ""))
        except ValueError:
            return "", f"“{q.prompt}” needs a number."
        return (str(int(n)) if n == int(n) else str(n)), None
    opts = _options(q)
    if opts:
        key = _norm(v)
        for o in opts:
            if key in (_norm(o.label), _norm(o.code)):
                return o.code, None
        return "", f"“{v}” isn’t one of the choices for “{q.prompt}”."
    return str(v).strip(), None


def read(section, uploaded):
    """Rows from a filled-in template: (list of {code: value}, list of problems)."""
    name = (getattr(uploaded, "name", "") or "").lower()
    if not name.endswith((".xlsx", ".xlsm")):
        raise SheetError("Please upload an Excel file (.xlsx).")
    try:
        wb = load_workbook(uploaded, read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - any unreadable workbook
        raise SheetError("That Excel file couldn’t be opened. Please use the template.") from exc
    ws = wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    header = next(it, None) or ()
    qs = _questions(section)
    by_key = {}
    for q in qs:
        by_key[_norm(q.prompt)] = q
        by_key[_norm(q.code)] = q
    cols = {i: by_key.get(_norm(h)) for i, h in enumerate(header)}
    if not any(cols.values()):
        raise SheetError(
            "The first row of your sheet doesn’t match the template’s column names. "
            "Please download the template and copy your list into it."
        )
    rows, problems = [], []
    for n, values in enumerate(it, start=2):
        if len(rows) >= MAX_ROWS:
            problems.append(f"Only the first {MAX_ROWS} rows were added.")
            break
        row = {q.code: "" for q in qs}
        for i, v in enumerate(values or ()):
            q = cols.get(i)
            if not q:
                continue
            val, err = _cell(q, v)
            if err:
                problems.append(f"Row {n}: {err}")
            row[q.code] = val
        if any(row.values()):
            rows.append(row)
    wb.close()
    if not rows and not problems:
        problems.append("Your sheet has no rows filled in under the column names.")
    return rows, problems
