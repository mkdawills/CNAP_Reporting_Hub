"""Emailed sign-in links, codes for confidential forms, password throttling, period e-mails (Milestone 9)."""

import re
from datetime import timedelta

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone

from apps.accounts import signin
from apps.accounts.models import SignInLink, User
from apps.people.models import Person, PersonEmail
from apps.reporting.models import Assignment, PeriodEmail, ReportingPeriod
from apps.reporting.services import assignments as asg
from apps.reporting.services import emails


@pytest.fixture
def center(db, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.SITE_URL = "http://testserver"
    call_command("seed", "--fictional", verbosity=0)
    p = ReportingPeriod.objects.get(status="open")
    asg.generate(p)
    return p


def link_from(msg):
    return re.search(r"http://testserver(/accounts/link/[^\s?]+/)(\?next=\S+)?", msg.body)


def outside_person():
    p = Person.objects.create(
        first_name="Ada", last_name="Outside", institution="Example University"
    )
    PersonEmail.objects.create(person=p, email="ada@example.org", is_primary=True)
    return p


def test_request_sends_link_only_to_people_on_file(client, center):
    p = outside_person()
    r = client.post("/accounts/link/", {"email": "ADA@example.org"})
    assert "is on file with the Center" in r.content.decode()
    assert len(mail.outbox) == 1 and link_from(mail.outbox[0])
    # unknown address: same page, nothing sent
    r = client.post("/accounts/link/", {"email": "nobody@example.org"})
    assert "is on file with the Center" in r.content.decode() and len(mail.outbox) == 1
    assert SignInLink.objects.filter(person=p).count() == 1


def test_administrators_never_get_links(client, center):
    admin = User.objects.get(username="mwills")
    client.post("/accounts/link/", {"email": admin.person.primary_email})
    assert len(mail.outbox) == 0


def test_link_is_single_use_and_scanner_safe(client, center):
    p = outside_person()
    client.post("/accounts/link/", {"email": "ada@example.org"})
    path = link_from(mail.outbox[0]).group(1)
    # a mail scanner opening the link doesn't use it up
    r = client.get(path)
    assert "Signing in as" in r.content.decode()
    assert not SignInLink.objects.get(person=p).used_at
    r = client.post(path)
    assert r.status_code == 302 and r["Location"] == "/tasks/"
    u = User.objects.get(person=p)  # account created on first sign-in
    assert not u.has_usable_password() and client.session["signed_in_by_link"]
    client.logout()
    r = client.post(path)
    assert "already been used or has expired" in r.content.decode()
    assert "_auth_user_id" not in client.session


def test_expired_link_and_unsafe_next(client, center):
    p = outside_person()
    url = signin.make_link(p, "ada@example.org", next_path="https://evil.example.com/")
    path = url.replace("http://testserver", "").split("?")[0]
    r = client.post(path, {"next": "https://evil.example.com/"})
    assert r["Location"] == "/tasks/"
    client.logout()
    url = signin.make_link(p, "ada@example.org")
    SignInLink.objects.filter(used_at__isnull=True).update(
        expires_at=timezone.now() - timedelta(minutes=1)
    )
    r = client.post(url.replace("http://testserver", ""))
    assert "already been used or has expired" in r.content.decode()


def test_link_requests_are_throttled(client, center):
    outside_person()
    for _ in range(5):
        client.post("/accounts/link/", {"email": "ada@example.org"})
    assert len(mail.outbox) == signin.LINKS_PER_HOUR


def test_confidential_form_from_link_needs_code(client, center):
    santos = User.objects.get(username="santos").person
    a = Assignment.objects.filter(
        person=santos, form_definition__confidentiality_class="mentoring", reporting_period=center
    ).first()
    url = signin.make_link(santos, santos.primary_email)
    client.post(url.replace("http://testserver", ""))
    r = client.get(f"/tasks/{a.pk}/")
    assert r.status_code == 302 and r["Location"].startswith("/accounts/code/")
    r = client.get(r["Location"])
    assert "6-digit code" in r.content.decode()
    code = re.search(r"code is (\d{6})", mail.outbox[-1].body).group(1)
    wrong = "000000" if code != "000000" else "111111"
    r = client.post("/accounts/code/", {"code": wrong, "next": f"/tasks/{a.pk}/"})
    assert "didn’t match" in r.content.decode()
    r = client.post("/accounts/code/", {"code": code, "next": f"/tasks/{a.pk}/"})
    assert r["Location"] == f"/tasks/{a.pk}/"
    assert client.get(f"/tasks/{a.pk}/").status_code == 200


def test_code_locks_after_five_wrong_tries(center):
    p = outside_person()
    signin.send_code(p)
    code = re.search(r"code is (\d{6})", mail.outbox[-1].body).group(1)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        assert not signin.check_code(p, wrong)
    assert not signin.check_code(p, code)


def test_password_sign_in_is_throttled(client, center):
    for _ in range(signin.FAILED_LOGIN_LIMIT):
        client.post("/accounts/login/", {"username": "okafor", "password": "wrong"})
    r = client.post("/accounts/login/", {"username": "okafor", "password": "Demo-Password-2026"})
    assert "Too many sign-in attempts" in r.content.decode()
    assert "_auth_user_id" not in client.session


def test_period_open_and_reminder_emails(client, center):
    rows = emails.plan(center, "open")
    santos = next(r for r in rows if r["person"].last_name == "Santos")
    open_before = Assignment.objects.filter(
        person=santos["person"], reporting_period=center, status__in=["not_started", "in_progress"]
    ).count()
    assert santos["with_link"] and santos["forms"] and not santos["skip"]
    n, skipped = emails.send(center, "open")
    assert n == len([r for r in rows if not r["skip"]]) and n > 0
    msg = next(m for m in mail.outbox if m.to == [santos["email"]])
    assert center.name in msg.subject and link_from(msg) and santos["forms"][0] in msg.body
    # the personal link signs them in and lands on their tasks
    found = link_from(msg)
    r = client.post(found.group(1) + "?next=/tasks/")
    assert r["Location"] == "/tasks/"
    # a second "open" send skips everyone already e-mailed
    assert emails.send(center, "open")[0] == 0
    # the reminder lists only forms still to do (an exempted form drops off)
    a = Assignment.objects.filter(
        person=santos["person"], reporting_period=center, status__in=["not_started", "in_progress"]
    ).first()
    asg.exempt(None, a, "test")
    rem = next(r for r in emails.plan(center, "reminder") if r["person"] == santos["person"])
    assert len(rem["forms"]) == open_before - 1
    emails.send(center, "reminder")
    assert PeriodEmail.objects.filter(
        period=center, kind="reminder", person=santos["person"]
    ).exists()
    rem = next(r for r in emails.plan(center, "reminder") if r["person"] == santos["person"])
    assert rem["skip"].startswith("Reminded")


def test_emails_only_while_open(center):
    draft = ReportingPeriod.objects.filter(status="draft").first()
    with pytest.raises(emails.EmailError):
        emails.send(draft, "open")


def test_admin_email_page(client, center):
    client.force_login(User.objects.get(username="mwills"))
    html = client.get(f"/manage/periods/{center.pk}/emails/?kind=open").content.decode()
    assert "will get" in html and "Personal link" in html
    r = client.post(f"/manage/periods/{center.pk}/emails/send/", {"kind": "open"})
    assert r.status_code == 302 and len(mail.outbox) > 0


def test_turn_off_sign_in_ends_open_sessions(client, center):
    from django.test import Client

    okafor = User.objects.get(username="okafor")
    other = Client()
    other.force_login(okafor)
    assert other.get("/tasks/").status_code == 200
    client.force_login(User.objects.get(username="mwills"))
    client.post(f"/manage/people/{okafor.person.pk}/account/", {"enable": "0"})
    okafor.refresh_from_db()
    assert okafor.is_enabled is False
    r = other.get("/tasks/")
    assert r.status_code == 302 and "/accounts/login/" in r["Location"]
    # and no emailed link either
    client.post("/accounts/link/", {"email": okafor.person.primary_email})
    assert not any(okafor.person.primary_email in m.to for m in mail.outbox)
    client.post(f"/manage/people/{okafor.person.pk}/account/", {"enable": "1"})
    okafor.refresh_from_db()
    assert okafor.is_enabled is True
