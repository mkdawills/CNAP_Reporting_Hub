"""
Drafts, submissions, opt-outs and uploads for one assignment (Milestone 4).

Form field names posted by the form page:
    q-<code>                         one answer (option code, text or date)
    file-<code>                      an uploaded file for a file question
    rep-<section>-count              number of rows in a repeatable section
    rep-<section>-<i>-<code>         one field in row i of a repeatable section
"""

import datetime as dt
import hashlib
from pathlib import Path

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog, record_event
from apps.common.enums import AssignmentStatus, PeriodStatus, QuestionType
from apps.forms_engine.runtime import FormSchema

from ..models import Answer, AnswerFile, File, Response

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
OPTION_TYPES = (
    QuestionType.LIKERT,
    QuestionType.YES_NO,
    QuestionType.SINGLE_SELECT,
)


class SubmitError(ValueError):
    def __init__(self, missing, message=None):
        self.missing = missing
        n = len(missing)
        super().__init__(
            message
            or f"Answer {n} required question{'s' if n != 1 else ''} marked with * before submitting, "
            "or save a draft for later."
        )


class UploadError(ValueError):
    pass


class LockedError(ValueError):
    pass


# --------------------------------------------------------------------------- reading


def current_response(assignment):
    return assignment.responses.filter(is_current=True).first()


def answers_of(response, schema):
    """Return (answers, rows, files): values by code, repeatable rows by section code, File objects by code."""
    answers, rows, files = {}, {}, {}
    if not response:
        return answers, rows, files
    repeat_sections = {s.pk: s.code for s in schema.sections if s.is_repeatable}
    for a in response.answers.select_related("question", "option").prefetch_related("files__file"):
        q = a.question
        if a.option_id:
            val = a.option.code
        elif a.value_text is not None:
            val = a.value_text
        elif a.value_date is not None:
            val = a.value_date.isoformat()
        elif a.value_number is not None:
            n = a.value_number
            val = str(int(n)) if n == int(n) else format(n.normalize(), "f")  # "3", not "3.00"
        else:
            link = a.files.all().first()
            val = str(link.file_id) if link else None
            if link:
                files[q.code] = link.file
        if q.form_section_id in repeat_sections:
            sec = rows.setdefault(repeat_sections[q.form_section_id], [])
            while len(sec) <= a.repeat_index:
                sec.append({})
            sec[a.repeat_index][q.code] = val
        else:
            answers[q.code] = val
    return answers, rows, files


def is_editable(assignment, user):
    return (
        assignment.person_id == user.person_id
        and assignment.reporting_period.status == PeriodStatus.OPEN
        and not assignment.reporting_period.in_preview
        and assignment.status
        not in (
            AssignmentStatus.SUBMITTED,
            AssignmentStatus.COMPLETED_OPT_OUT,
            AssignmentStatus.EXEMPT,
        )
    )


# --------------------------------------------------------------------------- writing


def _draft(assignment, user):
    resp = current_response(assignment)
    if resp and resp.submitted_at:
        raise LockedError(
            "This form has been submitted. Ask the Center to reopen it if you need to change it."
        )
    if not resp:
        resp = Response.objects.create(assignment=assignment, submitted_by=None)
    if assignment.status == AssignmentStatus.NOT_STARTED:
        assignment.status = AssignmentStatus.IN_PROGRESS
        assignment.started_at = timezone.now()
        assignment.save(update_fields=["status", "started_at", "updated_at"])
    return resp


def _set_value(response, q, raw, repeat_index=0):
    Answer.objects.filter(response=response, question=q, repeat_index=repeat_index).delete()
    if raw in (None, ""):
        return None
    a = Answer(response=response, question=q, repeat_index=repeat_index)
    if q.question_type in OPTION_TYPES:
        opt = q.answer_set.options.filter(code=raw).first()
        if not opt:
            return None
        a.option = opt
    elif q.question_type == QuestionType.DATE:
        try:
            a.value_date = dt.date.fromisoformat(raw)
        except ValueError:
            return f"“{q.prompt}” needs a date."
    elif q.question_type in (QuestionType.NUMBER, QuestionType.CURRENCY):
        try:
            a.value_number = float(raw)
        except ValueError:
            return f"“{q.prompt}” needs a number."
    else:
        a.value_text = raw
    a.save()
    return None


def system_value(assignment, q):
    """Answers the site fills in itself (hidden questions), e.g. whether the person is named on the NoA."""
    if q.config.get("source") == "senior_key":
        from apps.people.services import is_senior_key

        return "yes" if is_senior_key(assignment.person) else "no"
    if q.config.get("source") == "nih_audience":  # which NIH-documents directions to show
        from apps.people.services import is_osc_only, is_senior_key

        p = assignment.person
        return "osc" if is_osc_only(p) else "senior_key" if is_senior_key(p) else "default"
    if q.config.get("source") == "osc_only":
        from apps.people.services import is_osc_only

        return "yes" if is_osc_only(assignment.person) else "no"
    return ""


def system_answers(assignment, schema):
    return {
        q.code: system_value(assignment, q)
        for q in schema.questions
        if q.config.get("widget") == "system"
    }


def store_upload(user, uploaded, question):
    accept = [x.lower() for x in question.config.get("accept", [])]
    ext = Path(uploaded.name).suffix.lower()
    if accept and ext not in accept:
        names = " or ".join(accept)
        if accept == [".pdf"]:
            kind = "a PDF"
        elif set(accept) <= {".doc", ".docx"}:
            kind = f"a Word document ({names})"
        else:
            kind = f"one of these file types: {', '.join(accept)}"
        raise UploadError(f"Please upload {kind}. Other file types can’t be accepted.")
    if uploaded.size > MAX_UPLOAD_BYTES:
        raise UploadError("That file is larger than 20 MB. Please upload a smaller file.")
    if ext == ".pdf":
        head = uploaded.read(1024)
        uploaded.seek(0)
        if b"%PDF-" not in head:
            raise UploadError("That file doesn’t look like a PDF. Please upload the PDF itself.")
    digest = hashlib.sha256()
    for chunk in uploaded.chunks():
        digest.update(chunk)
    uploaded.seek(0)
    f = File(
        original_filename=Path(uploaded.name).name[:255],
        content_type=getattr(uploaded, "content_type", "") or "application/octet-stream",
        byte_size=uploaded.size,
        sha256=digest.hexdigest(),
        uploaded_by=user,
    )
    f.storage_key.save(Path(uploaded.name).name, uploaded, save=False)
    f.save()
    return f


@transaction.atomic
def save_draft(assignment, user, post, files=None, *, row_action=None):
    """Save whatever is filled in. Returns a list of messages for fields that couldn't be saved."""
    if not is_editable(assignment, user):
        raise LockedError("This form can’t be changed now.")
    schema = FormSchema(assignment.form_version)
    resp = _draft(assignment, user)
    problems = []
    files = files or {}
    for sec in schema.sections:
        if sec.is_repeatable:
            continue
        for q in sec.questions.all():
            if q.question_type == QuestionType.INSTRUCTIONS:
                continue
            if q.question_type == QuestionType.FILE:
                up = files.get(f"file-{q.code}")
                if up:
                    try:
                        f = store_upload(user, up, q)
                    except UploadError as exc:
                        problems.append(str(exc))
                        continue
                    Answer.objects.filter(response=resp, question=q).delete()
                    a = Answer.objects.create(response=resp, question=q)
                    AnswerFile.objects.create(answer=a, file=f)
                elif post.get(f"remove-{q.code}"):
                    Answer.objects.filter(response=resp, question=q).delete()
                continue
            raw = post.get(f"q-{q.code}", "")
            raw = raw.strip() if isinstance(raw, str) else raw
            if q.config.get("widget") == "system":  # set by the site, never by the person
                raw = system_value(assignment, q)
            if q.config.get("widget") == "optout_checkbox":
                raw = "yes" if raw else ""
            err = _set_value(resp, q, raw)
            if err:
                problems.append(err)
    for sec in schema.sections:
        if not sec.is_repeatable:
            continue
        qs = list(sec.questions.all())
        try:
            count = int(post.get(f"rep-{sec.code}-count", 0))
        except ValueError:
            count = 0
        rows = []
        for i in range(min(count, 200)):
            row = {q.code: (post.get(f"rep-{sec.code}-{i}-{q.code}", "") or "").strip() for q in qs}
            if any(row.values()):
                rows.append(row)
        if row_action and row_action.startswith(f"remove:{sec.code}:"):
            idx = int(row_action.rsplit(":", 1)[1])
            if 0 <= idx < len(rows):
                rows.pop(idx)
        sheet = files.get(f"sheet-{sec.code}")
        if sheet:  # an Excel sheet instead of typing (MW 2026-11-03); its rows are added
            from . import sheets

            try:
                new, notes = sheets.read(sec, sheet)
            except sheets.SheetError as exc:
                problems.append(str(exc))
            else:
                rows.extend(new[: max(0, sheets.MAX_ROWS - len(rows))])
                problems.extend(notes)
        Answer.objects.filter(response=resp, question__in=qs).delete()
        for i, row in enumerate(rows):
            for q in qs:
                err = _set_value(resp, q, row[q.code], repeat_index=i)
                if err:
                    problems.append(err)
    resp.save(update_fields=["updated_at"])
    return problems


@transaction.atomic
def submit(assignment, user, *, request=None):
    """Submit the current draft. Raises SubmitError listing required questions still blank."""
    if not is_editable(assignment, user):
        raise LockedError("This form can’t be submitted now.")
    schema = FormSchema(assignment.form_version)
    resp = _draft(assignment, user)
    answers, rows, files = answers_of(resp, schema)
    answers |= system_answers(assignment, schema)
    missing = schema.missing_required(answers, rows)
    if missing:
        raise SubmitError(missing)
    if assignment.form_definition.code == "nih_documents":  # SciENcv PDFs must pass (MW 2026-10-28)
        from apps.outcomes import sciencv

        labels = {"biosketch": "Biosketch", "current_pending": "Current and Pending"}
        problems = []
        for code, label in labels.items():
            q = schema.by_code.get(code)
            if files.get(code) and q and schema.question_visible(q, answers):
                msg = sciencv.message(code, sciencv.read_file(files[code], code))
                if msg:
                    problems.append(f"{label}: {msg}")
        if problems:
            raise SubmitError([], "Not submitted yet. " + " ".join(problems))
    pathway = schema.pathway(answers)
    hidden = [q.pk for q in schema.questions if not schema.question_visible(q, answers)]
    resp.answers.filter(question_id__in=hidden).delete()
    now = timezone.now()
    resp.submitted_at = now
    resp.submitted_by = user
    resp.save(update_fields=["submitted_at", "submitted_by", "updated_at"])
    assignment.status = (
        AssignmentStatus.COMPLETED_OPT_OUT if pathway.is_opt_out else AssignmentStatus.SUBMITTED
    )
    assignment.completion_pathway = pathway
    assignment.submitted_at = now
    assignment.save(update_fields=["status", "completion_pathway", "submitted_at", "updated_at"])
    record_event(user, AuditLog.Action.SUBMIT, assignment, new={"pathway": pathway.code})
    _contact_requests(assignment, schema, answers)
    return assignment


@transaction.atomic
def quick_opt_out(assignment, user):
    """
    The Opt out button on My tasks. Forms with follow-up questions (cores,
    NeuroSync) open with the opt-out ticked so the follow-ups can be answered;
    the others are recorded straight away. Returns 'open' or 'done'.
    """
    schema = FormSchema(assignment.form_version)
    q = schema.optout_question
    if not q:
        raise ValueError("This form has no opt-out.")
    if not is_editable(assignment, user):
        raise LockedError("This form can’t be changed now.")
    resp = _draft(assignment, user)
    _set_value(resp, q, "yes")
    if schema.followup_section:
        return "open"
    submit(assignment, user)
    return "done"


@transaction.atomic
def reopen(actor, assignment, reason=""):
    """
    Let the respondent change a submitted form. The submitted response is kept
    (no longer current) and a new current draft starts from a copy of it.
    """
    if assignment.status not in (AssignmentStatus.SUBMITTED, AssignmentStatus.COMPLETED_OPT_OUT):
        raise ValueError("Only a submitted form can be reopened.")
    old = current_response(assignment)
    if old:
        old.is_current = False
        old.reopened_at = timezone.now()
        old.save(update_fields=["is_current", "reopened_at", "updated_at"])
        new = Response.objects.create(assignment=assignment)
        for a in old.answers.prefetch_related("files"):
            links = list(a.files.all())
            a.pk = None
            a.response = new
            a.save()
            for link in links:
                AnswerFile.objects.create(
                    answer=a, file_id=link.file_id, sort_order=link.sort_order
                )
    assignment.status = AssignmentStatus.IN_PROGRESS
    assignment.completion_pathway = None
    assignment.reopened_at = timezone.now()
    assignment.save(update_fields=["status", "completion_pathway", "reopened_at", "updated_at"])
    record_event(actor, AuditLog.Action.REOPEN, assignment, reason=reason)


def can_self_reopen(assignment, user):
    """Someone may reopen their own submitted form while its period is open (MW 2026-11-02)."""
    return (
        assignment.person_id == user.person_id
        and assignment.status in (AssignmentStatus.SUBMITTED, AssignmentStatus.COMPLETED_OPT_OUT)
        and assignment.reporting_period.status == PeriodStatus.OPEN
        and not assignment.reporting_period.in_preview
    )


def _contact_requests(assignment, schema, answers):
    """A core non-user asked to be contacted: tell that core's directors and staff."""
    for q in schema.questions:
        if not q.config.get("contact_request") or answers.get(q.code) != "yes":
            continue
        core = assignment.form_definition.about_core
        if not core:
            continue
        from apps.people.models import PersonRelationship

        today = timezone.localdate()
        contacts = (
            PersonRelationship.objects.filter(
                core=core,
                relationship_type__code__in=["core_director", "core_staff"],
                effective_from__lte=today,
            )
            .exclude(effective_to__lt=today)
            .select_related("person")
        )
        emails = sorted({r.person.primary_email for r in contacts if r.person.primary_email})
        person = assignment.person
        record_event(
            None,
            AuditLog.Action.UPDATE,
            assignment,
            new={"core_contact_request": core.code, "notified": len(emails)},
        )
        if emails:
            send_mail(
                subject=f"CNAP Reporting Hub: someone would like to hear about the {core.name}",
                message=(
                    f"{person.full_name} ({person.primary_email or 'no email on file'}"
                    f"{', ' + person.institution if person.institution else ''}) said in the "
                    f"{assignment.reporting_period.short_label} survey that they didn’t use the {core.name}, "
                    "and would like someone from the core to reach out about what it offers.\n\n"
                    "Only this contact request is shared with you. Their survey answers are not."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=emails,
                fail_silently=True,
            )
