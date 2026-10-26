"""
Band A: authentication and application permissions.

A user is a person who logs in; every user belongs to exactly one Person.
Application roles are bundles of permissions and are never derived from CNAP
relationships. The confidential-mentoring permission is granted to named
users only and is never part of a role (analytics addendum, section D).
"""

from django.conf import settings
from django.contrib.auth.models import AbstractUser, Permission, UserManager
from django.db import models

from apps.common.models import TimestampedModel
from apps.people.models import Core, Person

CONFIDENTIAL_MENTORING_PERM = "reporting.view_confidential_mentoring_data"
IDENTIFIED_SURVEYS_PERM = "reporting.view_identified_survey_responses"
# Permissions that are only ever granted to a named user, never through a role.
DIRECT_GRANT_PERMS = (CONFIDENTIAL_MENTORING_PERM, IDENTIFIED_SURVEYS_PERM)


class CnapUserManager(UserManager):
    """Creates the Person row alongside a user when none is supplied (createsuperuser)."""

    def _ensure_person(self, extra_fields):
        if extra_fields.get("person") is None:
            from apps.people.models import PersonEmail

            email = extra_fields.get("email") or ""
            person = None
            if email:
                row = (
                    PersonEmail.objects.filter(email__iexact=email).select_related("person").first()
                )
                person = row.person if row else None
            if person is None:
                person = Person.objects.create(
                    first_name=extra_fields.get("first_name") or "",
                    last_name=extra_fields.get("last_name") or "",
                )
                if email:
                    PersonEmail.objects.create(person=person, email=email, is_primary=True)
            extra_fields["person"] = person
        return extra_fields

    def create_user(self, username, email=None, password=None, **extra_fields):
        extra_fields = self._ensure_person({**extra_fields, "email": email})
        extra_fields.pop("email", None)
        return super().create_user(username, email, password, **extra_fields)

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields = self._ensure_person({**extra_fields, "email": email})
        extra_fields.pop("email", None)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    person = models.OneToOneField(Person, on_delete=models.PROTECT, related_name="user")
    is_enabled = models.BooleanField(
        default=True, help_text="Disabled users cannot log in; the record stays."
    )

    REQUIRED_FIELDS = ["email", "first_name", "last_name"]

    objects = CnapUserManager()

    class Meta:
        db_table = "users"

    def __str__(self):
        return self.get_full_name() or self.username

    def role_codes(self):
        return list(self.user_roles.values_list("role__code", flat=True))

    def _has_direct_grant(self, perm):
        if not self.is_active or not self.is_enabled:
            return False
        cache = self.__dict__.setdefault("_direct_grant_cache", {})
        if perm not in cache:
            app_label, codename = perm.split(".")
            cache[perm] = self.user_permissions.filter(
                content_type__app_label=app_label, codename=codename
            ).exists()
        return cache[perm]

    def has_confidential_mentoring_access(self):
        """
        True only for an explicit, direct grant on this user. Roles never carry
        it, and being a superuser does not imply it: the data-access layer calls
        this method, not has_perm(), so nothing bypasses the rule by accident.
        """
        return self._has_direct_grant(CONFIDENTIAL_MENTORING_PERM)

    def has_identified_survey_access(self):
        """
        The evaluator's grant: read core, NeuroSync and Team Science responses
        with the respondent's name. Direct grant only, like the confidential one.
        Without it, administrators see those surveys de-identified.
        """
        return self._has_direct_grant(IDENTIFIED_SURVEYS_PERM)


class ApplicationRole(TimestampedModel):
    class Code(models.TextChoices):
        ADMINISTRATOR = "administrator", "Administrator (manages the Center)"
        CENTER_LEADERSHIP = "center_leadership", "Administrator, view only"
        STANDARD_USER = "standard_user", "Standard User"

    code = models.CharField(max_length=40, unique=True, choices=Code.choices)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    permissions = models.ManyToManyField(Permission, blank=True, related_name="application_roles")

    class Meta:
        db_table = "application_roles"
        ordering = ["name"]

    def __str__(self):
        return self.name


class UserRole(TimestampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_roles")
    role = models.ForeignKey(ApplicationRole, on_delete=models.PROTECT, related_name="user_roles")
    scope_core = models.ForeignKey(
        Core,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Reserved for a future core-scoped role. Empty means no scope.",
    )
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    granted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_roles"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "role", "scope_core"],
                nulls_distinct=False,
                name="user_roles_unique",
            ),
        ]

    def __str__(self):
        return f"{self.user}: {self.role}" + (f" ({self.scope_core})" if self.scope_core_id else "")


class SignInLink(models.Model):
    """A single-use emailed sign-in link (decisions.md 2026-10-24, sign-in plan). Only a hash of the token is kept."""

    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="signin_links")
    email = models.EmailField()
    token_hash = models.CharField(max_length=64, unique=True)
    purpose = models.CharField(
        max_length=20, default="request", help_text="request, period_open or reminder"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    used_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = "signin_links"
        indexes = [models.Index(fields=["email", "created_at"])]

    def __str__(self):
        return f"Sign-in link for {self.email} ({self.purpose})"


class SignInCode(models.Model):
    """A 6-digit code e-mailed before a link-signed-in person opens a confidential mentoring form."""

    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="signin_codes")
    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "signin_codes"


class FailedLogin(models.Model):
    """Failed password sign-ins, for throttling (kept 1 day)."""

    username = models.CharField(max_length=150)
    ip = models.GenericIPAddressField(null=True, blank=True)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "failed_logins"
        indexes = [models.Index(fields=["username", "at"]), models.Index(fields=["ip", "at"])]
