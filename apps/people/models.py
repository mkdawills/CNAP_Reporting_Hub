"""
Band C: people, CNAP relationships, projects, cores and resources.

The relationship rules of review section 2.1 live here. Django expresses the
CHECK and UNIQUE constraints; the composite foreign keys, the two exclusion
constraints and the project_people / core_people views are SQL in
migrations/0002_constraints.py, which is the schema of record for them.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from apps.common.enums import ContextKind, ProjectKind
from apps.common.models import ArchivableModel, TimestampedModel


class Person(ArchivableModel):
    """Every CNAP person has exactly one row here, whether or not they ever log in."""

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    institution = models.CharField(max_length=200, blank=True)
    department = models.CharField(max_length=200, blank=True)
    position_title = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    rich_profile_override = models.BooleanField(
        null=True,
        blank=True,
        help_text="Leave empty to derive the rich profile from relationships; set to force it on or off.",
    )
    era_commons_id = models.CharField(
        "eRA Commons ID",
        max_length=40,
        blank=True,
        help_text="NIH eRA Commons user name. Needed for RPPR D.1 for everyone in a personnel role.",
    )
    orcid = models.CharField(
        "ORCID iD",
        max_length=19,
        blank=True,
        help_text="16 digits, like 0000-0002-1825-0097. NIH requires senior/key personnel to link it in SciENcv.",
    )
    senior_key = models.BooleanField(
        "Named on the Notice of Award (senior/key)",
        null=True,
        blank=True,
        help_text="Leave as automatic: the PD/PI and RP Leaders count as senior/key. Set Yes for anyone else named on the NoA.",
    )
    degrees = models.CharField(
        "Degree(s)",
        max_length=100,
        blank=True,
        help_text="As on the RPPR D.1 table, e.g. BS, MA, PhD.",
    )
    foreign_org = models.CharField(
        "Foreign organization",
        max_length=200,
        blank=True,
        help_text="RPPR D.1: only if they are at a foreign organization.",
    )
    foreign_country = models.CharField("Country (foreign organization)", max_length=100, blank=True)
    trainee_level = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ("postdoc", "Postdoc"),
            ("graduate", "Graduate student"),
            ("undergraduate", "Undergraduate student"),
            ("high_school", "High school student"),
        ],
        help_text="Career level for trainees (RPPR D.1).",
    )
    era_commons_help_requested_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the person last asked the Center for help with eRA Commons.",
    )
    era_commons_help_kind = models.CharField(
        max_length=10,
        blank=True,
        choices=[
            ("setup", "Needs help setting one up"),
            ("unsure", "Unsure whether they need one"),
        ],
    )
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "people"
        ordering = ["last_name", "first_name"]
        verbose_name_plural = "people"

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def primary_email(self):
        row = self.emails.filter(is_primary=True).first() or self.emails.first()
        return row.email if row else ""

    def current_relationships(self, on=None):
        from django.utils import timezone

        on = on or timezone.localdate()
        return self.relationships.filter(effective_from__lte=on).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=on)
        )

    def has_rich_profile(self, on=None):
        if self.rich_profile_override is not None:
            return self.rich_profile_override
        return (
            self.current_relationships(on)
            .filter(relationship_type__grants_rich_profile=True)
            .exists()
        )


class PersonEmail(TimestampedModel):
    """Several addresses per person; unique across the system, case-insensitively."""

    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="emails")
    email = models.EmailField(max_length=254)
    is_primary = models.BooleanField(default=False)

    class Meta:
        db_table = "person_emails"
        constraints = [
            models.UniqueConstraint(Lower("email"), name="person_emails_email_unique_ci"),
            models.UniqueConstraint(
                fields=["person"], condition=Q(is_primary=True), name="person_emails_one_primary"
            ),
        ]

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        self.email = self.email.strip()
        super().save(*args, **kwargs)


class Core(ArchivableModel):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "cores"
        ordering = ["sort_order", "code"]

    def __str__(self):
        return self.name


class Project(ArchivableModel):
    title = models.CharField(max_length=300)
    kind = models.CharField(max_length=10, choices=ProjectKind.choices)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "projects"
        ordering = ["title"]
        constraints = [
            models.CheckConstraint(
                condition=Q(kind__in=[k.value for k in ProjectKind]), name="projects_kind_valid"
            ),
            # Lets other tables pin the kind with a composite foreign key.
            models.UniqueConstraint(fields=["id", "kind"], name="projects_id_kind_unique"),
            models.CheckConstraint(
                condition=Q(end_date__isnull=True)
                | Q(start_date__isnull=True)
                | Q(end_date__gte=models.F("start_date")),
                name="projects_dates_ordered",
            ),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_kind_display()})"


class Resource(ArchivableModel):
    """A CNAP resource an outcome can draw on: the cores, Connect Lab, Mentorship, Admin Core, Other."""

    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=200)
    core = models.ForeignKey(
        Core, null=True, blank=True, on_delete=models.PROTECT, related_name="resources"
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "resources"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class RelationshipType(TimestampedModel):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=120)
    context_kind = models.CharField(max_length=10, choices=ContextKind.choices)
    is_single_holder = models.BooleanField(
        default=False,
        help_text="One person per project or core at a time (Project Leader, Pilot Awardee).",
    )
    grants_rich_profile = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    description = models.TextField(blank=True)

    class Meta:
        db_table = "relationship_types"
        ordering = ["sort_order", "name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(context_kind__in=[k.value for k in ContextKind]),
                name="relationship_types_context_kind_valid",
            ),
            models.UniqueConstraint(
                fields=["id", "context_kind"], name="relationship_types_id_context_unique"
            ),
            models.UniqueConstraint(
                fields=["id", "is_single_holder"], name="relationship_types_id_single_holder_unique"
            ),
        ]

    def __str__(self):
        return self.name


class RelationshipTypeProjectKind(models.Model):
    """Which project kinds a project-scoped relationship type may attach to."""

    relationship_type = models.ForeignKey(
        RelationshipType, on_delete=models.CASCADE, related_name="allowed_project_kinds"
    )
    project_kind = models.CharField(max_length=10, choices=ProjectKind.choices)

    class Meta:
        db_table = "relationship_type_project_kinds"
        constraints = [
            models.UniqueConstraint(
                fields=["relationship_type", "project_kind"],
                name="relationship_type_project_kinds_unique",
            ),
            models.CheckConstraint(
                condition=Q(project_kind__in=[k.value for k in ProjectKind]),
                name="relationship_type_project_kinds_valid",
            ),
        ]

    def __str__(self):
        return f"{self.relationship_type.code}: {self.project_kind}"


class PersonRelationship(TimestampedModel):
    """
    One CNAP relationship held by one person for a span of time.

    `context_kind`, `is_single_holder` and `project_kind` are copied from the
    type and the project in save(); composite foreign keys in the SQL
    migration keep the copies truthful, and the CHECK below ties the context
    columns to the kind. If application code gets it wrong, PostgreSQL refuses.
    """

    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="relationships")
    relationship_type = models.ForeignKey(
        RelationshipType, on_delete=models.PROTECT, related_name="+"
    )
    context_kind = models.CharField(max_length=10, choices=ContextKind.choices, editable=False)
    is_single_holder = models.BooleanField(editable=False)
    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.PROTECT, related_name="relationships"
    )
    project_kind = models.CharField(
        max_length=10, choices=ProjectKind.choices, null=True, blank=True, editable=False
    )
    core = models.ForeignKey(
        Core, null=True, blank=True, on_delete=models.PROTECT, related_name="relationships"
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True, help_text="Empty means still current.")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "person_relationships"
        ordering = ["-effective_from"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(context_kind="none", project__isnull=True, core__isnull=True)
                    | Q(
                        context_kind="project",
                        project__isnull=False,
                        core__isnull=True,
                        project_kind__isnull=False,
                    )
                    | Q(context_kind="core", core__isnull=False, project__isnull=True)
                ),
                name="person_relationships_context_shape",
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="person_relationships_dates_ordered",
            ),
        ]

    def __str__(self):
        ctx = self.project or self.core
        return f"{self.person} - {self.relationship_type}" + (f" ({ctx})" if ctx else "")

    def fill_copied_columns(self):
        rt = self.relationship_type
        self.context_kind = rt.context_kind
        self.is_single_holder = rt.is_single_holder
        self.project_kind = self.project.kind if self.project_id else None

    def clean(self):
        """Plain-English version of the database rules, for forms and the admin."""
        if not self.relationship_type_id:
            return
        self.fill_copied_columns()
        rt = self.relationship_type
        if rt.context_kind == ContextKind.PROJECT and not self.project_id:
            raise ValidationError({"project": f"{rt.name} must be attached to a project."})
        if rt.context_kind == ContextKind.CORE and not self.core_id:
            raise ValidationError({"core": f"{rt.name} must be attached to a core."})
        if rt.context_kind == ContextKind.NONE and (self.project_id or self.core_id):
            raise ValidationError(f"{rt.name} is not attached to a project or a core.")
        if rt.context_kind == ContextKind.PROJECT and self.core_id:
            raise ValidationError({"core": f"{rt.name} attaches to a project, not a core."})
        if rt.context_kind == ContextKind.CORE and self.project_id:
            raise ValidationError({"project": f"{rt.name} attaches to a core, not a project."})
        if self.project_id:
            allowed = set(rt.allowed_project_kinds.values_list("project_kind", flat=True))
            if self.project.kind not in allowed:
                raise ValidationError(
                    {
                        "project": f"{self.project.title} is a {self.project.get_kind_display()}; "
                        f"a {rt.name} cannot be attached to it."
                    }
                )
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "The end date is before the start date."})

    def save(self, *args, **kwargs):
        self.fill_copied_columns()
        super().save(*args, **kwargs)

    @property
    def is_current(self):
        return self.effective_to is None


class PersonEffort(TimestampedModel):
    """Calendar months a person worked on CNAP in one budget year (June 1 - May 31), for RPPR D.1.

    D.1 lists people who worked at least 1.0 calendar month in the year. Calendar months = share of
    full-time effort x 12 (10% all year = 1.2 months)."""

    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="efforts")
    grant_year = models.PositiveSmallIntegerField()
    calendar_months = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    academic_months = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True, help_text="For 9-month appointments."
    )
    summer_months = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    entered_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        db_table = "person_efforts"
        constraints = [
            models.UniqueConstraint(fields=["person", "grant_year"], name="one_effort_per_year"),
            models.CheckConstraint(
                condition=(
                    models.Q(calendar_months__isnull=True)
                    | models.Q(calendar_months__gte=0, calendar_months__lte=12)
                )
                & (
                    models.Q(academic_months__isnull=True)
                    | models.Q(academic_months__gte=0, academic_months__lte=9)
                )
                & (
                    models.Q(summer_months__isnull=True)
                    | models.Q(summer_months__gte=0, summer_months__lte=3)
                ),
                name="effort_months_0_12",
            ),
        ]

    @property
    def person_months(self):
        """Total person months (calendar, or academic + summer), used for D.1's 1.0-month threshold."""
        vals = [
            v
            for v in (self.calendar_months, self.academic_months, self.summer_months)
            if v is not None
        ]
        return sum(vals) if vals else None

    def __str__(self):
        return f"{self.person} Y{self.grant_year}: {self.person_months} person months"
