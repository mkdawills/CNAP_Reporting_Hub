"""
A period's full timeline, with exact dates (MW 2026-11-06): launch, opening, every reminder email, the due date,
the past-due emails, closing, and results. It is read-only: every date comes from what the Hub already stores
(the period's dates, when forms were assigned, each email sent, and each results version) or from the email
schedule in apps.reporting.services.emails. Nothing is written.
"""

from collections import Counter
from datetime import timedelta

from django.utils import timezone

from ..models import PeriodEmail
import datetime as dt

from . import emails as em


def _d(dt):
    return timezone.localtime(dt).date() if dt else None


def _people(n):
    return f"{n} {'person' if n == 1 else 'people'}"


def period_timeline(period, today=None):
    today = today or timezone.localdate()
    opens, due = _d(period.opens_at), _d(period.due_at)
    closes_plan, closed = _d(period.closes_at), _d(period.closed_at)
    first_assigned = period.assignments.order_by("assigned_at").values_list("assigned_at", flat=True).first()
    launched = _d(first_assigned)
    paused = not period.auto_emails
    sent = Counter((e.kind, _d(e.sent_at)) for e in PeriodEmail.objects.filter(period=period).only("kind", "sent_at"))
    ev = []

    def add(day, label, detail="", kind="step", tone=""):
        ev.append({"date": day, "label": label, "detail": detail, "kind": kind, "tone": tone})

    add(launched, "Launched, open for preview", "Forms were assigned, and people could read them." if launched else "Forms are assigned when you launch the reporting session.")
    open_n = sum(n for (k, d), n in sent.items() if k == PeriodEmail.Kind.OPEN and d == opens)
    add(opens, "Opens for answers", f"The “your reporting session is open” email went to {_people(open_n)}." if opens and opens <= today and open_n else "The “your reporting session is open” email goes to everyone with forms.", "email")
    for (k, d), n in sorted(sent.items(), key=lambda x: x[0][1]):
        if k == PeriodEmail.Kind.OPEN and d != opens:
            add(d, "“Your reporting session is open,” for people added later", f"Sent to {_people(n)}.", "email")

    # Every reminder date the schedule plans, plus any reminder sent by hand on another day.
    # Email controls (MW 2026-11-08): the evaluator's frequency, skipped days, and added days.
    gap = em.every(period, "reminder")
    skips, adds = em.skipped_days(period), em.added_days(period)
    plan = []
    d = opens + timedelta(days=gap) if opens else None
    while d and due and d <= due:
        plan.append(d)
        d += timedelta(days=gap)
    hand = sorted(d for (k, d), _ in sent.items() if k == PeriodEmail.Kind.REMINDER and d not in plan)
    added = {dt.date.fromisoformat(x): k for x, k in adds.items()}
    for day in sorted(set(plan) | set(hand) | {x for x, k in added.items() if x not in plan}):
        n = sent.get((PeriodEmail.Kind.REMINDER, day), 0) + sent.get((PeriodEmail.Kind.OVERDUE, day), 0) * (day in added)
        kind_word = "Past-due email" if added.get(day) == "overdue" else "Reminder email"
        future = day > today or (day == today and not n)
        if day in added:
            label = f"{kind_word}, added"
        elif day in plan:
            label = kind_word
        else:
            label = f"{kind_word}, sent by hand"
        if day.isoformat() in skips and day not in added and day > today:
            add(day, "Reminder email, skipped", "You skipped this email. Nothing goes out this day.", "email", "muted")
            ev[-1].update(iso=day.isoformat(), skipped=True)
            continue
        if not future:
            detail = f"Sent to {_people(n)} with surveys or reports still to do." if n else "Not sent: nobody needed one, or emails were paused."
        else:
            detail = "Paused: nothing goes out unless you turn automatic emails back on." if paused else (
                "Goes to everyone with surveys or reports still to do." if day in added else
                "Goes to everyone with surveys or reports still to do, unless the person had an email in the last " + (f"{gap} days." if gap > 1 else "day."))
        add(day, label, detail, "email")
        if day > today and day != opens:
            ev[-1].update(iso=day.isoformat(), added=day in added, skippable=day in plan and day not in added)

    add(due, "Due", f"{timezone.localtime(period.due_at):%-I:%M %p} Central Time.", "due")

    end = closed or closes_plan
    for (k, d), n in sorted(sent.items(), key=lambda x: x[0][1]):
        if k == PeriodEmail.Kind.OVERDUE:
            add(d, "Past-due email", f"Sent to {_people(n)} not yet finished.", "email", "warn")
    if due and not closed:
        start = max(due + timedelta(days=1), today if today > due else due + timedelta(days=1))
        until = f"until {end:%B %-d}" if end else "until you close the reporting session"
        og = em.every(period, "overdue")
        often = "every day" if og == 1 else f"every {og} days"
        add(start, f"Past-due emails {often}" if not paused else "Past-due emails (paused)",
            f"To everyone not yet finished, {until}." + (" Skipped days: " + ", ".join(f"{dt.date.fromisoformat(x):%B %-d}" for x in sorted(skips) if dt.date.fromisoformat(x) > due) + "." if any(dt.date.fromisoformat(x) > due for x in skips) else ""), "zone", "warn")

    add(closed or closes_plan, "Closed" if closed else "Closes", "Respondents can no longer change their forms." if closed else "Planned closing date. You close the reporting session on Reporting sessions.")
    snaps = list(period.snapshots.order_by("generated_at"))
    if snaps:
        add(_d(snaps[0].generated_at), "Results generated", f"Version {snaps[0].version_no}.")
    fin = period.finalized_at or next((s.finalized_at for s in snaps if s.finalized_at), None)
    if fin:
        add(_d(fin), "Finalized", "These are the official results.")

    ev = [e for e in ev if e["date"]]
    ev.sort(key=lambda e: (e["date"], {"step": 0, "email": 1, "due": 2, "zone": 3}[e["kind"]]))
    for e in ev:
        e["state"] = "past" if e["date"] < today else ("today" if e["date"] == today else "future")

    # Where things stand today, in words.
    if launched is None:
        now = "Not launched yet."
    elif opens and today < opens:
        now = f"Open for preview. Answers open in {(opens - today).days} day{'s' if (opens - today).days != 1 else ''}."
    elif closed:
        now = "The reporting session is closed."
    elif due and today <= due:
        left = (due - today).days
        now = f"Reminder emails: {left} day{'s' if left != 1 else ''} until the due date." if left else "Due today."
    else:
        og = em.every(period, "overdue")
        now = "Past due: past-due emails go out " + ("every day" if og == 1 else f"every {og} days") + " until you close the reporting session."
    if paused and not closed:
        now += " Automatic emails are paused."
    marker = {"date": today, "label": f"Today, {today:%B %-d}", "detail": now, "kind": "now", "tone": "warn" if now.startswith("Past due") else "", "state": "now"}
    i = next((k for k, e in enumerate(ev) if e["date"] > today), len(ev))
    ev.insert(i, marker)
    return {"events": ev, "now": now}
