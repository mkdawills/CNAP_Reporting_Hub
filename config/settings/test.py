"""Test settings: same PostgreSQL requirement, faster password hashing."""

from .base import *  # noqa: F401,F403

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}  # noqa: F405

SIGNIN_SEND_ASYNC = False  # send in the request so tests can read the mail outbox
