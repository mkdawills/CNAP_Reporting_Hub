"""Record logins and failed logins as audit events."""

from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

from .models import AuditLog, record_event


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    record_event(user, AuditLog.Action.LOGIN, user)


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request, **kwargs):
    record_event(
        None,
        AuditLog.Action.LOGIN,
        "accounts.login_failed",
        new={"username": credentials.get("username", "")[:150]},
    )
