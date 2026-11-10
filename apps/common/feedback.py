"""The feedback button on every page (MW 2026-11-04)."""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import PageFeedback


@login_required
@require_POST
def send(request):
    topic = request.POST.get("topic", "")
    comment = request.POST.get("comment", "").strip()
    if topic not in dict(PageFeedback.TOPICS) or not comment:
        return JsonResponse(
            {"ok": False, "error": "Choose a topic and write a few words."}, status=400
        )
    try:
        rating = int(request.POST.get("rating") or 0) or None
    except ValueError:
        rating = None
    if rating and not 1 <= rating <= 5:
        rating = None
    PageFeedback.objects.create(
        user=request.user,
        path=request.POST.get("path", "")[:500],
        page_title=request.POST.get("page_title", "")[:300],
        topic=topic,
        rating=rating,
        comment=comment[:5000],
    )
    return JsonResponse({"ok": True})


def site_photo(request):
    """Serves the sign-in photo. Public, like the sign-in page itself."""
    from django.http import FileResponse, Http404

    from .models import SitePhoto

    ph = SitePhoto.current()
    if not ph:
        raise Http404
    return FileResponse(ph.image.open("rb"))
