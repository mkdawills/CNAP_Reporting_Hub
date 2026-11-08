"""
"Your forms are open" and reminder emails for a reporting period (sign-in plan, decisions.md 2026-10-24).

Each email lists the person's own forms and due date. People who sign in by emailed link get a personal,
single-use link; K-State people (once single sign-on is on) get the site address instead.
- open: once per person per period, to everyone with forms in the period.
- reminder: to people with forms still to do, at most once every REMINDER_GAP_DAYS days.
- overdue: after the due date, to people with forms still to do, at most once a day.
plan() shows exactly who would get what, without sending anything.

Automatic schedule (MW 2026-10-28), run daily by manage.py send_scheduled_emails while a period accepts answers
and its auto_emails is on: the "open" email on opening day; a reminder every 4 days until the due date (counted
from each person's last email); then a reminder every day after the due date until the period closes.
"""

from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from apps.accounts import signin
from apps.audit.models import AuditLog, record_event
from apps.common.enums import AssignmentStatus

from ..models import Assignment, PeriodEmail

REMINDER_GAP_DAYS = 4  # MW 2026-10-28
OVERDUE_GAP_DAYS = 1
OPEN_STATUSES = (AssignmentStatus.NOT_STARTED, AssignmentStatus.IN_PROGRESS)


class EmailError(Exception):
    pass


# Email controls (MW 2026-11-08). Each period's email_plan can change how often reminders and past-due
# emails go out, skip a scheduled day, add a day, and reword each email's subject and opening sentence.
# The list of surveys and reports, the due date, and the sign-in link always stay automatic.
STANDARD_WORDING = {
    "open": {
        "subject": "CNAP Reporting Hub: your {session} reporting session is open",
        "opening": "The {session} CNAP reporting session is open.",
    },
    "reminder": {
        "subject": "Reminder: your {session} CNAP reporting session is due {due}",
        "opening": "This is a reminder that your {session} CNAP reporting session is due {due}.",
    },
    "overdue": {
        "subject": "Your {session} CNAP reporting session was due {due}",
        "opening": "Your {session} CNAP reporting session was due {due}, and the reporting session is still open, so there's still time.",
    },
}
EVERY_LIMITS = {"reminder": (1, 14), "overdue": (1, 7)}


def every(period, kind):
    """Days between reminders (kind "reminder") or past-due emails (kind "overdue") for one person."""
    default = REMINDER_GAP_DAYS if kind == "reminder" else OVERDUE_GAP_DAYS
    lo, hi = EVERY_LIMITS[kind]
    try:
        n = int((period.email_plan or {}).get(f"{kind}_every", default))
    except (TypeError, ValueError):
        n = default
    return min(max(n, lo), hi)


def skipped_days(period):
    return set((period.email_plan or {}).get("skip", []))


def added_days(period):
    """{date ISO string: kind} for emails the evaluator added on the timeline."""
    return {x["date"]: x["kind"] for x in (period.email_plan or {}).get("add", []) if x.get("kind") in ("reminder", "overdue")}


def wording(period, kind):
    """{subject, opening, custom}: this period's wording for one email, with {session} and {due} still in place."""
    std = STANDARD_WORDING[kind]
    own = ((period.email_plan or {}).get("wording") or {}).get(kind) or {}
    subject = (own.get("subject") or "").strip() or std["subject"]
    opening = (own.get("opening") or "").strip() or std["opening"]
    return {"subject": subject, "opening": opening, "custom": subject != std["subject"] or opening != std["opening"]}


def _fill(text, period):
    due = timezone.localtime(period.due_at)
    return text.replace("{session}", period.name).replace("{due}", f"{due:%A, %B} {due.day}")


def subject_for(period, kind):
    # Subjects name the due date without the weekday, as before.
    due = timezone.localtime(period.due_at)
    return wording(period, kind)["subject"].replace("{session}", period.name).replace("{due}", f"{due:%B} {due.day}")


def opening_for(period, kind):
    return _fill(wording(period, kind)["opening"], period)


def _label(a):
    ctx = a.project.title if a.project_id else (a.core.name if a.core_id else "")
    return a.form_definition.name + (f" ({ctx})" if ctx else "")


def _items(assignments):
    """Each survey or report with its time, and the summary line (MW 2026-11-07):
    "3 surveys and 2 reports, about 1 hour in all", then each one by name with its own time."""
    from apps.common.enums import FormCategory
    from apps.common.templatetags.cnap import duration
    from apps.forms_engine.runtime import FormSchema
    from apps.portal.presenters import _label_minutes, todo_summary

    cache, items = {}, []
    for a in assignments:
        if a.form_version_id not in cache:
            cache[a.form_version_id] = FormSchema(a.form_version)
        s = cache[a.form_version_id]
        label = (s.display or {}).get("time_label")
        minutes = _label_minutes(label) if label else s.minutes()
        items.append({
            "label": _label(a),
            "noun": "report" if a.form_definition.category == FormCategory.REPORT else "survey",
            "minutes": minutes,
            "time": s.time_label() if label else duration(minutes),
        })
    total = sum(i["minutes"] for i in items)
    summary = todo_summary(sum(1 for i in items if i["noun"] == "survey"), sum(1 for i in items if i["noun"] == "report"))
    return items, summary, (duration(total) if total else "")


def plan(period, kind, gap=None):
    """Rows of {person, email, forms, with_link, skip}. skip is a reason the person won't be emailed, or ''."""
    if kind not in PeriodEmail.Kind.values:
        raise EmailError("Unknown email kind.")
    qs = (
        Assignment.objects.filter(reporting_period=period)
        .exclude(status=AssignmentStatus.EXEMPT)
        .exclude(form_definition__code="neurosync_speaker_survey")  # sent on its own when the talk ends
        .select_related("person", "form_definition", "project", "core")
        .order_by("person__last_name", "person__first_name", "form_definition__sort_order")
    )
    by = {}
    for a in qs:
        by.setdefault(a.person_id, {"person": a.person, "all": [], "open": []})
        by[a.person_id]["all"].append(a)
        if a.status in OPEN_STATUSES:
            by[a.person_id]["open"].append(a)
    sent, last = {}, {}
    for e in PeriodEmail.objects.filter(period=period).order_by("sent_at"):
        if e.kind == kind:
            sent[e.person_id] = e.sent_at
        last[e.person_id] = e.sent_at  # any email for this period counts toward the gap
    today = timezone.localdate()
    gap_days = gap if gap is not None else (every(period, kind) if kind != "open" else 0)
    rows = []
    for d in by.values():
        p = d["person"]
        forms = d["all"] if kind == "open" else d["open"]
        skip = ""
        if not p.is_active or p.archived_at:
            skip = "Not active"
        elif not p.primary_email:
            skip = "No email on file"
        elif not forms:
            skip = "Nothing left to do"
        elif kind == "open" and p.pk in sent:
            skip = f"Already sent {timezone.localtime(sent[p.pk]):%b %-d}"
        elif (
            kind != "open"
            and p.pk in last
            and (today - timezone.localtime(last[p.pk]).date()).days < gap_days
        ):
            skip = f"Emailed {timezone.localtime(last[p.pk]):%b %-d}"
        rows.append(
            {
                "person": p,
                "email": p.primary_email,
                "forms": [_label(a) for a in forms],
                "assignments": forms,
                "with_link": signin.may_use_link(p),
                "skip": skip,
            }
        )
    return rows


def send(period, kind, actor=None, dry_run=False, gap=None):
    """Send the emails plan() says to send. Returns (sent, skipped) counts."""
    if not period.accepting_responses:
        raise EmailError("Emails can be sent only while the reporting session is open for answers.")
    rows = plan(period, kind, gap=gap)
    due = timezone.localtime(period.due_at)
    n = 0
    for r in rows:
        if r["skip"] or dry_run:
            continue
        p = r["person"]
        url = (
            signin.make_link(p, r["email"], purpose=f"period_{kind}", next_path="/tasks/")
            if r["with_link"]
            else f"{settings.SITE_URL}/tasks/"
        )
        items, summary, total = _items(r["assignments"])
        body = render_to_string(
            f"email/period_{kind}.txt",
            {
                "person": p,
                "period": period,
                "forms": r["forms"],
                "items": items,
                "summary": summary,
                "total": total,
                "opening": opening_for(period, kind),
                "due": f"{due:%A, %B} {due.day}",
                "url": url,
                "with_link": r["with_link"],
                "days": signin.LINK_DAYS,
                "site": settings.SITE_URL,
            },
        )
        subject = subject_for(period, kind)
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[r["email"]],
            fail_silently=False,
        )
        PeriodEmail.objects.create(
            period=period,
            person=p,
            kind=kind,
            email=r["email"],
            forms_listed=len(r["forms"]),
            with_link=r["with_link"],
            sent_by=actor,
        )
        n += 1
    skipped = sum(1 for r in rows if r["skip"])
    if not dry_run:
        record_event(
            actor, AuditLog.Action.UPDATE, period, new={f"emails_{kind}": n, "skipped": skipped}
        )
    return n, skipped


def scheduled_kind(period, today=None):
    """Which email the schedule sends today for this period ("open", "reminder", "overdue"), or None."""
    today = today or timezone.localdate()
    if not (period.accepting_responses and period.auto_emails):
        return None
    opens = timezone.localtime(period.opens_at).date()
    due = timezone.localtime(period.due_at).date()
    if today < opens:
        return None
    if today == opens:
        return PeriodEmail.Kind.OPEN
    iso = today.isoformat()
    if iso in added_days(period):
        return added_days(period)[iso]
    if iso in skipped_days(period):
        return None
    return PeriodEmail.Kind.REMINDER if today <= due else PeriodEmail.Kind.OVERDUE


def run_schedule(period, today=None):
    """Send what the schedule says for today. Anyone who missed the opening email gets it first.

    Returns a list of (kind, sent, skipped). Safe to run more than once a day: the gaps stop repeats.
    """
    kind = scheduled_kind(period, today)
    if not kind:
        return []
    today = today or timezone.localdate()
    out = [(PeriodEmail.Kind.OPEN, *send(period, PeriodEmail.Kind.OPEN))]
    if kind != PeriodEmail.Kind.OPEN:
        # An added day goes to everyone with something left, whatever their last email (one a day at most).
        gap = 1 if today.isoformat() in added_days(period) else None
        out.append((kind, *send(period, kind, gap=gap)))
    return out


def schedule_preview(period):
    """Plain-language description of the automatic schedule, for the emails page."""
    opens = timezone.localtime(period.opens_at).date()
    due = timezone.localtime(period.due_at).date()
    closes = timezone.localtime(period.closes_at).date() if period.closes_at else None
    return {
        "opens": opens,
        "due": due,
        "closes": closes,
        "first_reminder": opens + timedelta(days=every(period, "reminder")),
        "reminder_every": every(period, "reminder"),
        "overdue_every": every(period, "overdue"),
        "after_due": due + timedelta(days=1),
    }


def preview(period, kind):
    """The email exactly as one person would receive it today (MW 2026-11-07), for the emails page.
    Uses the first person this email would go to; the sign-in link is shown as a placeholder. Sends nothing."""
    rows = [r for r in plan(period, kind) if r["assignments"]]
    if not rows:
        return ""
    r = next((x for x in rows if not x["skip"]), rows[0])
    due = timezone.localtime(period.due_at)
    items, summary, total = _items(r["assignments"])
    body = render_to_string(
        f"email/period_{kind}.txt",
        {
            "person": r["person"], "period": period, "forms": r["forms"], "items": items,
            "summary": summary, "total": total, "opening": opening_for(period, kind), "due": f"{due:%A, %B} {due.day}",
            "url": "[personal sign-in link]" if r["with_link"] else f"{settings.SITE_URL}/tasks/",
            "with_link": r["with_link"], "days": signin.LINK_DAYS, "site": settings.SITE_URL,
        },
    )
    subject = subject_for(period, kind)
    return f"Subject: {subject}\n\n{body.strip()}"
