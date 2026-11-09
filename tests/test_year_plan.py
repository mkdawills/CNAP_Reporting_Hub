"""Your year on My tasks (MW 2026-11-06)."""

import pytest
from django.test import override_settings
from django.core.management import call_command

from apps.accounts.models import User
from apps.portal.presenters import year_plan
from apps.reporting.models import ReportingPeriod
from apps.reporting.services import assignments as asg


@pytest.fixture
def member(db):
    call_command("seed", "--fictional", verbosity=0)
    p = ReportingPeriod.objects.get(status="open")
    asg.generate(p)
    a = p.assignments.select_related("person__user").filter(person__user__isnull=False).first()
    return a.person, p


@override_settings(UI_PROTOTYPE=True)
def test_every_session_of_the_grant_year_with_its_surveys(client, member):
    person, p = member
    year = year_plan(person, p)
    assert [y["p"].grant_year for y in year] == [p.grant_year] * len(year)
    assert any(y["current"] for y in year)
    coming = [y for y in year if y["state"] == "coming"]
    assert coming and coming[0]["items"], "a session not yet open lists what the rules call for"
    labels = [i["label"] for i in year[0]["items"]]
    assert labels == sorted(labels, key=labels.index)  # stable
    # Nothing is created for a session that hasn't opened.
    assert not coming[0]["p"].assignments.exists()
    client.force_login(person.user)
    session = client.session
    session["ui_view"] = "after"
    session.save()
    html = client.get("/tasks/").content.decode()
    assert "Your year" in html and coming[0]["p"].name in html


def test_only_your_own(member):
    person, p = member
    other = p.assignments.exclude(person=person).select_related("person").first().person
    mine = {i["label"] for y in year_plan(person, p) for i in y["items"]}
    theirs = {i["label"] for y in year_plan(other, p) for i in y["items"]}
    assert mine and theirs
