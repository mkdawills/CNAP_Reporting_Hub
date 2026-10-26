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
