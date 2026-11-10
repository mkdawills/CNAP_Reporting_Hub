"""My publications and grants: self-entry following MW's Publication flow and Grant flow."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.common import prototype
from apps.common.enums import GrantStatus, PeriodStatus, PublicationStatus
from apps.outcomes import journey
from apps.outcomes import services as os
from apps.outcomes.models import GrantSubmission, OutcomeDelegate, Publication
from apps.people.models import Person
from apps.reporting.models import ReportingPeriod

from .outcome_forms import GRANT_FORMS, NEXT, PUB_FORMS

# MW's words (decisions.md 2026-10-26), shown after a proposal is marked Not funded.
NOT_FUNDED_NOTE = (
    "Thank you for the update. Submitting a proposal is a major accomplishment and something that should always be "
    "celebrated! A not-funded decision is part of every researcher’s journey toward funding. Your reviewers’ feedback "
    "is valuable for the next round, and we’re here to help you think through its application."
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
                f"Publications, talks, and grants open again on {reopens:%A, %B %-d}, "
                "once the Center has finished this reporting session’s report.",
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
            if not journey.enabled():
                raise PermissionDenied("You can’t enter publications or grants for this person.")
            # Prototype screen 5: CNAP people involved in someone else's item come back to their own
            # page after an update. They still see only items they are linked to (MW 2026-11-05).
            pk = None
        else:
            return owner, owners
    if pk:
        return owner, owners
    if not owners:
        raise PermissionDenied(
            "Publications, talks, and grants are kept by project leaders and the people they choose."
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
    tpl = prototype.template(request, "outcomes", "portal/outcomes.html")
    from apps.outcomes import asof as asof_mod

    asof = asof_mod.parse(request.GET.get("asof"))
    if asof and tpl != "portal/outcomes.html":
        return _as_of_page(request, owner, owners, asof)
    extra = {}
    if tpl != "portal/outcomes.html":
        extra = _journey_cards(st)
    return render(
        request,
        tpl,
        {
            **extra,
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
            "asof_picks": asof_mod.quick_picks(),
            "review_pub": {p.pk for p in st["review_pubs"]},
            "review_grant": {g.pk for g in st["review_grants"]},
            "roster": Person.objects.filter(archived_at__isnull=True, is_active=True).order_by(
                "last_name", "first_name"
            ),
        },
    )


def _as_of_page(request, owner, owners, day):
    """Where each of the person's papers, proposals, and talks stood at the end of `day` (MW 2026-11-05).
    Read-only. Built from the status history, dated by the person where a date was given."""
    from apps.outcomes import asof as asof_mod

    def rows(kind, objs, title, sub):
        out = []
        for o in objs:
            st = asof_mod.status_on(kind, o, day)
            if st:
                out.append({"title": title(o), "sub": sub(o), "then": STATUS_WORDS[kind].get(st, st), "now": STATUS_WORDS[kind].get(o.status, o.status), "changed": st != o.status, "anchor": f"item-{kind}-{o.pk}"})
        return out

    pubs = rows("pub", os.pubs_of(owner).prefetch_related("status_history"), lambda o: o.title, lambda o: o.journal)
    grants = rows("grant", os.grants_of(owner).prefetch_related("status_history"), lambda o: o.project_title, lambda o: " ".join(x for x in (o.funding_agency, o.mechanism) if x))
    talks = [{"title": t.title, "sub": " · ".join(x for x in (t.get_presentation_type_display(), t.event) if x), "day": t.presented_on, "anchor": f"item-talk-{t.pk}"} for t in os.presentations_of(owner) if asof_mod.talk_on(t, day)]
    return render(
        request,
        "proto/outcomes_asof.html",
        {"owner": owner, "owners": owners, "day": day, "pubs": pubs, "grants": grants, "talks": talks,
         "picks": asof_mod.quick_picks(), "acting_for_other": owner.pk != request.user.person.pk},
    )


def _journey_cards(st):
    """Prototype screen 5: one card per paper or proposal, its latest attempt only; earlier attempts
    show on the card's track. Items still planned or submitted come first, those to review on top."""
    review = {("pub", p.pk) for p in st["review_pubs"]} | {("grant", g.pk) for g in st["review_grants"]}
    later_pubs = set(
        Publication.objects.filter(resubmission_of__in=st["pubs"], archived_at__isnull=True).values_list(
            "resubmission_of_id", flat=True
        )
    )
    latest = {}
    for g in st["grants"]:
        if g.grant_family_id not in latest or g.version_no > latest[g.grant_family_id].version_no:
            latest[g.grant_family_id] = g
    items = [("pub", p) for p in st["pubs"] if p.pk not in later_pubs] + [("grant", g) for g in latest.values()]
    cards = [journey.card(k, o, review=(k, o.pk) in review) for k, o in items]
    open_ = sorted((c for c in cards if c["open"]), key=lambda c: (not c["review"], c["kind"], c["title"].lower()))
    return {
        "open_cards": open_,
        "done_pubs": [c for c in cards if not c["open"] and c["kind"] == "pub"],
        "done_grants": [c for c in cards if not c["open"] and c["kind"] == "grant"],
        "role_choices": journey.ROLE_CHOICES,
    }


def _start_resources(owner):
    """A new record starts with the person's own CNAP project ticked, and the matching resource with it."""
    from apps.people.models import Resource

    prj = list(os.awardee_projects(owner))
    codes = {"research_project" if p.kind == "primary" else "pilot_project" for p in prj}
    return {"projects": prj, "resources": list(Resource.objects.filter(code__in=codes))}


def _own(F, owner):
    """The person's own CNAP projects, marked "(your project)" on forms that list projects."""
    from .outcome_forms import _Resources

    return {"own_projects": list(os.awardee_projects(owner))} if issubclass(F, _Resources) else {}


def _initial_resources(obj, actual):
    res = os.resources_of(obj, anticipated=False) if actual else []
    return res or os.resources_of(obj, anticipated=True) or os.resources_of(obj, anticipated=False)


@login_required
@entry_open
def new(request, kind):
    owner, _ = _owner(request)
    F = PUB_FORMS["planned"] if kind == "pub" else GRANT_FORMS["planned"]
    form = F(request.POST or None, initial=_start_resources(owner), **_own(F, owner))
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


def _facts(kind, obj):
    """One line of what's on file, so the person can see whether the details need editing (MW 2026-11-03)."""
    f = []
    if kind == "grant":
        if obj.funding_agency:
            f.append(obj.funding_agency)
        if obj.mechanism:
            f.append(obj.mechanism)
        when = obj.submission_date or obj.anticipated_submission_date
        if when:
            word = "submitted" if obj.submission_date else "planned for"
            f.append(f"{word} {when:%B} {when.day if obj.submission_date or obj.anticipated_day_known else ''} {when:%Y}".replace("  ", " "))
        amt = obj.requested_total or obj.anticipated_total
        if amt:
            f.append(f"${amt:,.0f} requested")
    else:
        if obj.journal:
            f.append(obj.journal)
        if obj.submission_date:
            f.append(f"submitted {obj.submission_date:%B} {obj.submission_date.day}, {obj.submission_date:%Y}")
        elif obj.anticipated_submission_month:
            m = obj.anticipated_submission_month
            f.append(f"planned for {m:%B} {m.day if obj.anticipated_day_known else ''} {m:%Y}".replace("  ", " "))
    return " · ".join(f)


@login_required
@entry_open
def update(request, kind, pk):
    obj, owner = _obj(kind, pk, request)
    if journey.enabled():
        # Prototype screen 5, option A (MW 2026-11-05): the form shows, and a save records, the role
        # of the person filling it in. A co-investigator's update never changes the PI's role.
        owner = journey.acting_person(request.user, obj) or owner
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
                "facts": _facts(kind, obj),
            },
        )
    forms_ = PUB_FORMS if kind == "pub" else GRANT_FORMS
    F = forms_[to]
    initial = {f: getattr(obj, f, None) for f in F.base_fields if hasattr(obj, f)}
    if kind == "grant" and "funding_source" in F.base_fields:
        initial["funding_source_type"] = obj.funding_source_type  # _Funding maps it to the radio
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
    if "anticipated_day" in F.base_fields and getattr(obj, "anticipated_day_known", False):
        when = getattr(obj, F.date_field, None)
        if when:
            initial["anticipated_day"] = when.day
    if "resources" in F.base_fields:
        initial["resources"] = _initial_resources(obj, actual=to != "planned")
        initial["projects"] = [x.project for x in obj.project_links.all()]
    if kind == "pub":  # "did you cite the core's RRID?" answers already given
        for x in obj.resource_links.all():
            if x.rrid_cited:
                initial[f"rrid_{x.resource_id}"] = x.rrid_cited
    if kind == "grant" and "role" in F.base_fields:
        link = obj.people.filter(person=owner).first()
        initial["role"] = link.role if link else None
        initial["role_other"] = link.role_other if link else ""
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
            note = "Filled in from PubMed. Check the title, journal, date, and authors before saving."
            if found.get("cnap_in_grant_index") is not None:
                note += (
                    " CNAP’s grant "
                    + ("is" if found["cnap_in_grant_index"] else "is not")
                    + " listed in PubMed’s grant index for this paper."
                )
            messages.success(request, note)
        typed = {
            k: (data.getlist(k) if k in ("resources", "projects") else data.get(k))
            for k in [*F.base_fields, *(k for k in data if k.startswith("rrid_"))]
        }
        form = F(initial={**initial, **{k: v for k, v in typed.items() if v not in (None, "", [])}}, **_own(F, owner))
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
    form = F(request.POST or None, initial=initial, **_own(F, owner))
    if kind == "grant" and to == "awarded":
        from apps.common.enums import GrantRole

        link = obj.people.filter(person=owner).first()
        form.shared_role = bool(link and link.role and link.role != GrantRole.PI)
    if request.method == "POST" and form.is_valid():
        d = dict(form.cleaned_data)
        res = d.pop("resources", None)
        prj = d.pop("projects", None)
        other = d.pop("resources_other_text", None)
        rrid = None
        if kind == "pub" and hasattr(form, "rrid_fields"):
            from .outcome_forms import rrid_answers

            rrid = rrid_answers(form)
            for name in form.rrid_fields.values():
                d.pop(name, None)
        was = obj.status
        if kind == "pub":
            created = os.update_publication(request.user, obj, to, d, res, prj, other, rrid=rrid)
        else:
            created = os.update_grant(request.user, obj, to, d, res, prj, other, owner=owner)
        if journey.enabled():
            # Prototype screen 5 (MW 2026-11-05): a resubmission keeps everyone involved, and the
            # other people involved hear right away who changed what.
            if created:
                journey.copy_people(kind, obj, created)
            words = journey.WORDS[kind]
            what = (
                f"changed the status from {words[was]} to {words[to]}"
                if to != was
                else "updated the details"
            )
            if created:
                what += " and started the next attempt"
            journey.notify(kind, obj, request.user, what, request=request)
        if (
            kind == "pub"
            and to == "published"
            and d.get("has_foreign_authors")
            and d.get("foreign_component_approved") is False
        ):
            messages.warning(
                request,
                "Because the National Institute of General Medical Sciences (NIGMS) hasn’t approved the foreign component, NIH rules say this paper can’t be listed in "
                "CNAP’s Research Performance Progress Report (RPPR) and shouldn’t cite P20GM113109. The CNAP evaluator will be in touch about it.",
            )
        if kind == "grant" and to == "not_funded":
            messages.add_message(request, messages.INFO, NOT_FUNDED_NOTE, extra_tags="encourage")
        if kind == "grant" and to == "submitted" and obj.status != "submitted":
            messages.add_message(
                request,
                messages.INFO,
                "Congratulations on submitting your proposal! Submitting is a major accomplishment, "
                "and the Center is cheering for you.",
                extra_tags="encourage",
            )
        not_funded = kind == "grant" and to == "not_funded"
        if created:
            label = "publication" if kind == "pub" else f"proposal ({created.version_label})"
            messages.success(
                request,
                f"Your changes are saved. A new planned {label} was created from it. Check its details below.",
            )
            if not_funded:  # MW 2026-11-10: keep the A1 redirect, and point to the funding page
                messages.add_message(
                    request,
                    messages.INFO,
                    "When you’re ready, your Funding opportunities page has options picked for this moment.",
                    extra_tags="funding",
                )
            return redirect(_url("portal:outcome_update", owner, kind, created.pk, to="planned"))
        messages.success(request, "Your changes are saved.")
        if not_funded:  # MW 2026-11-10: go straight to the funding page
            return redirect(f"{reverse('portal:funding')}?from=not_funded&for={owner.pk}")
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
            "title": (
                "Edit the planned details"
                if to == obj.status == "planned"
                else f"Your details ({STATUS_WORDS[kind][to].lower()})"
                if to == obj.status
                else "Mark as " + STATUS_WORDS[kind][to].lower()
            ),
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
    initial = _start_resources(owner)
    if obj:
        initial = {f: getattr(obj, f) for f in PresentationForm.base_fields if hasattr(obj, f)}
        if obj.location and not any((obj.venue, obj.city, obj.state_region, obj.country)):
            initial["venue"] = obj.location  # an older record kept the place on one line
        initial["cnap_cited"] = (
            "" if obj.cnap_cited is None else ("yes" if obj.cnap_cited else "no")
        )
        initial["resources"] = [x.resource for x in obj.resource_links.all()]
        initial["projects"] = [x.project for x in obj.project_links.all()]
    form = PresentationForm(request.POST or None, initial=initial, **_own(PresentationForm, owner))
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
            "title": "Edit a presentation" if obj else "Add a presentation",
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
            {"owner": o, "todo": st["todo"], "n_review": st["n_review"], "n_ask": st["n_ask"], "done": st["done"], "self": o.pk == person.pk}
        )
    if not items:
        return None
    todo = sum(i["todo"] for i in items)
    return {"items": items, "todo": todo, "done": todo == 0, "minutes": max(2, min(10, 2 * todo))}


@login_required
def nudge(request, pk):
    """Answer a monthly check-in about a planned grant proposal (MW 2026-11-03)."""
    from apps.outcomes import nudges as nsvc
    from apps.outcomes.models import GrantNudge

    n = get_object_or_404(
        GrantNudge.objects.select_related("grant", "person"), pk=pk
    )
    if not os.can_act_for(request.user, n.person):
        raise PermissionDenied("This check-in belongs to someone else.")
    grant = n.grant
    role = nsvc.role_of(n.person)
    if request.method == "POST" and grant.status == GrantStatus.PLANNED:
        choice = request.POST.get("choice", "")
        comments = request.POST.get("comments", "").strip()
        valid = {c for c, _ in GrantNudge.Choice.choices}
        if choice not in valid:
            messages.error(request, "Choose one of the five answers.")
        elif choice == GrantNudge.Choice.PIVOT and not comments:
            messages.error(
                request, "Share your new alternative plans in the comments box."
            )
        else:
            from django.utils import timezone

            n.choice = choice
            n.comments = comments
            n.answered_at = timezone.now()
            n.answered_by = request.user
            n.save(update_fields=["choice", "comments", "answered_at", "answered_by"])
            grant.confirmed_at = timezone.now()
            grant.save(update_fields=["confirmed_at", "updated_at"])
            messages.success(request, "Thank you! Your answer has been shared with the CNAP evaluation team.")
            return redirect(f"{reverse('portal:outcome_nudge', args=[n.pk])}?done=1")
    return render(
        request,
        "portal/nudge.html",
        {
            "nudge": n,
            "grant": grant,
            "choices": GrantNudge.Choice.choices,
            "preselect": request.GET.get("choice", n.choice),
            "done": request.GET.get("done") or n.answered_at,
            "still_planned": grant.status == GrantStatus.PLANNED,
            "milestones": nsvc.MILESTONES.get(role, []),
            "role_word": {"research": "Research Project Leader", "pilot": "Pilot Project Leader"}.get(role, ""),
            "supports": nsvc.SUPPORTS,
        },
    )


__all__ = [
    "home",
    "new",
    "update",
    "confirm",
    "plans",
    "delegate_add",
    "delegate_end",
    "task_item",
    "nudge",
    "GrantStatus",
    "PublicationStatus",
]


@login_required
@require_POST
def people(request, kind, pk):
    """Prototype screen 5: add or remove a CNAP person involved in a paper or proposal (MW 2026-11-05).
    Anyone who can update the item can do this; the first person linked always stays."""
    from django.http import Http404

    if not journey.enabled() or kind not in ("pub", "grant"):
        raise Http404
    obj, owner = _obj(kind, pk, request)
    person = get_object_or_404(Person, pk=request.POST.get("person"), archived_at__isnull=True)
    title = obj.title if kind == "pub" else obj.project_title
    if request.POST.get("action") == "remove":
        if journey.remove_person(kind, obj, person):
            messages.success(request, f"{person} is no longer listed on “{title[:60]}.”")
        else:
            messages.warning(request, "The person who entered this item always stays listed.")
    else:
        role = request.POST.get("role", "")
        if journey.add_person(kind, obj, person, role, request.POST.get("role_other", "").strip()):
            label = dict(journey.ROLE_CHOICES).get(role, "Co-author") if kind == "grant" else "a co-author"
            journey.notify(kind, obj, request.user, f"added you as {label}", request=request, only={person.pk})
            messages.success(request, f"{person} can now see and update “{title[:60]}.” We emailed them.")
        else:
            messages.info(request, f"{person} is already listed.")
    return redirect(reverse("portal:outcomes") + f"#item-{kind}-{obj.pk}")
