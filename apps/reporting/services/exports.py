"""
Excel downloads (Batch 2, MW 2026-11-05).

1. Each form's answers for a reporting period: one row per respondent, one column per question.
2. Real Excel workbooks for the existing CSV downloads: the same rows, formatted.
3. One "Download everything" workbook for a reporting period.

Who may download what is exactly who may read it on screen (apps.reporting.access):
- names only where the reader sees names (form_access == IDENTIFIED);
- de-identified rows ("Respondent n", in the same shuffled order as the results page, with no
  project, core, or prefilled details) only where the small-group safeguard allows them;
- confidential mentoring forms only for people with that permission.
Nothing here writes to the database.
"""

import csv
import io
import re

from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from apps.common.enums import COMPLETE_STATUSES, QuestionType
from apps.forms_engine.runtime import FormSchema
from apps.reporting.access import (
    DEIDENTIFIED,
    IDENTIFIED,
    deidentified_rows_allowed,
    form_access,
    respondent_label_order,
)
from apps.reporting.models import Assignment

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
HEAD_FILL = PatternFill("solid", fgColor="EFEDF5")
TITLE_FONT = Font(bold=True, size=13, color="3B1D66")
HEAD_FONT = Font(bold=True, color="2A2236")
NOTE_FONT = Font(italic=False, color="5F5A6B", size=10)
THIN = Side(style="thin", color="D3D1DA")
SKIP_TYPES = {QuestionType.FILE}  # files are listed by name, not embedded


# ------------------------------------------------------------------ formatting
def _safe_title(s, used):
    """Excel sheet names: at most 31 characters, none of []:*?/\\, and unique in the workbook."""
    clean = " ".join(re.sub(r"[\[\]:*?/\\]", " ", s).split())
    if len(clean) > 31:  # cut at the last whole word, never mid-word
        cut = clean[:31]
        clean = cut[: cut.rfind(" ")] if " " in cut else cut
        clean = clean.rstrip(" ,;–-(")
    base = clean or "Sheet"
    name, n = base, 2
    while name.lower() in used:
        suffix = f" ({n})"
        name, n = base[: 31 - len(suffix)] + suffix, n + 1
    used.add(name.lower())
    return name


def _cell_value(v):
    """Keep numbers as numbers so Excel can sum and average them; guard against formula injection."""
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        return v
    s = str(v)
    if re.fullmatch(r"-?\d+(\.\d+)?", s):
        return float(s) if "." in s else int(s)
    if s[:1] in ("=", "+", "-", "@") and not re.fullmatch(r"-?\d", s[:2]):
        return "'" + s  # shown as text, never run as a formula
    return s


def write_sheet(ws, title, header, rows, notes=(), widths=None):
    """A formatted sheet: title, notes, one bold header row (frozen), sized columns, wrapped text."""
    r = 1
    if title:
        ws.cell(row=1, column=1, value=title).font = TITLE_FONT
        r = 2
    for n in notes:
        ws.cell(row=r, column=1, value=n).font = NOTE_FONT
        r += 1
    if title or notes:
        r += 1
    head_row = r
    for c, h in enumerate(header, 1):
        cell = ws.cell(row=r, column=c, value=h)
        cell.font, cell.fill = HEAD_FONT, HEAD_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="bottom")
        cell.border = Border(bottom=THIN)
    for row in rows:
        r += 1
        for c, v in enumerate(row, 1):
            cell = ws.cell(row=r, column=c, value=_cell_value(v))
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = ws.cell(row=head_row + 1, column=2 if len(header) > 2 else 1)
    for c in range(1, len(header) + 1):
        if widths and c <= len(widths) and widths[c - 1]:
            w = widths[c - 1]
        else:
            longest = max([len(str(header[c - 1]))] + [len(str(row[c - 1])) for row in rows if c - 1 < len(row)] + [6])
            w = min(max(10, longest + 2), 60)
        ws.column_dimensions[get_column_letter(c)].width = w
    return ws


def csv_rows(text):
    return list(csv.reader(io.StringIO(text)))


def write_csv_sheet(ws, rows, title=None):
    """An existing CSV download, cell for cell, formatted: the first row and one-cell title rows are bold."""
    r = 0
    if title:
        ws.cell(row=1, column=1, value=title).font = TITLE_FONT
        r = 2
    head_done = False
    width = {}
    for row in rows:
        r += 1
        for c, v in enumerate(row, 1):
            cell = ws.cell(row=r, column=c, value=_cell_value(v))
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            width[c] = max(width.get(c, 8), min(len(str(v)) + 2, 60))
        filled = [v for v in row if str(v).strip()]
        if row and (not head_done or len(filled) == 1 and len(row) <= 2):
            for c in range(1, len(row) + 1):
                ws.cell(row=r, column=c).font = HEAD_FONT if not head_done else Font(bold=True)
                if not head_done:
                    ws.cell(row=r, column=c).fill = HEAD_FILL
            if not head_done:
                ws.freeze_panes = ws.cell(row=r + 1, column=1)
                head_done = True
    for c, w in width.items():
        ws.column_dimensions[get_column_letter(c)].width = w
    return ws


def workbook_response(wb, filename):
    buf = io.BytesIO()
    wb.save(buf)
    resp = HttpResponse(buf.getvalue(), content_type=XLSX)
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


def csv_to_xlsx(csv_response, filename, title=None):
    """Turn an existing CSV download into a formatted workbook with exactly the same cells."""
    text = csv_response.content.decode("utf-8-sig")
    wb = Workbook()
    write_csv_sheet(wb.active, csv_rows(text), title=title)
    wb.active.title = _safe_title(title or "Download", set())
    return workbook_response(wb, filename)


# ------------------------------------------------------------------ one form's answers
def _option_maps(schema):
    out = {}
    for q in schema.questions:
        if q.answer_set_id:
            out[q.code] = {o.code: o for o in q.answer_set.options.all()}
    return out


def _value(q, a, opts, named=True):
    """One stored answer as a cell: a scale point's number, otherwise the words the person saw.
    A file is listed by its name only when the reader sees names, since file names often carry one."""
    if a.option_id:
        o = opts.get(q.code, {}).get(a.option.code) or a.option
        if q.question_type == QuestionType.LIKERT and o.value is not None:
            return o.value
        return o.label
    if a.value_text is not None:
        return a.value_text
    if a.value_date is not None:
        return a.value_date.isoformat()
    if a.value_number is not None:
        n = a.value_number
        return int(n) if n == int(n) else float(n)
    link = a.files.all().first()
    if not link:
        return ""
    return link.file.original_filename if named else "File uploaded"


def form_answers(user, fd, period, *, core=None, project=None):
    """Rows of every completed response this reader may see, or PermissionDenied.

    Returns {"mode", "columns": [(code, prompt)], "rows": [[...]], "repeats": {title: (header, rows)},
    "blocked": str or ""}.
    """
    mode = form_access(user, fd)
    if not mode:
        raise PermissionDenied("Your access doesn’t include individual responses to this form.")
    done = list(
        Assignment.objects.filter(form_definition=fd, reporting_period=period, status__in=COMPLETE_STATUSES)
        .select_related("person", "project", "core", "form_version")
        .prefetch_related("responses")
    )
    if (core or project) and mode == IDENTIFIED:  # narrowing only where names are already shown
        done = [a for a in done if (not project or a.project_id == project.pk) and (not core or a.core_id == core.pk)]
    if mode == DEIDENTIFIED and not deidentified_rows_allowed(fd, period):
        return {"mode": mode, "columns": [], "rows": [], "repeats": {}, "blocked": "Individual responses aren’t included because fewer than 5 people completed this form"}
    if mode == IDENTIFIED:
        ordered = sorted(done, key=lambda a: (a.person.last_name, a.person.first_name))
        labels = [a.person.full_name for a in ordered]
    else:
        ordered = respondent_label_order(done, fd, period)
        labels = [f"Respondent {i}" for i in range(1, len(ordered) + 1)]

    schemas = {}
    columns, seen, repeat_cols = [], set(), {}
    for a in ordered:
        if a.form_version_id not in schemas:
            schemas[a.form_version_id] = FormSchema(a.form_version)
    for s in schemas.values():
        for sec in s.sections:
            for q in sec.questions.all():
                if q.config.get("widget") == "system" or q.code in seen:
                    continue
                seen.add(q.code)
                if sec.is_repeatable:
                    repeat_cols.setdefault(sec.title or sec.code, []).append((q.code, q.prompt))
                else:
                    columns.append((q.code, q.prompt))

    rows, repeats = [], {t: [] for t in repeat_cols}
    for label, a in zip(labels, ordered):
        s = schemas[a.form_version_id]
        opts = _option_maps(s)
        resp = next((r for r in a.responses.all() if r.is_current), None)
        vals, multi, reps = {}, {}, {}
        if resp:
            sec_title = {sec.pk: (sec.title or sec.code) for sec in s.sections if sec.is_repeatable}
            for ans in resp.answers.select_related("question", "option").prefetch_related("files__file"):
                q = ans.question
                if q.config.get("widget") == "system":
                    continue
                v = _value(q, ans, opts, named=mode == IDENTIFIED)
                if q.form_section_id in sec_title:
                    reps.setdefault(sec_title[q.form_section_id], {}).setdefault(ans.repeat_index, {})[q.code] = v
                elif q.question_type == QuestionType.MULTI_SELECT:
                    multi.setdefault(q.code, []).append(str(v))
                else:
                    vals[q.code] = v
        for code, parts in multi.items():
            vals[code] = "; ".join(parts)
        lead = [label]
        if mode == IDENTIFIED:
            ctx = a.project.title if a.project_id else (a.core.name if a.core_id else "")
            lead.append(ctx)
        lead += [
            "Opted out" if a.status == "completed_opt_out" else "Answered",
            timezone.localtime(a.submitted_at).date().isoformat() if getattr(a, "submitted_at", None) else "",
        ]
        rows.append(lead + [vals.get(c, "") for c, _ in columns])
        for t, entries in reps.items():
            for i in sorted(entries):
                repeats[t].append([label, i + 1] + [entries[i].get(c, "") for c, _ in repeat_cols[t]])
    lead_head = ["Person" if mode == IDENTIFIED else "Respondent"] + (["Project or core"] if mode == IDENTIFIED else []) + ["How it was completed", "Submitted on"]
    return {
        "mode": mode,
        "lead": lead_head,
        "columns": columns,
        "rows": rows,
        "repeats": {t: (["Person" if mode == IDENTIFIED else "Respondent", "Entry"] + [p for _, p in repeat_cols[t]], repeats[t]) for t in repeat_cols},
        "blocked": "",
    }


def add_form_sheets(wb, user, fd, period, used, first=False):
    """Add one form's answers (and its repeating sections) to a workbook. Returns a contents line."""
    data = form_answers(user, fd, period)
    ws = wb.active if first else wb.create_sheet()
    ws.title = _safe_title(fd.name, used)
    notes = [
        period.name,
        "With names." if data["mode"] == IDENTIFIED else "Without names: respondents are numbered in the same order as the results page.",
        "Rating questions show the number the person chose (for example, 4 for Good). Other questions show the words the person saw.",
    ]
    if data["blocked"]:
        write_sheet(ws, fd.name, ["Note"], [[data["blocked"] + "."]], notes=notes[:2])
        return ws.title, data["blocked"]
    header = data["lead"] + [p for _, p in data["columns"]]
    write_sheet(ws, fd.name, header, data["rows"], notes=notes, widths=[24] + [None] * (len(header) - 1))
    for t, (h, rows) in data["repeats"].items():
        rs = wb.create_sheet()
        rs.title = _safe_title(f"{fd.name[:18]} – {t}", used)
        write_sheet(rs, f"{fd.name}: {t}", h, rows, notes=[period.name, "One row per entry."])
    return ws.title, f"{len(data['rows'])} response{'s' if len(data['rows']) != 1 else ''}"


def form_answers_workbook(user, fd, period):
    wb = Workbook()
    add_form_sheets(wb, user, fd, period, set(), first=True)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", f"{fd.code}-{period.short_label}").strip("-")
    return workbook_response(wb, f"{slug}-answers.xlsx")
