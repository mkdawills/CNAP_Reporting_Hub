"""
Emailed sign-in links and 6-digit codes (decisions.md 2026-10-24, sign-in plan).

- A link is single-use and expires after SIGNIN_LINK_DAYS (7). Only the SHA-256 of its token is stored.
- Opening a link shows a "Sign in" button; the token is used only when that button is pressed, so email
  security scanners that pre-open links can't use it up.
- A link session lasts SESSION_COOKIE_AGE (8 hours).
- Opening a confidential mentoring form from a link session also needs a 6-digit code sent to the same address
  (valid SIGNIN_CODE_MINUTES, 5 tries).
- Administrators never sign in by link: they use K-State single sign-on with two-factor authentication.
- Who may use links: people outside K-State always; K-State people too until single sign-on is switched on
  (SIGNIN_LINKS_FOR_KSTATE, default: not SSO_ENABLED).
- Requests are throttled per address, and the request page never says whether an address is on file.
"""

import hashlib
import hmac
import ipaddress
import secrets
import threading
import unicodedata
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import F
from django.template.loader import render_to_string
from django.utils import timezone

from apps.audit.models import AuditLog, record_event
from apps.people.models import PersonEmail

from . import access
from .models import FailedLogin, LinkRequest, SignInCode, SignInLink, User

LINK_DAYS = getattr(settings, "SIGNIN_LINK_DAYS", 7)
CODE_MINUTES = getattr(settings, "SIGNIN_CODE_MINUTES", 15)
CODE_TRIES = 5
LINKS_PER_HOUR = 3
CODES_PER_15_MIN = 3
FAILED_LOGIN_LIMIT = 10  # per username or IP in 15 minutes
LINK_REQUESTS_PER_IP_HOUR = 20


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _code_hash(person_pk, code):
    return hmac.new(
        settings.SECRET_KEY.encode(), f"{person_pk}:{code}".encode(), hashlib.sha256
    ).hexdigest()


def links_for_kstate():
    return getattr(settings, "SIGNIN_LINKS_FOR_KSTATE", not settings.SSO_ENABLED)


def may_use_link(person):
    """True when this person may sign in by emailed link."""
    from apps.people.services import is_external

    if not person or not person.is_active or person.archived_at:
        return False
    user = getattr(person, "user", None)
    if user is not None and not link_session_allowed(user):
        return False
    return is_external(person) or links_for_kstate()


def link_session_allowed(user):
    """Accounts that must never be in a link session: disabled, superuser, staff (Django admin), administrators."""
    return bool(
        user.is_enabled
        and not user.is_superuser
        and not user.is_staff
        and not access.can_view_admin(user)
    )


def person_for_email(email):
    row = (
        PersonEmail.objects.filter(email__iexact=(email or "").strip())
        .select_related("person")
        .first()
    )
    return row.person if row else None


def make_link(person, email, purpose="request", next_path=""):
    """Create a link and return its full URL (the token exists only in this URL)."""
    token = secrets.token_urlsafe(32)
    SignInLink.objects.create(
        person=person,
        email=email,
        token_hash=_hash(token),
        purpose=purpose,
        expires_at=timezone.now() + timedelta(days=LINK_DAYS),
    )
    url = f"{settings.SITE_URL}/accounts/link/{token}/"
    if next_path:
        from urllib.parse import quote

        url += f"?next={quote(next_path)}"
    return url


def _send(**kw):
    """Send mail off the request thread (SIGNIN_SEND_ASYNC), so a known address doesn't answer more slowly than an
    unknown one."""
    if getattr(settings, "SIGNIN_SEND_ASYNC", True):
        threading.Thread(
            target=send_mail, kwargs={**kw, "fail_silently": True}, daemon=True
        ).start()
    else:
        send_mail(**kw, fail_silently=True)


def request_link(email, ip=None):
    """Send a fresh link if the address belongs to someone who may use one. Always returns None: the page says
    the same thing either way. At most LINK_REQUESTS_PER_IP_HOUR requests per address of origin."""
    email = (email or "").strip()
    if ip:
        if LinkRequest.objects.filter(
            ip=ip, at__gte=timezone.now() - timedelta(hours=1)
        ).count() >= (LINK_REQUESTS_PER_IP_HOUR):
            return None
        LinkRequest.objects.create(ip=ip)
        LinkRequest.objects.filter(at__lt=timezone.now() - timedelta(days=1)).delete()
    person = person_for_email(email)
    if not person or not may_use_link(person):
        return None
    recent = SignInLink.objects.filter(
        email__iexact=email, created_at__gte=timezone.now() - timedelta(hours=1)
    ).count()
    if recent >= LINKS_PER_HOUR:
        return None
    url = make_link(person, email, "request")
    _send(
        subject="Your CNAP Reporting Hub sign-in link",
        message=render_to_string(
            "email/signin_link.txt",
            {"person": person, "url": url, "days": LINK_DAYS, "site": settings.SITE_URL},
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
    )
    record_event(None, AuditLog.Action.UPDATE, person, new={"signin_link_sent": "request"})
    return None


def find_link(token):
    """The usable link for a token, or None (unknown, used or expired)."""
    link = SignInLink.objects.filter(token_hash=_hash(token or "")).select_related("person").first()
    if not link or link.used_at or link.expires_at < timezone.now():
        return None
    if not may_use_link(link.person):
        return None
    # the address must still belong to this person (it may have been corrected or moved since the link was sent)
    if not PersonEmail.objects.filter(person=link.person, email__iexact=link.email).exists():
        return None
    return link


def _username_for(email):
    base = email.lower()[:150]
    name, n = base, 1
    while User.objects.filter(username=name).exists():
        n += 1
        name = f"{base[:140]}-{n}"
    return name


@transaction.atomic
def use_link(token, ip=None):
    """Mark the link used and return the User to sign in (created on first sign-in), or None."""
    link = find_link(token)
    if not link:
        return None
    updated = SignInLink.objects.filter(pk=link.pk, used_at__isnull=True).update(
        used_at=timezone.now(), used_ip=ip
    )
    if not updated:  # used by a parallel request
        return None
    person = link.person
    user = User.objects.filter(person=person).first()
    if user is None:
        user = User(
            username=_username_for(link.email),
            email=link.email,
            first_name=person.first_name,
            last_name=person.last_name,
            person=person,
        )
        user.set_unusable_password()
        try:
            with transaction.atomic():
                user.save()
        except IntegrityError:  # two links for the same person used at the same moment
            user = User.objects.get(person=person)
        else:
            record_event(
                None, AuditLog.Action.CREATE, user, new={"created_by": "emailed sign-in link"}
            )
    record_event(user, AuditLog.Action.UPDATE, person, new={"signed_in": "emailed link"})
    return user


def last_link_email(user):
    """The address of the link this person signed in with most recently."""
    link = (
        SignInLink.objects.filter(person=user.person, used_at__isnull=False)
        .order_by("-used_at")
        .first()
    )
    return link.email if link else user.person.primary_email


def send_code(person, email=None):
    """Email a fresh 6-digit code (to the address the link went to). Returns False when too many were sent
    recently."""
    now = timezone.now()
    if (
        SignInCode.objects.filter(
            person=person, created_at__gte=now - timedelta(minutes=15)
        ).count()
        >= CODES_PER_15_MIN
    ):
        return False
    code = f"{secrets.randbelow(1_000_000):06d}"
    SignInCode.objects.create(
        person=person,
        code_hash=_code_hash(person.pk, code),
        expires_at=now + timedelta(minutes=CODE_MINUTES),
    )
    _send(
        subject=f"Your CNAP Reporting Hub code: {code}",
        message=render_to_string(
            "email/signin_code.txt", {"person": person, "code": code, "minutes": CODE_MINUTES}
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email or person.primary_email],
    )
    return True


def check_code(person, code):
    """True when the code matches the newest unexpired code (5 tries)."""
    c = (
        SignInCode.objects.filter(
            person=person, used_at__isnull=True, expires_at__gte=timezone.now()
        )
        .order_by("-created_at")
        .first()
    )
    if not c:
        return False
    # count the try first, atomically, so parallel guesses can't share one count
    if not SignInCode.objects.filter(pk=c.pk, attempts__lt=CODE_TRIES).update(
        attempts=F("attempts") + 1
    ):
        return False
    if hmac.compare_digest(c.code_hash, _code_hash(person.pk, (code or "").strip())):
        return bool(
            SignInCode.objects.filter(pk=c.pk, used_at__isnull=True).update(used_at=timezone.now())
        )
    return False


# ------------------------------------------------------------------ password sign-in throttle


def norm_username(username):
    """The username as Django's login form sees it (Unicode-normalised, trimmed), lower-cased for counting."""
    return unicodedata.normalize("NFKC", username or "").strip().casefold()[:150]


def too_many_failures(username, ip):
    since = timezone.now() - timedelta(minutes=15)
    by_user = FailedLogin.objects.filter(username=norm_username(username), at__gte=since).count()
    by_ip = FailedLogin.objects.filter(ip=ip, at__gte=since).count() if ip else 0
    return by_user >= FAILED_LOGIN_LIMIT or by_ip >= FAILED_LOGIN_LIMIT * 3


def note_failure(username, ip):
    FailedLogin.objects.create(username=norm_username(username), ip=ip)
    FailedLogin.objects.filter(at__lt=timezone.now() - timedelta(days=1)).delete()


def _valid_ip(v):
    try:
        return str(ipaddress.ip_address((v or "").strip()))
    except ValueError:
        return None


def client_ip(request):
    """The client address. Behind nginx (which must set X-Forwarded-For to $remote_addr, docs/deployment.md),
    REMOTE_ADDR is the proxy; X-Forwarded-For is trusted only when configured and only if it is a valid address."""
    if getattr(settings, "TRUST_X_FORWARDED_FOR", False):
        fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip = _valid_ip(fwd.split(",")[-1]) if fwd else None
        if ip:
            return ip
    return _valid_ip(request.META.get("REMOTE_ADDR"))
