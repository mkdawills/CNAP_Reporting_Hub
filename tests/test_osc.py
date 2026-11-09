"""Other Significant Contributors in RPPR D.1 at 0.0 person months (MW 2026-10-28, handbook ch. 6)."""

import datetime as dt

import pytest
from django.core.management import call_command

from apps.outcomes import rppr
from apps.people.models import Person, PersonEffort, PersonRelationship, RelationshipType


@pytest.fixture
def center(db):
    call_command("seed", "--fictional", verbosity=0)


def test_osc_listed_at_zero_months(center):
    gy = rppr.current_year()
    start, _ = rppr.period(gy)
    osc = RelationshipType.objects.get(code="osc")
    assert osc.name == "Other Significant Contributor (OSC)"
    p = Person.objects.create(first_name="Ines", last_name="Halvorsen")
    PersonRelationship.objects.create(person=p, relationship_type=osc, effective_from=start)
    d1 = rppr.d1(gy)
    row = next(x for x in d1["rows"] if x["person"] == p)
    assert row["category"] == "Other" and row["label"] == "Other (Other Significant Contributor)" and row["months"] == 0
    assert p not in [x["person"] for x in d1["missing_months"]]
    # a staff member at 0.5 months is set aside; the same person as an OSC is listed
    staff = RelationshipType.objects.get(code="collaborator")
    q = Person.objects.create(first_name="Ola", last_name="Brandt")
    PersonEffort.objects.create(person=q, grant_year=gy, calendar_months=0.5)
    from apps.people.models import Project

    pr = Project.objects.first()
    PersonRelationship.objects.create(person=q, relationship_type=staff, project=pr, effective_from=start)
    assert q in [x["person"] for x in rppr.d1(gy)["below"]]
    PersonRelationship.objects.create(person=q, relationship_type=osc, effective_from=start)
    row = next(x for x in rppr.d1(gy)["rows"] if x["person"] == q)
    assert row["months"] == 0.5 and row["osc"]


def test_osc_gets_no_tasks(center):
    """MW 2026-11-04: NIH documents come only from Core Directors, RPLs, PPLs, and the PD/PI."""
    from apps.reporting.models import Assignment, ReportingPeriod
    from apps.reporting.services import assignments as asg

    period = ReportingPeriod.objects.get(status="open")
    p = Person.objects.create(first_name="Ines", last_name="Halvorsen")
    PersonRelationship.objects.create(
        person=p, relationship_type=RelationshipType.objects.get(code="osc"),
        effective_from=dt.date(2020, 1, 1),
    )
    asg.generate(period)
    got = set(Assignment.objects.filter(person=p).values_list("form_definition__code", flat=True))
    assert got == set()


def test_osc_only_person_is_not_asked_for_nih_documents(center):
    from apps.reporting.models import Assignment, ReportingPeriod
    from apps.reporting.services import assignments as asg

    asg.generate(ReportingPeriod.objects.get(status="open"))
    rowe = Person.objects.get(last_name="Rowe")
    assert not Assignment.objects.filter(person=rowe, form_definition__code="nih_documents").exists()


def test_nih_documents_directions_fit_the_person(client, center):
    from apps.accounts.models import User
    from apps.reporting.models import Assignment, ReportingPeriod
    from apps.reporting.services import assignments as asg

    asg.generate(ReportingPeriod.objects.get(status="open"))
    want = {
        "Brandt": "from people named on the Notice of Award",
        "Varga": "collects the Current and Pending (Other) Support of each Core Director",
    }
    for last, text in want.items():
        p = Person.objects.get(last_name=last)
        a = Assignment.objects.get(person=p, form_definition__code="nih_documents")
        u = User.objects.filter(person=p).first() or User.objects.create(username=f"u{last}", person=p)
        client.force_login(u)
        page = client.get(f"/tasks/{a.pk}/").content.decode()
        assert text in page, last
        others = [t for k, t in want.items() if k != last] + ["from each Other Significant Contributor"]
        assert not any(t in page for t in others), last
