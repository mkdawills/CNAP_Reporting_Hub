"""Administrator home: where each period stands and what needs attention."""

from django.db.models import Count, Q
from django.shortcuts import render

from apps.common.enums import COMPLETE_STATUSES, AssignmentStatus, PeriodStatus
from apps.reporting.models import ReportingPeriod
from apps.reporting.services import periods as ps

from .. import quality
from ..decorators import admin_view
from .periods import lifecycle


@admin_view
def home(request):
    current = (
        ReportingPeriod.objects.filter(status=PeriodStatus.OPEN).order_by("-display_order").first()
    )
    draft = (
        ReportingPeriod.objects.filter(status=PeriodStatus.DRAFT).order_by("display_order").first()
    )
    pending = (
        ReportingPeriod.objects.filter(status=PeriodStatus.CLOSED)
        .order_by("-display_order")
        .first()
    )
    stats = None
    if current:
        agg = current.assignments.aggregate(
            total=Count("id", filter=~Q(status=AssignmentStatus.EXEMPT)),
            done=Count("id", filter=Q(status__in=COMPLETE_STATUSES)),
            people=Count("person", distinct=True),
            started=Count("id", filter=Q(status=AssignmentStatus.IN_PROGRESS)),
        )
        agg["pct"] = round(100 * agg["done"] / agg["total"]) if agg["total"] else 0
        stats = agg
    checks = quality.run()
    return render(
        request,
        "manage/home.html",
        {
            "current": current,
            "steps": lifecycle(current) if current else None,
            "stats": stats,
            "draft": draft,
            "pending": pending,
            "pending_stage": ps.stage(pending) if pending else None,
            "issues": sum(len(c["rows"]) for c in checks),
            "checks": [c for c in checks if c["rows"]][:4],
        },
    )
