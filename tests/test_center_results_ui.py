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
    assert "data-expand-all" in html and "Open every item-by-item table" in html
    assert "site-visit report" in html
    assert "0</b> people answered" not in html


def test_menu_highlights_the_current_page(client, center):
    client.force_login(User.objects.get(username="okafor"))
    html = client.get("/profile/").content.decode()
    assert 'href="/profile/" aria-current="page"' in html
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


def test_also_use_heading_matches_number_of_cores(client, center):
    from apps.reporting.models import ReportingPeriod
    from apps.reporting.services import assignments as asg

    asg.generate(ReportingPeriod.objects.get(status="open"))
    client.force_login(User.objects.get(username="okafor"))  # uses BN and NI: one core left (CN)
    html = client.get("/tasks/").content.decode()
    assert "Did you also use this core?" in html and "Did you also use these?" not in html


def test_prior_year_overall_sd_from_the_report(center):
    from apps.analytics.report import build
    from apps.forms_engine.models import FormDefinition
    from apps.reporting.models import ReportingPeriod

    d = build(
        FormDefinition.objects.get(code="neurosync_survey"),
        ReportingPeriod.objects.get(short_label="Y9 Spring"),
        audience="staff",
    )
    t = next(t for t in d["tables"] if t.get("lon"))
    got = [(round(c["mean"], 1), c["sd"]) for c in t["lon"]["overall"]]
    # NeuroSync Year 9 site-visit report, Table 2 "Overall Means"
    assert got == [
        (4.2, 0.7),
        (4.2, 0.5),
        (3.9, 0.8),
        (4.2, 0.6),
        (4.4, 0.6),
        (4.3, 0.7),
        (4.5, 0.6),
        (4.5, 0.6),
    ]
