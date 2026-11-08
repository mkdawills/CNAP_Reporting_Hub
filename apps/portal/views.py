"""
What respondents see (Milestones 4 and 6): My tasks, the form pages, My
history, Center results and Profile. Nobody here can see another person's
answers; the form page refuses anyone but the respondent (administrators read
responses from their own screens, under their own rules).
"""

import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts import access
from apps.common.enums import COMPLETE_STATUSES, PeriodStatus
from apps.people.models import Person
from apps.people.services import SENIOR_KEY_TYPES, is_external, normalize_orcid, update_person
from apps.reporting.models import Assignment, File, ReportingPeriod
from apps.reporting.services import responses as rs
from apps.reporting.services.assignments import due_label

from . import presenters


@login_required
def home(request):
    """Send people where they work: respondents to My tasks, administrators to their home."""
    person = request.user.person
    if person.current_relationships().exists() or person.assignments.exists():
        return redirect("portal:tasks")
    if access.can_view_admin(request.user):
        return redirect("manage:home")
    return render(request, "portal/no_tasks.html")


@login_required
def tasks(request):
    person = request.user.person
    period = (
        ReportingPeriod.objects.filter(status=PeriodStatus.OPEN, assignments__person=person)
        .distinct()
        .order_by("-display_order")
        .first()
    )
    if not period:
        from apps.outcomes import cpcheck

        return render(
            request,
            "portal/tasks.html",
            {
                "period": None,
                "cp_check": cpcheck.pending_for(person),
                "sow_excerpts": [d for d in person.documents.all() if d.excerpt],
                **_extras(),
            },
        )
    mine = list(
        Assignment.objects.filter(person=person, reporting_period=period).select_related(
            "form_definition", "form_version", "project", "core", "completion_pathway"
        )
    )
    ctx = presenters.task_list(person, period, mine, just_done=request.GET.get("done"))
    ctx["due"] = due_label(period)
    from .outcome_views import task_item

    oc = task_item(person, period)
    ctx["outcome"] = oc
    from apps.outcomes import cpcheck

    ctx["cp_check"] = cpcheck.pending_for(person)
    ctx["sow_excerpts"] = [d for d in person.documents.all() if d.excerpt]
    from django.utils import timezone as _tz

    hour = _tz.localtime().hour
    ctx["greeting"] = (
        "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
    )
    ctx.update(_extras())
    ctx["done_count"] = len(ctx["done"]) + (1 if oc and oc["done"] else 0)
    if oc:  # the publications-and-grants check-in counts as one task
        ctx["total"] += 1
        if not oc["done"]:
            ctx["todo"] += 1
            ctx["minutes_left"] += oc["minutes"]
        ctx["done_n"] = ctx["total"] - ctx["todo"]
        ctx["pct"] = round(100 * ctx["done_n"] / ctx["total"]) if ctx["total"] else 0
    if ctx.get("period"):
        from .presenters import todo_summary

        ctx["todo_summary"] = todo_summary(
            ctx.get("todo_surveys", 0), ctx.get("todo_reports", 0), 1 if oc and not oc["done"] else 0
        )
    from apps.common import prototype

    return render(request, prototype.template(request, "tasks", "portal/tasks.html"), ctx)


def _own_assignment(request, pk):
    a = get_object_or_404(
        Assignment.objects.select_related(
            "form_definition", "form_version", "reporting_period", "project", "core", "person"
        ),
        pk=pk,
    )
    if a.person_id != request.user.person_id:
        raise PermissionDenied("Only the person who received a survey or report can open it here.")
    return a


@login_required
def helpful_doc(request, pk):
    """A file the evaluator shared with everyone (Helpful documents)."""
    from apps.reporting.models import HelpfulDocument

    d = get_object_or_404(HelpfulDocument.objects.select_related("file"), pk=pk, is_active=True)
    if not d.file_id:
        raise Http404
    return FileResponse(
        d.file.storage_key.open("rb"), as_attachment=True, filename=d.file.original_filename
    )


def _extras():
    """What sits below the tasks: the Center's output this year and the helpful documents (MW 2026-10-28)."""
    from apps.outcomes import snapshot
    from apps.reporting.models import HelpfulDocument

    return {
        "made": snapshot.this_year(),
        "trend": snapshot.by_year(),
        "docs": list(HelpfulDocument.objects.filter(is_active=True).select_related("file")),
    }


@login_required
def cp_check(request, pk):
    """The February question: has your Current and Pending changed since the fall?"""
    from apps.outcomes import cpcheck
    from apps.reporting.models import CurrentPendingCheck

    c = cpcheck.with_dates(
        get_object_or_404(
            CurrentPendingCheck.objects.select_related(
                "assignment__person", "assignment__reporting_period"
            ),
            pk=pk,
        )
    )
    if c.assignment.person_id != request.user.person_id:
        raise PermissionDenied("Only the person asked can answer.")
    error = ""
    if request.method == "POST" and not c.answered_at:
        changed = request.POST.get("action") == "changed"
        try:
            cpcheck.answer(
                c, request.user, changed=changed, upload=request.FILES.get("file-current_pending")
            )
        except cpcheck.CheckError as exc:
            error = str(exc)
        else:
            return redirect("portal:cp_check", pk)
    from apps.common import prototype

    return render(
        request, prototype.template(request, "cp_check", "portal/cp_check.html"), {"c": c, "error": error}
    )


@login_required
def mftrp_form(request, pk):
    """The MFTRP certification with the person's own name filled in, from their NIH documents task."""
    from django.http import HttpResponse

    from apps.outcomes import mftrp

    a = _own_assignment(request, pk)
    if a.form_definition.code != "nih_documents":
        raise Http404
    resp = HttpResponse(mftrp.build(a.person), content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{mftrp.filename(a.person)}"'
    return resp


@login_required
@require_POST
def autosave(request, pk):
    """Save answers as they're typed (MW 2026-10-28). Files are saved only with Save draft or Submit."""
    from django.http import JsonResponse
    from django.utils import timezone as _tz

    a = _own_assignment(request, pk)
    if not rs.is_editable(a, request.user) or a.reporting_period.in_preview:
        return JsonResponse({"ok": False, "reason": "locked"}, status=409)
    try:
        problems = rs.save_draft(a, request.user, request.POST, None)
    except rs.LockedError:
        return JsonResponse({"ok": False, "reason": "locked"}, status=409)
    return JsonResponse(
        {"ok": True, "problems": problems, "at": _tz.localtime().strftime("%-I:%M %p")}
    )


@login_required
def form(request, pk):
    a = _own_assignment(request, pk)
    gate = presenters.confidential_gate(request, a)
    if gate:
        return gate
    if a.reporting_period.in_preview:
        return redirect("portal:preview", pk)
    editable = rs.is_editable(a, request.user)
    errors, missing = [], []
    if request.method == "POST":
        if not editable:
            raise PermissionDenied
        action = request.POST.get("action", "save")
        row_action = action if action.startswith("remove:") else None
        try:
            errors = rs.save_draft(
                a, request.user, request.POST, request.FILES, row_action=row_action
            )
        except rs.LockedError as exc:
            messages.error(request, str(exc))
            return redirect("portal:form", pk)
        if action.startswith("sheet:") and not errors:
            messages.success(request, "Your sheet’s rows were added. Check them below.")
            return redirect(f"{reverse('portal:form', args=[pk])}#sec-{action[6:]}")
        if action.startswith("add:"):
            return redirect(
                f"{reverse('portal:form', args=[pk])}?add={action[4:]}#sec-{action[4:]}"
            )
        if action == "submit" and not errors:
            try:
                rs.submit(a, request.user, request=request)
            except rs.SubmitError as exc:
                missing = exc.missing
                errors = [] if missing else [str(exc)]
            else:
                return redirect(f"{reverse('portal:tasks')}?done={a.pk}")
        elif action == "save" and not errors:
            messages.success(
                request, "Draft saved. You can come back to it any time before the reporting session closes."
            )
            return redirect("portal:form", pk)
        elif not errors and row_action:
            return redirect("portal:form", pk)
        a.refresh_from_db()
    ctx = presenters.form_page(request, a, editable=editable, errors=errors, missing=missing)
    from apps.common import prototype

    tpl = prototype.template(request, f"form:{a.form_definition.code}", "portal/form.html")
    return render(request, tpl, ctx)


@login_required
def sheet_template(request, pk, section):
    """The Excel template for one repeatable section of this person's form."""
    from apps.forms_engine.runtime import FormSchema
    from apps.reporting.services import sheets

    a = _own_assignment(request, pk)
    sec = next(
        (s for s in FormSchema(a.form_version).sections if s.code == section and s.is_repeatable),
        None,
    )
    if not sec:
        raise Http404
    name = re.sub(r"[^A-Za-z0-9]+", "_", sec.title or section).strip("_") or "Entries"
    resp = HttpResponse(
        sheets.template(sec),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="{name}_template.xlsx"'
    return resp


@login_required
def preview(request, pk):
    a = _own_assignment(request, pk)
    gate = presenters.confidential_gate(request, a)
    if gate:
        return gate
    ctx = presenters.form_page(request, a, editable=False, preview=True)
    from apps.common import prototype

    return render(request, prototype.template(request, "preview", "portal/form.html"), ctx)


@login_required
@require_POST
def opt_out(request, pk):
    a = _own_assignment(request, pk)
    gate = presenters.confidential_gate(request, a)
    if gate:
        return gate
    try:
        result = rs.quick_opt_out(a, request.user)
    except (rs.LockedError, ValueError) as exc:
        messages.error(request, str(exc))
        return redirect("portal:tasks")
    if result == "open":
        return redirect("portal:form", pk)
    return redirect(f"{reverse('portal:tasks')}?done={a.pk}")


@login_required
@require_POST
def edit_again(request, pk):
    """The respondent reopens their own submitted form while the period is open; the submitted copy is kept."""
    a = _own_assignment(request, pk)
    if not rs.can_self_reopen(a, request.user):
        messages.error(request, "This survey or report can’t be changed now. Ask the evaluator if you need to.")
        return redirect("portal:form", pk)
    rs.reopen(request.user, a, reason="Reopened by the respondent")
    messages.success(request, "Your answers are open to change. Submit again when you’re done.")
    return redirect("portal:form", pk)


@login_required
def history(request):
    person = request.user.person
    done = (
        Assignment.objects.filter(person=person, status__in=COMPLETE_STATUSES)
        .select_related(
            "form_definition", "reporting_period", "project", "core", "completion_pathway"
        )
        .order_by("-reporting_period__display_order", "form_definition__sort_order")
    )
    return render(request, "portal/history.html", {"rows": presenters.history_rows(done)})


@login_required
def center_results(request):
    from apps.common import prototype
    from apps.outcomes import rppr, snapshot

    view = "products" if request.GET.get("view") == "products" else "surveys"
    ctx = {"view": view}
    if view == "products":
        now = rppr.current_year()
        trend = snapshot.by_year(now)
        first = trend["first"] if trend else now
        years = list(range(now, first - 1, -1))
        # Any combination of grant years, or all of them (MW 2026-11-06): ?years=8&years=10 or ?years=all.
        # The older ?year=10 still works.
        picked = request.GET.getlist("years")
        if "all" in picked:
            chosen = list(years)
        else:
            chosen = [int(x) for x in picked + [request.GET.get("year", "")] if str(x).isdigit() and int(x) in years]
        chosen = sorted(set(chosen)) or [now]
        gy = chosen[-1]
        prod = dict(snapshot.products_for(chosen)) if len(chosen) > 1 else dict(snapshot.products(gy))
        prod.update(n_papers=len(prod["papers"]), n_talks=len(prod["talks"]), n_awards=len(prod["awards"]))
        all_years = len(chosen) == len(years) and len(years) > 1
        if len(chosen) == 1:
            span = f"Year {chosen[0]}"
        elif chosen == list(range(chosen[0], chosen[-1] + 1)):
            span = f"Years {chosen[0]} to {chosen[-1]}"
        else:
            span = "Years " + ", ".join(str(y) for y in chosen[:-1]) + (", and " if len(chosen) > 2 else " and ") + str(chosen[-1])
        ctx.update({"chosen": chosen, "all_years": all_years, "span": f"All years ({span})" if all_years else span, "by_core": snapshot.by_core(chosen), "core_groups": snapshot.CORE_GROUPS})
        # MW 2026-11-04: respondents see counts only. Titles, people, and funders stay with the
        # evaluator, the Center Director, and the Associate Director (the administrator screens).
        show_detail = access.can_view_admin(request.user)
        if not show_detail:
            prod.update(papers=[], talks=[], awards=[])
        ctx.update({"years": years, "prod": prod, "now": now, "show_detail": show_detail})
        return render(request, prototype.template(request, "center_results", "portal/center_results.html"), ctx)
    periods = ReportingPeriod.objects.filter(status=PeriodStatus.FINALIZED).order_by(
        "-display_order"
    )
    selected = None
    if periods:
        label = request.GET.get("period")
        selected = next((p for p in periods if p.short_label == label), periods[0])
    cards = presenters.center_results(selected) if selected else []
    ctx.update({"periods": periods, "selected": selected, "cards": cards})
    return render(request, prototype.template(request, "center_results", "portal/center_results.html"), ctx)


LEVELS = [c for c in Person._meta.get_field("trainee_level").choices]


@login_required
def profile(request):
    from apps.outcomes import rppr
    from apps.people.models import PersonEffort
    from apps.people.services import request_commons_help, set_effort

    person = request.user.person
    gy = rppr.current_year()
    rels = person.current_relationships().select_related("relationship_type", "project", "core")
    in_d1 = any(r.relationship_type.code in rppr.D1_CATEGORY for r in rels)
    if request.method == "POST":
        if request.POST.get("action") == "commons_help":
            request_commons_help(request.user, person, request.POST.get("kind", ""))
            messages.success(
                request,
                "Thanks. The Center evaluator has your request and will get in touch by email.",
            )
            return redirect(reverse("portal:profile") + "#commons")
        orcid = person.orcid
        if "orcid" in request.POST:
            try:
                orcid = normalize_orcid(request.POST.get("orcid", "")[:60])
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect(reverse("portal:profile") + "#orcid")
        update_person(
            request.user,
            person,
            orcid=orcid,
            department=request.POST.get("department", "")[:200],
            position_title=request.POST.get("position_title", "")[:200],
            era_commons_id=request.POST.get("era_commons_id", "")[:40],
            trainee_level=(
                request.POST.get("trainee_level", "")
                if request.POST.get("trainee_level", "") in dict(LEVELS)
                else ""
            ),
        )
        if in_d1 and "calendar_months" in request.POST:
            try:
                set_effort(request.user, person, gy, request.POST.get("calendar_months"))
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect("portal:profile")
        messages.success(request, "Profile saved.")
        return redirect("portal:profile")
    effort = PersonEffort.objects.filter(person=person, grant_year=gy).first()
    return render(
        request,
        "portal/profile.html",
        {
            "person": person,
            "my_docs": person.documents.select_related("file"),
            "rels": [r for r in rels if r.relationship_type.code != "cnap_member"],
            "on_roster": any(r.relationship_type.code == "cnap_member" for r in rels),
            "levels": LEVELS,
            "is_trainee": any(
                r.relationship_type.code in ("project_student", "student_trainee") for r in rels
            ),
            "in_d1": in_d1,
            "needs_orcid": any(r.relationship_type.code in SENIOR_KEY_TYPES for r in rels),
            "is_external": is_external(person),
            "gy": gy,
            "gy_start": 2016 + gy,
            "effort": effort,
        },
    )


@login_required
def my_document(request, pk):
    """A document on the person's own page, such as their Statement of Work (MW 2026-11-03)."""
    from apps.accounts import access
    from apps.people.models import PersonDocument

    d = get_object_or_404(PersonDocument.objects.select_related("file", "person"), pk=pk)
    if d.person_id != request.user.person_id and not access.can_view_admin(request.user):
        raise PermissionDenied
    f = d.file
    return FileResponse(
        f.storage_key.open("rb"), as_attachment=True, filename=f.original_filename
    )


@login_required
def download(request, file_pk):
    """A file is downloadable by its uploader, or by an administrator allowed to read that response."""
    f = get_object_or_404(File, pk=file_pk)
    link = f.answer_links.select_related("answer__response__assignment").first()
    if link:
        assignment = link.answer.response.assignment
    else:  # a Current and Pending sent in at the February check
        from apps.reporting.models import CurrentPendingCheck

        c = CurrentPendingCheck.objects.filter(file=f).select_related("assignment").first()
        if not c:
            raise Http404
        assignment = c.assignment
    from apps.reporting.access import response_access

    if (
        assignment.person_id != request.user.person_id
        and response_access(request.user, assignment) != "identified"
    ):
        raise PermissionDenied
    if assignment.person_id == request.user.person_id:
        gate = presenters.confidential_gate(request, assignment)
        if gate:
            return gate
    return FileResponse(f.storage_key.open("rb"), as_attachment=True, filename=f.original_filename)


@login_required
def print_form(request, pk):
    """A person's own form as PDF or Word: blank (?blank=1) or as they answered it (MW 2026-11-05).
    Same access as opening the form, including the code check for confidential mentoring forms."""
    from apps.reporting.services import documents

    a = _own_assignment(request, pk)
    gate = presenters.confidential_gate(request, a)
    if gate:
        return gate
    fmt = "docx" if request.GET.get("fmt") == "docx" else "pdf"
    fd = a.form_definition
    if request.GET.get("blank"):
        intro = presenters._intro_for(a, rs.system_answers(a, presenters.FormSchema(a.form_version)))
        blocks = documents.blank_blocks(a.form_version, intro=intro)
        return documents.file_response([blocks], fd.name, f"{fd.name} blank", fmt)
    ctx = presenters.form_page(request, a, editable=False)
    blocks = documents.response_blocks(ctx, named=True)
    return documents.file_response([blocks], fd.name, f"{fd.name} {a.reporting_period.short_label}", fmt)
