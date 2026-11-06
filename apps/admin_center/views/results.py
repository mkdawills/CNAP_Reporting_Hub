"""Results in the site-visit report layout, response reading, exports (Milestones 7 and 8)."""

import csv
import io

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.common import prototype
from apps.accounts import access
from apps.analytics import report as rpt
from apps.analytics import snapshots
from apps.audit.models import AuditLog, record_event
from apps.common.enums import COMPLETE_STATUSES, ConfidentialityClass, FormCategory, PeriodStatus
from apps.forms_engine.models import FormDefinition
from apps.portal import presenters
from apps.reporting.access import (
    DEIDENTIFIED,
    IDENTIFIED,
    deidentified_rows_allowed,
    form_access,
    respondent_label_order,
    response_access,
)
from apps.reporting.models import Assignment, ReportingPeriod
from apps.reporting.services import exports
from django.utils import timezone

from ..decorators import admin_view, manage_action


def _period(request, label=None):
    qs = ReportingPeriod.objects.order_by("-display_order")
    label = label or request.GET.get("period")
    p = qs.filter(short_label=label).first() if label else None
    # Default: the latest finalized period (today Y9 Spring); open periods are still selectable for live results.
    return (
        p
        or qs.filter(status=PeriodStatus.FINALIZED).first()
        or qs.exclude(status=PeriodStatus.DRAFT).first()
    )


@admin_view
def results(request):
    p = _period(request)
    periods = ReportingPeriod.objects.exclude(status=PeriodStatus.DRAFT).order_by("-display_order")
    cards = []
    if p:
        historical = not p.assignments.exists()
        imported = set()
        if historical:
            # List every form, so nobody wonders where a survey went: forms without imported
            # averages get a "nothing on file" row instead of disappearing (MW 2026-11-03).
            imported = set(
                p.snapshots.filter(provenance="aggregate_import")
                .values_list("results__group_key", flat=True)
                .distinct()
            ) - {None, ""}
            forms = FormDefinition.objects.order_by("sort_order")
        else:
            forms = (
                FormDefinition.objects.filter(assignments__reporting_period=p)
                .distinct()
                .order_by("sort_order")
            )
        for fd in forms:
            mode = form_access(request.user, fd)
            locked = (
                fd.confidentiality_class == ConfidentialityClass.MENTORING
                and not request.user.has_confidential_mentoring_access()
            )
            comp = None if historical else rpt.completion(fd, p)
            cards.append(
                {
                    "fd": fd,
                    "mode": mode,
                    "locked": locked,
                    "comp": comp,
                    "historical": historical,
                    "no_data": historical and fd.code not in imported,
                }
            )
    return render(
        request,
        prototype.template(request, "results_list", "manage/results.html"),
        {
            "p": p,
            "periods": periods,
            "cards": cards,
            "snapshot": snapshots.latest(p) if p else None,
        },
    )


@admin_view
def form_report(request, label, code):
    p = get_object_or_404(ReportingPeriod, short_label=label)
    fd = get_object_or_404(FormDefinition, code=code)
    if fd.confidentiality_class == ConfidentialityClass.MENTORING and not access.can_read_mentoring(
        request.user
    ):
        raise PermissionDenied("Confidential mentoring data.")
    mode = form_access(request.user, fd)
    data = rpt.build(fd, p, audience="admin")
    rows = []
    if mode and p.assignments.exists():
        done = list(
            Assignment.objects.filter(
                form_definition=fd, reporting_period=p, status__in=COMPLETE_STATUSES
            ).select_related("person", "project", "core", "completion_pathway")
        )
        if mode == IDENTIFIED:
            rows = [
                {
                    "a": a,
                    "label": a.person.full_name,
                    "ctx": a.project.title
                    if a.project_id
                    else (a.core.name if a.core_id and fd.context_kind == "core" else ""),
                }
                for a in sorted(done, key=lambda a: a.person.last_name)
            ]
        elif deidentified_rows_allowed(fd, p):
            rows = [
                {"a": a, "label": f"Respondent {i}", "ctx": ""}
                for i, a in enumerate(respondent_label_order(done, fd, p), start=1)
            ]
    show_verbatims = mode == IDENTIFIED or (
        mode == DEIDENTIFIED and deidentified_rows_allowed(fd, p)
    )
    # Who is behind each count on the "Who responded" line (MW 2026-11-04). Names only where
    # this person's access to the form allows names.
    who = None
    if mode == IDENTIFIED and p.assignments.exists():
        every = list(
            Assignment.objects.filter(form_definition=fd, reporting_period=p)
            .exclude(status="exempt")
            .select_related("person")
            .order_by("person__last_name", "person__first_name")
        )
        names = lambda xs: sorted({a.person.full_name for a in xs}, key=lambda n: n.split()[-1])
        who = {
            "received": names(every),
            "responded": names([a for a in every if a.status in COMPLETE_STATUSES]),
            "full": names([a for a in every if a.status == "submitted"]),
            "opted": names([a for a in every if a.status == "completed_opt_out"]),
            "waiting": names([a for a in every if a.status not in COMPLETE_STATUSES]),
        }
    return render(
        request,
        prototype.template(
            request, f"results:{fd.code}", "manage/report.html"
        ),
        {
            **data,
            "mode": mode,
            "rows": rows,
            "show_verbatims": show_verbatims,
            "who": who,
            "deid_blocked": mode == DEIDENTIFIED and not deidentified_rows_allowed(fd, p),
            "can_edit_themes": access.can_manage(request.user)
            and data["snapshot"] is not None
            and data["snapshot"].provenance != "aggregate_import",
        },
    )


@manage_action
def save_themes(request, label, code):
    p = get_object_or_404(ReportingPeriod, short_label=label)
    snap = snapshots.latest(p)
    if not snap:
        messages.error(request, "Generate results before writing themes.")
    else:
        snapshots.set_theme_summary(
            request.user, snap, code, request.POST.get("themes", "").strip()
        )
        messages.success(request, "Themes saved.")
    return redirect("manage:form_report", label, code)


@admin_view
def response(request, pk):
    a = get_object_or_404(
        Assignment.objects.select_related(
            "form_definition", "form_version", "reporting_period", "person", "project", "core"
        ),
        pk=pk,
    )
    mode = response_access(request.user, a)
    if not mode:
        raise PermissionDenied
    if mode == DEIDENTIFIED and not deidentified_rows_allowed(
        a.form_definition, a.reporting_period
    ):
        raise PermissionDenied("Fewer than 5 people completed this survey.")
    ctx = presenters.form_page(request, a, editable=False)
    ctx.update({"reader": True, "deidentified": mode == DEIDENTIFIED})
    if mode == DEIDENTIFIED:
        ctx["prefill"] = []
        ctx["context_line"] = ""
    record_event(
        request.user,
        AuditLog.Action.UPDATE,
        a,
        new={"read_by_admin": True, "deidentified": mode == DEIDENTIFIED},
    ) if False else None
    return render(request, prototype.template(request, "response", "manage/response.html"), ctx)


@admin_view
def export_report(request, label, code):
    """Table 1 and the year-over-year table as a CSV, for the site-visit report."""
    p = get_object_or_404(ReportingPeriod, short_label=label)
    fd = get_object_or_404(FormDefinition, code=code)
    if fd.confidentiality_class == ConfidentialityClass.MENTORING and not access.can_read_mentoring(
        request.user
    ):
        raise PermissionDenied
    data = rpt.build(fd, p, audience="admin")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([fd.name, p.name])
    if data["tables"]:
        t0 = data["tables"][0]
        line = f"Table {t0['no']} data captures {t0['section'].title.rstrip(':').lower()} for the {fd.name}. "
        line += (
            f"{data['opened']} individual{'s' if data['opened'] != 1 else ''} completed the survey."
        )
        if data["opted_out"]:
            line += f" Once inside, {data['opted_out']} of the {data['opened']} opted out by selecting “{data['optout_label']}”."
        if t0["has_na"]:
            line += (
                " Occasionally, respondents selected N/A in response to individual survey items"
                f" (observable when the Total column is less than {data['full']})."
            )
        w.writerow(["Report wording", line])
    for t in data["tables"]:
        w.writerow([])
        w.writerow([f"Table {t['no']}. {t['section'].title}"])
        head = ["Item", "Mean", "SD"]
        for s in t["scale"]:
            head += [f"({s['num']}) {s['text']} n", "%"]
        w.writerow(head + ["Total"])
        for r in t["rows"]:
            line = [
                f"{r['no']}. {r['q'].prompt}",
                f"{r['mean']:.1f}" if r["mean"] is not None else "",
                f"{r['sd']:.1f}",
            ]
            for c in r["cells"]:
                line += [c["count"], f"{c['pct']}%"]
            w.writerow(line + [r["n"]])
        gm = t["grand_mean"]
        line = [
            "Grand mean, totals and %",
            f"{gm:.1f}" if gm is not None else "",
            f"{t['grand_sd']:.1f}",
        ]
        for c in t["totals"]:
            line += [c["count"], f"{c['pct']}%"]
        w.writerow(line + [t["total"]])
        if t.get("lon"):
            w.writerow([])
            w.writerow([f"Table {t['lon']['no']}. Mean ratings by reporting period"])
            w.writerow(["Item"] + [pp.short_label for pp in t["lon"]["periods"]])
            for r in t["lon"]["rows"]:
                w.writerow(
                    [f"{r['no']}. {r['prompt']}" if r["no"] else r["prompt"]]
                    + [f"{c['mean']:.1f}" if c["mean"] is not None else "" for c in r["cells"]]
                )
    record_event(request.user, AuditLog.Action.EXPORT, f"report:{label}:{code}")
    resp = HttpResponse(buf.getvalue(), content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="{code}_{label.replace(" ", "_")}.csv"'
    if request.GET.get("format") == "xlsx":  # the same cells as the CSV, as a formatted workbook (MW 2026-11-05)
        return exports.csv_to_xlsx(resp, f'{code}_{label.replace(" ", "_")}.xlsx', title=f"{fd.name}, {p.name}")
    return resp


@admin_view
def export_answers(request, label, code):
    """Each form's answers for a period, one row per respondent, as an Excel workbook (MW 2026-11-05).
    Same access as reading the responses on screen."""
    p = get_object_or_404(ReportingPeriod, short_label=label)
    fd = get_object_or_404(FormDefinition, code=code)
    resp = exports.form_answers_workbook(request.user, fd, p)
    record_event(request.user, AuditLog.Action.EXPORT, f"answers:{label}:{code}")
    return resp


@admin_view
def export_everything(request, label):
    """One workbook for a reporting period: a contents sheet, each form's answers this reader may see,
    and the papers, talks, and grants lists (MW 2026-11-05)."""
    from openpyxl import Workbook

    from apps.reporting.services.exports import _safe_title, add_form_sheets, csv_rows, write_csv_sheet, write_sheet

    from . import outcomes as outcome_views

    p = get_object_or_404(ReportingPeriod, short_label=label)
    wb = Workbook()
    used = {"contents"}
    contents = wb.active
    contents.title = "Contents"
    lines = []
    forms = FormDefinition.objects.filter(assignments__reporting_period=p).distinct().order_by("sort_order")
    for fd in forms:
        if not form_access(request.user, fd):
            lines.append([fd.name, "Not included: your access doesn’t include individual responses to this form."])
            continue
        sheet, note = add_form_sheets(wb, request.user, fd, p, used)
        lines.append([fd.name, f"Sheet “{sheet}”: {note}."])
    for kind, name in (("publications", "Papers"), ("talks", "Talks and posters"), ("grants", "Grant proposals")):
        try:
            csv_resp = outcome_views.export(request, kind)
        except PermissionDenied:
            lines.append([name, "Not included: your access doesn’t include this list."])
            continue
        ws = wb.create_sheet()
        ws.title = _safe_title(name, used)
        write_csv_sheet(ws, csv_rows(csv_resp.content.decode("utf-8-sig")), title=f"{name}: every entry in the Hub")
        lines.append([name, f"Sheet “{ws.title}”: every entry in the Hub, not only this period."])
    write_sheet(
        contents,
        f"Everything for {p.name}",
        ["Part", "Where to find it"],
        lines,
        notes=[f"Downloaded {timezone.localdate():%B %-d, %Y} by {request.user.get_full_name() or request.user.get_username()}.", "Each sheet follows the same access rules as the screens: names appear only where your access shows names."],
        widths=[44, 90],
    )
    record_event(request.user, AuditLog.Action.EXPORT, f"everything:{label}")
    return exports.workbook_response(wb, f"CNAP-{label.replace(' ', '-')}-everything.xlsx")


@admin_view
def print_response(request, pk):
    """One completed form as PDF or Word, with the same access as reading it on screen (MW 2026-11-05)."""
    from apps.reporting.services import documents

    a = get_object_or_404(Assignment.objects.select_related("form_definition", "form_version", "reporting_period", "person"), pk=pk)
    mode = response_access(request.user, a)
    if not mode:
        raise PermissionDenied
    if mode == DEIDENTIFIED and not deidentified_rows_allowed(a.form_definition, a.reporting_period):
        raise PermissionDenied("Fewer than 5 people completed this survey.")
    ctx = presenters.form_page(request, a, editable=False)
    named = mode == IDENTIFIED
    label = None
    if not named:
        done = list(Assignment.objects.filter(form_definition=a.form_definition, reporting_period=a.reporting_period, status__in=COMPLETE_STATUSES))
        order = respondent_label_order(done, a.form_definition, a.reporting_period)
        label = f"Respondent {next((i for i, x in enumerate(order, 1) if x.pk == a.pk), '')}"
    fmt = "docx" if request.GET.get("fmt") == "docx" else "pdf"
    blocks = documents.response_blocks(ctx, named=named, label=label)
    record_event(request.user, AuditLog.Action.EXPORT, f"print:response:{a.pk}")
    who = a.person.last_name if named else (label or "response")
    return documents.file_response([blocks], a.form_definition.name, f"{a.form_definition.name} {a.reporting_period.short_label} {who}", fmt)


@admin_view
def print_form_all(request, label, code):
    """Every completed form for a period in one document (?blank=1: the blank form), as PDF or Word.
    Names only where the reader sees names; otherwise numbered as on the results page (MW 2026-11-05)."""
    from apps.reporting.services import documents

    p = get_object_or_404(ReportingPeriod, short_label=label)
    fd = get_object_or_404(FormDefinition, code=code)
    fmt = "docx" if request.GET.get("fmt") == "docx" else "pdf"
    if request.GET.get("blank"):
        if fd.confidentiality_class == ConfidentialityClass.MENTORING and not access.can_read_mentoring(request.user):
            raise PermissionDenied
        version = fd.versions.order_by("-version_no").first() if hasattr(fd, "versions") else None
        a0 = Assignment.objects.filter(form_definition=fd, reporting_period=p).select_related("form_version").first()
        version = a0.form_version if a0 else version
        return documents.file_response([documents.blank_blocks(version)], fd.name, f"{fd.name} blank", fmt)
    mode = form_access(request.user, fd)
    if not mode:
        raise PermissionDenied("Your access doesn’t include individual responses to this form.")
    done = list(Assignment.objects.filter(form_definition=fd, reporting_period=p, status__in=COMPLETE_STATUSES).select_related("person", "form_version", "reporting_period", "form_definition"))
    if mode == DEIDENTIFIED and not deidentified_rows_allowed(fd, p):
        raise PermissionDenied("Fewer than 5 people completed this survey.")
    named = mode == IDENTIFIED
    ordered = sorted(done, key=lambda a: (a.person.last_name, a.person.first_name)) if named else respondent_label_order(done, fd, p)
    cover = [("title", fd.name), ("meta", [("CNAP reporting period", p.name), ("Completed forms", len(ordered)), ("Names", "Shown" if named else "Not shown. Respondents are numbered as on the results page.")])]
    docs = [cover] + [documents.response_blocks(presenters.form_page(request, a, editable=False), named=named, label=f"Respondent {i}") for i, a in enumerate(ordered, 1)]
    record_event(request.user, AuditLog.Action.EXPORT, f"print:all:{label}:{code}")
    return documents.file_response(docs, f"{fd.name}, {p.name}", f"{fd.name} {label} all", fmt)


@admin_view
def export_builder(request):
    """Build a download (MW 2026-11-06): any combination of periods, grant years, forms, products, a core,
    and a project, in one Excel workbook. Same access rules as the screens, form by form and period by period."""
    from django.conf import settings
    from django.http import Http404

    from apps.reporting.services import builder

    if not getattr(settings, "UI_PROTOTYPE", False):
        raise Http404
    if request.GET.get("go"):
        choice = builder.parse(request.user, request.GET)

        def tables_csv(p, fd):
            try:
                r = export_report(request, p.short_label, fd.code)
            except PermissionDenied:
                return None
            return r.content.decode("utf-8-sig") if r.status_code == 200 else None

        record_event(request.user, AuditLog.Action.EXPORT, "custom:" + ",".join(p.short_label for p in choice["periods"]) + ";" + ",".join(f.code for f in choice["forms"]))
        return builder.build(request.user, choice, tables_csv=tables_csv)
    ctx = builder.options(request.user)
    from apps.outcomes.rppr import current_year

    ctx["now"] = current_year()
    ctx["pre_period"] = request.GET.get("period", "")
    ctx["pre_form"] = request.GET.get("form", "")
    return render(request, prototype.template(request, "builder", "proto/builder.html"), ctx)


def _unused():
    return FormCategory
