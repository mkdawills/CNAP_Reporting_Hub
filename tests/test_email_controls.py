"""Email controls (MW 2026-11-08): how often, skip or add a day, and each email's wording."""

from datetime import timedelta

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import User
from apps.reporting.models import ReportingPeriod
from apps.reporting.services import assignments as asg
from apps.reporting.services import emails
from apps.reporting.services.timeline import period_timeline


@pytest.fixture
def center(db):
    call_command("seed", "--fictional", verbosity=0)
    p = ReportingPeriod.objects.get(status="open")
    asg.generate(p)
    return p


def _post(client, p, **data):
    client.force_login(User.objects.get(username="mwills"))
    return client.post(f"/manage/periods/{p.pk}/emails/plan/", data)


def test_how_often(client, center):
    _post(client, center, action="every", reminder_every="7", overdue_every="2")
    center.refresh_from_db()
    assert emails.every(center, "reminder") == 7 and emails.every(center, "overdue") == 2
    _post(client, center, action="every", reminder_every="30", overdue_every="2")
    center.refresh_from_db()
    assert emails.every(center, "reminder") == 7  # out of range: refused


def test_skip_and_add_a_day(client, center):
    center.opens_at = timezone.now() - timedelta(days=10)
    center.due_at = timezone.now() + timedelta(days=10)
    center.save()
    day = timezone.localdate() + timedelta(days=3)
    _post(client, center, action="skip", date=day.isoformat())
    center.refresh_from_db()
    assert emails.scheduled_kind(center, day) is None
    _post(client, center, action="unskip", date=day.isoformat())
    center.refresh_from_db()
    assert emails.scheduled_kind(center, day) == "reminder"
    _post(client, center, action="add", date=day.isoformat())
    center.refresh_from_db()
    assert emails.added_days(center) == {day.isoformat(): "reminder"}
    labels = [e["label"] for e in period_timeline(center)["events"]]
    assert "Reminder email, added" in labels
    # An added day goes to everyone with something left, whatever their last email.
    emails.send(center, "open")
    from apps.reporting.models import PeriodEmail

    PeriodEmail.objects.update(sent_at=timezone.now() - timedelta(days=2))  # well inside the 4-day gap
    out = dict((k, n) for k, n, _ in emails.run_schedule(center, day))
    assert out["reminder"] > 0
    # The past and opening day can't be changed.
    _post(client, center, action="skip", date=timezone.localdate().isoformat())
    center.refresh_from_db()
    assert timezone.localdate().isoformat() not in emails.skipped_days(center)


def test_wording(client, center):
    _post(client, center, action="wording", kind="reminder", subject="A friendly note: {session} is due {due}", opening="Hello from the CNAP team. {session} is due {due}.", closing="Questions? Reply to this email.", signoff="With thanks,\nMorgan")
    center.refresh_from_db()
    text = emails.preview(center, "reminder")
    assert text.startswith(f"Subject: A friendly note: {center.name} is due ")
    assert f"Hello from the CNAP team. {center.name} is due " in text
    assert "Questions? Reply to this email." in text and text.rstrip().endswith("With thanks,\nMorgan")
    assert "{session}" not in text and "{due}" not in text
    assert "Questions? Reply to this email." in emails.preview(center, "reminder", html=True)["html"]
    emails.send(center, "reminder", gap=0)
    assert mail.outbox and mail.outbox[-1].subject.startswith("A friendly note:")
    _post(client, center, action="wording_reset", kind="reminder")
    center.refresh_from_db()
    assert not emails.wording(center, "reminder")["custom"]


def test_only_the_evaluator_changes_emails(client, center):
    client.force_login(User.objects.get(username="okafor"))
    assert client.post(f"/manage/periods/{center.pk}/emails/plan/", {"action": "every", "reminder_every": "2", "overdue_every": "1"}).status_code == 403
