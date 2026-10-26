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
        "People with no e-mail",
        "They can’t receive their forms, reminders or sign-in links.",
    ),
    (
        "project_no_leader",
        "Projects with no leader",
        "No progress report or Mentee Survey goes out for them.",
    ),
    ("project_no_mentor", "Projects with no mentor", "No mentor report goes out for them."),
    ("ended_but_open", "Open forms whose relationship has ended", "Consider exempting them."),
    ("duplicate_names", "Possible duplicate people", "Same first and last name on two records."),
    (
        "overdue",
        "Past due and not started",
        "Forms in an open period that are past due and untouched.",
    ),
]


def _current(on):
    return Q(effective_from__lte=on) & (Q(effective_to__isnull=True) | Q(effective_to__gte=on))


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
        result.append({"code": code, "title": title, "note": note, "rows": rows})
    return result


def count():
    return sum(len(c["rows"]) for c in run())
