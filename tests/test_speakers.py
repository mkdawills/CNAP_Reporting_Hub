"""NeuroSync Speaker Survey: sent when the talk ends (MW 2026-11-03)."""

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.accounts.models import User
from apps.reporting.models import Assignment, SpeakerTalk
from apps.reporting.services import assignments as asg
from apps.reporting.services import emails, speakers
from tests.test_nih_documents import center  # noqa: F401  (fixture)

pytestmark = pytest.mark.django_db


def _evaluator(client):
    from apps.accounts import access

    u = next(u for u in User.objects.all() if access.can_manage(u))
    client.force_login(u)
    return u


def test_add_a_new_speaker_and_the_job_sends_when_the_talk_ends(client, center):
    _evaluator(client)
    assert "NeuroSync speakers" in client.get("/manage/neurosync/").content.decode()
    later = timezone.localtime() + timedelta(hours=2)
    r = client.post(
        "/manage/neurosync/add/",
        {
            "first_name": "Pat",
            "last_name": "Visitor",
            "email": "pat.visitor@example.org",
            "institution": "Example University",
            "title": "Sleep and memory",
            "day": later.date().isoformat(),
            "ends": later.strftime("%H:%M"),
            "auto_send": "on",
        },
    )
    assert r.status_code == 302
    t = SpeakerTalk.objects.get(title="Sleep and memory")
    assert speakers.run_due() == (0, [])  # not over yet
    mail.outbox.clear()
    n, problems = speakers.run_due(now=t.ends_at + timedelta(minutes=5))
    assert (n, problems) == (1, [])
    t.refresh_from_db()
    assert t.sent_at and t.sent_to == "pat.visitor@example.org"
    a = t.assignment
    assert a.form_definition.code == "neurosync_speaker_survey" and a.reporting_period == center
    m = mail.outbox[-1]
    assert m.to == ["pat.visitor@example.org"] and "Thank you for speaking at NeuroSync" in m.subject
    assert "/accounts/link/" in m.body and '"Sleep and memory"' in m.body
    assert speakers.run_due(now=t.ends_at + timedelta(minutes=15)) == (0, [])  # never twice
    # not part of the period e-mails, and never assigned by a rule
    for row in emails.plan(center, "open"):
        assert "NeuroSync Speaker Survey" not in row["forms"]
    assert a.form_definition_id not in {p.form_definition_id for p in asg.plan(center)}


def test_send_by_hand_and_the_form_shows_the_talk(client, center):
    _evaluator(client)
    from apps.people.models import Person

    p = Person.objects.filter(emails__isnull=False, is_active=True).first()
    t = SpeakerTalk.objects.create(
        speaker=p, title="Hippocampal maps", ends_at=timezone.now() - timedelta(minutes=1), auto_send=False
    )
    assert speakers.run_due() == (0, [])  # hand-sent only
    r = client.post(f"/manage/neurosync/{t.pk}/send/")
    assert r.status_code == 302
    t.refresh_from_db()
    assert Assignment.objects.filter(pk=t.assignment_id).exists()
    u = User.objects.filter(person=p).first()
    if u:
        client.force_login(u)
        page = client.get(f"/tasks/{t.assignment_id}/").content.decode()
        assert "Hippocampal maps" in page and "Please answer by" in page
        assert "This reporting period runs" not in page


def test_old_talks_are_not_sent_late(center):
    from apps.people.models import Person

    p = Person.objects.filter(emails__isnull=False, is_active=True).first()
    SpeakerTalk.objects.create(speaker=p, title="Old", ends_at=timezone.now() - timedelta(days=5))
    assert speakers.run_due() == (0, [])
