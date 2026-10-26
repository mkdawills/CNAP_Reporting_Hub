"""Center results page: Show all / Collapse all, and imported prior-year periods (decisions.md 2026-10-26)."""

import pytest
from django.core.management import call_command

from apps.accounts.models import User
from apps.reporting.models import ReportingPeriod


@pytest.fixture
def center(db):
    call_command("seed", "--fictional", verbosity=0)
    call_command("import_aggregates", verbosity=0)


def test_expand_all_and_prior_year_wording(client, center):
    client.force_login(User.objects.get(username="okafor"))
    p = (
        ReportingPeriod.objects.filter(assignments__isnull=True, snapshots__isnull=False)
        .order_by("-display_order")
        .first()
    )
    html = client.get(f"/results/?period={p.short_label}").content.decode()
    assert "data-expand-all" in html and "Show all tables" in html
    assert "site-visit report" in html
    assert "0</b> people answered" not in html


def test_menu_highlights_the_current_page(client, center):
    client.force_login(User.objects.get(username="okafor"))
    html = client.get("/profile/").content.decode()
    assert '<a href="/profile/" aria-current="page">' in html
    assert "&quot;page&quot;" not in html


def test_profile_help_and_evaluator_contact(client, center):
    from apps.people.models import Person

    okafor = User.objects.get(username="okafor")  # K-State
    client.force_login(okafor)
    html = client.get("/profile/").content.decode()
    assert "mailto:mkwills@ksu.edu" in html and "research@k-state.edu" in html
    santos = User.objects.get(username="santos")  # outside K-State
    assert Person.objects.get(pk=santos.person_id).institution != "Kansas State University"
    client.force_login(santos)
    html = client.get("/profile/").content.decode()
    assert (
        "Contact your institution’s research office" in html and "research@k-state.edu" not in html
    )
