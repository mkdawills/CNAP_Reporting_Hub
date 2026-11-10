"""Core reports: what each core's directors receive about their own core (MW 2026-11-08).

Historically the evaluator gave each core director a core report: the numbers and written
answers from the user survey about that core, plus her themes and reflections. The Hub does
the same, under these rules:

- The evaluator releases each report. Before release, core directors see nothing.
- A core director sees only the report for a core the core director currently directs.
- No names, no list of who answered, and no answers shown together as one person's response.
- The evaluator can hold back any written answer that could identify the writer.
- Fewer than SMALL_N_THRESHOLD full responses: the report holds the reflections only.
- A release freezes the written answers, themes, and reflections. Changes need a new release.
"""

import hashlib

from django.conf import settings
from django.utils import timezone

from apps.audit.models import AuditLog, record_event
from apps.common.enums import FormCategory, QuestionType
from apps.forms_engine.models import FormDefinition
from apps.forms_engine.runtime import FormSchema
from apps.reporting.models import Answer

from .models import CoreReport, SnapshotNote
from .results import _ids, full_responses


def core_surveys():
    """The user surveys about a core: one per core."""
    return (
        FormDefinition.objects.filter(about_core__isnull=False, category=FormCategory.SURVEY)
        .select_related("about_core")
        .order_by("sort_order")
    )


def is_core_survey(form_definition):
    return bool(form_definition.about_core_id) and form_definition.category == FormCategory.SURVEY


def directed_core_ids(user):
    """Cores the signed-in person directs today (co-directors included)."""
    person = getattr(user, "person", None)
    if not person:
        return set()
    return set(
        person.current_relationships()
        .filter(relationship_type__code="core_director", core__isnull=False)
        .values_list("core_id", flat=True)
    )


def full_count(form_definition, period):
    return full_responses(form_definition, period).count()


def small_group(form_definition, period):
    return full_count(form_definition, period) < settings.SMALL_N_THRESHOLD


def _order(answer_ids, form_definition, period):
    """A stable shuffle, so the order of written answers can't point to who wrote them."""
    salt = f"{settings.SECRET_KEY}:core:{form_definition.pk}:{period.pk}"
    return sorted(answer_ids, key=lambda i: hashlib.sha256(f"{salt}:{i}".encode()).hexdigest())


def written_answers(form_definition, period):
    """Written answers from full responses, grouped by question: [{prompt, answers: [{id, text}]}]."""
    responses = full_responses(form_definition, period)
    first = responses.select_related("assignment__form_version").first()
    if not first:
        return []
    schema = FormSchema(first.assignment.form_version)
    followup = schema.followup_section.pk if schema.followup_section else None
    rows = (
        Answer.objects.filter(
            response_id__in=_ids(responses),
            question__question_type=QuestionType.LONG_TEXT,
        )
        .exclude(value_text="")
        .select_related("question", "question__form_section")
        .order_by("question__form_section__sort_order", "question__sort_order")
    )
    groups, by_prompt = [], {}
    for a in rows:
        q = a.question
        if q.config.get("narrative") or (followup and q.form_section_id == followup):
            continue
        if not (a.value_text or "").strip():
            continue
        g = by_prompt.get(q.prompt)
        if g is None:
            g = by_prompt[q.prompt] = {"prompt": q.prompt, "answers": []}
            groups.append(g)
        g["answers"].append({"id": a.pk, "text": a.value_text.strip()})
    for g in groups:
        texts = {x["id"]: x for x in g["answers"]}
        g["answers"] = [texts[i] for i in _order(list(texts), form_definition, period)]
    return groups


def themes_text(form_definition, period):
    snap = period.snapshots.order_by("-version_no").first()
    if not snap:
        return ""
    note = SnapshotNote.objects.filter(
        snapshot=snap, kind="theme_summary", section_ref=form_definition.code
    ).first()
    return note.body if note else ""


def get(form_definition, period):
    report, _ = CoreReport.objects.get_or_create(
        reporting_period=period, form_definition=form_definition
    )
    return report


def draft_content(report):
    """What a release would send right now."""
    fd, p = report.form_definition, report.reporting_period
    small = small_group(fd, p)
    content = {
        "small": small,
        "full": full_count(fd, p),
        "reflections": report.reflections.strip(),
        "themes": "",
        "written": [],
    }
    if not small:
        hidden = set(report.hidden_answers or [])
        content["themes"] = themes_text(fd, p).strip()
        for g in written_answers(fd, p):
            kept = [x["text"] for x in g["answers"] if x["id"] not in hidden]
            if kept:
                content["written"].append({"prompt": g["prompt"], "answers": kept})
    return content


def changed_since_release(report):
    return bool(report.released_at) and draft_content(report) != report.released_content


def release(user, report):
    content = draft_content(report)
    report.released_content = content
    report.released_at = timezone.now()
    report.released_by = user
    report.release_count += 1
    report.save()
    record_event(
        user,
        AuditLog.Action.UPDATE,
        report,
        new={
            "core_report_released": report.release_count,
            "written_answers": sum(len(g["answers"]) for g in content["written"]),
            "held_back": len(report.hidden_answers or []),
            "small_group": content["small"],
        },
    )
    return report


def withdraw(user, report):
    report.released_at = None
    report.released_content = {}
    report.save()
    record_event(user, AuditLog.Action.UPDATE, report, new={"core_report_withdrawn": True})
    return report


def released_for(user):
    """Released core reports for the cores this person directs, newest reporting session first."""
    cores = directed_core_ids(user)
    if not cores:
        return CoreReport.objects.none()
    return (
        CoreReport.objects.filter(
            released_at__isnull=False, form_definition__about_core_id__in=cores
        )
        .select_related("form_definition__about_core", "reporting_period")
        .order_by("-reporting_period__display_order", "form_definition__sort_order")
    )


def can_read(user, report):
    return (
        report.released_at is not None
        and report.form_definition.about_core_id in directed_core_ids(user)
    )
