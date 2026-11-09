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


def _clamp(rng, asof):
    """A grant year's (start, end), ending no later than the "As of" day (MW 2026-11-05)."""
    start, end = rng
    return (start, min(end, asof)) if asof else (start, end)


def products(gy=None, asof=None):
    """The Center's products in one budget year, for the respondent Center results page (MW 2026-10-28).

    Published papers, talks and posters given, and funded grants are public, so they are listed. Submitted
    proposals are counted only: pending and unfunded proposals stay private."""
    from apps.common.enums import GrantRole

    gy = gy or current_year()
    start, end = _clamp(period(gy), asof)
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


# ------------------------------------------------------------------ several grant years at once (MW 2026-11-06)
CORE_GROUPS = (
    ("bn_core", "BN Core", "#5b2a9a"),
    ("ni_core", "NI Core", "#8f6bc4"),
    ("cn_core", "CN Core", "#c4b1e2"),
    ("admin_core", "Administrative Core", "#2f7d6b"),
    ("other", "Other Center resources", "#9fc9bd"),
    ("none", "No resource named", "#d3d1da"),
)
CORE_CODES = {"bn_core", "ni_core", "cn_core", "admin_core"}


def products_for(years, asof=None):
    """products() for any set of grant years, merged: lists newest first, counts summed."""
    years = sorted(set(years))
    parts = [products(gy, asof) for gy in years]
    merged = {
        "years": years,
        "gy": years[-1] if len(years) == 1 else None,
        "start": min(p["start"] for p in parts),
        "end": max(p["end"] for p in parts),
        "papers": sorted((x for p in parts for x in p["papers"]), key=lambda x: x["date"] or start_of(years), reverse=True),
        "talks": sorted((x for p in parts for x in p["talks"]), key=lambda x: x["date"] or start_of(years), reverse=True),
        "awards": [x for p in reversed(parts) for x in p["awards"]],
        "submitted": sum(p["submitted"] for p in parts),
    }
    return merged


def start_of(years):
    return period(min(years))[0]


def by_core(years, asof=None):
    """How many of each kind of product drew on each core, for the chosen grant years (MW 2026-11-06).

    Counts only, no names. A product that drew on two cores counts once for each, so a bar's
    segments can add up to more than the number of products; the page says so. Only resources a
    product actually used count, never ones it only planned to use.
    """
    from django.db.models import Q

    years = sorted(set(years))
    live = {"archived_at__isnull": True}
    rng = lambda field: _ranges(field, years, asof)
    kinds = (
        ("papers", "Papers published", Publication.objects.filter(rng("publication_date"), status=PublicationStatus.PUBLISHED, **live), True),
        ("talks", "Talks and posters", Presentation.objects.filter(rng("presented_on"), **live), False),
        ("proposals", "Proposals submitted", GrantSubmission.objects.filter(rng("submission_date"), **live).exclude(status=GrantStatus.PLANNED), True),
        ("awards", "Proposals awarded", GrantSubmission.objects.filter(rng("award_notice_date"), status=GrantStatus.AWARDED, **live), True),
    )
    out = []
    for key, label, qs, has_anticipated in kinds:
        counts = {code: 0 for code, _, _ in CORE_GROUPS}
        items = list(qs.prefetch_related("resource_links__resource"))
        for obj in items:
            links = [x for x in obj.resource_links.all() if not (has_anticipated and x.is_anticipated)]
            groups = {x.resource.code if x.resource.code in CORE_CODES else "other" for x in links}
            for g in groups or {"none"}:
                counts[g] += 1
        mentions = sum(counts.values())
        segs = [
            {"code": code, "label": name, "color": color, "n": counts[code], "w": round(100 * counts[code] / mentions, 2) if mentions else 0}
            for code, name, color in CORE_GROUPS
            if counts[code]
        ]
        out.append({"key": key, "label": label, "total": len(items), "mentions": mentions, "segments": segs})
    top = max((k["mentions"] for k in out), default=0)
    for k in out:  # bars share one scale, so lengths compare across kinds of product
        k["scale"] = round(100 * k["mentions"] / top, 2) if top else 0
    return out


def _ranges(field, years, asof=None):
    from django.db.models import Q

    q = Q()
    for gy in years:
        q |= Q(**{f"{field}__range": _clamp(period(gy), asof)})
    return q
