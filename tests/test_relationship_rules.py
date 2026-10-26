"""Review section 2.1: the database refuses every invalid relationship."""

import datetime as dt

import pytest
from django.db import IntegrityError, transaction
from django.db.utils import ProgrammingError

from apps.people.models import PersonRelationship

from .conftest import make_person, relate


def refused(func):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            func()


def test_four_different_relationships_coexist(okafor):
    assert okafor.relationships.count() == 4
    assert okafor.has_rich_profile() is True


def test_core_director_without_core_refused(reference):
    p = make_person("Ada", "Lovelace")
    refused(lambda: relate(p, reference["types"]["core_director"]))


def test_core_director_attached_to_project_refused(reference, projects):
    p = make_person("Ada", "Lovelace")
    refused(lambda: relate(p, reference["types"]["core_director"], project=projects["A"]))


def test_pilot_mentor_on_primary_project_refused(reference, projects):
    """FK to relationship_type_project_kinds: ('pilot_mentor', 'primary') is not allowed."""
    p = make_person("Ada", "Lovelace")
    refused(lambda: relate(p, reference["types"]["pilot_mentor"], project=projects["A"]))


def test_project_kind_copy_cannot_lie(reference, projects):
    """A row claiming project_kind='pilot' for a Primary project fails the (project_id, kind) FK."""
    p = make_person("Ada", "Lovelace")
    rel = PersonRelationship(
        person=p,
        relationship_type=reference["types"]["pilot_mentor"],
        project=projects["A"],
        effective_from=dt.date(2026, 1, 1),
    )
    rel.fill_copied_columns()
    rel.project_kind = "pilot"  # lie after the copy
    refused(lambda: PersonRelationship.objects.bulk_create([rel]))


def test_context_kind_copy_cannot_lie(reference):
    """A row claiming context_kind='none' for a core-scoped type fails the (type, context) FK."""
    p = make_person("Ada", "Lovelace")
    rel = PersonRelationship(
        person=p,
        relationship_type=reference["types"]["core_director"],
        effective_from=dt.date(2026, 1, 1),
    )
    rel.context_kind = "none"
    rel.is_single_holder = False
    refused(lambda: PersonRelationship.objects.bulk_create([rel]))


def test_second_current_project_leader_refused(reference, projects, okafor):
    """Exclusion 6: Project Leader is single-holder."""
    p = make_person("Ada", "Lovelace")
    refused(lambda: relate(p, reference["types"]["project_leader"], project=projects["A"]))


def test_project_leader_succession_allowed(reference, projects, okafor):
    old = okafor.relationships.get(relationship_type__code="project_leader")
    old.effective_to = dt.date(2027, 6, 30)
    old.save()
    p = make_person("Ada", "Lovelace")
    relate(
        p, reference["types"]["project_leader"], project=projects["A"], start=dt.date(2027, 7, 1)
    )
    assert (
        PersonRelationship.objects.filter(
            project=projects["A"], relationship_type__code="project_leader"
        ).count()
        == 2
    )


def test_co_directors_allowed(reference, okafor):
    """Review 15.10: Core Director is not single-holder."""
    p = make_person("Ada", "Lovelace")
    relate(p, reference["types"]["core_director"], core=reference["cores"]["NI"])
    assert (
        PersonRelationship.objects.filter(
            core=reference["cores"]["NI"], relationship_type__code="core_director"
        ).count()
        == 2
    )


def test_same_relationship_twice_with_overlap_refused(reference, projects, okafor):
    """Exclusion 5."""
    refused(
        lambda: relate(
            okafor,
            reference["types"]["pilot_mentor"],
            project=projects["B"],
            start=dt.date(2026, 3, 1),
        )
    )


def test_same_relationship_again_after_it_ended_allowed(reference, projects, okafor):
    rel = okafor.relationships.get(relationship_type__code="pilot_mentor")
    rel.effective_to = dt.date(2026, 6, 30)
    rel.save()
    relate(
        okafor, reference["types"]["pilot_mentor"], project=projects["B"], start=dt.date(2026, 7, 1)
    )


def test_end_before_start_refused(reference, okafor):
    rel = okafor.relationships.get(relationship_type__code="cnap_member")
    rel.effective_to = dt.date(2025, 12, 31)
    refused(rel.save)


def test_changing_type_context_while_in_use_refused(reference, okafor):
    """FK 1 with the default NO ACTION: a type cannot change context while rows use it."""
    core_director = reference["types"]["core_director"]
    core_director.context_kind = "project"
    with pytest.raises((IntegrityError, ProgrammingError)):
        with transaction.atomic():
            core_director.save()


def test_views_read_from_relationships(okafor, projects, django_db_blocker):
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(
            "SELECT role_code, is_current FROM project_people WHERE project_id = %s",
            [projects["A"].id],
        )
        rows = cur.fetchall()
        cur.execute("SELECT role_code FROM core_people WHERE person_id = %s", [okafor.id])
        core_rows = cur.fetchall()
    assert rows == [("project_leader", True)]
    assert core_rows == [("core_director",)]


def test_as_of_history_query(reference, okafor):
    rel = okafor.relationships.get(relationship_type__code="core_director")
    rel.effective_to = dt.date(2027, 6, 30)
    rel.save()
    assert (
        okafor.current_relationships(on=dt.date(2027, 3, 1))
        .filter(relationship_type__code="core_director")
        .exists()
    )
    assert (
        not okafor.current_relationships(on=dt.date(2027, 9, 1))
        .filter(relationship_type__code="core_director")
        .exists()
    )
