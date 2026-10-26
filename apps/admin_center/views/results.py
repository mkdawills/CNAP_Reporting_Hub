"""Results in the site-visit report layout, response reading, exports (Milestones 7 and 8)."""

import csv
import io

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

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

from ..decorators import admin_view, manage_action


def _period(request, label=None):
    qs = ReportingPeriod.objects.order_by("-display_order")
    label = label or request.GET.get("period")
    p = qs.filter(short_label=label).first() if label else None
    return p or qs.exclude(status=PeriodStatus.DRAFT).first()


@admin_view
def results(request):
    p = _period(request)
    periods = ReportingPeriod.objects.exclude(status=PeriodStatus.DRAFT).order_by("-display_order")
    cards = []
    if p:
        historical = not p.assignments.exists()
        if historical:
            codes = (
                p.snapshots.filter(provenance="aggregate_import")
                .values_list("results__group_key", flat=True)
                .distinct()
            )
            forms = FormDefinition.objects.filter(code__in=[c for c in codes if c]).order_by(
                "sort_order"
            )
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
                {"fd": fd, "mode": mode, "locked": locked, "comp": comp, "historical": historical}
            )
    return render(
        request,
        "manage/results.html",
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
    return render(
        request,
        "manage/report.html",
        {
            **data,
            "mode": mode,
            "rows": rows,
            "show_verbatims": show_verbatims,
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
    return render(request, "manage/response.html", ctx)


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
    return resp


def _unused():
    return FormCategory
