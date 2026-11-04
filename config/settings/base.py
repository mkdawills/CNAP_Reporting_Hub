"""
Base settings for the CNAP Evaluation and Reporting Platform.

Every deployment-specific value comes from the environment (see .env.example).
dev.py and prod.py import this file and change only what differs.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
    TIME_ZONE=(str, "America/Chicago"),
    MEDIA_ROOT=(str, str(BASE_DIR / "media")),
    SSO_ENABLED=(bool, False),
    SMALL_N_THRESHOLD=(int, 5),
    SITE_URL=(str, "http://localhost:8000"),
    DEFAULT_FROM_EMAIL=(str, "CNAP Reporting Hub <no-reply@localhost>"),
    OUTCOME_STALE_DAYS=(int, 120),
    OUTCOME_REMINDER_EVERY_DAYS=(int, 30),
    GRANT_NUDGE_EVERY_DAYS=(int, 28),
    OUTCOME_REOPEN_DAYS=(int, 7),
    CNAP_GRANT_NUMBERS=(list, ["P20GM113109"]),
    PUBMED_CONTACT_EMAIL=(str, ""),
    EVALUATOR_EMAIL=(str, "mkwills@ksu.edu"),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    # CNAP apps, in dependency order
    "apps.common",
    "apps.audit",
    "apps.people",
    "apps.accounts",
    "apps.forms_engine",
    "apps.reporting",
    "apps.analytics",
    "apps.outcomes",
    "apps.portal",
    "apps.admin_center",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.LinkSessionGuard",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.common.context_processors.cnap",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# PostgreSQL only. SQLite is never used, even for tests: the constraints
# that protect CNAP data (composite foreign keys, exclusion constraints,
# NULLS NOT DISTINCT) exist only in PostgreSQL.
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = 60
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

MEDIA_URL = "/media/"
MEDIA_ROOT = env("MEDIA_ROOT")

# ---------------------------------------------------------------------------
# CNAP-specific settings
# ---------------------------------------------------------------------------

# Single sign-on. Build 1 runs on local accounts only. When K-State IT approves
# SSO, the adapter is configured here and local password login is disabled;
# nothing else in the application changes. See docs/sso.md.
SSO_ENABLED = env("SSO_ENABLED")

# Means for groups smaller than this are suppressed for every audience except
# holders of view_confidential_mentoring_data (analytics addendum, section D).
SMALL_N_THRESHOLD = env("SMALL_N_THRESHOLD")

SESSION_COOKIE_AGE = 60 * 60 * 8  # eight hours
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"

AUTHENTICATION_BACKENDS = ["apps.accounts.backends.RoleBackend"]

# Django 6 default; set now so link fields assume https.
FORMS_URLFIELD_ASSUME_HTTPS = True

# Links in e-mails point here (no trailing slash).
SITE_URL = env("SITE_URL").rstrip("/")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")
# Mail server as one URL, e.g. smtp+tls://user:password@smtp.k-state.edu:587 (K-State's relay). Default: print to
# the console, which sends nothing.
vars().update(env.email_url("EMAIL_URL", default="consolemail://"))

# Shown to respondents wherever they're told to contact the evaluator (MW, 2026-10-26).
EVALUATOR_EMAIL = env("EVALUATOR_EMAIL")

# Emailed sign-in links (decisions.md 2026-10-24). K-State people may use links only until single sign-on is on.
SIGNIN_LINK_DAYS = 7
SIGNIN_CODE_MINUTES = 15
SIGNIN_LINKS_FOR_KSTATE = env.bool("SIGNIN_LINKS_FOR_KSTATE", default=not SSO_ENABLED)

# Publications and grants (decisions.md 2026-10-26).
# A Planned or Submitted record not reviewed for this many days is "stale" and its owner gets a reminder,
# at most once every OUTCOME_REMINDER_EVERY_DAYS days.
OUTCOME_STALE_DAYS = env("OUTCOME_STALE_DAYS")
OUTCOME_REMINDER_EVERY_DAYS = env("OUTCOME_REMINDER_EVERY_DAYS")
# A planned grant proposal gets a friendly monthly check-in email instead of the stale reminder
# (MW 2026-11-03): at most one every GRANT_NUDGE_EVERY_DAYS days.
GRANT_NUDGE_EVERY_DAYS = env("GRANT_NUDGE_EVERY_DAYS")
# After a reporting period closes, people can add or update outcomes again this many days later (entry is open
# all year otherwise), so the Center can finish that period's numbers first.
OUTCOME_REOPEN_DAYS = env("OUTCOME_REOPEN_DAYS")
# CNAP's grant number(s) (the COBRE award is P20GM113109): used to tell whether a PubMed entry lists CNAP in its grant index.
CNAP_GRANT_NUMBERS = env("CNAP_GRANT_NUMBERS")
# Sent to NCBI with PubMed look-ups, as their usage policy asks.
PUBMED_CONTACT_EMAIL = env("PUBMED_CONTACT_EMAIL")
