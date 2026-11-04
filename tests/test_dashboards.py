"""Product dashboards (MW 2026-11-03): live recreations of MW's dashboard documents."""

import pytest
from django.core.management import call_command

from apps.accounts.models import User


@pytest.fixture
def center(db):
    call_command("seed", "--fictional", verbosity=0)


def _login(client, username):
    client.force_login(User.objects.get(username=username))


@pytest.mark.parametrize("kind", ["pubs", "talks", "grants"])
def test_dashboard_renders(client, center, kind):
    _login(client, "mwills")
    r = client.get(f"/manage/outcomes/dashboard/{kind}/")
    assert r.status_code == 200
    page = r.content.decode()
    assert "Observations are written by the evaluator" in page
    if kind != "talks":  # the test seed has no dated presentations, so talks may have no graph
        assert "dash-svg" in page  # a graph rendered


def test_dashboard_contents(client, center):
    _login(client, "mwills")
    page = client.get("/manage/outcomes/dashboard/pubs/").content.decode()
    assert "Approximate publication pipeline comparison" in page
    assert "Ratios are presumed estimates." in page
    assert "No core involved" in page
    page = client.get("/manage/outcomes/dashboard/grants/").content.decode()
    assert "Awarded" in page and "Pending" in page and "Declined" in page
    assert "Center overall proposal dollars" in page


def test_dashboard_links_from_tabs(client, center):
    _login(client, "mwills")
    page = client.get("/manage/outcomes/?tab=grants").content.decode()
    assert "/manage/outcomes/dashboard/grants/" in page
