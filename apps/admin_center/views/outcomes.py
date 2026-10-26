"""
Publications and grants, starting with acknowledgment tracking (decisions.md 2026-10-25).

MW's first need: check whether CNAP was acknowledged. Publications carry `cnap_cited`
(the paper cites CNAP's grant) and `cnap_in_grant_index` (the paper is linked to the
grant in NIH's index); grant submissions carry `cnap_acknowledged`. Each is Yes, No,
or not checked yet (NULL). One outcome can be credited to several projects and cores.
"""

from django import forms
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts import access
from apps.audit.models import AuditLog, record_event
from apps.common.enums import GrantRole, GrantStatus, PublicationStatus
from apps.outcomes.models import (
    GrantFamily,
    GrantStatusHistory,
    GrantSubmission,
    GrantSubmissionPerson,
    GrantSubmissionProject,
    GrantSubmissionResource,
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
    if tab == "grants":
        rows = sent.filter(_ack_q("cnap_acknowledged", f)) if f != "all" else grants
        rows = rows.order_by("-submission_date", "-updated_at")
    else:
        rows = published.filter(_ack_q("cnap_cited", f)) if f != "all" else pubs
        rows = rows.order_by("-publication_date", "-updated_at")
    return render(
        request,
        "manage/outcomes.html",
        {
            "tab": tab,
            "ack": f,
            "filters": ACK_FILTERS,
            "rows": rows,
            "summary": summary,
            "can_edit": access.can_manage(request.user),
        },
    )


@manage_action
def set_ack(request, kind, pk):
    value = {"yes": True, "no": False}.get(request.POST.get("value"))
    if kind == "grant":
        obj = get_object_or_404(GrantSubmission, pk=pk)
        old = obj.cnap_acknowledged
        obj.cnap_acknowledged = value
        obj.save(update_fields=["cnap_acknowledged", "updated_at"])
        field = "cnap_acknowledged"
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
