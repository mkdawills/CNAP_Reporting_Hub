"""
Assignment generation (Milestone 5).

Who receives what (decisions.md):
- universal forms go to everyone with an active CNAP relationship on the
  generation date, minus anyone holding the rule's excluded type (a core's
  directors for that core's survey);
- relationship forms go to holders of the rule's relationship type: one per
  relationship row when the rule is per context (a mentor report per project,
  a progress report per project or per core), otherwise one per person.

Generation is INSERT ... ON CONFLICT DO NOTHING against the one-assignment
rule (person, form, period, project, core, NULLS NOT DISTINCT), so running it
again never duplicates, moves or deletes anything.
"""

from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.models import AuditLog, record_event
from apps.common.enums import AssignmentSource, AssignmentStatus, RuleScope, VersionStatus
from apps.forms_engine.models import FormAssignmentRule
from apps.people.models import Person, PersonRelationship

from ..models import Assignment


@dataclass
class PlannedAssignment:
    person_id: int
    form_definition_id: int
    form_version_id: int
    project_id: int | None
    core_id: int | None
    source: str
    source_relationship_id: int | None = None


@dataclass
class GenerationResult:
    planned: list = field(default_factory=list)
    created: int = 0
    existing: int = 0


NO_FORMS_TYPES = ("osc",)


def generation_date(period):
    """Relationships count if current on the later of today and the period's opening day."""
    opens = timezone.localtime(period.opens_at).date()
    return max(timezone.localdate(), opens)


def _current(on):
    return Q(effective_from__lte=on) & (Q(effective_to__isnull=True) | Q(effective_to__gte=on))


def plan(period, on=None):
    """Everything the rules say should exist for `period`, whether or not it exists yet."""
    on = on or generation_date(period)
    rels = list(
        PersonRelationship.objects.filter(_current(on))
        .filter(person__is_active=True, person__archived_at__isnull=True)
        .select_related("relationship_type")
    )
    # An Other Significant Contributor only appears in RPPR D.1; that role alone brings no forms (MW 2026-10-28).
    audience = sorted({r.person_id for r in rels if r.relationship_type.code not in NO_FORMS_TYPES})
    held = {}
    for r in rels:
        held.setdefault(r.person_id, []).append(r)

    rules = (
        FormAssignmentRule.objects.filter(
            is_active=True,
            form_definition__archived_at__isnull=True,
            form_definition__versions__status=VersionStatus.ACTIVE,
        )
        .select_related("form_definition", "relationship_type", "excluded_relationship_type")
        .distinct()
    )
    out, seen = [], set()

    def add(pa):
        key = (pa.person_id, pa.form_definition_id, pa.project_id, pa.core_id)
        if key not in seen:
            seen.add(key)
            out.append(pa)

    versions = {}
    for rule in rules:
        fd = rule.form_definition
        yearly = (fd.display or {}).get("yearly_sequence")
        if yearly and period.sequence != yearly:  # a once-a-year form, e.g. NIH documents in Fall
            continue
        if fd.pk not in versions:
            versions[fd.pk] = fd.versions.get(status=VersionStatus.ACTIVE).pk
        fv = versions[fd.pk]
        if rule.scope == RuleScope.UNIVERSAL:
            for pid in audience:
                ex = rule.excluded_relationship_type_id
                if ex and any(
                    r.relationship_type_id == ex
                    and (not fd.about_core_id or r.core_id == fd.about_core_id)
                    for r in held[pid]
                ):
                    continue
                add(PlannedAssignment(pid, fd.pk, fv, None, None, AssignmentSource.UNIVERSAL))
            continue
        for r in rels:
            if r.relationship_type_id != rule.relationship_type_id:
                continue
            if rule.per_context:
                add(
                    PlannedAssignment(
                        r.person_id,
                        fd.pk,
                        fv,
                        r.project_id,
                        r.core_id,
                        AssignmentSource.RELATIONSHIP,
                        r.pk,
                    )
                )
            else:
                add(
                    PlannedAssignment(
                        r.person_id, fd.pk, fv, None, None, AssignmentSource.RELATIONSHIP, r.pk
                    )
                )
    return out


@transaction.atomic
def generate(period, actor=None, on=None):
    """Create every planned assignment that does not exist yet. Safe to run again."""
    planned = plan(period, on)
    before = Assignment.objects.filter(reporting_period=period).count()
    rows = [
        Assignment(
            person_id=p.person_id,
            form_version_id=p.form_version_id,
            form_definition_id=p.form_definition_id,
            context_kind=("project" if p.project_id else "core" if p.core_id else "none"),
            reporting_period=period,
            project_id=p.project_id,
            core_id=p.core_id,
            source=p.source,
            source_relationship_id=p.source_relationship_id,
            due_at=period.due_at,
        )
        for p in planned
    ]
    Assignment.objects.bulk_create(rows, ignore_conflicts=True)
    after = Assignment.objects.filter(reporting_period=period).count()
    result = GenerationResult(
        planned=planned, created=after - before, existing=len(planned) - (after - before)
    )
    record_event(
        actor,
        AuditLog.Action.ASSIGN,
        period,
        new={"created": result.created, "already_existed": result.existing},
    )
    return result


@transaction.atomic
def exempt(actor, assignment, reason):
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("An exemption needs a reason.")
    if assignment.is_complete:
        raise ValueError("This form is already complete.")
    old = assignment.status
    assignment.status = AssignmentStatus.EXEMPT
    assignment.exempt_reason = reason
    assignment.save(update_fields=["status", "exempt_reason", "updated_at"])
    record_event(actor, AuditLog.Action.EXEMPT, assignment, old={"status": old}, reason=reason)


@transaction.atomic
def remove_exemption(actor, assignment):
    if assignment.status != AssignmentStatus.EXEMPT:
        raise ValueError("This form is not exempt.")
    has_draft = assignment.responses.filter(is_current=True).exists()
    assignment.status = AssignmentStatus.IN_PROGRESS if has_draft else AssignmentStatus.NOT_STARTED
    assignment.exempt_reason = ""
    assignment.save(update_fields=["status", "exempt_reason", "updated_at"])
    record_event(actor, AuditLog.Action.UPDATE, assignment, new={"exemption_removed": True})


def people_for(period):
    return Person.objects.filter(assignments__reporting_period=period).distinct()


def due_label(period, today=None):
    today = today or timezone.localdate()
    due = timezone.localtime(period.due_at).date()
    days = (due - today).days
    nice = f"{due:%B} {due.day}"
    if days > 1:
        return f"They’re due in {days} days, on {nice}"
    if days == 1:
        return f"They’re due tomorrow, {nice}"
    if days == 0:
        return f"They’re due today, {nice}"
    return f"They were due {nice}, and you can still finish them"
