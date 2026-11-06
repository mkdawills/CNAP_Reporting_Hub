"""Batch 2 of the redesign (MW 2026-11-05): results pages and Center results.

What must hold:
- With the switch off, nothing changes.
- With it on, every results table keeps exactly the same numbers, in the same order, as the
  current design: the results tables' data presentation is unchanged (MW 2026-11-05).
- Who sees what is unchanged: respondents never reach the administrator results; a de-identified
  response never shows the respondent's name or project; confidential mentoring results stay closed
  to anyone without that access.
"""

import re
from html import unescape

import pytest
from django.core.management import call_command
from django.test import override_settings

from apps.accounts.models import User
from apps.reporting.models import Assignment, ReportingPeriod


@pytest.fixture
def demo(db):
    call_command("seed", "--fictional", verbosity=0)
    return ReportingPeriod.objects.get(status="open")


def _view(client, mode):
    s = client.session
    s["ui_view"] = mode
    s.save()


def _templates(r):
    return {t.name for t in r.templates if t.name}


def _tables(html):
    """Every cell of every results table (item-by-item and year-by-year), in order, as plain text."""
    out = []
    for cls, body in re.findall(r'<table class="(reptab|lontab)"[^>]*>(.*?)</table>', html, re.S):
        cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", body, re.S)
        out.append((cls, [" ".join(unescape(re.sub(r"<[^>]+>", " ", c)).split()) for c in cells]))
    return out


def test_off_by_default_results_are_unchanged(client, demo):
    client.force_login(User.objects.get(username="mwills"))
    assert "manage/results.html" in _templates(client.get(f"/manage/results/?period={demo.short_label}"))
    r = client.get(f"/manage/results/{demo.short_label}/ts_admin_core/")
    assert "manage/report.html" in _templates(r) and "css/proto.css" not in r.content.decode()


@override_settings(UI_PROTOTYPE=True)
def test_every_results_table_keeps_the_same_numbers(client, demo):
    client.force_login(User.objects.get(username="mwills"))
    codes = sorted(set(Assignment.objects.filter(reporting_period=demo).values_list("form_definition__code", flat=True)))
    finalized = ReportingPeriod.objects.filter(status="finalized").order_by("-display_order").first()
    checked = 0
    pages = [(demo.short_label, c) for c in codes] + ([(finalized.short_label, "bn_core_survey")] if finalized else [])
    for label, code in pages:
        url = f"/manage/results/{label}/{code}/"
        _view(client, "before")
        before = client.get(url)
        _view(client, "after")
        after = client.get(url)
        assert before.status_code == after.status_code == 200, url
        assert "proto/report.html" in _templates(after)
        assert _tables(before.content.decode()) == _tables(after.content.decode()), url
        checked += len(_tables(after.content.decode()))
    assert checked > 0


@override_settings(UI_PROTOTYPE=True)
def test_center_results_keep_the_same_numbers(client, demo):
    client.force_login(User.objects.get(username="okafor"))
    for url in ["/results/", "/results/?view=products"]:
        _view(client, "before")
        before = client.get(url).content.decode()
        _view(client, "after")
        r = client.get(url)
        assert "proto/center_results.html" in _templates(r)
        assert _tables(before) == _tables(r.content.decode()), url
    # respondents see counts only, never titles or names of the Center's products
    html = client.get("/results/?view=products").content.decode()
    assert "Titles, names, and proposal details stay private." in html and 'id="r33-papers"' not in html


@override_settings(UI_PROTOTYPE=True)
def test_respondents_never_reach_administrator_results(client, demo):
    client.force_login(User.objects.get(username="okafor"))
    assert client.get(f"/manage/results/?period={demo.short_label}").status_code in (302, 403)
    assert client.get(f"/manage/results/{demo.short_label}/ts_admin_core/").status_code in (302, 403)


@override_settings(UI_PROTOTYPE=True)
def test_a_deidentified_response_shows_no_name_or_project(client, demo):
    client.force_login(User.objects.get(username="hbailey"))
    html = client.get(f"/manage/results/{demo.short_label}/bn_core_survey/").content.decode()
    m = re.search(r'href="/manage/responses/(\d+)/"', html)
    if not m:
        pytest.skip("fewer than 5 people completed this survey in the sample data")
    a = Assignment.objects.select_related("person", "project").get(pk=m.group(1))
    r = client.get(f"/manage/responses/{a.pk}/")
    assert "proto/progress_form.html" in _templates(r)
    page = r.content.decode()
    assert "De-identified response." in page
    for t in [a.person.first_name, a.person.last_name] + ([a.project.title] if a.project_id else []):
        assert t not in page, t
    # the results page lists respondents by number, never by name
    assert a.person.last_name not in html and "Respondent 1" in html


@override_settings(UI_PROTOTYPE=True)
def test_one_response_keeps_every_answer(client, demo):
    """Screen 66: the same questions and the same answers, read-only, in the form design."""
    client.force_login(User.objects.get(username="mwills"))
    a = Assignment.objects.filter(reporting_period=demo, status="submitted").first()
    url = f"/manage/responses/{a.pk}/"
    _view(client, "before")
    before = client.get(url).content.decode()
    _view(client, "after")
    after = client.get(url).content.decode()
    names = lambda h: sorted(set(re.findall(r'name="(q-[^"]+)"', h)))
    checked = lambda h: sorted(set(re.findall(r'name="(q-[^"]+)"[^>]*value="([^"]*)"[^>]*checked', h)))
    assert names(before) == names(after) and checked(before) == checked(after)
    assert "Back to the results" in after and "Edit my answers" not in after


@override_settings(UI_PROTOTYPE=True)
def test_confidential_mentoring_results_stay_closed(client, demo):
    """An administrator without the confidential mentoring permission can't open mentoring results."""
    from apps.accounts.models import ApplicationRole, UserRole

    u = User.objects.create_user(username="sample_admin", password="Demo-Password-2026", email="sample_admin@example.org")
    UserRole.objects.create(user=u, role=ApplicationRole.objects.get(code=ApplicationRole.Code.ADMINISTRATOR))
    assert not u.has_confidential_mentoring_access()
    client.force_login(u)
    assert client.get(f"/manage/results/{demo.short_label}/mentee_survey/").status_code == 403
    html = client.get(f"/manage/results/?period={demo.short_label}").content.decode()
    assert "Confidential: no access" in html


# ------------------------------------------------------------------ Excel downloads (MW 2026-11-05)
def _xlsx(resp):
    import io

    from openpyxl import load_workbook

    assert resp.status_code == 200 and "spreadsheetml" in resp["Content-Type"]
    return load_workbook(io.BytesIO(resp.content))


def _all_text(wb):
    return " ".join(str(v) for ws in wb.worksheets for row in ws.iter_rows(values_only=True) for v in row if v is not None)


def test_answers_download_follows_who_may_read_them(client, demo):
    from apps.common.enums import COMPLETE_STATUSES

    url = f"/manage/results/{demo.short_label}/bn_core_survey/answers.xlsx"
    done = Assignment.objects.filter(reporting_period=demo, form_definition__code="bn_core_survey", status__in=COMPLETE_STATUSES).select_related("person", "project")
    # the evaluator: with names, one row per completed response
    client.force_login(User.objects.get(username="mwills"))
    text = _all_text(_xlsx(client.get(url)))
    assert all(a.person.last_name in text for a in done)
    # the Director: numbered respondents, no names, no projects (when at least 5 completed)
    client.force_login(User.objects.get(username="hbailey"))
    wb = _xlsx(client.get(url))
    text = _all_text(wb)
    if done.count() >= 5:
        assert "Respondent 1" in text
    for a in done:
        assert a.person.last_name not in text and a.person.first_name not in text
        if a.project_id:
            assert a.project.title not in text
    # respondents never download anyone's answers
    client.force_login(User.objects.get(username="okafor"))
    assert client.get(url).status_code == 403
    assert client.get(f"/manage/results/{demo.short_label}/everything.xlsx").status_code in (302, 403)


def test_excel_tables_hold_exactly_the_csv_cells(client, demo):
    import csv
    import io

    client.force_login(User.objects.get(username="mwills"))
    for url in [f"/manage/results/{demo.short_label}/bn_core_survey/export/", "/manage/outcomes/export/grants/"]:
        rows = [r for r in csv.reader(io.StringIO(client.get(url).content.decode("utf-8-sig")))]
        wb = _xlsx(client.get(url + "?format=xlsx"))
        got = [[("" if v is None else str(v)) for v in row] for row in wb.active.iter_rows(min_row=3, values_only=True)]
        norm = lambda r: [c.lstrip("'") for c in r]
        want = [r + [""] * (max(len(g) for g in got) - len(r)) for r in rows]
        def canon(c):  # numbers compare as numbers ("1250000.00" in the CSV is 1250000 in Excel)
            try:
                return float(c)
            except ValueError:
                return c

        strip = lambda t: [[canon(c) for c in norm(r)] for r in t]
        assert strip([g[: len(w)] for g, w in zip(got, want)]) == strip([w[: len(w)] for w in want])


def test_confidential_answers_download_stays_closed(client, demo):
    from apps.accounts.models import ApplicationRole, UserRole

    u = User.objects.create_user(username="sample_admin2", password="Demo-Password-2026", email="sample_admin2@example.org")
    UserRole.objects.create(user=u, role=ApplicationRole.objects.get(code=ApplicationRole.Code.ADMINISTRATOR))
    client.force_login(u)
    assert client.get(f"/manage/results/{demo.short_label}/mentee_survey/answers.xlsx").status_code == 403
    text = _all_text(_xlsx(client.get(f"/manage/results/{demo.short_label}/everything.xlsx")))
    assert "Mentee Survey" in text and "Not included" in text


# ------------------------------------------------------------------ Word and PDF copies (MW 2026-11-05)
def _pdf_text(resp):
    import io

    from pypdf import PdfReader

    assert resp.status_code == 200 and resp["Content-Type"] == "application/pdf"
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(resp.content)).pages)


def _docx_text(resp):
    import io

    from docx import Document

    assert resp.status_code == 200 and "wordprocessingml" in resp["Content-Type"]
    d = Document(io.BytesIO(resp.content))
    return "\n".join([p.text for p in d.paragraphs] + [c.text for t in d.tables for r in t.rows for c in r.cells])


def test_people_print_their_own_forms_and_no_one_elses(client, demo):
    okafor = User.objects.get(username="okafor")
    client.force_login(okafor)
    a = Assignment.objects.filter(person=okafor.person, status="submitted").first()
    text = _pdf_text(client.get(f"/tasks/{a.pk}/print/"))
    assert a.form_definition.name.split(" (")[0] in text and okafor.person.full_name in text
    assert "Version" in _docx_text(client.get(f"/tasks/{a.pk}/print/?blank=1&fmt=docx"))
    _pdf_text(client.get(f"/tasks/{a.pk}/print/?blank=1"))
    _docx_text(client.get(f"/tasks/{a.pk}/print/?fmt=docx"))
    other = Assignment.objects.exclude(person=okafor.person).filter(reporting_period=demo).first()
    assert client.get(f"/tasks/{other.pk}/print/").status_code in (403, 404)


def test_printed_copies_follow_who_may_read_them(client, demo):
    from apps.common.enums import COMPLETE_STATUSES

    done = Assignment.objects.filter(reporting_period=demo, form_definition__code="bn_core_survey", status__in=COMPLETE_STATUSES).select_related("person", "project")
    client.force_login(User.objects.get(username="hbailey"))
    r = client.get(f"/manage/results/{demo.short_label}/bn_core_survey/print/")
    if done.count() < 5:
        assert r.status_code == 403
        return
    for text in (_pdf_text(r), _docx_text(client.get(f"/manage/results/{demo.short_label}/bn_core_survey/print/?fmt=docx"))):
        assert "Respondent 1" in text
        for a in done:
            assert a.person.last_name not in text and a.person.first_name not in text
            if a.project_id:
                assert a.project.title not in text
    one = done.first()
    text = _pdf_text(client.get(f"/manage/responses/{one.pk}/print/"))
    assert one.person.last_name not in text and "Respondent" in text
    # respondents never print the Center's copies
    client.force_login(User.objects.get(username="okafor"))
    assert client.get(f"/manage/results/{demo.short_label}/bn_core_survey/print/").status_code in (302, 403)
    assert client.get(f"/manage/responses/{one.pk}/print/").status_code in (302, 403)


def test_confidential_forms_print_only_with_that_access(client, demo):
    from apps.accounts.models import ApplicationRole, UserRole

    u = User.objects.create_user(username="sample_admin3", password="Demo-Password-2026", email="sample_admin3@example.org")
    UserRole.objects.create(user=u, role=ApplicationRole.objects.get(code=ApplicationRole.Code.ADMINISTRATOR))
    client.force_login(u)
    assert client.get(f"/manage/results/{demo.short_label}/mentee_survey/print/").status_code == 403
    assert client.get(f"/manage/results/{demo.short_label}/mentee_survey/print/?blank=1").status_code == 403
    m = Assignment.objects.filter(reporting_period=demo, form_definition__code="mentee_survey", status="submitted").first()
    if m:
        assert client.get(f"/manage/responses/{m.pk}/print/").status_code == 403


# ------------------------------------------------------------------ Research outputs: years and cores (MW 2026-11-06)
@override_settings(UI_PROTOTYPE=True)
def test_research_outputs_for_any_combination_of_years(client, demo):
    from apps.outcomes import snapshot
    from apps.outcomes.rppr import current_year

    now = current_year()
    client.force_login(User.objects.get(username="okafor"))
    one = client.get(f"/results/?view=products&years={now}").context
    old = client.get(f"/results/?view=products&year={now}").context  # the older link still works
    assert one["prod"]["submitted"] == old["prod"]["submitted"] and one["span"] == f"Year {now}"
    years = list(one["years"])
    r = client.get("/results/?view=products&years=all").context
    assert r["chosen"] == sorted(years)
    # totals for several years equal the sum of each year on its own
    each = [snapshot.products(y) for y in years]
    assert r["prod"]["submitted"] == sum(p["submitted"] for p in each)
    assert r["prod"]["n_papers"] == sum(len(p["papers"]) for p in each)
    # unknown years are ignored, never an error
    assert client.get("/results/?view=products&years=1999&years=abc").status_code == 200
    # respondents still see counts only, never titles
    html = client.get("/results/?view=products&years=all").content.decode()
    assert 'id="r33-papers"' not in html and "Which cores the products drew on" in html


def test_core_counts_skip_resources_only_planned(demo):
    from apps.outcomes import snapshot
    from apps.outcomes.models import GrantSubmission, GrantSubmissionResource
    from apps.outcomes.rppr import current_year
    from apps.people.models import Resource

    now = current_year()
    before = {k["key"]: k for k in snapshot.by_core([now])}
    g = GrantSubmission.objects.filter(submission_date__isnull=False).exclude(status="planned").first()
    if g is None:
        pytest.skip("no submitted proposal in the sample data")
    admin = Resource.objects.get(code="admin_core")
    GrantSubmissionResource.objects.create(grant_submission=g, resource=admin, is_anticipated=True)
    after = {k["key"]: k for k in snapshot.by_core([now])}
    count = lambda k, code: next((s["n"] for s in k["segments"] if s["code"] == code), 0)
    assert count(after["proposals"], "admin_core") == count(before["proposals"], "admin_core")
    # every product is counted at least once; the longest bar is full width
    for k in after.values():
        assert k["mentions"] >= k["total"]
    assert max(k["scale"] for k in after.values()) in (0, 100)


@override_settings(UI_PROTOTYPE=True)
def test_names_on_hover_only_where_names_are_allowed(client, demo):
    """Point to a count to see who is behind it (MW 2026-11-06): the evaluator yes; de-identified readers never."""
    url = f"/manage/results/{demo.short_label}/bn_core_survey/"
    client.force_login(User.objects.get(username="mwills"))
    assert 'class="px-names"' in client.get(url).content.decode()
    client.force_login(User.objects.get(username="hbailey"))
    html = client.get(url).content.decode()
    assert 'class="px-names"' not in html and "data-names" not in html
