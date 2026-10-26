"""Production settings: HTTPS assumed behind nginx, secure cookies, no debug."""

from .base import *  # noqa: F401,F403

DEBUG = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
# HSTS preload is a decision for the whole k-state.edu domain, not this site; left off (check --deploy W021).
# nginx sets X-Forwarded-For; the client address used for sign-in throttling is its last entry.
TRUST_X_FORWARDED_FOR = True
# Never print e-mails (with sign-in links) to logs in production: refuse to start without a real mail server.
if EMAIL_BACKEND.endswith("console.EmailBackend"):  # noqa: F405
    raise RuntimeError("Set EMAIL_URL to K-State's mail relay before running in production.")
SILENCED_SYSTEM_CHECKS = ["security.W021"]  # see above
