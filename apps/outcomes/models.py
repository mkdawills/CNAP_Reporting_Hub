"""
Band E: persistent research outcomes — publications, presentations, grants.

Build 1 creates these tables and migrations and registers them read-only in
the admin; their user interfaces arrive in Build 2. One real-world outcome is
one row, linked to many people, projects and resources; lifecycle changes
append history rows. Nothing here is ever hard-deleted.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.common.enums import (
    GrantRole,
    GrantStatus,
    PresentationType,
    PrimeOrSubaward,
    PublicationStatus,
    PublicationSubstatus,
    PublicationType,
)
from apps.common.models import ArchivableModel
from apps.people.models import Person, Project, Resource
from apps.reporting.models import File

# ---------------------------------------------------------------------------
# Publications
# ---------------------------------------------------------------------------


class Publication(ArchivableModel):
    """One manuscript = one record, followed through Planned -> Submitted -> Published / Declined."""

    title = models.CharField(max_length=500)
    publication_type = models.CharField(max_length=20, choices=PublicationType.choices)
    status = models.CharField(
        max_length=12, choices=PublicationStatus.choices, default=PublicationStatus.PLANNED
    )
    substatus = models.CharField(
        max_length=14,
        choices=PublicationSubstatus.choices,
        null=True,
        blank=True,
        help_text="Only while Submitted: under review, accepted, in press.",
    )
    author_display_text = models.TextField(
        blank=True, help_text="Full author list as entered, citation style."
    )
    journal = models.CharField(
        max_length=300,
        blank=True,
        help_text="Anticipated journal while Planned; actual afterwards.",
    )
    anticipated_submission_month = models.DateField(
        null=True, blank=True, help_text="First day of the month."
    )
    submission_date = models.DateField(null=True, blank=True)
    anticipated_publication_date = models.DateField(null=True, blank=True)
    publication_date = models.DateField(null=True, blank=True)
    decline_date = models.DateField(null=True, blank=True)
    pubmed_url = models.URLField(max_length=500, blank=True)
    cnap_cited = models.BooleanField(null=True, blank=True)
    cnap_in_grant_index = models.BooleanField(null=True, blank=True)
    has_foreign_authors = models.BooleanField(null=True, blank=True)
    resubmission_intent = models.BooleanField(null=True, blank=True)
    resubmission_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="resubmissions"
    )
    comments = models.TextField(blank=True)
    resources_other_text = models.CharField(
        max_length=300,
        blank=True,
        help_text="What 'Other' means when Other is among the Center resources.",
    )
    confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time the person reviewed this record ('Confirm no changes' or an update).",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "publications"
        ordering = ["-updated_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=[s.value for s in PublicationStatus]),
                name="publications_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(publication_type__in=[t.value for t in PublicationType]),
                name="publications_type_valid",
            ),
            models.CheckConstraint(
                condition=Q(substatus__isnull=True) | Q(status="submitted"),
                name="publications_substatus_only_when_submitted",
            ),
        ]

    def __str__(self):
        return self.title[:80]

    def clean(self):
        if self.substatus and self.status != PublicationStatus.SUBMITTED:
            raise ValidationError(
                {"substatus": "A substatus applies only while the manuscript is Submitted."}
            )


class PublicationPerson(models.Model):
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name="people")
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="publication_links")
    author_order = models.PositiveSmallIntegerField(default=0)
    author_role = models.CharField(max_length=60, blank=True)

    class Meta:
        db_table = "publication_people"
        constraints = [
            models.UniqueConstraint(
                fields=["publication", "person"], name="publication_people_unique"
            )
        ]


class PublicationProject(models.Model):
    publication = models.ForeignKey(
        Publication, on_delete=models.CASCADE, related_name="project_links"
    )
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="publication_links")

    class Meta:
        db_table = "publication_projects"
        constraints = [
            models.UniqueConstraint(
                fields=["publication", "project"], name="publication_projects_unique"
            )
        ]


class PublicationResource(models.Model):
    publication = models.ForeignKey(
        Publication, on_delete=models.CASCADE, related_name="resource_links"
    )
    resource = models.ForeignKey(
        Resource, on_delete=models.PROTECT, related_name="publication_links"
    )
    is_anticipated = models.BooleanField(
        default=False, help_text="Entered while Planned; confirmed later."
    )

    class Meta:
        db_table = "publication_resources"
        constraints = [
            models.UniqueConstraint(
                fields=["publication", "resource"], name="publication_resources_unique"
            )
        ]


class PublicationFile(models.Model):
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name="files")
    file = models.ForeignKey(File, on_delete=models.PROTECT, related_name="publication_links")

    class Meta:
        db_table = "publication_files"
        constraints = [
            models.UniqueConstraint(fields=["publication", "file"], name="publication_files_unique")
        ]


class PublicationStatusHistory(models.Model):
    publication = models.ForeignKey(
        Publication, on_delete=models.CASCADE, related_name="status_history"
    )
    from_status = models.CharField(
        max_length=12, choices=PublicationStatus.choices, null=True, blank=True
    )
    to_status = models.CharField(max_length=12, choices=PublicationStatus.choices)
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    note = models.TextField(blank=True)

    class Meta:
        db_table = "publication_status_history"
        ordering = ["publication", "changed_at"]


# ---------------------------------------------------------------------------
# Presentations
# ---------------------------------------------------------------------------


class Presentation(ArchivableModel):
    """Recorded once and linked to every relevant project; never duplicated per project."""

    presentation_type = models.CharField(max_length=20, choices=PresentationType.choices)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    author_display_text = models.TextField(blank=True, help_text="Full author list as entered.")
    event = models.CharField(max_length=300, blank=True)
    location = models.CharField(max_length=300, blank=True)
    presented_on = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "presentations"
        ordering = ["-presented_on"]
        constraints = [
            models.CheckConstraint(
                condition=Q(presentation_type__in=[t.value for t in PresentationType]),
                name="presentations_type_valid",
            ),
        ]

    def __str__(self):
        return self.title[:80]


class PresentationPerson(models.Model):
    presentation = models.ForeignKey(Presentation, on_delete=models.CASCADE, related_name="people")
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="presentation_links")
    author_order = models.PositiveSmallIntegerField(default=0)
    is_presenter = models.BooleanField(default=False)

    class Meta:
        db_table = "presentation_people"
        constraints = [
            models.UniqueConstraint(
                fields=["presentation", "person"], name="presentation_people_unique"
            )
        ]


class PresentationProject(models.Model):
    presentation = models.ForeignKey(
        Presentation, on_delete=models.CASCADE, related_name="project_links"
    )
    project = models.ForeignKey(
        Project, on_delete=models.PROTECT, related_name="presentation_links"
    )

    class Meta:
        db_table = "presentation_projects"
        constraints = [
            models.UniqueConstraint(
                fields=["presentation", "project"], name="presentation_projects_unique"
            )
        ]


class PresentationResource(models.Model):
    presentation = models.ForeignKey(
        Presentation, on_delete=models.CASCADE, related_name="resource_links"
    )
    resource = models.ForeignKey(
        Resource, on_delete=models.PROTECT, related_name="presentation_links"
    )

    class Meta:
        db_table = "presentation_resources"
        constraints = [
            models.UniqueConstraint(
                fields=["presentation", "resource"], name="presentation_resources_unique"
            )
        ]


class PresentationFile(models.Model):
    presentation = models.ForeignKey(Presentation, on_delete=models.CASCADE, related_name="files")
    file = models.ForeignKey(File, on_delete=models.PROTECT, related_name="presentation_links")

    class Meta:
        db_table = "presentation_files"
        constraints = [
            models.UniqueConstraint(
                fields=["presentation", "file"], name="presentation_files_unique"
            )
        ]


# ---------------------------------------------------------------------------
# Grants and awards
# ---------------------------------------------------------------------------


class GrantFamily(ArchivableModel):
    """The 'Parent Grant ID': one proposal idea, many submission attempts (A0, A1, ...)."""

    title = models.CharField(max_length=500)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "grant_families"
        verbose_name_plural = "grant families"

    def __str__(self):
        return self.title[:80]


class GrantSubmission(ArchivableModel):
    """Each submission attempt is one record. The version (A0, A1, ...) is system-set and immutable."""

    grant_family = models.ForeignKey(
        GrantFamily, on_delete=models.PROTECT, related_name="submissions"
    )
    version_no = models.PositiveSmallIntegerField(
        editable=False, help_text="0 = A0, 1 = A1, ... set by the system."
    )
    status = models.CharField(
        max_length=12, choices=GrantStatus.choices, default=GrantStatus.PLANNED
    )
    funding_agency = models.CharField(max_length=200, blank=True)
    opportunity_url = models.URLField(max_length=500, blank=True)
    mechanism = models.CharField(max_length=120, blank=True)
    project_title = models.CharField(max_length=500)
    anticipated_submission_date = models.DateField(null=True, blank=True)
    submission_date = models.DateField(null=True, blank=True)
    anticipated_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Planned stage, preliminary.",
    )
    planned_estimated_direct = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Planned stage, preliminary.",
    )
    requested_total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    requested_direct = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    requested_indirect = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    award_notice_date = models.DateField(null=True, blank=True)
    project_start_date = models.DateField(null=True, blank=True)
    project_end_date = models.DateField(null=True, blank=True)
    award_total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    award_direct = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    award_indirect = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    grant_number = models.CharField(max_length=120, blank=True)
    prime_or_subaward = models.CharField(max_length=10, choices=PrimeOrSubaward.choices, blank=True)
    cnap_acknowledged = models.BooleanField(null=True, blank=True)
    cnap_credited_in_publications = models.BooleanField(null=True, blank=True)
    has_foreign_component = models.BooleanField(null=True, blank=True)
    decision_date = models.DateField(null=True, blank=True)
    decision_comments = models.TextField(blank=True)
    discussed_with_program_officer = models.BooleanField(null=True, blank=True)
    program_officer_name = models.CharField(max_length=200, blank=True)
    discussion_date = models.DateField(null=True, blank=True)
    feedback_shared_with_cnap = models.BooleanField(null=True, blank=True)
    plans_to_resubmit = models.BooleanField(null=True, blank=True)
    resources_other_text = models.CharField(max_length=300, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    resubmission_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="resubmissions"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "grant_submissions"
        ordering = ["grant_family", "version_no"]
        constraints = [
            models.UniqueConstraint(
                fields=["grant_family", "version_no"], name="grant_submissions_version_unique"
            ),
            models.CheckConstraint(
                condition=Q(status__in=[s.value for s in GrantStatus]),
                name="grant_submissions_status_valid",
            ),
        ]

    def __str__(self):
        return f"{self.project_title[:60]} ({self.version_label})"

    @property
    def version_label(self):
        return f"A{self.version_no}"

    def save(self, *args, **kwargs):
        if self._state.adding and self.version_no is None:
            last = (
                GrantSubmission.objects.filter(grant_family_id=self.grant_family_id)
                .order_by("-version_no")
                .first()
            )
            self.version_no = 0 if last is None else last.version_no + 1
        super().save(*args, **kwargs)


class GrantSubmissionPerson(models.Model):
    grant_submission = models.ForeignKey(
        GrantSubmission, on_delete=models.CASCADE, related_name="people"
    )
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="grant_links")
    role = models.CharField(max_length=20, choices=GrantRole.choices)
    is_primary_cnap_contact = models.BooleanField(default=False)

    class Meta:
        db_table = "grant_submission_people"
        constraints = [
            models.UniqueConstraint(
                fields=["grant_submission", "person"], name="grant_submission_people_unique"
            ),
            models.UniqueConstraint(
                fields=["grant_submission"],
                condition=Q(is_primary_cnap_contact=True),
                name="grant_submission_people_one_primary",
            ),
            models.CheckConstraint(
                condition=Q(role__in=[r.value for r in GrantRole]),
                name="grant_submission_people_role_valid",
            ),
        ]


class GrantSubmissionProject(models.Model):
    grant_submission = models.ForeignKey(
        GrantSubmission, on_delete=models.CASCADE, related_name="project_links"
    )
    project = models.ForeignKey(Project, on_delete=models.PROTECT, related_name="grant_links")

    class Meta:
        db_table = "grant_submission_projects"
        constraints = [
            models.UniqueConstraint(
                fields=["grant_submission", "project"], name="grant_submission_projects_unique"
            )
        ]


class GrantSubmissionResource(models.Model):
    grant_submission = models.ForeignKey(
        GrantSubmission, on_delete=models.CASCADE, related_name="resource_links"
    )
    resource = models.ForeignKey(Resource, on_delete=models.PROTECT, related_name="grant_links")
    is_anticipated = models.BooleanField(
        default=False, help_text="Entered while Planned; confirmed later."
    )

    class Meta:
        db_table = "grant_submission_resources"
        constraints = [
            models.UniqueConstraint(
                fields=["grant_submission", "resource"], name="grant_submission_resources_unique"
            )
        ]


class GrantSubmissionFile(models.Model):
    grant_submission = models.ForeignKey(
        GrantSubmission, on_delete=models.CASCADE, related_name="files"
    )
    file = models.ForeignKey(File, on_delete=models.PROTECT, related_name="grant_links")

    class Meta:
        db_table = "grant_submission_files"
        constraints = [
            models.UniqueConstraint(
                fields=["grant_submission", "file"], name="grant_submission_files_unique"
            )
        ]


class GrantStatusHistory(models.Model):
    grant_submission = models.ForeignKey(
        GrantSubmission, on_delete=models.CASCADE, related_name="status_history"
    )
    from_status = models.CharField(
        max_length=12, choices=GrantStatus.choices, null=True, blank=True
    )
    to_status = models.CharField(max_length=12, choices=GrantStatus.choices)
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    note = models.TextField(blank=True)

    class Meta:
        db_table = "grant_status_history"
        ordering = ["grant_submission", "changed_at"]
        verbose_name_plural = "grant status history"


# ---------------------------------------------------------------------------
# Self-entry (decisions.md 2026-10-26)
# ---------------------------------------------------------------------------


class OutcomeDelegate(models.Model):
    """A faculty member lets someone (usually a student) enter publications and grants on their behalf."""

    owner = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="outcome_delegates")
    delegate = models.ForeignKey(
        Person, on_delete=models.PROTECT, related_name="outcome_delegations"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "outcome_delegates"
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "delegate"],
                condition=Q(ended_at__isnull=True),
                name="outcome_delegates_one_open",
            ),
            models.CheckConstraint(
                condition=~Q(owner=models.F("delegate")), name="outcome_delegates_not_self"
            ),
        ]


class OutcomeCheckin(models.Model):
    """One person's publications-and-grants check-in for one reporting period (the task on My tasks)."""

    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="outcome_checkins")
    reporting_period = models.ForeignKey(
        "reporting.ReportingPeriod", on_delete=models.PROTECT, related_name="outcome_checkins"
    )
    plans_publications = models.BooleanField(null=True, blank=True)
    plans_grants = models.BooleanField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "outcome_checkins"
        constraints = [
            models.UniqueConstraint(
                fields=["person", "reporting_period"], name="outcome_checkins_unique"
            )
        ]
