"""February "has your Current and Pending changed?" check (MW 2026-10-28)."""

import datetime as dt
from datetime import timedelta

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import User
from apps.outcomes import cpcheck
from apps.reporting.models import Assignment, CurrentPendingCheck, ReportingPeriod
from apps.reporting.services import assignments as asg
from apps.reporting.services import responses as rs
from tests.test_nih_documents import _open
from tests.test_sciencv import CPOS, _pdf

PDF = b"%PDF-1.7\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@pytest.fixture
def fall(db):
    call_command("seed", "--fictional", verbosity=0)
    p = ReportingPeriod.objects.get(status="open")
    asg.generate(p)
    return p


def _turn_in(fall):
    a = _open(
        Assignment.objects.filter(reporting_period=fall, form_definition__code="nih_documents")
        .select_related("person")
        .order_by("pk")
        .first()
    )
    u = User.objects.get(person=a.person)
    from tests.test_sciencv import BIO

    files = {
        "file-biosketch": SimpleUploadedFile("biosketch.pdf", _pdf(BIO), "application/pdf"),
        "file-current_pending": SimpleUploadedFile(
            "current_pending.pdf", _pdf(CPOS), "application/pdf"
        ),
        "file-mftrp_cert": SimpleUploadedFile("mftrp_cert.pdf", PDF, "application/pdf"),
    }
    assert rs.save_draft(a, u, {"q-d2a": "no"}, files) == []
    rs.submit(a, u)
    a.refresh_from_db()
    return a, u


def test_dates_are_in_the_budget_years_february(fall):
    ask, due, stop = cpcheck.dates(10)
    assert (ask, due, stop) == (dt.date(2027, 2, 1), dt.date(2027, 2, 15), dt.date(2027, 3, 1))


def test_ask_then_every_four_days_then_daily(fall):
    a, u = _turn_in(fall)
    gy = fall.grant_year
    ask, due, stop = cpcheck.dates(gy)
    assert cpcheck.run(ask - timedelta(days=1)) == 0
    mine = lambda: [m for m in mail.outbox if m.to == [a.person.primary_email]]  # noqa: E731
    before = len(mine())
    cpcheck.run(ask)
    assert len(mine()) == before + 1 and "Current and Pending" in mine()[-1].subject
    c = CurrentPendingCheck.objects.get(assignment=a)

    def at(day):  # pretend the last e-mail went out on `day`
        when = timezone.make_aware(dt.datetime.combine(day, dt.time(9)))
        CurrentPendingCheck.objects.filter(pk=c.pk).update(last_emailed_at=when)

    # last e-mailed Feb 1: nothing on Feb 4; a reminder on Feb 5
    at(ask)
    cpcheck.run(ask + timedelta(days=3))
    assert len(mine()) == before + 1
    cpcheck.run(ask + timedelta(days=4))
    assert len(mine()) == before + 2
    # after the due date: daily, until March 1
    at(due)
    cpcheck.run(due + timedelta(days=1))
    assert len(mine()) == before + 3
    at(stop - timedelta(days=1))
    assert cpcheck.run(stop) == 0


def test_no_changes_is_one_click_and_shown_on_my_tasks(client, fall):
    a, u = _turn_in(fall)
    cpcheck.run(cpcheck.dates(fall.grant_year)[0])
    c = CurrentPendingCheck.objects.get(assignment=a)
    client.force_login(u)
    assert f"/tasks/current-pending/{c.pk}/" in client.get("/tasks/").content.decode()
    client.post(f"/tasks/current-pending/{c.pk}/", {"action": "nochange"})
    c.refresh_from_db()
    assert c.answered_at and c.changed is False
    assert f"/tasks/current-pending/{c.pk}/" not in client.get("/tasks/").content.decode()
    # answered: no more e-mails to them
    n = sum(1 for m in mail.outbox if m.to == [a.person.primary_email])
    cpcheck.run(cpcheck.dates(fall.grant_year)[1] + timedelta(days=1))
    assert sum(1 for m in mail.outbox if m.to == [a.person.primary_email]) == n


def test_changed_needs_a_certified_pdf_which_replaces_the_fall_copy(client, fall):
    a, u = _turn_in(fall)
    cpcheck.run(cpcheck.dates(fall.grant_year)[0])
    c = CurrentPendingCheck.objects.get(assignment=a)
    client.force_login(u)
    # an uncertified copy is refused with the reason
    r = client.post(
        f"/tasks/current-pending/{c.pk}/",
        {
            "action": "changed",
            "file-current_pending": SimpleUploadedFile(
                "cp.pdf", _pdf(CPOS.replace("Certified by", "Previewed by")), "application/pdf"
            ),
        },
    )
    assert "isn’t certified" in r.content.decode()
    c.refresh_from_db()
    assert c.answered_at is None
    r = client.post(
        f"/tasks/current-pending/{c.pk}/",
        {
            "action": "changed",
            "file-current_pending": SimpleUploadedFile("cp2.pdf", _pdf(CPOS), "application/pdf"),
        },
    )
    c.refresh_from_db()
    assert c.changed and c.file.original_filename == "cp2.pdf"
    assert cpcheck.latest_file(a) == c.file
    # someone else can't open it
    other = User.objects.exclude(person=a.person).filter(person__isnull=False).first()
    client.force_login(other)
    assert client.get(f"/tasks/current-pending/{c.pk}/").status_code == 403
    # the evaluator sees "Updated" and gets the new copy
    client.force_login(User.objects.get(username="mwills"))
    tab = client.get(f"/manage/outcomes/?tab=rppr&year={fall.grant_year}").content.decode()
    assert "Updated " in tab and f"/files/{c.file.pk}/" in tab
    assert client.get(f"/files/{c.file.pk}/").status_code == 200
