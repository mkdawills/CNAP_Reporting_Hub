"""The schema of record is the migrations: models and migrations must agree, and they round-trip."""

from io import StringIO

from django.core.management import call_command


def test_no_missing_migrations(db):
    out = StringIO()
    call_command("makemigrations", "--check", "--dry-run", stdout=out)
    assert "No changes detected" in out.getvalue()


def test_constraints_present(db):
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(
            "SELECT conname FROM pg_constraint WHERE conname IN ("
            "'person_relationships_single_holder','person_relationships_no_overlapping_duplicate',"
            "'person_relationships_allowed_project_kind_fk','assignments_one_per_context',"
            "'assignments_version_definition_fk','questions_measure_scale_fk','answers_single_value')"
        )
        names = {r[0] for r in cur.fetchall()}
        cur.execute(
            "SELECT tgname FROM pg_trigger WHERE tgname = 'question_options_freeze_trigger'"
        )
        trigger = cur.fetchall()
    assert len(names) == 7, names
    assert trigger
