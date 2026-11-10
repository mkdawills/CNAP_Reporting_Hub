"""The "As of" view (MW 2026-11-05)."""

import datetime as dt

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.outcomes import asof, snapshot
from apps.outcomes.models import Publication


@pytest.fixture
def demo(db):
    call_command("seed", "--fictional", verbosity=0)


def test_parse_refuses_future_and_nonsense():
    today = timezone.localdate()
    assert asof.parse(today.isoformat()) == today
    assert asof.parse((today + dt.timedelta(days=1)).isoformat()) is None
    assert asof.parse("not a date") is None


def test_person_given_dates_decide_the_status(demo):
    p = Publication.objects.filter(status="published", publication_date__isnull=False).first()
    before = p.publication_date - dt.timedelta(days=1)
    assert asof.status_on("pub", p, p.publication_date) == "published"
    assert asof.status_on("pub", p, before) != "published"


def test_center_totals_shrink_to_the_day(demo):
    p = (
        Publication.objects.filter(status="published", publication_date__isnull=False)
        .order_by("-publication_date")
        .first()
    )
    gy = snapshot.current_year(p.publication_date)
    full = len(snapshot.products(gy)["papers"])
    earlier = len(snapshot.products(gy, p.publication_date - dt.timedelta(days=1))["papers"])
    assert earlier < full


@override_settings(UI_PROTOTYPE=True)
def test_pages_render_as_of(client, demo):
    for username, url in (
        ("brandt", "/outcomes/?asof=2025-12-31"),
        ("okafor", "/results/?view=products&asof=2026-05-31"),
    ):
        client.force_login(User.objects.get(username=username))
        s = client.session
        s["ui_view"] = "after"
        s.save()
        html = client.get(url).content.decode()
        assert "As of" in html and "Back to today" in html
