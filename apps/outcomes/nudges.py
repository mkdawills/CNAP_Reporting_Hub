"""
Monthly check-in emails for planned grant proposals (MW 2026-11-03).

A planned proposal no longer waits for the stale-record reminder. Instead, the person who plans it
gets one friendly check-in email about once a month (GRANT_NUDGE_EVERY_DAYS). The email names the
proposal, its funding agency, and its anticipated submission date, and links to a one-page answer
form in the Hub: five choices and a comments box. Answers appear on the Reminders tab.

Run daily by manage.py send_outcome_reminders, alongside the stale-record reminders.
"""

import datetime as dt

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone

from apps.accounts import signin
from apps.audit.models import AuditLog, record_event
from apps.common.enums import GrantStatus

from .models import GrantNudge, GrantSubmission, OutcomeDelegate

# From each cohort's signed "Roles, Responsibilities, and Terms" (Appendix A).
# Shown on the answer page when someone says they are pivoting away from a plan.
MILESTONES = {
    "research": [
        "Development of a functional laboratory, including installation of new equipment, and recruitment of students and staff.",
        "Progress toward completion of experiments that address the specific aims of the primary project.",
        "Submission of abstracts and delivery of presentations at national and international meetings based on the primary project (typically one to two per year of support).",
        "Submission and publication of high-impact articles in quality peer-reviewed journals based on the primary project (typically one publication per year of support).",
        "Collection of preliminary data suitable for a Research Project Grant (RPG) application.",
        "Submission of an RPG application within two years of support.",
        "Funding of an RPG within three years of support.",
    ],
    "pilot": [
        "Deliver at least one presentation at a national or international conference that cites CNAP support during the pilot grant support period.",
        "Submit at least one manuscript to a high-impact journal that cites CNAP support within six months of pilot grant completion.",
        "Submit an extramural grant as lead principal investigator (PI), based on CNAP-supported research, within one year of pilot grant completion.",
    ],
}

SUPPORTS = [
    "Coordination and payment of an external scientific review of your proposal.",
    "Support with the design of an internal timeline.",
    "Critical review of your written drafts.",
]


def role_of(person):
    """'research' for a current Research Project Leader, 'pilot' for a Pilot Project Leader, else ''."""
    codes = set(person.current_relationships().values_list("relationship_type__code", flat=True))
    if "project_leader" in codes:
        return "research"
    if "pilot_awardee" in codes:
        return "pilot"
    return ""


def lead(grant):
    """The person the check-in goes to: the primary CNAP contact, else the first person listed."""
    people = list(grant.people.all())
    row = next((x for x in people if x.is_primary_cnap_contact), None) or next(iter(people), None)
    return row.person if row else None


def due(now=None):
    """[(grant, person, [cc emails])] for every planned proposal whose monthly check-in is due now."""
    now = now or timezone.now()
    every = dt.timedelta(days=settings.GRANT_NUDGE_EVERY_DAYS)
    out = []
    grants = (
        GrantSubmission.objects.filter(archived_at__isnull=True, status=GrantStatus.PLANNED)
        .filter(created_at__lte=now - every)
        .prefetch_related("people__person")
        .order_by("project_title")
    )
    for g in grants:
        last = g.nudges.order_by("-sent_at").first()
        if last and last.sent_at > now - every:
            continue
        person = lead(g)
        if not person or not person.is_active or person.archived_at or not person.primary_email:
            continue
        cc = [
            d.delegate.primary_email
            for d in OutcomeDelegate.objects.filter(
                owner=person, ended_at__isnull=True
            ).select_related("delegate")
            if d.delegate.primary_email
        ]
        out.append((g, person, cc))
    return out


def send(actor=None, now=None, dry_run=False):
    """Send every check-in that is due. Returns [(grant, person, sent_to)]."""
    sent = []
    for grant, person, cc in due(now):
        to = person.primary_email
        if dry_run:
            sent.append((grant, person, ", ".join([to, *cc])))
            continue
        nudge = GrantNudge.objects.create(grant=grant, person=person, sent_to=", ".join([to, *cc]))
        path = f"/outcomes/nudge/{nudge.pk}/"

        def link(next_path):
            if signin.may_use_link(person):
                return signin.make_link(person, to, purpose="grant_nudge", next_path=next_path)
            return f"{settings.SITE_URL}{next_path}"

        url = link(path)
        # Each answer is its own link, so one click lands on the page with it already
        # selected (MW 2026-11-03).
        choice_links = [
            (label, link(f"{path}?choice={code}")) for code, label in GrantNudge.Choice.choices
        ]
        body = render_to_string(
            "email/grant_nudge.txt",
            {
                "person": person,
                "grant": grant,
                "url": url,
                "choice_links": choice_links,
                "supports": SUPPORTS,
            },
        )
        EmailMessage(
            subject=f"A quick check-in on your planned proposal: {grant.project_title}"[:200],
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to],
            cc=cc,
        ).send(fail_silently=False)
        record_event(
            actor,
            AuditLog.Action.CREATE,
            nudge,
            new={"grant": grant.pk, "to": nudge.sent_to},
        )
        sent.append((grant, person, nudge.sent_to))
    return sent
