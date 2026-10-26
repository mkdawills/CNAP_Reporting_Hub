"""RPPR rules from the FY27 COBRE reporting guidance (decisions.md 2026-10-26)."""

import datetime as dt

import pytest
from django.core.management import call_command

from apps.accounts.models import User
from apps.outcomes import rppr
from apps.outcomes.models import (
    GrantFamily,
    GrantSubmission,
    GrantSubmissionPerson,
    Publication,
    PublicationPerson,
)


@pytest.fixture
def center(db):
    call_command("seed", "--fictional", verbosity=0)


def person(u):
    return User.objects.get(username=u).person


def pub(title, when, **kw):
    p = Publication.objects.create(
        title=title,
        publication_type=kw.pop("publication_type", "journal_article"),
        status="published",
        publication_date=when,
        **kw,
    )
    PublicationPerson.objects.create(publication=p, person=person("okafor"))
    return p


def grant(title, *, sub=None, won=None, total=None, role="pi", agency="NIH", **kw):
    g = GrantSubmission.objects.create(
        grant_family=GrantFamily.objects.create(title=title),
        project_title=title,
        funding_agency=agency,
        status="awarded" if won else "submitted",
        submission_date=sub,
        award_notice_date=won,
        award_total=total,
        **kw,
    )
    GrantSubmissionPerson.objects.create(
        grant_submission=g, person=person("okafor"), role=role, is_primary_cnap_contact=True
    )
    return g


def test_period_is_june_to_may():
    assert rppr.period(9) == (dt.date(2025, 6, 1), dt.date(2026, 5, 31))
    assert rppr.current_year(dt.date(2026, 10, 26)) == 10


def test_c1_rules(center):
    Publication.objects.all().delete()
    ok = pub("Peer reviewed", dt.date(2025, 9, 1))
    pre = pub("A preprint", dt.date(2025, 9, 1), publication_type="preprint")
    foreign = pub(
        "Foreign, not approved",
        dt.date(2025, 9, 1),
        has_foreign_authors=True,
        foreign_component_approved=False,
    )
    approved = pub(
        "Foreign, approved",
        dt.date(2025, 9, 1),
        has_foreign_authors=True,
        foreign_component_approved=True,
    )
    old = pub("Reported last year", dt.date(2025, 9, 1), rppr_year=8)
    outside = pub("Next year", dt.date(2026, 7, 1))
    inc, exc = rppr.c1(9)
    assert set(inc) == {ok, approved}
    reasons = {p.title: why for p, why in exc}
    assert (
        "Preprint" in reasons[pre.title]
        and "NIGMS" in reasons[foreign.title]
        and "Year 8" in reasons[old.title]
    )
    assert outside not in inc


def test_table1_rules(center):
    GrantSubmission.objects.all().delete()
    grant("Submitted only", sub=dt.date(2025, 8, 1))
    grant(
        "Submitted and won same year",
        sub=dt.date(2025, 7, 1),
        won=dt.date(2026, 3, 1),
        total=400000,
    )
    grant(
        "Won as MPI",
        sub=dt.date(2024, 10, 1),
        won=dt.date(2025, 9, 1),
        total=1000000,
        role="mpi",
        cnap_portion=250000,
    )
    grant("Foundation", sub=dt.date(2025, 9, 1), agency="Sample Foundation")
    grant("NSF one", sub=dt.date(2025, 10, 1), agency="NSF")
    grant(
        "The parent",
        sub=dt.date(2025, 8, 1),
        won=dt.date(2026, 1, 1),
        total=9000000,
        grant_number="P20 GM113109",
    )
    grant("Counted before", sub=dt.date(2025, 8, 1), rppr_submitted_year=8)
    t = rppr.table1(9)
    assert (
        t["total"]["sub"] == 3
    )  # submitted only, foundation, NSF (the same-year award counts once, as an award)
    assert t["total"]["won"] == 2
    assert t["total"]["cost"] == 400000 + 250000  # MPI: the CNAP investigator's portion
    assert t["a"]["non_federal"]["sub"] == 1 and t["a"]["federal_other"]["sub"] == 1
    skipped = {g.project_title: why for g, why in t["skipped"]}
    assert "Parent COBRE" in skipped["The parent"] and "Year 8" in skipped["Counted before"]


def test_mark_reported_stops_double_counting(center):
    GrantSubmission.objects.all().delete()
    Publication.objects.all().delete()
    pub("Paper", dt.date(2025, 9, 1))
    grant("App", sub=dt.date(2025, 8, 1))
    rppr.mark_reported(User.objects.get(username="mwills"), 9)
    assert Publication.objects.get(title="Paper").rppr_year == 9
    assert GrantSubmission.objects.get(project_title="App").rppr_submitted_year == 9
    # still listed for Year 9 (re-download), never for another year
    assert len(rppr.c1(9)[0]) == 1


def test_foreign_approval_required_and_warned(client, center):
    client.force_login(User.objects.get(username="okafor"))
    p = Publication.objects.create(
        title="F", publication_type="journal_article", status="submitted"
    )
    PublicationPerson.objects.create(publication=p, person=person("okafor"))
    from apps.people.models import Resource

    bn = Resource.objects.get(code="bn_core").pk
    base = {
        "to": "published",
        "submission_date": "2025-08-01",
        "journal": "J",
        "title": "F",
        "pubmed_url": "https://pubmed.ncbi.nlm.nih.gov/1/",
        "cnap_cited": "no",
        "cnap_in_grant_index": "no",
        "has_foreign_authors": "yes",
        "has_non_idea_coauthors": "no",
        "resources": [bn],
    }
    r = client.post(f"/outcomes/pub/{p.pk}/", base)
    assert (
        r.status_code == 200 and "decides whether the paper can be reported" in r.content.decode()
    )
    r = client.post(
        f"/outcomes/pub/{p.pk}/", {**base, "foreign_component_approved": "no"}, follow=True
    )
    assert "can’t be listed in CNAP’s progress report" in r.content.decode()


def test_everyone_on_roster_can_open_prompt_only_for_roles(client, center):
    client.force_login(User.objects.get(username="lee"))  # student, no RPPR role
    assert client.get("/outcomes/").status_code == 200
    assert "Update your publications and grants" not in client.get("/tasks/").content.decode()


def test_rppr_tab_and_downloads(client, center):
    client.force_login(User.objects.get(username="mwills"))
    assert client.get("/manage/outcomes/?tab=rppr&year=9").status_code == 200
    assert (
        client.get("/manage/outcomes/export/table1/?year=9")
        .content.decode("utf-8-sig")
        .startswith("RPPR Year 9")
    )
    assert "C.1 Publications" in client.get("/manage/outcomes/export/c1/?year=9").content.decode(
        "utf-8-sig"
    )


def test_previous_year_unreported_items_count_in_the_next_rppr(center):
    late = pub("Published after the Y9 RPPR", dt.date(2026, 5, 10))
    inc, _ = rppr.c1(10)
    assert late in inc
    late.rppr_year = 9
    late.save()
    assert late not in rppr.c1(10)[0]
    g = grant(
        "Funded after the Y9 RPPR", sub=dt.date(2025, 9, 1), won=dt.date(2026, 5, 1), total=1000
    )
    row = next(r for r in rppr.table1(10)["rows"] if r["g"] == g)
    assert row["kind"] == "Award funded" and row["carried_from"] == 9
    # two years back is not carried
    old = pub("Two years back", dt.date(2025, 5, 1))
    assert old not in rppr.c1(10)[0]
    # once marked, the award's application is never counted separately afterwards
    rppr.mark_reported(None, 10)
    g.refresh_from_db()
    assert g.rppr_awarded_year == 10 and g.rppr_submitted_year == 10


def test_core_staff_awards_carry_the_idea_support_check(center):
    from apps.people.models import PersonRelationship, RelationshipType

    PersonRelationship.objects.filter(person=person("okafor")).delete()
    PersonRelationship.objects.create(
        person=person("okafor"),
        relationship_type=RelationshipType.objects.get(code="core_staff"),
        core=__import__("apps.people.models", fromlist=["Core"]).Core.objects.get(code="BN"),
        effective_from=dt.date(2020, 1, 1),
    )
    grant("Equipment", sub=dt.date(2026, 7, 1), won=dt.date(2026, 9, 1), total=50000)
    row = next(r for r in rppr.table1(10)["rows"] if r["g"].project_title == "Equipment")
    assert row["role"] == "Core Staff" and "related to IDeA support" in row["check"]


def test_award_form_asks_for_portion_when_shared(client, center):
    from apps.outcomes.models import GrantSubmissionResource
    from apps.people.models import Resource

    g = grant("Shared award", sub=dt.date(2026, 7, 1), role="mpi")
    GrantSubmissionResource.objects.create(
        grant_submission=g, resource=Resource.objects.get(code="cn_core"), is_anticipated=False
    )
    client.force_login(User.objects.get(username="okafor"))
    base = {
        "to": "awarded",
        "award_notice_date": "2026-09-01",
        "project_start_date": "2026-10-01",
        "project_end_date": "2029-09-30",
        "award_total": "300000",
        "award_direct": "200000",
        "award_indirect": "100000",
        "cnap_acknowledged": "yes",
        "cnap_credited_in_publications": "yes",
        "has_foreign_component": "no",
        "resources": [Resource.objects.get(code="cn_core").pk],
    }
    r = client.post(f"/outcomes/grant/{g.pk}/", base)
    assert "please give your portion" in r.content.decode()
    r = client.post(f"/outcomes/grant/{g.pk}/", {**base, "award_direct": "150000"})
    assert "don’t add up" in r.content.decode()
    client.post(f"/outcomes/grant/{g.pk}/", {**base, "cnap_portion": "120000"})
    g.refresh_from_db()
    assert g.status == "awarded" and g.cnap_portion == 120000
    assert rppr.amount(g) == (120000.0, "CNAP investigator's portion")
