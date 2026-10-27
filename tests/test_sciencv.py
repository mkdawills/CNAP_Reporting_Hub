"""Reading SciENcv Common Form PDFs (MW 2026-10-27). Made-up people in the real layout; no real documents."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from apps.accounts.models import User
from apps.outcomes import sciencv
from apps.reporting.models import Assignment, ReportingPeriod
from apps.reporting.services import assignments as asg
from apps.reporting.services import responses as rs

BIO = """NIH BIOGRAPHICAL SKETCH COMMON FORM
Name: Sample, Jordan
Persistent Identifier (PID) of the Senior/Key
Person:
https://orcid.org/0000-0002-1694-233X
Position Title: Associate Professor
Organization and Location:
Sample State University, Sampletown, Kansas, United States
PROFESSIONAL PREPARATION
INSTITUTION AND LOCATION
DEGREE
(if applicable)
Receipt Date
FIELD OF STUDY
Example University, Exampleville, Ohio, United States
Postdoctoral Fellow
07/2012
06/2015
Neuroscience
Sample College, Sampleburg, Iowa, United States
Doctor of Philosophy
(PHD)
05/2012
Psychology
Sample College, Sampleburg, Iowa, United States
Master of Arts (MA)
05/2008
Psychology
Example State, Exampleton, Texas, United States
Bachelor of Science (BS)
05/2006
Biology
APPOINTMENTS AND POSITIONS
2020 - present Associate Professor (20) (Sample Fund, Sample Org)
Certified by Sample, Jordan in SciENcv on 2026-09-22 10:51:47
NIH BIOGRAPHICAL SKETCH SUPPLEMENT
"""

CPOS = """NIH Current and Pending (Other) Support Common Form
CURRENT AND PENDING (OTHER) SUPPORT INFORMATION
*NAME:
Sample, Jordan
PERSISTENT IDENTIFIER (PID):
https://orcid.org/0000-0002-1694-233X
Proposals and Active Projects
*Proposal/Active Project Title:
A different project
*Status of Support:
Current
Proposal/Award Number:
1R01XX000001-01
* Person Months per budget period Devoted to the Proposal/Active Project:
Year
Person Months
2025
2
*Overall Objectives:
Something else.
*Proposal/Active Project Title:
Cognitive and Neurobiological Approaches to Plasticity (CNAP) Center Phase 2
*Status of Support:
Current
Proposal/Award Number:
5P20GM113109-09
*Source of Support:
HHS - National Institutes of Health (NIH)
* Person Months per budget period Devoted to the Proposal/Active Project:
Year
Person Months
2024
6
2025
1.8
2026
3
*Overall Objectives:
Center goals.
Certification:
Certified by Sample, Jordan in SciENcv on 2026-03-31 22:01:02
"""


def _pdf(text):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    y = 760
    for line in text.splitlines():
        if y < 40:
            c.showPage()
            y = 760
        c.drawString(40, y, line)
        y -= 13
    c.save()
    return buf.getvalue()


def test_reads_biosketch():
    b = sciencv.read_biosketch(BIO)
    assert b["form_ok"] and b["certified"] == "2026-09-22"
    assert b["orcid"] == "0000-0002-1694-233X"
    assert b["degrees"] == ["PhD", "MA", "BS"]  # the (20) in appointments is not a degree


def test_reads_cnap_months_only_from_the_cnap_award():
    c = sciencv.read_current_pending(CPOS, awards=["P20GM113109"])
    assert c["form_ok"] and c["certified"] == "2026-03-31" and c["cnap_found"]
    assert c["cnap_months"] == [(2024, "6"), (2025, "1.8"), (2026, "3")]


def test_uncertified_and_wrong_files_get_a_plain_message():
    uncert = sciencv.read_biosketch(BIO.replace("Certified by", "Previewed by"))
    assert "isn’t certified" in sciencv.message("biosketch", uncert)
    wrong = sciencv.read_current_pending(BIO)
    assert "doesn’t look like" in sciencv.message("current_pending", wrong)
    assert sciencv.message("biosketch", sciencv.read_biosketch(BIO)) == ""


@pytest.fixture
def center(db):
    call_command("seed", "--fictional", verbosity=0)
    fall = ReportingPeriod.objects.get(status="open")
    asg.generate(fall)
    return fall


def test_real_pdf_round_trip_and_suggestions(client, center):
    a = (
        Assignment.objects.filter(reporting_period=center, form_definition__code="nih_documents")
        .select_related("person")
        .order_by("pk")
        .first()
    )
    from tests.test_nih_documents import _open

    a = _open(a)
    u = User.objects.get(person=a.person)
    files = {
        "file-biosketch": SimpleUploadedFile(
            "bio.pdf", _pdf(BIO.replace("Certified by", "Previewed by")), "application/pdf"
        ),
        "file-current_pending": SimpleUploadedFile("cp.pdf", _pdf(CPOS), "application/pdf"),
    }
    assert rs.save_draft(a, u, {}, files) == []
    client.force_login(u)
    page = client.get(f"/tasks/{a.pk}/").content.decode()
    assert "isn’t certified in SciENcv yet" in page  # caught for the biosketch only
    assert page.count("isn’t certified in SciENcv yet") == 1

    # the evaluator sees the degrees and CNAP months, and can copy the degrees and ORCID iD over
    client.force_login(User.objects.get(username="mwills"))
    p = a.person
    p.orcid = ""
    p.degrees = ""
    p.save()
    html = client.get(f"/manage/people/{p.pk}/").content.decode()
    assert "PhD, MA, BS" in html and "1.8 person months in 2025" in html
    client.post(f"/manage/people/{p.pk}/apply-docs/", {"degrees": "PhD, MA, BS"})
    client.post(f"/manage/people/{p.pk}/apply-docs/", {"orcid": "0000-0002-1694-233X"})
    p.refresh_from_db()
    assert p.degrees == "PhD, MA, BS" and p.orcid == "0000-0002-1694-233X"
    tab = client.get(f"/manage/outcomes/?tab=rppr&year={center.grant_year}").content.decode()
    assert "not certified" in tab and "certified 2026-03-31" in tab
