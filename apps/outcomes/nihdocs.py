"""
RPPR inputs collected through forms (MW 2026-10-27):

- NIH documents: once a year (the Fall period) the PD/PI, RP Leaders, PP Leaders and core directors upload a
  certified SciENcv biosketch and Current and Pending (Other) Support, a signed MFTRP certification, optional
  foreign-activity documents, and answer RPPR D.2.a.
- Research teams: each progress report (RPL, PPL, core) lists the people on the project or core with calendar,
  academic and summer months (RPPR D.1 columns), plus optional suggested-table uploads.

Read-only: these build the RPPR tab's lists and downloads. Access checks happen in the views.
"""

import re

from apps.common.enums import AssignmentStatus
from apps.forms_engine.runtime import FormSchema
from apps.reporting.models import Assignment, ReportingPeriod
from apps.reporting.services import responses as rs

DOC_FORM = "nih_documents"
DOC_FILES = [
    ("biosketch", "Biosketch"),
    ("current_pending", "Current and Pending"),
    ("mftrp_cert", "MFTRP certification"),
    ("foreign_docs", "Foreign-activity documents"),
]
REQUIRED_FILES = ("biosketch", "current_pending", "mftrp_cert")
PROGRESS_FORMS = ("progress_research", "progress_pilot", "progress_core")
TEAM_COLS = [
    ("first_name", "First name"),
    ("last_name", "Last name"),
    ("email", "Email"),
    ("commons_id", "eRA Commons ID"),
    ("role", "Role"),
    ("cal_months", "Calendar months"),
    ("aca_months", "Academic months"),
    ("sum_months", "Summer months"),
]
DONE = (AssignmentStatus.SUBMITTED,)
QUICK_ITEMS = [
    ("b1a", "B.1.a goals changed"),
    ("c3", "C.3 technologies or techniques"),
    ("c4", "C.4 inventions, patents, licenses"),
    ("c5a", "C.5.a other products"),
    ("c5c", "C.5.c data shared per plan"),
    ("f3", "F.3 changes: subjects, animals, biohazards, agents"),
    ("g9", "G.9 foreign component"),
]
# the answer that needs attention: Yes, except C.5.c where No does
FLAG = {code: ("no" if code == "c5c" else "yes") for code, _ in QUICK_ITEMS}


def _answers(a, cache):
    if a.form_version_id not in cache:
        cache[a.form_version_id] = FormSchema(a.form_version)
    return rs.answers_of(rs.current_response(a), cache[a.form_version_id])


def documents(gy):
    """One row per person asked for NIH documents in budget year `gy`, with their files. None if not asked."""
    asg = list(
        Assignment.objects.filter(
            form_definition__code=DOC_FORM, reporting_period__grant_year=gy
        ).select_related("person", "form_version", "reporting_period")
    )
    if not asg:
        return None
    cache, rows = {}, []
    for a in sorted(asg, key=lambda x: (x.person.last_name, x.person.first_name)):
        answers, _, files = _answers(a, cache)
        rows.append(
            {
                "a": a,
                "person": a.person,
                "submitted": a.status in DONE,
                "status": a.get_status_display(),
                "d2a": answers.get("d2a"),
                "d2a_explain": answers.get("d2a_explain") or "",
                "files": [(code, label, files.get(code)) for code, label in DOC_FILES],
                "missing": [
                    label
                    for code, label in DOC_FILES
                    if code in REQUIRED_FILES and not files.get(code)
                ],
            }
        )
    return {
        "rows": rows,
        "period": asg[0].reporting_period,
        "n": len(rows),
        "n_done": sum(1 for r in rows if r["submitted"]),
        "d2a_yes": [r for r in rows if r["d2a"] == "yes"],
    }


def safe_name(s):
    return re.sub(r"[^A-Za-z0-9]+", "", s or "") or "X"


def zip_name(person, label, f):
    ext = (f.original_filename.rsplit(".", 1)[-1] if "." in f.original_filename else "pdf").lower()
    return f"{safe_name(person.last_name)}_{safe_name(person.first_name)}_{safe_name(label)}.{ext}"


def teams(gy):
    """Research team lists and table uploads from this budget year's progress reports, newest period first."""
    periods = ReportingPeriod.objects.filter(grant_year=gy).order_by("-sequence")
    out, cache = [], {}
    for p in periods:
        asg = (
            Assignment.objects.filter(
                reporting_period=p,
                form_definition__code__in=PROGRESS_FORMS,
                status__in=(AssignmentStatus.SUBMITTED, AssignmentStatus.IN_PROGRESS),
            )
            .select_related("person", "project", "core", "form_version", "form_definition")
            .order_by("core__name", "project__title")
        )
        for a in asg:
            answers, rows, files = _answers(a, cache)
            flags = [label for code, label in QUICK_ITEMS if answers.get(code) == FLAG[code]]
            people = [
                r
                for r in rows.get("team", [])
                if any((r.get(c) or "").strip() for c, _ in TEAM_COLS)
            ]
            tables = files.get("tables_file")
            answered = any(answers.get(code) for code, _ in QUICK_ITEMS)
            if not people and not tables and not answered:
                continue
            out.append(
                {
                    "a": a,
                    "period": p,
                    "where": a.core.name
                    if a.core_id
                    else (a.project.title if a.project_id else ""),
                    "leader": a.person,
                    "submitted": a.status in DONE,
                    "people": people,
                    "tables": tables,
                    "flags": flags,
                    "details": answers.get("rppr_details") or "",
                }
            )
    return out
