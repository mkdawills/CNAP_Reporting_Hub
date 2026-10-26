"""Milestone 2: relationship services, roster import, handoff, and who may change what."""

import datetime as dt

import pytest
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.common.enums import ImportMatchKind, ImportStatus
from apps.people import roster_import, services
from apps.people.models import Person, PersonRelationship

from .conftest import make_person, make_user


def grant(user, codename):
    user.user_permissions.add(Permission.objects.get(codename=codename))


@pytest.fixture
def evaluator(reference):
    u = make_user(
        make_person("Morgan", "Wills"), username="mw", role=reference["roles"]["administrator"]
    )
    grant(u, "view_confidential_mentoring_data")
    grant(u, "view_identified_survey_responses")
    return u


@pytest.fixture
def director(reference):
    u = make_user(
        make_person("Heather", "Bailey"),
        username="hb",
        role=reference["roles"]["center_leadership"],
    )
    grant(u, "view_confidential_mentoring_data")
    return u


@pytest.fixture
def respondent(reference):
    return make_user(make_person("Rhea", "Spondent"), username="rs")


# ------------------------------------------------------------------ services


def test_add_relationship_explains_single_holder(reference, projects, evaluator):
    t = reference["types"]
    a = make_person("Amy", "Lead")
    b = make_person("Bo", "Second")
    services.add_relationship(evaluator, a, t["project_leader"], project=projects["A"])
    with pytest.raises(services.RelationshipError) as exc:
        services.add_relationship(evaluator, b, t["project_leader"], project=projects["A"])
    assert "one holder" in str(exc.value) and "Amy Lead" in str(exc.value)


def test_add_relationship_explains_wrong_project_kind(reference, projects, evaluator):
    with pytest.raises(services.RelationshipError) as exc:
        services.add_relationship(
            evaluator,
            make_person("P", "M"),
            reference["types"]["pilot_mentor"],
            project=projects["A"],
        )
    assert "cannot be attached" in str(exc.value)


def test_handoff_ends_old_and_starts_new(reference, projects, evaluator):
    t = reference["types"]
    a, b = make_person("Amy", "Lead"), make_person("Bo", "Next")
    rel = services.add_relationship(
        evaluator, a, t["project_leader"], project=projects["A"], start=dt.date(2026, 1, 1)
    )
    new = services.hand_off(evaluator, rel, b, start=dt.date(2026, 9, 1))
    rel.refresh_from_db()
    assert rel.effective_to == dt.date(2026, 8, 31)
    assert new.person == b and new.effective_from == dt.date(2026, 9, 1)
    assert AuditLog.objects.filter(
        entity_type="people.PersonRelationship", entity_id=rel.pk
    ).exists()


def test_handoff_date_must_follow_start(reference, projects, evaluator):
    rel = services.add_relationship(
        evaluator,
        make_person("A", "L"),
        reference["types"]["project_leader"],
        project=projects["A"],
        start=dt.date(2026, 5, 1),
    )
    with pytest.raises(services.RelationshipError):
        services.hand_off(evaluator, rel, make_person("B", "N"), start=dt.date(2026, 5, 1))


def test_core_director_handoff_with_co_director(reference, evaluator):
    t, bn = reference["types"], reference["cores"]["BN"]
    a, b, c = make_person("A", "One"), make_person("B", "Two"), make_person("C", "Three")
    services.add_relationship(evaluator, a, t["core_director"], core=bn, start=dt.date(2026, 1, 1))
    rel_b = services.add_relationship(
        evaluator, b, t["core_director"], core=bn, start=dt.date(2026, 1, 1)
    )
    services.hand_off(evaluator, rel_b, c, start=dt.date(2026, 10, 1))
    current = PersonRelationship.objects.filter(core=bn, effective_to__isnull=True)
    assert {r.person for r in current} == {a, c}


def test_roster_add_and_remove(reference, evaluator):
    p = make_person("Ro", "Ster")
    services.add_to_roster(evaluator, p, start=dt.date(2026, 1, 1))
    assert services.is_on_roster(p)
    with pytest.raises(services.RelationshipError):
        services.add_to_roster(evaluator, p)
    services.remove_from_roster(evaluator, p)
    assert not services.is_on_roster(p)


def test_create_person_refuses_duplicate_email(reference, evaluator):
    make_person("Ada", "L", email="ada@example.edu")
    with pytest.raises(services.RelationshipError):
        services.create_person(evaluator, first_name="A", last_name="B", email="ADA@example.edu")


def test_external_is_by_institution(reference):
    p = make_person("Ex", "Ternal")
    p.institution = "University of Nebraska Medical Center"
    assert services.is_external(p)
    p.institution = "Kansas State University"
    assert not services.is_external(p)


# ------------------------------------------------------------------ roster import

CSV = (
    "First Name,Last Name,Email,Institution\n"
    "Known,Person,known@example.edu,Kansas State University\n"
    "Brand,New,brand@example.edu,Wichita State University\n"
    "Same,Name,other@example.edu,\n"
)


def test_roster_import_classifies_and_commits(reference, evaluator):
    known = make_person("Known", "Person", email="known@example.edu")
    same = make_person("Same", "Name", email="same@example.edu")
    gone = make_person("Gone", "Away", email="gone@example.edu")
    services.add_to_roster(evaluator, gone, start=dt.date(2026, 1, 1))
    imp = roster_import.parse(evaluator, SimpleUploadedFile("roster.csv", CSV.encode()))
    kinds = {(r.first_name, r.match_kind) for r in imp.rows.all()}
    assert ("Known", ImportMatchKind.MATCHED) in kinds
    assert ("Brand", ImportMatchKind.NEW) in kinds
    assert ("Same", ImportMatchKind.POSSIBLE_DUPLICATE) in kinds
    assert ("Gone", ImportMatchKind.MISSING) in kinds
    with pytest.raises(roster_import.RosterFileError):
        roster_import.commit(evaluator, imp)  # the duplicate needs a choice
    dup = imp.rows.get(match_kind=ImportMatchKind.POSSIBLE_DUPLICATE)
    roster_import.set_decision(dup, "merge")
    roster_import.set_decision(imp.rows.get(match_kind=ImportMatchKind.MISSING), "end-membership")
    done = roster_import.commit(evaluator, imp)
    assert done["created"] == 1 and done["merged"] == 1 and done["ended"] == 1
    assert services.is_on_roster(known) and services.is_on_roster(same)
    assert same.emails.filter(email="other@example.edu").exists()
    assert not services.is_on_roster(gone)
    brand = Person.objects.get(last_name="New")
    assert brand.institution == "Wichita State University" and services.is_external(brand)
    imp.refresh_from_db()
    assert imp.status == ImportStatus.COMMITTED
    assert AuditLog.objects.filter(action=AuditLog.Action.IMPORT).exists()


def test_roster_import_needs_columns(reference, evaluator):
    with pytest.raises(roster_import.RosterFileError) as exc:
        roster_import.parse(evaluator, SimpleUploadedFile("r.csv", b"Name,Mail\nA,b@c.d\n"))
    assert "first name" in str(exc.value)


def test_roster_import_reads_xlsx(reference, evaluator):
    import io

    from openpyxl import Workbook

    wb = Workbook()
    wb.active.append(["first name", "last name", "e-mail"])
    wb.active.append(["Xl", "Sheet", "xl@example.edu"])
    buf = io.BytesIO()
    wb.save(buf)
    imp = roster_import.parse(evaluator, SimpleUploadedFile("r.xlsx", buf.getvalue()))
    assert imp.rows.get(row_number=1).match_kind == ImportMatchKind.NEW


# ------------------------------------------------------------------ who may change what


def test_respondent_cannot_open_admin(client, respondent):
    client.force_login(respondent)
    assert client.get(reverse("manage:people")).status_code == 403


def test_view_only_director_sees_but_cannot_change(client, director, reference):
    p = make_person("Target", "Person")
    client.force_login(director)
    page = client.get(reverse("manage:person", args=[p.pk]))
    assert page.status_code == 200
    assert b"Add a relationship" not in page.content
    assert b"View only" in page.content
    resp = client.post(
        reverse("manage:relationship_add", args=[p.pk]),
        {"relationship_type": reference["types"]["cnap_member"].pk, "start": "2026-10-01"},
    )
    assert resp.status_code == 403
    assert not PersonRelationship.objects.filter(person=p).exists()
    assert client.get(reverse("manage:person_new")).status_code == 403
    assert client.post(reverse("manage:person_roster", args=[p.pk])).status_code == 403


def test_evaluator_adds_relationship_through_screen(client, evaluator, reference):
    p = make_person("Target", "Person")
    client.force_login(evaluator)
    resp = client.post(
        reverse("manage:relationship_add", args=[p.pk]),
        {
            "relationship_type": reference["types"]["core_director"].pk,
            "core": reference["cores"]["CN"].pk,
            "start": "2026-10-01",
        },
    )
    assert resp.status_code == 302
    assert PersonRelationship.objects.filter(person=p, core=reference["cores"]["CN"]).exists()


def test_screen_shows_readable_refusal(client, evaluator, reference):
    p = make_person("Target", "Person")
    client.force_login(evaluator)
    resp = client.post(
        reverse("manage:relationship_add", args=[p.pk]),
        {"relationship_type": reference["types"]["core_director"].pk, "start": "2026-10-01"},
        follow=True,
    )
    assert b"must be attached to a core" in resp.content


def test_admin_pages_render(client, evaluator, projects, reference):
    services.add_relationship(
        evaluator,
        make_person("A", "B"),
        reference["types"]["project_leader"],
        project=projects["A"],
    )
    client.force_login(evaluator)
    for name in (
        "manage:home",
        "manage:people",
        "manage:projects",
        "manage:roster_imports",
        "manage:audit",
        "manage:person_new",
        "manage:project_new",
    ):
        assert client.get(reverse(name)).status_code == 200, name
    assert client.get(reverse("manage:project", args=[projects["A"].pk])).status_code == 200


def test_roster_upload_screen_flow(client, evaluator):
    client.force_login(evaluator)
    resp = client.post(
        reverse("manage:roster_upload"),
        {
            "file": SimpleUploadedFile(
                "roster.csv", b"first,last,email\nNew,Person,np@example.edu\n"
            )
        },
    )
    assert resp.status_code == 302
    imp_url = resp["Location"]
    assert client.get(imp_url).status_code == 200
    from apps.reporting.models import RosterImport

    imp = RosterImport.objects.get()
    resp = client.post(reverse("manage:roster_decide", args=[imp.pk]), {"commit": "1"}, follow=True)
    assert b"Import committed" in resp.content
    assert services.is_on_roster(Person.objects.get(last_name="Person"))


def test_stack_filter_puts_sentences_on_lines():
    from apps.common.templatetags.cnap import stack

    out = stack("Dr. Okafor holds it now. Use Hand off to transfer it. 3 left.")
    assert out == "Dr. Okafor holds it now.<br>Use Hand off to transfer it.<br>3 left."
