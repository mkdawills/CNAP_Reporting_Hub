"""Audit log viewer."""

from django.core.paginator import Paginator
from django.shortcuts import render

from apps.audit.models import AuditLog

from ..decorators import admin_view


@admin_view
def audit(request):
    qs = AuditLog.objects.select_related("actor")
    action = request.GET.get("action", "")
    if action:
        qs = qs.filter(action=action)
    page = Paginator(qs, 50).get_page(request.GET.get("page"))
    return render(
        request,
        "manage/audit.html",
        {"page": page, "action": action, "actions": AuditLog.Action.choices},
    )
