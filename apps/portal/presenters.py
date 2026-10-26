"""Turn assignments and responses into what the portal templates show."""

import json

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.common.enums import AssignmentStatus, ConfidentialityClass, FormCategory, QuestionType
from apps.forms_engine.models import FormDefinition
from apps.forms_engine.runtime import FormSchema
from apps.people.models import PersonRelationship
from apps.reporting.services import responses as rs

TASK_GROUPS = [
    ("cores", "Core facilities", "Tell us about the cores you used. Opt out of any you didn’t."),
    ("grant", "Your CNAP grant", "Feedback on your project and your mentoring."),
    ("mycore", "Your core", "Reports for the core you direct: progress and who used the core."),
    ("mentoring", "Projects you mentor", "Your view as a mentor on a CNAP project."),
    ("admin", "Administrative Core", "How the Center’s administration is serving you."),
    ("other", "Other Center features and services", "Opt out of any you didn’t use."),
    (
        "hub",
        "CNAP Reporting Hub",
        "Help us improve this site. You’re using it right now, so this one applies to everyone.",
    ),
]
SHADES = ["#b04a5a", "#d38a6a", "#b9b3c6", "#7aa99c", "#2c7a68"]
OPEN_STATUSES = (AssignmentStatus.NOT_STARTED, AssignmentStatus.IN_PROGRESS)


def _schemas():
    cache = {}

    def get(version):
        if version.pk not in cache:
            cache[version.pk] = FormSchema(version)
        return cache[version.pk]

    return get


def _noun(fd):
    return "report" if fd.category == FormCategory.REPORT else "survey"


def _context_line(a):
    if a.project_id and a.form_definition.code in (
        "pilot_mentor_report",
        "primary_mentor_report",
        "mentee_survey",
    ):
        return a.project.title
    return ""


def task_list(person, period, mine, just_done=None):
    schema = _schemas()
    today = timezone.localdate()
    used = set(
        PersonRelationship.objects.filter(
            person=person, relationship_type__code="core_user", effective_from__lte=today
        )
        .exclude(effective_to__lt=today)
        .values_list("core_id", flat=True)
    )
    rows = []
    for a in mine:
        s = schema(a.form_version)
        fd = a.form_definition
        disp = fd.display or {}
        group = disp.get("task_group", "other")
        if fd.code == "progress_core":
            group = "mycore"
        is_open = a.status in OPEN_STATUSES
        rows.append(
            {
                "a": a,
                "name": fd.name,
                "context": _context_line(a),
                "group": group,
                "about": disp.get("about", []),
                "time": s.time_label(),
                "minutes": s.minutes() if not disp.get("time_label") else 0,
                "can_opt_out": bool(s.optout_question) and is_open and not period.in_preview,
                "opt_out_note": (disp.get("opt_out") or {}).get("short", ""),
                "used_core": bool(fd.about_core_id and fd.about_core_id in used),
                "is_open": is_open,
                "preview_only": period.in_preview,
                "noun": _noun(fd),
                "pathway": a.completion_pathway.name if a.completion_pathway_id else "",
            }
        )
    open_rows = sorted(
        [r for r in rows if r["is_open"]],
        key=lambda r: (
            not r["used_core"],
            r["a"].status != AssignmentStatus.IN_PROGRESS,
            r["minutes"] or 99,
        ),
    )
    groups = []
    for code, title, sub in TASK_GROUPS:
        g = [r for r in open_rows if r["group"] == code]
        if not g:
            continue
        used_rows = [r for r in g if r["used_core"]] if code == "cores" else []
        others = [r for r in g if r not in used_rows]
        groups.append(
            {
                "code": code,
                "title": title,
                "sub": sub,
                "used": used_rows,
                "rows": others,
                "count": len(g),
            }
        )
    done_rows = [r for r in rows if not r["is_open"]]
    total, todo = len(rows), len(open_rows)
    next_up = None
    done_item = None
    if just_done:
        done_item = next(
            (r for r in rows if str(r["a"].pk) == str(just_done) and not r["is_open"]), None
        )
        if done_item and open_rows:
            fam = "cores" if done_item["group"] == "cores" else done_item["a"].form_definition_id
            same = [
                r
                for r in open_rows
                if (r["group"] == "cores" and fam == "cores") or r["a"].form_definition_id == fam
            ]
            next_up = (same or sorted(open_rows, key=lambda r: r["minutes"] or 99))[0]
    return {
        "period": period,
        "groups": groups,
        "done": done_rows,
        "total": total,
        "todo": todo,
        "done_n": total - todo,
        "pct": round(100 * (total - todo) / total) if total else 0,
        "minutes_left": sum(r["minutes"] for r in open_rows),
        "has_optouts": any(r["can_opt_out"] for r in open_rows),
        "next_up": next_up,
        "just_done": done_item,
        "is_core_director": PersonRelationship.objects.filter(
            person=person, relationship_type__code="core_director", effective_from__lte=today
        )
        .exclude(effective_to__lt=today)
        .select_related("core"),
    }


# --------------------------------------------------------------------------- form page


def _prefill(a, fd):
    disp = fd.display or {}
    out = []
    holder = None
    if disp.get("holder_type") and a.project_id:
        today = timezone.localdate()
        rel = (
            PersonRelationship.objects.filter(
                project=a.project,
                relationship_type__code=disp["holder_type"],
                effective_from__lte=today,
            )
            .exclude(effective_to__lt=today)
            .select_related("person")
            .first()
        )
        holder = rel.person.full_name if rel else ""
    values = {
        "mentor": a.person.full_name,
        "institution": a.person.institution or "",
        "project": a.project.title if a.project_id else "",
        "holder": holder or "",
        "period": a.reporting_period.name,
    }
    for label, key in disp.get("prefill", []):
        out.append((label, values.get(key, "")))
    return out


def _question_view(q, value, *, missing_ids, file_obj=None, schema=None):
    view = {
        "q": q,
        "code": q.code,
        "type": q.question_type,
        "value": value or "",
        "required": q.is_required,
        "error": q.pk in missing_ids,
        "narrative": bool(q.config.get("narrative")),
        "widget": q.config.get("widget", ""),
        "accept": ",".join(q.config.get("accept", [])),
        "file": file_obj,
    }
    if q.answer_set_id:
        opts = list(q.answer_set.options.all())
        if q.question_type in (QuestionType.LIKERT, QuestionType.YES_NO):
            pts, na = [], []
            for o in opts:
                num, _, rest = o.label.partition(" - ")
                item = {
                    "code": o.code,
                    "label": o.label,
                    "num": num if rest else "",
                    "text": rest or o.label,
                }
                (na if o.is_na_option else pts).append(item)
            view["pts"], view["na"] = pts, na
        else:
            view["options"] = [{"code": o.code, "label": o.label} for o in opts]
    return view


def form_page(request, a, *, editable, errors=(), missing=(), preview=False):
    fd = a.form_definition
    schema = FormSchema(a.form_version)
    resp = rs.current_response(a)
    answers, rows, files = rs.answers_of(resp, schema)
    if request.method == "POST" and (errors or missing):
        # keep what was typed on the page when something couldn't be saved
        for q in schema.questions:
            if f"q-{q.code}" in request.POST:
                answers[q.code] = request.POST.get(f"q-{q.code}")
    missing_ids = {q.pk for q in missing}
    optout_q = schema.optout_question
    followup = schema.followup_section
    opted = bool(optout_q and answers.get(optout_q.code) == "yes")
    add_to = request.GET.get("add")
    sections = []
    for sec in schema.sections:
        if optout_q and sec.pk == optout_q.form_section_id:
            continue
        visible = schema.section_visible(sec, answers)
        if preview:
            visible = not (followup and sec.pk == followup.pk)
        sv = {
            "s": sec,
            "visible": visible,
            "is_followup": bool(followup and sec.pk == followup.pk),
            # one-paragraph directions above rating questions read as a caption under the heading
            "caption": bool(
                sec.instructions
                and "\n" not in sec.instructions.strip()
                and any(q.question_type == QuestionType.LIKERT for q in sec.questions.all())
            ),
            "questions": [],
            "rows": [],
        }
        qs = [q for q in sec.questions.all() if q.question_type != QuestionType.INSTRUCTIONS]
        if sec.is_repeatable:
            existing = rows.get(sec.code, [])
            if editable and (not existing or add_to == sec.code):
                existing = existing + [{}]
            for r in existing:
                sv["rows"].append(
                    [_question_view(q, r.get(q.code), missing_ids=missing_ids) for q in qs]
                )
            sv["template_row"] = [_question_view(q, "", missing_ids=set()) for q in qs]
        else:
            sv["questions"] = [
                _question_view(
                    q, answers.get(q.code), missing_ids=missing_ids, file_obj=files.get(q.code)
                )
                for q in qs
            ]
        sections.append(sv)
    preview_followup = None
    if preview and followup:
        preview_followup = next((s for s in sections if s["is_followup"]), None)
    hide_targets = {}
    show_targets = {}
    if optout_q:
        for r in schema.rules:
            if r.source_question_id != optout_q.pk or not r.target_section_id:
                continue
            (hide_targets if r.action == "hide" else show_targets).setdefault(
                r.target_section.code, True
            )
    missing_list = [{"code": q.code, "prompt": q.prompt or "Response"} for q in missing]
    return {
        "missing_list": missing_list,
        "a": a,
        "fd": fd,
        "noun": _noun(fd),
        "schema": schema,
        "intro": a.form_version.intro_text,
        "sections": [s for s in sections if not (preview and s["is_followup"])],
        "preview_followup": preview_followup,
        "optout": optout_q,
        "opted": opted,
        "optout_followups": bool(followup),
        "hide_on_optout": json.dumps(list(hide_targets)),
        "show_on_optout": json.dumps(list(show_targets)),
        "prefill": _prefill(a, fd),
        "editable": editable and not preview,
        "preview": preview,
        "errors": errors,
        "resume": editable
        and not preview
        and a.status == AssignmentStatus.IN_PROGRESS
        and resp
        and resp.answers.exists(),
        "context_line": _context_line(a)
        or (a.core.name if a.core_id and fd.code == "progress_core" else ""),
        "time_label": schema.time_label(),
        "max_upload_mb": 20,
        "debug": settings.DEBUG,
    }


def confidential_gate(request, a):
    """
    People who signed in with an emailed link confirm a 6-digit code before
    opening a confidential mentoring form (decisions.md, sign-in plan).
    Returns a redirect when the code is still needed, otherwise None.
    """
    if a.form_definition.confidentiality_class != ConfidentialityClass.MENTORING:
        return None
    if not request.session.get("signed_in_by_link"):
        return None
    if request.session.get("code_verified"):
        return None
    from django.shortcuts import redirect

    return redirect(f"{reverse('link_code')}?next={request.path}")


# --------------------------------------------------------------------------- history and results


def history_rows(done):
    periods = []
    for a in done:
        if not periods or periods[-1]["period"].pk != a.reporting_period_id:
            periods.append({"period": a.reporting_period, "rows": []})
        periods[-1]["rows"].append(
            {
                "a": a,
                "name": a.form_definition.name,
                "context": _context_line(a) or (a.core.name if a.core_id else ""),
                "opted": a.status == AssignmentStatus.COMPLETED_OPT_OUT,
                "pathway": a.completion_pathway.name if a.completion_pathway_id else "",
            }
        )
    return periods


def center_results(period):
    """Respondent-facing combined results: surveys only, never mentoring forms, items with n < 5 left out."""
    from apps.analytics.report import build

    cards = []
    if period.assignments.exists():
        forms = FormDefinition.objects.filter(
            category=FormCategory.SURVEY, assignments__reporting_period=period
        )
    else:  # imported prior-year averages only (decisions.md: prior-year averages)
        codes = period.snapshots.filter(provenance="aggregate_import").values_list(
            "results__group_key", flat=True
        )
        forms = FormDefinition.objects.filter(
            category=FormCategory.SURVEY, code__in=[c for c in codes if c]
        )
    forms = (
        forms.exclude(confidentiality_class=ConfidentialityClass.MENTORING)
        .distinct()
        .order_by("sort_order")
    )
    for fd in forms:
        data = build(fd, period, audience="respondent")
        if any(t["rows"] or t["left_out"] for t in data["tables"]):
            cards.append(data)
    return cards
