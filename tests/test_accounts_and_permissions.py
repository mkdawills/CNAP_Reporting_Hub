"""Band A: users belong to people; roles bundle permissions; the confidential grant is explicit."""

import pytest
from django.contrib.auth.models import Permission
from django.db import IntegrityError, transaction

from apps.accounts.models import CONFIDENTIAL_MENTORING_PERM, ApplicationRole, User, UserRole
from apps.audit.models import AuditLog

from .conftest import make_person, make_user


def test_createsuperuser_creates_person(db):
    u = User.objects.create_superuser(
        "boot", "boot@k-state.example", "x" * 14, first_name="Boot", last_name="Strap"
    )
    assert u.person.full_name == "Boot Strap"
    assert u.person.primary_email == "boot@k-state.example"


def test_create_user_reuses_person_with_same_email(reference):
    p = make_person("Ada", "Lovelace", email="ada@k-state.example")
    u = User.objects.create_user(
        "ada", "ada@k-state.example", "x" * 14, first_name="Ada", last_name="Lovelace"
    )
    assert u.person_id == p.id


def test_one_user_per_person(reference):
    p = make_person("Ada", "Lovelace")
    make_user(p, username="ada1")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            make_user(p, username="ada2")


def test_roles_grant_permissions_through_backend(reference):
    p = make_person("Eve", "Staff")
    u = make_user(p, role=reference["roles"]["evaluation_staff"])
    assert u.has_perm("reporting.view_operational_dashboard")
    assert u.has_perm("reporting.review_responses")
    assert not u.has_perm("reporting.generate_assignments")
    admin = make_user(
        make_person("Ann", "Admin"), username="ann", role=reference["roles"]["administrator"]
    )
    assert admin.has_perm("reporting.generate_assignments")


def test_no_role_carries_the_confidential_permission(reference):
    for role in ApplicationRole.objects.all():
        assert not role.permissions.filter(codename="view_confidential_mentoring_data").exists(), (
            role.code
        )


def test_confidential_access_requires_explicit_grant(reference):
    admin = make_user(
        make_person("Ann", "Admin"), username="ann", role=reference["roles"]["administrator"]
    )
    assert admin.has_confidential_mentoring_access() is False
    superuser = User.objects.create_superuser(
        "root", "root@k-state.example", "x" * 14, first_name="R", last_name="T"
    )
    assert superuser.has_confidential_mentoring_access() is False, (
        "superuser status does not imply the grant"
    )
    app_label, codename = CONFIDENTIAL_MENTORING_PERM.split(".")
    admin.user_permissions.add(
        Permission.objects.get(content_type__app_label=app_label, codename=codename)
    )
    assert User.objects.get(pk=admin.pk).has_confidential_mentoring_access() is True


def test_scoped_reviewer_role_unique(reference):
    u = make_user(make_person("Rae", "Viewer"), username="rae")
    reviewer = reference["roles"]["reviewer"]
    ni = reference["cores"]["NI"]
    UserRole.objects.create(user=u, role=reviewer, scope_core=ni)
    UserRole.objects.create(user=u, role=reviewer)  # unscoped as well is a different row
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            UserRole.objects.create(user=u, role=reviewer)  # NULLS NOT DISTINCT


def test_disabled_user_cannot_authenticate(reference, client):
    p = make_person("Dee", "Sabled")
    u = make_user(p, username="dee")
    assert client.login(username="dee", password="Test-Password-2026")
    client.logout()
    u.is_enabled = False
    u.save()
    assert not client.login(username="dee", password="Test-Password-2026")


def test_login_is_audited(reference, client):
    p = make_person("Lou", "Gin")
    make_user(p, username="lou")
    client.login(username="lou", password="Test-Password-2026")
    assert AuditLog.objects.filter(
        action=AuditLog.Action.LOGIN, entity_type="accounts.User"
    ).exists()


def test_email_unique_case_insensitive(reference):
    from apps.people.models import PersonEmail

    p = make_person("Ada", "Lovelace", email="Ada@K-State.example")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PersonEmail.objects.create(
                person=make_person("Bob", "Builder", email="bob@k-state.example"),
                email="ada@k-state.example",
            )
    assert p.primary_email == "Ada@K-State.example"
