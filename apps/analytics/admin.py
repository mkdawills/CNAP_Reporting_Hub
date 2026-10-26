from django.contrib import admin

from .models import (
    AnswerThemeTag,
    DataQualityDismissal,
    MetricDefinition,
    ReportingSnapshot,
    SnapshotMember,
    SnapshotNote,
    SnapshotResult,
    Theme,
)


@admin.register(Theme)
class ThemeAdmin(admin.ModelAdmin):
    list_display = ("name", "form_definition", "is_active")
    list_filter = ("is_active", "form_definition")
    search_fields = ("name",)


@admin.register(MetricDefinition)
class MetricDefinitionAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "domain", "version", "requires_permission", "updated_at")
    list_filter = ("domain",)
    search_fields = ("code", "name", "definition_text")
    readonly_fields = [f.name for f in MetricDefinition._meta.fields]

    def has_add_permission(self, request):
        return False


class SnapshotNoteInline(admin.TabularInline):
    model = SnapshotNote
    extra = 0


@admin.register(ReportingSnapshot)
class ReportingSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "reporting_period",
        "version_no",
        "kind",
        "status",
        "provenance",
        "generated_at",
        "finalized_at",
    )
    list_filter = ("status", "kind", "provenance")
    readonly_fields = ("generated_at", "finalized_at", "finalized_by", "supersedes")
    inlines = [SnapshotNoteInline]

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(SnapshotResult)
admin.site.register(SnapshotMember)
admin.site.register(AnswerThemeTag)
admin.site.register(DataQualityDismissal)
