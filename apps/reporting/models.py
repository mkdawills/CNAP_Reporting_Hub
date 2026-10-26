"""
Band D: reporting periods, roster imports, assignments, responses, answers, files.

An assignment is the explicit statement that a person owes a form for a
period (and a project or core when relevant). Nothing is owed until one
exists and nothing counts as done until it says so. Its uniqueness rule
(review 15.1) is a database constraint and is what makes generation safe to
rerun. The composite foreign keys that keep the copied `form_definition_id`
and `context_kind` truthful are SQL in migrations/0002_constraints.py.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.common.enums import (
    COMPLETE_STATUSES,
    AssignmentSource,
    AssignmentStatus,
    ContextKind,
    ImportMatchKind,
    ImportStatus,
    PeriodStatus,
    PeriodType,
    Provenance,
)
from apps.common.models import TimestampedModel
from apps.forms_engine.models import (
    CompletionPathway,
    FormDefinition,
    FormVersion,
    Question,
    QuestionOption,
)
from apps.people.models import Core, Person, PersonRelationship, Project


class ReportingPeriod(TimestampedModel):
    name = models.CharField(max_length=120, help_text="e.g. 'Year 10 Fall'")
    short_label = models.CharField(max_length=20, unique=True, help_text="e.g. 'Y10A' or 'Y10-1'")
    period_type = models.CharField(
        max_length=12, choices=PeriodType.choices, default=PeriodType.SEMIANNUAL
    )
    grant_year = models.PositiveSmallIntegerField(help_text="Center grant year, e.g. 10")
    sequence = models.PositiveSmallIntegerField(
        default=1, help_text="Order within the grant year: 1 = first, 2 = second"
    )
    display_order = models.PositiveIntegerField(editable=False)
    start_date = models.DateField()
    end_date = models.DateField()
    opens_at = models.DateTimeField(help_text="When assignments become available to respondents.")
    due_at = models.DateTimeField()
    closes_at = models.DateTimeField(
        null=True, blank=True, help_text="Planned close; the administrator closes explicitly."
    )
    status = models.CharField(
        max_length=10, choices=PeriodStatus.choices, default=PeriodStatus.DRAFT
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "reporting_periods"
        ordering = ["-display_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["grant_year", "sequence"], name="reporting_periods_year_sequence_unique"
            ),
            models.CheckConstraint(
                condition=Q(end_date__gte=models.F("start_date")),
                name="reporting_periods_dates_ordered",
            ),
            models.CheckConstraint(
                condition=Q(due_at__gte=models.F("opens_at")),
                name="reporting_periods_due_after_open",
            ),
            models.CheckConstraint(
                condition=Q(status__in=[s.value for s in PeriodStatus]),
                name="reporting_periods_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(status__in=["draft", "open"], closed_at__isnull=True)
                | Q(status__in=["closed", "finalized"], closed_at__isnull=False),
                name="reporting_periods_closed_at_matches_status",
            ),
            models.CheckConstraint(
                condition=~Q(status="finalized") | Q(finalized_at__isnull=False),
                name="reporting_periods_finalized_at_when_finalized",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.short_label})"

    def save(self, *args, **kwargs):
        self.display_order = self.grant_year * 10 + self.sequence
        super().save(*args, **kwargs)

    @property
    def is_open(self):
        return self.status == PeriodStatus.OPEN


class File(TimestampedModel):
    """A stored object. Linked to its owners through join tables with real foreign keys (review 15.2)."""

    storage_key = models.FileField(upload_to="uploads/%Y/%m/", max_length=500, unique=True)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120)
    byte_size = models.BigIntegerField()
    sha256 = models.CharField(max_length=64, db_index=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="uploaded_files"
    )
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "files"

    def __str__(self):
        return self.original_filename


class RosterImport(TimestampedModel):
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    file = models.ForeignKey(
        File, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    original_filename = models.CharField(max_length=255)
    status = models.CharField(
        max_length=10, choices=ImportStatus.choices, default=ImportStatus.PARSED
    )
    committed_at = models.DateTimeField(null=True, blank=True)
    committed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    summary = models.JSONField(
        default=dict, blank=True, help_text="Counts by match kind, decisions taken."
    )

    class Meta:
        db_table = "roster_imports"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Roster import {self.pk}: {self.original_filename} ({self.status})"


class RosterImportRow(models.Model):
    roster_import = models.ForeignKey(RosterImport, on_delete=models.CASCADE, related_name="rows")
    row_number = models.PositiveIntegerField()
    email = models.EmailField(blank=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    raw = models.JSONField(default=dict, blank=True)
    match_kind = models.CharField(max_length=20, choices=ImportMatchKind.choices)
    matched_person = models.ForeignKey(
        Person, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decision = models.CharField(
        max_length=20,
        blank=True,
        help_text="accept / skip / merge-into:<person_id> / end-membership",
    )
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "roster_import_rows"
        ordering = ["roster_import", "row_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["roster_import", "row_number"], name="roster_import_rows_unique"
            ),
            models.CheckConstraint(
                condition=Q(match_kind__in=[k.value for k in ImportMatchKind]),
                name="roster_import_rows_kind_valid",
            ),
        ]


class Assignment(TimestampedModel):
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="assignments")
    form_version = models.ForeignKey(
        FormVersion, on_delete=models.PROTECT, related_name="assignments"
    )
    form_definition = models.ForeignKey(
        FormDefinition, on_delete=models.PROTECT, related_name="assignments", editable=False
    )
    context_kind = models.CharField(max_length=10, choices=ContextKind.choices, editable=False)
    reporting_period = models.ForeignKey(
        ReportingPeriod, on_delete=models.PROTECT, related_name="assignments"
    )
    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.PROTECT, related_name="assignments"
    )
    core = models.ForeignKey(
        Core, null=True, blank=True, on_delete=models.PROTECT, related_name="assignments"
    )
    source = models.CharField(max_length=14, choices=AssignmentSource.choices)
    source_relationship = models.ForeignKey(
        PersonRelationship,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assignments",
    )
    status = models.CharField(
        max_length=20, choices=AssignmentStatus.choices, default=AssignmentStatus.NOT_STARTED
    )
    completion_pathway = models.ForeignKey(
        CompletionPathway, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    due_at = models.DateTimeField()
    assigned_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reopened_at = models.DateTimeField(null=True, blank=True)
    exempt_reason = models.TextField(blank=True)
    admin_notes = models.TextField(
        blank=True, help_text="Administrators only; never respondent data."
    )
    reminder_state = models.JSONField(default=dict, blank=True)
    provenance = models.CharField(
        max_length=20, choices=Provenance.choices, default=Provenance.PLATFORM
    )

    class Meta:
        db_table = "assignments"
        ordering = ["-reporting_period__display_order", "person__last_name"]
        permissions = [
            ("view_operational_dashboard", "Can view the administrator screens"),
            ("generate_assignments", "Can generate and exempt assignments"),
            ("manage_center", "Can change Center setup: people, periods, assignments, snapshots"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(context_kind="none", project__isnull=True, core__isnull=True)
                    | Q(context_kind="project", project__isnull=False, core__isnull=True)
                    | Q(context_kind="core", core__isnull=False, project__isnull=True)
                ),
                name="assignments_context_shape",
            ),
            models.UniqueConstraint(
                fields=["person", "form_definition", "reporting_period", "project", "core"],
                nulls_distinct=False,
                name="assignments_one_per_context",
            ),
            models.CheckConstraint(
                condition=~Q(status="exempt") | ~Q(exempt_reason=""),
                name="assignments_exempt_has_reason",
            ),
            models.CheckConstraint(
                condition=~Q(status__in=["submitted", "completed_opt_out"])
                | Q(completion_pathway__isnull=False),
                name="assignments_pathway_when_done",
            ),
            models.CheckConstraint(
                condition=Q(status__in=[s.value for s in AssignmentStatus]),
                name="assignments_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(source__in=[s.value for s in AssignmentSource]),
                name="assignments_source_valid",
            ),
        ]

    def __str__(self):
        ctx = self.project or self.core
        return (
            f"{self.person}: {self.form_definition.name} / {self.reporting_period.short_label}"
            + (f" ({ctx})" if ctx else "")
        )

    def fill_copied_columns(self):
        self.form_definition_id = self.form_version.form_definition_id
        self.context_kind = self.form_version.form_definition.context_kind

    def clean(self):
        self.fill_copied_columns()
        if self.context_kind == ContextKind.PROJECT and not self.project_id:
            raise ValidationError({"project": "This form is about a project; choose one."})
        if self.context_kind == ContextKind.CORE and not self.core_id:
            raise ValidationError({"core": "This form is about a core; choose one."})
        if self.context_kind == ContextKind.NONE and (self.project_id or self.core_id):
            raise ValidationError("This form has no project or core context.")
        if self.status == AssignmentStatus.EXEMPT and not self.exempt_reason.strip():
            raise ValidationError({"exempt_reason": "An exemption needs a reason."})

    def save(self, *args, **kwargs):
        self.fill_copied_columns()
        super().save(*args, **kwargs)

    @property
    def is_complete(self):
        return self.status in COMPLETE_STATUSES

    def is_overdue(self, now=None):
        from django.utils import timezone

        now = now or timezone.now()
        return (
            self.status not in COMPLETE_STATUSES
            and self.status != AssignmentStatus.EXEMPT
            and self.due_at < now
        )


class Response(TimestampedModel):
    """One submission attempt. A reopen creates a new current response; the earlier one stays."""

    assignment = models.ForeignKey(Assignment, on_delete=models.PROTECT, related_name="responses")
    form_version = models.ForeignKey(
        FormVersion, on_delete=models.PROTECT, related_name="responses", editable=False
    )
    is_current = models.BooleanField(default=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reopened_at = models.DateTimeField(null=True, blank=True)
    provenance = models.CharField(
        max_length=20, choices=Provenance.choices, default=Provenance.PLATFORM
    )

    class Meta:
        db_table = "responses"
        permissions = [
            (
                "view_confidential_mentoring_data",
                "Can view individual mentor and mentee responses, verbatims and exports",
            ),
            (
                "view_identified_survey_responses",
                "Can read core, NeuroSync and Team Science responses with names (evaluator)",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["assignment"], condition=Q(is_current=True), name="responses_one_current"
            ),
        ]

    def __str__(self):
        return f"Response {self.pk} for {self.assignment}"

    def save(self, *args, **kwargs):
        self.form_version_id = self.assignment.form_version_id
        super().save(*args, **kwargs)

    @property
    def is_submitted(self):
        return self.submitted_at is not None


class Answer(TimestampedModel):
    """
    One answer to one question (per repeat for repeatable sections). Exactly
    one value column is used, matching the question type; multi-select rows
    use AnswerSelectedOption and file uploads use AnswerFile.
    """

    response = models.ForeignKey(Response, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.PROTECT, related_name="answers")
    repeat_index = models.PositiveSmallIntegerField(default=0)
    value_text = models.TextField(null=True, blank=True)
    value_number = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    value_date = models.DateField(null=True, blank=True)
    option = models.ForeignKey(
        QuestionOption, null=True, blank=True, on_delete=models.PROTECT, related_name="answers"
    )
    person_value = models.ForeignKey(
        Person, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    project_value = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "answers"
        constraints = [
            models.UniqueConstraint(
                fields=["response", "question", "repeat_index"], name="answers_unique_per_question"
            ),
        ]

    def __str__(self):
        return f"Answer to {self.question.code}"


class AnswerSelectedOption(models.Model):
    answer = models.ForeignKey(Answer, on_delete=models.CASCADE, related_name="selected_options")
    option = models.ForeignKey(QuestionOption, on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "answer_selected_options"
        constraints = [
            models.UniqueConstraint(
                fields=["answer", "option"], name="answer_selected_options_unique"
            )
        ]


class AnswerFile(models.Model):
    answer = models.ForeignKey(Answer, on_delete=models.CASCADE, related_name="files")
    file = models.ForeignKey(File, on_delete=models.PROTECT, related_name="answer_links")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "answer_files"
        constraints = [
            models.UniqueConstraint(fields=["answer", "file"], name="answer_files_unique")
        ]
