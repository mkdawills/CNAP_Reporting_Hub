"""Administrator home: where each period stands and what needs attention."""

from django.contrib import messages
from django.urls import reverse
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.audit.models import AuditLog, record_event
from apps.common.enums import COMPLETE_STATUSES, AssignmentStatus, PeriodStatus
from apps.reporting.models import HelpfulDocument, ReportingPeriod
from apps.reporting.services import periods as ps

from .. import quality
from ..decorators import admin_view, manage_action
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
            "docs": HelpfulDocument.objects.filter(is_active=True).select_related("file"),
            "funding": _funding(),
        },
    )


def _funding():
    from apps.outcomes.models import FundingStatement

    return FundingStatement.current()


@manage_action
def funding_save(request):
    """Save the Stevens Amendment figures shown in every "How to acknowledge CNAP" box (MW 2026-11-02)."""
    from decimal import Decimal, InvalidOperation

    from apps.outcomes.models import FundingStatement

    def money(name):
        raw = (request.POST.get(name) or "").replace("$", "").replace(",", "").strip()
        if not raw:
            return None
        try:
            v = Decimal(raw)
        except InvalidOperation:
            raise ValueError(name)
        if v < 0:
            raise ValueError(name)
        return v.quantize(Decimal("1"))

    try:
        fed, non = money("federal_total"), money("nonfederal_total")
    except ValueError:
        messages.error(request, "Enter the dollar amounts as numbers, for example 11,250,000.")
        return redirect(reverse("manage:home") + "#funding")
    f = FundingStatement.objects.order_by("pk").first() or FundingStatement()
    old = {"federal_total": str(f.federal_total), "nonfederal_total": str(f.nonfederal_total)}
    f.federal_total = fed
    f.nonfederal_total = non or 0
    f.segment_label = (request.POST.get("segment_label") or "").strip()[:80]
    f.updated_by = request.user
    f.save()
    record_event(request.user, AuditLog.Action.UPDATE, f, old=old,
                 new={"federal_total": str(f.federal_total), "nonfederal_total": str(f.nonfederal_total)})
    messages.success(request, "Saved. Every “How to acknowledge CNAP” box now uses these figures.")
    return redirect(reverse("manage:home") + "#funding")


DOC_TYPES = (".pdf", ".docx", ".doc", ".xlsx", ".pptx")


@manage_action
def doc_add(request):
    """Add a helpful document (a file, or a link) to everyone's My tasks page."""
    import hashlib
    from pathlib import Path

    from apps.reporting.models import File

    title = request.POST.get("title", "").strip()[:200]
    note = request.POST.get("note", "").strip()[:300]
    url = request.POST.get("url", "").strip()
    up = request.FILES.get("file")
    if not title or bool(url) == bool(up):
        messages.error(request, "Give it a title, and either a file or a link (not both).")
        return redirect("manage:home")
    f = None
    if up:
        if Path(up.name).suffix.lower() not in DOC_TYPES or up.size > 20 * 1024 * 1024:
            messages.error(request, "Upload a PDF, Word, Excel or PowerPoint file under 20 MB.")
            return redirect("manage:home")
        digest = hashlib.sha256(up.read()).hexdigest()
        up.seek(0)
        f = File(
            original_filename=Path(up.name).name[:255],
            content_type=getattr(up, "content_type", "") or "application/octet-stream",
            byte_size=up.size,
            sha256=digest,
            uploaded_by=request.user,
        )
        f.storage_key.save(Path(up.name).name, up, save=False)
        f.save()
    elif not url.startswith(("https://", "http://")):
        messages.error(request, "A link starts with https://")
        return redirect("manage:home")
    n = HelpfulDocument.objects.count()
    d = HelpfulDocument.objects.create(
        title=title, note=note, file=f, url=url if not f else "", sort_order=n
    )
    record_event(request.user, AuditLog.Action.CREATE, d, new={"title": title})
    messages.success(request, f"“{title}” is on everyone’s My tasks page.")
    return redirect("manage:home")


@manage_action
def doc_remove(request, pk):
    d = get_object_or_404(HelpfulDocument, pk=pk)
    d.is_active = False
    d.save(update_fields=["is_active", "updated_at"])
    record_event(request.user, AuditLog.Action.UPDATE, d, new={"removed": True})
    messages.success(request, f"Removed “{d.title}”.")
    return redirect("manage:home")
