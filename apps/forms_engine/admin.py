from django.contrib import admin

from .models import (
    AnswerSet,
    CompletionPathway,
    ConditionalRule,
    FormAssignmentRule,
    FormDefinition,
    FormSection,
    FormVersion,
    Measure,
    Question,
    QuestionOption,
)


@admin.register(Measure)
class MeasureAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "scale_kind", "is_active")
    list_filter = ("scale_kind", "is_active")
    search_fields = ("code", "name")


class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 0


@admin.register(AnswerSet)
class AnswerSetAdmin(admin.ModelAdmin):
    list_display = ("name", "scale_kind", "is_shared", "option_count")
    list_filter = ("scale_kind", "is_shared")
    search_fields = ("name",)
    inlines = [QuestionOptionInline]

    @admin.display(description="Options")
    def option_count(self, obj):
        return obj.options.count()


@admin.register(CompletionPathway)
class CompletionPathwayAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_opt_out", "sort_order")


class FormAssignmentRuleInline(admin.TabularInline):
    model = FormAssignmentRule
    extra = 0
    fields = (
        "scope",
        "relationship_type",
        "per_context",
        "excluded_relationship_type",
        "is_active",
    )


class FormVersionInline(admin.TabularInline):
    model = FormVersion
    extra = 0
    fields = ("version_no", "status", "activated_at", "retired_at", "change_notes")
    readonly_fields = ("activated_at", "retired_at")
    show_change_link = True


@admin.register(FormDefinition)
class FormDefinitionAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "category",
        "context_kind",
        "confidentiality_class",
        "about_core",
        "active_version_no",
    )
    list_filter = ("category", "context_kind", "confidentiality_class")
    search_fields = ("code", "name")
    inlines = [FormAssignmentRuleInline, FormVersionInline]

    @admin.display(description="Active version")
    def active_version_no(self, obj):
        v = obj.active_version
        return v.version_no if v else "-"

    def has_delete_permission(self, request, obj=None):
        return False


class FormSectionInline(admin.TabularInline):
    model = FormSection
    extra = 0
    show_change_link = True


class ConditionalRuleInline(admin.TabularInline):
    model = ConditionalRule
    extra = 0
    fk_name = "form_version"


@admin.register(FormVersion)
class FormVersionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "form_definition", "version_no", "status", "activated_at")
    list_filter = ("status", "form_definition")
    inlines = [FormSectionInline, ConditionalRuleInline]
    readonly_fields = ("activated_at", "retired_at", "cloned_from")

    def has_delete_permission(self, request, obj=None):
        return False


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    fields = (
        "sort_order",
        "code",
        "prompt",
        "question_type",
        "answer_set",
        "measure",
        "is_required",
    )
    show_change_link = True


@admin.register(FormSection)
class FormSectionAdmin(admin.ModelAdmin):
    list_display = ("title", "form_version", "code", "sort_order", "is_repeatable")
    list_filter = ("form_version__form_definition",)
    inlines = [QuestionInline]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "prompt_short",
        "question_type",
        "answer_set",
        "measure",
        "form_version",
        "is_required",
    )
    list_filter = ("question_type", "form_version__form_definition")
    search_fields = ("code", "prompt")
    readonly_fields = ("form_version", "scale_kind")

    @admin.display(description="Prompt")
    def prompt_short(self, obj):
        return obj.prompt[:80]


@admin.register(FormAssignmentRule)
class FormAssignmentRuleAdmin(admin.ModelAdmin):
    list_display = (
        "form_definition",
        "scope",
        "relationship_type",
        "per_context",
        "excluded_relationship_type",
        "is_active",
    )
    list_filter = ("scope", "per_context")
    readonly_fields = ("form_context_kind", "relationship_context_kind")
