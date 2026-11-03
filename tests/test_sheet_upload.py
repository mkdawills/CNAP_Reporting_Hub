"""Excel upload for repeatable lists (MW 2026-11-03)."""

import io

import pytest

from tests.test_nih_documents import center  # noqa: F401  (fixture)
from openpyxl import Workbook, load_workbook

from apps.accounts.models import User
from apps.forms_engine.runtime import FormSchema
from apps.reporting.models import Assignment
from apps.reporting.services import responses as rs
from apps.reporting.services import sheets

pytestmark = pytest.mark.django_db


def _team_task(center):
    from tests.test_nih_documents import _open

    a = (
        Assignment.objects.filter(reporting_period=center, form_definition__code="progress_pilot")
        .select_related("person")
        .order_by("pk")
        .first()
    )
    a = _open(a)
    return a, User.objects.get(person=a.person)


def _upload(rows, name="team.xlsx"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    wb = Workbook()
    for r in rows:
        wb.active.append(r)
    b = io.BytesIO()
    wb.save(b)
    return SimpleUploadedFile(name, b.getvalue())


def test_template_has_the_section_columns(client, center):
    a, u = _team_task(center)
    client.force_login(u)
    page = client.get(f"/tasks/{a.pk}/").content.decode()
    assert "Download the Excel template" in page and f"/tasks/{a.pk}/sheet/team/" in page
    r = client.get(f"/tasks/{a.pk}/sheet/team/")
    assert r.status_code == 200 and r["Content-Disposition"].endswith('_template.xlsx"')
    head = [c.value for c in load_workbook(io.BytesIO(r.content)).active[1]]
    assert head[:2] == ["First name", "Last name"] and "Calendar months" in head
    other = User.objects.exclude(person=a.person).filter(person__isnull=False).first()
    client.force_login(other)
    assert client.get(f"/tasks/{a.pk}/sheet/team/").status_code in (403, 404)


def test_sheet_rows_are_added_and_checked(center):
    from apps.reporting.services.responses import answers_of

    a, u = _team_task(center)
    up = _upload(
        [
            ["first name", "Last Name", "Email", "Calendar months"],
            ["Ada", "Example", "ada@example.org", 1.5],
            [None, None, None, None],
            ["Bo", "Sample", "", "lots"],
        ]
    )
    problems = rs.save_draft(a, u, {"rep-team-count": "0"}, {"sheet-team": up})
    assert problems == ["Row 4: “Calendar months” needs a number."]
    resp = a.responses.first()
    _, rows, _ = answers_of(resp, FormSchema(a.form_version))
    team = rows["team"]
    assert [r["first_name"] for r in team] == ["Ada", "Bo"]
    assert team[0]["cal_months"] in (1.5, "1.5")


def test_wrong_file_is_refused(center):
    a, u = _team_task(center)
    sec = next(s for s in FormSchema(a.form_version).sections if s.code == "team")
    with pytest.raises(sheets.SheetError):
        sheets.read(sec, _upload([["a"]], name="team.csv"))
    with pytest.raises(sheets.SheetError):
        sheets.read(sec, _upload([["Nothing", "Matches"], ["x", "y"]]))
