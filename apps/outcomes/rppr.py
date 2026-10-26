"""
RPPR-ready lists and tables from the FY27 COBRE reporting guidance (decisions.md 2026-10-26).

Budget period = grant year: June 1 to May 31 (Year 9 = June 1, 2025 - May 31, 2026).

C.1 Publications: published, peer reviewed (no preprints), published in the budget period, not reported in an
earlier RPPR, and not a paper with foreign co-authors lacking NIGMS prior approval for the foreign component
(those "must neither be included in C.1 nor cite the grant").

Table 1A/1B Funding Accomplishments: applications submitted and awards funded in the budget period by Center
participants, by funding source (NIH / Federal non-NIH / Non-federal) and by role (RPLs, PPLs, SPLs, Core staff
incl. the PD/PI, Others). An application submitted and funded in the same period is reported once, as an award.
Awards are counted once across RPPRs; applications again only when reapplied (A1 is its own record). The parent
COBRE award and its supplements are never counted. For MPI/Co-PI/collaborator/subaward, the CNAP investigator's
portion is used instead of the total.
"""

import datetime as dt
import re

from django.db import transaction
from django.db.models import Q

from apps.audit.models import AuditLog, record_event
from apps.common.enums import (
    FundingSourceType,
    GrantRole,
    GrantStatus,
    PublicationStatus,
    PublicationType,
)
from apps.people.models import PersonRelationship

from .models import GrantSubmission, Publication

PARENT_AWARD = "GM113109"
SOURCES = [FundingSourceType.NIH, FundingSourceType.FEDERAL_OTHER, FundingSourceType.NON_FEDERAL]
ROLES = ["RPLs", "PPLs", "SPLs", "Core Staff", "Others"]
FEDERAL_WORDS = r"\b(NSF|DOD|DoD|DOE|NASA|USDA|NIFA|HRSA|CDC|AHRQ|FDA|VA|DARPA|NOAA|NEH|NEA|IES|EPA|Department of|National Science Foundation|federal)\b"


def period(gy):
    return dt.date(2016 + gy, 6, 1), dt.date(2017 + gy, 5, 31)


def current_year(today=None):
    today = today or dt.date.today()
    return today.year - 2016 if today.month >= 6 else today.year - 2017


def source_of(g):
    """(source, guessed). Uses the person's answer; otherwise reads the agency name."""
    if g.funding_source_type:
        return g.funding_source_type, False
    a = g.funding_agency or ""
    if re.search(r"\bNIH\b|National Institutes? of Health|\bNI[A-Z]{1,4}\b", a):
        return FundingSourceType.NIH, True
    if re.search(FEDERAL_WORDS, a):
        return FundingSourceType.FEDERAL_OTHER, True
    return FundingSourceType.NON_FEDERAL, True


def is_parent_or_supplement(g):
    return g.exclude_from_table1 or PARENT_AWARD in re.sub(
        r"[^A-Z0-9]", "", (g.grant_number or "").upper()
    )


def lead_of(g):
    people = list(g.people.all())
    return next((x for x in people if x.is_primary_cnap_contact), None) or (
        people[0] if people else None
    )


def role_on(person, on):
    codes = set(
        PersonRelationship.objects.filter(person=person, effective_from__lte=on)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on))
        .values_list("relationship_type__code", flat=True)
    )
    if "project_leader" in codes:
        return "RPLs"
    if "pilot_awardee" in codes:
        return "PPLs"
    if "supplement_leader" in codes:
        return "SPLs"
    if codes & {"pd_pi", "associate_director", "core_director", "core_staff"}:
        return "Core Staff"
    return "Others"


def amount(g):
    lead = lead_of(g)
    shared = lead and lead.role in (
        GrantRole.MPI,
        GrantRole.CO_I,
        GrantRole.OTHER,
        GrantRole.CONSULTANT,
        GrantRole.KEY_PERSONNEL,
    )
    if (shared or g.prime_or_subaward == "subaward") and g.cnap_portion is not None:
        return float(g.cnap_portion), "CNAP investigator's portion"
    return float(g.award_total or 0), (
        "total; the CNAP investigator's portion is missing"
        if shared or g.prime_or_subaward == "subaward"
        else "total"
    )


def c1(gy):
    start, end = period(gy)
    included, excluded = [], []
    qs = Publication.objects.filter(
        archived_at__isnull=True, status=PublicationStatus.PUBLISHED
    ).prefetch_related("people__person")
    for p in qs.order_by("publication_date", "title"):
        d = p.publication_date
        if not d or not (start <= d <= end):
            if not d:
                excluded.append((p, "No publication date yet"))
            continue
        if p.publication_type == PublicationType.PREPRINT:
            excluded.append((p, "Preprint (C.1 is peer-reviewed publications only)"))
        elif p.has_foreign_authors and p.foreign_component_approved is not True:
            excluded.append(
                (p, "Foreign co-authors without NIGMS prior approval for the foreign component")
            )
        elif p.rppr_year and p.rppr_year != gy:
            excluded.append((p, f"Already reported in the Year {p.rppr_year} RPPR"))
        else:
            included.append(p)
    return included, excluded


def table1(gy):
    start, end = period(gy)
    a = {k: {"sub": 0, "won": 0, "cost": 0.0} for k in SOURCES}
    b = {k: {"sub": 0, "won": 0, "cost": 0.0} for k in ROLES}
    rows, skipped = [], []
    qs = (
        GrantSubmission.objects.filter(archived_at__isnull=True)
        .exclude(status=GrantStatus.PLANNED)
        .prefetch_related("people__person")
    )
    for g in qs.order_by("submission_date"):
        if is_parent_or_supplement(g):
            skipped.append((g, "Parent COBRE award or a supplement to it"))
            continue
        won = (
            g.status == GrantStatus.AWARDED
            and g.award_notice_date
            and start <= g.award_notice_date <= end
        )
        sub = g.submission_date and start <= g.submission_date <= end
        if won and g.rppr_awarded_year and g.rppr_awarded_year != gy:
            skipped.append((g, f"Award already reported in the Year {g.rppr_awarded_year} RPPR"))
            won = False
        if sub and not won and g.rppr_submitted_year and g.rppr_submitted_year != gy:
            skipped.append(
                (g, f"Application already reported in the Year {g.rppr_submitted_year} RPPR")
            )
            sub = False
        if not (won or sub):
            continue
        src, guessed = source_of(g)
        lead = lead_of(g)
        role = role_on(lead.person, g.submission_date or g.award_notice_date) if lead else "Others"
        kind = "won" if won else "sub"  # submitted and funded in the same period: once, as an award
        cost, basis = amount(g) if won else (0.0, "")
        for t, key in ((a, src), (b, role)):
            t[key][kind] += 1
            t[key]["cost"] += cost
        rows.append(
            {
                "g": g,
                "kind": "Award funded" if won else "Application submitted",
                "source": FundingSourceType(src).label,
                "guessed": guessed,
                "role": role,
                "lead": lead.person if lead else None,
                "cost": cost,
                "basis": basis,
            }
        )
    tot = {
        "sub": sum(v["sub"] for v in a.values()),
        "won": sum(v["won"] for v in a.values()),
        "cost": sum(v["cost"] for v in a.values()),
    }
    return {
        "a": a,
        "b": b,
        "total": tot,
        "rows": rows,
        "skipped": skipped,
        "sources": SOURCES,
        "roles": ROLES,
    }


@transaction.atomic
def mark_reported(user, gy):
    pubs, _ = c1(gy)
    t = table1(gy)
    n = 0
    for p in pubs:
        if p.rppr_year != gy:
            p.rppr_year = gy
            p.save(update_fields=["rppr_year", "updated_at"])
            n += 1
    for r in t["rows"]:
        g = r["g"]
        if r["kind"] == "Award funded":
            g.rppr_awarded_year = gy
            if g.submission_date and period(gy)[0] <= g.submission_date <= period(gy)[1]:
                g.rppr_submitted_year = gy
        else:
            g.rppr_submitted_year = gy
        g.save(update_fields=["rppr_awarded_year", "rppr_submitted_year", "updated_at"])
        n += 1
    record_event(user, AuditLog.Action.UPDATE, f"rppr:Y{gy}", new={"marked_reported": n})
    return n
