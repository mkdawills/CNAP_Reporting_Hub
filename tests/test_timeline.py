"""The full timeline (MW 2026-11-06): exact dates, read-only, and only in the redesign."""

import pytest
from django.core.management import call_command
from django.test import override_settings

from apps.accounts.models import User
from apps.reporting.models import PeriodEmail, ReportingPeriod
from apps.reporting.services.emails import REMINDER_GAP_DAYS
from apps.reporting.services.timeline import period_timeline


@pytest.fixture
def demo(db):
    call_command("seed", "--fictional", verbosity=0)
    return ReportingPeriod.objects.get(status="open")


def test_every_reminder_date_and_the_due_date_are_listed(demo):
    from datetime import timedelta

    from django.utils import timezone

    t = period_timeline(demo)
    opens = timezone.localtime(demo.opens_at).date()
    due = timezone.localtime(demo.due_at).date()
    reminders = [e["date"] for e in t["events"] if e["label"] == "Reminder email"]
    d, expected = opens + timedelta(days=REMINDER_GAP_DAYS), []
    while d <= due:
        expected.append(d)
        d += timedelta(days=REMINDER_GAP_DAYS)
    assert reminders == expected
    assert any(e["label"] == "Due" and e["date"] == due for e in t["events"])
    assert sum(1 for e in t["events"] if e["kind"] == "now") == 1


def test_the_timeline_writes_nothing(demo):
    before = PeriodEmail.objects.count()
    period_timeline(demo)
    assert PeriodEmail.objects.count() == before


@pytest.mark.parametrize("path", ["/manage/", "/manage/periods/", "/manage/dashboard/"])
def test_only_in_the_redesign(client, demo, path):
    client.force_login(User.objects.get(username="mwills"))
    assert "Show the full timeline" not in client.get(path).content.decode()
    with override_settings(UI_PROTOTYPE=True):
        assert "Show the full timeline" in client.get(path).content.decode()
