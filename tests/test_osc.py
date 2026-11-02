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


def test_osc_gets_only_the_nih_documents_task(center):
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
    assert got == ({"nih_documents"} if period.sequence == 1 else set())


def test_osc_gets_nih_documents_with_the_biosketch_only(client, center):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.accounts.models import User
    from apps.forms_engine.runtime import FormSchema
    from apps.outcomes import nihdocs
    from apps.reporting.models import Assignment, ReportingPeriod
    from apps.reporting.services import assignments as asg
    from apps.reporting.services import responses as rs
    from tests.test_nih_documents import _open
    from tests.test_sciencv import BIO, _pdf

    period = ReportingPeriod.objects.get(status="open")
    asg.generate(period)
    rowe = Person.objects.get(last_name="Rowe")
    a = _open(Assignment.objects.get(person=rowe, form_definition__code="nih_documents"))
    schema = FormSchema(a.form_version)
    answers = rs.system_answers(a, schema)
    assert answers["osc_only"] == "yes"
    shown = [s.code for s in schema.visible_sections(answers)]
    assert shown == ["biosketch"]
    assert [q.code for q in schema.missing_required(answers)] == ["biosketch"]
    u = User.objects.filter(person=rowe).first() or User.objects.create(username="rowe", person=rowe)
    rs.save_draft(
        a, u, {}, {"file-biosketch": SimpleUploadedFile("b.pdf", _pdf(BIO), "application/pdf")}
    )
    rs.submit(a, u)
    a.refresh_from_db()
    assert a.status == "submitted"
    row = next(r for r in nihdocs.documents(period.grant_year)["rows"] if r["person"] == rowe)
    assert row["osc"] and row["missing"] == []
    # a core director who is also an OSC keeps the full task
    reyes = Person.objects.get(last_name="Reyes")
    PersonRelationship.objects.create(
        person=reyes, relationship_type=RelationshipType.objects.get(code="osc"),
        effective_from=dt.date(2020, 1, 1),
    )
    b = Assignment.objects.get(person=reyes, form_definition__code="nih_documents")
    assert rs.system_answers(b, FormSchema(b.form_version))["osc_only"] == "no"
