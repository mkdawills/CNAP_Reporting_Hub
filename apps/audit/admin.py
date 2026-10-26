from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("at", "actor", "action", "entity_type", "entity_id", "entity_repr", "reason")
    list_filter = ("action", "entity_type")
    search_fields = ("entity_repr", "reason", "actor__username")
    date_hierarchy = "at"
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
