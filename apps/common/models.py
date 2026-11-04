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


class PageFeedback(models.Model):
    """A note from anyone signed in about the page they were on: design, clarity, logic, speed,
    motivating touches, or something broken (MW 2026-11-04). Read on the admin Page feedback list."""

    TOPICS = [
        ("design", "Design and look"),
        ("clarity", "Clarity of wording or directions"),
        ("logic", "Logic or flow"),
        ("speed", "Speed and efficiency"),
        ("fun", "Fun and motivating touches"),
        ("broken", "Something is broken"),
        ("other", "Something else"),
    ]
    user = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    path = models.CharField(max_length=500)
    page_title = models.CharField(max_length=300, blank=True)
    topic = models.CharField(max_length=10, choices=TOPICS)
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "page_feedback"
        ordering = ["-created_at"]


class SitePhoto(models.Model):
    """The optional photo beside the sign-in box (MW 2026-11-04). Only the newest active one shows.
    The sign-in page is public, so this image is visible to anyone with the site's address."""

    image = models.ImageField(upload_to="site/")
    alt_text = models.CharField(max_length=300)
    caption = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)
    uploaded_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "site_photos"
        ordering = ["-created_at"]

    @classmethod
    def current(cls):
        return cls.objects.filter(is_active=True).first()
