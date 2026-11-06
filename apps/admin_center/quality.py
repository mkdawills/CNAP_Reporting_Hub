"""
Data-quality checks (Milestone 7). Each check returns rows the evaluator can fix
or dismiss with a reason; dismissals are remembered (data_quality_dismissals).
"""

from django.db.models import Q
from django.utils import timezone

from apps.analytics.models import DataQualityDismissal
from apps.common.enums import AssignmentStatus, PeriodStatus
from apps.people.models import Person, PersonRelationship, Project
from apps.reporting.models import Assignment

CHECKS = [
    (
        "no_email",
        "People with no email address",
        "These people can’t receive forms, reminders, or sign-in links.",
    ),
    (
        "project_no_leader",
        "Projects with no leader",
        "No progress report or Mentee Survey goes out for them.",
    ),
    ("project_no_mentor", "Projects with no mentor", "No mentor report goes out for these projects."),
    (
        "ended_but_open",
        "Forms still open for people who have left the role",
        "The CNAP role that earned the person this form has ended, but the form is still open and "
        "counts against completion. Consider exempting them.",
    ),
    ("duplicate_names", "Possible duplicate people", "Same first and last name on two records."),
    (
        "director_and_leader",
        "Core directors who are also a project leader",
        "A core director normally isn’t also a Research Project Leader or Pilot Project Leader. Check this person’s roles, or dismiss the check if the roles are right.",
    ),
    (
        "rrid_not_cited",
        "Published papers that used a core but didn’t cite its RRID",
        "Without the RRID, the core’s use can only be found if the paper cites the grant. Ask the author to add "
        "it next time, or dismiss if there’s a reason.",
    ),
    (
        "foreign_cites_grant",
        "Papers with foreign co-authors that cite the grant without approval",
        "NIH may treat this as an unapproved foreign component. Credit the core with its RRID instead, or seek "
        "NIGMS approval (handbook chapters 12 and 14).",
    ),
    (
        "overdue",
        "Past due and not started",
        "Forms in an open reporting session that are past due and untouched.",
    ),
]


def _current(on):
    return Q(effective_from__lte=on) & (Q(effective_to__isnull=True) | Q(effective_to__gte=on))


LEADER_CODES = ("project_leader", "pilot_awardee")


def director_and_leader(on, person=None):
    """People who are currently a core director and an RPL or PPL at the same time."""
    cur = PersonRelationship.objects.filter(_current(on))
    if person is not None:
        cur = cur.filter(person=person)
    directors = set(
        cur.filter(relationship_type__code="core_director").values_list("person_id", flat=True)
    )
    leaders = set(
        cur.filter(relationship_type__code__in=LEADER_CODES).values_list("person_id", flat=True)
    )
    return Person.objects.active().filter(pk__in=directors & leaders)


def run():
    today = timezone.localdate()
    dismissed = set(
        DataQualityDismissal.objects.values_list("check_code", "record_type", "record_id")
    )
    out = {code: [] for code, *_ in CHECKS}
    active_people = (
        Person.objects.active()
        .filter(
            is_active=True, relationships__in=PersonRelationship.objects.filter(_current(today))
        )
        .distinct()
    )
    for p in active_people.prefetch_related("emails"):
        if not p.emails.exists():
            out["no_email"].append(("person", p.pk, str(p), f"/manage/people/{p.pk}/"))
    for pr in Project.objects.active().filter(is_active=True):
        rels = pr.relationships.filter(_current(today))
        lead = "pilot_awardee" if pr.kind == "pilot" else "project_leader"
        ment = "pilot_mentor" if pr.kind == "pilot" else "primary_mentor"
        if not rels.filter(relationship_type__code=lead).exists():
            out["project_no_leader"].append(
                ("project", pr.pk, pr.title, f"/manage/projects/{pr.pk}/")
            )
        if not rels.filter(relationship_type__code=ment).exists():
            out["project_no_mentor"].append(
                ("project", pr.pk, pr.title, f"/manage/projects/{pr.pk}/")
            )
    open_forms = Assignment.objects.filter(
        reporting_period__status=PeriodStatus.OPEN,
        status__in=[AssignmentStatus.NOT_STARTED, AssignmentStatus.IN_PROGRESS],
    ).select_related("person", "form_definition", "source_relationship", "reporting_period")
    for a in open_forms:
        rel = a.source_relationship
        if rel and rel.effective_to and rel.effective_to < today:
            out["ended_but_open"].append(
                (
                    "assignment",
                    a.pk,
                    f"{a.person}: {a.form_definition.name}",
                    f"/manage/dashboard/?period={a.reporting_period.short_label}",
                )
            )
        if a.status == AssignmentStatus.NOT_STARTED and a.due_at < timezone.now():
            out["overdue"].append(
                (
                    "assignment",
                    a.pk,
                    f"{a.person}: {a.form_definition.name}",
                    f"/manage/dashboard/?period={a.reporting_period.short_label}",
                )
            )
    from apps.common.enums import PublicationStatus
    from apps.outcomes.models import Publication

    published = Publication.objects.filter(archived_at__isnull=True, status=PublicationStatus.PUBLISHED)
    from apps.outcomes.services import rrid_missing_ids

    missing = published.filter(pk__in=rrid_missing_ids())
    for pub in missing:
        out["rrid_not_cited"].append(
            ("publication", pub.pk, pub.title, f"/manage/outcomes/publications/{pub.pk}/")
        )
    for pub in published.filter(has_foreign_authors=True, cnap_cited=True).exclude(
        foreign_component_approved=True
    ):
        out["foreign_cites_grant"].append(
            ("publication", pub.pk, pub.title, f"/manage/outcomes/publications/{pub.pk}/")
        )
    for p in director_and_leader(today):
        out["director_and_leader"].append(("person", p.pk, str(p), f"/manage/people/{p.pk}/"))
    seen = {}
    for p in Person.objects.active():
        key = (p.first_name.strip().lower(), p.last_name.strip().lower())
        if key in seen:
            out["duplicate_names"].append(
                ("person", p.pk, f"{p} (also record {seen[key]})", f"/manage/people/{p.pk}/")
            )
        else:
            seen[key] = p.pk
    result = []
    for code, title, note in CHECKS:
        rows = [r for r in out[code] if (code, r[0], r[1]) not in dismissed]
        result.append({"code": code, "title": title, "note": note, "rows": rows, "why": WHY.get(code, note)})
    return result


def count():
    return sum(len(c["rows"]) for c in run())


# What each check looks for, why it matters, and what happens downstream (MW 2026-11-04: every
# heading explains itself on hover).
WHY = {
    "no_email": "Looks for people with no email address on file. Without one they never receive their forms, reminders, or sign-in links, so their answers are missing from the results and the RPPR. Click to see them, then add an address on each person’s page.",
    "project_no_leader": "Looks for projects with no current leader. Without a leader, no progress report or Mentee Survey goes out for the project, and RPPR D.1 has a gap. Click to see them, then add the leader on the project page.",
    "project_no_mentor": "Looks for projects with no current mentor. Without one, no mentor report goes out, so the mentoring evaluation has a gap. Click to see them, then add the mentor on the project page.",
    "ended_but_open": "Looks for forms still open for someone whose role has ended. Those forms count against completion even though the person is no longer expected to answer. Click to see them, then exempt each form on the reporting session dashboard.",
    "duplicate_names": "Looks for two people with the same first and last name. Duplicates split one person’s forms and credits across two records. Click to see them, then merge or correct them.",
    "director_and_leader": "Looks for core directors who are also a Research or Pilot Project Leader. That is normally not allowed, so it is usually a data-entry slip. Click to see them, then correct the roles, or dismiss if it is right.",
    "rrid_not_cited": "Looks for published papers that used a core but did not cite its Research Resource Identifier (RRID). Without the RRID, the core’s use is traceable only through the grant citation. Click to see them, then note it for the author next time.",
    "foreign_cites_grant": "Looks for papers with foreign co-authors that cite CNAP’s grant without NIGMS approval of the foreign component. NIH may treat that as an unapproved foreign component. Click to see them, then credit the core with its RRID instead, or seek approval.",
    "overdue": "Looks for forms in an open reporting session that are past due and not started. These are the people to nudge personally. Click to see them, then send a reminder from the reporting session’s emails page.",
}
