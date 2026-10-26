"""My publications and grants: self-entry following MW's Publication flow and Grant flow."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.common.enums import GrantStatus, PeriodStatus, PublicationStatus
from apps.outcomes import services as os
from apps.outcomes.models import GrantSubmission, OutcomeDelegate, Publication
from apps.people.models import Person
from apps.reporting.models import ReportingPeriod

from .outcome_forms import GRANT_FORMS, NEXT, PUB_FORMS

STATUS_WORDS = {
    "pub": {
        "planned": "Planned",
        "submitted": "Submitted",
        "published": "Published",
        "declined": "Declined",
    },
    "grant": {
        "planned": "Planned",
        "submitted": "Submitted / pending",
        "awarded": "Awarded",
        "not_funded": "Not funded",
    },
}


def current_period():
    return (
        ReportingPeriod.objects.filter(status=PeriodStatus.OPEN).order_by("-display_order").first()
    )


def _owner(request):
    me = request.user.person
    owners = os.owners_for(me)
    pk = request.GET.get("for") or request.POST.get("for")
    if pk:
        owner = get_object_or_404(Person, pk=pk)
        if not os.can_act_for(request.user, owner):
            raise PermissionDenied("You can’t enter publications or grants for this person.")
        return owner, owners
    if not owners:
        raise PermissionDenied(
            "Publications and grants are kept by project leaders and the people they choose."
        )
    return owners[0], owners


def _url(name, owner, *args, **q):
    u = reverse(name, args=args)
    q = {"for": owner.pk, **q}
    return u + "?" + "&".join(f"{k}={v}" for k, v in q.items() if v not in (None, ""))


@login_required
def home(request):
    owner, owners = _owner(request)
    period = current_period()
    st = os.state(owner, period)
    delegates = OutcomeDelegate.objects.filter(owner=owner, ended_at__isnull=True).select_related(
        "delegate"
    )
    return render(
        request,
        "portal/outcomes.html",
        {
            "owner": owner,
            "owners": owners,
            "period": period,
            "st": st,
            "delegates": delegates,
            "acting_for_other": owner.pk != request.user.person.pk,
            "words": STATUS_WORDS,
            "next": NEXT,
            "review_pub": {p.pk for p in st["review_pubs"]},
            "review_grant": {g.pk for g in st["review_grants"]},
            "roster": Person.objects.filter(archived_at__isnull=True, is_active=True).order_by(
                "last_name", "first_name"
            ),
        },
    )


def _initial_resources(obj, actual):
    res = os.resources_of(obj, anticipated=False) if actual else []
    return res or os.resources_of(obj, anticipated=True) or os.resources_of(obj, anticipated=False)


@login_required
def new(request, kind):
    owner, _ = _owner(request)
    F = PUB_FORMS["planned"] if kind == "pub" else GRANT_FORMS["planned"]
    form = F(request.POST or None, initial={"projects": os.awardee_projects(owner)})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        res, prj, other = d.pop("resources"), d.pop("projects"), d.pop("resources_other_text")
        if kind == "pub":
            os.create_publication(request.user, owner, d, res, prj, other)
            messages.success(request, "Planned publication saved.")
        else:
            os.create_grant(request.user, owner, d, res, prj, other)
            messages.success(request, "Planned grant proposal saved.")
        period = current_period()
        if period:
            os.answer_plans(
                request.user, owner, period, "pubs" if kind == "pub" else "grants", True
            )
        if request.POST.get("another"):
            return redirect(_url("portal:outcome_new", owner, kind))
        return redirect(_url("portal:outcomes", owner))
    return render(
        request,
        "portal/outcome_form.html",
        {
            "form": form,
            "kind": kind,
            "owner": owner,
            "stage": "planned",
            "obj": None,
            "title": "Add a planned publication"
            if kind == "pub"
            else "Add a planned grant proposal",
        },
    )


def _obj(kind, pk, request):
    obj = get_object_or_404(Publication if kind == "pub" else GrantSubmission, pk=pk)
    people = [x.person for x in obj.people.all()]
    if not any(os.can_act_for(request.user, p) for p in people):
        raise PermissionDenied
    return obj, people[0] if people else request.user.person


@login_required
def update(request, kind, pk):
    obj, owner = _obj(kind, pk, request)
    to = request.GET.get("to") or request.POST.get("to")
    allowed = NEXT[kind].get(obj.status, [])
    if to not in allowed + [obj.status]:
        return render(
            request,
            "portal/outcome_choose.html",
            {
                "obj": obj,
                "kind": kind,
                "owner": owner,
                "choices": [(s, STATUS_WORDS[kind][s]) for s in allowed],
                "words": STATUS_WORDS,
            },
        )
    forms_ = PUB_FORMS if kind == "pub" else GRANT_FORMS
    F = forms_[to]
    initial = {f: getattr(obj, f, None) for f in F.base_fields if hasattr(obj, f)}
    for f in (
        "cnap_cited",
        "cnap_in_grant_index",
        "has_foreign_authors",
        "cnap_acknowledged",
        "cnap_credited_in_publications",
        "has_foreign_component",
        "discussed_with_program_officer",
        "feedback_shared_with_cnap",
        "plans_to_resubmit",
        "resubmission_intent",
    ):
        if f in initial:
            v = initial[f]
            initial[f] = "" if v is None else ("yes" if v else "no")
    if "resources" in F.base_fields:
        initial["resources"] = _initial_resources(obj, actual=to != "planned")
        initial["projects"] = [x.project for x in obj.project_links.all()]
    if kind == "grant" and "role" in F.base_fields:
        link = obj.people.filter(person=owner).first()
        initial["role"] = link.role if link else None
    form = F(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = dict(form.cleaned_data)
        res = d.pop("resources", None)
        prj = d.pop("projects", None)
        other = d.pop("resources_other_text", None)
        if kind == "pub":
            created = os.update_publication(request.user, obj, to, d, res, prj, other)
        else:
            created = os.update_grant(request.user, obj, to, d, res, prj, other, owner=owner)
        if created:
            label = "publication" if kind == "pub" else f"proposal ({created.version_label})"
            messages.success(
                request,
                f"Saved. A new planned {label} was created from it; check its details below.",
            )
            return redirect(_url("portal:outcome_update", owner, kind, created.pk, to="planned"))
        messages.success(request, "Saved.")
        return redirect(_url("portal:outcomes", owner))
    return render(
        request,
        "portal/outcome_form.html",
        {
            "form": form,
            "kind": kind,
            "owner": owner,
            "stage": to,
            "obj": obj,
            "title": f"{'Edit planned details' if to == obj.status == 'planned' else 'Mark as ' + STATUS_WORDS[kind][to].lower()}",
        },
    )


@login_required
@require_POST
def confirm(request, kind, pk):
    obj, owner = _obj(kind, pk, request)
    os.confirm(request.user, obj)
    return redirect(_url("portal:outcomes", owner))


@login_required
@require_POST
def plans(request, kind):
    owner, _ = _owner(request)
    period = current_period()
    yes = request.POST.get("answer") == "yes"
    if period:
        os.answer_plans(request.user, owner, period, kind, yes)
    if yes:
        return redirect(_url("portal:outcome_new", owner, "pub" if kind == "pubs" else "grant"))
    return redirect(_url("portal:outcomes", owner))


@login_required
@require_POST
def delegate_add(request):
    owner, _ = _owner(request)
    if owner.pk != request.user.person.pk:
        raise PermissionDenied("Only the faculty member can choose who enters for them.")
    who = get_object_or_404(Person, pk=request.POST.get("person"))
    try:
        os.add_delegate(request.user, owner, who)
        messages.success(request, f"{who} can now enter publications and grants for you.")
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect(_url("portal:outcomes", owner))


@login_required
@require_POST
def delegate_end(request, pk):
    d = get_object_or_404(OutcomeDelegate, pk=pk, owner=request.user.person)
    os.end_delegate(request.user, d)
    messages.success(request, f"{d.delegate} can no longer enter for you.")
    return redirect(_url("portal:outcomes", d.owner))


def task_item(person, period):
    """The check-in shown on My tasks, or None for people who don't keep outcomes."""
    owners = os.owners_for(person)
    if not owners or not period:
        return None
    items = []
    for o in owners:
        st = os.state(o, period)
        items.append(
            {"owner": o, "todo": st["todo"], "done": st["done"], "self": o.pk == person.pk}
        )
    todo = sum(i["todo"] for i in items)
    return {"items": items, "todo": todo, "done": todo == 0, "minutes": max(2, min(10, 2 * todo))}


__all__ = [
    "home",
    "new",
    "update",
    "confirm",
    "plans",
    "delegate_add",
    "delegate_end",
    "task_item",
    "GrantStatus",
    "PublicationStatus",
]
