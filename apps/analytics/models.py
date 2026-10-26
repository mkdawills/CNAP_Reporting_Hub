"""
Band G: analytics and reporting (analytics addendum, section B).

Snapshots preserve what CNAP officially reported for a period. Themes are
reporting metadata attached to answers that are never edited. Metric
definitions mirror the code registry so a snapshot can name the version that
produced it. Build 1 creates these tables; Milestone 8 fills them.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.common.enums import NoteKind, Provenance, SnapshotKind, SnapshotStatus
from apps.common.models import TimestampedModel
from apps.forms_engine.models import FormDefinition
from apps.reporting.models import Answer, ReportingPeriod


class Theme(TimestampedModel):
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    form_definition = models.ForeignKey(
        FormDefinition,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="themes",
        help_text="Optional: a theme used for one instrument. Empty means any.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "themes"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "form_definition"], nulls_distinct=False, name="themes_name_unique"
            ),
        ]

    def __str__(self):
        return self.name


class AnswerThemeTag(models.Model):
    answer = models.ForeignKey(Answer, on_delete=models.CASCADE, related_name="theme_tags")
    theme = models.ForeignKey(Theme, on_delete=models.PROTECT, related_name="tags")
    tagged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    tagged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "answer_theme_tags"
        constraints = [
            models.UniqueConstraint(fields=["answer", "theme"], name="answer_theme_tags_unique")
        ]


class MetricDefinition(models.Model):
    """Mirror of the code registry (apps/analytics/metrics.py), refreshed on deploy."""

    code = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=200)
    definition_text = models.TextField(help_text="Plain-language 'how calculated'.")
    version = models.PositiveSmallIntegerField(default=1)
    domain = models.CharField(max_length=40)
    requires_permission = models.CharField(max_length=120, blank=True)
    dimensions = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "metric_definitions"
        ordering = ["domain", "code"]

    def __str__(self):
        return f"{self.code} v{self.version}"


class ReportingSnapshot(TimestampedModel):
    reporting_period = models.ForeignKey(
        ReportingPeriod, on_delete=models.PROTECT, related_name="snapshots"
    )
    version_no = models.PositiveSmallIntegerField()
    kind = models.CharField(
        max_length=20, choices=SnapshotKind.choices, default=SnapshotKind.PERIOD_CLOSE
    )
    status = models.CharField(
        max_length=12, choices=SnapshotStatus.choices, default=SnapshotStatus.GENERATED
    )
    provenance = models.CharField(
        max_length=20, choices=Provenance.choices, default=Provenance.PLATFORM
    )
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    finalized_at = models.DateTimeField(null=True, blank=True)
    finalized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    supersedes = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="superseded_by"
    )
    definitions = models.JSONField(
        default=dict, blank=True, help_text="Registry version, form versions used, filters."
    )
    regeneration_reason = models.TextField(blank=True)

    class Meta:
        db_table = "reporting_snapshots"
        ordering = ["reporting_period", "-version_no"]
        constraints = [
            models.UniqueConstraint(
                fields=["reporting_period", "version_no"], name="reporting_snapshots_version_unique"
            ),
            models.CheckConstraint(
                condition=~Q(status="finalized") | Q(finalized_at__isnull=False),
                name="reporting_snapshots_finalized_at",
            ),
            models.CheckConstraint(
                condition=Q(status__in=[s.value for s in SnapshotStatus]),
                name="reporting_snapshots_status_valid",
            ),
        ]

    def __str__(self):
        return f"{self.reporting_period.short_label} snapshot v{self.version_no} ({self.status})"


class SnapshotResult(models.Model):
    snapshot = models.ForeignKey(
        ReportingSnapshot, on_delete=models.CASCADE, related_name="results"
    )
    metric_code = models.CharField(max_length=80, db_index=True)
    subject_type = models.CharField(
        max_length=20,
        help_text="form, section, measure, question, core, resource, pathway, overall",
    )
    subject_id = models.BigIntegerField(null=True, blank=True)
    group_key = models.CharField(max_length=120, blank=True, default="")
    n = models.IntegerField(null=True, blank=True)
    value = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    detail = models.JSONField(
        default=dict,
        blank=True,
        help_text="Distribution counts and percentages, SD, N/A count, flags.",
    )
    is_confidential = models.BooleanField(default=False)

    class Meta:
        db_table = "snapshot_results"
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "metric_code", "subject_type", "subject_id", "group_key"],
                nulls_distinct=False,
                name="snapshot_results_unique",
            ),
        ]


class SnapshotMember(models.Model):
    """Exactly which records a snapshot counted: the basis for drill-down and regeneration diffs."""

    snapshot = models.ForeignKey(
        ReportingSnapshot, on_delete=models.CASCADE, related_name="members"
    )
    record_type = models.CharField(max_length=40)
    record_id = models.BigIntegerField()

    class Meta:
        db_table = "snapshot_members"
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot", "record_type", "record_id"], name="snapshot_members_unique"
            )
        ]


class SnapshotNote(TimestampedModel):
    snapshot = models.ForeignKey(ReportingSnapshot, on_delete=models.CASCADE, related_name="notes")
    kind = models.CharField(max_length=24, choices=NoteKind.choices)
    section_ref = models.CharField(
        max_length=120, blank=True, help_text="Which instrument or table the note belongs to."
    )
    body = models.TextField()
    evidence = models.JSONField(default=dict, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    is_confidential = models.BooleanField(default=False)

    class Meta:
        db_table = "snapshot_notes"
        ordering = ["snapshot", "section_ref", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(kind__in=[k.value for k in NoteKind]), name="snapshot_notes_kind_valid"
            ),
        ]


class DataQualityDismissal(TimestampedModel):
    check_code = models.CharField(max_length=80)
    record_type = models.CharField(max_length=40)
    record_id = models.BigIntegerField()
    dismissed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    reason = models.TextField()

    class Meta:
        db_table = "data_quality_dismissals"
        constraints = [
            models.UniqueConstraint(
                fields=["check_code", "record_type", "record_id"],
                name="data_quality_dismissals_unique",
            ),
        ]
