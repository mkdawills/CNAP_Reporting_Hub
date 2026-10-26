from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.audit.models import AuditLog, record_event

from .models import CONFIDENTIAL_MENTORING_PERM, ApplicationRole, User, UserRole


class UserRoleInline(admin.TabularInline):
    model = UserRole
    fk_name = "user"
    extra = 0
    autocomplete_fields = ("scope_core",)
    readonly_fields = ("granted_by", "granted_at")


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = (
        "username",
        "first_name",
        "last_name",
        "email",
        "person",
        "is_enabled",
        "is_staff",
        "last_login",
    )
    list_filter = ("is_enabled", "is_staff", "is_superuser")
    search_fields = ("username", "first_name", "last_name", "email")
    autocomplete_fields = ("person",)
    inlines = [UserRoleInline]
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Person", {"fields": ("person", "first_name", "last_name", "email")}),
        (
            "Access",
            {"fields": ("is_enabled", "is_active", "is_staff", "is_superuser", "user_permissions")},
        ),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "password1",
                    "password2",
                    "person",
                    "first_name",
                    "last_name",
                    "email",
                ),
            },
        ),
    )

    def save_related(self, request, form, formsets, change):
        """Audit direct grants and revocations of the confidential-mentoring permission."""
        user = form.instance
        before = user.has_perm(CONFIDENTIAL_MENTORING_PERM) if change else False
        super().save_related(request, form, formsets, change)
        if hasattr(user, "_perm_cache"):
            del user._perm_cache
        after = User.objects.get(pk=user.pk).has_perm(CONFIDENTIAL_MENTORING_PERM)
        if before != after:
            record_event(
                request.user,
                AuditLog.Action.GRANT_PERMISSION if after else AuditLog.Action.REVOKE_PERMISSION,
                user,
                new={"permission": CONFIDENTIAL_MENTORING_PERM, "granted": after},
            )


@admin.register(ApplicationRole)
class ApplicationRoleAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "permission_count")
    filter_horizontal = ("permissions",)
    readonly_fields = ("code",)

    @admin.display(description="Permissions")
    def permission_count(self, obj):
        return obj.permissions.count()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "scope_core", "granted_by", "granted_at")
    list_filter = ("role",)
    autocomplete_fields = ("user", "scope_core")
    readonly_fields = ("granted_by", "granted_at")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.granted_by = request.user
        super().save_model(request, obj, form, change)
