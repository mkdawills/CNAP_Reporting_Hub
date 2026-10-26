"""
Audit log: consequential events only (review section 37).

Use `record_event()` from service code rather than creating rows directly, so
every entry carries the same shape.
"""

from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "create", "Created"
        UPDATE = "update", "Updated"
        ARCHIVE = "archive", "Archived"
        UNARCHIVE = "unarchive", "Unarchived"
        STATUS_CHANGE = "status_change", "Status changed"
        SUBMIT = "submit", "Submitted"
        REOPEN = "reopen", "Reopened"
        EXEMPT = "exempt", "Exempted"
        ASSIGN = "assign", "Assignments generated"
        IMPORT = "import", "Roster import committed"
        ACTIVATE_VERSION = "activate_version", "Form version activated"
        CORRECTION = "correction", "Administrative correction"
        GRANT_PERMISSION = "grant_permission", "Permission granted"
        REVOKE_PERMISSION = "revoke_permission", "Permission revoked"
        EXPORT = "export", "Export produced"
        SNAPSHOT = "snapshot", "Reporting snapshot generated or finalized"
        LOGIN = "login", "Login"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    at = models.DateTimeField(auto_now_add=True, db_index=True)
    action = models.CharField(max_length=32, choices=Action.choices)
    entity_type = models.CharField(max_length=64, db_index=True, help_text="app_label.ModelName")
    entity_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    entity_repr = models.CharField(max_length=255, blank=True)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True)

    class Meta:
        db_table = "audit_log"
        ordering = ["-at"]
        indexes = [models.Index(fields=["entity_type", "entity_id"])]

    def __str__(self):
        return f"{self.at:%Y-%m-%d %H:%M} {self.action} {self.entity_type}#{self.entity_id}"


def record_event(actor, action, entity, *, old=None, new=None, reason=""):
    """
    Write one audit row for a consequential event.

    `entity` is a model instance (its type and id are recorded) or a string
    for events without a single record (for example a roster import run).
    """
    if isinstance(entity, str):
        entity_type, entity_id, entity_repr = entity, None, ""
    else:
        entity_type = f"{entity._meta.app_label}.{entity.__class__.__name__}"
        entity_id = entity.pk
        entity_repr = str(entity)[:255]
    return AuditLog.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_repr=entity_repr,
        old_value=old,
        new_value=new,
        reason=reason or "",
    )
