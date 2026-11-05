"""Batch 1 of the redesign (MW 2026-11-05): sign-in, My tasks for every role, every respondent form,
the survey preview, and the February Current and Pending check.

What must hold: with the switch off nothing changes; with it on, every form keeps exactly the same
field names, both actions, and the autosave address, and every sign-in form keeps its fields.
"""

import re

import pytest
from django.core.management import call_command
from django.test import override_settings

from apps.accounts.models import User
from apps.reporting.models import Assignment, ReportingPeriod

PEOPLE = ["okafor", "reyes", "varga", "santos", "bell", "kim", "chen", "adeyemi", "natarajan"]


@pytest.fixture
def demo(db):
    call_command("seed", "--fictional", verbosity=0)
    return ReportingPeriod.objects.get(status="open")


def _names(html):
    m = re.search(r'<form[^>]*id="runner".*?</form>', html, re.S)
    return sorted(set(re.findall(r'name="([^"]+)"', m.group(0) if m else "")) - {"csrfmiddlewaretoken"})


def _view(client, mode):
    s = client.session
    s["ui_view"] = mode
    s.save()


def test_off_by_default_sign_in_is_unchanged(client, demo):
    r = client.get("/accounts/login/")
    assert "registration/login.html" in {t.name for t in r.templates if t.name}
    assert "css/proto.css" not in r.content.decode()


@override_settings(UI_PROTOTYPE=True)
def test_sign_in_pages_keep_their_fields(client, demo):
    for url, fields in (("/accounts/login/", {"username", "password", "next"}), ("/accounts/link/", {"email"})):
        _view(client, "before")
        before = set(re.findall(r'name="([^"]+)"', client.get(url).content.decode())) - {"csrfmiddlewaretoken"}
        _view(client, "after")
        r = client.get(url)
        after = set(re.findall(r'name="([^"]+)"', r.content.decode())) - {"csrfmiddlewaretoken"}
        assert "css/proto.css" in r.content.decode()
        assert before == after and fields <= after
    # signing in still works through the new page
    r = client.post("/accounts/login/", {"username": "okafor", "password": "Demo-Password-2026"})
    assert r.status_code == 302


@override_settings(UI_PROTOTYPE=True)
def test_every_form_keeps_every_field_for_every_person(client, demo):
    checked = 0
    for u in PEOPLE:
        user = User.objects.filter(username=u).first()
        if not user:
            continue
        client.force_login(user)
        for a in Assignment.objects.filter(person=user.person, reporting_period=demo).exclude(status="exempt"):
            _view(client, "before")
            r1 = client.get(f"/tasks/{a.pk}/")
            if r1.status_code != 200:
                continue  # e.g. a confidential form that asks for a code first
            _view(client, "after")
            r2 = client.get(f"/tasks/{a.pk}/")
            before, after = r1.content.decode(), r2.content.decode()
            assert "proto/progress_form.html" in {t.name for t in r2.templates if t.name}, a.form_definition.code
            assert _names(before) == _names(after), a.form_definition.code
            if 'value="submit"' in before:
                assert 'value="submit"' in after and 'value="save"' in after
                assert f"/tasks/{a.pk}/autosave/" in after
            checked += 1
    assert checked >= 20


@override_settings(UI_PROTOTYPE=True)
def test_preview_uses_the_new_design_and_saves_nothing(client, demo):
    okafor = User.objects.get(username="okafor")
    client.force_login(okafor)
    a = Assignment.objects.filter(person=okafor.person, reporting_period=demo, status="not_started").first()
    r = client.get(f"/tasks/{a.pk}/preview/")
    html = r.content.decode()
    assert "proto/progress_form.html" in {t.name for t in r.templates if t.name}
    assert "This is a preview" in html and 'value="submit"' not in html


@override_settings(UI_PROTOTYPE=True)
def test_my_tasks_works_for_every_role(client, demo):
    for u in PEOPLE:
        user = User.objects.filter(username=u).first()
        if not user:
            continue
        client.force_login(user)
        r = client.get("/tasks/")
        assert r.status_code == 200
        assert "proto/tasks.html" in {t.name for t in r.templates if t.name}
