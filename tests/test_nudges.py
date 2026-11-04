"""Monthly check-in emails for planned grant proposals (MW 2026-11-03)."""

import datetime as dt

import pytest
from django.core import mail
from django.utils import timezone

from apps.common.enums import GrantStatus
from apps.outcomes import nudges, reminders
from apps.outcomes.models import GrantFamily, GrantNudge, GrantSubmission, GrantSubmissionPerson
from apps.people.models import Person, PersonEmail

pytestmark = pytest.mark.django_db

LATER = timezone.now() + dt.timedelta(days=40)


def _person(first="Nadia", last="Planner", email="nadia.planner@example.edu"):
    p = Person.objects.create(first_name=first, last_name=last)
    PersonEmail.objects.create(person=p, email=email, is_primary=True)
    return p


def _grant(person, title="Sample R01: planned work", status=GrantStatus.PLANNED, **kw):
    fam = GrantFamily.objects.create(created_by=None)
    g = GrantSubmission.objects.create(
        grant_family=fam,
        version_no=0,
        status=status,
        project_title=title,
        funding_agency=kw.pop("funding_agency", "NIH"),
        anticipated_submission_date=kw.pop(
            "anticipated_submission_date", dt.date(2027, 2, 5)
        ),
        **kw,
    )
    GrantSubmissionPerson.objects.create(
        grant_submission=g, person=person, role="pi", is_primary_cnap_contact=True
    )
    return g


def test_due_waits_a_month_from_creation():
    person = _person()
    _grant(person)
    assert nudges.due() == []  # brand new: no nudge yet
    assert [g.pk for g, p, cc in nudges.due(now=LATER)]


def test_send_emails_and_records(settings):
    settings.SIGNIN_LINKS_FOR_KSTATE = True
    person = _person()
    g = _grant(person)
    sent = nudges.send(now=LATER)
    assert len(sent) == 1
    assert GrantNudge.objects.filter(grant=g, person=person).count() == 1
    m = mail.outbox[-1]
    assert "Sample R01" in m.subject
    body = m.body
    assert "We hope your month is going well" in body
    assert "ideation stage" in body
    assert "writer's block" in body
    assert "grant specialist" in body
    assert "clear internal due dates" in body
    assert "pivoting" in body
    assert "external scientific review" in body
    assert "Cheering you on!" in body
    assert "February 2027" in body  # day not known, so month and year only
    # once a month, not every day (sent_at is auto-set to the real clock, so pin it to LATER)
    GrantNudge.objects.update(sent_at=LATER)
    assert nudges.send(now=LATER) == []
    again = LATER + dt.timedelta(days=29)
    assert len(nudges.send(now=again)) == 1


def test_only_planned_grants_get_nudges_and_skip_stale_reminder(settings):
    person = _person()
    g = _grant(person, status=GrantStatus.SUBMITTED, submission_date=dt.date(2026, 9, 1))
    assert nudges.due(now=LATER) == []
    # stale reminders still cover submitted proposals, but not planned ones
    old = timezone.now() - dt.timedelta(days=settings.OUTCOME_STALE_DAYS + 5)
    GrantSubmission.objects.filter(pk=g.pk).update(updated_at=old)
    kinds = {k for p, recs, cc in reminders.due() for k, o, t in recs}
    assert kinds == {"Grant proposal"}
    planned = _grant(person, title="Planned one")
    GrantSubmission.objects.filter(pk=planned.pk).update(updated_at=old)
    titles = [t for p, recs, cc in reminders.due() for k, o, t in recs]
    assert not any("Planned one" in t for t in titles)


def test_answer_page(client, settings):
    person = _person()
    g = _grant(person)
    nudges.send(now=LATER)
    n = GrantNudge.objects.get()
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.create_user(
        username="nplanner", password="x", person=person
    )
    client.force_login(user)
    r = client.get(f"/outcomes/nudge/{n.pk}/?choice=block")
    assert r.status_code == 200
    page = r.content.decode()
    assert "checking in to see how this planned proposal" in page
    assert "Grant Writing support" in page
    # pivot without comments is refused
    r = client.post(f"/outcomes/nudge/{n.pk}/", {"choice": "pivot", "comments": ""})
    n.refresh_from_db()
    assert not n.answered_at
    # a real answer lands
    r = client.post(
        f"/outcomes/nudge/{n.pk}/", {"choice": "timeline", "comments": "Drafting now."}
    )
    assert r.status_code == 302
    n.refresh_from_db()
    assert n.choice == "timeline" and n.comments == "Drafting now."
    g.refresh_from_db()
    assert g.confirmed_at  # answering counts as a review touch
    r = client.get(f"/outcomes/nudge/{n.pk}/")
    assert "Thank you" in r.content.decode()


def test_answer_page_is_owner_only(client):
    person = _person()
    other = _person("Omar", "Other", "omar.other@example.edu")
    _grant(person)
    nudges.send(now=LATER)
    n = GrantNudge.objects.get()
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.create_user(username="oother", password="x", person=other)
    client.force_login(user)
    assert client.get(f"/outcomes/nudge/{n.pk}/").status_code == 403


def test_admin_starts_a_resubmission_copied_from_the_original(client):
    """MW 2026-11-04: a resubmission builds on the original, so the next round starts as a copy."""
    from django.core.management import call_command

    from apps.accounts.models import User

    call_command("seed", "--fictional", verbosity=0)
    client.force_login(User.objects.get(username="mwills"))
    g = GrantSubmission.objects.filter(status=GrantStatus.NOT_FUNDED).first()
    page = client.get(f"/manage/outcomes/grants/{g.pk}/").content.decode()
    assert "Start the resubmission" in page
    r = client.post(f"/manage/outcomes/grants/{g.pk}/resubmit/")
    new = GrantSubmission.objects.get(resubmission_of=g)
    assert r.status_code == 302 and r["Location"].endswith(f"/manage/outcomes/grants/{new.pk}/")
    assert new.project_title == g.project_title and new.funding_agency == g.funding_agency
    assert new.version_no == g.version_no + 1
    # pressing it again opens the same next round, never a second copy
    client.post(f"/manage/outcomes/grants/{g.pk}/resubmit/")
    assert GrantSubmission.objects.filter(resubmission_of=g).count() == 1


def test_evaluator_leaves_a_proposal_out_of_table1_with_a_reason(client):
    """MW 2026-11-04: the Table 1 exclusion is the evaluator's review step, with a reason."""
    from django.core.management import call_command

    from apps.accounts.models import User

    call_command("seed", "--fictional", verbosity=0)
    client.force_login(User.objects.get(username="mwills"))
    g = GrantSubmission.objects.exclude(status=GrantStatus.PLANNED).first()
    # not on the data-entry form any more
    assert "exclude_from_table1" not in client.get(f"/manage/outcomes/grants/{g.pk}/").content.decode()
    # a reason is required
    client.post(f"/manage/outcomes/grants/{g.pk}/table1/", {"reason": ""})
    g.refresh_from_db()
    assert not g.exclude_from_table1
    client.post(f"/manage/outcomes/grants/{g.pk}/table1/", {"reason": "Core staff grant unrelated to IDeA"})
    g.refresh_from_db()
    assert g.exclude_from_table1 and g.table1_exclusion_reason.startswith("Core staff")
    client.post(f"/manage/outcomes/grants/{g.pk}/table1/", {"action": "restore"})
    g.refresh_from_db()
    assert not g.exclude_from_table1 and not g.table1_exclusion_reason
