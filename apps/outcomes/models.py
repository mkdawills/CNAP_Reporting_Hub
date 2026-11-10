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
    FundingAudience,
    FundingMilestone,
    FundingSourceKind,
    FundingSourceType,
    GrantRole,
    GrantStatus,
    PresentationType,
    PrimeOrSubaward,
    PublicationStatus,
    PublicationSubstatus,
    PublicationType,
)
from apps.common.models import ArchivableModel, TimestampedModel
from apps.people.models import Person, Project, Resource
from apps.reporting.models import File

# ---------------------------------------------------------------------------
# Publications
# ---------------------------------------------------------------------------


class Publication(ArchivableModel):
    """One manuscript = one record, followed through Planned -> Submitted -> Published / Declined."""

    title = models.CharField(max_length=500)
    publication_type = models.CharField(max_length=20, choices=PublicationType.choices)
    publication_type_other = models.CharField(
        "Please describe the type", max_length=200, blank=True,
        help_text="Shown when the type is Other (MW 2026-11-04).",
    )
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
    anticipated_day_known = models.BooleanField(default=False)  # day is optional (MW 2026-11-03)
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
    foreign_component_approved = models.BooleanField(
        null=True,
        blank=True,
        help_text="With foreign co-authors: has NIGMS given prior approval for the foreign component?",
    )
    has_non_idea_coauthors = models.BooleanField(
        null=True, blank=True, help_text="Co-authors from non-IDeA states?"
    )
    rppr_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Grant year of the RPPR it was reported in (C.1). Never reported twice.",
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

    class RridCited(models.TextChoices):
        YES = "yes", "Yes"
        NO = "no", "No"
        UNSURE = "unsure", "Not sure"

    rrid_cited = models.CharField(
        max_length=8,
        choices=RridCited.choices,
        blank=True,
        help_text="Did the paper cite this core's RRID in its methods? Blank = not asked (no RRID then, or not a core).",
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
    presentation_type_other = models.CharField(
        "Please describe the type", max_length=200, blank=True,
        help_text="Shown when the type is Other (MW 2026-11-04).",
    )
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    author_display_text = models.TextField(blank=True, help_text="Full author list as entered.")
    event = models.CharField(max_length=300, blank=True)
    location = models.CharField(max_length=300, blank=True)  # older records; new ones fill the parts below
    venue = models.CharField(max_length=300, blank=True, help_text="Host university or venue.")
    city = models.CharField(max_length=120, blank=True)
    state_region = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=120, blank=True)
    presented_on = models.DateField(null=True, blank=True)
    cnap_cited = models.BooleanField(
        null=True, blank=True, help_text="Did the presentation acknowledge CNAP?"
    )
    resources_other_text = models.CharField(max_length=300, blank=True)
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
    anticipated_day_known = models.BooleanField(default=False)  # day is optional (MW 2026-11-03)
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
    cayuse_ipf = models.CharField(  # K-State's Cayuse proposal number, for cross-checking (MW 2026-11-03)
        max_length=40, blank=True
    )
    funding_source_type = models.CharField(
        max_length=14,
        blank=True,
        choices=FundingSourceType.choices,
        help_text="RPPR Table 1A: NIH, Federal non-NIH, Non-federal.",
    )
    cnap_portion = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="If MPI, Co-PI, collaborator or subawardee: the CNAP investigator's portion of the award (RPPR Table 1).",
    )
    table1_exclusion_reason = models.TextField(
        blank=True,
        help_text="Why the evaluator left this out of RPPR Table 1 (MW 2026-11-04).",
    )
    exclude_from_table1 = models.BooleanField(
        "Leave out of Table 1",
        default=False,
        help_text=(
            "Never counted in RPPR Table 1: the parent COBRE award or a supplement to it, or core-staff "
            "funding not related to IDeA support."
        ),
    )
    rppr_submitted_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Grant year of the RPPR that counted this application as submitted.",
    )
    rppr_awarded_year = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Grant year of the RPPR that counted this award."
    )
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
    role_other = models.CharField(
        "Please describe your role", max_length=200, blank=True,
        help_text="Shown when the role is Other (MW 2026-11-04).",
    )
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


class OutcomeReminder(models.Model):
    """One reminder email about stale publications/grants, so nobody is reminded more often than configured."""

    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="outcome_reminders")
    sent_at = models.DateTimeField(auto_now_add=True)
    sent_to = models.TextField(
        help_text="Addresses the reminder went to (the person and anyone entering for them)."
    )
    records = models.JSONField(
        default=list,
        help_text="[{kind, id, title, status, last_reviewed}] at the time it was sent.",
    )

    class Meta:
        db_table = "outcome_reminders"
        ordering = ["-sent_at"]



class GrantNudge(models.Model):
    """One monthly check-in email about a planned grant proposal, and the answer it brought back (MW 2026-11-03)."""

    class Choice(models.TextChoices):
        IDEATION = "ideation", (
            "The proposal has not progressed past the ideation stage. I am hopeful to get things kick-started soon."
        )
        BLOCK = "block", "I am experiencing a little writer's block. Thanks for the nudge!"
        SPECIALIST = "specialist", (
            "I have taken the first step of notifying my Central Office or departmental grant "
            "specialist of my plans to submit."
        )
        TIMELINE = "timeline", "I have a timeline in place with clear internal due dates."
        PIVOT = "pivot", "I am pivoting away from this plan, or abandoning it."

    grant = models.ForeignKey(GrantSubmission, on_delete=models.CASCADE, related_name="nudges")
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="grant_nudges")
    sent_at = models.DateTimeField(auto_now_add=True)
    sent_to = models.TextField(
        help_text="Addresses the check-in went to (the person and anyone entering for them)."
    )
    choice = models.CharField(max_length=12, blank=True, choices=Choice.choices)
    comments = models.TextField(blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    answered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "grant_nudges"
        ordering = ["-sent_at"]

    def __str__(self):
        return f"Nudge to {self.person} about {self.grant.project_title[:40]}"



# ---------------------------------------------------------------------------
# Funding opportunities and the not-funded follow-up (MW 2026-11-10)
# docs/funding-follow-up-spec.md. Matches are MW's choices; nothing is emailed automatically.
# ---------------------------------------------------------------------------


class FundingQuestion(ArchivableModel):
    """MW's questions for weighing any funding opportunity. Reference data she can edit without a code change."""

    position = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=120)
    text = models.TextField(help_text="One sentence per line.")

    class Meta:
        db_table = "funding_questions"
        ordering = ["position", "pk"]

    def __str__(self):
        return self.title


class FundingOpportunity(ArchivableModel):
    """One funding opportunity in the catalog: public facts, with a source link and the day they were checked."""

    name = models.CharField(max_length=300)
    sponsor = models.CharField(max_length=300, blank=True)
    source_kind = models.CharField(max_length=14, choices=FundingSourceKind.choices)
    mechanism = models.CharField(max_length=120, blank=True)
    amount_text = models.CharField(max_length=300, blank=True)
    deadline = models.DateField(null=True, blank=True)
    deadline_text = models.CharField(
        max_length=200, blank=True, help_text="Shown when there is no single date, such as early March each year."
    )
    url = models.URLField(max_length=500, blank=True)
    summary = models.TextField(blank=True, help_text="One or two plain sentences. One sentence per line.")
    fuller_text = models.TextField(blank=True, help_text="The longer explanation for the letter page.")
    counts_toward_milestone = models.CharField(
        max_length=8, choices=FundingMilestone.choices, default=FundingMilestone.NO
    )
    esi_only = models.BooleanField(default=False)
    audience = models.CharField(max_length=10, choices=FundingAudience.choices, default=FundingAudience.MATCHED)
    checked_on = models.DateField(null=True, blank=True)
    source_url = models.URLField(max_length=500, blank=True)
    tracker_id = models.CharField(max_length=60, blank=True)
    suggested_by = models.ForeignKey(
        Person, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "funding_opportunities"
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(source_kind__in=[x.value for x in FundingSourceKind]),
                name="funding_opportunities_kind_valid",
            ),
            models.CheckConstraint(
                condition=Q(counts_toward_milestone__in=[x.value for x in FundingMilestone]),
                name="funding_opportunities_milestone_valid",
            ),
            models.CheckConstraint(
                condition=Q(audience__in=[x.value for x in FundingAudience]),
                name="funding_opportunities_audience_valid",
            ),
        ]

    def __str__(self):
        return self.name


class FundingMatch(models.Model):
    """An opportunity MW picked for one person, with her one-sentence reason. Ending hides it; nothing is deleted."""

    opportunity = models.ForeignKey(FundingOpportunity, on_delete=models.PROTECT, related_name="matches")
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="funding_matches")
    why = models.TextField(blank=True, help_text="Why the opportunity fits the person. One sentence per line.")
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    added_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "funding_matches"
        constraints = [
            models.UniqueConstraint(
                fields=["opportunity", "person"],
                condition=Q(ended_at__isnull=True),
                name="funding_matches_one_open",
            )
        ]


class FundingSuggestion(TimestampedModel):
    """An opportunity a member suggests. It waits in MW's review queue, like roster suggestions."""

    class Status(models.TextChoices):
        TO_REVIEW = "to_review", "To review"
        ADDED = "added", "Added"
        DECLINED = "declined", "Declined"

    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="funding_suggestions")
    name = models.CharField(max_length=300)
    sponsor = models.CharField(max_length=300, blank=True)
    url = models.URLField(max_length=500, blank=True)
    deadline_text = models.CharField(max_length=200, blank=True)
    why = models.TextField(blank=True)
    for_everyone = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.TO_REVIEW)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    handled_at = models.DateTimeField(null=True, blank=True)
    opportunity = models.ForeignKey(
        FundingOpportunity, null=True, blank=True, on_delete=models.SET_NULL, related_name="suggestions"
    )
    note_to_person = models.TextField(blank=True)

    class Meta:
        db_table = "funding_suggestions"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["to_review", "added", "declined"]),
                name="funding_suggestions_status_valid",
            )
        ]


class FundingNewsItem(ArchivableModel):
    """A funding news item MW posts: a summary in her own words with the source link."""

    headline = models.CharField(max_length=300)
    news_date = models.DateField(null=True, blank=True)
    date_text = models.CharField(max_length=100, blank=True, help_text="Shown when there is no single day.")
    summary = models.TextField(help_text="Two or three sentences in your own words. One sentence per line.")
    source_name = models.CharField(max_length=200, blank=True)
    source_url = models.URLField(max_length=500, blank=True)
    pinned = models.BooleanField(default=False)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "funding_news"
        ordering = ["-pinned", "-news_date", "-created_at"]


class FundingFollowUp(TimestampedModel):
    """One per proposal marked Not funded: the letter MW reviews, edits, and sends herself."""

    class Status(models.TextChoices):
        TO_REVIEW = "to_review", "To review"
        SENT = "sent", "Sent"
        DISMISSED = "dismissed", "Dismissed"

    grant = models.OneToOneField(GrantSubmission, on_delete=models.CASCADE, related_name="funding_followup")
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="funding_followups")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.TO_REVIEW)
    subject = models.CharField(max_length=300, blank=True)
    opening = models.TextField(blank=True)
    body_note = models.TextField(blank=True, help_text="MW's personal paragraph. One sentence per line.")
    closing = models.TextField(blank=True)
    signoff = models.TextField(blank=True)
    opportunities = models.ManyToManyField(FundingOpportunity, blank=True, related_name="followups")
    sent_at = models.DateTimeField(null=True, blank=True)
    sent_to = models.TextField(blank=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    dismissed_reason = models.TextField(blank=True)

    @property
    def name(self):
        """The letter's name, identical in the email subject, the letter page, and every list (MW 2026-11-10)."""
        return self.subject or f"Next steps after {self.grant.project_title}"

    class Meta:
        db_table = "funding_followups"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["to_review", "sent", "dismissed"]),
                name="funding_followups_status_valid",
            )
        ]
