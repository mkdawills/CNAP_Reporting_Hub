"""Roster check before each reporting session (MW 2026-11-06, Batch 4).

Three weeks before a reporting session opens, each project leader and core director gets an email
with a personal link. The link shows the whole roster, names and roles only, with the people
connected to the reader listed first. Anyone holding the link (the person, or a student the person
forwards it to) can suggest changes: someone who has left, someone new, or a new core user. Each
suggestion comes to the evaluator to handle; nothing on the roster changes until the evaluator acts.
The link stops working when the reporting session opens.
"""

import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone

from apps.audit.models import AuditLog, record_event
from apps.common.enums import PeriodStatus
from apps.people.models import Person, PersonRelationship

from ..models import RosterCheckLink, RosterSuggestion

LEAD_DAYS = 21
ASKED = ("project_leader", "pilot_awardee", "core_director")


def _current(on):
    return Q(effective_from__lte=on) & (Q(effective_to__isnull=True) | Q(effective_to__gte=on))


def send_day(period):
    return timezone.localtime(period.opens_at).date() - timedelta(days=LEAD_DAYS)


def is_open(link):
    p = link.reporting_period
    return p.status == PeriodStatus.DRAFT and timezone.now() < p.opens_at


def recipients():
    today = timezone.localdate()
    ids = (
        PersonRelationship.objects.filter(_current(today), relationship_type__code__in=ASKED)
        .filter(person__is_active=True, person__archived_at__isnull=True)
        .values_list("person_id", flat=True)
    )
    return (
        Person.objects.filter(pk__in=set(ids))
        .prefetch_related("emails")
        .order_by("last_name", "first_name")
    )


def ensure_links(period):
    have = set(period.roster_links.values_list("person_id", flat=True))
    for person in recipients():
        if person.pk not in have:
            RosterCheckLink.objects.create(
                reporting_period=period, person=person, token=secrets.token_urlsafe(32)
            )
    return period.roster_links.select_related("person").order_by(
        "person__last_name", "person__first_name"
    )


def _email_of(person):
    return person.primary_email or ""


def send(period, actor=None):
    """Email every link not yet sent. Returns (sent, without an email address)."""
    sent = missing = 0
    closes = timezone.localtime(period.opens_at)
    for link in ensure_links(period):
        if link.sent_at:
            continue
        to = _email_of(link.person)
        if not to:
            missing += 1
            continue
        ctx = {
            "person": link.person,
            "period": period,
            "url": f"{settings.SITE_URL}/roster-check/{link.token}/",
            "closes": f"{closes:%A, %B} {closes.day}",
        }
        send_mail(
            subject=f"Help bring the CNAP roster up to date before {period.name} opens",
            message=render_to_string("email/roster_check.txt", ctx),
            html_message=render_to_string("email/roster_check.html", ctx),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to],
            fail_silently=False,
        )
        link.sent_at = timezone.now()
        link.save(update_fields=["sent_at", "updated_at"])
        sent += 1
    if actor and sent:
        record_event(actor, AuditLog.Action.UPDATE, period, new={"roster_check_sent": sent})
    return sent, missing


def run(today=None):
    """For the daily job: send the roster check for any draft reporting session three weeks out."""
    from ..models import ReportingPeriod

    today = today or timezone.localdate()
    n = 0
    for p in ReportingPeriod.objects.filter(status=PeriodStatus.DRAFT, opens_at__gt=timezone.now()):
        if send_day(p) <= today:
            n += send(p)[0]
    return n


def roster(link):
    """Everyone on the roster today, names and roles only. People who share a project or core with the
    link's owner come first. Never email addresses."""
    today = timezone.localdate()
    rels = list(
        PersonRelationship.objects.filter(_current(today))
        .filter(person__is_active=True, person__archived_at__isnull=True)
        .select_related("person", "relationship_type", "project", "core")
        .order_by("person__last_name", "person__first_name")
    )
    mine = [r for r in rels if r.person_id == link.person_id]
    projects = {r.project_id for r in mine if r.project_id}
    cores = {r.core_id for r in mine if r.core_id}
    people = {}
    for r in rels:
        row = people.setdefault(r.person_id, {"person": r.person, "roles": [], "near": False})
        where = r.project.title if r.project_id else (r.core.name if r.core_id else "")
        role = r.relationship_type.name.split(" (")[0]
        row["roles"].append(f"{role}, {where}" if where else role)
        if (r.project_id and r.project_id in projects) or (r.core_id and r.core_id in cores):
            row["near"] = True
    rows = sorted(
        people.values(),
        key=lambda x: (
            x["person"].pk == link.person_id,
            x["person"].last_name.lower(),
            x["person"].first_name.lower(),
        ),
    )
    rows = [r for r in rows if r["person"].pk != link.person_id]
    return [r for r in rows if r["near"]], [r for r in rows if not r["near"]]


def suggest(link, kind, **data):
    s = RosterSuggestion.objects.create(link=link, kind=kind, **data)
    if not link.replied_at:
        link.replied_at = timezone.now()
    link.no_changes = False
    link.save(update_fields=["replied_at", "no_changes", "updated_at"])
    return s


def mark_no_changes(link):
    link.replied_at = link.replied_at or timezone.now()
    link.no_changes = not link.suggestions.exists()
    link.save(update_fields=["replied_at", "no_changes", "updated_at"])


def decide(user, suggestion, status):
    suggestion.status = status
    suggestion.decided_by = user
    suggestion.decided_at = timezone.now()
    suggestion.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
    record_event(
        user,
        AuditLog.Action.UPDATE,
        suggestion.link.reporting_period,
        new={"roster_suggestion": suggestion.pk, "status": status},
    )


def summary(period):
    links = list(
        period.roster_links.select_related("person")
        .prefetch_related("suggestions")
        .order_by("person__last_name", "person__first_name")
    )
    return {
        "links": links,
        "sent": sum(1 for x in links if x.sent_at),
        "replied": sum(1 for x in links if x.replied_at),
        "waiting": [x for x in links if x.sent_at and not x.replied_at],
        "pending": RosterSuggestion.objects.filter(
            link__reporting_period=period, status=RosterSuggestion.Status.PENDING
        ).count(),
        "send_day": send_day(period),
    }
