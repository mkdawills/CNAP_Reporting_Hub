"""
"Your forms are open" and reminder emails for a reporting period (sign-in plan, decisions.md 2026-10-24).

Each email lists the person's own forms and due date. People who sign in by emailed link get a personal,
single-use link; K-State people (once single sign-on is on) get the site address instead.
- open: once per person per period, to everyone with forms in the period.
- reminder: to people with forms still to do, at most once every REMINDER_GAP_DAYS days.
- overdue: after the due date, to people with forms still to do, at most once a day.
plan() shows exactly who would get what, without sending anything.

Automatic schedule (MW 2026-10-28), run daily by manage.py send_scheduled_emails while a period accepts answers
and its auto_emails is on: the "open" email on opening day; a reminder every 4 days until the due date (counted
from each person's last email); then a reminder every day after the due date until the period closes.
"""

from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from apps.accounts import signin
from apps.audit.models import AuditLog, record_event
from apps.common.enums import AssignmentStatus

from ..models import Assignment, PeriodEmail

REMINDER_GAP_DAYS = 4  # MW 2026-10-28
OVERDUE_GAP_DAYS = 1
OPEN_STATUSES = (AssignmentStatus.NOT_STARTED, AssignmentStatus.IN_PROGRESS)


class EmailError(Exception):
    pass


def _label(a):
    ctx = a.project.title if a.project_id else (a.core.name if a.core_id else "")
    return a.form_definition.name + (f" ({ctx})" if ctx else "")


def plan(period, kind):
    """Rows of {person, email, forms, with_link, skip}. skip is a reason the person won't be emailed, or ''."""
    if kind not in PeriodEmail.Kind.values:
        raise EmailError("Unknown email kind.")
    qs = (
        Assignment.objects.filter(reporting_period=period)
        .exclude(status=AssignmentStatus.EXEMPT)
        .exclude(form_definition__code="neurosync_speaker_survey")  # sent on its own when the talk ends
        .select_related("person", "form_definition", "project", "core")
        .order_by("person__last_name", "person__first_name", "form_definition__sort_order")
    )
    by = {}
    for a in qs:
        by.setdefault(a.person_id, {"person": a.person, "all": [], "open": []})
        by[a.person_id]["all"].append(a)
        if a.status in OPEN_STATUSES:
            by[a.person_id]["open"].append(a)
    sent, last = {}, {}
    for e in PeriodEmail.objects.filter(period=period).order_by("sent_at"):
        if e.kind == kind:
            sent[e.person_id] = e.sent_at
        last[e.person_id] = e.sent_at  # any email for this period counts toward the gap
    today = timezone.localdate()
    gap_days = OVERDUE_GAP_DAYS if kind == PeriodEmail.Kind.OVERDUE else REMINDER_GAP_DAYS
    rows = []
    for d in by.values():
        p = d["person"]
        forms = d["all"] if kind == "open" else d["open"]
        skip = ""
        if not p.is_active or p.archived_at:
            skip = "Not active"
        elif not p.primary_email:
            skip = "No email on file"
        elif not forms:
            skip = "Nothing left to do"
        elif kind == "open" and p.pk in sent:
            skip = f"Already sent {timezone.localtime(sent[p.pk]):%b %-d}"
        elif (
            kind != "open"
            and p.pk in last
            and (today - timezone.localtime(last[p.pk]).date()).days < gap_days
        ):
            skip = f"Emailed {timezone.localtime(last[p.pk]):%b %-d}"
        rows.append(
            {
                "person": p,
                "email": p.primary_email,
                "forms": [_label(a) for a in forms],
                "with_link": signin.may_use_link(p),
                "skip": skip,
            }
        )
    return rows


def send(period, kind, actor=None, dry_run=False):
    """Send the emails plan() says to send. Returns (sent, skipped) counts."""
    if not period.accepting_responses:
        raise EmailError("Emails can be sent only while the reporting session is open for answers.")
    rows = plan(period, kind)
    due = timezone.localtime(period.due_at)
    n = 0
    for r in rows:
        if r["skip"] or dry_run:
            continue
        p = r["person"]
        url = (
            signin.make_link(p, r["email"], purpose=f"period_{kind}", next_path="/tasks/")
            if r["with_link"]
            else f"{settings.SITE_URL}/tasks/"
        )
        body = render_to_string(
            f"email/period_{kind}.txt",
            {
                "person": p,
                "period": period,
                "forms": r["forms"],
                "due": f"{due:%A, %B} {due.day}",
                "url": url,
                "with_link": r["with_link"],
                "days": signin.LINK_DAYS,
                "site": settings.SITE_URL,
            },
        )
        subject = {
            "open": f"CNAP Reporting Hub: your {period.name} reporting session is open",
            "reminder": f"Reminder: your {period.name} CNAP forms are due {due:%B} {due.day}",
            "overdue": f"Your {period.name} CNAP forms were due {due:%B} {due.day}",
        }[kind]
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[r["email"]],
            fail_silently=False,
        )
        PeriodEmail.objects.create(
            period=period,
            person=p,
            kind=kind,
            email=r["email"],
            forms_listed=len(r["forms"]),
            with_link=r["with_link"],
            sent_by=actor,
        )
        n += 1
    skipped = sum(1 for r in rows if r["skip"])
    if not dry_run:
        record_event(
            actor, AuditLog.Action.UPDATE, period, new={f"emails_{kind}": n, "skipped": skipped}
        )
    return n, skipped


def scheduled_kind(period, today=None):
    """Which email the schedule sends today for this period ("open", "reminder", "overdue"), or None."""
    today = today or timezone.localdate()
    if not (period.accepting_responses and period.auto_emails):
        return None
    opens = timezone.localtime(period.opens_at).date()
    due = timezone.localtime(period.due_at).date()
    if today < opens:
        return None
    if today == opens:
        return PeriodEmail.Kind.OPEN
    return PeriodEmail.Kind.REMINDER if today <= due else PeriodEmail.Kind.OVERDUE


def run_schedule(period, today=None):
    """Send what the schedule says for today. Anyone who missed the opening email gets it first.

    Returns a list of (kind, sent, skipped). Safe to run more than once a day: the gaps stop repeats.
    """
    kind = scheduled_kind(period, today)
    if not kind:
        return []
    out = [(PeriodEmail.Kind.OPEN, *send(period, PeriodEmail.Kind.OPEN))]
    if kind != PeriodEmail.Kind.OPEN:
        out.append((kind, *send(period, kind)))
    return out


def schedule_preview(period):
    """Plain-language description of the automatic schedule, for the emails page."""
    opens = timezone.localtime(period.opens_at).date()
    due = timezone.localtime(period.due_at).date()
    closes = timezone.localtime(period.closes_at).date() if period.closes_at else None
    return {
        "opens": opens,
        "due": due,
        "closes": closes,
        "first_reminder": opens + timedelta(days=REMINDER_GAP_DAYS),
        "after_due": due + timedelta(days=1),
    }
