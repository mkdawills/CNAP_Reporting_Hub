"""Planned dates with an optional day, structured talk locations, "(your project)" and review-first (MW 2026-11-03)."""

import datetime as dt

import pytest
from django.core.management import call_command

from apps.accounts.models import User
from apps.outcomes.models import GrantSubmission, Presentation, Publication
from apps.people.models import Resource

pytestmark = pytest.mark.django_db


@pytest.fixture
def center(db):
    call_command("seed", "--fictional", verbosity=0)


def _login(client, u):
    user = User.objects.get(username=u)
    client.force_login(user)
    return user


def test_planned_publication_day_is_optional(client, center):
    u = _login(client, "okafor")
    page = client.get("/outcomes/new/pub/").content.decode()
    assert "Day (optional)" in page and "(your project)" in page
    assert "Center resources you anticipate using" in page
    pilot = Resource.objects.get(code="pilot_project")
    from apps.outcomes.services import awardee_projects

    prj = awardee_projects(u.person)[0]
    base = {
        "title": "Spindles A",
        "publication_type": "journal_article",
        "anticipated_submission_month": "2027-03",
        "resources": [pilot.pk],
        "projects": [prj.pk],
    }
    client.post("/outcomes/new/pub/", base)
    p = Publication.objects.get(title="Spindles A")
    assert p.anticipated_submission_month == dt.date(2027, 3, 1) and not p.anticipated_day_known
    client.post("/outcomes/new/pub/", base | {"title": "Spindles B", "anticipated_day": "14"})
    p = Publication.objects.get(title="Spindles B")
    assert p.anticipated_submission_month == dt.date(2027, 3, 14) and p.anticipated_day_known
    r = client.post(
        "/outcomes/new/pub/",
        base
        | {
            "title": "Spindles C",
            "anticipated_submission_month": "2027-02",
            "anticipated_day": "30",
        },
    )
    assert "That month has only 28 days." in r.content.decode()
    # a project resource needs its project
    r = client.post("/outcomes/new/pub/", base | {"title": "Spindles D", "projects": []})
    assert "Choose which pilot project or projects." in r.content.decode()


def test_proposal_title_is_explained(client, center):
    _login(client, "okafor")
    page = client.get("/outcomes/new/grant/").content.decode()
    assert "Proposal title" in page and "not your CNAP project’s title" in page
    assert GrantSubmission is not None


def test_talk_location_has_parts(client, center):
    _login(client, "okafor")
    page = client.get("/outcomes/presentations/new/").content.decode()
    assert "NeuroSync presentations do not qualify." in page and "Name of Event or Meeting" in page
    client.post(
        "/outcomes/presentations/new/",
        {
            "presentation_type": "conference",
            "title": "Sleep talk",
            "venue": "Kansas State University",
            "city": "Manhattan",
            "state_region": "Kansas",
            "country": "United States",
            "presented_on": "2026-10-01",
            "cnap_cited": "yes",
        },
    )
    t = Presentation.objects.get(title="Sleep talk")
    assert (
        t.location == "Kansas State University, Manhattan, Kansas, United States"
        and t.city == "Manhattan"
    )
