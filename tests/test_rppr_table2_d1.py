"""RPPR Table 2 (core usage) and D.1 participants (decisions.md 2026-10-26, item 7)."""

from decimal import Decimal

import pytest
from django.core.management import call_command

from apps.accounts.models import User
from apps.outcomes import rppr
from apps.reporting.models import Assignment, ReportingPeriod
from apps.reporting.services import assignments as asg


@pytest.fixture
def center(db):
    call_command("seed", "--fictional", verbosity=0)
    for p in ReportingPeriod.objects.filter(status="open"):
        asg.generate(p)
    return ReportingPeriod.objects.get(status="open")


def login(client, u):
    user = User.objects.get(username=u)
    client.force_login(user)
    return user


def usage_assignment(person):
    """The person's usage report, reset to not started (the sample seed may have submitted it)."""
    a = Assignment.objects.get(form_definition__code="core_usage_report", person=person)
    for r in a.responses.all():
        r.answers.all().delete()
    a.responses.all().delete()
    Assignment.objects.filter(pk=a.pk).update(status="not_started")
    a.refresh_from_db()
    return a


def test_core_director_gets_usage_report_with_row_widgets(client, center):
    u = login(client, "reyes")
    a = usage_assignment(u.person)
    html = client.get(f"/tasks/{a.pk}/").content.decode()
    assert '<select name="rep-users-0-user_type"' in html
    assert 'type="number" min="0" step="1" name="rep-users-0-n_users"' in html
    assert '<select name="rep-users-0-core_data_used"' in html


def test_submitted_rows_build_table2(client, center):
    u = login(client, "reyes")
    a = usage_assignment(u.person)
    post = {
        "rep-users-count": "2",
        "rep-users-0-user_type": "rpl",
        "rep-users-0-lab": "Kim lab",
        "rep-users-0-project_name": "Project A",
        "rep-users-0-services": "Behavior suite",
        "rep-users-0-n_users": "3",
        "rep-users-0-n_students": "2",
        "rep-users-0-payment": "in_kind",
        "rep-users-0-core_data_used": "yes",
        "rep-users-1-user_type": "external",
        "rep-users-1-n_users": "1",
        "rep-users-1-lab": " kim  LAB ",
        "rep-users-1-project_name": "Project B",
        "rep-users-1-payment": "voucher",
        "action": "submit",
    }
    client.post(f"/tasks/{a.pk}/", post)
    a.refresh_from_db()
    assert a.status == "submitted"
    # numbers come back as whole numbers on the form
    assert 'value="3"' in client.get(f"/tasks/{a.pk}/").content.decode()
    bn = next(c for c in rppr.table2(center.grant_year)["cores"] if c["core"].code == "BN")
    assert [r["cells"][0] for r in bn["rows"]] == ["RPL", "External"]
    assert bn["users"] == 4 and bn["students"] == 2 and bn["said_yes"] == 1
    assert u.person not in [p for g in bn["gaps"] for p in g["people"]]
    # one lab listed for two projects counts once
    assert bn["labs"] == 1 and bn["total_users"] == 6
    assert bn["summary"] == (
        "There were 6 users of the Behavioral Neuroscience Core. 5 in-kind users; 1 voucher user."
    )


def test_gaps_and_two_reports_for_a_two_director_core(client, center):
    reyes = User.objects.get(username="reyes").person
    varga = User.objects.get(username="varga").person
    usage_assignment(reyes), usage_assignment(varga)
    bn = next(c for c in rppr.table2(center.grant_year)["cores"] if c["core"].code == "BN")
    assert {p.pk for g in bn["gaps"] for p in g["people"]} == {reyes.pk, varga.pk}
    for u in ("reyes", "varga"):
        a = usage_assignment(login(client, u).person)
        client.post(
            f"/tasks/{a.pk}/",
            {"rep-users-count": "1", "rep-users-0-user_type": "ppl", "action": "submit"},
        )
    bn = next(c for c in rppr.table2(center.grant_year)["cores"] if c["core"].code == "BN")
    assert not bn["gaps"] and len(bn["doubles"]) == 1


def test_admin_core_is_left_out(center):
    from apps.people.models import Core

    Core.objects.create(code="ADMIN", name="Administrative Core", sort_order=0)
    assert "ADMIN" not in [c["core"].code for c in rppr.table2(center.grant_year)["cores"]]


def test_d1_uses_only_the_six_nih_categories(center):
    rows = rppr.d1(rppr.current_year())["rows"]
    allowed = {"PD/PI", "Core Director", "Mentor", "Trainee", "Other"} | {
        f"Project Leader ({k} Leader)" for k in ("RP", "PP", "SP")
    }
    assert {x["category"] for x in rows} <= allowed


def test_table2_and_d1_on_rppr_tab_and_csv(client, center):
    usage_assignment(User.objects.get(username="reyes").person)
    usage_assignment(User.objects.get(username="varga").person)
    login(client, "mwills")
    gy = center.grant_year
    html = client.get(f"/manage/outcomes/?tab=rppr&year={gy}").content.decode()
    assert "Table 2: COBRE Core Users" in html and "Table 2A" in html and "D.1 Participants" in html
    assert "Not reported yet" in html
    csv2 = client.get(f"/manage/outcomes/export/table2/?year={gy}").content.decode("utf-8-sig")
    assert "Number of individual users per project (exclude student users)" in csv2
    d1 = client.get(f"/manage/outcomes/export/d1/?year={gy}").content.decode("utf-8-sig")
    assert "eRA Commons ID" in d1.splitlines()[1]


def test_d1_commons_id_from_profile(client, center):
    u = login(client, "okafor")
    gy = rppr.current_year()
    before = rppr.d1(gy)
    assert u.person in [x["person"] for x in before["missing_commons"]]
    client.post("/profile/", {"department": "", "position_title": "", "era_commons_id": "AOKAFOR"})
    after = rppr.d1(gy)
    row = next(x for x in after["rows"] if x["person"] == u.person)
    assert row["commons"] == "AOKAFOR" and row["category"] == "Project Leader (PP Leader)"
    assert u.person not in [x["person"] for x in after["missing_commons"]]


def test_d1_leaves_out_core_users_and_members(center):
    rows = rppr.d1(rppr.current_year())["rows"]
    cats = {x["category"] for x in rows}
    assert cats <= set(rppr.D1_ORDER)
    from apps.people.models import PersonRelationship

    only_users = {
        r.person_id for r in PersonRelationship.objects.filter(relationship_type__code="core_user")
    } - {
        r.person_id
        for r in PersonRelationship.objects.filter(relationship_type__code__in=rppr.D1_CATEGORY)
    }
    assert not only_users & {x["person"].pk for x in rows}


def test_calendar_months_filter_d1(client, center):
    from apps.people.models import PersonEffort

    u = login(client, "okafor")
    gy = rppr.current_year()
    html = client.get("/profile/").content.decode()
    assert 'name="calendar_months"' in html
    client.post("/profile/", {"department": "", "position_title": "", "calendar_months": "0.5"})
    assert PersonEffort.objects.get(person=u.person, grant_year=gy).calendar_months == Decimal(
        "0.5"
    )
    d = rppr.d1(gy)
    assert u.person in [x["person"] for x in d["below"]]
    assert u.person not in [x["person"] for x in d["rows"]]
    client.post("/profile/", {"department": "", "position_title": "", "calendar_months": "1.2"})
    d = rppr.d1(gy)
    row = next(x for x in d["rows"] if x["person"] == u.person)
    assert float(row["months"]) == 1.2 and u.person not in [
        x["person"] for x in d["missing_months"]
    ]
    # out of range is refused
    client.post("/profile/", {"department": "", "position_title": "", "calendar_months": "13"})
    assert PersonEffort.objects.get(person=u.person, grant_year=gy).calendar_months == Decimal(
        "1.2"
    )


def test_commons_help_button_emails_evaluator(client, center, mailoutbox):
    u = login(client, "okafor")
    html = client.get("/profile/").content.decode()
    assert (
        "I need help setting up eRA Commons" in html and "I’m not sure I need eRA Commons" in html
    )
    client.post("/profile/", {"action": "commons_help", "kind": "unsure"})
    u.person.refresh_from_db()
    assert u.person.era_commons_help_kind == "unsure" and u.person.era_commons_help_requested_at
    assert any("eRA Commons help" in m.subject for m in mailoutbox)
    login(client, "mwills")
    html = client.get(f"/manage/outcomes/?tab=rppr&year={rppr.current_year()}").content.decode()
    assert "Asked for help: unsure whether they need one" in html


def test_admin_sets_months(client, center):
    from apps.people.models import Person, PersonEffort

    login(client, "mwills")
    p = Person.objects.get(last_name="Kim")
    client.post(f"/manage/people/{p.pk}/effort/", {"grant_year": "10", "calendar_months": "3"})
    assert PersonEffort.objects.get(person=p, grant_year=10).calendar_months == 3
    assert "Year 10: <strong>3.0</strong>" in client.get(f"/manage/people/{p.pk}/").content.decode()


def test_project_leader_comes_before_core_director_and_is_flagged(client, center):
    from apps.admin_center import quality

    gy = rppr.current_year()
    moreau = User.objects.get(username="moreau").person  # sample data: CN director and an RPL
    row = next(x for x in rppr.d1(gy)["rows"] if x["person"] == moreau)
    assert row["category"] == "Project Leader (RP Leader)" and "Core Director" in row["roles"]
    flagged = next(c for c in quality.run() if c["code"] == "director_and_leader")
    assert moreau.pk in [r[1] for r in flagged["rows"]]


def test_late_items_carry_into_next_rppr(center):
    import datetime as dt

    from apps.outcomes.models import Publication, PublicationPerson

    p = Publication.objects.create(
        title="After the Y9 RPPR",
        publication_type="journal_article",
        status="published",
        publication_date=dt.date(2026, 5, 10),
    )
    PublicationPerson.objects.create(
        publication=p, person=User.objects.get(username="okafor").person
    )
    inc, _ = rppr.c1(10)
    got = next(x for x in inc if x == p)
    assert got.carried_from == 9
    p.rppr_year = 9
    p.save()
    assert p not in rppr.c1(10)[0]
