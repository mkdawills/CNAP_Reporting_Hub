"""Yearly NIH documents, ORCID, research teams and table uploads (MW 2026-10-27)."""

import io
import zipfile

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from apps.accounts.models import User
from apps.people.models import PersonRelationship
from apps.people.services import SENIOR_KEY_TYPES, normalize_orcid
from apps.reporting.models import Assignment, ReportingPeriod
from apps.reporting.services import assignments as asg
from apps.reporting.services import responses as rs

PDF = b"%PDF-1.7\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@pytest.fixture
def center(db):
    call_command("seed", "--fictional", verbosity=0)
    fall = ReportingPeriod.objects.get(status="open")
    asg.generate(fall)
    return fall


def test_orcid_check_digit():
    assert normalize_orcid("0000-0002-1825-0097") == "0000-0002-1825-0097"
    assert normalize_orcid("https://orcid.org/0000-0002-1825-0097") == "0000-0002-1825-0097"
    assert normalize_orcid("0000000218250097") == "0000-0002-1825-0097"
    assert normalize_orcid("0000-0002-1694-233x") == "0000-0002-1694-233X"
    assert normalize_orcid("") == ""
    with pytest.raises(ValueError, match="typo"):
        normalize_orcid("0000-0002-1825-0098")
    with pytest.raises(ValueError, match="16 digits"):
        normalize_orcid("1234")


def test_assigned_once_a_year_to_senior_key_roles(center):
    assert center.sequence == 1
    got = set(
        Assignment.objects.filter(
            reporting_period=center, form_definition__code="nih_documents"
        ).values_list("person_id", flat=True)
    )
    want = set(
        PersonRelationship.objects.filter(
            relationship_type__code__in=SENIOR_KEY_TYPES,
            person__is_active=True,
            person__archived_at__isnull=True,
        )
        .filter(effective_to__isnull=True)
        .values_list("person_id", flat=True)
    )
    assert got and got == want
    # one per person, even with two qualifying roles
    assert Assignment.objects.filter(
        reporting_period=center, form_definition__code="nih_documents"
    ).count() == len(got)
    spring = ReportingPeriod.objects.filter(grant_year=center.grant_year, sequence=2).first()
    if spring:
        codes = {p.form_definition_id for p in asg.plan(spring)}
        nih = Assignment.objects.filter(form_definition__code="nih_documents").first()
        assert nih.form_definition_id not in codes


def _open(a):
    """Seeded answers are random; make sure the assignment a test uses is still open."""
    from apps.reporting.models import Response

    if a.status not in ("not_started", "in_progress"):
        Response.objects.filter(assignment=a).delete()
        Assignment.objects.filter(pk=a.pk).update(
            status="not_started", submitted_at=None, completion_pathway=None
        )
        a.refresh_from_db()
    return a


def _nih(center):
    a = (
        Assignment.objects.filter(reporting_period=center, form_definition__code="nih_documents")
        .select_related("person")
        .order_by("status", "pk")
        .first()
    )
    a = _open(a)
    return a, User.objects.get(person=a.person)


def test_pdf_only_and_must_really_be_pdf(center):
    a, u = _nih(center)
    errs = rs.save_draft(
        a, u, {}, {"file-biosketch": SimpleUploadedFile("bio.docx", b"PK..", "application/msword")}
    )
    assert any("Please upload a PDF" in e for e in errs)
    errs = rs.save_draft(
        a, u, {}, {"file-biosketch": SimpleUploadedFile("bio.pdf", b"not a pdf", "application/pdf")}
    )
    assert any("doesn’t look like a PDF" in e for e in errs)
    assert (
        rs.save_draft(
            a, u, {}, {"file-biosketch": SimpleUploadedFile("bio.pdf", PDF, "application/pdf")}
        )
        == []
    )


def test_d2a_yes_needs_an_explanation(center):
    from apps.forms_engine.runtime import FormSchema

    a, u = _nih(center)
    s = FormSchema(a.form_version)
    assert "d2a_explain" not in {q.code for q in s.missing_required({"d2a": "no"})}
    assert "d2a_explain" in {q.code for q in s.missing_required({"d2a": "yes"})}


def test_rppr_tab_lists_and_zip(client, center):
    a, u = _nih(center)
    files = {
        f"file-{c}": SimpleUploadedFile(f"{c}.pdf", PDF, "application/pdf")
        for c in ("biosketch", "current_pending", "mftrp_cert")
    }
    assert rs.save_draft(a, u, {"q-d2a": "yes", "q-d2a_explain": "Fewer months"}, files) == []
    rs.submit(a, u)
    client.force_login(User.objects.get(username="mwills"))
    html = client.get(f"/manage/outcomes/?tab=rppr&year={center.grant_year}").content.decode()
    assert "D.2 and NIH documents" in html and "Download all (zip)" in html
    assert "expects a 25% effort drop" in html
    r = client.get(f"/manage/outcomes/export/nihdocs/?year={center.grant_year}")
    assert r.status_code == 200 and r["Content-Type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    from apps.outcomes.nihdocs import safe_name

    last = safe_name(a.person.last_name)
    assert "summary.csv" in names
    assert safe_name("Tomás") == "Tomas"
    from apps.people.services import is_senior_key

    first = safe_name(a.person.first_name)
    assert f"{last}_{first}_CurrentandPending.pdf" in names
    assert z.read(f"{last}_{first}_CurrentandPending.pdf") == PDF
    # biosketch and MFTRP only for people named on the NoA; anyone else's stray upload is dropped
    noa = is_senior_key(a.person)
    assert (f"MFTRPcert_{last}_{first}.pdf" in names) is noa
    assert (f"{last}_{first}_Biosketch.pdf" in names) is noa
    assert "Fewer months" in z.read("summary.csv").decode("utf-8-sig")


def test_view_only_admin_cant_download_documents(client, center):
    from apps.admin_center.views.outcomes import _identified

    hb = User.objects.get(username="hbailey")
    client.force_login(hb)
    r = client.get(f"/manage/outcomes/export/nihdocs/?year={center.grant_year}")
    assert r.status_code == (200 if _identified(hb, "nih_documents") else 403)


def test_research_team_rows_feed_the_rppr_tab(client, center):
    a = (
        Assignment.objects.filter(reporting_period=center, form_definition__code="progress_core")
        .select_related("person")
        .order_by("pk")
        .first()
    )
    a = _open(a)
    u = User.objects.get(person=a.person)
    from apps.forms_engine.runtime import FormSchema

    team = next(sec for sec in FormSchema(a.form_version).sections if sec.code == "team")
    qs = {q.code: q for q in team.questions.all()}
    assert {"first_name", "last_name", "cal_months", "aca_months", "sum_months"} <= set(qs)
    post = {
        "rep-team-count": "1",
        "rep-team-0-first_name": "Sam",
        "rep-team-0-last_name": "Rivera",
        "rep-team-0-cal_months": "1.5",
    }
    rs.save_draft(a, u, post)
    from apps.outcomes import nihdocs

    t = [x for x in nihdocs.teams(center.grant_year) if x["a"].pk == a.pk]
    assert t and t[0]["people"][0]["last_name"] == "Rivera"
    client.force_login(User.objects.get(username="mwills"))
    r = client.get(f"/manage/outcomes/export/teams/?year={center.grant_year}")
    assert r.status_code == 200 and "Rivera" in r.content.decode()


def test_profile_orcid(client, center):
    a, u = _nih(center)
    client.force_login(u)
    assert 'name="orcid"' in client.get("/profile/").content.decode()
    client.post("/profile/", {"orcid": "0000-0002-1825-0098"})
    a.person.refresh_from_db()
    assert a.person.orcid == ""
    client.post("/profile/", {"orcid": "https://orcid.org/0000-0002-1825-0097"})
    a.person.refresh_from_db()
    assert a.person.orcid == "0000-0002-1825-0097"


def test_quick_rppr_items_flag_for_a_closer_look(center):
    from apps.forms_engine.runtime import FormSchema
    from apps.outcomes import nihdocs

    a = (
        Assignment.objects.filter(reporting_period=center, form_definition__code="progress_pilot")
        .select_related("person")
        .order_by("pk")
        .first()
    )
    a = _open(a)
    u = User.objects.get(person=a.person)
    s = FormSchema(a.form_version)
    codes = [c for c, _ in nihdocs.QUICK_ITEMS]
    all_no = {c: "no" for c in codes} | {"c5c": "yes"}
    assert "rppr_details" not in {q.code for q in s.missing_required(all_no)}
    assert "rppr_details" in {q.code for q in s.missing_required(all_no | {"c4": "yes"})}
    assert "rppr_details" in {q.code for q in s.missing_required(all_no | {"c5c": "no"})}
    rs.save_draft(
        a,
        u,
        {f"q-{c}": v for c, v in (all_no | {"c4": "yes"}).items()}
        | {
            "q-rppr_details": "C.4: a provisional patent",
            "q-proj_status": "ended",
            "q-ended_on": "2026-09-30",
        },
    )
    t = [x for x in nihdocs.teams(center.grant_year) if x["a"].pk == a.pk][0]
    assert t["flags"] == ["C.4 inventions, patents, licenses"] and "provisional" in t["details"]
    assert t["status"] == "ENDED AS OF 09/30/2026"


def test_mftrp_form_has_their_name_and_nih_file_name(client, center):
    import subprocess
    import tempfile

    a, u = _nih(center)
    client.force_login(u)
    page = client.get(f"/tasks/{a.pk}/").content.decode()
    assert f"/tasks/{a.pk}/mftrp-form/" in page and "NIH_Annual_MFTRP_Certification.docx" in page
    r = client.get(f"/tasks/{a.pk}/mftrp-form/")
    assert r.status_code == 200 and r["Content-Type"] == "application/pdf"
    assert 'filename="MFTRPcert_' in r["Content-Disposition"]
    with tempfile.NamedTemporaryFile(suffix=".pdf") as fh:
        fh.write(r.content)
        fh.flush()
        text = " ".join(
            subprocess.run(
                ["pdftotext", fh.name, "-"], capture_output=True, text=True
            ).stdout.split()
        )
    name = f"{a.person.first_name} {a.person.last_name}"
    assert (
        f"I, {name}, certify that, at the time of submission, I am not a party to a malign foreign talent recruitment program."
        in text
    )
    # someone else's task: refused
    other = User.objects.exclude(person=a.person).filter(person__isnull=False).first()
    client.force_login(other)
    assert client.get(f"/tasks/{a.pk}/mftrp-form/").status_code == 403


def test_biosketch_and_mftrp_only_for_people_named_on_the_noa(client, center):
    """MW 2026-10-27: everyone gives Current and Pending; only NoA-named people give a biosketch and MFTRP."""
    from apps.forms_engine.runtime import FormSchema
    from apps.people.services import is_senior_key

    rows = list(
        Assignment.objects.filter(reporting_period=center, form_definition__code="nih_documents")
        .select_related("person")
        .order_by("pk")
    )
    rpl = next(
        a
        for a in rows
        if a.person.relationships.filter(relationship_type__code="project_leader").exists()
    )
    other = next(
        a
        for a in rows
        if not a.person.relationships.filter(
            relationship_type__code__in=("project_leader", "pd_pi")
        ).exists()
    )
    assert is_senior_key(rpl.person) and not is_senior_key(other.person)
    for a, needs in ((rpl, True), (other, False)):
        a = _open(a)
        s = FormSchema(a.form_version)
        missing = {q.code for q in s.missing_required(rs.system_answers(a, s))}
        assert "current_pending" in missing
        assert ("biosketch" in missing) is needs and ("mftrp_cert" in missing) is needs
        client.force_login(User.objects.get(person=a.person))
        page = client.get(f"/tasks/{a.pk}/").content.decode()
        sec = page[
            page.index('id="sec-biosketch"') : page.index(">", page.index('id="sec-biosketch"'))
        ]
        assert ("hidden" in sec) is (not needs)
        assert "Named on the Notice of Award (set by the site)" not in page
    # the evaluator can mark someone else as named on the NoA
    other.person.senior_key = True
    other.person.save()
    s = FormSchema(other.form_version)
    assert "biosketch" in {q.code for q in s.missing_required(rs.system_answers(other, s))}
    client.force_login(User.objects.get(username="mwills"))
    csv = client.get(f"/manage/outcomes/export/d1/?year={center.grant_year}").content.decode(
        "utf-8-sig"
    )
    assert "Sr/Key (named on the NoA)" in csv
