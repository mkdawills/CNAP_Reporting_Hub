"""
Site-visit outcome tables, laid out like MW's Year 9 site-visit workbooks (Publications, Presentations, Awards;
decisions.md 2026-10-26). Counts only: no names leave this module except through the admin list it feeds.

- Columns are the cores the item credits: BN, CN, NI, Admin, and "No core". An item crediting two cores is
  counted under each ("duplicates counted", as in the workbooks); the totals row says how many items that is.
- Publications: core x type x status, with the workbooks' status words:
  Submitted (no review status yet), Under Review, Accepted, Awaiting Publication (in press), Published,
  Not Published (declined). Preprints are their own type, "In Pre-Print". Planned papers aren't counted.
- Presentations: core x type (Poster or Flyer, Conference Presentation, Invited Talk, Other).
- Grants: core x status (Awarded / Pending / Declined) with counts and dollars, and funder (NIH / NSF / Other)
  x status. Dollars are total costs: the award total for awards, the requested total otherwise.
- What belongs to a year (June 1 - May 31): anything with a submission, publication, decline, presentation,
  award or decision date in it, plus papers and proposals still under review at its end.
- "New since": items first entered after a date (the RPPR submission, say), like the workbooks' peach rows.
"""

import re

from apps.common.enums import GrantStatus, PublicationStatus, PublicationSubstatus, PublicationType

from .models import GrantSubmission, Presentation, Publication
from .rppr import period

CORES = [
    ("BN", "BN Core"),
    ("CN", "CN Core"),
    ("NI", "NI Core"),
    ("ADMIN", "Admin Core"),
    ("NONE", "No core"),
]
PUB_TYPES = [
    (PublicationType.JOURNAL_ARTICLE, "Journal Article"),
    (PublicationType.BOOK_CHAPTER, "Book Chapter"),
    (PublicationType.CONFERENCE_PAPER, "Conference Paper or Proceeding"),
    (PublicationType.THESIS, "Thesis or Dissertation"),
    (PublicationType.PREPRINT, "In Pre-Print"),
    (PublicationType.OTHER, "Other"),
]
PUB_STATUSES = [
    "Submitted",
    "Under Review",
    "Accepted",
    "Awaiting Publication",
    "Published",
    "Not Published",
]
TALK_TYPES = [
    ("poster_or_flyer", "Poster or Flyer"),
    ("conference", "Conference Presentation"),
    ("invited_talk", "Invited Talk"),
    ("other", "Other"),
]
GRANT_STATUSES = ["Awarded", "Pending", "Declined"]
FUNDERS = ["NIH", "NSF", "Other"]


def cores_of(obj):
    """Site-visit core columns an item credits (actual resources, not anticipated)."""
    out = set()
    for link in obj.resource_links.all():
        if getattr(link, "is_anticipated", False):  # presentations have no anticipated list
            continue
        r = link.resource
        if r.code == "admin_core":
            out.add("ADMIN")
        elif r.core_id and r.core.code in ("BN", "CN", "NI"):
            out.add(r.core.code)
    return sorted(out) or ["NONE"]


def pub_status(p):
    if p.status == PublicationStatus.PUBLISHED:
        return "Published"
    if p.status == PublicationStatus.DECLINED:
        return "Not Published"
    if p.status == PublicationStatus.SUBMITTED:
        return {
            PublicationSubstatus.UNDER_REVIEW: "Under Review",
            PublicationSubstatus.ACCEPTED: "Accepted",
            PublicationSubstatus.IN_PRESS: "Awaiting Publication",
        }.get(p.substatus, "Submitted")
    return None


def grant_status(g):
    return {
        GrantStatus.AWARDED: "Awarded",
        GrantStatus.SUBMITTED: "Pending",
        GrantStatus.NOT_FUNDED: "Declined",
    }.get(g.status)


def funder(g):
    a = g.funding_agency or ""
    if re.search(r"\bNIH\b|National Institutes? of Health|\bNI[A-Z]{1,4}\b", a):
        return "NIH"
    if re.search(r"\bNSF\b|National Science Foundation", a):
        return "NSF"
    return "Other"


def grant_dollars(g):
    v = g.award_total if g.status == GrantStatus.AWARDED else g.requested_total
    return float(v or 0)


def _in(d, start, end):
    return bool(d and start <= d <= end)


def _new(obj, since):
    return bool(since and obj.created_at.date() > since)


def publications(gy, since=None):
    start, end = period(gy)
    items = []
    qs = (
        Publication.objects.filter(archived_at__isnull=True)
        .exclude(status=PublicationStatus.PLANNED)
        .prefetch_related("resource_links__resource__core")
    )
    for p in qs:
        active = (
            _in(p.submission_date, start, end)
            or _in(p.publication_date, start, end)
            or _in(p.decline_date, start, end)
            or (
                p.status == PublicationStatus.SUBMITTED
                and p.submission_date
                and p.submission_date <= end
            )
        )
        st = pub_status(p)
        if active and st:
            items.append(
                {
                    "obj": p,
                    "cores": cores_of(p),
                    "type": p.publication_type,
                    "status": st,
                    "new": _new(p, since),
                }
            )
    grid = {c: {t: {s: 0 for s in PUB_STATUSES} for t, _ in PUB_TYPES} for c, _ in CORES}
    for it in items:
        for c in it["cores"]:
            grid[c][it["type"]][it["status"]] += 1
    tables = []
    for c, clabel in CORES:
        rows = []
        for t, tlabel in PUB_TYPES:
            vals = [grid[c][t][s] for s in PUB_STATUSES]
            if any(vals):
                rows.append({"type": tlabel, "vals": vals, "total": sum(vals)})
        tables.append(
            {
                "core": clabel,
                "rows": rows,
                "total": sum(r["total"] for r in rows),
                "col_totals": [sum(r["vals"][i] for r in rows) for i in range(len(PUB_STATUSES))],
            }
        )
    return _wrap(items, tables, PUB_STATUSES)


def presentations(gy, since=None):
    start, end = period(gy)
    items = []
    qs = Presentation.objects.filter(archived_at__isnull=True).prefetch_related(
        "resource_links__resource__core"
    )
    for t in qs:
        if _in(t.presented_on, start, end):
            items.append(
                {"obj": t, "cores": cores_of(t), "type": t.presentation_type, "new": _new(t, since)}
            )
    rows = []
    for c, clabel in CORES:
        vals = [
            sum(1 for it in items if c in it["cores"] and it["type"] == k) for k, _ in TALK_TYPES
        ]
        rows.append({"core": clabel, "vals": vals, "total": sum(vals)})
    col_totals = [sum(r["vals"][i] for r in rows) for i in range(len(TALK_TYPES))]
    out = _wrap(items, rows, [label for _, label in TALK_TYPES])
    out["col_totals"] = col_totals
    return out


def grants(gy, since=None):
    start, end = period(gy)
    items = []
    qs = (
        GrantSubmission.objects.filter(archived_at__isnull=True)
        .exclude(status=GrantStatus.PLANNED)
        .prefetch_related("resource_links__resource__core")
    )
    for g in qs:
        active = (
            _in(g.submission_date, start, end)
            or _in(g.award_notice_date, start, end)
            or _in(g.decision_date, start, end)
            or (
                g.status == GrantStatus.SUBMITTED and g.submission_date and g.submission_date <= end
            )
        )
        st = grant_status(g)
        if active and st:
            items.append(
                {
                    "obj": g,
                    "cores": cores_of(g),
                    "status": st,
                    "funder": funder(g),
                    "dollars": grant_dollars(g),
                    "new": _new(g, since),
                }
            )

    def cell(pred):
        sel = [it for it in items if pred(it)]
        return {"n": len(sel), "dollars": sum(it["dollars"] for it in sel)}

    by_core = []
    for c, clabel in CORES:
        cells = [
            cell(lambda it, c=c, s=s: c in it["cores"] and it["status"] == s)
            for s in GRANT_STATUSES
        ]
        by_core.append(
            {"label": clabel, "cells": cells, "dollars": sum(x["dollars"] for x in cells)}
        )
    by_funder = []
    for f in FUNDERS:
        cells = [
            cell(lambda it, f=f, s=s: it["funder"] == f and it["status"] == s)
            for s in GRANT_STATUSES
        ]
        by_funder.append(
            {
                "label": f,
                "cells": cells,
                "n": sum(x["n"] for x in cells),
                "dollars": sum(x["dollars"] for x in cells),
            }
        )

    def totals(rows):
        return [
            {
                "n": sum(r["cells"][i]["n"] for r in rows),
                "dollars": sum(r["cells"][i]["dollars"] for r in rows),
            }
            for i in range(len(GRANT_STATUSES))
        ]

    out = _wrap(items, by_core, GRANT_STATUSES)
    out.update(
        by_funder=by_funder,
        core_totals=totals(by_core),
        funder_totals=totals(by_funder),
        status_counts={s: sum(1 for it in items if it["status"] == s) for s in GRANT_STATUSES},
    )
    return out


def _wrap(items, rows, cols):
    return {
        "items": items,
        "rows": rows,
        "cols": cols,
        "n_items": len(items),
        "n_counted": sum(len(it["cores"]) for it in items),
        "multi_core": [it for it in items if len(it["cores"]) > 1],
        "new": [it for it in items if it["new"]],
    }
