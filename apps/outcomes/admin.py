"""Outcome tables are visible but read-only in Build 1; their screens come in Build 2."""

from django.contrib import admin

from .models import (
    GrantFamily,
    GrantStatusHistory,
    GrantSubmission,
    GrantSubmissionPerson,
    GrantSubmissionProject,
    GrantSubmissionResource,
    Presentation,
    PresentationPerson,
    PresentationProject,
    PresentationResource,
    Publication,
    PublicationPerson,
    PublicationProject,
    PublicationResource,
    PublicationStatusHistory,
)


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Publication)
class PublicationAdmin(ReadOnlyAdmin):
    list_display = (
        "title",
        "publication_type",
        "status",
        "substatus",
        "journal",
        "publication_date",
    )
    list_filter = ("status", "publication_type")
    search_fields = ("title", "journal")


@admin.register(Presentation)
class PresentationAdmin(ReadOnlyAdmin):
    list_display = ("title", "presentation_type", "event", "presented_on")
    list_filter = ("presentation_type",)
    search_fields = ("title", "event")


@admin.register(GrantFamily)
class GrantFamilyAdmin(ReadOnlyAdmin):
    list_display = ("title", "created_by", "created_at")


@admin.register(GrantSubmission)
class GrantSubmissionAdmin(ReadOnlyAdmin):
    list_display = (
        "project_title",
        "version_label",
        "status",
        "funding_agency",
        "mechanism",
        "submission_date",
        "award_notice_date",
    )
    list_filter = ("status",)
    search_fields = ("project_title", "funding_agency", "grant_number")


for model in (
    PublicationPerson,
    PublicationProject,
    PublicationResource,
    PublicationStatusHistory,
    PresentationPerson,
    PresentationProject,
    PresentationResource,
    GrantSubmissionPerson,
    GrantSubmissionProject,
    GrantSubmissionResource,
    GrantStatusHistory,
):
    admin.site.register(model, ReadOnlyAdmin)
