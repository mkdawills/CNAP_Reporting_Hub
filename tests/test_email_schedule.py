"""Automatic period e-mails (MW 2026-10-28): opening day, every 4 days to the due date, then daily."""

from datetime import timedelta

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from apps.reporting.models import PeriodEmail, ReportingPeriod
from apps.reporting.services import assignments as asg
from apps.reporting.services import emails


@pytest.fixture
def center(db):
    call_command("seed", "--fictional", verbosity=0)
    p = ReportingPeriod.objects.get(status="open")
    asg.generate(p)
    return p


def test_which_email_each_day(center):
    opens = timezone.localtime(center.opens_at).date()
    due = timezone.localtime(center.due_at).date()
    assert emails.scheduled_kind(center, opens - timedelta(days=1)) is None
    assert emails.scheduled_kind(center, opens) == "open"
    assert emails.scheduled_kind(center, opens + timedelta(days=1)) == "reminder"
    assert emails.scheduled_kind(center, due) == "reminder"
    assert emails.scheduled_kind(center, due + timedelta(days=1)) == "overdue"
    center.auto_emails = False
    assert emails.scheduled_kind(center, opens) is None


def _age(days):
    PeriodEmail.objects.update(sent_at=timezone.now() - timedelta(days=days))


def test_reminders_every_four_days_then_daily(center):
    today = timezone.localdate()
    # opening day: everyone with forms gets "open"
    center.opens_at = timezone.now()
    center.save()
    out = emails.run_schedule(center, today)
    assert out[0][0] == "open" and out[0][1] > 0
    n_open = out[0][1]
    # three days later: nothing new (reminders wait 4 days from the last e-mail)
    _age(3)
    center.opens_at = timezone.now() - timedelta(days=3)
    center.save()
    assert [k for k, n, _ in emails.run_schedule(center, today) if n] == []
    # four days after: a reminder to those with forms left, only once
    _age(4)
    sent = dict((k, n) for k, n, _ in emails.run_schedule(center, today))
    assert 0 < sent["reminder"] <= n_open
    assert dict((k, n) for k, n, _ in emails.run_schedule(center, today))["reminder"] == 0
    # after the due date: every day
    center.due_at = timezone.now() - timedelta(days=1)
    center.closes_at = timezone.now() + timedelta(days=10)
    center.save()
    assert emails.scheduled_kind(center, today) == "overdue"
    _age(1)
    sent = dict((k, n) for k, n, _ in emails.run_schedule(center, today))
    assert sent["overdue"] > 0
    assert dict((k, n) for k, n, _ in emails.run_schedule(center, today))["overdue"] == 0
    msg = [m for m in mail.outbox if "was due" in m.subject][-1]
    assert "still open" in msg.body


def test_paused_sends_nothing_and_command_runs(center, capsys):
    center.auto_emails = False
    center.save()
    assert emails.run_schedule(center) == []
    call_command("send_scheduled_emails", "--dry-run")
    assert center.short_label in capsys.readouterr().out
