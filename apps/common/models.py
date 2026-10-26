"""Abstract base models shared by every app."""

from django.db import models
from django.utils import timezone


class ActiveQuerySet(models.QuerySet):
    def active(self):
        return self.filter(archived_at__isnull=True)

    def archived(self):
        return self.filter(archived_at__isnull=False)


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ArchivableModel(TimestampedModel):
    """
    Institutional records are archived, never deleted. `archived_at` set means
    the row is hidden from ordinary screens but kept for history and audit.
    """

    archived_at = models.DateTimeField(null=True, blank=True)

    objects = ActiveQuerySet.as_manager()

    class Meta:
        abstract = True

    @property
    def is_archived(self):
        return self.archived_at is not None

    def archive(self):
        self.archived_at = timezone.now()
        self.save(update_fields=["archived_at", "updated_at"])

    def unarchive(self):
        self.archived_at = None
        self.save(update_fields=["archived_at", "updated_at"])
