"""
February check on Current and Pending (Other) Support (MW 2026-10-28).

NIH documents are collected in the Fall period; the RPPR goes in about April 1. Current and Pending changes most
in between (new submissions and awards), so in February everyone who turned in fall documents is asked one
question: has it changed? "No" takes one click; "Yes" asks for the new certified PDF.

Schedule, run daily by send_scheduled_emails: ask on February 1; remind every 4 days until February 15; then
daily until March 1. Dates can be changed in settings (CP_CHECK_ASK, CP_CHECK_DUE, CP_CHECK_STOP as "MM-DD").
"""

import datetime as dt

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.accounts import signin
from apps.audit.models import AuditLog, record_event
from apps.common.enums import AssignmentStatus
from apps.reporting.models import Assignment, CurrentPendingCheck
from apps.reporting.services import responses as rs

from . import rppr, sciencv

GAP_DAYS = 4


def _md(name, default):
    m, d = (getattr(settings, name, default) or default).split("-")
    return int(m), int(d)


def dates(gy):
    """(ask, due, stop) for budget year `gy`: in its second calendar year (Feb 2027 for Year 10)."""
    y = 2017 + gy
    return tuple(
        dt.date(y, *_md(n, d))
        for n, d in (
            ("CP_CHECK_ASK", "02-01"),
            ("CP_CHECK_DUE", "02-15"),
            ("CP_CHECK_STOP", "03-01"),
        )
    )


def fall_tasks(gy):
    """Fall NIH documents tasks turned in for budget year `gy`, with a Current and Pending on file."""
    out = []
    for a in Assignment.objects.filter(
        form_definition__code="nih_documents",
        reporting_period__grant_year=gy,
        status=AssignmentStatus.SUBMITTED,
        person__is_active=True,
        person__archived_at__isnull=True,
    ).select_related("person", "form_version", "reporting_period"):
        if current_file(a):
            out.append(a)
    return out


def current_file(a):
    """The Current and Pending from the fall task itself."""
    from apps.forms_engine.runtime import FormSchema

    _, _, files = rs.answers_of(rs.current_response(a), FormSchema(a.form_version))
    return files.get("current_pending")


def latest_file(a):
    """The newest Current and Pending: the February update if there is one, else the fall upload."""
    c = getattr(a, "cp_check", None)
    if c and c.changed and c.file_id:
        return c.file
    return current_file(a)


def _send(c, kind, due):
    p = c.assignment.person
    email = p.primary_email
    if not email:
        return False
    path = f"/tasks/current-pending/{c.pk}/"
    url = (
        signin.make_link(p, email, purpose="cp_check", next_path=path)
        if signin.may_use_link(p)
        else f"{settings.SITE_URL}{path}"
    )
    fall = timezone.localtime(c.assignment.submitted_at) if c.assignment.submitted_at else None
    body = render_to_string(
        "email/cp_check.txt",
        {
            "person": p,
            "kind": kind,
            "due": f"{due:%A, %B} {due.day}",
            "evaluator_email": settings.EVALUATOR_EMAIL,
            "fall": f"{fall:%B} {fall.day}" if fall else "the fall",
            "rppr_due": f"{rppr_due(c.assignment.reporting_period.grant_year):%B} 1",
            "url": url,
            "with_link": signin.may_use_link(p),
            "days": signin.LINK_DAYS,
            "site": settings.SITE_URL,
        },
    )
    subject = (
        "CNAP: has your Current and Pending changed since the fall?"
        if kind == "ask"
        else f"Reminder: has your Current and Pending changed? (due {due:%B} {due.day})"
    )
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
    now = timezone.now()
    c.asked_at = c.asked_at or now
    c.last_emailed_at = now
    c.emails_sent += 1
    c.save(update_fields=["asked_at", "last_emailed_at", "emails_sent", "updated_at"])
    return True


def run(today=None):
    """Send today's February-check emails. Returns the number sent. Safe to run more than once a day."""
    if not getattr(settings, "CP_CHECK_ENABLED", True):
        return 0
    today = today or timezone.localdate()
    gy = rppr.current_year(today)
    ask, due, stop = dates(gy)
    if not (ask <= today < stop):
        return 0
    n = 0
    for a in fall_tasks(gy):
        c, _ = CurrentPendingCheck.objects.get_or_create(assignment=a)
        if c.answered_at:
            continue
        last = timezone.localtime(c.last_emailed_at).date() if c.last_emailed_at else None
        if last is None:
            n += _send(c, "ask", due)
        elif today <= due and (today - last).days >= GAP_DAYS:
            n += _send(c, "reminder", due)
        elif today > due and last < today:
            n += _send(c, "reminder", due)
    return n


def rppr_due(gy):
    """When the Center's progress report is due to NIH: 60 days before the June 1 budget start, so April 1
    of the budget year's second calendar year (MW 2026-11-02)."""
    return dt.date(2017 + gy, 4, 1)


def with_dates(c):
    """Attach .due (answer by) and .rppr_due (the report's due date) for pages and emails."""
    if c is not None:
        gy = c.assignment.reporting_period.grant_year
        c.due = dates(gy)[1]
        c.rppr_due = rppr_due(gy)
        c.prev_file = current_file(
            c.assignment
        )  # the one they turned in, to look over before answering
    return c


def pending_for(person, today=None):
    """This person's unanswered February check, if one has been asked."""
    return with_dates(
        CurrentPendingCheck.objects.filter(
            assignment__person=person, asked_at__isnull=False, answered_at__isnull=True
        )
        .select_related("assignment__reporting_period")
        .first()
    )


class CheckError(Exception):
    pass


@transaction.atomic
def answer(c, user, *, changed, upload=None):
    if c.assignment.person_id != getattr(user, "person_id", None):
        raise CheckError("Only the person asked can answer.")
    if changed:
        if not upload:
            raise CheckError("Please choose the new PDF from SciENcv.")
        q = c.assignment.form_version.sections.get(code="documents").questions.get(
            code="current_pending"
        )
        try:
            f = rs.store_upload(user, upload, q)
        except rs.UploadError as exc:
            raise CheckError(str(exc)) from exc
        msg = sciencv.message("current_pending", sciencv.read_file(f, "current_pending"))
        if msg:
            raise CheckError(msg)
        c.file = f
    c.changed = bool(changed)
    c.answered_at = timezone.now()
    c.save(update_fields=["changed", "file", "answered_at", "updated_at"])
    record_event(
        user,
        AuditLog.Action.UPDATE,
        c.assignment,
        new={"cp_check": "changed" if changed else "no change"},
    )
    return c
