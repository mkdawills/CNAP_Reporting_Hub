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


# ---------------------------------------------------------------- independent security review (2026-10-26)


def _link_session(client, person):
    url = signin.make_link(person, person.primary_email)
    client.post(url.replace("http://testserver", ""))


def _mentoring(person, period):
    return Assignment.objects.filter(
        person=person, form_definition__confidentiality_class="mentoring", reporting_period=period
    ).first()


def test_preview_and_opt_out_need_the_code_too(client, center):
    santos = User.objects.get(username="santos").person
    a = _mentoring(santos, center)
    _link_session(client, santos)
    r = client.get(f"/tasks/{a.pk}/preview/")
    assert r.status_code == 302 and r["Location"].startswith("/accounts/code/")
    r = client.post(f"/tasks/{a.pk}/opt-out/", {})
    assert r.status_code == 302 and r["Location"].startswith("/accounts/code/")


def test_admin_login_goes_through_the_throttled_page(client, center):
    r = client.get("/admin/login/?next=/admin/")
    assert r.status_code == 302 and r["Location"].startswith("/accounts/login/")
    r = client.post("/admin/login/", {"username": "mwills", "password": "x"})
    assert r.status_code == 302 and "_auth_user_id" not in client.session


def test_username_variants_share_one_failure_count(client, center):
    for _ in range(signin.FAILED_LOGIN_LIMIT):
        client.post("/accounts/login/", {"username": "okafor", "password": "wrong"})
    for variant in ("okafor ", " OKAFOR", "ｏｋａｆｏｒ"):
        r = client.post("/accounts/login/", {"username": variant, "password": "Demo-Password-2026"})
        assert "Too many sign-in attempts" in r.content.decode(), variant
        assert "_auth_user_id" not in client.session


def test_forwarded_for_is_validated(client, center, settings):
    settings.TRUST_X_FORWARDED_FOR = True
    r = client.post(
        "/accounts/login/", {"username": "x", "password": "y"}, HTTP_X_FORWARDED_FOR="nope"
    )
    assert r.status_code == 200  # a bad header no longer breaks the page
    r = client.post("/accounts/link/", {"email": "a@b.org"}, HTTP_X_FORWARDED_FOR="nope")
    assert r.status_code == 200
    rf = __import__("django.test", fromlist=["RequestFactory"]).RequestFactory()
    req = rf.get("/", HTTP_X_FORWARDED_FOR="203.0.113.9", REMOTE_ADDR="127.0.0.1")
    assert signin.client_ip(req) == "203.0.113.9"
    req = rf.get("/", HTTP_X_FORWARDED_FOR="garbage", REMOTE_ADDR="127.0.0.1")
    assert signin.client_ip(req) == "127.0.0.1"


def test_link_requests_limited_per_address_of_origin(client, center):
    for i in range(signin.LINK_REQUESTS_PER_IP_HOUR + 2):
        client.post("/accounts/link/", {"email": f"nobody{i}@example.org"})
    outside_person()
    client.post("/accounts/link/", {"email": "ada@example.org"})
    assert len(mail.outbox) == 0  # this address of origin is over its hourly limit


def test_staff_never_get_links(center):
    p = outside_person()
    u = User.objects.create_user(username="staffer", email="ada@example.org", is_staff=True)
    assert u.person == p
    assert not signin.may_use_link(p)


def test_link_session_ends_when_made_administrator(client, center):
    from apps.accounts.models import ApplicationRole, UserRole

    santos = User.objects.get(username="santos")
    _link_session(client, santos.person)
    assert client.get("/tasks/").status_code == 200
    UserRole.objects.create(user=santos, role=ApplicationRole.objects.get(code="administrator"))
    r = client.get("/manage/")
    assert r.status_code == 302 and "/accounts/login/" in r["Location"]
    assert "_auth_user_id" not in client.session


def test_link_stops_working_when_its_address_is_removed(client, center):
    p = outside_person()
    url = signin.make_link(p, "ada@example.org")
    PersonEmail.objects.filter(person=p).update(email="ada-correct@example.org")
    r = client.post(url.replace("http://testserver", ""))
    assert "already been used or has expired" in r.content.decode()
    assert not User.objects.filter(person=p).exists()


def test_kstate_people_refused_links_when_sso_is_on(center, settings):
    p = Person.objects.create(
        first_name="K", last_name="Stater", institution="kansas state university"
    )
    PersonEmail.objects.create(person=p, email="k@ksu.edu", is_primary=True)
    settings.SIGNIN_LINKS_FOR_KSTATE = False
    assert not signin.may_use_link(p)
    p.institution = "Example University"
    p.save()
    assert signin.may_use_link(p)


def test_code_sends_limited(center):
    p = outside_person()
    assert all(signin.send_code(p) for _ in range(signin.CODES_PER_15_MIN))
    assert not signin.send_code(p)


def test_code_page_only_for_link_sessions(client, center):
    client.force_login(User.objects.get(username="santos"))
    r = client.get("/accounts/code/?next=/tasks/")
    assert r.status_code == 302 and r["Location"] == "/tasks/"
    assert len(mail.outbox) == 0


def test_code_goes_to_the_address_the_link_used(client, center):
    santos = User.objects.get(username="santos").person
    PersonEmail.objects.create(person=santos, email="santos-other@example.org", is_primary=False)
    url = signin.make_link(santos, "santos-other@example.org")
    client.post(url.replace("http://testserver", ""))
    a = _mentoring(santos, center)
    client.get(f"/accounts/code/?next=/tasks/{a.pk}/")
    assert mail.outbox[-1].to == ["santos-other@example.org"]


def test_turning_off_someone_without_an_account_explains_how(client, center):
    p = outside_person()
    client.force_login(User.objects.get(username="mwills"))
    r = client.post(f"/manage/people/{p.pk}/account/", {"enable": "0"}, follow=True)
    assert "untick “Active”" in r.content.decode()
    p.is_active = False
    p.save()
    assert not signin.may_use_link(p)
