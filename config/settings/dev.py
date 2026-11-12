"""Development settings: DEBUG on, e-mail to the console, no HTTPS redirects."""

import os

from .base import *  # noqa: F401,F403

# Development settings print e-mails (with sign-in links) to the console. Refuse to run them on a server that was
# configured for production (DEBUG=false in .env) but left on the development settings by mistake.
if os.environ.get("DEBUG", "").strip().lower() in ("false", "0", "no", "off"):
    raise RuntimeError(
        "DEBUG is false: use DJANGO_SETTINGS_MODULE=config.settings.prod on a server."
    )

DEBUG = True
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
# Static files are served by Django's runserver in development.
STORAGES["staticfiles"] = {"BACKEND": "apps.common.storage.VersionedStaticFilesStorage"}  # noqa: F405
# Each static URL carries the file’s last-changed time, so browsers fetch a fixed file fresh (MW 2026-11-12).

# GitHub Codespaces (MW 2026-11-12): the port forwarder sometimes passes the page's origin as https://localhost:8000,
# which Django's form check refused ("Origin checking failed"). Trust it, and the Codespace's own address, in Codespaces only.
if os.environ.get("CODESPACES") == "true":
    CSRF_TRUSTED_ORIGINS = [  # noqa: F405
        *CSRF_TRUSTED_ORIGINS,  # noqa: F405
        "https://localhost:8000",
        "http://localhost:8000",
        "https://*.app.github.dev",
    ]
