"""The evaluator's side of the core reports (MW 2026-11-08): read, hold back, reflect, release."""

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts import access
from apps.analytics import core_reports as cr
from apps.common.enums import PeriodStatus
from apps.forms_engine.models import FormDefinition
from apps.reporting.access import IDENTIFIED, form_access
from apps.reporting.models import ReportingPeriod

from ..decorators import admin_view, manage_action

RELEASABLE = (PeriodStatus.CLOSED, PeriodStatus.FINALIZED)


def _load(label, code):
    p = get_object_or_404(ReportingPeriod, short_label=label)
    fd = get_object_or_404(FormDefinition, code=code)
    if not cr.is_core_survey(fd):
        raise Http404("Only the user survey about a core has a core report.")
    return p, fd


@admin_view
def core_report(request, label, code):
    p, fd = _load(label, code)
    if not form_access(request.user, fd):
        raise PermissionDenied
    report = cr.get(fd, p)
    hidden = set(report.hidden_answers or [])
    written = cr.written_answers(fd, p)
    if form_access(request.user, fd) != IDENTIFIED and cr.small_group(fd, p):
        written = []  # the same small-group rule as the de-identified results page
    for g in written:
        for x in g["answers"]:
            x["hidden"] = x["id"] in hidden
    from apps.people.models import PersonRelationship
    from django.db.models import Q
    from django.utils import timezone

    today = timezone.localdate()
    directors = sorted(
        {
            r.person.full_name
            for r in PersonRelationship.objects.filter(
                core=fd.about_core, relationship_type__code="core_director", effective_from__lte=today
            )
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=today))
            .select_related("person")
        },
        key=lambda n: n.split()[-1],
    )
    return render(
        request,
        "manage/core_report.html",
        {
            "p": p,
            "fd": fd,
            "core": fd.about_core,
            "report": report,
            "written": written,
            "themes": cr.themes_text(fd, p),
            "small": cr.small_group(fd, p),
            "full": cr.full_count(fd, p),
            "min_n": settings.SMALL_N_THRESHOLD,
            "directors": directors,
            "can_manage": access.can_manage(request.user),
            "releasable": p.status in RELEASABLE,
            "changed": cr.changed_since_release(report),
        },
    )


@manage_action
def core_report_save(request, label, code):
    p, fd = _load(label, code)
    report = cr.get(fd, p)
    valid = {x["id"] for g in cr.written_answers(fd, p) for x in g["answers"]}
    report.reflections = request.POST.get("reflections", "").strip()
    report.hidden_answers = sorted(
        {int(v) for v in request.POST.getlist("hide") if v.isdigit() and int(v) in valid}
    )
    report.save()
    action = request.POST.get("action", "save")
    if action == "release":
        if p.status not in RELEASABLE:
            messages.error(request, "A core report can be released once the reporting session closes.")
        else:
            cr.release(request.user, report)
            messages.success(request, f"Released to the {fd.about_core.name} directors.")
    elif action == "withdraw" and report.released_at:
        cr.withdraw(request.user, report)
        messages.success(request, f"Withdrawn. The {fd.about_core.name} Core directors no longer see this core report.")
    else:
        messages.success(request, "Saved. The core directors see nothing until you release the core report.")
    return redirect("manage:core_report", label, code)
