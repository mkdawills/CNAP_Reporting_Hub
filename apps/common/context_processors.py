"""Values every template needs: what the signed-in person may see and do."""

from apps.accounts import access


def cnap(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {"platform_name": "CNAP Reporting Hub"}
    person = getattr(user, "person", None)
    has_roles = bool(person and person.current_relationships().exists())
    return {
        "platform_name": "CNAP Reporting Hub",
        "can_view_admin": access.can_view_admin(user),
        "can_manage": access.can_manage(user),
        "is_view_only_admin": access.is_view_only_admin(user),
        "access_label": access.admin_label(user),
        "has_cnap_roles": has_roles,
    }
