"""The CNAP Member Hub homepage (MW 2026-11-13), built from the approved homepage prototype
(design/prototypes/member-hub/).

Presentation only. Every number, name, and date that describes the person or the Center comes from
records the app already keeps: the person's relationships, the open reporting session and their
assignments, funding matches and news, funding events and deadlines, NeuroSync talks, and the cores.
Nothing here writes to the database, and nothing changes who may see what: the person sees their own
tasks and matches, and the same Center-wide funding news, events, and talks the rest of the app shows
every member.

Sections the app has no records for yet (research stories, community profiles and threads, the
listserv, site-visit photos) render the prototype's sample content under a visible "Sample content"
note. docs/member-hub-homepage.md lists each one and the backend it needs.
"""

import re
from datetime import date, timedelta

from django.urls import reverse
from django.utils import timezone

from apps.accounts import access
from apps.common.templatetags.cnap import duration
from apps.outcomes import funding
from apps.people.models import Core, PersonRelationship
from apps.reporting.models import Assignment, ReportingPeriod, SpeakerTalk

from . import presenters

MENTOR_CODES = ("primary_mentor", "pilot_mentor")
LED_CODES = ("project_leader", "pilot_awardee")
CORE_ROLE_WORDS = {"core_user": "user", "core_director": "director", "core_staff": "staff"}
# MW 2026-11-13: "talks are on Wednesday at 2:30 to 3:30. Refreshments provided. In Leadership Room 127."
NEUROSYNC_WHERE = "Leadership Room 127"


def _strip_abbrev(name):
    """'Pilot Project Leader (PPL)' -> 'Pilot Project Leader'."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", name)


def _md(d):
    return f"{d:%B} {d.day}"


def _wmd(d):
    return f"{d:%A}, {d:%B} {d.day}"


def _first_sentence(text):
    text = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    return text


def role_lines(person, rels):
    """The person's current roles in plain words, then who mentors them."""
    lines = []
    for r in rels:
        code = r.relationship_type.code
        if r.core_id and code in CORE_ROLE_WORDS:
            words = f"{r.core.name} {CORE_ROLE_WORDS[code]}"
        else:
            words = _strip_abbrev(r.relationship_type.name)
        if words not in lines:
            lines.append(words)
    projects = [
        r.project_id for r in rels if r.project_id and r.relationship_type.code in LED_CODES
    ]
    if projects:
        today = timezone.localdate()
        mentors = (
            PersonRelationship.objects.filter(
                project_id__in=projects,
                relationship_type__code__in=MENTOR_CODES,
                effective_from__lte=today,
            )
            .exclude(effective_to__lt=today)
            .exclude(person=person)
            .select_related("person")
        )
        for m in mentors:
            words = f"Mentored by {m.person.full_name}"
            if words not in lines:
                lines.append(words)
    return lines


def _period_for(person):
    return (
        ReportingPeriod.objects.filter(status="open", assignments__person=person)
        .distinct()
        .order_by("-display_order")
        .first()
    )


def reporting(person):
    """The person's open reporting session, in the words the homepage uses, or None."""
    period = _period_for(person)
    if not period:
        return None
    mine = list(
        Assignment.objects.filter(person=person, reporting_period=period).select_related(
            "form_definition", "form_version", "project", "core", "completion_pathway"
        )
    )
    if not mine:
        return None
    t = presenters.task_list(person, period, mine)
    today = timezone.localdate()
    due = timezone.localtime(period.due_at).date()
    days = (due - today).days
    left = presenters.todo_summary(t["todo_surveys"], t["todo_reports"])
    return {
        "period": period,
        "name": f"{period.name} reporting",
        "total": t["total"],
        "todo": t["todo"],
        "done_n": t["done_n"],
        "left": left,
        "time": duration(t["minutes_left"]) if t["minutes_left"] else "",
        "due": due,
        "due_words": _wmd(due),
        "days": days,
        "kind": "red" if days <= 3 else "amber",
        "when": (
            f"Due in {days} days"
            if days > 1
            else "Due tomorrow"
            if days == 1
            else "Due today"
            if days == 0
            else "Past due"
        ),
        "closes": (
            f"closes in {days} days"
            if days > 1
            else "closes tomorrow"
            if days == 1
            else "closes today"
            if days == 0
            else f"was due {_md(due)}"
        ),
        "pct_dash": round(6 * t["done_n"] / t["total"], 2) if t["total"] else 0,
    }


def center_reporting():
    """For administrators: where the open reporting session stands, as on their dashboard."""
    from apps.common.enums import COMPLETE_STATUSES, AssignmentStatus

    period = ReportingPeriod.objects.filter(status="open").order_by("-display_order").first()
    if not period:
        return None
    # Counted the way the administrator home counts them: exempt assignments are left out.
    rows = list(
        Assignment.objects.filter(reporting_period=period)
        .exclude(status=AssignmentStatus.EXEMPT)
        .values_list("person_id", "status")
    )
    if not rows:
        return None
    people, open_people = set(), set()
    for pid, st in rows:
        people.add(pid)
        if st not in COMPLETE_STATUSES:
            open_people.add(pid)
    due = timezone.localtime(period.due_at).date()
    return {
        "period": period,
        "people": len(people),
        "finished": len(people) - len(open_people),
        "forms": len(rows),
        "forms_done": sum(1 for _, st in rows if st in COMPLETE_STATUSES),
        "due_words": _wmd(due),
    }


def _talk_row(t):
    end = timezone.localtime(t.ends_at)
    day = end.date()
    # The series runs 2:30 to 3:30 (MW 2026-11-13). A talk that ends at 3:30 shows the series time;
    # any other talk shows only when it ends, because the app records the end, not the start.
    standard = (end.hour, end.minute) == (15, 30)
    return {
        "t": t,
        "day": day,
        "weekday": f"{day:%A}",
        "date_words": _wmd(day),
        "time": "2:30 to 3:30 p.m."
        if standard
        else f"Ends {end:%-I:%M %p}".replace("AM", "a.m.").replace("PM", "p.m."),
        "chip_time": "2:30 p.m." if standard else f"to {end:%-I:%M}",
        "speaker": t.speaker,
        "initials": (t.speaker.first_name[:1] + t.speaker.last_name[:1]).upper(),
        "dept": t.speaker.department or t.speaker.institution,
    }


def neurosync(now=None):
    now = now or timezone.now()
    upcoming = list(
        SpeakerTalk.objects.filter(ends_at__gte=now)
        .select_related("speaker")
        .order_by("ends_at")[:6]
    )
    rows = [_talk_row(t) for t in upcoming]
    return {"next": rows[0] if rows else None, "later": rows[1:]}


def _funding_rows(person, today):
    rows = funding.picked_for(person, today)
    out = []
    week_ago = timezone.now() - timedelta(days=7)
    added = {
        m.opportunity_id: m.added_at for m in person.funding_matches.filter(ended_at__isnull=True)
    }
    for r in rows:
        o = r["o"]
        n = funding.days_left(o, today)
        if n is not None and n < 0:
            continue
        out.append(
            {
                **r,
                "days": n,
                "soon": n is not None and n <= 14,
                "is_new": bool(added.get(o.pk) and added[o.pk] >= week_ago),
                "why_line": _first_sentence(r["why"]),
                "eyebrow": " · ".join(x for x in (o.sponsor, o.mechanism) if x),
            }
        )
    return out


def calendar(person, today, picked):
    """The calendar's items for the academic year around today, from records the app keeps."""
    start = date(today.year if today.month >= 8 else today.year - 1, 8, 1)
    end = date(start.year + 1, 7, 31)
    ev = []
    talks = SpeakerTalk.objects.filter(
        ends_at__date__gte=start, ends_at__date__lte=end
    ).select_related("speaker")
    for t in talks:
        row = _talk_row(t)
        ev.append([row["day"].isoformat(), row["chip_time"], "ns", t.title, None, "#ev-h"])
    for p in ReportingPeriod.objects.filter(status="open"):
        d = timezone.localtime(p.due_at).date()
        if start <= d <= end:
            ev.append(
                [
                    d.isoformat(),
                    "All day",
                    "due",
                    f"{p.name} reporting due",
                    None,
                    reverse("portal:tasks"),
                ]
            )
    fund_url = reverse("portal:funding")
    seen = set()
    for r in picked + funding.for_everyone(today):
        o = r["o"]
        if o.pk in seen or not o.deadline or not (start <= o.deadline <= end):
            continue
        seen.add(o.pk)
        ev.append([o.deadline.isoformat(), "All day", "due", f"Deadline: {o.name}", None, fund_url])
    for e in funding.upcoming_events(today):
        if start <= e.starts_on <= end:
            ev.append(
                [
                    e.starts_on.isoformat(),
                    e.time_text or "All day",
                    "ctr",
                    e.title,
                    e.ends_on.isoformat() if e.ends_on and e.ends_on != e.starts_on else None,
                    e.url or fund_url,
                ]
            )
    ev.sort(key=lambda x: (x[0], x[1]))
    kinds = sorted({x[2] for x in ev}, key=["ns", "ctr", "due", "you", "cam"].index)
    upcoming_due = [x for x in ev if x[2] == "due" and x[0] >= today.isoformat()]
    nm = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
    next_month = [x for x in ev if x[0][:7] == nm.isoformat()[:7]][:2]
    return {
        "data": {
            "today": today.isoformat(),
            "min": start.isoformat(),
            "max": end.isoformat(),
            "events": ev,
            "breaks": [],
        },
        "kinds": kinds,
        "next_due": (
            {
                "date": date.fromisoformat(upcoming_due[0][0]),
                "title": upcoming_due[0][3],
                "url": upcoming_due[0][5],
            }
            if upcoming_due
            else None
        ),
        "next_month_name": f"{nm:%B}",
        "next_month": [
            {"date": date.fromisoformat(x[0]), "title": x[3], "time": x[1], "url": x[5]}
            for x in next_month
        ],
    }


def build(request):
    user = request.user
    person = user.person
    now = timezone.localtime()
    today = now.date()
    rels = list(
        person.current_relationships().select_related("relationship_type", "core", "project")
    )
    rep = reporting(person)
    picked = _funding_rows(person, today)
    ns = neurosync()
    cal = calendar(person, today, funding.picked_for(person, today))
    year_period = ReportingPeriod.objects.exclude(status="draft").order_by("-display_order").first()
    is_admin = access.can_view_admin(user)
    roles = role_lines(person, rels)
    if not roles and is_admin:
        roles = [access.admin_label(user)]
    return {
        "person": person,
        "greeting": "Good morning"
        if now.hour < 12
        else "Good afternoon"
        if now.hour < 17
        else "Good evening",
        "date_line": f"{now:%A}, {now:%B} {now.day}"
        + (f" · Grant Year {year_period.grant_year}" if year_period else ""),
        "initials": (person.first_name[:1] + person.last_name[:1]).upper(),
        "roles": roles,
        "rep": rep,
        "picked": picked[:3],
        "picked_more": max(0, len(picked) - 3),
        "picked_new": sum(1 for r in picked if r["is_new"]),
        "match": picked[0] if picked else None,
        "news": [{"n": n, "first": _first_sentence(n.summary)} for n in funding.news(limit=3)],
        "ns_where": NEUROSYNC_WHERE,
        "ns": ns,
        "ns_soon": ns["next"] if ns["next"] and (ns["next"]["day"] - today).days <= 7 else None,
        "cal": cal,
        "cores": list(Core.objects.filter(is_active=True)),
        "is_admin": is_admin,
        "center": center_reporting() if is_admin else None,
        "mentors_others": any(r.relationship_type.code in MENTOR_CODES for r in rels),
        "leads_project": any(r.relationship_type.code in LED_CODES for r in rels),
    }
