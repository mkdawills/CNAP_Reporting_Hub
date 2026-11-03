"""
NeuroSync speakers (MW 2026-11-03): "it would be nice if I could send this survey to speakers immediately upon
their presentation concluding."

The evaluator lists each talk with its end time. When the talk ends, the speaker gets the NeuroSync Speaker
Survey by e-mail: automatically (the every-10-minutes job) or by hand from the NeuroSync speakers page. External
speakers sign in by emailed link; K-State speakers with their eID.
"""

from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.accounts import signin
from apps.audit.models import AuditLog, record_event
from apps.common.enums import AssignmentSource, PeriodStatus
from apps.forms_engine.models import FormDefinition

from ..models import Assignment, ReportingPeriod, SpeakerTalk

FORM_CODE = "neurosync_speaker_survey"
ANSWER_DAYS = 14  # the speaker has two weeks to answer
LATE_LIMIT = timedelta(days=3)  # the job never sends for a talk that ended more than 3 days ago


class SpeakerError(Exception):
    pass


def period_for(when):
    """The open period that takes answers for a talk ending at `when` (the latest one that has opened)."""
    rows = ReportingPeriod.objects.filter(status=PeriodStatus.OPEN).order_by("-opens_at")
    for p in rows:
        if p.accepting_responses and p.opens_at <= when:
            return p
    for p in rows:
        if p.accepting_responses:
            return p
    return None


@transaction.atomic
def send(talk, actor=None):
    """Create the speaker's survey task (once) and e-mail it. Returns the e-mail address used."""
    p = talk.speaker
    if not p.is_active or p.archived_at:
        raise SpeakerError(f"{p} is not active.")
    email = p.primary_email
    if not email:
        raise SpeakerError(f"{p} has no e-mail address on file.")
    fd = FormDefinition.objects.filter(code=FORM_CODE).first()
    version = fd.active_version if fd else None
    if not version:
        raise SpeakerError("The NeuroSync Speaker Survey isn’t loaded yet.")
    period = talk.assignment.reporting_period if talk.assignment_id else period_for(talk.ends_at)
    if not period:
        raise SpeakerError("No reporting period is open for answers, so the survey can’t be sent yet.")
    a = talk.assignment
    if a is None:
        a = Assignment.objects.filter(
            person=p, form_definition=fd, reporting_period=period, project=None, core=None
        ).first()
    if a is None:
        a = Assignment.objects.create(
            person=p,
            form_version=version,
            form_definition=fd,
            context_kind="none",
            reporting_period=period,
            source=AssignmentSource.MANUAL,
            due_at=max(talk.ends_at, timezone.now()) + timedelta(days=ANSWER_DAYS),
        )
    with_link = signin.may_use_link(p)
    path = f"/tasks/{a.pk}/"
    url = (
        signin.make_link(p, email, purpose="speaker_survey", next_path=path)
        if with_link
        else f"{settings.SITE_URL}{path}"
    )
    due = timezone.localtime(a.due_at)
    send_mail(
        subject="Thank you for speaking at NeuroSync: a 5-minute survey",
        message=render_to_string(
            "email/speaker_survey.txt",
            {
                "person": p,
                "talk": talk,
                "url": url,
                "with_link": with_link,
                "days": signin.LINK_DAYS,
                "site": settings.SITE_URL,
                "due": f"{due:%A, %B} {due.day}",
            },
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )
    talk.assignment = a
    talk.sent_at = timezone.now()
    talk.sent_to = email
    talk.save(update_fields=["assignment", "sent_at", "sent_to", "updated_at"])
    record_event(actor, AuditLog.Action.UPDATE, talk, new={"speaker_survey_sent": email})
    return email


def due_talks(now=None):
    now = now or timezone.now()
    return SpeakerTalk.objects.filter(
        auto_send=True, sent_at__isnull=True, ends_at__lte=now, ends_at__gte=now - LATE_LIMIT
    ).select_related("speaker")


def run_due(now=None):
    """Send every survey whose talk has just ended. Returns (sent, problems)."""
    sent, problems = 0, []
    for t in due_talks(now):
        try:
            send(t)
        except SpeakerError as exc:
            problems.append(f"{t}: {exc}")
        else:
            sent += 1
    return sent, problems
