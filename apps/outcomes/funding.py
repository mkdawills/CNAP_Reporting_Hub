"""
Funding opportunities, funding news, and the not-funded follow-up letter (MW 2026-11-10).

Spec: docs/funding-follow-up-spec.md. The opportunity catalog is public information. Matches are MW's own
choices, never automatic. A person sees only their own matches, letters, and suggestions. Nothing is ever
emailed automatically: every letter waits for MW's review and Send.
"""

import json
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from apps.accounts import signin
from apps.audit.models import AuditLog, record_event
from apps.common.enums import FundingAudience, FundingMilestone, GrantStatus

from . import nudges
from .models import (
    FundingFollowUp,
    FundingMatch,
    FundingNewsItem,
    FundingOpportunity,
    FundingQuestion,
    FundingSuggestion,
    GrantSubmission,
    OutcomeDelegate,
)

FIXTURE = Path(settings.BASE_DIR) / "fixtures" / "funding" / "opportunities.json"

# MW's seven questions for weighing any funding opportunity (2026-11-10). Seeded once; MW edits them in the Hub.
QUESTIONS = [
    ("Eligibility", "Are you eligible for the funding opportunity?"),
    (
        "Preliminary data",
        "Do you have sufficient preliminary data to be competitive for the funding opportunity?",
    ),
    (
        "Fit with the funder",
        "Is your research question or hypothesis aligned with the objectives of the funding agency and of the "
        "funding opportunity?",
    ),
    (
        "Expertise",
        "Is your expertise sufficient for the call?\n"
        "Or do you need to build a team of co-investigators and collaborators to fill potential gaps?",
    ),
    (
        "Advancing the field",
        "Will your research question advance the field?\n"
        "Does the question sit at the intersection of current knowledge in the field and the next frontier of the field?",
    ),
    (
        "Available effort",
        "Do you have available person months of effort for the project?\n"
        "Count current and pending commitments, including CNAP effort.",
    ),
    (
        "Equipment and infrastructure",
        "Do you have the equipment and infrastructure necessary to make a strong pitch for your proposed project?\n"
        "Do you need to source other cores or resources outside of K-State?",
    ),
]

# MW's approved opening (2026-11-10). One sentence per line on the page and in the email.
OPENING = (
    "Submitting a proposal to the {agency} is a major accomplishment.\n"
    "We hope you’ve taken a moment to celebrate!\n"
    "And although it’s never easy, please be reminded that a non-award is part of every researcher’s journey "
    "toward funding."
)
SIGNOFF = "With best wishes,\nThe CNAP evaluation team"  # approved by MW 2026-11-10 (replaces "Cheering you on!")
COFUND_MECHANISMS = ("R01", "R15", "R35")
DUE_SOON_DAYS = 30
COMING_UP_DAYS = 120
STALE_DAYS = 90

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------


def load_questions(stdout=None):
    """Seed MW's seven questions once. Later edits are MW's, so existing questions are never overwritten."""
    if FundingQuestion.objects.exists():
        return 0
    for i, (title, text) in enumerate(QUESTIONS, start=1):
        FundingQuestion.objects.create(position=i, title=title, text=text)
    if stdout:
        stdout.write(f"funding questions: {len(QUESTIONS)} created")
    return len(QUESTIONS)


def load_catalog(stdout=None, path=FIXTURE):
    """Load the public opportunity catalog. Idempotent, keyed on tracker_id (or name): new rows are added and
    existing rows are left alone, so MW's edits in the Hub are never overwritten."""
    rows = json.loads(Path(path).read_text())["opportunities"]
    fields = {f.name for f in FundingOpportunity._meta.get_fields()}
    made = 0
    for row in rows:
        key = row.get("tracker_id") or ""
        q = (
            FundingOpportunity.objects.filter(tracker_id=key)
            if key
            else FundingOpportunity.objects.filter(name=row["name"])
        )
        if q.exists():
            continue
        FundingOpportunity.objects.create(
            **{k: v for k, v in row.items() if k in fields and v is not None}
        )
        made += 1
    if stdout:
        stdout.write(f"funding opportunities: {made} created, {len(rows) - made} already present")
    return made


def questions():
    return list(FundingQuestion.objects.active())


# ---------------------------------------------------------------------------
# What a person sees
# ---------------------------------------------------------------------------


def days_left(o, today=None):
    if not o.deadline:
        return None
    return (o.deadline - (today or timezone.localdate())).days


def status_of(o, today=None):
    """(state, words) for an opportunity's deadline. Color always comes with words (Design Rules, checklist F)."""
    n = days_left(o, today)
    if n is None:
        return ("idle", "Ongoing" if (o.deadline_text or "").startswith("Ongoing") else "Open")
    if n < 0:
        return ("idle", "Closed")
    days = f"{n} day{'' if n == 1 else 's'} left"
    if n <= DUE_SOON_DAYS:
        return ("alert", f"Due soon, {days}")
    if n <= COMING_UP_DAYS:
        return ("warn", f"Coming up, {days}")
    return ("ok", f"Open, {days}")


def _sort_key(o):
    n = days_left(o)
    return (n is None or n < 0, n if n is not None else 10**6, o.name.lower())


def row(o, why="", today=None):
    """One opportunity, ready for the page, the letter, and the email (the same order everywhere)."""
    state, words = status_of(o, today)
    return {
        "o": o,
        "state": state,
        "words": words,
        "milestone": FundingMilestone(o.counts_toward_milestone).label,
        "milestone_state": "ok" if o.counts_toward_milestone == FundingMilestone.YES else "idle",
        "when": o.deadline.strftime("%B %-d, %Y")
        if o.deadline and not o.deadline_text
        else (o.deadline_text or "Not listed"),
        "why": why,
    }


def open_matches(person):
    return FundingMatch.objects.filter(
        person=person, ended_at__isnull=True, opportunity__archived_at__isnull=True
    ).select_related("opportunity")


def picked_for(person, today=None):
    rows = [row(m.opportunity, m.why, today) for m in open_matches(person)]
    return sorted(rows, key=lambda r: _sort_key(r["o"]))


def for_everyone(today=None):
    qs = FundingOpportunity.objects.active().filter(audience=FundingAudience.EVERYONE)
    return sorted((row(o, today=today) for o in qs), key=lambda r: _sort_key(r["o"]))


def next_deadline(rows):
    days = [r["o"].deadline for r in rows if r["o"].deadline and days_left(r["o"]) >= 0]
    return min(days) if days else None


def news(limit=None):
    qs = FundingNewsItem.objects.active().order_by("-pinned", "-news_date", "-created_at")
    return list(qs[:limit] if limit else qs)


def letters_for(person):
    return list(
        FundingFollowUp.objects.filter(person=person, status=FundingFollowUp.Status.SENT)
        .select_related("grant")
        .order_by("-sent_at")
    )


def can_read_letter(user, f):
    """The person the letter is for, anyone entering for them, and the CNAP office."""
    from apps.accounts import access

    me = getattr(user, "person", None)
    if access.can_view_admin(user):
        return True
    if not me or f.status != FundingFollowUp.Status.SENT:
        return False
    return (
        me.pk == f.person_id
        or OutcomeDelegate.objects.filter(
            owner_id=f.person_id, delegate=me, ended_at__isnull=True
        ).exists()
    )


# ---------------------------------------------------------------------------
# Not funded
# ---------------------------------------------------------------------------


def letter_name(grant):
    return f"Next steps after {grant.project_title}"


def ensure_followup(grant, user=None):
    """One follow-up per proposal marked Not funded, for MW's queue. Re-saving never makes a second one."""
    if grant.status != GrantStatus.NOT_FUNDED:
        return None
    person = nudges.lead(grant)
    if not person:
        return None
    f, made = FundingFollowUp.objects.get_or_create(grant=grant, defaults={"person": person})
    if made:
        f.opportunities.set(
            default_featured(f)
        )  # pre-ticked: the person's matches and anything due soon
        record_event(user, AuditLog.Action.CREATE, f, new={"grant": grant.pk, "person": person.pk})
    return f


def add_match(o, person, why, user):
    """MW picks an opportunity for a person. A letter still waiting for review features it too."""
    m = FundingMatch.objects.create(opportunity=o, person=person, why=why, added_by=user)
    record_event(user, AuditLog.Action.CREATE, m, new={"opportunity": o.pk, "person": person.pk})
    for f in FundingFollowUp.objects.filter(person=person, status=FundingFollowUp.Status.TO_REVIEW):
        f.opportunities.add(o)
    return m


def status_changed(f):
    return f.status == FundingFollowUp.Status.TO_REVIEW and f.grant.status != GrantStatus.NOT_FUNDED


# ---------------------------------------------------------------------------
# The letter
# ---------------------------------------------------------------------------


def agency_phrase(grant):
    a = (grant.funding_agency or "").strip()
    return a or "funding agency"


def default_opening(f):
    return OPENING.format(agency=agency_phrase(f.grant))


def default_featured(f, today=None):
    """Pre-ticked: the person's open matches, plus anything relevant to most members due within 120 days."""
    today = today or timezone.localdate()
    ids = {m.opportunity_id for m in open_matches(f.person)}
    soon = FundingOpportunity.objects.active().filter(
        audience=FundingAudience.EVERYONE,
        deadline__gte=today,
        deadline__lte=today + timedelta(days=COMING_UP_DAYS),
    )
    ids |= set(soon.values_list("pk", flat=True))
    return ids


def wants_cofunding(grant):
    """IDeA co-funding applies to a single-principal-investigator NIH R01, R15, or R35 (COBRE handbook, chapter 19)."""
    mech = (grant.mechanism or "").upper()
    agency = (grant.funding_agency or "").upper()
    nih = "NIH" in agency or "NATIONAL INSTITUTE" in agency or (grant.funding_source_type == "nih")
    if not nih or not any(m in mech for m in COFUND_MECHANISMS):
        return False
    return not grant.people.filter(role="mpi").exists()


def letter_parts(f, today=None):
    """Everything the email, the letter page, and the composer preview share."""
    g = f.grant
    mine = set(open_matches(f.person).values_list("opportunity_id", flat=True))
    # The person's own picks first, then the rest, each soonest deadline first. The same order on the
    # letter page, in the email, and in the composer (MW 2026-11-10).
    featured = sorted(
        (
            row(o, why=_why_for(f.person, o), today=today)
            for o in f.opportunities.filter(archived_at__isnull=True)
        ),
        key=lambda r: (r["o"].pk not in mine, *_sort_key(r["o"])),
    )
    resub = GrantSubmission.objects.filter(resubmission_of=g, archived_at__isnull=True).first()
    return {
        "f": f,
        "name": f.name,
        "first": f.person.first_name,
        "opening": f.opening or default_opening(f),
        "note": f.body_note,
        "closing": f.closing,
        "signoff": f.signoff or SIGNOFF,
        "featured": featured,
        "cofund": wants_cofunding(g),
        "cofund_item": FundingOpportunity.objects.active().filter(tracker_id="cofund").first(),
        "talked_to_po": g.discussed_with_program_officer,
        "resub": resub,
        "supports": nudges.SUPPORTS,
        "news": news(3),
        "all_news": news(),
        "questions": questions(),
    }


def _why_for(person, o):
    m = FundingMatch.objects.filter(person=person, opportunity=o, ended_at__isnull=True).first()
    return m.why if m else ""


def recipients(f):
    to = f.person.primary_email
    cc = [
        d.delegate.primary_email
        for d in OutcomeDelegate.objects.filter(
            owner=f.person, ended_at__isnull=True
        ).select_related("delegate")
        if d.delegate.primary_email
    ]
    return to, cc


def letter_url(f, for_email=True):
    path = reverse("portal:funding_letter", args=[f.pk])
    to, _ = recipients(f)
    if for_email and to and signin.may_use_link(f.person):
        return signin.make_link(f.person, to, purpose="funding_letter", next_path=path)
    return f"{settings.SITE_URL}{path}"


def render_email(f, url=None):
    ctx = {
        **letter_parts(f),
        "url": url or f"{settings.SITE_URL}{reverse('portal:funding_letter', args=[f.pk])}",
    }
    ctx["table"] = ctx["featured"][:3]
    ctx["with_link"] = bool(url) and "/accounts/link/" in (url or "")
    ctx["days"] = signin.LINK_DAYS
    ctx["site"] = settings.SITE_URL
    return (
        ctx["name"][:200],
        render_to_string("email/funding_letter.txt", ctx),
        render_to_string("email/funding_letter.html", ctx),
    )


class AlreadySent(Exception):
    pass


def send(f, user):
    """MW pressed Send and confirmed. One email to the person, copied to anyone entering for them."""
    with transaction.atomic():
        f = FundingFollowUp.objects.select_for_update().get(pk=f.pk)
        if f.status == FundingFollowUp.Status.SENT:
            raise AlreadySent
        to, cc = recipients(f)
        if not to:
            raise ValueError("The person has no email address on file.")
        subject, text, html = render_email(f, url=letter_url(f))
        msg = EmailMultiAlternatives(
            subject=subject, body=text, from_email=settings.DEFAULT_FROM_EMAIL, to=[to], cc=cc
        )
        msg.attach_alternative(html, "text/html")
        msg.send(fail_silently=False)
        f.status = FundingFollowUp.Status.SENT
        f.sent_at = timezone.now()
        f.sent_by = user
        f.sent_to = ", ".join([to, *cc])
        f.save(update_fields=["status", "sent_at", "sent_by", "sent_to", "updated_at"])
        record_event(user, AuditLog.Action.UPDATE, f, new={"status": "sent", "to": f.sent_to})
    return f


# ---------------------------------------------------------------------------
# Counts for MW's dashboard
# ---------------------------------------------------------------------------


def counts():
    return {
        "followups": FundingFollowUp.objects.filter(
            status=FundingFollowUp.Status.TO_REVIEW
        ).count(),
        "suggestions": FundingSuggestion.objects.filter(
            status=FundingSuggestion.Status.TO_REVIEW
        ).count(),
    }


def stale(o, today=None):
    today = today or timezone.localdate()
    return not o.checked_on or (today - o.checked_on).days > STALE_DAYS


def search(q):
    return Q(name__icontains=q) | Q(sponsor__icontains=q)
