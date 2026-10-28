"""This budget year's Center output for the My tasks strip (MW 2026-10-28). Counts only; no names."""

from apps.common.enums import GrantStatus, PublicationStatus

from .models import GrantSubmission, Presentation, Publication
from .rppr import current_year, period


def this_year(gy=None):
    gy = gy or current_year()
    start, end = period(gy)
    live = {"archived_at__isnull": True}
    return {
        "gy": gy,
        "start": start,
        "papers": Publication.objects.filter(
            status=PublicationStatus.PUBLISHED, publication_date__range=(start, end), **live
        ).count(),
        "talks": Presentation.objects.filter(presented_on__range=(start, end), **live).count(),
        "proposals": GrantSubmission.objects.filter(submission_date__range=(start, end), **live)
        .exclude(status=GrantStatus.PLANNED)
        .count(),
        "awards": GrantSubmission.objects.filter(
            status=GrantStatus.AWARDED, award_notice_date__range=(start, end), **live
        ).count(),
    }
