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
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts import access
from apps.audit.models import AuditLog, record_event
from apps.common.enums import GrantRole, GrantStatus, PublicationStatus
from apps.outcomes import reminders as _rem
from apps.outcomes.models import (
    GrantFamily,
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
        "people__person", "project_links__project", "resource_links__resource"
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
    else:
        rows = published.filter(_ack_q("cnap_cited", f)) if f != "all" else pubs
        rows = rows.order_by("-publication_date", "-updated_at")
    return render(
        request,
        "manage/outcomes.html",
        {
            "reminders_due": _rem.due() if tab == "reminders" else None,
            "reminders_sent": OutcomeReminder.objects.select_related("person")[:20]
            if tab == "reminders"
            else None,
            "stale_days": settings.OUTCOME_STALE_DAYS,
            "remind_every": settings.OUTCOME_REMINDER_EVERY_DAYS,
            "counts": (c := counts() if tab == "counts" else None),
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


def counts():
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
        add(groups_of(p), "pubs", grant_year(p.publication_date))
    for t in talks:
        add(groups_of(t), "talks", grant_year(t.presented_on))
    for g in grants:
        add(groups_of(g), "sub", grant_year(g.submission_date))
        if g.status == GrantStatus.AWARDED:
            y = grant_year(g.award_notice_date or g.submission_date)
            add(groups_of(g), "won", y)
            add(groups_of(g), "dollars", y, float(g.award_total or 0))
    years = sorted(years)

    def table(kind):
        names = sorted({k[1] for k in tally if k[0] == kind})
        rows = []
        for n in names:
            for m, label in metrics:
                vals = [tally.get((kind, n, m, y), 0) for y in years]
                if any(vals):
                    rows.append(
                        {
                            "group": n,
                            "metric": label,
                            "dollars": m == "dollars",
                            "vals": vals,
                            "total": sum(vals),
                        }
                    )
        return rows

    return {
        "years": years,
        "all": table("all"),
        "projects": table("project"),
        "cores": table("core"),
    }


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
        label="CNAP people on it",
    )
    projects = forms.ModelMultipleChoiceField(
        queryset=Project.objects.filter(archived_at__isnull=True).order_by("title"),
        required=False,
        widget=forms.CheckboxSelectMultiple,
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
            "title",
            "publication_type",
            "status",
            "substatus",
            "author_display_text",
            "journal",
            "submission_date",
            "publication_date",
            "pubmed_url",
            "comments",
        ]
        widgets = {
            "submission_date": forms.DateInput(attrs={"type": "date"}),
            "publication_date": forms.DateInput(attrs={"type": "date"}),
            "author_display_text": forms.Textarea(attrs={"rows": 2}),
            "comments": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {"author_display_text": "Authors (as cited)", "pubmed_url": "PubMed or DOI link"}


class GrantForm(forms.ModelForm):
    family_title = forms.CharField(
        required=False,
        label="Resubmission of (title of the earlier proposal)",
        help_text="Leave blank for a new proposal. Matching titles are grouped as A0, A1, …",
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
            "project_title",
            "funding_agency",
            "mechanism",
            "status",
            "submission_date",
            "requested_total",
            "award_notice_date",
            "award_total",
            "grant_number",
            "decision_comments",
        ]
        widgets = {
            "submission_date": forms.DateInput(attrs={"type": "date"}),
            "award_notice_date": forms.DateInput(attrs={"type": "date"}),
            "decision_comments": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {"project_title": "Proposal title", "decision_comments": "Notes"}


def _sync(model, owner_field, owner, field, values, **extra):
    want = {v.pk for v in values}
    have = set(model.objects.filter(**{owner_field: owner}).values_list(f"{field}_id", flat=True))
    model.objects.filter(**{owner_field: owner}, **{f"{field}_id__in": have - want}).delete()
    for v in values:
        if v.pk not in have:
            model.objects.create(**{owner_field: owner, field: v}, **extra)


@manage_page
def publication_edit(request, pk=None):
    obj = get_object_or_404(Publication, pk=pk) if pk else None
    old_status = obj.status if obj else None
    form = PublicationForm(
        request.POST or None,
        instance=obj,
        initial={
            "cnap_cited_tri": _tri_initial(obj.cnap_cited) if obj else "",
            "cnap_index_tri": _tri_initial(obj.cnap_in_grant_index) if obj else "",
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
    if request.method == "POST" and form.is_valid() and credit.is_valid():
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
        {"form": form, "credit": credit, "obj": obj, "kind": "publication"},
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
    if request.method == "POST" and form.is_valid() and credit.is_valid():
        with transaction.atomic():
            g = form.save(commit=False)
            g.cnap_acknowledged = _tri(form.cleaned_data["ack_tri"])
            if not obj:
                fam_title = form.cleaned_data["family_title"].strip()
                fam = (
                    GrantFamily.objects.filter(title__iexact=fam_title).first()
                    if fam_title
                    else None
                )
                g.grant_family = fam or GrantFamily.objects.create(
                    title=g.project_title, created_by=request.user
                )
                g.created_by = request.user
            g.save()
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
        {"form": form, "credit": credit, "obj": obj, "kind": "grant"},
    )


def _yn(v):
    return "" if v is None else ("Yes" if v else "No")


@admin_view
def export(request, kind):
    """Citation list, grant list or counts as a spreadsheet-ready CSV."""
    import csv
    import io

    from django.http import HttpResponse

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
            ]
        )
        qs = (
            Publication.objects.filter(archived_at__isnull=True)
            .prefetch_related(
                "people__person",
                "project_links__project",
                "resource_links__resource",
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
    else:
        c = counts()
        w.writerow(["Group", "Credited to", "Measure"] + [f"Y{y}" for y in c["years"]] + ["Total"])
        for title, rows in [
            ("All CNAP", c["all"]),
            ("Project", c["projects"]),
            ("Core or resource", c["cores"]),
        ]:
            for r in rows:
                w.writerow([title, r["group"], r["metric"]] + r["vals"] + [r["total"]])
    record_event(request.user, AuditLog.Action.EXPORT, f"outcomes:{kind}")
    resp = HttpResponse("﻿" + buf.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="cnap_{kind}.csv"'
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
    return {"pubs": pubs, "grants": grants}


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
