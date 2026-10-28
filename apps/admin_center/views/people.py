"""People, CNAP relationships, projects and cores (Milestone 2)."""

from django.contrib import messages
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts import access
from apps.audit.models import AuditLog, record_event
from apps.people import services
from apps.people.models import Core, Person, PersonEmail, PersonRelationship, Project

from ..decorators import admin_view, manage_action, manage_page
from ..forms import (
    EmailForm,
    EndForm,
    HandoffForm,
    PersonEditForm,
    PersonForm,
    ProjectForm,
    RelationshipForm,
)


def _current_rels_prefetch():
    today = timezone.localdate()
    return Prefetch(
        "relationships",
        queryset=PersonRelationship.objects.filter(effective_from__lte=today)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=today))
        .select_related("relationship_type", "project", "core"),
        to_attr="current_rels",
    )


@admin_view
def people(request):
    q = request.GET.get("q", "").strip()
    show = request.GET.get("show", "all")
    qs = Person.objects.active().prefetch_related(_current_rels_prefetch(), "emails")
    if q:
        qs = qs.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(emails__email__icontains=q)
            | Q(institution__icontains=q)
        ).distinct()
    rows = []
    for p in qs:
        codes = {r.relationship_type.code for r in p.current_rels}
        external = services.is_external(p)
        if show == "roster" and "cnap_member" not in codes:
            continue
        if show == "external" and not external:
            continue
        if show == "none" and codes:
            continue
        rows.append(
            {
                "person": p,
                "roles": [r for r in p.current_rels if r.relationship_type.code != "cnap_member"],
                "on_roster": "cnap_member" in codes,
                "external": external,
                "email": next((e.email for e in p.emails.all() if e.is_primary), ""),
            }
        )
    return render(request, "manage/people.html", {"rows": rows, "q": q, "show": show})


@manage_page
def person_new(request):
    form = PersonForm(request.POST or None, initial={"institution": services.KSU_INSTITUTION})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            person = services.create_person(
                request.user,
                first_name=d["first_name"],
                last_name=d["last_name"],
                email=d["email"],
                institution=d["institution"],
                department=d["department"],
                position_title=d["position_title"],
                notes=d["notes"],
            )
        except services.RelationshipError as exc:
            form.add_error(None, str(exc))
        else:
            if request.POST.get("roster"):
                services.add_to_roster(request.user, person)
            messages.success(request, f"{person} added. Give them CNAP relationships below.")
            return redirect("manage:person", person.pk)
    return render(request, "manage/person_new.html", {"form": form})


@admin_view
def person(request, pk):
    p = get_object_or_404(Person, pk=pk)
    rels = p.relationships.select_related("relationship_type", "project", "core").order_by(
        "effective_to", "-effective_from"
    )
    current = [r for r in rels if r.effective_to is None or r.effective_to >= timezone.localdate()]
    past = [r for r in rels if r not in current]
    rel_form = RelationshipForm(initial={"start": timezone.localdate()})
    handoff_rel = None
    if request.GET.get("handoff"):
        handoff_rel = get_object_or_404(PersonRelationship, pk=request.GET["handoff"], person=p)
    ctx = {
        "p": p,
        "current": current,
        "past": past,
        "emails": p.emails.order_by("-is_primary", "email"),
        "rel_form": rel_form,
        "email_form": EmailForm(),
        "edit_form": PersonEditForm(instance=p),
        "handoff_rel": handoff_rel,
        "handoff_form": HandoffForm(initial={"start": timezone.localdate()}),
        "end_form": EndForm(initial={"end": timezone.localdate()}),
        "external": services.is_external(p),
        "on_roster": services.is_on_roster(p),
        "user_account": getattr(p, "user", None),
        "assignments": p.assignments.select_related(
            "form_definition", "reporting_period", "project", "core"
        ).order_by("-reporting_period__display_order")[:30]
        if access.can_read_identified_surveys(request.user)
        else None,
        "history": AuditLog.objects.filter(entity_type="people.Person", entity_id=p.pk)[:10],
    }
    from .outcomes import person_outcomes

    ctx["outcomes"] = person_outcomes(p)
    from apps.outcomes import rppr

    ctx["efforts"] = p.efforts.order_by("-grant_year")
    ctx["cur_gy"] = rppr.current_year()
    ctx["docs"] = _doc_suggestions(request.user, p)
    return render(request, "manage/person.html", ctx)


def _doc_suggestions(user, p):
    """What their latest SciENcv biosketch and Current and Pending say, for the evaluator to use or ignore."""
    from apps.admin_center.views.outcomes import _identified
    from apps.outcomes import sciencv

    if not _identified(user, "nih_documents"):
        return None
    docs = sciencv.latest_for(p)
    if not docs:
        return None
    bio = docs.get("biosketch", {}).get("info", {})
    cp = docs.get("current_pending", {}).get("info", {})
    orcid = bio.get("orcid") or cp.get("orcid") or ""
    degrees = ", ".join(bio.get("degrees", []))
    from apps.outcomes import rppr

    gy = rppr.current_year()
    sp = (
        sciencv.spans(cp.get("cnap_start"), cp.get("cnap_end"), cp.get("cnap_months"))
        if cp
        else None
    )
    return {
        "spans": sp,
        "gy": gy,
        "estimate": sciencv.budget_year_estimate(sp, gy),
        "estimate_prev": sciencv.budget_year_estimate(sp, gy - 1),
        "bio": docs.get("biosketch"),
        "cp": docs.get("current_pending"),
        "degrees": degrees,
        "degrees_new": bool(degrees) and degrees != p.degrees,
        "orcid": orcid,
        "orcid_new": bool(orcid) and not p.orcid,
        "orcid_differs": bool(orcid and p.orcid and orcid != p.orcid),
        "bio_msg": sciencv.message("biosketch", bio) if bio else "",
        "cp_msg": sciencv.message("current_pending", cp) if cp else "",
    }


@manage_action
def person_apply_docs(request, pk):
    """Copy degrees and/or an ORCID iD read from their SciENcv PDFs onto the person (the evaluator chose to)."""
    from apps.people.services import normalize_orcid

    p = get_object_or_404(Person, pk=pk)
    fields = {}
    if request.POST.get("degrees"):
        fields["degrees"] = request.POST["degrees"][:100]
    if request.POST.get("orcid"):
        try:
            fields["orcid"] = normalize_orcid(request.POST["orcid"])
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("manage:person", pk)
    if fields:
        services.update_person(request.user, p, **fields)
        messages.success(request, "Saved from their NIH documents.")
    return redirect("manage:person", pk)


@manage_action
def person_effort(request, pk):
    p = get_object_or_404(Person, pk=pk)
    try:
        gy = int(request.POST.get("grant_year", ""))
        services.set_effort(
            request.user,
            p,
            gy,
            request.POST.get("calendar_months", ""),
            academic=request.POST.get("academic_months", ""),
            summer=request.POST.get("summer_months", ""),
        )
    except ValueError as exc:
        messages.error(request, str(exc) if "month" in str(exc) else "Choose a budget year.")
    else:
        messages.success(request, f"Months saved for Year {gy}.")
    return redirect("manage:person", pk)


@manage_action
def person_edit(request, pk):
    p = get_object_or_404(Person, pk=pk)
    form = PersonEditForm(request.POST, instance=Person.objects.get(pk=pk))
    if form.is_valid():
        services.update_person(request.user, p, **form.cleaned_data)
        messages.success(request, "Saved.")
    else:
        messages.error(request, " ".join(e for errs in form.errors.values() for e in errs))
    return redirect("manage:person", pk)


@manage_action
def person_email_add(request, pk):
    p = get_object_or_404(Person, pk=pk)
    form = EmailForm(request.POST)
    if form.is_valid():
        try:
            services.add_email(
                request.user,
                p,
                form.cleaned_data["email"],
                make_primary=form.cleaned_data["make_primary"],
            )
            messages.success(request, "E-mail added.")
        except services.RelationshipError as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, "Enter a valid e-mail address.")
    return redirect("manage:person", pk)


@manage_action
def person_email_remove(request, pk, email_pk):
    p = get_object_or_404(Person, pk=pk)
    row = get_object_or_404(PersonEmail, pk=email_pk, person=p)
    services.remove_email(request.user, p, row)
    messages.success(request, f"Removed {row.email}.")
    return redirect("manage:person", pk)


@manage_action
def person_email_primary(request, pk, email_pk):
    p = get_object_or_404(Person, pk=pk)
    row = get_object_or_404(PersonEmail, pk=email_pk, person=p)
    p.emails.filter(is_primary=True).update(is_primary=False)
    row.is_primary = True
    row.save(update_fields=["is_primary", "updated_at"])
    record_event(request.user, AuditLog.Action.UPDATE, p, new={"primary_email": row.email})
    messages.success(request, f"{row.email} is now the main address.")
    return redirect("manage:person", pk)


@manage_action
def relationship_add(request, pk):
    p = get_object_or_404(Person, pk=pk)
    form = RelationshipForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Choose a relationship and a start date.")
        return redirect("manage:person", pk)
    d = form.cleaned_data
    try:
        rel = services.add_relationship(
            request.user,
            p,
            d["relationship_type"],
            project=d.get("project"),
            core=d.get("core"),
            start=d["start"],
        )
        messages.success(request, f"Added {rel.relationship_type.name}.")
        from .. import quality

        if quality.director_and_leader(max(d["start"], timezone.localdate()), person=p).exists():
            messages.warning(
                request,
                f"{p} is now both a core director and a project leader (RPL or PPL). "
                "A core director normally isn’t also an RPL or PPL. Check that this is right.",
            )
    except services.RelationshipError as exc:
        messages.error(request, str(exc))
    return redirect("manage:person", pk)


@manage_action
def relationship_end(request, pk, rel_pk):
    rel = get_object_or_404(PersonRelationship, pk=rel_pk, person_id=pk)
    form = EndForm(request.POST)
    end = form.cleaned_data["end"] if form.is_valid() else None
    try:
        services.end_relationship(request.user, rel, end=end)
        messages.success(request, f"Ended {rel.relationship_type.name}. The record is kept.")
    except services.RelationshipError as exc:
        messages.error(request, str(exc))
    return redirect("manage:person", pk)


@manage_action
def relationship_handoff(request, pk, rel_pk):
    rel = get_object_or_404(PersonRelationship, pk=rel_pk, person_id=pk)
    form = HandoffForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Choose the new holder and the date they start.")
        return redirect("manage:person", pk)
    try:
        new = services.hand_off(
            request.user, rel, form.cleaned_data["new_person"], start=form.cleaned_data["start"]
        )
        messages.success(request, f"Handed off to {new.person}.")
    except services.RelationshipError as exc:
        messages.error(request, str(exc))
    return redirect("manage:person", pk)


@manage_action
def person_roster(request, pk):
    p = get_object_or_404(Person, pk=pk)
    try:
        if request.POST.get("action") == "remove":
            services.remove_from_roster(request.user, p)
            messages.success(request, f"{p} is no longer on the CNAP roster.")
        else:
            services.add_to_roster(request.user, p)
            messages.success(request, f"{p} is now on the CNAP roster.")
    except services.RelationshipError as exc:
        messages.error(request, str(exc))
    nxt = request.POST.get("next", "")
    if nxt.startswith("/manage/"):
        return redirect(nxt)
    return redirect("manage:person", pk)


# ---------------------------------------------------------------- projects and cores


@admin_view
def projects(request):
    today = timezone.localdate()
    current = Q(relationships__effective_to__isnull=True) | Q(
        relationships__effective_to__gte=today
    )
    projs = (
        Project.objects.active()
        .annotate(people_n=Count("relationships__person", filter=current, distinct=True))
        .order_by("-is_active", "kind", "title")
    )
    rows = []
    for pr in projs:
        rels = (
            pr.relationships.filter(Q(effective_to__isnull=True) | Q(effective_to__gte=today))
            .select_related("person", "relationship_type")
            .order_by("relationship_type__sort_order")
        )
        rows.append(
            {
                "project": pr,
                "leaders": [
                    r
                    for r in rels
                    if r.relationship_type.code in ("project_leader", "pilot_awardee")
                ],
                "mentors": [
                    r
                    for r in rels
                    if r.relationship_type.code in ("primary_mentor", "pilot_mentor")
                ],
                "others": [
                    r
                    for r in rels
                    if r.relationship_type.code
                    not in ("project_leader", "pilot_awardee", "primary_mentor", "pilot_mentor")
                ],
            }
        )
    cores = []
    for c in Core.objects.active():
        rels = (
            c.relationships.filter(Q(effective_to__isnull=True) | Q(effective_to__gte=today))
            .select_related("person", "relationship_type")
            .order_by("relationship_type__sort_order", "person__last_name")
        )
        cores.append(
            {
                "core": c,
                "directors": [r for r in rels if r.relationship_type.code == "core_director"],
                "staff": [r for r in rels if r.relationship_type.code == "core_staff"],
                "users": [r for r in rels if r.relationship_type.code == "core_user"],
            }
        )
    return render(request, "manage/projects.html", {"rows": rows, "cores": cores})


@manage_action
def core_rrid(request, pk):
    """Set a core's RRID (MW 2026-10-28). Users are asked whether their paper cited it."""
    core = get_object_or_404(Core, pk=pk)
    try:
        rrid = services.normalize_rrid(request.POST.get("rrid", ""))
    except ValueError as exc:
        messages.error(request, f"{core.name}: {exc}")
        return redirect(reverse("manage:projects") + "#cores")
    clash = Core.objects.exclude(pk=core.pk).filter(rrid=rrid).first() if rrid else None
    if clash:
        messages.error(request, f"{rrid} is already saved for {clash.name}. Each core has its own RRID.")
        return redirect(reverse("manage:projects") + "#cores")
    old = core.rrid
    if rrid != old:
        core.rrid = rrid
        core.save(update_fields=["rrid", "updated_at"])
        record_event(request.user, AuditLog.Action.UPDATE, core, old={"rrid": old}, new={"rrid": rrid})
    messages.success(
        request,
        f"{core.name}: RRID saved as {rrid}. People who add a paper that used this core will now be asked whether they cited it."
        if rrid
        else f"{core.name}: RRID removed. The question about it is hidden.",
    )
    return redirect(reverse("manage:projects") + "#cores")


@manage_page
def project_new(request):
    form = ProjectForm(request.POST or None, initial={"is_active": True})
    if request.method == "POST" and form.is_valid():
        pr = form.save()
        record_event(request.user, AuditLog.Action.CREATE, pr)
        messages.success(
            request, f"Added {pr.title}. Add its leader and mentor from their people pages."
        )
        return redirect("manage:project", pr.pk)
    return render(request, "manage/project_form.html", {"form": form, "new": True})


@admin_view
def project(request, pk):
    pr = get_object_or_404(Project, pk=pk)
    if request.method == "POST":
        if not access.can_manage(request.user):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied
        form = ProjectForm(request.POST, instance=pr)
        if form.is_valid():
            old_kind = Project.objects.get(pk=pk).kind
            if form.cleaned_data["kind"] != old_kind and pr.relationships.exists():
                form.add_error(
                    "kind", "This project already has people attached; its type can’t change."
                )
            else:
                form.save()
                record_event(
                    request.user,
                    AuditLog.Action.UPDATE,
                    pr,
                    new=form.cleaned_data
                    | {
                        "start_date": str(form.cleaned_data["start_date"]),
                        "end_date": str(form.cleaned_data["end_date"]),
                    },
                )
                messages.success(request, "Saved.")
                return redirect("manage:project", pk)
    else:
        form = ProjectForm(instance=pr)
    rels = pr.relationships.select_related("person", "relationship_type").order_by(
        "effective_to", "relationship_type__sort_order"
    )
    return render(request, "manage/project_form.html", {"form": form, "project": pr, "rels": rels})


@manage_action
def person_account(request, pk):
    """Turn a person's sign-in off or back on. Records are kept; open sessions end on their next page."""
    p = get_object_or_404(Person, pk=pk)
    user = getattr(p, "user", None)
    if user is None:
        messages.error(
            request,
            f"{p} has never signed in, so there's no account to turn off. To stop them, untick “Active” under "
            "Edit details: an inactive person can't use any sign-in link, including ones already sent.",
        )
    elif user == request.user:
        messages.error(request, "You can’t turn off your own sign-in.")
    else:
        enable = request.POST.get("enable") == "1"
        user.is_enabled = enable
        user.save(update_fields=["is_enabled"])
        record_event(request.user, AuditLog.Action.UPDATE, user, new={"is_enabled": enable})
        messages.success(request, f"Sign-in turned {'back on' if enable else 'off'} for {p}.")
    return redirect("manage:person", pk)
