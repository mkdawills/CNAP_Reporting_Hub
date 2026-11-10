"""
"Build a download" (Batch 2, MW 2026-11-06): one Excel workbook tailored to any combination of
reporting periods and grant years, forms, kinds of product, a core, and a project.

Privacy comes first, and every rule is the screens' own:
- Each form is checked against the reader's access separately (apps.reporting.access.form_access),
  and the small-group safeguard is applied to each period separately.
- De-identified respondents are numbered within each period only, in the results page's order, so
  "Respondent 3" in one period can't be followed into another.
- A project or core filter narrows only forms the reader sees with names. On forms the reader sees
  without names, a narrower group could point to one person, so the filter is not applied there and
  the contents sheet says so.
- Products (papers, talks, grants) list names, so the whole page is for administrators only.
Nothing here writes to the database.
"""

import re

from django.db.models import Q
from django.utils import timezone
from openpyxl import Workbook

from apps.common.enums import ConfidentialityClass, GrantStatus, PeriodStatus, PublicationStatus
from apps.forms_engine.models import FormDefinition
from apps.outcomes.models import GrantSubmission, Presentation, Publication
from apps.outcomes.rppr import period as grant_period
from apps.people.models import Core, Project
from apps.reporting.access import IDENTIFIED, form_access
from apps.reporting.models import ReportingPeriod
from apps.reporting.services import exports

PRODUCT_KINDS = (
    ("papers", "Papers"),
    ("talks", "Talks and posters"),
    ("grants", "Grant proposals"),
)


def options(user):
    """What the page offers this reader: periods by grant year, forms with this reader's access, cores, projects."""
    periods = list(
        ReportingPeriod.objects.exclude(status=PeriodStatus.DRAFT).order_by("-display_order")
    )
    years = {}
    for p in periods:
        years.setdefault(p.grant_year, []).append(p)
    forms = []
    for fd in FormDefinition.objects.order_by("sort_order"):
        mode = form_access(user, fd)
        locked = (
            fd.confidentiality_class == ConfidentialityClass.MENTORING
            and not user.has_confidential_mentoring_access()
        )
        forms.append({"fd": fd, "mode": mode, "locked": locked, "report": fd.category == "report"})
    return {
        "years": sorted(years.items(), reverse=True),
        "forms": forms,
        "cores": list(Core.objects.filter(archived_at__isnull=True).order_by("name")),
        "projects": list(Project.objects.filter(archived_at__isnull=True).order_by("title")),
        "kinds": PRODUCT_KINDS,
    }


def parse(user, get):
    """Read the reader's choices from the query string, keeping only what exists and is allowed."""
    labels = set(get.getlist("periods"))
    periods = [
        p
        for p in ReportingPeriod.objects.exclude(status=PeriodStatus.DRAFT).order_by(
            "display_order"
        )
        if p.short_label in labels
    ]
    codes = set(get.getlist("forms"))
    forms = [fd for fd in FormDefinition.objects.order_by("sort_order") if fd.code in codes]
    kinds = [k for k, _ in PRODUCT_KINDS if k in get.getlist("products")]
    years = sorted({int(y) for y in get.getlist("years") if str(y).isdigit()})
    core = (
        Core.objects.filter(pk=get.get("core")).first()
        if str(get.get("core", "")).isdigit()
        else None
    )
    project = (
        Project.objects.filter(pk=get.get("project")).first()
        if str(get.get("project", "")).isdigit()
        else None
    )
    parts = set(get.getlist("parts")) & {"answers", "tables"}
    return {
        "periods": periods,
        "forms": forms,
        "kinds": kinds,
        "years": years,
        "core": core,
        "project": project,
        "parts": parts,
    }


# ------------------------------------------------------------------ products
def _in_years(field, years):
    q = Q()
    for gy in years:
        q |= Q(**{f"{field}__range": grant_period(gy)})
    return q


def _gy(d):
    if not d:
        return ""
    return d.year - 2016 if d.month >= 6 else d.year - 2017


def _common(obj, core, project):
    people = "; ".join(str(x.person) for x in obj.people.all())
    projects = "; ".join(x.project.title for x in obj.project_links.all())
    res = "; ".join(
        sorted(
            {
                x.resource.name
                for x in obj.resource_links.all()
                if not getattr(x, "is_anticipated", False)
            }
        )
    )
    return people, projects, res


def _filtered(qs, core, project):
    if core:
        qs = qs.filter(resource_links__resource__core=core)
    if project:
        qs = qs.filter(project_links__project=project)
    return qs.distinct().prefetch_related(
        "people__person", "project_links__project", "resource_links__resource"
    )


def product_rows(kind, years, core=None, project=None):
    live = {"archived_at__isnull": True}
    if kind == "papers":
        qs = _filtered(
            Publication.objects.filter(
                _in_years("publication_date", years), status=PublicationStatus.PUBLISHED, **live
            ),
            core,
            project,
        ).order_by("publication_date")
        head = [
            "Grant year",
            "Title",
            "Journal",
            "Published on",
            "CNAP people",
            "Projects",
            "Center resources used",
        ]
        rows = [
            [
                _gy(o.publication_date),
                o.title,
                o.journal,
                o.publication_date.isoformat() if o.publication_date else "",
                *_common(o, core, project),
            ]
            for o in qs
        ]
    elif kind == "talks":
        qs = _filtered(
            Presentation.objects.filter(_in_years("presented_on", years), **live), core, project
        ).order_by("presented_on")
        head = [
            "Grant year",
            "Title",
            "Type",
            "Event",
            "Date",
            "CNAP people",
            "Projects",
            "Center resources used",
        ]
        rows = [
            [
                _gy(o.presented_on),
                o.title,
                o.get_presentation_type_display(),
                o.event,
                o.presented_on.isoformat() if o.presented_on else "",
                *_common(o, core, project),
            ]
            for o in qs
        ]
    else:
        q = _in_years("submission_date", years) | _in_years("award_notice_date", years)
        qs = _filtered(
            GrantSubmission.objects.filter(q, **live).exclude(status=GrantStatus.PLANNED),
            core,
            project,
        ).order_by("submission_date")
        head = [
            "Grant year submitted",
            "Title",
            "Version",
            "Funding agency",
            "Mechanism",
            "Status",
            "Submitted on",
            "Award notice",
            "CNAP people",
            "Projects",
            "Center resources used",
        ]
        rows = [
            [
                _gy(o.submission_date),
                o.project_title,
                o.version_label,
                o.funding_agency,
                o.mechanism,
                o.get_status_display(),
                o.submission_date.isoformat() if o.submission_date else "",
                o.award_notice_date.isoformat() if o.award_notice_date else "",
                *_common(o, core, project),
            ]
            for o in qs
        ]
    return head, rows


# ------------------------------------------------------------------ the workbook
def build(user, choice, *, tables_csv=None):
    """The tailored workbook. `tables_csv(period, fd)` returns the results-table CSV text the reader may see."""
    wb = Workbook()
    used = {"contents"}
    contents = wb.active
    contents.title = "Contents"
    lines = []
    core, project = choice["core"], choice["project"]
    narrow = " and ".join(
        x
        for x in (
            (f"core: {core.name}" if core else ""),
            (f"project: {project.title}" if project else ""),
        )
        if x
    )

    for fd in choice["forms"]:
        mode = form_access(user, fd)
        if not mode:
            lines.append(
                [
                    fd.name,
                    "Not included: your access doesn’t include individual responses to this form.",
                ]
            )
            continue
        apply_filter = mode == IDENTIFIED and (core or project)
        if "answers" in choice["parts"] and choice["periods"]:
            header, rows, notes = None, [], []
            for p in choice["periods"]:
                if not p.assignments.exists():
                    notes.append(
                        f"{p.name}: this reporting session predates the Reporting Hub, so there are only imported averages, no individual responses."
                    )
                    continue
                data = exports.form_answers(
                    user,
                    fd,
                    p,
                    core=core if apply_filter else None,
                    project=project if apply_filter else None,
                )
                if data["blocked"]:
                    notes.append(f"{p.name}: {data['blocked']}.")
                    continue
                if not data["rows"] and not data["columns"]:
                    continue
                h = ["CNAP reporting session"] + data["lead"] + [pr for _, pr in data["columns"]]
                if header is None:
                    header = h
                rows += (
                    [[p.name] + r for r in data["rows"]]
                    if h == header
                    else [[p.name] + r for r in data["rows"]]
                )
            ws = wb.create_sheet()
            ws.title = exports._safe_title(fd.name, used)
            sheet_notes = [
                "With names."
                if mode == IDENTIFIED
                else "Without names. Respondents are numbered within each reporting session only, so a number can’t be followed from one reporting session to another.",
                "Rating questions show the number chosen (for example, 4 for Good).",
            ]
            if (core or project) and mode == IDENTIFIED:
                sheet_notes.append(f"Narrowed to {narrow}.")
            elif core or project:
                sheet_notes.append(
                    "Not narrowed by core or project: on a form you see without names, a narrower group could point to one person."
                )
            sheet_notes += notes
            exports.write_sheet(
                ws,
                fd.name,
                header or ["Note"],
                rows
                if header
                else [["No completed responses in the reporting sessions you chose."]],
                notes=sheet_notes,
                widths=[18, 24],
            )
            lines.append(
                [
                    fd.name,
                    f"Sheet “{ws.title}”: {len(rows)} response{'s' if len(rows) != 1 else ''}"
                    + ("" if not notes else ", with notes")
                    + ".",
                ]
            )
        if "tables" in choice["parts"] and tables_csv and choice["periods"]:
            ws = wb.create_sheet()
            ws.title = exports._safe_title(f"{fd.name[:20]} – tables", used)
            r = 1
            for p in choice["periods"]:
                text = tables_csv(p, fd)
                if not text:
                    continue
                part = wb.create_sheet()
                exports.write_csv_sheet(part, exports.csv_rows(text), title=p.name)
                for row in part.iter_rows():
                    for c in row:
                        ws.cell(row=r + c.row - 1, column=c.column, value=c.value)._style = c._style
                r += part.max_row + 2
                wb.remove(part)
            lines.append(
                [
                    f"{fd.name}: results tables",
                    f"Sheet “{ws.title}”: one block per reporting session.",
                ]
            )

    if choice["kinds"] and choice["years"]:
        for kind, name in PRODUCT_KINDS:
            if kind not in choice["kinds"]:
                continue
            head, rows = product_rows(kind, choice["years"], core, project)
            ws = wb.create_sheet()
            ws.title = exports._safe_title(name, used)
            yrs = ", ".join(f"Year {y}" for y in choice["years"])
            exports.write_sheet(
                ws,
                name,
                head,
                rows,
                notes=[yrs + "." + (f" Narrowed to {narrow}." if narrow else "")],
            )
            lines.append(
                [name, f"Sheet “{ws.title}”: {len(rows)} entr{'ies' if len(rows) != 1 else 'y'}."]
            )

    picked = [
        "Reporting sessions: " + (", ".join(p.name for p in choice["periods"]) or "none"),
        "Grant years for products: " + (", ".join(f"Year {y}" for y in choice["years"]) or "none"),
        f"Narrowed to {narrow}." if narrow else "Not narrowed by core or project.",
        f"Downloaded {timezone.localdate():%B %-d, %Y} by {user.get_full_name() or user.get_username()}. Each sheet follows the same access rules as the screens.",
    ]
    exports.write_sheet(
        contents,
        "Your custom download",
        ["Part", "Where to find it"],
        lines or [["Nothing chosen", "Please choose at least one form or kind of product."]],
        notes=picked,
        widths=[48, 90],
    )
    slug = re.sub(
        r"[^A-Za-z0-9]+", "-", "-".join(p.short_label for p in choice["periods"][:3]) or "products"
    ).strip("-")
    return exports.workbook_response(wb, f"CNAP-custom-{slug}.xlsx")
