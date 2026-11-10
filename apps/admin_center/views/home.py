"""Administrator home: where each period stands and what needs attention."""

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts import access
from apps.audit.models import AuditLog, record_event
from apps.common.enums import COMPLETE_STATUSES, AssignmentStatus, PeriodStatus
from apps.reporting.models import HelpfulDocument, ReportingPeriod
from apps.reporting.services import periods as ps

from .. import quality
from ..decorators import admin_view, manage_action
from .periods import _timeline, lifecycle


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
        # people in three buckets: finished, partway, not started (MW 2026-11-03)
        per = {}
        for pid, st in current.assignments.exclude(status=AssignmentStatus.EXEMPT).values_list(
            "person_id", "status"
        ):
            per.setdefault(pid, []).append(st)
        agg["p_done"] = sum(1 for v in per.values() if all(s in COMPLETE_STATUSES for s in v))
        agg["p_not"] = sum(
            1 for v in per.values() if all(s == AssignmentStatus.NOT_STARTED for s in v)
        )
        agg["p_underway"] = len(per) - agg["p_done"] - agg["p_not"]
        stats = agg
    checks = quality.run()
    return render(
        request,
        "manage/home.html",
        {
            "current": current,
            "steps": lifecycle(current) if current else None,
            "timeline": _timeline(request, current) if current else None,
            "stats": stats,
            "draft": draft,
            "pending": pending,
            "pending_stage": ps.stage(pending) if pending else None,
            "issues": sum(len(c["rows"]) for c in checks),
            "checks": [c for c in checks if c["rows"]][:4],
            "docs": HelpfulDocument.objects.filter(is_active=True).select_related("file"),
            "site_photo": __import__(
                "apps.common.models", fromlist=["SitePhoto"]
            ).SitePhoto.current(),
            "funding_counts": __import__(
                "apps.outcomes.funding", fromlist=["counts"]
            ).counts(),  # MW 2026-11-10
        },
    )


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
            messages.error(request, "Upload a PDF, Word, Excel, or PowerPoint file under 20 MB.")
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


@admin_view
def feedback_list(request):
    """Every note sent with the feedback button (MW 2026-11-04)."""
    from apps.common.models import PageFeedback

    if request.method == "POST" and access.can_manage(request.user):
        fb = get_object_or_404(PageFeedback, pk=request.POST.get("pk"))
        fb.resolved_at = None if fb.resolved_at else timezone.now()
        fb.save(update_fields=["resolved_at"])
        return redirect("manage:feedback")
    rows = PageFeedback.objects.select_related("user", "user__person")[:300]
    return render(
        request,
        "manage/feedback.html",
        {
            "rows": rows,
            "open_n": PageFeedback.objects.filter(resolved_at__isnull=True).count(),
            "can_edit": access.can_manage(request.user),
        },
    )


@manage_action
def photo_set(request):
    """Upload, replace, or remove the sign-in page photo (MW 2026-11-04)."""
    from pathlib import Path

    from apps.common.models import SitePhoto

    if request.POST.get("action") == "remove":
        SitePhoto.objects.filter(is_active=True).update(is_active=False)
        messages.success(request, "The sign-in page no longer shows a photo.")
        return redirect("manage:home")
    up = request.FILES.get("image")
    alt = request.POST.get("alt_text", "").strip()
    if not up or not alt:
        messages.error(request, "Choose a photo and describe it in a few words for screen readers.")
        return redirect("manage:home")
    if (
        Path(up.name).suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp")
        or up.size > 8 * 1024 * 1024
    ):
        messages.error(request, "Upload a JPG, PNG, or WebP image under 8 MB.")
        return redirect("manage:home")
    SitePhoto.objects.filter(is_active=True).update(is_active=False)
    ph = SitePhoto.objects.create(
        image=up,
        alt_text=alt[:300],
        caption=request.POST.get("caption", "").strip()[:300],
        uploaded_by=request.user,
    )
    record_event(request.user, AuditLog.Action.CREATE, ph, new={"alt": alt})
    messages.success(request, "The new photo now shows on the sign-in page.")
    return redirect("manage:home")
