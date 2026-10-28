"""PubMed fill-in and stale-record reminders (decisions.md 2026-10-26)."""

import datetime as dt

import pytest
from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.outcomes import pubmed, reminders
from apps.outcomes.models import OutcomeDelegate, OutcomeReminder, Publication

EFETCH = b"""<?xml version="1.0" ?>
<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID Version="1">31234567</PMID>
<Article><Journal><JournalIssue><PubDate><Year>2025</Year><Month>Mar</Month></PubDate></JournalIssue>
<Title>Journal of Sample Neuroscience</Title></Journal>
<ArticleTitle>Attention shifts measured with <i>EEG</i> in young adults.</ArticleTitle>
<AuthorList><Author><LastName>Okafor</LastName><Initials>A</Initials><AffiliationInfo><Affiliation>Kansas State University, Manhattan, KS, USA.</Affiliation></AffiliationInfo></Author>
<Author><LastName>Schmidt</LastName><Initials>K</Initials><AffiliationInfo><Affiliation>University of Heidelberg, Germany.</Affiliation></AffiliationInfo></Author></AuthorList>
<GrantList><Grant><GrantID>P20 GM000000</GrantID><Agency>NIGMS NIH HHS</Agency></Grant></GrantList>
<ArticleDate DateType="Electronic"><Year>2025</Year><Month>02</Month><Day>14</Day></ArticleDate>
</Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"""


def test_pmid_parsing():
    assert pubmed.pmid_from("https://pubmed.ncbi.nlm.nih.gov/31234567/") == "31234567"
    assert pubmed.pmid_from("PMID: 31234567") == "31234567"
    assert pubmed.pmid_from("31234567") == "31234567"
    assert pubmed.pmid_from("https://doi.org/10.1000/xyz") is None
    assert pubmed.doi_from("https://doi.org/10.1000/xyz.123") == "10.1000/xyz.123"


@override_settings(CNAP_GRANT_NUMBERS=["P20GM113109"])
def test_grant_number_forms():
    for form, hit in [
        ("P20 GM113109", True),
        ("P20GM113109/GM/NIGMS NIH HHS/United States", True),
        ("GM113109", True),
        ("R01 GM113110", False),
    ]:
        x = EFETCH.replace(b"P20 GM000000", form.encode())
        assert (
            pubmed.lookup("31234567", get=lambda url, timeout=8, x=x: x)["cnap_in_grant_index"]
            is hit
        ), form


@override_settings(CNAP_GRANT_NUMBERS=["P20GM000000"])
def test_lookup_parses_details_and_grant_index():
    out = pubmed.lookup(
        "https://pubmed.ncbi.nlm.nih.gov/31234567/", get=lambda url, timeout=8: EFETCH
    )
    assert out["title"] == "Attention shifts measured with EEG in young adults"
    assert out["journal"] == "Journal of Sample Neuroscience"
    assert out["publication_date"] == dt.date(2025, 2, 14)
    assert out["authors"] == "Okafor A, Schmidt K"
    assert out["cnap_in_grant_index"] is True
    assert any("Germany" in a for a in out["affiliations"])


def test_lookup_failure_is_friendly():
    def boom(url, timeout=8):
        raise OSError("blocked")

    with pytest.raises(pubmed.LookupError_, match="type the details in"):
        pubmed.lookup("https://pubmed.ncbi.nlm.nih.gov/1/", get=boom)
    with pytest.raises(pubmed.LookupError_, match="doesn’t look like"):
        pubmed.lookup("not a link")


@pytest.fixture
def center(db):
    call_command("seed", "--fictional", verbosity=0)


def test_fill_in_button_shows_values_without_saving(client, center, monkeypatch):
    u = User.objects.get(username="okafor")
    client.force_login(u)
    client.post(
        "/outcomes/new/pub/", {"title": "Placeholder", "publication_type": "journal_article"}
    )
    p = Publication.objects.get(title="Placeholder")
    Publication.objects.filter(pk=p.pk).update(status="submitted")
    monkeypatch.setattr(pubmed, "_get", lambda url, timeout=8: EFETCH)
    r = client.post(
        f"/outcomes/pub/{p.pk}/",
        {
            "to": "published",
            "lookup": "1",
            "pubmed_url": "https://pubmed.ncbi.nlm.nih.gov/31234567/",
        },
    )
    html = r.content.decode()
    assert r.status_code == 200 and "Filled in from PubMed" in html
    assert (
        "Attention shifts measured with EEG in young adults" in html
        and "Journal of Sample Neuroscience" in html
    )
    p.refresh_from_db()
    assert p.status == "submitted" and p.title == "Placeholder"  # nothing saved until Save


@override_settings(
    OUTCOME_STALE_DAYS=120, OUTCOME_REMINDER_EVERY_DAYS=30, SITE_URL="https://hub.example"
)
def test_reminders_for_stale_records(center):
    owner = User.objects.get(username="okafor").person
    student = User.objects.get(username="lee").person
    OutcomeDelegate.objects.create(owner=owner, delegate=student)
    p = Publication.objects.create(
        title="Old plan", publication_type="journal_article", status="planned"
    )
    p.people.create(person=owner)
    old = timezone.now() - dt.timedelta(days=200)
    Publication.objects.filter(pk=p.pk).update(confirmed_at=old, updated_at=old)
    sent = reminders.send()
    assert [s[0] for s in sent] == [owner]
    m = mail.outbox[-1]
    assert "Old plan" in m.body and "https://hub.example/outcomes/" in m.body
    assert m.to == [owner.primary_email] and student.primary_email in m.cc
    assert OutcomeReminder.objects.filter(person=owner).count() == 1
    # not again within 30 days
    assert reminders.send() == []
    # a fresh review stops reminders
    Publication.objects.filter(pk=p.pk).update(confirmed_at=timezone.now())
    OutcomeReminder.objects.all().delete()
    assert all(s[0] != owner for s in reminders.send())


def test_dry_run_command(center, capsys):
    call_command("send_outcome_reminders", "--dry-run")
    assert "reminder" in capsys.readouterr().out


def test_admin_reminders_tab(client, center):
    client.force_login(User.objects.get(username="mwills"))
    assert client.get("/manage/outcomes/?tab=reminders").status_code == 200
    client.force_login(User.objects.get(username="hbailey"))
    assert client.post("/manage/outcomes/reminders/send/").status_code == 403


def test_not_funded_shows_encouraging_note(client, center):
    from apps.outcomes.models import GrantSubmission

    client.force_login(User.objects.get(username="okafor"))
    client.post(
        "/outcomes/new/grant/", {"funding_agency": "NIH", "project_title": "Grant E", "role": "pi"}
    )
    g = GrantSubmission.objects.get(project_title="Grant E")
    GrantSubmission.objects.filter(pk=g.pk).update(status="submitted")
    r = client.post(
        f"/outcomes/grant/{g.pk}/",
        {
            "to": "not_funded",
            "decision_date": "2027-02-01",
            "discussed_with_program_officer": "no",
            "feedback_shared_with_cnap": "no",
            "plans_to_resubmit": "no",
        },
        follow=True,
    )
    html = r.content.decode()
    assert "part of every researcher’s journey toward funding" in html and "encourage" in html


def test_presentations(client, center):
    from apps.outcomes.models import Presentation

    client.force_login(User.objects.get(username="okafor"))
    client.post(
        "/outcomes/presentations/new/",
        {
            "presentation_type": "invited_talk",
            "title": "Talk P",
            "presented_on": "2026-09-12",
            "cnap_cited": "no",
        },
    )
    t = Presentation.objects.get(title="Talk P")
    assert t.cnap_cited is False and "Talk P" in client.get("/outcomes/").content.decode()
    client.force_login(User.objects.get(username="mwills"))
    assert "Talk P" in client.get("/manage/outcomes/export/talks/").content.decode("utf-8-sig")


@override_settings(OUTCOME_REOPEN_DAYS=7)
def test_entry_closed_for_a_week_after_a_period_closes(client, center):
    from apps.outcomes.services import entry_window
    from apps.reporting.models import ReportingPeriod

    open_p = ReportingPeriod.objects.get(status="open")
    open_p.status, open_p.closed_at = "closed", timezone.now() - dt.timedelta(days=2)
    open_p.save()
    ok, reopens = entry_window()
    assert not ok and reopens == timezone.localtime(open_p.closed_at + dt.timedelta(days=7)).date()
    client.force_login(User.objects.get(username="okafor"))
    r = client.get("/outcomes/new/pub/")
    assert r.status_code == 302
    assert "opens again on" in client.get("/outcomes/").content.decode().lower()
    open_p.closed_at = timezone.now() - dt.timedelta(days=8)
    open_p.save()
    assert entry_window()[0] is True
    assert client.get("/outcomes/new/pub/").status_code == 200


def test_talks_are_entered_after_they_happen(db):
    """MW 2026-10-28: a talk is added once given, not before."""
    import datetime as dt

    from django.utils import timezone

    from apps.portal.outcome_forms import PresentationForm

    tomorrow = timezone.localdate() + dt.timedelta(days=1)
    f = PresentationForm(
        data={"presentation_type": "conference", "title": "T", "presented_on": tomorrow.isoformat()}
    )
    f.is_valid()
    assert "hasn’t happened yet" in " ".join(f.errors.get("presented_on", []))
    f = PresentationForm(
        data={
            "presentation_type": "conference",
            "title": "T",
            "presented_on": timezone.localdate().isoformat(),
        }
    )
    f.is_valid()
    assert "presented_on" not in f.errors
