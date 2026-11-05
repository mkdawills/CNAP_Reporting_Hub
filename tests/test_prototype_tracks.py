"""Prototype screen 5: progress tracks, CNAP people involved, and change emails (MW 2026-11-05).

Rules being protected:
- Respondents never see papers or proposals they aren't involved in, unless the owner asked them
  to enter on the owner's behalf (and only while that lasts).
- Anyone involved may update an item; the others involved get an email naming who changed it.
- With the prototype switch off, nothing changes.
"""

import pytest
from django.core import mail
from django.core.management import call_command
from django.test import override_settings

from apps.accounts.models import User
from apps.outcomes import journey
from apps.outcomes.models import GrantSubmission, OutcomeDelegate, Publication
from apps.people.models import Resource


@pytest.fixture
def center(db):
    call_command("seed", "--fictional", verbosity=0)
    from apps.outcomes import services as os

    u = User.objects.get(username="okafor")
    if not GrantSubmission.objects.filter(people__person=u.person, status="planned").exists():
        a0 = os.create_grant(u, u.person, {"project_title": "Sample R21: attention and sleep", "funding_agency": "NIH"})
        GrantSubmission.objects.filter(pk=a0.pk).update(status="not_funded")
        a0.refresh_from_db()
        os.start_resubmission(u, a0)
    if not Publication.objects.filter(people__person=u.person).exists():
        os.create_publication(u, u.person, {"title": "Sample paper: sleep spindles", "journal": "Sample Journal"})


def login(client, u):
    user = User.objects.get(username=u)
    client.force_login(user)
    return user


def okafor_grant():
    p = User.objects.get(username="okafor").person
    return GrantSubmission.objects.filter(people__person=p, status="planned").order_by("-version_no").first()


def email_of(username):
    u = User.objects.get(username=username)
    return getattr(u.person, "email", "") or u.email


def test_off_by_default_nothing_changes(client, center):
    login(client, "okafor")
    r = client.get("/outcomes/")
    assert "portal/outcomes.html" in {t.name for t in r.templates if t.name}
    g = okafor_grant()
    varga = User.objects.get(username="varga").person
    assert client.post(f"/outcomes/grant/{g.pk}/people/", {"person": varga.pk}).status_code == 404
    assert not g.people.filter(person=varga).exists()


@override_settings(UI_PROTOTYPE=True)
def test_one_card_per_proposal_with_every_attempt_on_it(client, center):
    login(client, "okafor")
    r = client.get("/outcomes/")
    assert "proto/outcomes.html" in {t.name for t in r.templates if t.name}
    html = r.content.decode()
    g = okafor_grant()
    assert f'id="item-grant-{g.pk}"' in html
    # the earlier attempt shows on the newer card's track, not as its own card
    if g.resubmission_of_id:
        assert f'id="item-grant-{g.resubmission_of_id}"' not in html
        assert "Every submission of this proposal" in html


@override_settings(UI_PROTOTYPE=True)
def test_people_not_involved_are_refused(client, center):
    g = okafor_grant()
    pub = Publication.objects.filter(people__person__user__username="okafor").first()
    login(client, "lee")
    html = client.get("/outcomes/").content.decode()
    assert g.project_title not in html and pub.title not in html
    assert client.get(f"/outcomes/grant/{g.pk}/").status_code == 403
    assert client.get(f"/outcomes/pub/{pub.pk}/").status_code == 403
    lee = User.objects.get(username="lee").person
    assert client.post(f"/outcomes/grant/{g.pk}/people/", {"person": lee.pk}).status_code == 403
    assert not g.people.filter(person=lee).exists()
    # asking for someone else's page shows your own page, never theirs
    okafor = User.objects.get(username="okafor").person
    html = client.get(f"/outcomes/?for={okafor.pk}").content.decode()
    assert g.project_title not in html


@override_settings(UI_PROTOTYPE=True)
def test_an_ended_delegate_loses_access(client, center):
    owner = login(client, "okafor").person
    lee = User.objects.get(username="lee").person
    client.post("/outcomes/delegates/add/", {"person": lee.pk})
    g = okafor_grant()
    login(client, "lee")
    assert client.get(f"/outcomes/grant/{g.pk}/").status_code == 200
    OutcomeDelegate.objects.filter(owner=owner, delegate=lee).update(ended_at="2026-11-01T00:00:00Z")
    assert client.get(f"/outcomes/grant/{g.pk}/").status_code == 403


@override_settings(UI_PROTOTYPE=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_people_involved_see_update_and_the_others_hear_about_it(client, center):
    login(client, "okafor")
    g = okafor_grant()
    varga = User.objects.get(username="varga").person
    mail.outbox.clear()
    client.post(f"/outcomes/grant/{g.pk}/people/", {"person": varga.pk, "role": "co_i", "action": "add"})
    link = g.people.get(person=varga)
    assert link.role == "co_i"
    # the person added hears about it, and only that person
    assert [m.to for m in mail.outbox] == [[email_of("varga")]]
    assert "added you as Co-Investigator" in mail.outbox[0].body

    # the co-investigator now sees the proposal and can move it forward
    login(client, "varga")
    assert g.project_title in client.get("/outcomes/").content.decode()
    mail.outbox.clear()
    cn = Resource.objects.filter(code__iexact="CN").first() or Resource.objects.first()
    r = client.post(
        f"/outcomes/grant/{g.pk}/",
        {
            "to": "submitted",
            "funding_source": "federal",
            "federal_agency": "NIH",
            "project_title": g.project_title,
            "role": "co_i",
            "submission_date": "2026-11-04",
            "requested_total": "120000",
            "resources": [cn.pk],
        },
    )
    assert r.status_code == 302
    g.refresh_from_db()
    assert g.status == "submitted"
    # everyone else involved is told, by name; the person who made the change is not
    recipients = [t for m in mail.outbox for t in m.to]
    assert email_of("okafor") in recipients and email_of("varga") not in recipients
    body = mail.outbox[0].body
    assert varga.full_name in body and "from Planned to Submitted" in body
    # after saving, the co-investigator lands on their own page, not a refusal
    assert client.get(r["Location"]).status_code == 200
    # option A: the save recorded the co-investigator's own role and left the PI's alone
    okafor = User.objects.get(username="okafor").person
    assert g.people.get(person=varga).role == "co_i"
    assert g.people.get(person=okafor).role == "pi"
    # and the form shows the co-investigator their own role
    html = client.get(f"/outcomes/grant/{g.pk}/?to=submitted").content.decode()
    import re as _re
    sel = _re.search(r'<select[^>]*name="role"[^>]*>(.*?)</select>', html, _re.S)
    assert sel and _re.search(r'<option value="co_i"[^>]*selected', sel.group(1))


@override_settings(UI_PROTOTYPE=True)
def test_the_person_who_entered_it_always_stays(client, center):
    login(client, "okafor")
    g = okafor_grant()
    okafor = User.objects.get(username="okafor").person
    varga = User.objects.get(username="varga").person
    client.post(f"/outcomes/grant/{g.pk}/people/", {"person": varga.pk, "role": "co_i", "action": "add"})
    client.post(f"/outcomes/grant/{g.pk}/people/", {"person": okafor.pk, "action": "remove"})
    assert g.people.filter(person=okafor).exists()
    client.post(f"/outcomes/grant/{g.pk}/people/", {"person": varga.pk, "action": "remove"})
    assert not g.people.filter(person=varga).exists()
    login(client, "varga")
    assert client.get(f"/outcomes/grant/{g.pk}/").status_code == 403


@override_settings(UI_PROTOTYPE=True)
def test_a_resubmission_keeps_everyone_involved(center):
    g = okafor_grant()
    varga = User.objects.get(username="varga").person
    journey.add_person("grant", g, varga, "co_i")
    from apps.outcomes import services as os

    okafor = User.objects.get(username="okafor")
    nxt = os.create_grant(okafor, okafor.person, {"project_title": g.project_title}, family=g.grant_family)
    journey.copy_people("grant", g, nxt)
    assert set(nxt.people.values_list("person_id", flat=True)) == set(g.people.values_list("person_id", flat=True))
    assert nxt.people.get(person=varga).role == "co_i"


@override_settings(UI_PROTOTYPE=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
def test_a_change_made_for_someone_else_names_both_people(client, center):
    """Jordan Lee enters for Dr. Okafor: the email says so, and Dr. Okafor hears about it too (MW 2026-11-05)."""
    owner = login(client, "okafor").person
    lee = User.objects.get(username="lee")
    varga = User.objects.get(username="varga").person
    client.post("/outcomes/delegates/add/", {"person": lee.person.pk})
    g = okafor_grant()
    journey.add_person("grant", g, varga, "co_i")
    mail.outbox.clear()
    journey.notify("grant", g, lee, "changed the status from Planned to Submitted")
    recipients = sorted(t for m in mail.outbox for t in m.to)
    assert recipients == sorted([email_of("okafor"), email_of("varga")])
    assert f"{lee.person.full_name}, entering for {owner.full_name}, changed the status" in mail.outbox[0].body
