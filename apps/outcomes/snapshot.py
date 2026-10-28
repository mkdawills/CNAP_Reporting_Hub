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


MEASURES = (
    ("papers", "Papers published"),
    ("talks", "Talks and posters"),
    ("proposals", "Proposals submitted"),
    ("awards", "Proposals awarded"),
)


def by_year(gy=None):
    """The same four counts for every budget year that has any, up to this one (MW 2026-10-28). Counts only.

    Years run from the earliest with an entry to the current year, with empty years kept so the trend is honest.
    Returns None when only the current year has data (nothing to compare yet)."""
    gy = gy or current_year()
    live = {"archived_at__isnull": True}

    def year_of(d):
        return current_year(d)

    dates = {
        "papers": Publication.objects.filter(status=PublicationStatus.PUBLISHED, **live)
        .exclude(publication_date=None)
        .values_list("publication_date", flat=True),
        "talks": Presentation.objects.filter(**live)
        .exclude(presented_on=None)
        .values_list("presented_on", flat=True),
        "proposals": GrantSubmission.objects.filter(**live)
        .exclude(status=GrantStatus.PLANNED)
        .exclude(submission_date=None)
        .values_list("submission_date", flat=True),
        "awards": GrantSubmission.objects.filter(status=GrantStatus.AWARDED, **live)
        .exclude(award_notice_date=None)
        .values_list("award_notice_date", flat=True),
    }
    counts = {k: {} for k in dates}
    for k, qs in dates.items():
        for d in qs:
            y = year_of(d)
            if 1 <= y <= gy:
                counts[k][y] = counts[k].get(y, 0) + 1
    first = min((y for c in counts.values() for y in c), default=gy)
    if first >= gy:
        return None
    years = list(range(first, gy + 1))
    rows = []
    for k, label in MEASURES:
        vals = [counts[k].get(y, 0) for y in years]
        top = max(vals) or 1
        rows.append(
            {
                "key": k,
                "label": label,
                "total": sum(vals),
                "bars": [
                    {"year": y, "n": n, "h": round(100 * n / top), "now": y == gy}
                    for y, n in zip(years, vals)
                ],
            }
        )
    return {"years": years, "first": first, "rows": rows}


def products(gy=None):
    """The Center's products in one budget year, for the respondent Center results page (MW 2026-10-28).

    Published papers, talks and posters given, and funded grants are public, so they are listed. Submitted
    proposals are counted only: pending and unfunded proposals stay private."""
    from apps.common.enums import GrantRole

    gy = gy or current_year()
    start, end = period(gy)
    live = {"archived_at__isnull": True}

    def names(links, key="person"):
        return ", ".join(str(getattr(x, key)) for x in links)

    papers = (
        Publication.objects.filter(status=PublicationStatus.PUBLISHED, publication_date__range=(start, end), **live)
        .prefetch_related("people__person")
        .order_by("-publication_date", "title")
    )
    talks = (
        Presentation.objects.filter(presented_on__range=(start, end), **live)
        .prefetch_related("people__person")
        .order_by("-presented_on", "title")
    )
    awards = (
        GrantSubmission.objects.filter(status=GrantStatus.AWARDED, award_notice_date__range=(start, end), **live)
        .prefetch_related("people__person")
        .order_by("-award_notice_date", "project_title")
    )
    submitted = (
        GrantSubmission.objects.filter(submission_date__range=(start, end), **live)
        .exclude(status=GrantStatus.PLANNED)
        .count()
    )
    out_papers = [
        {
            "authors": p.author_display_text
            or names(sorted(p.people.all(), key=lambda x: x.author_order)),
            "title": p.title,
            "journal": p.journal,
            "date": p.publication_date,
            "url": p.pubmed_url,
        }
        for p in papers
    ]
    out_talks = [
        {
            "title": t.title,
            "kind": t.get_presentation_type_display(),
            "event": t.event,
            "date": t.presented_on,
            "who": names([x for x in sorted(t.people.all(), key=lambda x: x.author_order) if x.is_presenter])
            or t.author_display_text
            or names(sorted(t.people.all(), key=lambda x: x.author_order)),
        }
        for t in talks
    ]
    out_awards = [
        {
            "title": g.project_title,
            "agency": " ".join(x for x in (g.funding_agency, g.mechanism) if x),
            "number": g.grant_number,
            "start": g.project_start_date,
            "end": g.project_end_date,
            "pis": names([x for x in g.people.all() if x.role in (GrantRole.PI, GrantRole.MPI)]),
        }
        for g in awards
    ]
    return {
        "gy": gy,
        "start": start,
        "end": end,
        "papers": out_papers,
        "talks": out_talks,
        "awards": out_awards,
        "submitted": submitted,
    }
