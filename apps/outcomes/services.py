"""
Self-entry of publications and grants (MW's Publication flow and Grant flow, decisions.md 2026-10-26).

Each reporting period, project awardees (RPL, PPL) check in once:
  * with no records of a kind yet: "Do you plan to submit any publications?" / "... grant proposals?"
    Yes -> create Planned entries; No -> recorded for the period.
  * for every Planned or Submitted record: "Confirm no changes" or "Update status", with the
    questions for the new status. Records reviewed since the period opened don't come back.
A faculty member can let someone (usually a student) enter on their behalf.
"""

import datetime as dt

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.models import AuditLog, record_event
from apps.common.enums import GrantRole, GrantStatus, PublicationStatus
from apps.people.models import Person, PersonRelationship

from .models import (
    GrantFamily,
    GrantStatusHistory,
    GrantSubmission,
    GrantSubmissionPerson,
    GrantSubmissionProject,
    GrantSubmissionResource,
    OutcomeCheckin,
    OutcomeDelegate,
    Presentation,
    PresentationPerson,
    PresentationProject,
    PresentationResource,
    Publication,
    PublicationPerson,
    PublicationProject,
    PublicationResource,
    PublicationStatusHistory,
)

AWARDEE_ROLES = ("project_leader", "pilot_awardee")
OPEN_PUB = (PublicationStatus.PLANNED, PublicationStatus.SUBMITTED)
OPEN_GRANT = (GrantStatus.PLANNED, GrantStatus.SUBMITTED)
STALE_DAYS = getattr(settings, "OUTCOME_STALE_DAYS", 120)


# --------------------------------------------------------------------------- who


def is_awardee(person, on=None):
    on = on or timezone.localdate()
    return (
        PersonRelationship.objects.filter(
            person=person, relationship_type__code__in=AWARDEE_ROLES, effective_from__lte=on
        )
        .exclude(effective_to__lt=on)
        .exists()
    )


def owners_for(person):
    """People this person can enter for: themselves (if an awardee or already has records) and anyone who delegated to them."""
    out = []
    if (
        is_awardee(person)
        or Publication.objects.filter(people__person=person).exists()
        or GrantSubmission.objects.filter(people__person=person).exists()
    ):
        out.append(person)
    for d in OutcomeDelegate.objects.filter(delegate=person, ended_at__isnull=True).select_related(
        "owner"
    ):
        if d.owner not in out:
            out.append(d.owner)
    return out


def can_act_for(user, owner):
    me = getattr(user, "person", None)
    if not me:
        return False
    return (
        me.pk == owner.pk
        or OutcomeDelegate.objects.filter(owner=owner, delegate=me, ended_at__isnull=True).exists()
    )


def awardee_projects(person, on=None):
    on = on or timezone.localdate()
    return [
        r.project
        for r in PersonRelationship.objects.filter(
            person=person,
            relationship_type__code__in=AWARDEE_ROLES,
            effective_from__lte=on,
            project__isnull=False,
        )
        .exclude(effective_to__lt=on)
        .select_related("project")
    ]


def add_delegate(user, owner, delegate):
    if owner.pk == delegate.pk:
        raise ValueError("You can’t add yourself.")
    d, created = OutcomeDelegate.objects.get_or_create(
        owner=owner, delegate=delegate, ended_at=None, defaults={"created_by": user}
    )
    if created:
        record_event(
            user, AuditLog.Action.CREATE, d, new={"owner": owner.pk, "delegate": delegate.pk}
        )
    return d


def end_delegate(user, d):
    d.ended_at = timezone.now()
    d.save(update_fields=["ended_at"])
    record_event(user, AuditLog.Action.UPDATE, d, new={"ended": True})


# --------------------------------------------------------------------------- records


def pubs_of(owner):
    return (
        Publication.objects.filter(archived_at__isnull=True, people__person=owner)
        .distinct()
        .order_by("-updated_at")
    )


def grants_of(owner):
    return (
        GrantSubmission.objects.filter(archived_at__isnull=True, people__person=owner)
        .select_related("grant_family")
        .distinct()
        .order_by("grant_family_id", "version_no")
    )


def needs_review(obj, period):
    """Planned/Submitted records not reviewed since this period opened (or for STALE_DAYS when no period)."""
    open_statuses = OPEN_PUB if isinstance(obj, Publication) else OPEN_GRANT
    if obj.status not in open_statuses:
        return False
    since = period.opens_at if period else timezone.now() - dt.timedelta(days=STALE_DAYS)
    return obj.confirmed_at is None or obj.confirmed_at < since


def checkin(owner, period):
    if not period:
        return None
    c, _ = OutcomeCheckin.objects.get_or_create(person=owner, reporting_period=period)
    return c


def state(owner, period):
    """What the check-in still needs for this owner and period."""
    pubs, grants = list(pubs_of(owner)), list(grants_of(owner))
    c = checkin(owner, period)
    ask_pubs = not pubs and (c is None or c.plans_publications is None)
    ask_grants = not grants and (c is None or c.plans_grants is None)
    review_pubs = [p for p in pubs if needs_review(p, period)]
    review_grants = [g for g in grants if needs_review(g, period)]
    todo = int(ask_pubs) + int(ask_grants) + len(review_pubs) + len(review_grants)
    if c and todo == 0 and not c.completed_at:
        c.completed_at = timezone.now()
        c.save(update_fields=["completed_at"])
    return {
        "pubs": pubs,
        "grants": grants,
        "checkin": c,
        "ask_pubs": ask_pubs,
        "ask_grants": ask_grants,
        "review_pubs": review_pubs,
        "review_grants": review_grants,
        "todo": todo,
        "done": todo == 0,
    }


def answer_plans(user, owner, period, kind, yes):
    c = checkin(owner, period)
    if kind == "pubs":
        c.plans_publications = yes
        c.save(update_fields=["plans_publications"])
    else:
        c.plans_grants = yes
        c.save(update_fields=["plans_grants"])
    record_event(user, AuditLog.Action.UPDATE, c, new={kind: yes})


def confirm(user, obj):
    obj.confirmed_at = timezone.now()
    obj.save(update_fields=["confirmed_at", "updated_at"])
    record_event(user, AuditLog.Action.UPDATE, obj, new={"confirmed_no_changes": True})


def _set_resources(link_model, owner_field, obj, resources, anticipated):
    link_model.objects.filter(**{owner_field: obj, "is_anticipated": anticipated}).delete()
    for r in resources:
        link_model.objects.get_or_create(
            **{owner_field: obj, "resource": r}, defaults={"is_anticipated": anticipated}
        )
        link_model.objects.filter(**{owner_field: obj, "resource": r}).update(
            is_anticipated=anticipated
        )


def _set_projects(link_model, owner_field, obj, projects):
    link_model.objects.filter(**{owner_field: obj}).exclude(project__in=projects).delete()
    for p in projects:
        link_model.objects.get_or_create(**{owner_field: obj, "project": p})


def resources_of(obj, anticipated):
    return [
        x.resource
        for x in obj.resource_links.filter(is_anticipated=anticipated).select_related("resource")
    ]


# --------------------------------------------------------------------------- publications


@transaction.atomic
def create_publication(user, owner, data, resources=(), projects=(), other_text=""):
    p = Publication.objects.create(
        title=data["title"],
        journal=data.get("journal", ""),
        publication_type=data.get("publication_type") or "journal_article",
        anticipated_submission_month=data.get("anticipated_submission_month"),
        status=PublicationStatus.PLANNED,
        resources_other_text=other_text,
        confirmed_at=timezone.now(),
        created_by=user,
    )
    PublicationPerson.objects.create(publication=p, person=owner)
    _set_resources(PublicationResource, "publication", p, resources, anticipated=True)
    _set_projects(PublicationProject, "publication", p, projects)
    PublicationStatusHistory.objects.create(
        publication=p, from_status=None, to_status=p.status, changed_by=user
    )
    record_event(user, AuditLog.Action.CREATE, p, new={"owner": owner.pk})
    return p


@transaction.atomic
def update_publication(user, p, new_status, data, resources=None, projects=None, other_text=None):
    old = p.status
    for f in (
        "title",
        "journal",
        "submission_date",
        "anticipated_publication_date",
        "publication_date",
        "pubmed_url",
        "author_display_text",
        "cnap_cited",
        "cnap_in_grant_index",
        "has_foreign_authors",
        "decline_date",
        "comments",
        "resubmission_intent",
        "anticipated_submission_month",
    ):
        if f in data:
            setattr(p, f, data[f])
    p.status = new_status
    if new_status != PublicationStatus.SUBMITTED:
        p.substatus = None
    if other_text is not None:
        p.resources_other_text = other_text
    p.confirmed_at = timezone.now()
    p.save()
    if resources is not None:
        _set_resources(
            PublicationResource,
            "publication",
            p,
            resources,
            anticipated=new_status == PublicationStatus.PLANNED,
        )
    if projects is not None:
        _set_projects(PublicationProject, "publication", p, projects)
    if new_status != old:
        PublicationStatusHistory.objects.create(
            publication=p, from_status=old, to_status=new_status, changed_by=user
        )
    record_event(
        user,
        AuditLog.Action.STATUS_CHANGE if new_status != old else AuditLog.Action.UPDATE,
        p,
        old={"status": old},
        new={"status": new_status},
    )
    new = None
    if new_status == PublicationStatus.DECLINED and data.get("resubmission_intent"):
        owner = p.people.order_by("author_order").first()
        new = create_publication(
            user,
            owner.person if owner else user.person,
            {"title": p.title, "journal": "", "publication_type": p.publication_type},
            resources=[x.resource for x in p.resource_links.all()],
            projects=[x.project for x in p.project_links.all()],
            other_text=p.resources_other_text,
        )
        new.resubmission_of = p
        new.save(update_fields=["resubmission_of"])
    return new


# --------------------------------------------------------------------------- grants


@transaction.atomic
def create_grant(
    user, owner, data, resources=(), projects=(), other_text="", family=None, role=GrantRole.PI
):
    fam = family or GrantFamily.objects.create(title=data["project_title"], created_by=user)
    g = GrantSubmission.objects.create(
        grant_family=fam,
        project_title=data["project_title"],
        funding_agency=data.get("funding_agency", ""),
        opportunity_url=data.get("opportunity_url", ""),
        mechanism=data.get("mechanism", ""),
        anticipated_submission_date=data.get("anticipated_submission_date"),
        anticipated_total=data.get("anticipated_total"),
        planned_estimated_direct=data.get("planned_estimated_direct"),
        status=GrantStatus.PLANNED,
        resources_other_text=other_text,
        confirmed_at=timezone.now(),
        created_by=user,
    )
    GrantSubmissionPerson.objects.create(
        grant_submission=g,
        person=owner,
        role=data.get("role") or role,
        is_primary_cnap_contact=True,
    )
    _set_resources(GrantSubmissionResource, "grant_submission", g, resources, anticipated=True)
    _set_projects(GrantSubmissionProject, "grant_submission", g, projects)
    GrantStatusHistory.objects.create(
        grant_submission=g, from_status=None, to_status=g.status, changed_by=user
    )
    record_event(
        user, AuditLog.Action.CREATE, g, new={"owner": owner.pk, "version": g.version_label}
    )
    return g


@transaction.atomic
def update_grant(
    user, g, new_status, data, resources=None, projects=None, other_text=None, owner=None
):
    old = g.status
    for f in (
        "project_title",
        "funding_agency",
        "opportunity_url",
        "mechanism",
        "anticipated_submission_date",
        "anticipated_total",
        "planned_estimated_direct",
        "submission_date",
        "requested_total",
        "requested_direct",
        "requested_indirect",
        "award_notice_date",
        "project_start_date",
        "project_end_date",
        "award_total",
        "award_direct",
        "award_indirect",
        "grant_number",
        "prime_or_subaward",
        "cnap_acknowledged",
        "cnap_credited_in_publications",
        "has_foreign_component",
        "decision_date",
        "decision_comments",
        "discussed_with_program_officer",
        "program_officer_name",
        "discussion_date",
        "feedback_shared_with_cnap",
        "plans_to_resubmit",
    ):
        if f in data:
            setattr(g, f, data[f])
    g.status = new_status
    if other_text is not None:
        g.resources_other_text = other_text
    g.confirmed_at = timezone.now()
    g.save()
    if "role" in data and owner:
        GrantSubmissionPerson.objects.filter(grant_submission=g, person=owner).update(
            role=data["role"]
        )
    if resources is not None:
        _set_resources(
            GrantSubmissionResource,
            "grant_submission",
            g,
            resources,
            anticipated=new_status == GrantStatus.PLANNED,
        )
    if projects is not None:
        _set_projects(GrantSubmissionProject, "grant_submission", g, projects)
    if new_status != old:
        GrantStatusHistory.objects.create(
            grant_submission=g, from_status=old, to_status=new_status, changed_by=user
        )
    record_event(
        user,
        AuditLog.Action.STATUS_CHANGE if new_status != old else AuditLog.Action.UPDATE,
        g,
        old={"status": old},
        new={"status": new_status},
    )
    new = None
    if new_status == GrantStatus.NOT_FUNDED and data.get("plans_to_resubmit"):
        lead = g.people.filter(is_primary_cnap_contact=True).first() or g.people.first()
        new = create_grant(
            user,
            lead.person if lead else user.person,
            {
                "project_title": g.project_title,
                "funding_agency": g.funding_agency,
                "mechanism": g.mechanism,
                "opportunity_url": g.opportunity_url,
                "anticipated_total": g.requested_total or g.anticipated_total,
                "planned_estimated_direct": g.requested_direct or g.planned_estimated_direct,
                "role": lead.role if lead else GrantRole.PI,
            },
            resources=[x.resource for x in g.resource_links.all()],
            projects=[x.project for x in g.project_links.all()],
            other_text=g.resources_other_text,
            family=g.grant_family,
        )
        new.resubmission_of = g
        new.save(update_fields=["resubmission_of"])
    return new


def status_dates(obj):
    """First date each status was reached, from the history (for the export's timestamp columns)."""
    hist = obj.status_history.order_by("changed_at")
    out = {}
    for h in hist:
        out.setdefault(h.to_status, h.changed_at)
    return out


def people_search(q):
    return (
        Person.objects.filter(archived_at__isnull=True)
        .filter(Q(first_name__icontains=q) | Q(last_name__icontains=q))
        .order_by("last_name")[:20]
    )


# --------------------------------------------------------------------------- presentations (no lifecycle: one entry each)


def presentations_of(owner):
    return (
        Presentation.objects.filter(archived_at__isnull=True, people__person=owner)
        .distinct()
        .order_by("-presented_on")
    )


@transaction.atomic
def save_presentation(user, owner, data, resources=(), projects=(), other_text="", obj=None):
    fields = (
        "presentation_type",
        "title",
        "event",
        "location",
        "presented_on",
        "author_display_text",
        "description",
        "cnap_cited",
    )
    created = obj is None
    obj = obj or Presentation(created_by=user)
    for f in fields:
        if f in data:
            setattr(obj, f, data[f])
    obj.resources_other_text = other_text
    obj.save()
    if created:
        PresentationPerson.objects.create(presentation=obj, person=owner, is_presenter=True)
    PresentationResource.objects.filter(presentation=obj).exclude(resource__in=resources).delete()
    for r in resources:
        PresentationResource.objects.get_or_create(presentation=obj, resource=r)
    _set_projects(PresentationProject, "presentation", obj, projects)
    record_event(
        user,
        AuditLog.Action.CREATE if created else AuditLog.Action.UPDATE,
        obj,
        new={"owner": owner.pk},
    )
    return obj


# --------------------------------------------------------------------------- when entry is open


def entry_window(now=None):
    """
    (open, reopens_on). Entry is open any time, except for OUTCOME_REOPEN_DAYS (default 7) after a reporting
    period closes while no period is open, so the Center can finish that period's numbers (decisions.md 2026-10-26).
    """
    from apps.common.enums import PeriodStatus
    from apps.reporting.models import ReportingPeriod

    now = now or timezone.now()
    if ReportingPeriod.objects.filter(status=PeriodStatus.OPEN).exists():
        return True, None
    last = ReportingPeriod.objects.filter(closed_at__isnull=False).order_by("-closed_at").first()
    days = getattr(settings, "OUTCOME_REOPEN_DAYS", 7)
    if last and last.closed_at + dt.timedelta(days=days) > now:
        return False, timezone.localtime(last.closed_at + dt.timedelta(days=days)).date()
    return True, None
