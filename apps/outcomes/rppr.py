"""
RPPR-ready lists and tables from the FY27 COBRE reporting guidance (decisions.md 2026-10-26).

Budget period = grant year: June 1 to May 31 (Year 9 = June 1, 2025 - May 31, 2026).

C.1 Publications: published, peer reviewed (no preprints), published in the budget period (or in the previous one
and never reported: MW 2026-10-26, items dated after an RPPR went in belong in the next one), not reported in an
earlier RPPR, and not a paper with foreign co-authors lacking NIGMS prior approval for the foreign component
(those "must neither be included in C.1 nor cite the grant").

Table 1A/1B Funding Accomplishments: applications submitted and awards funded in the budget period by Center
participants, by funding source (NIH / Federal non-NIH / Non-federal) and by role (RPLs, PPLs, SPLs, Core staff
incl. the PD/PI, Others). An application submitted and funded in the same period is reported once, as an award.
Awards are counted once across RPPRs; applications again only when reapplied (A1 is its own record). The parent
COBRE award and its supplements are never counted. For MPI/Co-PI/collaborator/subaward, the CNAP investigator's
portion is used instead of the total.

Table 2 Core usage: built from the core directors' "Core Usage Report" submissions in the budget year's periods
(Fall and Spring), one row per user group, plus a cross-check of papers and proposals that credit each core.

D.1 Participants: everyone with a CNAP role during the budget year, in the guidance's six categories only, with
eRA Commons ID (required for everyone, trainees included) and, for trainees, career level. The guidance lists people
who worked at least 1.0 calendar month in the year: people enter their calendar months on their Profile (or the
evaluator does); anyone under 1.0 is set aside, and anyone with no months entered stays listed and is flagged.
Core users, general members and event participants are left out.
"""

from decimal import Decimal

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
from apps.people.models import Core, PersonRelationship

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
        if not d:
            excluded.append((p, "No publication date yet"))
            continue
        carried = period(gy - 1)[0] <= d < start and not p.rppr_year
        if not (start <= d <= end or carried):
            continue
        p.carried_from = gy - 1 if carried else None
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
        if g.exclude_from_table1:
            skipped.append(
                (g, "Left out by the evaluator: " + (g.table1_exclusion_reason or "no reason given"))
            )
            continue
        if is_parent_or_supplement(g):
            skipped.append((g, "Parent COBRE award or a supplement to it"))
            continue
        # Window: this budget period, plus anything from the previous one never reported (MW 2026-10-26:
        # items dated after that RPPR went in, about April 1 - May 31, go in the next RPPR).
        prev_s = period(gy - 1)[0]
        won_d, sub_d = g.award_notice_date, g.submission_date
        won = bool(
            g.status == GrantStatus.AWARDED
            and won_d
            and (start <= won_d <= end or (prev_s <= won_d < start and not g.rppr_awarded_year))
        )
        sub = bool(
            sub_d
            and (start <= sub_d <= end or (prev_s <= sub_d < start and not g.rppr_submitted_year))
        )
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
        key_d = won_d if won else sub_d
        carried = gy - 1 if key_d < start else None
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
                "carried_from": carried,
                # FY27 guidance, Table 1 notes: "When reporting funding for Core staff, report only if related to
                # IDeA support. For example, equipment grants."
                "check": (
                    "Core staff: count only if related to IDeA support (for example, an equipment grant). "
                    "If not, please use \u201cLeave out\u201d on this row and give the reason."
                    if role == "Core Staff"
                    else ""
                ),
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
            # reported once, as an award: its application is never counted separately afterwards
            if g.submission_date and not g.rppr_submitted_year:
                g.rppr_submitted_year = gy
        else:
            g.rppr_submitted_year = gy
        g.save(update_fields=["rppr_awarded_year", "rppr_submitted_year", "updated_at"])
        n += 1
    record_event(user, AuditLog.Action.UPDATE, f"rppr:Y{gy}", new={"marked_reported": n})
    return n


USAGE_FORM = "core_usage_report"
# The columns of the guidance's Table 2 "COBRE Core Users", in order, with its wording (used in the CSV).
# SHORT: the same columns, briefly, for the screen (the full wording shows on hover).
USAGE_SHORT = [
    "Type of user lab",
    "Project name",
    "Technology, instruments, services",
    "Individual users",
    "Student users",
    "Payment",
    "Data in a grant or paper?",
]
USAGE_COLS = [
    (
        "user_type",
        "Type of User Lab (RPL, PPL, former RPL, former PPL, Other Institutional, External)",
    ),
    ("project_name", "Project Name"),
    ("services", "Technology, instruments, or services used"),
    ("n_users", "Number of individual users per project"),
    ("n_students", "Number of student users (all levels)"),
    ("payment", "Payment type (in-kind, voucher, fee-for-service, etc.)"),
    ("core_data_used", "Were data included in a grant application or publication?"),
]


def research_cores():
    """Table 2 is completed "for each Core except the Admin Core"."""
    return [
        c
        for c in Core.objects.filter(is_active=True, archived_at__isnull=True)
        if "admin" not in f"{c.code} {c.name}".lower()
    ]


def usage_periods(gy):
    """Collections whose Core Usage Reports feed Table 2 for budget year gy, by default."""
    from apps.reporting.models import ReportingPeriod

    return list(ReportingPeriod.objects.filter(grant_year=gy).order_by("display_order"))


def table2(gy, periods=None):
    """Per research core: usage rows from submitted reports, totals, reporting gaps, and outcomes crediting it.

    periods: the collections to include (defaults to usage_periods(gy)).
    Total User Labs counts distinct labs (a lab may be listed more than once for different projects)."""
    from apps.reporting.models import Answer, Assignment

    start, end = period(gy)
    periods = usage_periods(gy) if periods is None else list(periods)
    asg = list(
        Assignment.objects.filter(
            form_definition__code=USAGE_FORM, reporting_period__in=periods, core__isnull=False
        )
        .exclude(status="exempt")
        .select_related("core", "person", "reporting_period")
    )
    submitted = {
        a.pk
        for a in asg
        if a.responses.filter(is_current=True, submitted_at__isnull=False).exists()
    }
    ans = (
        Answer.objects.filter(
            response__assignment__in=[a for a in asg if a.pk in submitted],
            response__is_current=True,
            response__submitted_at__isnull=False,
        )
        .select_related("question", "option", "response__assignment__reporting_period")
        .order_by("response__assignment__reporting_period__display_order", "repeat_index")
    )
    rows_by = {}
    for a in ans:
        r = rows_by.setdefault(
            (a.response.assignment_id, a.repeat_index), {"asg": a.response.assignment}
        )
        if a.question.code == "n_users" and "exclude student" in a.question.prompt.lower():
            r["_students_apart"] = True  # an older form: individual users didn't include students
        if a.option_id:
            r[a.question.code] = a.option.label
        elif a.value_number is not None:
            r[a.question.code] = int(a.value_number)
        else:
            r[a.question.code] = (a.value_text or "").strip()
    cores = []
    for n, core in enumerate(research_cores()):
        mine = [a for a in asg if a.core_id == core.pk]
        rows = [r for r in rows_by.values() if r["asg"].core_id == core.pk and r.get("user_type")]
        for r in rows:
            if r.pop("_students_apart", False):  # bring older rows to NIH's meaning: students are among the users
                r["n_users"] = (r.get("n_users") or 0) + (r.get("n_students") or 0)
            r["period"] = r["asg"].reporting_period.name
            r["by"] = str(r["asg"].person)
            r["cells"] = [r.get(k, "") for k, _ in USAGE_COLS]
        users = sum(r.get("n_users") or 0 for r in rows)
        students = sum(r.get("n_students") or 0 for r in rows)
        labs = set()
        for i, r in enumerate(rows):
            lab = " ".join((r.get("lab") or "").lower().split())
            labs.add(lab or f"row-{i}")  # a row with no lab named counts as its own lab
        gaps, doubles = [], []
        for p in periods:
            here = [a for a in mine if a.reporting_period_id == p.pk]
            done = [a for a in here if a.pk in submitted]
            if here and not done:
                gaps.append({"period": p, "people": [a.person for a in here]})
            if len(done) > 1:
                doubles.append({"period": p, "people": [a.person for a in done]})
        pay = {}
        for r in rows:
            k = r.get("payment") or "payment type not given"
            pay[k] = pay.get(k, 0) + (r.get("n_users") or 0)
        summary = ""
        if rows:
            tot = users
            summary = f"There {'was' if tot == 1 else 'were'} {tot} user{'' if tot == 1 else 's'} of the {core.name}."
            parts = [f"{v} {k.lower()} user{'' if v == 1 else 's'}" for k, v in pay.items() if v]
            if parts:
                summary += " " + "; ".join(parts) + "."
        pubs = (
            Publication.objects.filter(
                archived_at__isnull=True,
                status=PublicationStatus.PUBLISHED,
                publication_date__range=(start, end),
                resource_links__resource__core=core,
                resource_links__is_anticipated=False,
            )
            .distinct()
            .order_by("publication_date")
        )
        grants = (
            GrantSubmission.objects.filter(grant_links_q(core), archived_at__isnull=True)
            .filter(
                Q(submission_date__range=(start, end)) | Q(award_notice_date__range=(start, end))
            )
            .exclude(status=GrantStatus.PLANNED)
            .distinct()
            .order_by("submission_date")
        )
        # NIGMS "Total Award Costs (entire period of performance)": awards this year from proposals that credit
        # this core, at their full award total
        award_costs = sum(
            (g.award_total or 0)
            for g in grants
            if g.status == GrantStatus.AWARDED
            and g.award_notice_date
            and start <= g.award_notice_date <= end
        )
        cores.append(
            {
                "core": core,
                "letter": str(2 + n),  # NIGMS: the first core is Table 2, the second Table 3, and so on
                "rows": rows,
                "labs": len(labs),
                "users": users,
                "students": students,
                "total_users": users,  # students are counted among the individual users (NIGMS Table 2)
                "award_costs": award_costs,
                "said_yes": sum(1 for r in rows if r.get("core_data_used") == "Yes"),
                "summary": summary,
                "gaps": gaps,
                "doubles": doubles,
                "assigned": len(mine),
                "pubs": list(pubs),
                "grants": list(grants),
                "credit_n": len(pubs) + len(grants),
            }
        )
    return {
        "cores": cores,
        "cols": USAGE_COLS,
        "heads": [(short, full) for short, (_, full) in zip(USAGE_SHORT, USAGE_COLS, strict=True)],
        "periods": periods,
    }


def grant_links_q(core):
    return Q(resource_links__resource__core=core, resource_links__is_anticipated=False)


# Only the guidance's six categories (FY27 guidance, D.1: "Do not create categories other than those listed").
# Associate Director, core staff, project staff and collaborators fall under "Other" (research staff, consultants).
D1_CATEGORY = {
    "pd_pi": "PD/PI",
    "project_leader": "Project Leader (RP Leader)",
    "pilot_awardee": "Project Leader (PP Leader)",
    "supplement_leader": "Project Leader (SP Leader)",
    "core_director": "Core Director",
    "primary_mentor": "Mentor",
    "pilot_mentor": "Mentor",
    "project_student": "Trainee",
    "student_trainee": "Trainee",
    "associate_director": "Other",
    "core_staff": "Other",
    "project_staff": "Other",
    "collaborator": "Other",
    "osc": "Other",  # listed as Other (the guidance's six categories), labeled OSC
}
# Someone with several roles is listed once, in the first category of this order (MW 2026-10-26: Project Leader
# before Core Director; she expects a core director not to also be an RPL/PPL, see the data check).
D1_ORDER = list(dict.fromkeys(D1_CATEGORY.values()))


def d1(gy):
    """One row per person active in a personnel role at any time in the budget year."""
    from apps.people.services import is_senior_key

    start, end = period(gy)
    rels = (
        PersonRelationship.objects.filter(
            relationship_type__code__in=D1_CATEGORY, effective_from__lte=end
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=start))
        .select_related("person", "relationship_type", "project", "core")
    )
    from apps.people.models import PersonEffort

    efforts = {e.person_id: e for e in PersonEffort.objects.filter(grant_year=gy)}
    months = {pid: e.person_months for pid, e in efforts.items()}
    by = {}
    for r in rels:
        p = r.person
        if p.archived_at:
            continue
        e = by.setdefault(p.pk, {"person": p, "roles": set(), "where": set(), "codes": set()})
        e["roles"].add(D1_CATEGORY[r.relationship_type.code])
        e["codes"].add(r.relationship_type.code)
        ctx = getattr(r, "project", None) or getattr(r, "core", None)
        if ctx:
            e["where"].add(str(ctx))
    out = []
    for e in by.values():
        p = e["person"]
        roles = sorted(e["roles"], key=D1_ORDER.index)
        osc_only = e["codes"] == {"osc"}
        level = p.get_trainee_level_display() if p.trainee_level else ""
        out.append(
            {
                "person": p,
                "category": roles[0],
                "label": (
                    f"Trainee ({level})"
                    if roles[0] == "Trainee" and level
                    else "Other (Other Significant Contributor)"
                    if osc_only
                    else roles[0]
                ),
                "roles": roles,
                "where": sorted(e["where"]),
                "commons": p.era_commons_id,
                "level": p.get_trainee_level_display() if p.trainee_level else "",
                "needs_level": "Trainee" in roles and not p.trainee_level,
                # total person months (calendar, or academic + summer); an OSC with none entered is 0.0
                "months": months.get(p.pk)
                if months.get(p.pk) is not None or not osc_only
                else Decimal("0.0"),
                "osc": "osc" in e["codes"],
                "cal": getattr(efforts.get(p.pk), "calendar_months", None),
                "aca": getattr(efforts.get(p.pk), "academic_months", None),
                "sum": getattr(efforts.get(p.pk), "summer_months", None),
                "degrees": p.degrees,
                "senior_key": is_senior_key(p),
                "orcid": p.orcid,
                "foreign": ", ".join(x for x in (p.foreign_org, p.foreign_country) if x),
                "help": p.get_era_commons_help_kind_display() if p.era_commons_help_kind else "",
            }
        )
    out.sort(
        key=lambda x: (D1_ORDER.index(x["category"]), x["person"].last_name, x["person"].first_name)
    )
    # Senior/key people (named on the NoA, Common Form filers) are listed even under 1.0 person month
    # (MW's COBRE Administrator Handbook, ch. 6; the 2026 RPPR accepts them at 0.0).
    # OSCs are listed at any effort, including 0.0 (2026 RPPR; MW 2026-10-28).
    listed = [
        x for x in out if x["months"] is None or x["months"] >= 1 or x["senior_key"] or x["osc"]
    ]
    return {
        "rows": listed,
        "below": [x for x in out if x not in listed],
        "missing_orcid": [x for x in listed if x["senior_key"] and not x["orcid"]],
        "missing_months": [x for x in listed if x["months"] is None],
        "missing_commons": [x for x in listed if not x["commons"]],
        "missing_level": [x for x in listed if x["needs_level"]],
    }
