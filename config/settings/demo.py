"""Demo settings for a public test copy outside K-State (MW 2026-11-09). Fictional data only.

The same security as production (HTTPS, secure cookies, no debug), but emails print to the host's
log instead of being sent, because a test copy has no mail server. Never use with real CNAP data.
"""

from .base import *  # noqa: F401,F403

DEBUG = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
TRUST_X_FORWARDED_FOR = True
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
# Tell every visitor this is a test copy.
DEMO_SITE = True
