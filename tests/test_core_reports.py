"""Core reports for core directors (MW 2026-11-08)."""

import pytest
from django.core.management import call_command

from apps.accounts.models import User
from apps.analytics import core_reports as cr
from apps.analytics.models import CoreReport
from apps.forms_engine.models import FormDefinition
from apps.reporting.models import ReportingPeriod


@pytest.fixture
def demo(db):
    call_command("seed", "--fictional", verbosity=0)
    fd = FormDefinition.objects.get(code="bn_core_survey")
    p = ReportingPeriod.objects.filter(assignments__form_definition=fd).distinct().first()
    return fd, p


def _director_of(core_id, other=False):
    for u in User.objects.all():
        ids = cr.directed_core_ids(u)
        if ids and ((core_id in ids) != other):
            return u
    raise AssertionError("no such core director in the demo data")


def test_nothing_before_release(client, demo):
    fd, p = demo
    director = _director_of(fd.about_core_id)
    cr.get(fd, p)
    client.force_login(director)
    assert client.get("/core-reports/").status_code == 200
    report = CoreReport.objects.get(form_definition=fd, reporting_period=p)
    assert client.get(f"/core-reports/{report.pk}/").status_code == 403


def test_release_needs_a_closed_session(client, demo):
    fd, p = demo
    client.force_login(User.objects.get(username="mwills"))
    url = f"/manage/results/{p.short_label}/{fd.code}/core-report/save/"
    client.post(url, {"action": "release", "reflections": "Strong year."})
    assert CoreReport.objects.get(form_definition=fd, reporting_period=p).released_at is None


def test_release_shows_only_kept_answers_and_never_names(client, demo):
    fd, p = demo
    from django.utils import timezone

    p.status = "closed"
    p.closed_at = timezone.now()
    p.save()
    written = cr.written_answers(fd, p)
    first = written[0]["answers"][0]
    client.force_login(User.objects.get(username="mwills"))
    page = client.get(f"/manage/results/{p.short_label}/{fd.code}/core-report/").content.decode()
    assert "Hold back" in page and "Your reflections" in page
    client.post(
        f"/manage/results/{p.short_label}/{fd.code}/core-report/save/",
        {
            "action": "release",
            "reflections": "The core’s new scheduling worked well.",
            "hide": [str(first["id"])],
        },
    )
    report = CoreReport.objects.get(form_definition=fd, reporting_period=p)
    assert report.released_at and report.release_count == 1
    kept = [t for g in report.released_content["written"] for t in g["answers"]]
    total = sum(len(g["answers"]) for g in written)
    assert len(kept) == total - 1  # the held-back answer stays out

    director = _director_of(fd.about_core_id)
    client.force_login(director)
    html = client.get(f"/core-reports/{report.pk}/").content.decode()
    assert "The core’s new scheduling worked well." in html
    assert html.count("crp-list") == len(report.released_content["written"])
    for a in fd.assignments.filter(reporting_period=p).select_related("person"):
        assert a.person.full_name not in html
    assert "Core reports" in client.get("/core-reports/").content.decode()

    other = _director_of(fd.about_core_id, other=True)
    client.force_login(other)
    assert client.get(f"/core-reports/{report.pk}/").status_code == 403


def test_small_group_gets_reflections_only(demo, settings):
    fd, p = demo
    settings.SMALL_N_THRESHOLD = 100
    report = cr.get(fd, p)
    report.reflections = "Only reflections this time."
    content = cr.draft_content(report)
    assert content["small"] and content["written"] == [] and content["themes"] == ""
    assert content["reflections"] == "Only reflections this time."


def test_changes_after_release_need_a_new_release(demo):
    fd, p = demo
    evaluator = User.objects.get(username="mwills")
    report = cr.get(fd, p)
    cr.release(evaluator, report)
    assert not cr.changed_since_release(report)
    report.reflections = "An added thought."
    report.save()
    assert cr.changed_since_release(report)
    cr.withdraw(evaluator, report)
    assert report.released_at is None


def test_members_are_told_in_the_survey_purpose():
    from apps.common.templatetags.cnap import form_purpose

    for code in ("bn_core_survey", "cn_core_survey", "ni_core_survey"):
        assert (
            "Core directors receive a report of combined answers and written comments, without names."
            in form_purpose(code)
        )
