"""
Band B: the configurable, versioned form engine.

A form is data. A version is immutable once activated; editing means cloning.
Options always belong to an answer set (Question -> Answer Set -> Options).
Measures give questions a stable identity across versions so longitudinal
comparison follows meaning, not wording. Composite foreign keys that keep the
copied `scale_kind` truthful, and the trigger that freezes options once they
have been answered, are SQL in migrations/0002_constraints.py.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.common.enums import (
    OPTION_QUESTION_TYPES,
    ConfidentialityClass,
    ContextKind,
    FormCategory,
    QuestionType,
    RuleAction,
    RuleOperator,
    RuleScope,
    ScaleKind,
    VersionStatus,
)
from apps.common.models import ArchivableModel, TimestampedModel
from apps.people.models import Core, RelationshipType


class Measure(TimestampedModel):
    """
    The thing CNAP tracks over time, independent of how one version words it.
    Example: code 'bn_quality_booking', name 'Quality: booking of shared facilities'.
    """

    code = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=255)
    scale_kind = models.CharField(max_length=12, choices=ScaleKind.choices)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "measures"
        ordering = ["code"]
        constraints = [
            models.CheckConstraint(
                condition=Q(scale_kind__in=[k.value for k in ScaleKind]),
                name="measures_scale_kind_valid",
            ),
            models.UniqueConstraint(fields=["id", "scale_kind"], name="measures_id_scale_unique"),
        ]

    def __str__(self):
        return self.name


class AnswerSet(TimestampedModel):
    """A reusable (is_shared) or one-off list of options with a scale kind."""

    name = models.CharField(max_length=120)
    scale_kind = models.CharField(max_length=12, choices=ScaleKind.choices)
    is_shared = models.BooleanField(
        default=False, help_text="Shown in the picker for reuse across forms."
    )
    description = models.TextField(blank=True)

    class Meta:
        db_table = "answer_sets"
        ordering = ["-is_shared", "name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(scale_kind__in=[k.value for k in ScaleKind]),
                name="answer_sets_scale_kind_valid",
            ),
            models.UniqueConstraint(
                fields=["id", "scale_kind"], name="answer_sets_id_scale_unique"
            ),
        ]

    def __str__(self):
        return self.name


class QuestionOption(TimestampedModel):
    """
    One choice in an answer set. `value` is the numeric score for scale
    options (1-5) and NULL for N/A or non-numeric options. Frozen once any
    answer references it (trigger in the SQL migration).
    """

    answer_set = models.ForeignKey(AnswerSet, on_delete=models.CASCADE, related_name="options")
    label = models.CharField(max_length=255)
    code = models.CharField(
        max_length=40, help_text="Stable short code, e.g. 'strongly_agree', 'na'."
    )
    value = models.SmallIntegerField(
        null=True, blank=True, help_text="Numeric score; empty for N/A."
    )
    is_na_option = models.BooleanField(default=False)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "question_options"
        ordering = ["answer_set", "sort_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["answer_set", "code"], name="question_options_code_unique"
            ),
            models.CheckConstraint(
                condition=~Q(is_na_option=True, value__isnull=False),
                name="question_options_na_has_no_value",
            ),
        ]

    def __str__(self):
        return self.label


class CompletionPathway(TimestampedModel):
    """How an assignment was completed: a full response or a structured opt-out."""

    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=120)
    is_opt_out = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "completion_pathways"
        ordering = ["sort_order", "code"]

    def __str__(self):
        return self.name


class FormDefinition(ArchivableModel):
    code = models.CharField(max_length=60, unique=True)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=10, choices=FormCategory.choices)
    context_kind = models.CharField(
        max_length=10,
        choices=ContextKind.choices,
        help_text="What one assignment of this form is about: nothing, a project, or a core.",
    )
    about_core = models.ForeignKey(
        Core,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="evaluated_by_forms",
        help_text="For a Core survey: the core it evaluates (used to exclude that core's director).",
    )
    confidentiality_class = models.CharField(
        max_length=10, choices=ConfidentialityClass.choices, default=ConfidentialityClass.STANDARD
    )
    respondent_can_view_own = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    display = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "How the form appears on My tasks: task_group, short_name, about (paragraphs), "
            "time_label, opt_out {question, short}, prefill [[label, key]], holder_type. "
            "Loaded from fixtures/forms; not source wording."
        ),
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "form_definitions"
        ordering = ["sort_order", "name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(context_kind__in=[k.value for k in ContextKind]),
                name="form_definitions_context_kind_valid",
            ),
            models.UniqueConstraint(
                fields=["id", "context_kind"], name="form_definitions_id_context_unique"
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def is_confidential_mentoring(self):
        return self.confidentiality_class == ConfidentialityClass.MENTORING

    @property
    def active_version(self):
        return self.versions.filter(status=VersionStatus.ACTIVE).first()


class FormVersion(TimestampedModel):
    form_definition = models.ForeignKey(
        FormDefinition, on_delete=models.PROTECT, related_name="versions"
    )
    version_no = models.PositiveSmallIntegerField()
    status = models.CharField(
        max_length=10, choices=VersionStatus.choices, default=VersionStatus.DRAFT
    )
    cloned_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="clones"
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    retired_at = models.DateTimeField(null=True, blank=True)
    change_notes = models.TextField(
        blank=True, help_text="What changed from the previous version and why."
    )
    intro_text = models.TextField(blank=True)
    source_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="Fingerprint of the fixture this version was built from (load_forms).",
    )

    class Meta:
        db_table = "form_versions"
        ordering = ["form_definition", "-version_no"]
        constraints = [
            models.UniqueConstraint(
                fields=["form_definition", "version_no"], name="form_versions_number_unique"
            ),
            models.UniqueConstraint(
                fields=["id", "form_definition"], name="form_versions_id_definition_unique"
            ),
            models.UniqueConstraint(
                fields=["form_definition"],
                condition=Q(status="active"),
                name="form_versions_one_active_per_definition",
            ),
            models.CheckConstraint(
                condition=Q(status__in=[s.value for s in VersionStatus]),
                name="form_versions_status_valid",
            ),
        ]

    def __str__(self):
        return f"{self.form_definition.name} v{self.version_no} ({self.status})"

    @property
    def is_editable(self):
        return self.status == VersionStatus.DRAFT


class FormSection(TimestampedModel):
    form_version = models.ForeignKey(FormVersion, on_delete=models.CASCADE, related_name="sections")
    code = models.CharField(max_length=40, help_text="Stable across versions, e.g. 'admin_core'.")
    title = models.CharField(max_length=255)
    instructions = models.TextField(blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_repeatable = models.BooleanField(
        default=False, help_text="Respondent may add several entries (meetings)."
    )
    repeat_label = models.CharField(
        max_length=80, blank=True, help_text="Button text, e.g. 'Add another meeting'."
    )

    class Meta:
        db_table = "form_sections"
        ordering = ["form_version", "sort_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["form_version", "code"], name="form_sections_code_unique"
            )
        ]

    def __str__(self):
        return self.title


class Question(TimestampedModel):
    form_section = models.ForeignKey(
        FormSection, on_delete=models.CASCADE, related_name="questions"
    )
    form_version = models.ForeignKey(
        FormVersion, on_delete=models.CASCADE, related_name="questions", editable=False
    )
    code = models.CharField(max_length=60, help_text="Stable within the form, e.g. 'q_booking'.")
    prompt = models.TextField()
    help_text = models.TextField(blank=True)
    question_type = models.CharField(max_length=16, choices=QuestionType.choices)
    answer_set = models.ForeignKey(
        AnswerSet, null=True, blank=True, on_delete=models.PROTECT, related_name="questions"
    )
    scale_kind = models.CharField(
        max_length=12, choices=ScaleKind.choices, null=True, blank=True, editable=False
    )
    measure = models.ForeignKey(
        Measure, null=True, blank=True, on_delete=models.PROTECT, related_name="questions"
    )
    is_required = models.BooleanField(default=False)
    sort_order = models.PositiveSmallIntegerField(default=0)
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Type-specific settings (max length, currency, file types).",
    )

    class Meta:
        db_table = "questions"
        ordering = ["form_section", "sort_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["form_version", "code"], name="questions_code_unique_per_version"
            ),
            models.CheckConstraint(
                condition=Q(question_type__in=[t.value for t in QuestionType]),
                name="questions_type_valid",
            ),
            # Option-type questions have an answer set; all others do not.
            models.CheckConstraint(
                condition=(
                    Q(
                        question_type__in=[t.value for t in OPTION_QUESTION_TYPES],
                        answer_set__isnull=False,
                    )
                    | (
                        ~Q(question_type__in=[t.value for t in OPTION_QUESTION_TYPES])
                        & Q(answer_set__isnull=True)
                    )
                ),
                name="questions_answer_set_matches_type",
            ),
            # scale_kind is the copy of the answer set's scale kind, present iff an answer set is.
            models.CheckConstraint(
                condition=(
                    Q(answer_set__isnull=True, scale_kind__isnull=True)
                    | Q(answer_set__isnull=False, scale_kind__isnull=False)
                ),
                name="questions_scale_kind_with_answer_set",
            ),
            # A measure needs a scale; only questions with an answer set may carry one.
            models.CheckConstraint(
                condition=Q(measure__isnull=True) | Q(scale_kind__isnull=False),
                name="questions_measure_needs_scale",
            ),
        ]

    def __str__(self):
        return f"{self.code}: {self.prompt[:60]}"

    @property
    def is_option_type(self):
        return self.question_type in OPTION_QUESTION_TYPES

    def fill_copied_columns(self):
        self.form_version_id = self.form_section.form_version_id
        self.scale_kind = self.answer_set.scale_kind if self.answer_set_id else None

    def clean(self):
        if self.is_option_type and not self.answer_set_id:
            raise ValidationError({"answer_set": "This question type needs an answer set."})
        if not self.is_option_type and self.answer_set_id:
            raise ValidationError({"answer_set": "Only choice-type questions use an answer set."})
        if (
            self.measure_id
            and self.answer_set_id
            and self.measure.scale_kind != self.answer_set.scale_kind
        ):
            raise ValidationError(
                {
                    "measure": f"Measure scale ({self.measure.scale_kind}) differs from the answer set ({self.answer_set.scale_kind})."
                }
            )

    def save(self, *args, **kwargs):
        self.fill_copied_columns()
        super().save(*args, **kwargs)


class ConditionalRule(TimestampedModel):
    """
    Show / hide / require a target when a source question's answer matches, or
    classify the submission with a completion pathway (set_pathway).
    """

    form_version = models.ForeignKey(FormVersion, on_delete=models.CASCADE, related_name="rules")
    source_question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="rules_from"
    )
    operator = models.CharField(max_length=16, choices=RuleOperator.choices)
    value_option = models.ForeignKey(
        QuestionOption, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    action = models.CharField(max_length=12, choices=RuleAction.choices)
    target_section = models.ForeignKey(
        FormSection, null=True, blank=True, on_delete=models.CASCADE, related_name="rules_to"
    )
    target_question = models.ForeignKey(
        Question, null=True, blank=True, on_delete=models.CASCADE, related_name="rules_to"
    )
    pathway = models.ForeignKey(
        CompletionPathway, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "conditional_rules"
        ordering = ["form_version", "sort_order"]
        constraints = [
            models.CheckConstraint(
                condition=Q(operator__in=[o.value for o in RuleOperator]),
                name="conditional_rules_operator_valid",
            ),
            models.CheckConstraint(
                condition=Q(action__in=[a.value for a in RuleAction]),
                name="conditional_rules_action_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        action="set_pathway",
                        pathway__isnull=False,
                        target_section__isnull=True,
                        target_question__isnull=True,
                    )
                    | (
                        ~Q(action="set_pathway")
                        & Q(pathway__isnull=True)
                        & (
                            Q(target_section__isnull=False, target_question__isnull=True)
                            | Q(target_section__isnull=True, target_question__isnull=False)
                        )
                    )
                ),
                name="conditional_rules_target_shape",
            ),
            models.CheckConstraint(
                condition=(
                    Q(operator__in=["equals", "not_equals"], value_option__isnull=False)
                    | Q(operator__in=["is_answered", "is_not_answered"], value_option__isnull=True)
                ),
                name="conditional_rules_value_matches_operator",
            ),
        ]

    def __str__(self):
        return f"{self.source_question.code} {self.operator} -> {self.action}"


class FormAssignmentRule(TimestampedModel):
    """
    Who receives a form: everyone on the active roster, or holders of one
    relationship type (one assignment per person, or one per project/core).
    Copied context kinds plus the CHECK make a mis-scoped rule impossible to save.
    """

    form_definition = models.ForeignKey(
        FormDefinition, on_delete=models.CASCADE, related_name="assignment_rules"
    )
    form_context_kind = models.CharField(max_length=10, choices=ContextKind.choices, editable=False)
    scope = models.CharField(max_length=14, choices=RuleScope.choices)
    relationship_type = models.ForeignKey(
        RelationshipType,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="assignment_rules",
    )
    relationship_context_kind = models.CharField(
        max_length=10, choices=ContextKind.choices, null=True, blank=True, editable=False
    )
    per_context = models.BooleanField(
        default=False, help_text="One assignment per relationship row (per project or core)."
    )
    excluded_relationship_type = models.ForeignKey(
        RelationshipType,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Skip people holding this type (for the form's about_core when set), e.g. core_director.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "form_assignment_rules"
        constraints = [
            models.UniqueConstraint(
                fields=["form_definition", "relationship_type"],
                nulls_distinct=False,
                name="form_assignment_rules_unique",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        scope="universal",
                        relationship_type__isnull=True,
                        per_context=False,
                        form_context_kind="none",
                    )
                    | (
                        Q(scope="relationship", relationship_type__isnull=False)
                        & (
                            Q(
                                per_context=True,
                                form_context_kind=models.F("relationship_context_kind"),
                            )
                            | Q(per_context=False, form_context_kind="none")
                        )
                    )
                ),
                name="form_assignment_rules_shape",
            ),
        ]

    def __str__(self):
        who = (
            "everyone on the roster"
            if self.scope == RuleScope.UNIVERSAL
            else str(self.relationship_type)
        )
        return f"{self.form_definition.code}: {who}" + (" per context" if self.per_context else "")

    def fill_copied_columns(self):
        self.form_context_kind = self.form_definition.context_kind
        self.relationship_context_kind = (
            self.relationship_type.context_kind if self.relationship_type_id else None
        )

    def clean(self):
        self.fill_copied_columns()
        if self.scope == RuleScope.UNIVERSAL:
            if self.relationship_type_id or self.per_context:
                raise ValidationError(
                    "A universal rule has no relationship type and is never per context."
                )
            if self.form_context_kind != ContextKind.NONE:
                raise ValidationError(
                    "A universal rule can only be attached to a form with no project or core context."
                )
        else:
            if not self.relationship_type_id:
                raise ValidationError(
                    {"relationship_type": "Choose the relationship that receives this form."}
                )
            if self.per_context and self.form_context_kind != self.relationship_context_kind:
                raise ValidationError(
                    "A per-context rule needs a form whose context matches the relationship's "
                    f"({self.relationship_context_kind}); this form is '{self.form_context_kind}'."
                )
            if not self.per_context and self.form_context_kind != ContextKind.NONE:
                raise ValidationError(
                    "A per-person rule can only be attached to a form with no project or core context."
                )

    def save(self, *args, **kwargs):
        self.fill_copied_columns()
        super().save(*args, **kwargs)
