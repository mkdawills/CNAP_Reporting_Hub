"""
Reminder e-mails for stale publications and grants (Publication flow 11 / Grant flow: "reminder notifications
for stale records").

A record is stale when it is Planned or Submitted and nobody has reviewed it ("Confirm no changes" or an update)
for OUTCOME_STALE_DAYS days. Each person with stale records gets one e-mail listing them, copied to anyone who
enters for them, at most once every OUTCOME_REMINDER_EVERY_DAYS days. Run daily: manage.py send_outcome_reminders.
"""

import datetime as dt

from django.conf import settings
from django.core.mail import EmailMessage
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone

from apps.audit.models import AuditLog, record_event
from apps.common.enums import GrantStatus, PublicationStatus

from .models import GrantSubmission, OutcomeDelegate, OutcomeReminder, Publication


def _stale_q(cutoff):
    return Q(confirmed_at__isnull=True, updated_at__lt=cutoff) | Q(confirmed_at__lt=cutoff)


def due(now=None):
    """[(person, [records], [cc emails])] for everyone a reminder should go to now."""
    now = now or timezone.now()
    cutoff = now - dt.timedelta(days=settings.OUTCOME_STALE_DAYS)
    quiet = now - dt.timedelta(days=settings.OUTCOME_REMINDER_EVERY_DAYS)
    by_person = {}
    pubs = (
        Publication.objects.filter(
            archived_at__isnull=True,
            status__in=[PublicationStatus.PLANNED, PublicationStatus.SUBMITTED],
        )
        .filter(_stale_q(cutoff))
        .prefetch_related("people__person")
    )
    grants = (
        GrantSubmission.objects.filter(
            archived_at__isnull=True, status__in=[GrantStatus.PLANNED, GrantStatus.SUBMITTED]
        )
        .filter(_stale_q(cutoff))
        .prefetch_related("people__person")
    )
    for p in pubs:
        link = sorted(p.people.all(), key=lambda x: x.author_order)[:1]
        if link:
            by_person.setdefault(link[0].person, []).append(("Publication", p, p.title))
    for g in grants:
        lead = next((x for x in g.people.all() if x.is_primary_cnap_contact), None) or next(
            iter(g.people.all()), None
        )
        if lead:
            by_person.setdefault(lead.person, []).append(
                ("Grant proposal", g, f"{g.project_title} ({g.version_label})")
            )
    out = []
    for person, recs in sorted(by_person.items(), key=lambda t: (t[0].last_name, t[0].first_name)):
        if not person.is_active or person.archived_at:
            continue
        if OutcomeReminder.objects.filter(person=person, sent_at__gte=quiet).exists():
            continue
        cc = [
            d.delegate.primary_email
            for d in OutcomeDelegate.objects.filter(
                owner=person, ended_at__isnull=True
            ).select_related("delegate")
            if d.delegate.primary_email
        ]
        out.append((person, recs, cc))
    return out


def send(actor=None, now=None, dry_run=False):
    """Send every reminder that is due. Returns [(person, n_records, sent_to)]."""
    sent = []
    for person, recs, cc in due(now):
        to = person.primary_email
        if not to:
            continue
        lines = [
            {
                "kind": k,
                "title": t,
                "status": o.get_status_display(),
                "last": o.confirmed_at or o.updated_at,
            }
            for k, o, t in recs
        ]
        body = render_to_string(
            "email/outcome_reminder.txt",
            {
                "person": person,
                "records": lines,
                "url": f"{settings.SITE_URL}/outcomes/?for={person.pk}",
                "days": settings.OUTCOME_STALE_DAYS,
            },
        )
        if not dry_run:
            EmailMessage(
                subject=f"Please update {len(lines)} publication{'s' if len(lines) != 1 else ''} or grant{'s' if len(lines) != 1 else ''} in the CNAP Reporting Hub"
                if len(lines) > 1
                else "Please update a publication or grant in the CNAP Reporting Hub",
                body=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[to],
                cc=cc,
            ).send(fail_silently=False)
            r = OutcomeReminder.objects.create(
                person=person,
                sent_to=", ".join([to, *cc]),
                records=[
                    {
                        "kind": k,
                        "id": o.pk,
                        "title": t,
                        "status": o.status,
                        "last_reviewed": (o.confirmed_at or o.updated_at).isoformat(),
                    }
                    for k, o, t in recs
                ],
            )
            record_event(
                actor, AuditLog.Action.CREATE, r, new={"records": len(recs), "to": r.sent_to}
            )
        sent.append((person, len(lines), ", ".join([to, *cc])))
    return sent
