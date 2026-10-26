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
STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}  # noqa: F405
