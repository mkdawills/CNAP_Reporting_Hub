from django.contrib import admin

from .models import (
    Core,
    Person,
    PersonEmail,
    PersonRelationship,
    Project,
    RelationshipType,
    RelationshipTypeProjectKind,
    Resource,
)


class ArchiveMixin:
    """Archive instead of delete for institutional records (review section 36)."""

    actions = ["archive_selected", "unarchive_selected"]

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Archive selected (hidden, never deleted)")
    def archive_selected(self, request, queryset):
        for obj in queryset.filter(archived_at__isnull=True):
            obj.archive()

    @admin.action(description="Unarchive selected")
    def unarchive_selected(self, request, queryset):
        for obj in queryset.filter(archived_at__isnull=False):
            obj.unarchive()


class PersonEmailInline(admin.TabularInline):
    model = PersonEmail
    extra = 1


class PersonRelationshipInline(admin.TabularInline):
    model = PersonRelationship
    fk_name = "person"
    extra = 0
    fields = ("relationship_type", "project", "core", "effective_from", "effective_to", "notes")
    autocomplete_fields = ("project", "core")


@admin.register(Person)
class PersonAdmin(ArchiveMixin, admin.ModelAdmin):
    list_display = (
        "last_name",
        "first_name",
        "primary_email",
        "institution",
        "department",
        "is_active",
        "archived_at",
    )
    list_filter = ("is_active", "institution")
    search_fields = ("first_name", "last_name", "emails__email", "institution", "department")
    inlines = [PersonEmailInline, PersonRelationshipInline]
    readonly_fields = ("created_at", "updated_at", "archived_at")


@admin.register(Core)
class CoreAdmin(ArchiveMixin, admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "sort_order")
    search_fields = ("code", "name")


@admin.register(Project)
class ProjectAdmin(ArchiveMixin, admin.ModelAdmin):
    list_display = ("title", "kind", "start_date", "end_date", "is_active", "archived_at")
    list_filter = ("kind", "is_active")
    search_fields = ("title",)


@admin.register(Resource)
class ResourceAdmin(ArchiveMixin, admin.ModelAdmin):
    list_display = ("code", "name", "core", "is_active", "sort_order")
    search_fields = ("code", "name")


class RelationshipTypeProjectKindInline(admin.TabularInline):
    model = RelationshipTypeProjectKind
    extra = 0


@admin.register(RelationshipType)
class RelationshipTypeAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "context_kind",
        "is_single_holder",
        "grants_rich_profile",
        "is_active",
        "sort_order",
    )
    list_filter = ("context_kind", "is_single_holder", "grants_rich_profile")
    search_fields = ("code", "name")
    inlines = [RelationshipTypeProjectKindInline]


@admin.register(PersonRelationship)
class PersonRelationshipAdmin(admin.ModelAdmin):
    list_display = (
        "person",
        "relationship_type",
        "project",
        "core",
        "effective_from",
        "effective_to",
    )
    list_filter = ("relationship_type", "context_kind")
    search_fields = ("person__first_name", "person__last_name", "project__title", "core__name")
    autocomplete_fields = ("person", "project", "core")
    readonly_fields = (
        "context_kind",
        "is_single_holder",
        "project_kind",
        "created_at",
        "updated_at",
    )

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
