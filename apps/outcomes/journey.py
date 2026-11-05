"""
Progress tracks for papers and grant proposals, and the CNAP people involved in each
(prototype screen 5, MW 2026-11-05).

Everything here reads data the Hub already keeps (status history, resubmission links, grant
families, people links). Writes touch only the existing people link tables, and only from the
prototype screen. Who may see or change an item is unchanged: the people linked to it and the
people they have asked to enter for them (services.can_act_for).
"""

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.common.enums import GrantRole, GrantStatus, PublicationStatus

from . import services as os
from .models import GrantSubmission, GrantSubmissionPerson, Publication, PublicationPerson

FINAL = {
    "pub": [(PublicationStatus.PUBLISHED, "Published"), (PublicationStatus.DECLINED, "Declined")],
    "grant": [(GrantStatus.AWARDED, "Funded"), (GrantStatus.NOT_FUNDED, "Not funded")],
}
WORDS = {
    "pub": {"planned": "Planned", "submitted": "Submitted", "published": "Published", "declined": "Declined"},
    "grant": {"planned": "Planned", "submitted": "Submitted", "awarded": "Funded", "not_funded": "Not funded"},
}
OPEN = {"planned", "submitted"}


def enabled():
    return bool(getattr(settings, "UI_PROTOTYPE", False))


def _first_dates(obj):
    return {k: timezone.localtime(v).date() for k, v in os.status_dates(obj).items()}


def _stage_date(kind, obj, status, hist):
    """The date a stage was reached: the person's own date when they gave one, else the day it was recorded."""
    if kind == "pub":
        own = {"submitted": obj.submission_date, "published": obj.publication_date}.get(status)
    else:
        own = {
            "submitted": obj.submission_date,
            "awarded": obj.award_notice_date or obj.decision_date,
            "not_funded": obj.decision_date,
        }.get(status)
    return own or hist.get(status)


def track(kind, obj):
    """The three stages of one item: Planned, Submitted, and the outcome reached (or the two still possible)."""
    hist = _first_dates(obj)
    status = obj.status
    order = ["planned", "submitted"]
    stages = []
    for i, s in enumerate(order):
        reached = status == s or order.index(status) > i if status in order else True
        when = _stage_date(kind, obj, s, hist) if reached else None
        if s == "planned" and not when:
            when = None
        planned_for = None
        if s == "planned":
            planned_for = obj.anticipated_submission_month if kind == "pub" else obj.anticipated_submission_date
        stages.append(
            {
                "key": s,
                "word": WORDS[kind][s],
                "state": "now" if status == s else ("done" if reached else "next"),
                "date": when,
                "planned_for": planned_for if s == "planned" else None,
                "day_known": getattr(obj, "anticipated_day_known", False),
                "detail": obj.get_substatus_display() if kind == "pub" and s == "submitted" and obj.substatus else "",
            }
        )
    finals = FINAL[kind]
    reached_final = next((f for f in finals if f[0] == status), None)
    if reached_final:
        stages.append(
            {
                "key": reached_final[0],
                "word": reached_final[1],
                "state": "done good" if reached_final is finals[0] else "done bad",
                "date": _stage_date(kind, obj, reached_final[0], hist),
            }
        )
    else:
        stages.append({"key": "outcome", "word": " or ".join(w for _, w in finals), "state": "next", "date": None})
    return stages


def attempts(kind, obj):
    """Every attempt of the same paper or proposal, oldest first (A0, A1, ... for proposals)."""
    if kind == "grant":
        rows = list(
            GrantSubmission.objects.filter(grant_family_id=obj.grant_family_id, archived_at__isnull=True).order_by(
                "version_no"
            )
        )
        return [{"label": g.version_label, "obj": g, "word": WORDS[kind][g.status], "status": g.status} for g in rows]
    chain = [obj]
    p = obj
    while p.resubmission_of_id:
        p = p.resubmission_of
        chain.insert(0, p)
    p = obj
    while True:
        nxt = Publication.objects.filter(resubmission_of=p, archived_at__isnull=True).first()
        if not nxt:
            break
        chain.append(nxt)
        p = nxt
    return [{"label": f"Attempt {i}", "obj": x, "word": WORDS[kind][x.status], "status": x.status} for i, x in enumerate(chain, 1)]


def involved(kind, obj):
    """CNAP people linked to the item, the person who entered it first."""
    if kind == "grant":
        links = obj.people.select_related("person").order_by("-is_primary_cnap_contact", "pk")
        return [
            {
                "link": x,
                "person": x.person,
                "role": x.role_other if x.role == GrantRole.OTHER and x.role_other else x.get_role_display(),
                "lead": i == 0,
            }
            for i, x in enumerate(links)
        ]
    links = obj.people.select_related("person").order_by("author_order", "pk")
    return [
        {"link": x, "person": x.person, "role": x.author_role or ("Author" if i == 0 else "Co-author"), "lead": i == 0}
        for i, x in enumerate(links)
    ]


def card(kind, obj, review=False):
    return {
        "kind": kind,
        "obj": obj,
        "title": obj.title if kind == "pub" else obj.project_title,
        "sub": (obj.journal if kind == "pub" else " ".join(x for x in (obj.funding_agency, obj.mechanism) if x)),
        "stages": track(kind, obj),
        "attempts": attempts(kind, obj),
        "people": involved(kind, obj),
        "ids": {x.person_id for x in obj.people.all()},
        "open": obj.status in OPEN,
        "review": review,
    }


def acting_person(user, obj):
    """Whose role a save records (MW 2026-11-05, option A): the person filling in the form when they
    are on the item; otherwise the person on it they enter for; never someone else by default."""
    me = getattr(user, "person", None)
    linked = [x.person for x in obj.people.select_related("person")]
    if me and any(p.pk == me.pk for p in linked):
        return me
    for p in linked:
        if os.can_act_for(user, p):
            return p
    return None


ROLE_CHOICES = [(r.value, r.label) for r in GrantRole]


@transaction.atomic
def add_person(kind, obj, person, role="", role_other=""):
    """Link one more CNAP person to the item. Returns False when they are already linked."""
    if obj.people.filter(person=person).exists():
        return False
    if kind == "grant":
        role = role if role in dict(ROLE_CHOICES) else GrantRole.CO_I
        GrantSubmissionPerson.objects.create(
            grant_submission=obj, person=person, role=role, role_other=role_other if role == GrantRole.OTHER else ""
        )
    else:
        last = obj.people.order_by("-author_order").first()
        PublicationPerson.objects.create(
            publication=obj, person=person, author_order=(last.author_order + 1) if last else 0, author_role="Co-author"
        )
    return True


@transaction.atomic
def remove_person(kind, obj, person):
    """Unlink a person. The first person (who entered it) always stays, so an item never has no one."""
    first = involved(kind, obj)[0]["person"] if obj.people.exists() else None
    if first and first.pk == person.pk:
        return False
    return obj.people.filter(person=person).delete()[0] > 0


def copy_people(kind, src, dst):
    """A resubmission keeps everyone who was involved in the earlier attempt."""
    for row in involved(kind, src):
        if not dst.people.filter(person=row["person"]).exists():
            if kind == "grant":
                add_person(kind, dst, row["person"], row["link"].role, row["link"].role_other)
            else:
                add_person(kind, dst, row["person"])


def notify(kind, obj, actor_user, what, request=None, only=None):
    """Email the other CNAP people involved that something changed, and who changed it.

    `what` is one plain sentence, such as 'changed the status from Submitted to Funded'.
    The person who made the change is never emailed about their own change.
    """
    actor = getattr(actor_user, "person", None)
    name = actor.full_name if actor else actor_user.get_username()
    # Someone entering on another person's behalf is named with that person (MW 2026-11-05).
    behalf = acting_person(actor_user, obj)
    if actor and behalf and behalf.pk != actor.pk:
        name = f"{actor.full_name}, entering for {behalf.full_name},"
    title = obj.title if kind == "pub" else f"{obj.project_title} ({obj.version_label})"
    url = reverse("portal:outcomes")
    if request is not None:
        url = request.build_absolute_uri(url)
    sent = []
    for row in involved(kind, obj):
        p = row["person"]
        if actor and p.pk == actor.pk:
            continue
        if only is not None and p.pk not in only:
            continue
        to = getattr(p, "email", "") or getattr(getattr(p, "user", None), "email", "")
        if not to:
            continue
        send_mail(
            subject=f"Update: {title[:80]}",
            message=(
                f"Hello {p.first_name},\n\n"
                f"{name} {what} for “{title}.”\n"
                f"You’re receiving this because you’re listed as one of the CNAP people involved.\n\n"
                f"Please see it here: {url}\n\n"
                "CNAP Reporting Hub"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to],
            fail_silently=True,
        )
        sent.append(to)
    return sent
