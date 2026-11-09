"""Roster check before each reporting session (MW 2026-11-06)."""

from datetime import timedelta

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import User
from apps.reporting.models import ReportingPeriod, RosterSuggestion
from apps.reporting.services import roster_check as rc


@pytest.fixture
def spring(db):
    call_command("seed", "--fictional", verbosity=0)
    p = ReportingPeriod.objects.get(status="draft")
    p.opens_at = timezone.now() + timedelta(days=20)
    p.due_at = p.opens_at + timedelta(days=30)
    p.save()
    return p


def test_daily_job_sends_three_weeks_out_to_leaders_and_directors(spring):
    assert rc.run() > 0
    links = list(spring.roster_links.select_related("person"))
    assert links and all(l.sent_at for l in links)
    codes = {"project_leader", "pilot_awardee", "core_director"}
    for l in links:
        assert l.person.relationships.filter(relationship_type__code__in=codes).exists()
    assert mail.outbox and "/roster-check/" in mail.outbox[0].body
    n = len(mail.outbox)
    rc.run()
    assert len(mail.outbox) == n  # once only


def test_page_shows_names_and_roles_never_emails_and_takes_suggestions(client, spring):
    rc.send(spring)
    link = spring.roster_links.select_related("person").first()
    html = client.get(f"/roster-check/{link.token}/").content.decode()
    assert "No changes needed" in html
    near, others = rc.roster(link)
    for row in near + others:
        assert row["person"].full_name in html
        if row["person"].primary_email:
            assert row["person"].primary_email not in html
    target = (near + others)[0]["person"]
    client.post(f"/roster-check/{link.token}/", {"action": "left", "person": target.pk, "note": "Graduated", "from_name": "A student"})
    client.post(f"/roster-check/{link.token}/", {"action": "new", "name": "Jordan Sample", "role": "Graduate student"})
    s = list(link.suggestions.all())
    assert [x.kind for x in s] == ["left", "new"] and s[0].from_name == "A student"
    link.refresh_from_db()
    assert link.replied_at
    # Nothing on the roster changed.
    assert target.relationships.filter(effective_to__isnull=True).exists()


def test_link_stops_when_the_session_opens_and_bad_tokens_fail(client, spring):
    rc.send(spring)
    link = spring.roster_links.first()
    assert client.get("/roster-check/not-a-real-token/").status_code == 404
    spring.opens_at = timezone.now() - timedelta(minutes=1)
    spring.save()
    assert client.get(f"/roster-check/{link.token}/").status_code == 410


def test_evaluator_reviews_and_launch_shows_who_is_out(client, spring):
    rc.send(spring)
    link = spring.roster_links.first()
    s = rc.suggest(link, RosterSuggestion.Kind.NEW, name="Jordan Sample")
    client.force_login(User.objects.get(username="mwills"))
    page = client.get(f"/manage/periods/{spring.pk}/roster-check/").content.decode()
    assert "Jordan Sample" in page and "Not yet replied" in page
    client.post(f"/manage/periods/{spring.pk}/roster-check/do/", {"action": "done", "id": s.pk})
    s.refresh_from_db()
    assert s.status == "done"


def test_members_cannot_open_the_evaluator_page(client, spring):
    client.force_login(User.objects.get(username="okafor"))
    assert client.get(f"/manage/periods/{spring.pk}/roster-check/").status_code in (302, 403)
