"""Below the tasks: the Center's output this year and helpful documents (MW 2026-10-28)."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from apps.accounts.models import User
from apps.outcomes import snapshot
from apps.reporting.models import HelpfulDocument


@pytest.fixture
def center(db):
    call_command("seed", "--fictional", verbosity=0)


def test_strip_counts_this_budget_year(client, center):
    from apps.outcomes.models import Presentation
    from apps.outcomes.rppr import current_year, period

    start, end = period(current_year())
    n = Presentation.objects.filter(
        presented_on__range=(start, end), archived_at__isnull=True
    ).count()
    assert snapshot.this_year()["talks"] == n
    client.force_login(User.objects.get(username="okafor"))
    html = client.get("/tasks/").content.decode()
    assert "What CNAP produced this year" in html and "submitted</span>" in html


def test_evaluator_adds_a_document_everyone_sees(client, center):
    client.force_login(User.objects.get(username="mwills"))
    client.post(
        "/manage/documents/add/",
        {
            "title": "PL Guidelines",
            "note": "For project leaders",
            "file": SimpleUploadedFile("g.pdf", b"%PDF-1.4 x", "application/pdf"),
        },
    )
    d = HelpfulDocument.objects.get(title="PL Guidelines")
    client.post("/manage/documents/add/", {"title": "Bad", "url": "ftp://x"})
    assert not HelpfulDocument.objects.filter(title="Bad").exists()
    client.force_login(User.objects.get(username="okafor"))
    html = client.get("/tasks/").content.decode()
    assert "PL Guidelines" in html and f"/documents/{d.pk}/" in html
    assert client.get(f"/documents/{d.pk}/").status_code == 200
    # view-only administrators can't add or remove
    client.force_login(User.objects.get(username="hbailey"))
    assert client.post(f"/manage/documents/{d.pk}/remove/").status_code == 403
    client.force_login(User.objects.get(username="mwills"))
    client.post(f"/manage/documents/{d.pk}/remove/")
    d.refresh_from_db()
    assert not d.is_active
    client.force_login(User.objects.get(username="okafor"))
    assert f"/documents/{d.pk}/" not in client.get("/tasks/").content.decode()
    assert client.get(f"/documents/{d.pk}/").status_code == 404


def test_default_documents(client, center):
    call_command("add_default_documents", verbosity=0)
    call_command("add_default_documents", verbosity=0)  # twice: no duplicates
    assert HelpfulDocument.objects.filter(is_active=True).count() == 3
    client.force_login(User.objects.get(username="okafor"))
    html = client.get("/tasks/").content.decode()
    assert "CNAP Phase 2 PL Guidelines" in html and "https://www.k-state.edu/cnap/" in html


def test_welcome_ring_and_group_icons(client, center):
    client.force_login(User.objects.get(username="okafor"))
    html = client.get("/tasks/").content.decode()
    assert "Amara." in html and ('class="ring"' in html) and 'class="gicon"' in html
    assert any(g in html for g in ("Good morning", "Good afternoon", "Good evening"))


def test_answers_save_as_you_go(client, center):
    from apps.reporting.models import Assignment, ReportingPeriod
    from apps.reporting.services import assignments as asg
    from apps.reporting.services import responses as rs

    asg.generate(ReportingPeriod.objects.get(status="open"))
    u = User.objects.get(username="okafor")
    a = Assignment.objects.filter(person=u.person, form_definition__code="ts_admin_core").first()
    client.force_login(u)
    page = client.get(f"/tasks/{a.pk}/").content.decode()
    assert f"/tasks/{a.pk}/autosave/" in page and "unless it says optional" in page
    r = client.post(f"/tasks/{a.pk}/autosave/", {"q-item_01": "agree"})
    assert r.status_code == 200 and r.json()["ok"]
    from apps.forms_engine.runtime import FormSchema

    assert (
        rs.answers_of(rs.current_response(a), FormSchema(a.form_version))[0]["item_01"] == "agree"
    )
    other = User.objects.get(username="reyes")
    client.force_login(other)
    assert client.post(f"/tasks/{a.pk}/autosave/", {"q-item_01": "agree"}).status_code == 403


def test_year_by_year_counts_every_year_from_the_first(db):
    import datetime as dt

    from apps.outcomes import snapshot
    from apps.outcomes.models import Presentation
    from apps.outcomes.rppr import current_year, period

    assert snapshot.by_year() is None  # nothing earlier to compare
    gy = current_year()
    Presentation.objects.create(presentation_type="invited_talk", title="Older talk", presented_on=period(gy - 2)[0] + dt.timedelta(days=3))
    t = snapshot.by_year()
    assert t["years"] == [gy - 2, gy - 1, gy]
    talks = next(r for r in t["rows"] if r["key"] == "talks")
    assert [b["n"] for b in talks["bars"]] == [1, 0, 0] and talks["bars"][-1]["now"]
