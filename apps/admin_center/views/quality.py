from django.contrib import messages
from django.shortcuts import redirect, render

from apps.analytics.models import DataQualityDismissal
from apps.audit.models import AuditLog, record_event

from .. import quality
from ..decorators import admin_view, manage_action


@admin_view
def checks(request):
    return render(request, "manage/quality.html", {"checks": quality.run()})


@manage_action
def dismiss(request):
    code, rtype, rid = (
        request.POST.get("check"),
        request.POST.get("record_type"),
        request.POST.get("record_id"),
    )
    reason = request.POST.get("reason", "").strip()
    if not reason:
        messages.error(request, "Give a reason for dismissing this.")
        return redirect("manage:quality")
    d, _ = DataQualityDismissal.objects.get_or_create(
        check_code=code,
        record_type=rtype,
        record_id=int(rid),
        defaults={"dismissed_by": request.user, "reason": reason},
    )
    record_event(request.user, AuditLog.Action.UPDATE, d, new={"dismissed": code}, reason=reason)
    messages.success(request, "Dismissed.")
    return redirect("manage:quality")
