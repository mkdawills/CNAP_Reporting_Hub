"""Development settings: DEBUG on, e-mail to the console, no HTTPS redirects."""

from .base import *  # noqa: F401,F403

DEBUG = True
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
# Static files are served by Django's runserver in development.
STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}  # noqa: F405
