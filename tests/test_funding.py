"""Funding opportunities, follow-up letters, suggestions, and funding news (MW 2026-11-10).
Spec: docs/funding-follow-up-spec.md, section Tests."""

import datetime as dt
from html import unescape

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditLog
from apps.outcomes import funding
from apps.outcomes.models import (
    FundingFollowUp,
    FundingMatch,
    FundingNewsItem,
    FundingOpportunity,
    FundingQuestion,
    FundingSuggestion,
    GrantFamily,
    GrantSubmission,
    GrantSubmissionPerson,
    OutcomeDelegate,
)
from apps.people.models import Person

PW = "Demo-Password-2026"


@pytest.fixture
def center(db):
    call_command("seed", "--fictional", verbosity=0)


def _login(client, username):
    assert client.login(username=username, password=PW)
    return User.objects.get(username=username)


def _person(username):
    return User.objects.get(username=username).person


def _grant(
    person,
    title="Sample R01: a fictional test proposal",
    status="submitted",
    mechanism="R01",
    agency="National Institutes of Health",
    role="pi",
):
    g = GrantSubmission.objects.create(
        grant_family=GrantFamily.objects.create(title=title),
        project_title=title,
        funding_agency=agency,
        funding_source_type="nih",
        mechanism=mechanism,
        status=status,
        submission_date=dt.date(2026, 6, 5),
    )
    GrantSubmissionPerson.objects.create(
        grant_submission=g, person=person, role=role, is_primary_cnap_contact=True
    )
    return g


def _not_funded_post(client, g, owner, **extra):
    data = {
        "for": owner.pk,
        "to": "not_funded",
        "decision_date": "2026-11-04",
        "discussed_with_program_officer": "no",
        "feedback_shared_with_cnap": "no",
        "plans_to_resubmit": "no",
        "decision_comments": "Fictional.",
    }
    data.update(extra)
    return client.post(f"/outcomes/grant/{g.pk}/", data)


# 1 and 2 ----------------------------------------------------------------------------------------


def test_not_funded_makes_one_follow_up_and_goes_to_the_funding_page(client, center):
    _login(client, "okafor")
    me = _person("okafor")
    g = _grant(me)
    r = _not_funded_post(client, g, me)
    assert r.status_code == 302 and r.url.startswith("/funding/?from=not_funded"), r.url
    assert FundingFollowUp.objects.filter(grant=g).count() == 1
    _not_funded_post(client, g, me)  # saving again never makes a second follow-up
    assert FundingFollowUp.objects.filter(grant=g).count() == 1
    html = client.get(r.url).content.decode()
    assert "The CNAP team will follow up with you personally." in html


def test_not_funded_with_a_resubmission_keeps_the_a1_redirect_and_links_the_funding_page(
    client, center
):
    _login(client, "okafor")
    me = _person("okafor")
    g = _grant(me, title="Sample R01: a second fictional proposal")
    r = _not_funded_post(client, g, me, plans_to_resubmit="yes")
    a1 = GrantSubmission.objects.get(resubmission_of=g)
    assert f"/outcomes/grant/{a1.pk}/" in r.url
    assert FundingFollowUp.objects.filter(grant=g).exists()
    html = client.get(r.url).content.decode()
    assert "Open Funding and news" in html


# 3 and 4 ----------------------------------------------------------------------------------------


def test_a_person_sees_only_their_own_matches_and_letters(client, center):
    okafor, varga = _person("okafor"), _person("varga")
    secret = FundingOpportunity.objects.create(
        name="Fictional award picked only for Varga", source_kind="foundation"
    )
    FundingMatch.objects.create(
        opportunity=secret, person=varga, why="A fictional reason for Varga alone."
    )
    f = FundingFollowUp.objects.get(person=okafor)
    _login(client, "okafor")
    html = client.get("/funding/").content.decode()
    assert "Fictional award picked only for Varga" not in html
    assert "Fear extinction research relates directly" in html  # okafor's own sample match
    assert "Relevant to most members" in html
    # The letter page: 403 until sent, then the owner and active delegates only.
    assert client.get(f"/funding/letter/{f.pk}/").status_code == 403
    funding.send(f, User.objects.get(username="mwills"))
    assert client.get(f"/funding/letter/{f.pk}/").status_code == 200
    client.logout()
    _login(client, "varga")
    assert client.get(f"/funding/letter/{f.pk}/").status_code == 403
    d = OutcomeDelegate.objects.create(owner=okafor, delegate=varga)
    assert client.get(f"/funding/letter/{f.pk}/").status_code == 200
    d.ended_at = timezone.now()
    d.save()
    assert client.get(f"/funding/letter/{f.pk}/").status_code == 403


def test_ended_matches_and_archived_opportunities_are_hidden(client, center):
    okafor = _person("okafor")
    m = FundingMatch.objects.filter(person=okafor).select_related("opportunity").first()
    everyone = FundingOpportunity.objects.filter(audience="everyone").first()
    _login(client, "okafor")
    html = unescape(client.get("/funding/").content.decode())
    assert m.opportunity.name in html and everyone.name in html
    m.ended_at = timezone.now()
    m.save()
    everyone.archived_at = timezone.now()
    everyone.save()
    html = unescape(client.get("/funding/").content.decode())
    if m.opportunity.audience != "everyone":
        assert m.opportunity.name not in html
    assert everyone.name not in html


# 5 ------------------------------------------------------------------------------------------------


def test_a_suggestion_waits_for_review_and_add_to_the_list_links_it(client, center):
    _login(client, "okafor")
    client.post(
        "/funding/suggest/", {"name": "Fictional Foundation Starter Award", "for_everyone": "1"}
    )
    s = FundingSuggestion.objects.get(name="Fictional Foundation Starter Award")
    assert s.status == "to_review" and s.for_everyone
    client.logout()
    _login(client, "mwills")
    html = client.get(f"/manage/funding/opportunities/new/?suggestion={s.pk}").content.decode()
    assert "Fictional Foundation Starter Award" in html
    client.post(
        "/manage/funding/opportunities/new/do/",
        {
            "name": s.name,
            "source_kind": "foundation",
            "audience": "everyone",
            "counts_toward_milestone": "no",
            "suggestion": s.pk,
            "note_to_person": "Thank you. The opportunity is now listed.",
        },
    )
    s.refresh_from_db()
    assert s.status == "added" and s.opportunity and s.opportunity.audience == "everyone"
    assert s.opportunity.suggested_by == s.person


# 6 ------------------------------------------------------------------------------------------------


def test_send_emails_once_with_delegates_copied_and_a_sign_in_link(client, center, settings):
    settings.SIGNIN_LINKS_FOR_KSTATE = True
    okafor, varga = _person("okafor"), _person("varga")
    OutcomeDelegate.objects.create(owner=okafor, delegate=varga)
    f = FundingFollowUp.objects.get(person=okafor)
    _login(client, "mwills")
    r = client.post(
        f"/manage/funding/followups/{f.pk}/do/",
        {"action": "send", "opp": [o.pk for o in f.opportunities.all()]},
    )
    assert "confirm=send" in r.url and not mail.outbox  # Send asks first
    client.post(
        f"/manage/funding/followups/{f.pk}/do/",
        {
            "action": "send_yes",
            "opp": [o.pk for o in f.opportunities.all()],
            "body_note": "A fictional personal paragraph.",
        },
    )
    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert msg.to == [okafor.primary_email] and varga.primary_email in msg.cc
    assert msg.subject == f.name
    assert "Read the full letter" in msg.alternatives[0][0]
    assert f"/funding/letter/{f.pk}/" in msg.body
    f.refresh_from_db()
    assert f.status == "sent" and f.sent_at and okafor.primary_email in f.sent_to
    assert AuditLog.objects.filter(
        entity_type="outcomes.FundingFollowUp", entity_id=f.pk, new_value__status="sent"
    ).exists()
    client.post(f"/manage/funding/followups/{f.pk}/do/", {"action": "send_yes"})
    assert len(mail.outbox) == 1  # a second Send is refused
    with pytest.raises(funding.AlreadySent):
        funding.send(f, User.objects.get(username="mwills"))


# 7 ------------------------------------------------------------------------------------------------


def test_cofunding_only_for_single_pi_nih_r01_r15_r35(center):
    me = _person("okafor")
    assert funding.wants_cofunding(_grant(me, title="Fictional R01 one"))
    assert funding.wants_cofunding(_grant(me, title="Fictional R35 one", mechanism="R35"))
    assert not funding.wants_cofunding(_grant(me, title="Fictional R21 one", mechanism="R21"))
    assert not funding.wants_cofunding(_grant(me, title="Fictional multiple-PI one", role="mpi"))


# 8 ------------------------------------------------------------------------------------------------


def test_the_catalog_and_questions_load_twice_without_duplicates(db):
    funding.load_catalog()
    funding.load_questions()
    n, q = FundingOpportunity.objects.count(), FundingQuestion.objects.count()
    assert n == 28 and q == 7
    assert funding.load_catalog() == 0 and funding.load_questions() == 0
    assert FundingOpportunity.objects.count() == n and FundingQuestion.objects.count() == q
    assert not FundingMatch.objects.exists()  # the catalog never seeds matches


# 10 -----------------------------------------------------------------------------------------------


def test_news_pinned_first_archived_hidden_and_only_admins_write(client, center):
    old = FundingNewsItem.objects.create(
        headline="A fictional old item",
        summary="Fictional.",
        news_date=dt.date(2020, 1, 1),
        pinned=True,
    )
    gone = FundingNewsItem.objects.create(
        headline="A fictional archived item", summary="Fictional.", archived_at=timezone.now()
    )
    items = funding.news()
    assert [n.pinned for n in items] == sorted(
        (n.pinned for n in items), reverse=True
    )  # pinned first
    assert old in items and gone not in items
    _login(client, "okafor")
    html = client.get("/funding/").content.decode()
    assert "A fictional old item" in html and "A fictional archived item" not in html
    assert (
        client.post("/manage/funding/news/new/do/", {"headline": "x", "summary": "y"}).status_code
        == 403
    )
    client.logout()
    _login(client, "hbailey")  # view-only leadership can read but not write
    assert client.get("/manage/funding/?tab=news").status_code == 200
    assert (
        client.post("/manage/funding/news/new/do/", {"headline": "x", "summary": "y"}).status_code
        == 403
    )
    client.logout()
    _login(client, "mwills")
    client.post(
        "/manage/funding/news/new/do/",
        {"headline": "A fictional new item", "summary": "Fictional."},
    )
    assert FundingNewsItem.objects.filter(headline="A fictional new item").exists()
    assert gone.archived_at


# 11 -----------------------------------------------------------------------------------------------


def test_manage_pages_refuse_members(client, center):
    f = FundingFollowUp.objects.first()
    _login(client, "okafor")
    for url in [
        "/manage/funding/",
        f"/manage/funding/followups/{f.pk}/",
        f"/manage/funding/followups/{f.pk}/email/",
        "/manage/funding/opportunities/new/",
        "/manage/funding/news/new/",
    ]:
        assert client.get(url).status_code == 403, url
    assert (
        client.post(f"/manage/funding/followups/{f.pk}/do/", {"action": "send_yes"}).status_code
        == 403
    )
    assert not mail.outbox


def test_matches_tick_themselves_on_an_open_letter_and_the_person_page_panel(client, center):
    okafor = _person("okafor")
    f = FundingFollowUp.objects.get(person=okafor)
    o = (
        FundingOpportunity.objects.filter(audience="matched")
        .exclude(matches__person=okafor)
        .first()
    )
    _login(client, "mwills")
    client.post(
        f"/manage/funding/person/{okafor.pk}/match/",
        {"opportunity": o.pk, "why": "A fictional reason."},
    )
    assert FundingMatch.objects.filter(person=okafor, opportunity=o, ended_at__isnull=True).exists()
    assert f.opportunities.filter(pk=o.pk).exists()
    assert "A fictional reason." in client.get(f"/manage/people/{okafor.pk}/").content.decode()


def test_the_letter_name_is_identical_everywhere(client, center):
    f = FundingFollowUp.objects.select_related("grant").first()
    name = f"Next steps after {f.grant.project_title}"
    assert f.name == name
    subject, text, html = funding.render_email(f)
    assert subject == name and name in html and text.startswith(name)
    _login(client, "mwills")
    assert name in client.get(f"/manage/funding/followups/{f.pk}/").content.decode()
    assert name in client.get(f"/funding/letter/{f.pk}/").content.decode()
    assert Person.objects.filter(pk=f.person_id).exists()


def test_opportunities_tab_names_who_each_is_picked_for_and_lists_by_member(client, center):
    okafor = _person("okafor")
    m = FundingMatch.objects.filter(person=okafor).select_related("opportunity").first()
    _login(client, "mwills")
    html = unescape(client.get("/manage/funding/?tab=opportunities").content.decode())
    assert "Picked for" in html and okafor.full_name in html
    html = unescape(client.get("/manage/funding/?tab=opportunities&view=members").content.decode())
    assert okafor.full_name in html and m.opportunity.name in html and m.why in html


# K-State Research Weekly headings and Events and talks (MW 2026-11-10) -------------------------------


def test_kstate_updates_load_once_and_sit_under_the_research_weekly_heading(client, center):
    from apps.outcomes.models import FundingBulletin, FundingEvent

    assert funding.load_updates() == 0  # seed already loaded them; nothing twice
    b = FundingBulletin.objects.get(name="K-State Research Weekly")
    assert b.news.exists() and b.events.exists() and b.opportunities.exists()
    _login(client, "okafor")
    html = unescape(client.get("/funding/").content.decode())
    assert "From K-State Research Weekly" in html and "Read the full issue" in html
    assert "Events and talks" in html
    assert html.index("From K-State Research Weekly") < html.index("From other sources")
    past = FundingEvent.objects.create(title="A fictional past talk", starts_on=dt.date(2020, 1, 1))
    html = client.get("/funding/").content.decode()
    assert past.title not in html  # past events leave the member page


def test_events_and_new_issues_are_added_by_the_cnap_office_only(client, center):
    from apps.outcomes.models import FundingBulletin, FundingEvent

    data = {
        "title": "A fictional seminar",
        "starts_on": "2027-01-20",
        "time_text": "4 p.m.",
        "bulletin": "new",
        "bulletin_name": "K-State Research Weekly",
        "bulletin_date": "2027-01-13",
    }
    _login(client, "okafor")
    assert client.post("/manage/funding/events/new/do/", data).status_code == 403
    client.logout()
    _login(client, "hbailey")
    assert client.post("/manage/funding/events/new/do/", data).status_code == 403
    client.logout()
    _login(client, "mwills")
    client.post("/manage/funding/events/new/do/", data)
    e = FundingEvent.objects.get(title="A fictional seminar")
    assert e.bulletin == FundingBulletin.objects.get(issue_date=dt.date(2027, 1, 13))
    bad = {**data, "title": "A fictional backward event", "ends_on": "2027-01-01", "bulletin": ""}
    client.post("/manage/funding/events/new/do/", bad)
    assert not FundingEvent.objects.filter(title="A fictional backward event").exists()
    assert client.get("/manage/funding/?tab=events").status_code == 200
