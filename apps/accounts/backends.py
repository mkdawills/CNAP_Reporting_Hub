"""
Authentication backend that adds role permissions to Django's own.

Permissions come from three places, in this order of precedence (union):
1. permissions granted directly to the user (the confidential-mentoring
   permission is only ever granted this way);
2. permissions of the application roles the user holds (UserRole);
3. superuser, which Django treats as holding everything.

CNAP relationships never grant permissions. Scoped roles (a Reviewer limited to
one core) are enforced in the data-access layer, not here: has_perm answers
"may this user use this feature at all"; `visible_records()` answers "which
rows".
"""

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import Permission


class RoleBackend(ModelBackend):
    def _get_role_permissions(self, user_obj):
        return Permission.objects.filter(application_roles__user_roles__user=user_obj)

    def _get_permissions(self, user_obj, obj, from_name):
        if from_name == "role":
            perms = self._get_role_permissions(user_obj)
            return {
                f"{ct}.{name}"
                for ct, name in perms.values_list("content_type__app_label", "codename")
            }
        return super()._get_permissions(user_obj, obj, from_name)

    def get_all_permissions(self, user_obj, obj=None):
        if not user_obj.is_active or user_obj.is_anonymous or obj is not None:
            return set()
        if not hasattr(user_obj, "_perm_cache"):
            user_obj._perm_cache = {
                *self.get_user_permissions(user_obj),
                *self.get_group_permissions(user_obj),
                *self._get_permissions(user_obj, None, "role"),
            }
        return user_obj._perm_cache

    def user_can_authenticate(self, user):
        return super().user_can_authenticate(user) and getattr(user, "is_enabled", True)
