from django.contrib import admin

from .models import (
    Answer,
    AnswerFile,
    AnswerSelectedOption,
    Assignment,
    File,
    ReportingPeriod,
    Response,
    RosterImport,
    RosterImportRow,
)


@admin.register(ReportingPeriod)
class ReportingPeriodAdmin(admin.ModelAdmin):
    list_display = (
        "short_label",
        "name",
        "grant_year",
        "sequence",
        "status",
        "start_date",
        "end_date",
        "due_at",
    )
    list_filter = ("status", "period_type", "grant_year")
    readonly_fields = ("display_order", "closed_at", "finalized_at")
    ordering = ("-display_order",)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "person",
        "form_definition",
        "reporting_period",
        "project",
        "core",
        "status",
        "completion_pathway",
        "due_at",
        "source",
    )
    list_filter = ("status", "reporting_period", "form_definition", "source")
    search_fields = ("person__first_name", "person__last_name")
    autocomplete_fields = ("person", "project", "core")
    readonly_fields = (
        "form_definition",
        "context_kind",
        "assigned_at",
        "started_at",
        "submitted_at",
        "reopened_at",
    )

    def has_delete_permission(self, request, obj=None):
        return False


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    can_delete = False
    readonly_fields = (
        "question",
        "repeat_index",
        "value_text",
        "value_number",
        "value_date",
        "option",
        "person_value",
        "project_value",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = ("id", "assignment", "is_current", "submitted_at", "submitted_by", "provenance")
    list_filter = ("is_current", "provenance")
    readonly_fields = ("form_version",)
    inlines = [AnswerInline]

    def has_delete_permission(self, request, obj=None):
        return False


class RosterImportRowInline(admin.TabularInline):
    model = RosterImportRow
    extra = 0
    readonly_fields = (
        "row_number",
        "email",
        "first_name",
        "last_name",
        "match_kind",
        "matched_person",
    )


@admin.register(RosterImport)
class RosterImportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "original_filename",
        "uploaded_by",
        "created_at",
        "status",
        "committed_at",
    )
    inlines = [RosterImportRowInline]


@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    list_display = (
        "original_filename",
        "content_type",
        "byte_size",
        "uploaded_by",
        "created_at",
        "archived_at",
    )

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(AnswerSelectedOption)
admin.site.register(AnswerFile)
