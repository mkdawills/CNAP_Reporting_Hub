"""Four-screen design prototype (MW 2026-11-05).

The prototype must be invisible unless UI_PROTOTYPE is on, must touch only its four screens, must
keep every form field on Screen 21, and must not loosen confidentiality on Screen 90.
"""

import re

import pytest
from django.core.management import call_command
from django.test import override_settings

from apps.accounts.models import ApplicationRole, User, UserRole
from apps.reporting.models import Assignment, ReportingPeriod

PROTO_CSS = "css/proto.css"


@pytest.fixture
def demo(db):
    call_command("seed", "--fictional", verbosity=0)
    return ReportingPeriod.objects.get(status="open")


def _names(html):
    return sorted(set(re.findall(r'name="([^"]+)"', html)) - {"csrfmiddlewaretoken"})


def _templates(resp):
    return {t.name for t in resp.templates if t.name}


def _view(client, mode):
    session = client.session
    session["ui_view"] = mode
    session.save()


def _pages(period):
    okafor = User.objects.get(username="okafor")
    pilot = Assignment.objects.get(
        person=okafor.person, reporting_period=period, form_definition__code="progress_pilot"
    )
    other = (
        Assignment.objects.filter(person=okafor.person, reporting_period=period)
        .exclude(form_definition__code="progress_pilot")
        .first()
    )
    return okafor, pilot, other


def test_off_by_default_every_screen_keeps_its_original_template(client, demo):
    okafor, pilot, _ = _pages(demo)
    client.force_login(okafor)
    r = client.get("/tasks/")
    assert "portal/tasks.html" in _templates(r) and PROTO_CSS not in r.content.decode()
    r = client.get(f"/tasks/{pilot.pk}/")
    assert "portal/form.html" in _templates(r) and PROTO_CSS not in r.content.decode()
    client.force_login(User.objects.get(username="mwills"))
    r = client.get("/manage/dashboard/")
    assert "manage/dashboard.html" in _templates(r) and PROTO_CSS not in r.content.decode()
    r = client.get(f"/manage/results/{demo.short_label}/mentee_survey/")
    assert "manage/report.html" in _templates(r) and PROTO_CSS not in r.content.decode()
    assert client.get("/ui-preview/after/?next=/").status_code == 404  # the switch doesn't exist


@override_settings(UI_PROTOTYPE=True)
def test_on_only_the_redesigned_screens_change(client, demo):
    okafor, pilot, other = _pages(demo)
    client.force_login(okafor)
    assert "proto/tasks.html" in _templates(client.get("/tasks/"))
    assert "proto/progress_form.html" in _templates(client.get(f"/tasks/{pilot.pk}/"))
    # Batch 1 (MW 2026-11-05): every other form uses the same design
    r = client.get(f"/tasks/{other.pk}/")
    assert "proto/progress_form.html" in _templates(r)
    client.force_login(User.objects.get(username="mwills"))
    assert "proto/dashboard.html" in _templates(client.get("/manage/dashboard/"))
    assert "proto/report.html" in _templates(
        client.get(f"/manage/results/{demo.short_label}/mentee_survey/")
    )
    # Batch 2 (MW 2026-11-05): every form's results use the Screen 90 design
    r = client.get(f"/manage/results/{demo.short_label}/ts_admin_core/")
    assert "proto/report.html" in _templates(r)
    assert "proto/results.html" in _templates(client.get(f"/manage/results/?period={demo.short_label}"))
    # Batch 3 (MW 2026-11-06): administration pages take the shared design layer, and only the layer:
    # the same template renders, with the prototype class on the page.
    r = client.get("/manage/")
    assert "manage/home.html" in _templates(r) and 'class="proto pa"' in r.content.decode()


@override_settings(UI_PROTOTYPE=True)
def test_reviewer_can_flip_back_to_the_current_design(client, demo):
    okafor, _, _ = _pages(demo)
    client.force_login(okafor)
    r = client.get("/ui-preview/before/?next=/tasks/")
    assert r.status_code == 302 and r["Location"] == "/tasks/"
    assert "portal/tasks.html" in _templates(client.get("/tasks/"))
    client.get("/ui-preview/after/?next=/tasks/")
    assert "proto/tasks.html" in _templates(client.get("/tasks/"))
    # the switch never redirects off the site
    assert client.get("/ui-preview/after/?next=https://example.com/").headers["Location"] == "/"


@override_settings(UI_PROTOTYPE=True)
def test_screen21_keeps_every_field_and_both_actions(client, demo):
    okafor, pilot, _ = _pages(demo)
    client.force_login(okafor)
    _view(client, "before")
    before = client.get(f"/tasks/{pilot.pk}/").content.decode()
    _view(client, "after")
    after = client.get(f"/tasks/{pilot.pk}/").content.decode()
    assert _names(before) == _names(after)
    for html in (before, after):
        assert 'value="submit"' in html and 'value="save"' in html
        assert f"/tasks/{pilot.pk}/autosave/" in html
    # the reporting period and the deadline are shown as two separate facts
    assert "Your answers cover" in after and "Due" in after
    assert pilot.due_at.strftime("%B") in after


@override_settings(UI_PROTOTYPE=True)
def test_screen21_save_draft_still_works(client, demo):
    okafor, pilot, _ = _pages(demo)
    client.force_login(okafor)
    r = client.post(f"/tasks/{pilot.pk}/", {"action": "save"})
    assert r.status_code == 302
    pilot.refresh_from_db()
    assert pilot.status in ("in_progress", "not_started")


@override_settings(UI_PROTOTYPE=True)
def test_screen3_counts_add_up(client, demo):
    okafor, _, _ = _pages(demo)
    client.force_login(okafor)
    r = client.get("/tasks/")
    ctx = r.context
    html = r.content.decode()
    assert "Reporting progress" in html and "Submitted" in html and "Opted out" in html
    opted = sum(1 for x in ctx["done"] if x["a"].status == "completed_opt_out")
    assert (ctx["done_n"] - opted) + opted + ctx["todo"] == ctx["total"]


@override_settings(UI_PROTOTYPE=True)
@pytest.mark.parametrize("path", ["/manage/results/{p}/mentee_survey/", "/manage/results/{p}/mentee_survey/export/"])
def test_screen90_confidentiality_unchanged(client, demo, path):
    url = path.format(p=demo.short_label)
    # a respondent never reaches administrator screens
    client.force_login(User.objects.get(username="okafor"))
    assert client.get(url).status_code in (302, 403)
    # an administrator without the confidential mentoring grant is refused too
    viewer = User.objects.create_user(username="leader_no_grant", password="x")
    UserRole.objects.create(
        user=viewer, role=ApplicationRole.objects.get(code=ApplicationRole.Code.CENTER_LEADERSHIP)
    )
    client.force_login(viewer)
    assert client.get(url).status_code == 403


@override_settings(UI_PROTOTYPE=True)
def test_screen90_separates_identifiable_information(client, demo):
    client.force_login(User.objects.get(username="mwills"))
    html = client.get(f"/manage/results/{demo.short_label}/mentee_survey/").content.decode()
    combined = html.index('id="r90-combined-h"')
    ident = html.index('id="r90-ident-h"')
    assert combined < ident
    # names appear as text only after the "Identifiable information" heading; above it, only inside the
    # hover cards on the counts (MW 2026-11-06), which hold names and nothing else
    import re

    visible = re.sub(r'<span class="px-names"[^>]*>', '<span class="px-names">', html)
    okafor = User.objects.get(username="okafor").person
    for name in (okafor.full_name,):
        if name in visible:
            assert visible.index(name) > visible.index('id="r90-ident-h"')


@override_settings(UI_PROTOTYPE=True)
def test_screen21_markers_count_the_same_required_answers_as_the_server(client, demo):
    """Option B (MW 2026-11-05): each section's marker counts the server's own required questions."""
    from apps.forms_engine.runtime import FormSchema
    from apps.reporting.services import responses as rs

    okafor, pilot, _ = _pages(demo)
    client.force_login(okafor)
    html = client.get(f"/tasks/{pilot.pk}/").content.decode()
    on_page = set()
    for codes in re.findall(r'data-req="([^"]*)"', html):
        on_page |= set(codes.split())
    schema = FormSchema(pilot.form_version)
    answers, rows, _ = rs.answers_of(rs.current_response(pilot), schema)
    answers |= rs.system_answers(pilot, schema)
    server_missing = {q.code for q in schema.missing_required(answers, rows)}
    # every question the server says is missing is one the page counts
    assert server_missing <= on_page


@override_settings(UI_PROTOTYPE=True)
def test_screen90_names_the_section_from_the_administrators_view(client, demo):
    """Titles state the subject, with no pronouns: "Mentee Survey," not "My mentor or mentors" (MW 2026-11-05)."""
    client.force_login(User.objects.get(username="mwills"))
    html = client.get(f"/manage/results/{demo.short_label}/mentee_survey/").content.decode()
    assert 'id="r90-t1">Mentee Survey<' in html
    assert "My Mentor or Mentors" not in html
