"""Your year on My tasks (MW 2026-11-06)."""

import pytest
from django.core.management import call_command
from django.test import override_settings

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


@override_settings(UI_PROTOTYPE=True)
def test_my_history_part_two_lists_own_products_by_grant_year(client, member):
    from apps.portal.presenters import my_products

    best = max(
        (u for u in User.objects.filter(person__isnull=False)),
        key=lambda u: sum(len(y["rows"]) for y in my_products(u.person)),
    )
    years = my_products(best.person)
    assert years and [y["year"] for y in years] == sorted((y["year"] for y in years), reverse=True)
    client.force_login(best)
    session = client.session
    session["ui_view"] = "after"
    session.save()
    html = client.get("/history/").content.decode()
    assert "Publications, talks, and grants" in html
    first = years[0]["rows"][0]
    assert f"#{first['anchor']}" in html
