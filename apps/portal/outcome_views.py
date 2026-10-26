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

# MW's words (decisions.md 2026-10-26), shown after a proposal is marked Not funded.
NOT_FUNDED_NOTE = (
    "Thank you for the update. Submitting a proposal is a real accomplishment and something that should always be "
    "celebrated! A not-funded decision is part of every researcher’s journey toward funding. Your reviewers’ feedback "
    "is valuable for the next round, and we’re here to help you think through its application. We are very proud of "
    "you and excited for your next steps!"
)

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


def entry_open(view):
    """Adding or changing outcomes is closed for a few days after a period closes (decisions.md 2026-10-26)."""
    from functools import wraps

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        ok, reopens = os.entry_window()
        if not ok:
            messages.info(
                request,
                f"Publications, presentations and grants open again on {reopens:%A, %B %-d}, "
                "once the Center has finished this period’s report.",
            )
            return redirect("portal:outcomes")
        return view(request, *args, **kwargs)

    return wrapper


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
            "presentations": os.presentations_of(owner),
            "window": os.entry_window(),
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
@entry_open
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
    from apps.outcomes.models import Presentation

    model = {"pub": Publication, "grant": GrantSubmission, "presentation": Presentation}[kind]
    obj = get_object_or_404(model, pk=pk)
    people = [x.person for x in obj.people.all()]
    if not any(os.can_act_for(request.user, p) for p in people):
        raise PermissionDenied
    return obj, people[0] if people else request.user.person


@login_required
@entry_open
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
    if request.method == "POST" and "lookup" in request.POST and kind == "pub":
        # "Fill in from PubMed": show the values for checking; nothing is saved yet.
        from apps.outcomes import pubmed

        data = request.POST.copy()
        try:
            found = pubmed.lookup(data.get("pubmed_url", ""))
        except pubmed.LookupError_ as exc:
            messages.warning(request, str(exc))
        else:
            for f in ("title", "journal"):
                if found.get(f):
                    data[f] = found[f]
            if found.get("authors"):
                data["author_display_text"] = found["authors"]
            if found.get("publication_date"):
                data["publication_date"] = found["publication_date"].isoformat()
            if found.get("url"):
                data["pubmed_url"] = found["url"]
            if found.get("cnap_in_grant_index") is not None and not data.get("cnap_in_grant_index"):
                data["cnap_in_grant_index"] = "yes" if found["cnap_in_grant_index"] else "no"
            note = "Filled in from PubMed. Please check the title, journal, date and authors before saving."
            if found.get("cnap_in_grant_index") is not None:
                note += (
                    " CNAP’s grant "
                    + ("is" if found["cnap_in_grant_index"] else "is not")
                    + " listed in PubMed’s grant index for this paper."
                )
            messages.success(request, note)
        typed = {
            k: (data.getlist(k) if k in ("resources", "projects") else data.get(k))
            for k in F.base_fields
        }
        form = F(initial={**initial, **{k: v for k, v in typed.items() if v not in (None, "", [])}})
        affs = found.get("affiliations", []) if "found" in locals() else []
        return render(
            request,
            "portal/outcome_form.html",
            {
                "form": form,
                "kind": kind,
                "owner": owner,
                "stage": to,
                "obj": obj,
                "affiliations": affs,
                "title": f"Mark as {STATUS_WORDS[kind][to].lower()}",
            },
        )
    form = F(request.POST or None, initial=initial)
    if kind == "grant" and to == "awarded":
        from apps.common.enums import GrantRole

        link = obj.people.filter(person=owner).first()
        form.shared_role = bool(link and link.role and link.role != GrantRole.PI)
    if request.method == "POST" and form.is_valid():
        d = dict(form.cleaned_data)
        res = d.pop("resources", None)
        prj = d.pop("projects", None)
        other = d.pop("resources_other_text", None)
        if kind == "pub":
            created = os.update_publication(request.user, obj, to, d, res, prj, other)
        else:
            created = os.update_grant(request.user, obj, to, d, res, prj, other, owner=owner)
        if (
            kind == "pub"
            and to == "published"
            and d.get("has_foreign_authors")
            and d.get("foreign_component_approved") is False
        ):
            messages.warning(
                request,
                "Because NIGMS hasn’t approved the foreign component, NIH rules say this paper can’t be listed in "
                "CNAP’s progress report and shouldn’t cite P20GM113109. The CNAP evaluator will be in touch about it.",
            )
        if kind == "grant" and to == "not_funded":
            messages.add_message(request, messages.INFO, NOT_FUNDED_NOTE, extra_tags="encourage")
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
@entry_open
def confirm(request, kind, pk):
    obj, owner = _obj(kind, pk, request)
    os.confirm(request.user, obj)
    return redirect(_url("portal:outcomes", owner))


@login_required
@require_POST
@entry_open
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


@login_required
@entry_open
def presentation(request, pk=None):
    from apps.outcomes.models import Presentation

    from .outcome_forms import PresentationForm

    if pk:
        obj, owner = _obj("presentation", pk, request)
    else:
        obj, (owner, _) = None, _owner(request)
    initial = {"projects": os.awardee_projects(owner)}
    if obj:
        initial = {f: getattr(obj, f) for f in PresentationForm.base_fields if hasattr(obj, f)}
        initial["cnap_cited"] = (
            "" if obj.cnap_cited is None else ("yes" if obj.cnap_cited else "no")
        )
        initial["resources"] = [x.resource for x in obj.resource_links.all()]
        initial["projects"] = [x.project for x in obj.project_links.all()]
    form = PresentationForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        d = dict(form.cleaned_data)
        res, prj, other = d.pop("resources"), d.pop("projects"), d.pop("resources_other_text")
        os.save_presentation(request.user, owner, d, res, prj, other, obj=obj)
        messages.success(request, "Presentation saved.")
        if request.POST.get("another"):
            return redirect(_url("portal:presentation_new", owner))
        return redirect(_url("portal:outcomes", owner))
    _ = Presentation
    return render(
        request,
        "portal/outcome_form.html",
        {
            "form": form,
            "kind": "presentation",
            "owner": owner,
            "stage": "",
            "obj": obj,
            "title": "Edit presentation" if obj else "Add a presentation",
        },
    )


def task_item(person, period):
    """The check-in shown on My tasks, or None for people who don't keep outcomes."""
    owners = os.owners_for(person)
    if not owners or not period:
        return None
    items = []
    for o in owners:
        # The check-in goes to RPPR roles and core users, and to anyone with papers or proposals to review.
        if (
            o.pk == person.pk
            and not os.is_prompted(o)
            and not (os.pubs_of(o).exists() or os.grants_of(o).exists())
        ):
            continue
        st = os.state(o, period)
        items.append(
            {"owner": o, "todo": st["todo"], "done": st["done"], "self": o.pk == person.pk}
        )
    if not items:
        return None
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
