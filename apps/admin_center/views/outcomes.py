"""
Publications and grants, starting with acknowledgment tracking (decisions.md 2026-10-25).

MW's first need: check whether CNAP was acknowledged. Publications carry `cnap_cited`
(the paper cites CNAP's grant) and `cnap_in_grant_index` (the paper is linked to the
grant in NIH's index); grant submissions carry `cnap_acknowledged`. Each is Yes, No,
or not checked yet (NULL). One outcome can be credited to several projects and cores.
"""

from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts import access
from apps.audit.models import AuditLog, record_event
from apps.common.enums import GrantRole, GrantStatus, PublicationStatus
from apps.outcomes import nihdocs
from apps.outcomes import nudges as _ndg
from apps.outcomes import reminders as _rem
from apps.outcomes.models import (
    GrantFamily,
    GrantNudge,
    GrantStatusHistory,
    GrantSubmission,
    GrantSubmissionPerson,
    GrantSubmissionProject,
    GrantSubmissionResource,
    OutcomeReminder,
    Publication,
    PublicationPerson,
    PublicationProject,
    PublicationResource,
    PublicationStatusHistory,
)
from apps.people.fields import ProjectChoiceField
from apps.people.models import Person, Project, Resource

from ..decorators import admin_view, manage_action, manage_page

ACK_FILTERS = [
    ("all", "All"),
    ("check", "Needs checking"),
    ("no", "Not acknowledged"),
    ("yes", "Acknowledged"),
]


def _ack_q(field, f):
    return {
        "check": Q(**{f"{field}__isnull": True}),
        "no": Q(**{field: False}),
        "yes": Q(**{field: True}),
    }.get(f, Q())


def _rrid_missing_q():
    """Published papers that used a core with an RRID but haven't said Yes to citing it."""
    from apps.outcomes.services import rrid_missing_ids

    return Q(pk__in=rrid_missing_ids())


def _rrid_summary(published):
    """How many published papers that used a core with an RRID cited it (MW 2026-10-28)."""
    from apps.outcomes.models import PublicationResource

    links = PublicationResource.objects.filter(
        publication__in=published, resource__core__isnull=False
    ).exclude(resource__core__rrid="")
    used = links.values("publication").distinct().count()
    if not used:
        return None
    missing = published.filter(_rrid_missing_q()).distinct().count()
    return {"used": used, "cited": used - missing, "missing": missing}


def _share(qs, field):
    """(acknowledged, checked, total) for a queryset."""
    total = qs.count()
    yes = qs.filter(**{field: True}).count()
    checked = qs.exclude(**{f"{field}__isnull": True}).count()
    return {
        "yes": yes,
        "checked": checked,
        "total": total,
        "unchecked": total - checked,
        "pct": round(100 * yes / checked) if checked else None,
    }


@admin_view
def outcomes(request):
    tab = request.GET.get("tab", "pubs")
    f = request.GET.get("ack", "all")
    pubs = Publication.objects.filter(archived_at__isnull=True).prefetch_related(
        "people__person", "project_links__project", "resource_links__resource__core"
    )
    grants = (
        GrantSubmission.objects.filter(archived_at__isnull=True)
        .select_related("grant_family")
        .prefetch_related("people__person", "project_links__project", "resource_links__resource")
    )
    published = pubs.filter(status=PublicationStatus.PUBLISHED)
    sent = grants.exclude(status=GrantStatus.PLANNED)
    summary = {"pubs": _share(published, "cnap_cited"), "grants": _share(sent, "cnap_acknowledged")}
    if tab == "talks":
        from apps.outcomes.models import Presentation

        rows = Presentation.objects.filter(archived_at__isnull=True).prefetch_related(
            "people__person", "project_links__project", "resource_links__resource"
        )
        rows = rows.filter(_ack_q("cnap_cited", f)).order_by("-presented_on")
    elif tab == "grants":
        rows = sent.filter(_ack_q("cnap_acknowledged", f)) if f != "all" else grants
        rows = rows.order_by("-submission_date", "-updated_at")
    elif f == "rrid":
        rows = (
            published.filter(_rrid_missing_q())
            .distinct()
            .order_by("-publication_date", "-updated_at")
        )
    else:
        rows = published.filter(_ack_q("cnap_cited", f)) if f != "all" else pubs
        rows = rows.order_by("-publication_date", "-updated_at")
    return render(
        request,
        "manage/outcomes.html",
        {
            "rppr": _rppr_ctx(request) if tab == "rppr" else None,
            "sv": _sv_ctx(request) if tab == "sitevisit" else None,
            "reminders_due": _rem.due() if tab == "reminders" else None,
            "nudges_due": _ndg.due() if tab == "reminders" else None,
            "nudge_rows": GrantNudge.objects.select_related("grant", "person").order_by("-sent_at")[
                :30
            ]
            if tab == "reminders"
            else None,
            "nudge_every": settings.GRANT_NUDGE_EVERY_DAYS,
            "reminders_sent": OutcomeReminder.objects.select_related("person")[:20]
            if tab == "reminders"
            else None,
            "stale_days": settings.OUTCOME_STALE_DAYS,
            "remind_every": settings.OUTCOME_REMINDER_EVERY_DAYS,
            "counts": (
                c := counts(year=_int(request.GET.get("year"))) if tab == "counts" else None
            ),
            "counts_year": _int(request.GET.get("year")),
            "counts_tables": [
                ("All CNAP", c["all"]),
                ("By project", c["projects"]),
                ("By core and resource", c["cores"]),
            ]
            if c
            else [],
            "tab": tab,
            "ack": f,
            "filters": ACK_FILTERS,
            "rrid_summary": _rrid_summary(published) if tab == "pubs" else None,
            "rows": rows,
            "summary": summary,
            "can_edit": access.can_manage(request.user),
        },
    )


def grant_year(d):
    """Grant Year N runs June to May: June 2025 - May 2026 is Year 9."""
    if not d:
        return None
    return d.year - 2016 if d.month >= 6 else d.year - 2017


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def counts(year=None):
    """Outcome counts by grant year, overall and by project and by core/resource (for the NIH progress report)."""
    from apps.outcomes.models import Presentation

    pubs = Publication.objects.filter(
        archived_at__isnull=True, status=PublicationStatus.PUBLISHED
    ).prefetch_related("project_links__project", "resource_links__resource")
    talks = Presentation.objects.filter(archived_at__isnull=True).prefetch_related(
        "project_links__project", "resource_links__resource"
    )
    grants = (
        GrantSubmission.objects.filter(archived_at__isnull=True)
        .exclude(status=GrantStatus.PLANNED)
        .prefetch_related("project_links__project", "resource_links__resource")
    )
    metrics = [
        ("pubs", "Papers published"),
        ("rrid", "Papers citing a core RRID"),
        ("talks", "Presentations"),
        ("sub", "Grants submitted"),
        ("won", "Grants awarded"),
        ("dollars", "Awarded dollars"),
    ]
    years = set()
    tally = {}

    def add(groups, metric, year, value=1):
        if year is None:
            return
        years.add(year)
        for g in groups:
            k = (*g, metric, year)
            tally[k] = tally.get(k, 0) + value

    def groups_of(o):
        out = [("all", "All CNAP")]
        out += [("project", x.project.title) for x in o.project_links.all()]
        out += [("core", x.resource.name) for x in o.resource_links.all()]
        return out

    for p in pubs:
        y = grant_year(p.publication_date)
        add(groups_of(p), "pubs", y)
        cited = [x for x in p.resource_links.all() if x.rrid_cited == "yes"]
        if cited:  # MW 2026-10-28: core use the grant citation can't show
            # Count the paper once for the Center and its projects, and under each core it cited,
            # so all three tables share the same columns and line up (MW 2026-11-03).
            add([("all", "All CNAP")], "rrid", y)
            add([("project", x.project.title) for x in p.project_links.all()], "rrid", y)
            for x in cited:
                add([("core", x.resource.name)], "rrid", y)
    for t in talks:
        add(groups_of(t), "talks", grant_year(t.presented_on))
    for g in grants:
        add(groups_of(g), "sub", grant_year(g.submission_date))
        if g.status == GrantStatus.AWARDED:
            y = grant_year(g.award_notice_date or g.submission_date)
            add(groups_of(g), "won", y)
            add(groups_of(g), "dollars", y, float(g.award_total or 0))
    years = sorted(years)

    hue = {m: i for i, (m, _) in enumerate(metrics)}

    shown = [year] if year in years else years  # one year from the dropdown, or every year

    def pivot(kind, skip=()):
        """One row per project or core, one column per measure (MW 2026-11-03: cognitive clarity).
        No year groupings inside a cell: the dropdown narrows the whole page to one year instead."""
        names = sorted({k[1] for k in tally if k[0] == kind})
        cols = [(m, label) for m, label in metrics if m not in skip]
        rows = []
        for n in names:
            cells = []
            for m, _label in cols:
                per = [(y, tally.get((kind, n, m, y), 0)) for y in shown]
                cells.append(
                    {
                        "m": m,
                        "hue": hue[m],
                        "total": sum(v for _, v in per),
                        "dollars": m == "dollars",
                        "per": [(y, v) for y, v in per if v],
                    }
                )
            rows.append({"group": n, "cells": cells})
        col_totals = [
            {
                "total": sum(r["cells"][i]["total"] for r in rows),
                "dollars": m == "dollars",
            }
            for i, (m, label) in enumerate(cols)
        ]
        return {"cols": [label for _, label in cols], "rows": rows, "col_totals": col_totals}

    out = {
        "years": years,
        "all": pivot("all"),
        "projects": pivot("project"),
        "cores": pivot("core"),
    }
    # One small table per core: years across the top, one row per measure (MW 2026-11-03).
    out["per_core"] = []
    for name in sorted({k[1] for k in tally if k[0] == "core"}):
        rows = []
        for m, label in metrics:
            vals = [tally.get(("core", name, m, y), 0) for y in years]
            rows.append(
                {
                    "label": label,
                    "m": m,
                    "hue": hue[m],
                    "dollars": m == "dollars",
                    "vals": vals,
                    "total": sum(vals),
                }
            )
        out["per_core"].append({"name": name, "rows": rows})
    # a cell holding the whole Center total gets the same tint as that total in All CNAP (MW 2026-11-03)
    all_total = {c["m"]: c["total"] for r in out["all"]["rows"] for c in r["cells"]}
    for key in ("projects", "cores"):
        for r in out[key]["rows"]:
            for c in r["cells"]:
                c["match"] = bool(c["total"]) and c["total"] == all_total.get(c["m"])
                if c["match"]:
                    all_total[c["m"] + "_hit"] = True
    # the per-core year-by-year tables keep the same tints where their totals match All CNAP
    for t in out["per_core"]:
        for r in t["rows"]:
            r["match"] = bool(r["total"]) and r["total"] == all_total.get(r["m"])
            if r["match"]:
                all_total[r["m"] + "_hit"] = True
    for r in out["all"]["rows"]:
        for c in r["cells"]:
            c["match"] = bool(all_total.get(c["m"] + "_hit")) and bool(c["total"])
    return out


@manage_action
def set_ack(request, kind, pk):
    value = {"yes": True, "no": False}.get(request.POST.get("value"))
    if kind == "grant":
        obj = get_object_or_404(GrantSubmission, pk=pk)
        old = obj.cnap_acknowledged
        obj.cnap_acknowledged = value
        obj.save(update_fields=["cnap_acknowledged", "updated_at"])
        field = "cnap_acknowledged"
    elif kind == "presentation":
        from apps.outcomes.models import Presentation

        obj = get_object_or_404(Presentation, pk=pk)
        old = obj.cnap_cited
        obj.cnap_cited = value
        obj.save(update_fields=["cnap_cited", "updated_at"])
        field = "cnap_cited"
    else:
        obj = get_object_or_404(Publication, pk=pk)
        old = obj.cnap_cited
        obj.cnap_cited = value
        obj.save(update_fields=["cnap_cited", "updated_at"])
        field = "cnap_cited"
    record_event(request.user, AuditLog.Action.UPDATE, obj, old={field: old}, new={field: value})
    return redirect(request.POST.get("next") or "manage:outcomes")


# --------------------------------------------------------------------------- add / edit


class _Credit(forms.Form):
    people = forms.ModelMultipleChoiceField(
        queryset=Person.objects.filter(archived_at__isnull=True).order_by(
            "last_name", "first_name"
        ),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="CNAP members on this publication",
    )
    projects = ProjectChoiceField(
        queryset=Project.objects.filter(archived_at__isnull=True)
        .prefetch_related("relationships__person", "relationships__relationship_type")
        .order_by("title"),
        required=False,
        label="Credit to projects",
        help_text="Choose every project that supported it.",
    )
    resources = forms.ModelMultipleChoiceField(
        queryset=Resource.objects.filter(is_active=True),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Credit to cores and other CNAP resources",
        help_text="Choose every core or resource that supported it.",
    )


YESNO = [("", "Not checked yet"), ("yes", "Yes"), ("no", "No")]


def _tri(v):
    return {"yes": True, "no": False}.get(v)


def _tri_initial(v):
    return "" if v is None else ("yes" if v else "no")


class PublicationForm(forms.ModelForm):
    cnap_cited_tri = forms.ChoiceField(
        choices=YESNO, required=False, label="Does the paper acknowledge CNAP’s grant?"
    )
    cnap_index_tri = forms.ChoiceField(
        choices=YESNO,
        required=False,
        label="Is it linked to CNAP’s grant in NIH’s records (PubMed / My Bibliography)?",
    )

    class Meta:
        model = Publication
        fields = [
            "status",
            "title",
            "publication_type",
            "publication_type_other",
            "substatus",
            "author_display_text",
            "journal",
            "submission_date",
            "publication_date",
            "pubmed_url",
            "comments",
            "has_foreign_authors",
            "foreign_component_approved",
            "has_non_idea_coauthors",
        ]
        widgets = {
            "submission_date": forms.DateInput(attrs={"type": "date"}),
            "publication_date": forms.DateInput(attrs={"type": "date"}),
            "author_display_text": forms.Textarea(attrs={"rows": 2}),
            "comments": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {
            "author_display_text": "Authors",
            "pubmed_url": "PubMed or DOI link",
            "rppr_year": "Reported in the RPPR (C.1), Year",
            "has_foreign_authors": "Foreign authors?",
            "foreign_component_approved": "Foreign component approved by NIGMS?",
            "has_non_idea_coauthors": "Co-authors from non-IDeA states?",
        }
        help_texts = {
            "author_display_text": (
                "List every author, in order, exactly as they appear on the paper. "
                "For example: Okafor A, Brandt H, Moreau C."
            )
        }


class _RoundChoice(forms.ModelChoiceField):
    def label_from_instance(self, g):
        bits = [f"{g.project_title} ({g.version_label})"]
        if g.funding_agency or g.mechanism:
            bits.append(" ".join(x for x in (g.funding_agency, g.mechanism) if x))
        bits.append(g.get_status_display())
        return " \u00b7 ".join(bits)


class GrantForm(forms.ModelForm):
    resubmission_of = _RoundChoice(
        queryset=GrantSubmission.objects.filter(archived_at__isnull=True)
        .exclude(status=GrantStatus.PLANNED)
        .order_by("project_title", "version_no"),
        required=False,
        empty_label="No, this is a new proposal",
        label="Is this a resubmission of an earlier proposal?",
        help_text=(
            "For a first submission, leave “No, this is a new proposal.” "
            "For a resubmission, choose the earlier submission from the list. "
            "The Hub then files this record as that proposal’s next round (A1, A2, and so on), "
            "and offers to copy the earlier round’s details into this form."
        ),
    )
    pi = forms.ModelChoiceField(
        queryset=Person.objects.filter(archived_at__isnull=True).order_by("last_name"),
        required=False,
        label="PI",
    )
    ack_tri = forms.ChoiceField(
        choices=YESNO, required=False, label="Does the proposal acknowledge CNAP?"
    )

    class Meta:
        model = GrantSubmission
        fields = [
            "status",
            "project_title",
            "funding_agency",
            "mechanism",
            "submission_date",
            "requested_total",
            "award_notice_date",
            "award_total",
            "grant_number",
            "decision_comments",
            "funding_source_type",
            "cnap_portion",
        ]
        widgets = {
            "submission_date": forms.DateInput(attrs={"type": "date"}),
            "award_notice_date": forms.DateInput(attrs={"type": "date"}),
            "decision_comments": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {
            "project_title": "Proposal title",
            "decision_comments": "Notes",
            "cnap_portion": "CNAP portion of the award",
            "funding_source_type": "Funding source",
            "rppr_submitted_year": "Reported as submitted in the RPPR (Table 1), Year",
            "rppr_awarded_year": "Reported as awarded in the RPPR (Table 1), Year",
            "exclude_from_table1": "Leave out of RPPR Table 1",
        }
        help_texts = {
            "exclude_from_table1": (
                "Tick this in two cases only. "
                "First, the parent COBRE award itself (P20GM113109) or a supplement to it. "
                "Second, a grant held by core staff that is not related to the core\u2019s IDeA-supported work. "
                "For example, a core technician\u2019s own research grant on an unrelated topic is left out, "
                "while an equipment grant for the core counts. "
                "This follows the FY27 COBRE guidance for Table 1: \u201cWhen reporting funding for Core staff, report only if related to IDeA support. For example, equipment grants.\u201d "
                "When unsure, leave it unticked. The Table 1 list can be checked on the RPPR tab before it goes in."
            ),
            "cnap_portion": (
                "If the CNAP investigator is the sole PI, leave this blank: "
                "the full award counts in RPPR Table 1. "
                "If the CNAP investigator is an MPI, Co-PI, collaborator, or subawardee, "
                "enter only that investigator’s portion of the award. "
                "For example: on a $1,200,000 award where the CNAP investigator's subaward "
                "is $250,000, enter 250000."
            ),
        }


from apps.portal.outcome_forms import apply_placeholders as _apply_placeholders  # noqa: E402

_apply_placeholders(PublicationForm)
_apply_placeholders(GrantForm)


def _sync(model, owner_field, owner, field, values, **extra):
    want = {v.pk for v in values}
    have = set(model.objects.filter(**{owner_field: owner}).values_list(f"{field}_id", flat=True))
    model.objects.filter(**{owner_field: owner}, **{f"{field}_id__in": have - want}).delete()
    for v in values:
        if v.pk not in have:
            model.objects.create(**{owner_field: owner, field: v}, **extra)


class _Rrid(forms.Form):
    """Admin view of "did the paper cite the core's RRID?", one select per core with an RRID (MW 2026-10-28)."""

    def __init__(self, *args, links=(), **kwargs):
        super().__init__(*args, **kwargs)
        from apps.outcomes.services import rrid_resources

        have = {x.resource_id: x.rrid_cited for x in links}
        self.by_pk = {}
        for r in rrid_resources():
            name = f"rrid_{r.pk}"
            self.fields[name] = forms.ChoiceField(
                label=f"{r.core.name} ({r.core.rrid}) cited in the methods?",
                choices=[
                    ("", "Not recorded"),
                    ("yes", "Yes"),
                    ("no", "No"),
                    ("unsure", "Not sure"),
                ],
                required=False,
                initial=have.get(r.pk, ""),
                help_text="Only counts if this core is ticked under Credit.",
            )
            self.by_pk[r.pk] = name

    def answers(self, picked):
        return {pk: self.cleaned_data.get(n) or "" for pk, n in self.by_pk.items() if pk in picked}


@manage_page
def publication_edit(request, pk=None):
    obj = get_object_or_404(Publication, pk=pk) if pk else None
    old_status = obj.status if obj else None
    post = request.POST or None
    if request.method == "POST" and "lookup" in request.POST:
        # "Fill in from PubMed": show the values for checking; nothing is saved yet (MW 2026-11-03).
        from apps.outcomes import pubmed

        post = request.POST.copy()
        try:
            found = pubmed.lookup(post.get("pubmed_url", ""))
        except pubmed.LookupError_ as exc:
            messages.warning(request, str(exc))
        else:
            for f in ("title", "journal"):
                if found.get(f):
                    post[f] = found[f]
            if found.get("authors"):
                post["author_display_text"] = found["authors"]
            if found.get("publication_date"):
                post["publication_date"] = found["publication_date"].isoformat()
            if found.get("url"):
                post["pubmed_url"] = found["url"]
            messages.info(
                request,
                "Filled in from PubMed. Check the title, journal, date, and authors before saving.",
            )
    form = PublicationForm(
        post,
        instance=obj,
        initial={
            "cnap_cited_tri": _tri_initial(obj.cnap_cited) if obj else "",
            "cnap_index_tri": _tri_initial(obj.cnap_in_grant_index) if obj else "",
        },
    )
    form.order_fields(
        [
            "status",
            "substatus",
            "title",
            "publication_type",
            "publication_type_other",
            "author_display_text",
            "journal",
            "pubmed_url",
            "submission_date",
            "publication_date",
            "cnap_cited_tri",
            "cnap_index_tri",
            "has_foreign_authors",
            "foreign_component_approved",
            "has_non_idea_coauthors",
            "comments",
        ]
    )
    credit = _Credit(
        request.POST or None,
        initial={
            "people": [x.person for x in obj.people.all()] if obj else [],
            "projects": [x.project for x in obj.project_links.all()] if obj else [],
            "resources": [x.resource for x in obj.resource_links.all()] if obj else [],
        },
    )
    rrid = _Rrid(request.POST or None, links=obj.resource_links.all() if obj else ())
    if (
        request.method == "POST"
        and "lookup" not in request.POST
        and form.is_valid()
        and credit.is_valid()
        and rrid.is_valid()
    ):
        with transaction.atomic():
            p = form.save(commit=False)
            p.cnap_cited = _tri(form.cleaned_data["cnap_cited_tri"])
            p.cnap_in_grant_index = _tri(form.cleaned_data["cnap_index_tri"])
            if p.status != PublicationStatus.SUBMITTED:
                p.substatus = None
            if not obj:
                p.created_by = request.user
            p.save()
            for i, person in enumerate(credit.cleaned_data["people"]):
                PublicationPerson.objects.update_or_create(
                    publication=p, person=person, defaults={"author_order": i}
                )
            PublicationPerson.objects.filter(publication=p).exclude(
                person__in=credit.cleaned_data["people"]
            ).delete()
            _sync(PublicationProject, "publication", p, "project", credit.cleaned_data["projects"])
            _sync(
                PublicationResource, "publication", p, "resource", credit.cleaned_data["resources"]
            )
            from apps.outcomes.services import set_rrid_answers

            set_rrid_answers(p, rrid.answers({r.pk for r in credit.cleaned_data["resources"]}))
            if p.status != old_status:
                PublicationStatusHistory.objects.create(
                    publication=p,
                    from_status=old_status,
                    to_status=p.status,
                    changed_by=request.user,
                )
            record_event(request.user, AuditLog.Action.UPDATE if obj else AuditLog.Action.CREATE, p)
        messages.success(request, "Publication saved.")
        return redirect("/manage/outcomes/?tab=pubs")
    return render(
        request,
        "manage/outcome_form.html",
        {"form": form, "credit": credit, "rrid": rrid, "obj": obj, "kind": "publication"},
    )


@manage_page
def grant_edit(request, pk=None):
    obj = get_object_or_404(GrantSubmission, pk=pk) if pk else None
    old_status = obj.status if obj else None
    pi = obj.people.filter(role=GrantRole.PI).first() if obj else None
    form = GrantForm(
        request.POST or None,
        instance=obj,
        initial={
            "ack_tri": _tri_initial(obj.cnap_acknowledged) if obj else "",
            "pi": pi.person if pi else None,
        },
    )
    credit = _Credit(
        request.POST or None,
        initial={
            "people": [x.person for x in obj.people.all()] if obj else [],
            "projects": [x.project for x in obj.project_links.all()] if obj else [],
            "resources": [x.resource for x in obj.resource_links.all()] if obj else [],
        },
    )
    credit.fields["people"].label = "CNAP members on this proposal"
    if obj:
        form.fields.pop("resubmission_of", None)
    # One field group after another, so the small group headings read in order (MW 2026-11-04).
    form.order_fields(
        [
            "status",
            "resubmission_of",
            "project_title",
            "pi",
            "grant_number",
            "funding_source_type",
            "funding_agency",
            "mechanism",
            "submission_date",
            "award_notice_date",
            "requested_total",
            "award_total",
            "cnap_portion",
            "ack_tri",
            "decision_comments",
        ]
    )
    if request.method == "POST" and form.is_valid() and credit.is_valid():
        with transaction.atomic():
            g = form.save(commit=False)
            g.cnap_acknowledged = _tri(form.cleaned_data["ack_tri"])
            if not obj:
                earlier = form.cleaned_data.get("resubmission_of")
                if earlier:
                    g.grant_family = earlier.grant_family
                    g.resubmission_of = earlier
                else:
                    g.grant_family = GrantFamily.objects.create(
                        title=g.project_title, created_by=request.user
                    )
                g.created_by = request.user
            g.save()
            if g.status == "not_funded":
                from apps.outcomes import funding

                funding.ensure_followup(
                    g, request.user
                )  # MW 2026-11-10: the follow-up queue, no redirect
            people = list(credit.cleaned_data["people"])
            lead = form.cleaned_data["pi"]
            if lead and lead not in people:
                people.append(lead)
            GrantSubmissionPerson.objects.filter(grant_submission=g).exclude(
                person__in=people
            ).delete()
            for person in people:
                GrantSubmissionPerson.objects.update_or_create(
                    grant_submission=g,
                    person=person,
                    defaults={"role": GrantRole.PI if person == lead else GrantRole.CO_I},
                )
            _sync(
                GrantSubmissionProject,
                "grant_submission",
                g,
                "project",
                credit.cleaned_data["projects"],
            )
            _sync(
                GrantSubmissionResource,
                "grant_submission",
                g,
                "resource",
                credit.cleaned_data["resources"],
            )
            if g.status != old_status:
                GrantStatusHistory.objects.create(
                    grant_submission=g,
                    from_status=old_status,
                    to_status=g.status,
                    changed_by=request.user,
                )
            record_event(request.user, AuditLog.Action.UPDATE if obj else AuditLog.Action.CREATE, g)
        messages.success(request, "Grant saved.")
        return redirect("/manage/outcomes/?tab=grants")
    return render(
        request,
        "manage/outcome_form.html",
        {
            "form": form,
            "credit": credit,
            "obj": obj,
            "kind": "grant",
            "can_edit": access.can_manage(request.user),
        },
    )


def _yn(v):
    return "" if v is None else ("Yes" if v else "No")


def _identified(user, form_code):
    from apps.forms_engine.models import FormDefinition
    from apps.reporting.access import IDENTIFIED, form_access

    fd = FormDefinition.objects.filter(code=form_code).first()
    return bool(fd) and form_access(user, fd) == IDENTIFIED


def _nihdocs_zip(request, gy):
    """Every uploaded NIH document for budget year `gy`, named Last_First_Document.pdf, plus a summary CSV."""
    import csv
    import io
    import zipfile

    from django.http import HttpResponse

    data = nihdocs.documents(gy)
    if not data:
        raise Http404("No one was asked for NIH documents in that budget year.")
    buf = io.BytesIO()
    summary = io.StringIO()
    w = csv.writer(summary)
    w.writerow(
        ["Last name", "First name", "Status", "D.2.a (25% effort reduction)", "D.2.a explanation"]
        + [label for _, label in nihdocs.DOC_FILES]
    )
    used = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for r in data["rows"]:
            cells = []
            for _code, label, f, _check in r["files"]:
                if not f:
                    cells.append("")
                    continue
                name = nihdocs.zip_name(r["person"], label, f)
                base, n = name, 2
                while name in used:
                    name = base.replace(".", f"_{n}.", 1)
                    n += 1
                used.add(name)
                with f.storage_key.open("rb") as fh:
                    z.writestr(name, fh.read())
                cells.append(name)
            d2a = {"yes": "Yes", "no": "No"}.get(r["d2a"], "")
            w.writerow(
                [r["person"].last_name, r["person"].first_name, r["status"], d2a, r["d2a_explain"]]
                + cells
            )
        z.writestr("summary.csv", "\ufeff" + summary.getvalue())
    record_event(request.user, AuditLog.Action.EXPORT, f"outcomes:nihdocs:{gy}")
    resp = HttpResponse(buf.getvalue(), content_type="application/zip")
    resp["Content-Disposition"] = f'attachment; filename="CNAP_Year{gy}_NIH_documents.zip"'
    return resp


@admin_view
def export(request, kind):
    """Citation list, grant list, or counts as a spreadsheet-ready CSV."""
    import csv
    import io

    from django.http import HttpResponse

    if kind in ("nihdocs", "teams"):
        gy = int(request.GET.get("year") or 0)
        if not _identified(
            request.user, nihdocs.DOC_FORM if kind == "nihdocs" else "progress_core"
        ):
            raise PermissionDenied("These lists name people. Your role can’t download them.")
        if kind == "nihdocs":
            return _nihdocs_zip(request, gy)

    buf = io.StringIO()
    w = csv.writer(buf)
    from apps.outcomes.services import status_dates

    def res(o, anticipated):
        names = [x.resource.name for x in o.resource_links.all() if x.is_anticipated == anticipated]
        if o.resources_other_text and any(
            x.resource.code == "other" and x.is_anticipated == anticipated
            for x in o.resource_links.all()
        ):
            names = [n if n != "Other" else f"Other: {o.resources_other_text}" for n in names]
        return "; ".join(names)

    def ts(d, key):
        v = d.get(key)
        return timezone.localtime(v).strftime("%Y-%m-%d %H:%M") if v else ""

    if kind in ("publications", "pubs"):
        # Columns from MW's Publication flow, section 8 (one publication = one row), plus people.
        w.writerow(
            [
                "Project ID",
                "Title",
                "Journal",
                "Current Status",
                "Anticipated Submission Date",
                "Submission Date",
                "Publication Date",
                "Decline Date",
                "PubMed Link",
                "CNAP Cited",
                "CNAP Grant Index",
                "Foreign Authors",
                "Anticipated Center Resources Utilized",
                "Center Resources Utilized",
                "Decline Comments",
                "Planned Date (timestamp)",
                "Submitted Date (timestamp)",
                "Published Date (timestamp)",
                "Declined Date (timestamp)",
                "CNAP People",
                "Core RRIDs cited",
            ]
        )
        qs = (
            Publication.objects.filter(archived_at__isnull=True)
            .prefetch_related(
                "people__person",
                "project_links__project",
                "resource_links__resource__core",
                "status_history",
            )
            .order_by("-updated_at")
        )
        for p in qs:
            d = status_dates(p)
            w.writerow(
                [
                    "; ".join(x.project.title for x in p.project_links.all()),
                    p.title,
                    p.journal,
                    p.get_status_display(),
                    p.anticipated_submission_month.strftime("%Y-%m")
                    if p.anticipated_submission_month
                    else "",
                    p.submission_date or "",
                    p.publication_date or "",
                    p.decline_date or "",
                    p.pubmed_url,
                    _yn(p.cnap_cited),
                    _yn(p.cnap_in_grant_index),
                    _yn(p.has_foreign_authors),
                    res(p, True),
                    res(p, False),
                    p.comments if p.status == PublicationStatus.DECLINED else "",
                    ts(d, "planned"),
                    ts(d, "submitted"),
                    ts(d, "published"),
                    ts(d, "declined"),
                    "; ".join(str(x.person) for x in p.people.all()),
                    "; ".join(
                        f"{x.resource.name}: {x.get_rrid_cited_display() or 'not asked'}"
                        for x in p.resource_links.all()
                        if x.resource.core_id and x.resource.core.rrid
                    ),
                ]
            )
    elif kind in ("c1", "table1"):
        from apps.outcomes import rppr

        gy = int(request.GET.get("year", rppr.current_year()))
        if kind == "c1":
            inc, exc = rppr.c1(gy)
            w.writerow(
                [
                    f"RPPR Year {gy} — C.1 Publications (published June 1, {2016 + gy} – May 31, {2017 + gy})"
                ]
            )
            w.writerow(
                [
                    "Authors",
                    "Title",
                    "Journal",
                    "Publication date",
                    "PubMed link",
                    "Cites P20GM113109",
                    "Non-IDeA-state co-authors",
                    "CNAP authors",
                    "Note",
                ]
            )
            for p in inc:
                w.writerow(
                    [
                        p.author_display_text,
                        p.title,
                        p.journal,
                        p.publication_date,
                        p.pubmed_url,
                        _yn(p.cnap_cited),
                        _yn(p.has_non_idea_coauthors),
                        "; ".join(str(x.person) for x in p.people.all()),
                        f"From Year {p.carried_from}, not reported before"
                        if p.carried_from
                        else "",
                    ]
                )
            w.writerow([])
            w.writerow(["Left out", "Title", "Reason"])
            for p, why in exc:
                w.writerow(["", p.title, why])
        else:
            t = rppr.table1(gy)
            w.writerow([f"RPPR Year {gy} — Table 1A: Funding Accomplishments"])
            w.writerow(
                ["Funding Sources", "NIH", "Federal, non-NIH", "Non-Federal Sources", "Total"]
            )
            w.writerow(
                ["Applications Submitted"]
                + [t["a"][k]["sub"] for k in t["sources"]]
                + [t["total"]["sub"]]
            )
            w.writerow(
                ["Awards Funded (New/Renewal)"]
                + [t["a"][k]["won"] for k in t["sources"]]
                + [t["total"]["won"]]
            )
            w.writerow(
                ["Total Award Costs (entire period of performance)"]
                + [round(t["a"][k]["cost"], 2) for k in t["sources"]]
                + [round(t["total"]["cost"], 2)]
            )
            w.writerow([])
            w.writerow(
                ["Table 1B: COBRE Funding Accomplishments by Role for This Reporting Period"]
            )
            w.writerow(["Breakdown of Table 1A by Role"] + t["roles"])
            w.writerow(["# Applications Submitted"] + [t["b"][k]["sub"] for k in t["roles"]])
            w.writerow(["# New/Renewal Awards Funded"] + [t["b"][k]["won"] for k in t["roles"]])
            w.writerow(
                ["Total Award Costs (entire period of performance)"]
                + [round(t["b"][k]["cost"], 2) for k in t["roles"]]
            )
            w.writerow([])
            w.writerow(
                [
                    "Counted",
                    "Title",
                    "Version",
                    "Lead",
                    "Role",
                    "Funding source",
                    "Source guessed from agency",
                    "Amount",
                    "Amount basis",
                    "Note",
                ]
            )
            for r in t["rows"]:
                w.writerow(
                    [
                        r["kind"],
                        r["g"].project_title,
                        r["g"].version_label,
                        r["lead"] or "",
                        r["role"],
                        r["source"],
                        "yes" if r["guessed"] else "",
                        r["cost"] or "",
                        r["basis"],
                        "; ".join(
                            x
                            for x in (
                                f"From Year {r['carried_from']}, not reported before"
                                if r["carried_from"]
                                else "",
                                r["check"],
                            )
                            if x
                        ),
                    ]
                )
            for g, why in t["skipped"]:
                w.writerow(
                    ["Not counted", g.project_title, g.version_label, "", "", "", "", "", why]
                )
    elif kind == "sitevisit":
        import datetime as dt

        from apps.outcomes import rppr, sitevisit

        gy = int(request.GET.get("year", rppr.current_year()))
        try:
            since = dt.date.fromisoformat(request.GET.get("since", ""))
        except ValueError:
            since = None
        pubs, talks, grants = (
            sitevisit.publications(gy, since),
            sitevisit.presentations(gy, since),
            sitevisit.grants(gy, since),
        )
        core_names = [label for _, label in sitevisit.CORES]
        head = f"Year {gy} site visit (June 1, {2016 + gy} – May 31, {2017 + gy})"
        w.writerow([head + " — Publications (duplicates counted)"])
        for t in pubs["rows"]:
            if not t["rows"]:
                continue
            w.writerow([t["core"], "Type"] + pubs["cols"] + ["Total"])
            for r in t["rows"]:
                w.writerow(["", r["type"]] + r["vals"] + [r["total"]])
            w.writerow(["", "Total"] + t["col_totals"] + [t["total"]])
        w.writerow([f"{pubs['n_items']} publications; {pubs['n_counted']} counted across cores"])
        w.writerow([])
        w.writerow([head + " — Presentations (duplicates counted)"])
        w.writerow(["Core"] + talks["cols"] + ["Total"])
        for r in talks["rows"]:
            w.writerow([r["core"]] + r["vals"] + [r["total"]])
        w.writerow(["Total"] + talks["col_totals"] + [talks["n_counted"]])
        w.writerow([f"{talks['n_items']} presentations"])
        w.writerow([])
        w.writerow([head + " — Grants and awards (duplicates counted; total costs)"])
        hdr = ["Core"]
        for st in sitevisit.GRANT_STATUSES:
            hdr += [f"{st} count", f"{st} total $"]
        w.writerow(hdr + ["Total $"])
        for r in grants["rows"]:
            w.writerow(
                [r["label"]]
                + [v for x in r["cells"] for v in (x["n"], round(x["dollars"], 2))]
                + [round(r["dollars"], 2)]
            )
        w.writerow(["Funder"] + hdr[1:] + ["Total count"])
        for r in grants["by_funder"]:
            w.writerow(
                [r["label"]]
                + [v for x in r["cells"] for v in (x["n"], round(x["dollars"], 2))]
                + [r["n"]]
            )
        w.writerow([])
        w.writerow(["Pending proposals", "Count", "Requested $"])
        for r in grants["pending"]:
            w.writerow([r["label"], r["n"], round(r["dollars"], 2)])
        w.writerow(["Only 'Submitted this year' is in the tables above."])
        w.writerow([])
        w.writerow(
            [
                "Items",
                "Kind",
                "Title",
                "Type or funder",
                "Status",
                "Cores",
                "Two or more cores",
                "Added after " + (str(since) if since else "(no date chosen)"),
            ]
        )
        for it in pubs["items"]:
            p = it["obj"]
            w.writerow(
                [
                    "",
                    "Publication",
                    p.title,
                    p.get_publication_type_display(),
                    it["status"],
                    "; ".join(
                        core_names[[c for c, _ in sitevisit.CORES].index(c)] for c in it["cores"]
                    ),
                    "yes" if len(it["cores"]) > 1 else "",
                    "yes" if it["new"] else "",
                ]
            )
        for it in talks["items"]:
            t = it["obj"]
            w.writerow(
                [
                    "",
                    "Presentation",
                    t.title,
                    t.get_presentation_type_display(),
                    "",
                    "; ".join(
                        core_names[[c for c, _ in sitevisit.CORES].index(c)] for c in it["cores"]
                    ),
                    "yes" if len(it["cores"]) > 1 else "",
                    "yes" if it["new"] else "",
                ]
            )
        for it in grants["items"]:
            g = it["obj"]
            w.writerow(
                [
                    "",
                    "Grant",
                    g.project_title,
                    it["funder"],
                    it["status"],
                    "; ".join(
                        core_names[[c for c, _ in sitevisit.CORES].index(c)] for c in it["cores"]
                    ),
                    "yes" if len(it["cores"]) > 1 else "",
                    "yes" if it["new"] else "",
                ]
            )
        w.writerow([])
        w.writerow(
            [
                "Still waiting from earlier years (not in the numbers above)",
                "Kind",
                "Title",
                "Funder",
                "Status",
                "Cores",
                "Submitted",
                "Submitted in year",
                "First entered on the site",
                "Requested $",
            ]
        )
        for kind_label, lst, title in (
            ("Publication", pubs["carried"], lambda o: o.title),
            ("Grant", grants["carried"], lambda o: o.project_title),
        ):
            for it in lst:
                o = it["obj"]
                w.writerow(
                    [
                        "",
                        kind_label,
                        title(o),
                        it.get("funder", ""),
                        it.get("status", "Pending"),
                        "; ".join(
                            core_names[[c for c, _ in sitevisit.CORES].index(c)]
                            for c in it["cores"]
                        ),
                        o.submission_date,
                        f"Year {it['submitted_year']}",
                        timezone.localtime(it["entered"]).date(),
                        round(it["dollars"], 2) if "dollars" in it else "",
                    ]
                )
    elif kind in ("table2", "d1"):
        from apps.outcomes import rppr

        gy = int(request.GET.get("year", rppr.current_year()))
        if kind == "table2":
            t = rppr.table2(gy, _t2_periods(request, gy))
            w.writerow(
                [
                    f"RPPR Year {gy} — Table 2. COBRE Core Users (reports: "
                    + ", ".join(p.name for p in t["periods"])
                    + ")"
                ]
            )
            w.writerow(
                ["A user lab may be listed more than once if different projects were supported."]
            )
            for c in t["cores"]:
                w.writerow([])
                w.writerow([f"Table {c['letter']}", f"Core Name: {c['core'].name}"])
                w.writerow([label for _, label in t["cols"]] + ["User lab (not a Table 2 column)"])
                for r in c["rows"]:
                    w.writerow(r["cells"] + [r.get("lab", "")])
                w.writerow(
                    [
                        f"Total User Labs: {c['labs']}",
                        "",
                        f"Total Users: {c['total_users']}",
                        f"Total Award Costs (entire period of performance): ${c['award_costs']:,.0f}",
                        c["users"],
                        c["students"],
                        "",
                        "",
                    ]
                )
                for g in c["gaps"]:
                    w.writerow(
                        ["Not yet reported", g["period"].name, "; ".join(map(str, g["people"]))]
                    )
                for d in c["doubles"]:
                    w.writerow(
                        [
                            "Two reports, check for duplicates",
                            d["period"].name,
                            "; ".join(map(str, d["people"])),
                        ]
                    )
                if c["summary"]:
                    w.writerow(["Core use sentence", c["summary"]])
                for p in c["pubs"]:
                    w.writerow(
                        ["Paper crediting this core", p.title, p.journal, p.publication_date]
                    )
                for g in c["grants"]:
                    w.writerow(
                        [
                            "Proposal crediting this core",
                            g.project_title,
                            g.funding_agency,
                            g.get_status_display(),
                        ]
                    )
        else:
            t = rppr.d1(gy)
            w.writerow(
                [f"RPPR Year {gy} — D.1 Participants (June 1, {2016 + gy} – May 31, {2017 + gy})"]
            )
            w.writerow(
                [
                    "Name",
                    "eRA Commons ID",
                    "ORCID",
                    "Sr/Key (named on the NoA)",
                    "Degree(s)",
                    "Role",
                    "All CNAP roles",
                    "Project or core",
                    "Career level (trainees)",
                    "Institution",
                    "Calendar months",
                    "Academic months",
                    "Summer months",
                    "Total person months",
                    "Foreign organization and country",
                ]
            )
            for r in t["rows"]:
                p = r["person"]
                w.writerow(
                    [
                        f"{p.last_name}, {p.first_name}",
                        r["commons"],
                        p.orcid,
                        "Y" if r["senior_key"] else "N",
                        r["degrees"],
                        r["label"],
                        "; ".join(r["roles"]),
                        "; ".join(r["where"]),
                        r["level"],
                        p.institution,
                        "" if r["cal"] is None else r["cal"],
                        "" if r["aca"] is None else r["aca"],
                        "" if r["sum"] is None else r["sum"],
                        r["months"] if r["months"] is not None else "missing",
                        r["foreign"],
                    ]
                )
    elif kind in ("talks", "presentations"):
        from apps.outcomes.models import Presentation

        w.writerow(
            [
                "Project ID",
                "Type",
                "Title",
                "Event",
                "Location",
                "Date",
                "Presenters and authors",
                "Acknowledges CNAP",
                "Center Resources Utilized",
                "CNAP People",
            ]
        )
        for t in (
            Presentation.objects.filter(archived_at__isnull=True)
            .prefetch_related(
                "people__person", "project_links__project", "resource_links__resource"
            )
            .order_by("-presented_on")
        ):
            w.writerow(
                [
                    "; ".join(x.project.title for x in t.project_links.all()),
                    t.get_presentation_type_display(),
                    t.title,
                    t.event,
                    t.location,
                    t.presented_on or "",
                    t.author_display_text,
                    _yn(t.cnap_cited),
                    "; ".join(
                        x.resource.name
                        if x.resource.code != "other" or not t.resources_other_text
                        else f"Other: {t.resources_other_text}"
                        for x in t.resource_links.all()
                    ),
                    "; ".join(str(x.person) for x in t.people.all()),
                ]
            )
    elif kind == "grants":
        # Columns from MW's Grant flow, section 9 (one submission = one row).
        w.writerow(
            [
                "Parent Grant ID",
                "Submission Version",
                "Project ID",
                "PI / CNAP contact",
                "Role",
                "Title",
                "Funding Agency",
                "Mechanism",
                "Funding Opportunity Link",
                "Current Status",
                "Anticipated Submission Date",
                "Submission Date",
                "Award Date",
                "Project Start Date",
                "Project End Date",
                "Decision Date",
                "Anticipated Total Budget (planned, estimate)",
                "Estimated Direct Costs (planned, estimate)",
                "Total Requested Budget",
                "Estimated Direct Costs (submitted, estimate)",
                "Estimated Indirect Costs (submitted, estimate)",
                "Total Award Amount (final)",
                "Direct Costs (final)",
                "Indirect Costs (final)",
                "Grant Number",
                "Prime vs Subaward",
                "CNAP Acknowledged",
                "CNAP Future Credit",
                "Foreign Component",
                "Program Officer Discussion",
                "Program Officer Name",
                "Discussion Date",
                "Reviewer Feedback Shared with CNAP",
                "Comments",
                "Plans to Resubmit",
                "Anticipated Center Resources Utilized",
                "Center Resources Utilized",
                "Planned Date (timestamp)",
                "Submitted / Pending Date (timestamp)",
                "Awarded Date (timestamp)",
                "Not Funded Date (timestamp)",
            ]
        )
        qs = (
            GrantSubmission.objects.filter(archived_at__isnull=True)
            .select_related("grant_family")
            .prefetch_related(
                "people__person",
                "project_links__project",
                "resource_links__resource",
                "status_history",
            )
            .order_by("grant_family_id", "version_no")
        )
        for g in qs:
            d = status_dates(g)
            lead = next((x for x in g.people.all() if x.is_primary_cnap_contact), None) or next(
                iter(g.people.all()), None
            )
            w.writerow(
                [
                    g.grant_family_id,
                    g.version_label,
                    "; ".join(x.project.title for x in g.project_links.all()),
                    str(lead.person) if lead else "",
                    lead.get_role_display() if lead else "",
                    g.project_title,
                    g.funding_agency,
                    g.mechanism,
                    g.opportunity_url,
                    g.get_status_display(),
                    g.anticipated_submission_date.strftime("%Y-%m")
                    if g.anticipated_submission_date
                    else "",
                    g.submission_date or "",
                    g.award_notice_date or "",
                    g.project_start_date or "",
                    g.project_end_date or "",
                    g.decision_date or "",
                    g.anticipated_total or "",
                    g.planned_estimated_direct or "",
                    g.requested_total or "",
                    g.requested_direct or "",
                    g.requested_indirect or "",
                    g.award_total or "",
                    g.award_direct or "",
                    g.award_indirect or "",
                    g.grant_number,
                    g.get_prime_or_subaward_display() if g.prime_or_subaward else "",
                    _yn(g.cnap_acknowledged),
                    _yn(g.cnap_credited_in_publications),
                    _yn(g.has_foreign_component),
                    _yn(g.discussed_with_program_officer),
                    g.program_officer_name,
                    g.discussion_date or "",
                    _yn(g.feedback_shared_with_cnap),
                    g.decision_comments,
                    _yn(g.plans_to_resubmit),
                    res(g, True),
                    res(g, False),
                    ts(d, "planned"),
                    ts(d, "submitted"),
                    ts(d, "awarded"),
                    ts(d, "not_funded"),
                ]
            )
    elif kind == "teams":
        w.writerow(
            ["Period", "Project or core", "Reported by"] + [label for _, label in nihdocs.TEAM_COLS]
        )
        for t in nihdocs.teams(gy):
            for r in t["people"]:
                w.writerow(
                    [t["period"].short_label, t["where"], str(t["leader"])]
                    + [r.get(c) or "" for c, _ in nihdocs.TEAM_COLS]
                )
    else:
        c = counts()
        w.writerow(["Group", "Credited to", "Measure"] + [f"Y{y}" for y in c["years"]] + ["Total"])
        for title, t in [
            ("All CNAP", c["all"]),
            ("Project", c["projects"]),
            ("Core or resource", c["cores"]),
        ]:
            for r in t["rows"]:
                for label, cell in zip(t["cols"], r["cells"]):
                    per = dict(cell["per"])
                    w.writerow(
                        [title, r["group"], label]
                        + [per.get(y, 0) for y in c["years"]]
                        + [cell["total"]]
                    )
    record_event(request.user, AuditLog.Action.EXPORT, f"outcomes:{kind}")
    resp = HttpResponse("﻿" + buf.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="cnap_{kind}.csv"'
    if (
        request.GET.get("format") == "xlsx"
    ):  # the same cells as the CSV, as a formatted workbook (MW 2026-11-05)
        from apps.reporting.services.exports import csv_to_xlsx

        names = {
            "publications": "Papers",
            "pubs": "Papers",
            "talks": "Talks and posters",
            "presentations": "Talks and posters",
            "grants": "Grant proposals",
            "c1": "RPPR C.1",
            "table1": "RPPR Tables 1A and 1B",
            "table2": "RPPR Table 2",
            "d1": "RPPR D.1",
            "teams": "Research teams",
            "sitevisit": "Site-visit report",
        }
        return csv_to_xlsx(resp, f"cnap_{kind}.xlsx", title=names.get(kind, kind.title()))
    return resp


def person_outcomes(person):
    """Everything credited to one person, for their page."""
    pubs = (
        Publication.objects.filter(archived_at__isnull=True, people__person=person)
        .distinct()
        .order_by("-publication_date")
    )
    grants = (
        GrantSubmission.objects.filter(archived_at__isnull=True, people__person=person)
        .distinct()
        .order_by("-submission_date")
    )
    from apps.outcomes.models import Presentation

    talks = (
        Presentation.objects.filter(archived_at__isnull=True, people__person=person)
        .distinct()
        .order_by("-presented_on")
    )
    return {"pubs": pubs, "grants": grants, "talks": talks}


def _t2_choices():
    from apps.reporting.models import ReportingPeriod

    return list(
        ReportingPeriod.objects.filter(assignments__form_definition__code="core_usage_report")
        .distinct()
        .order_by("-display_order")
    )


def _t2_periods(request, gy):
    """Collections chosen for Table 2 (?t2p=…); the budget year's own collections by default."""
    from apps.outcomes import rppr
    from apps.reporting.models import ReportingPeriod

    ids = [int(x) for x in request.GET.getlist("t2p") if x.isdigit()]
    return list(ReportingPeriod.objects.filter(pk__in=ids)) if ids else rppr.usage_periods(gy)


def _sv_ctx(request):
    """Site-visit tables (MW's workbook layout) for a budget year; ?since=YYYY-MM-DD marks newer entries."""
    import datetime as dt

    from apps.outcomes import rppr, sitevisit

    cur = rppr.current_year()
    try:
        gy = int(request.GET.get("year", cur))
    except ValueError:
        gy = cur
    try:
        since = dt.date.fromisoformat(request.GET.get("since", ""))
    except ValueError:
        since = None
    return {
        "year": gy,
        "years": list(range(cur, 5, -1)),
        "since": since,
        "pubs": sitevisit.publications(gy, since),
        "talks": sitevisit.presentations(gy, since),
        "grants": sitevisit.grants(gy, since),
        "pub_statuses": sitevisit.PUB_STATUSES,
        "grant_statuses": sitevisit.GRANT_STATUSES,
    }


def _prev_marked(gy):
    """Has anything been marked as reported in the Year gy RPPR?"""
    return (
        Publication.objects.filter(rppr_year=gy).exists()
        or GrantSubmission.objects.filter(
            Q(rppr_submitted_year=gy) | Q(rppr_awarded_year=gy)
        ).exists()
    )


def _rppr_ctx(request):
    from apps.outcomes import rppr

    cur = rppr.current_year()
    try:
        gy = int(request.GET.get("year", cur))
    except ValueError:
        gy = cur
    inc, exc = rppr.c1(gy)
    t1 = rppr.table1(gy)
    start, end = rppr.period(gy)
    docs_ok = _identified(request.user, nihdocs.DOC_FORM)
    return {
        "docs": nihdocs.documents(gy) if docs_ok else None,
        "docs_ok": docs_ok,
        "teams": nihdocs.teams(gy) if _identified(request.user, "progress_core") else [],
        "year": gy,
        "years": list(range(cur, 5, -1)),
        "start": start,
        "end": end,
        "c1": inc,
        "c1_excluded": exc,
        "non_idea": sum(1 for p in inc if p.has_non_idea_coauthors),
        "carried": sum(1 for p in inc if p.carried_from)
        + sum(1 for r in t1["rows"] if r["carried_from"]),
        "prev_marked": _prev_marked(gy - 1),
        "t1": t1,
        "t2": (t2 := rppr.table2(gy, _t2_periods(request, gy))),
        "t2_choices": _t2_choices(),
        "d1": (d1 := rppr.d1(gy)),
        # roll-ups for the section headers
        "c1_not_cited": sum(1 for p in inc if p.cnap_cited is False),
        "c1_unchecked": sum(1 for p in inc if p.cnap_cited is None),
        "t2_users": sum(c["total_users"] for c in t2["cores"]),
        "t2_reported": sum(1 for c in t2["cores"] if c["assigned"] and not c["gaps"]),
        "t2_waiting": sum(1 for c in t2["cores"] if c["gaps"]),
        "d1_cats": [
            {
                "label": cat,
                "n": sum(1 for x in d1["rows"] if x["category"] == cat),
                "no_id": sum(1 for x in d1["rows"] if x["category"] == cat and not x["commons"]),
                "no_months": sum(
                    1 for x in d1["rows"] if x["category"] == cat and x["months"] is None
                ),
            }
            for cat in rppr.D1_ORDER
            if any(x["category"] == cat for x in d1["rows"])
        ],
    }


@manage_action
def mark_rppr(request):
    from apps.outcomes import rppr

    gy = int(request.POST["year"])
    n = rppr.mark_reported(request.user, gy)
    messages.success(
        request,
        f"{n} item{'s' if n != 1 else ''} marked as reported in the Year {gy} RPPR. Those items won’t be counted again in later years.",
    )
    return redirect(f"/manage/outcomes/?tab=rppr&year={gy}")


@manage_action
def send_reminders(request):
    sent = _rem.send(actor=request.user)
    messages.success(
        request,
        f"{len(sent)} reminder{'s' if len(sent) != 1 else ''} sent."
        if sent
        else "No reminders were due.",
    )
    return redirect("/manage/outcomes/?tab=reminders")


@manage_action
def grant_resubmit(request, pk):
    """Start the next round of a not-funded proposal, copied from it (MW 2026-11-04)."""
    from apps.outcomes.services import start_resubmission

    g = get_object_or_404(GrantSubmission, pk=pk)
    new = start_resubmission(request.user, g)
    record_event(request.user, AuditLog.Action.CREATE, new, new={"resubmission_of": g.pk})
    messages.success(
        request,
        f"Round {new.version_label} is ready, copied from {g.version_label}. Update anything that changed.",
    )
    return redirect("manage:grant_edit", pk=new.pk)


@manage_action
def table1_exclude(request, pk):
    """Leave a proposal out of RPPR Table 1, or put it back, with the evaluator's reason (MW 2026-11-04)."""
    g = get_object_or_404(GrantSubmission, pk=pk)
    back = request.POST.get("next") or "/manage/outcomes/?tab=rppr#rp-t1"
    if request.POST.get("action") == "restore":
        old = {"exclude": g.exclude_from_table1, "reason": g.table1_exclusion_reason}
        g.exclude_from_table1 = False
        g.table1_exclusion_reason = ""
        g.save(update_fields=["exclude_from_table1", "table1_exclusion_reason", "updated_at"])
        record_event(request.user, AuditLog.Action.UPDATE, g, old=old, new={"exclude": False})
        messages.success(
            request, f"{g.project_title} ({g.version_label}) is counted in Table 1 again."
        )
        return redirect(back)
    reason = request.POST.get("reason", "").strip()
    if not reason:
        messages.error(request, "Give a short reason for leaving it out of Table 1.")
        return redirect(back)
    g.exclude_from_table1 = True
    g.table1_exclusion_reason = reason[:1000]
    g.save(update_fields=["exclude_from_table1", "table1_exclusion_reason", "updated_at"])
    record_event(request.user, AuditLog.Action.UPDATE, g, new={"exclude": True, "reason": reason})
    messages.success(request, f"{g.project_title} ({g.version_label}) is left out of Table 1.")
    return redirect(back)


@admin_view
def grant_round_json(request, pk):
    """What the add form needs to fill itself in from an earlier round (MW 2026-11-04)."""
    from django.http import JsonResponse

    g = get_object_or_404(GrantSubmission, pk=pk)
    lead = g.people.filter(role=GrantRole.PI).first() or g.people.first()
    return JsonResponse(
        {
            "fields": {
                "project_title": g.project_title,
                "funding_agency": g.funding_agency,
                "mechanism": g.mechanism,
                "funding_source_type": g.funding_source_type,
                "requested_total": str(g.requested_total or ""),
            },
            "people": [x.person_id for x in g.people.all()],
            "projects": [x.project_id for x in g.project_links.all()],
            "resources": [x.resource_id for x in g.resource_links.all()],
            "pi": lead.person_id if lead else None,
            "label": f"{g.project_title} ({g.version_label})",
        }
    )
