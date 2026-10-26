"""
"Your forms are open" and reminder e-mails for a reporting period (sign-in plan, decisions.md 2026-10-24).

Each e-mail lists the person's own forms and due date. People who sign in by emailed link get a personal,
single-use link; K-State people (once single sign-on is on) get the site address instead.
- open: once per person per period, to everyone with forms in the period.
- reminder: to people with forms still to do, at most once every REMINDER_GAP_DAYS days.
plan() shows exactly who would get what, without sending anything.
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

REMINDER_GAP_DAYS = 3
OPEN_STATUSES = (AssignmentStatus.NOT_STARTED, AssignmentStatus.IN_PROGRESS)


class EmailError(Exception):
    pass


def _label(a):
    ctx = a.project.title if a.project_id else (a.core.name if a.core_id else "")
    return a.form_definition.name + (f" ({ctx})" if ctx else "")


def plan(period, kind):
    """Rows of {person, email, forms, with_link, skip}. skip is a reason the person won't be e-mailed, or ''."""
    if kind not in PeriodEmail.Kind.values:
        raise EmailError("Unknown e-mail kind.")
    qs = (
        Assignment.objects.filter(reporting_period=period)
        .exclude(status=AssignmentStatus.EXEMPT)
        .select_related("person", "form_definition", "project", "core")
        .order_by("person__last_name", "person__first_name", "form_definition__sort_order")
    )
    by = {}
    for a in qs:
        by.setdefault(a.person_id, {"person": a.person, "all": [], "open": []})
        by[a.person_id]["all"].append(a)
        if a.status in OPEN_STATUSES:
            by[a.person_id]["open"].append(a)
    sent = {}
    for e in PeriodEmail.objects.filter(period=period, kind=kind).order_by("sent_at"):
        sent[e.person_id] = e.sent_at
    gap = timezone.now() - timedelta(days=REMINDER_GAP_DAYS)
    rows = []
    for d in by.values():
        p = d["person"]
        forms = d["all"] if kind == "open" else d["open"]
        skip = ""
        if not p.is_active or p.archived_at:
            skip = "Not active"
        elif not p.primary_email:
            skip = "No e-mail on file"
        elif not forms:
            skip = "Nothing left to do"
        elif kind == "open" and p.pk in sent:
            skip = f"Already sent {timezone.localtime(sent[p.pk]):%b %-d}"
        elif kind == "reminder" and p.pk in sent and sent[p.pk] > gap:
            skip = f"Reminded {timezone.localtime(sent[p.pk]):%b %-d}"
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
    """Send the e-mails plan() says to send. Returns (sent, skipped) counts."""
    if not period.accepting_responses:
        raise EmailError("E-mails can be sent only while the period is open for answers.")
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
            "email/period_open.txt" if kind == "open" else "email/period_reminder.txt",
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
        subject = (
            f"CNAP Reporting Hub: your {period.name} forms are open"
            if kind == "open"
            else f"Reminder: your {period.name} CNAP forms are due {due:%B} {due.day}"
        )
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
