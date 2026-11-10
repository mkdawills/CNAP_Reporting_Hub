"""The "As of" view (MW 2026-11-05): where each paper, proposal, and talk stood on a chosen day.

Built from the status history the Hub keeps, using the date a person gave for each step when one
was given (for example a paper's publication date), and the day the Hub recorded the step otherwise.
Records imported later still count from the dates they carry, so a past day shows what was imported.
Future days are not allowed.
"""

import datetime as dt

from django.utils import timezone

PERSON_DATE = {
    "pub": {
        "submitted": "submission_date",
        "published": "publication_date",
        "declined": "decline_date",
    },
    "grant": {
        "submitted": "submission_date",
        "awarded": "award_notice_date",
        "not_funded": "decision_date",
    },
}
ORDER = {
    "pub": ["planned", "submitted", "published", "declined"],
    "grant": ["planned", "submitted", "awarded", "not_funded"],
}


def parse(value):
    """A valid past or present day from ?asof=YYYY-MM-DD, or None."""
    try:
        d = dt.date.fromisoformat(value or "")
    except ValueError:
        return None
    return d if d <= timezone.localdate() else None


def events(kind, obj):
    """[(day, status)] in order: each step the item reached, dated by the person when possible."""
    given = PERSON_DATE[kind]
    seen, out = set(), []
    for h in obj.status_history.all():
        if h.to_status in seen:
            continue
        seen.add(h.to_status)
        field = given.get(h.to_status)
        day = (
            getattr(obj, field)
            if field and getattr(obj, field)
            else timezone.localtime(h.changed_at).date()
        )
        out.append((day, h.to_status))
    # A record imported without history still carries its dates.
    for status, field in given.items():
        if (
            status not in seen
            and getattr(obj, field, None)
            and ORDER[kind].index(status) <= ORDER[kind].index(obj.status)
        ):
            out.append((getattr(obj, field), status))
    out.sort(key=lambda e: (e[0], ORDER[kind].index(e[1])))
    return out


def status_on(kind, obj, day):
    """The item's status on `day`, or None when the Hub has no sign it existed yet."""
    evs = events(kind, obj)
    reached = [s for d, s in evs if d <= day]
    if reached:
        return reached[-1]
    created = timezone.localtime(obj.created_at).date()
    if created <= day:
        return "planned"
    return None


def talk_on(talk, day):
    when = talk.presented_on or timezone.localtime(talk.created_at).date()
    return when <= day


def quick_picks():
    """The last day of each reporting session that has ended, newest first."""
    from apps.reporting.models import ReportingPeriod

    today = timezone.localdate()
    return [
        {"label": p.name, "day": p.end_date}
        for p in ReportingPeriod.objects.filter(end_date__lt=today).order_by("-end_date")
    ]
