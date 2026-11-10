"""
Load form definitions from fixtures/forms/*.json (manage.py load_forms).

Each file describes one form: its definition, display settings, sections,
questions, conditional rules and who receives it. Loading is idempotent:

- if the form's active version was built from identical content, nothing changes;
- if the content differs, a new version is created and (unless --draft) activated;
  the old version is retired. Not-started assignments in open periods move to
  the new version; anyone who has started keeps the version they began, so a
  respondent mid-way through a form is never moved;
- measures are created by code and must keep their scale;
- assignment rules are made to match the file (missing ones added, extra ones
  deactivated, never deleted).

Wording in these files is source wording: change it only as a form edit.
"""

import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog, record_event
from apps.common.enums import OPTION_QUESTION_TYPES, RuleScope, ScaleKind, VersionStatus
from apps.people.models import Core, RelationshipType

from .models import (
    AnswerSet,
    CompletionPathway,
    ConditionalRule,
    FormAssignmentRule,
    FormDefinition,
    FormSection,
    FormVersion,
    Measure,
    Question,
    QuestionOption,
)

FIXTURE_DIR = Path(settings.BASE_DIR) / "fixtures" / "forms"
VERSION_KEYS = ("intro_text", "sections", "rules")


class FormFixtureError(ValueError):
    pass


def _hash(spec):
    payload = {k: spec.get(k) for k in VERSION_KEYS}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _answer_set(form_code, q):
    if q.get("options"):
        name = f"{form_code}: {q['code']}"
        aset, created = AnswerSet.objects.get_or_create(
            name=name, is_shared=False, defaults={"scale_kind": ScaleKind.OTHER}
        )
        if created:
            for i, label in enumerate(q["options"], start=1):
                code = "".join(c if c.isalnum() else "_" for c in label.lower()).strip("_")[:40]
                QuestionOption.objects.create(answer_set=aset, code=code, label=label, sort_order=i)
        return aset
    name = q.get("answer_set")
    if not name:
        return None
    try:
        return AnswerSet.objects.get(name=name, is_shared=True)
    except AnswerSet.DoesNotExist as exc:
        raise FormFixtureError(
            f"{form_code}.{q['code']}: unknown answer set '{name}'. Run manage.py seed first."
        ) from exc


def _measure(form_code, q, aset):
    code = q.get("measure")
    if not code:
        return None
    m, created = Measure.objects.get_or_create(
        code=code, defaults={"name": q["prompt"][:255], "scale_kind": aset.scale_kind}
    )
    if m.scale_kind != aset.scale_kind:
        raise FormFixtureError(
            f"{form_code}.{q['code']}: measure {code} is {m.scale_kind} but the answer set is {aset.scale_kind}."
        )
    return m


def _build_version(fd, spec, version_no, cloned_from):
    fv = FormVersion.objects.create(
        form_definition=fd,
        version_no=version_no,
        status=VersionStatus.DRAFT,
        cloned_from=cloned_from,
        intro_text=spec.get("intro_text", ""),
        source_hash=_hash(spec),
        change_notes=spec.get("_change_notes", "Loaded from fixtures/forms."),
    )
    questions = {}
    sections = {}
    for s_order, s in enumerate(spec["sections"], start=1):
        sec = FormSection.objects.create(
            form_version=fv,
            code=s["code"],
            title=s.get("title", ""),
            instructions=s.get("instructions", ""),
            sort_order=s_order,
            is_repeatable=bool(s.get("repeatable")),
            repeat_label=s.get("repeat_label", ""),
        )
        sections[s["code"]] = sec
        for q_order, q in enumerate(s.get("questions", []), start=1):
            aset = _answer_set(fd.code, q)
            if q["type"] in OPTION_QUESTION_TYPES and not aset:
                raise FormFixtureError(
                    f"{fd.code}.{q['code']}: a {q['type']} question needs an answer set."
                )
            if q["type"] == "single_select" and not aset:
                raise FormFixtureError(f"{fd.code}.{q['code']}: a single select needs options.")
            question = Question(
                form_section=sec,
                code=q["code"],
                prompt=q["prompt"],
                help_text=q.get("help_text", ""),
                question_type=q["type"],
                answer_set=aset,
                measure=_measure(fd.code, q, aset) if aset else None,
                is_required=bool(q.get("required")),
                sort_order=q_order,
                config=q.get("config", {}),
            )
            question.save()
            questions[q["code"]] = question
    for r_order, r in enumerate(spec.get("rules", []), start=1):
        src = questions[r["source"]]
        value_option = None
        if r.get("value"):
            value_option = src.answer_set.options.get(code=r["value"])
        ConditionalRule.objects.create(
            form_version=fv,
            source_question=src,
            operator=r["operator"],
            value_option=value_option,
            action=r["action"],
            target_section=sections.get(r.get("target_section"))
            if r.get("target_section")
            else None,
            target_question=questions.get(r.get("target_question"))
            if r.get("target_question")
            else None,
            pathway=CompletionPathway.objects.get(code=r["pathway"]) if r.get("pathway") else None,
            sort_order=r_order,
        )
    return fv


def activate(actor, fv):
    """Make `fv` the active version of its form; retire the previous one."""
    with transaction.atomic():
        now = timezone.now()
        FormVersion.objects.filter(
            form_definition=fv.form_definition, status=VersionStatus.ACTIVE
        ).exclude(pk=fv.pk).update(status=VersionStatus.RETIRED, retired_at=now)
        fv.status = VersionStatus.ACTIVE
        fv.activated_at = now
        fv.save(update_fields=["status", "activated_at", "updated_at"])
        # Not-started assignments in open or draft periods move to the new
        # version; anyone who has started keeps the version they began.
        from apps.common.enums import AssignmentStatus, PeriodStatus
        from apps.reporting.models import Assignment

        moved = (
            Assignment.objects.filter(
                form_definition=fv.form_definition,
                status=AssignmentStatus.NOT_STARTED,
                reporting_period__status__in=[PeriodStatus.DRAFT, PeriodStatus.OPEN],
                responses__isnull=True,
            )
            .exclude(form_version=fv)
            .update(form_version=fv)
        )
        record_event(actor, AuditLog.Action.ACTIVATE_VERSION, fv, new={"moved_not_started": moved})
    return fv


def _sync_rules(fd, spec):
    wanted = []
    for r in spec.get("assignment_rules", []):
        rtype = (
            RelationshipType.objects.get(code=r["relationship_type"])
            if r.get("relationship_type")
            else None
        )
        excluded = RelationshipType.objects.get(code=r["excluded"]) if r.get("excluded") else None
        rule, _ = FormAssignmentRule.objects.get_or_create(
            form_definition=fd,
            relationship_type=rtype,
            defaults={
                "scope": r["scope"],
                "per_context": bool(r.get("per_context")),
                "excluded_relationship_type": excluded,
            },
        )
        rule.scope = r["scope"]
        rule.per_context = bool(r.get("per_context"))
        rule.excluded_relationship_type = excluded
        rule.is_active = True
        rule.full_clean(exclude=["form_definition"])
        rule.save()
        wanted.append(rule.pk)
    fd.assignment_rules.exclude(pk__in=wanted).update(is_active=False)


@transaction.atomic
def load_spec(spec, *, actor=None, draft=False):
    """Load one form spec. Returns (form_definition, version, status) where status is 'unchanged', 'created' or 'new version'."""
    if spec.get("about_core"):
        about_core = Core.objects.get(code=spec["about_core"])
    else:
        about_core = None
    fd, created = FormDefinition.objects.get_or_create(
        code=spec["code"],
        defaults={
            "name": spec["name"],
            "category": spec["category"],
            "context_kind": spec["context_kind"],
            "about_core": about_core,
        },
    )
    fd.name = spec["name"]
    fd.category = spec["category"]
    if fd.context_kind != spec["context_kind"]:
        if fd.assignments.exists():
            raise FormFixtureError(f"{fd.code}: its context can’t change once assignments exist.")
        fd.context_kind = spec["context_kind"]
    fd.about_core = about_core
    fd.confidentiality_class = spec.get("confidentiality", "standard")
    fd.sort_order = spec.get("sort_order", 0)
    fd.description = spec.get("description", "")
    fd.display = spec.get("display", {})
    fd.save()
    _sync_rules(fd, spec)
    h = _hash(spec)
    current = fd.versions.filter(status=VersionStatus.ACTIVE).first()
    pending = fd.versions.filter(status=VersionStatus.DRAFT, source_hash=h).first()
    if current and current.source_hash == h:
        return fd, current, "unchanged"
    if pending and draft:
        return fd, pending, "unchanged"
    last = fd.versions.order_by("-version_no").first()
    fv = pending or _build_version(fd, spec, (last.version_no + 1) if last else 1, current)
    if not draft or not current:
        activate(actor, fv)
    record_event(actor, AuditLog.Action.CREATE, fv, new={"source_hash": h})
    return fd, fv, "created" if created else "new version"


def load_all(*, actor=None, draft=False, directory=None, stdout=None):
    directory = Path(directory or FIXTURE_DIR)
    results = []
    for path in sorted(directory.glob("*.json")):
        spec = json.loads(path.read_text())
        fd, fv, status = load_spec(spec, actor=actor, draft=draft)
        results.append((fd, fv, status))
        if stdout:
            stdout.write(f"{fd.code}: v{fv.version_no} {status}")
        if not draft:
            n = sync_wording(fd)
            if n and stdout:
                stdout.write(f"{fd.code}: wording brought up to date on {n} earlier version(s)")
    return results


# Never copied back: a question whose meaning changed between versions (older answers are read by its old prompt).
KEEP_OLD_PROMPT = {"n_users"}


def sync_wording(fd):
    """Bring the directions on a form's earlier versions up to the current version (MW 2026-11-02: every request
    applies on every page, including forms already started or submitted). Copies the intro, section titles and
    directions, and each question's prompt, help text and required flag, matched by code and type. Answers,
    options and structure are untouched. Returns how many earlier versions changed."""
    from .models import FormSection, FormVersion, Question

    cur = fd.versions.filter(status=VersionStatus.ACTIVE).first()
    if not cur:
        return 0
    secs = {s.code: s for s in FormSection.objects.filter(form_version=cur)}
    qs = {q.code: q for q in Question.objects.filter(form_version=cur)}
    changed = 0
    for v in fd.versions.exclude(pk=cur.pk):
        hit = False
        if v.intro_text != cur.intro_text:
            FormVersion.objects.filter(pk=v.pk).update(intro_text=cur.intro_text)
            hit = True
        # an older Core Usage Report counted students apart from individual users: keep its own directions
        students_apart = Question.objects.filter(
            form_version=v, code="n_users", prompt__icontains="exclude student"
        ).exists()
        for s in FormSection.objects.filter(form_version=v):
            c = secs.get(s.code)
            if students_apart and s.code == "users":
                continue
            if c and (s.title, s.instructions) != (c.title, c.instructions):
                FormSection.objects.filter(pk=s.pk).update(
                    title=c.title, instructions=c.instructions
                )
                hit = True
        for q in Question.objects.filter(form_version=v):
            c = qs.get(q.code)
            if not c or c.question_type != q.question_type:
                continue
            new = {"help_text": c.help_text, "is_required": c.is_required}
            if q.code not in KEEP_OLD_PROMPT:
                new["prompt"] = c.prompt
            if any(getattr(q, k) != val for k, val in new.items()):
                Question.objects.filter(pk=q.pk).update(**new)
                hit = True
        changed += hit
    return changed


def universal_rule_check():
    """A sanity check used by tests: every universal rule is on a no-context form."""
    return (
        not FormAssignmentRule.objects.filter(scope=RuleScope.UNIVERSAL)
        .exclude(form_definition__context_kind="none")
        .exists()
    )
