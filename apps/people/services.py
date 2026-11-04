"""
Changes to people and CNAP relationships, each audited.

Views call these functions rather than saving models directly. The database
still enforces every rule (single holder, no overlapping duplicate, allowed
project kinds); these functions translate a refusal into a sentence an
administrator can act on.
"""

import datetime as dt

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.models import AuditLog, record_event
from apps.common.enums import ContextKind

from .models import Person, PersonEmail, PersonRelationship, RelationshipType

ROSTER_TYPE = "cnap_member"
KSU_INSTITUTION = "Kansas State University"


class RelationshipError(ValueError):
    """A change was refused; str(error) is the sentence to show."""


def _today():
    return timezone.localdate()


# Spellings of K-State that mean "internal" (empty also counts as K-State: the add-person form defaults to it).
KSU_NAMES = {"", "kansas state university", "kansas state", "k-state", "ksu", "kansas state univ"}


def is_external(person):
    """Outside K-State: signs in by emailed link rather than K-State single sign-on."""
    name = " ".join((person.institution or "").replace(".", "").split()).casefold()
    return name not in KSU_NAMES


def current_relationships(person, on=None):
    return person.current_relationships(on).select_related("relationship_type", "project", "core")


def is_on_roster(person, on=None):
    return current_relationships(person, on).filter(relationship_type__code=ROSTER_TYPE).exists()


@transaction.atomic
def create_person(actor, *, first_name, last_name, email="", institution="", **extra):
    first_name, last_name = first_name.strip(), last_name.strip()
    if not first_name or not last_name:
        raise RelationshipError("A person needs a first and last name.")
    email = (email or "").strip()
    if email and PersonEmail.objects.filter(email__iexact=email).exists():
        owner = PersonEmail.objects.get(email__iexact=email).person
        raise RelationshipError(f"{email} already belongs to {owner}.")
    person = Person.objects.create(
        first_name=first_name, last_name=last_name, institution=institution.strip(), **extra
    )
    if email:
        PersonEmail.objects.create(person=person, email=email, is_primary=True)
    record_event(actor, AuditLog.Action.CREATE, person, new={"email": email})
    return person


@transaction.atomic
def add_email(actor, person, email, *, make_primary=False):
    email = email.strip()
    if PersonEmail.objects.filter(email__iexact=email).exists():
        owner = PersonEmail.objects.get(email__iexact=email).person
        raise RelationshipError(f"{email} already belongs to {owner}.")
    if make_primary or not person.emails.exists():
        person.emails.filter(is_primary=True).update(is_primary=False)
        make_primary = True
    row = PersonEmail.objects.create(person=person, email=email, is_primary=make_primary)
    record_event(actor, AuditLog.Action.UPDATE, person, new={"email_added": email})
    return row


@transaction.atomic
def remove_email(actor, person, email_row):
    was_primary = email_row.is_primary
    address = email_row.email
    email_row.delete()
    if was_primary:
        nxt = person.emails.first()
        if nxt:
            nxt.is_primary = True
            nxt.save(update_fields=["is_primary", "updated_at"])
    record_event(actor, AuditLog.Action.UPDATE, person, old={"email_removed": address})


def _explain_integrity(exc, rtype, project=None, core=None, person=None):
    text = str(exc)
    if "single_holder" in text:
        ctx = project or core
        holder = (
            PersonRelationship.objects.filter(
                relationship_type=rtype, project=project, core=core, effective_to__isnull=True
            )
            .select_related("person")
            .first()
        )
        who = f" {holder.person} holds it now." if holder else ""
        return (
            f"{rtype.name} has one holder per {'project' if project else 'core'} "
            f"({ctx}).{who} Use “Pass to someone else” to transfer it."
        )
    if "no_overlapping_duplicate" in text:
        return f"{person} already holds this relationship for overlapping dates."
    if "allowed_project_kind" in text:
        return f"{rtype.name} cannot be attached to a {project.get_kind_display().lower()}."
    return f"The database refused this change: {text.splitlines()[0]}"


@transaction.atomic
def add_relationship(actor, person, rtype, *, project=None, core=None, start=None, notes=""):
    """Give `person` a CNAP relationship. Raises RelationshipError with a readable reason."""
    if isinstance(rtype, str):
        rtype = RelationshipType.objects.get(code=rtype)
    if rtype.context_kind == ContextKind.NONE:
        project = core = None
    rel = PersonRelationship(
        person=person,
        relationship_type=rtype,
        project=project,
        core=core,
        effective_from=start or _today(),
        notes=notes,
        created_by=actor if getattr(actor, "pk", None) else None,
    )
    try:
        rel.clean()
    except ValidationError as exc:
        raise RelationshipError(" ".join(exc.messages)) from exc
    try:
        with transaction.atomic():
            rel.save()
    except IntegrityError as exc:
        raise RelationshipError(_explain_integrity(exc, rtype, project, core, person)) from exc
    record_event(
        actor,
        AuditLog.Action.CREATE,
        rel,
        new={
            "type": rtype.code,
            "project": project.pk if project else None,
            "core": core.pk if core else None,
            "from": str(rel.effective_from),
        },
    )
    return rel


@transaction.atomic
def end_relationship(actor, rel, *, end=None, reason=""):
    """
    End a current relationship. The row stays, with its end date, for history.
    Dates are inclusive: with no date given, the relationship is held through
    yesterday, so it stops counting today (as a handoff does).
    """
    if rel.effective_to is not None:
        raise RelationshipError("This relationship has already ended.")
    end = end or (_today() - dt.timedelta(days=1))
    if end < rel.effective_from:
        end = rel.effective_from
    rel.effective_to = end
    rel.save(update_fields=["effective_to", "updated_at"])
    record_event(actor, AuditLog.Action.UPDATE, rel, new={"ended": str(end)}, reason=reason)
    return rel


@transaction.atomic
def hand_off(actor, rel, new_person, *, start=None, reason=""):
    """
    Transfer a relationship (typically a single-holder one, such as Research
    Project Leader, or a core directorship) to `new_person` from `start`.
    The current holder's row ends the day before. Assignments already issued
    stay with the person who received them.
    """
    if rel.effective_to is not None:
        raise RelationshipError("Only a current relationship can be handed off.")
    if new_person.pk == rel.person_id:
        raise RelationshipError("Choose a different person to hand off to.")
    start = start or _today()
    if start <= rel.effective_from:
        raise RelationshipError(
            f"The handoff date must be after {rel.effective_from:%b %-d, %Y}, "
            "when the current holder started."
        )
    rel.effective_to = start - dt.timedelta(days=1)
    rel.save(update_fields=["effective_to", "updated_at"])
    new_rel = add_relationship(
        actor,
        new_person,
        rel.relationship_type,
        project=rel.project,
        core=rel.core,
        start=start,
        notes=f"Handed off from {rel.person}.",
    )
    record_event(
        actor,
        AuditLog.Action.UPDATE,
        rel,
        new={"handed_off_to": new_person.pk, "on": str(start)},
        reason=reason,
    )
    return new_rel


def add_to_roster(actor, person, *, start=None):
    if is_on_roster(person):
        raise RelationshipError(f"{person} is already on the CNAP roster.")
    return add_relationship(actor, person, ROSTER_TYPE, start=start)


def remove_from_roster(actor, person, *, end=None, reason=""):
    rel = current_relationships(person).filter(relationship_type__code=ROSTER_TYPE).first()
    if not rel:
        raise RelationshipError(f"{person} is not on the CNAP roster.")
    return end_relationship(actor, rel, end=end, reason=reason)


SENIOR_KEY_TYPES = ("pd_pi", "project_leader", "pilot_awardee", "core_director")


NOA_DEFAULT_TYPES = ("pd_pi", "project_leader")


def is_senior_key(person):
    """Named on the Notice of Award? The evaluator's setting, or by default the PD/PI and RP Leaders (FY27 guidance)."""
    if person.senior_key is not None:
        return person.senior_key
    return (
        current_relationships(person).filter(relationship_type__code__in=NOA_DEFAULT_TYPES).exists()
    )


def normalize_orcid(raw):
    """Return an ORCID iD as 0000-0000-0000-000X, or "" for blank. Raise ValueError if it isn't valid.

    Accepts the bare iD or the orcid.org link. Checks the ISO 7064 MOD 11-2 check digit, so a mistyped
    digit is caught here rather than in SciENcv.
    """
    import re

    s = (raw or "").strip()
    if not s:
        return ""
    s = re.sub(r"^(https?://)?(www\.)?orcid\.org/", "", s, flags=re.I).strip("/ ")
    digits = s.replace("-", "").replace(" ", "").upper()
    if not re.fullmatch(r"\d{15}[\dX]", digits):
        raise ValueError("An ORCID iD has 16 digits, like 0000-0002-1825-0097.")
    total = 0
    for ch in digits[:15]:
        total = (total + int(ch)) * 2
    check = (12 - total % 11) % 11
    if digits[15] != ("X" if check == 10 else str(check)):
        raise ValueError("That ORCID iD has a typo: its last digit doesn’t match. Please check it.")
    return "-".join(digits[i : i + 4] for i in range(0, 16, 4))


NIH_DOC_TYPES = ("pd_pi", "project_leader", "pilot_awardee", "core_director")


def is_osc_only(person, on=None):
    """An Other Significant Contributor who holds none of the roles that give a full NIH documents task
    (MW 2026-11-02): they give a biosketch only."""
    from django.db.models import Q
    from django.utils import timezone

    on = on or timezone.localdate()
    codes = set(
        person.relationships.filter(effective_from__lte=on)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=on))
        .values_list("relationship_type__code", flat=True)
    )
    return "osc" in codes and not codes & set(NIH_DOC_TYPES)


def normalize_rrid(raw):
    """Return a core's RRID as RRID:SCR_012345, or "" for blank. Raise ValueError if it isn't one.

    Accepts the bare SCR_ number, "RRID: SCR_…", or a SciCrunch / rrid.site link. Cores are registered as
    SCR_ resources, so other RRID kinds (antibodies, cell lines) are refused here."""
    import re

    s = (raw or "").strip()
    if not s:
        return ""
    m = re.search(r"(?<![A-Z0-9])SCR[_ -]?(\d{4,9})(?!\d)", s, flags=re.I)
    if not m:
        raise ValueError(
            "A core’s RRID looks like RRID:SCR_012345. Find it by searching the core’s name at scicrunch.org/resources."
        )
    return "RRID:SCR_" + m.group(1)


@transaction.atomic
def update_person(actor, person, **fields):
    old = {k: getattr(person, k) for k in fields}
    for k, v in fields.items():
        setattr(person, k, v.strip() if isinstance(v, str) else v)
    person.save()
    changed = {k: getattr(person, k) for k in fields if old[k] != getattr(person, k)}
    if changed:
        record_event(
            actor,
            AuditLog.Action.UPDATE,
            person,
            old={k: old[k] for k in changed},
            new=changed,
        )
    return person


_KEEP = object()


def set_effort(actor, person, grant_year, months, academic=_KEEP, summer=_KEEP):
    """Record person months for one budget year: calendar months, or academic and summer months.

    Fields not passed are left as they are (the Profile only sends calendar months). Blank values clear a
    field; when all three are blank the year is removed.
    """
    from decimal import Decimal, InvalidOperation

    from .models import PersonEffort

    def parse(raw, label, top):
        raw = (str(raw) if raw is not None else "").strip()
        if not raw:
            return None
        try:
            m = Decimal(raw).quantize(Decimal("0.1"))
        except InvalidOperation as exc:
            raise ValueError(f"{label} needs a number, like 1.2.") from exc
        if not (0 <= m <= top):
            raise ValueError(f"{label} must be between 0 and {top}.")
        return m

    row = PersonEffort.objects.filter(person=person, grant_year=grant_year).first()
    vals = {
        "calendar_months": parse(months, "Calendar months", 12),
        "academic_months": parse(academic, "Academic months", 9)
        if academic is not _KEEP
        else (row.academic_months if row else None),
        "summer_months": parse(summer, "Summer months", 3)
        if summer is not _KEEP
        else (row.summer_months if row else None),
    }
    if all(v is None for v in vals.values()):
        PersonEffort.objects.filter(person=person, grant_year=grant_year).delete()
        record_event(actor, AuditLog.Action.UPDATE, person, new={f"effort_Y{grant_year}": None})
        return None
    row, _ = PersonEffort.objects.update_or_create(
        person=person, grant_year=grant_year, defaults=vals | {"entered_by": actor}
    )
    record_event(
        actor,
        AuditLog.Action.UPDATE,
        person,
        new={
            f"effort_Y{grant_year}": {
                k: (str(v) if v is not None else None) for k, v in vals.items()
            }
        },
    )
    return row


def request_commons_help(actor, person, kind):
    """The person asked for help with eRA Commons: note it and email the evaluator(s)."""
    from django.conf import settings
    from django.core.mail import send_mail
    from django.utils import timezone

    from apps.accounts.models import ApplicationRole, User

    kind = kind if kind in ("setup", "unsure") else "unsure"
    person.era_commons_help_requested_at = timezone.now()
    person.era_commons_help_kind = kind
    person.save(update_fields=["era_commons_help_requested_at", "era_commons_help_kind"])
    record_event(actor, AuditLog.Action.UPDATE, person, new={"era_commons_help": kind})
    admins = User.objects.filter(
        user_roles__role__code=ApplicationRole.Code.ADMINISTRATOR, is_enabled=True
    ).select_related("person")
    emails = sorted(
        {u.person.primary_email for u in admins if u.person_id and u.person.primary_email}
    )
    if emails:
        what = (
            "needs help setting up an eRA Commons account"
            if kind == "setup"
            else "isn’t sure whether they need an eRA Commons account"
        )
        send_mail(
            subject=f"CNAP Reporting Hub: eRA Commons help for {person.full_name}",
            message=(
                f"{person.full_name} ({person.primary_email or 'no email on file'}) {what}.\n\n"
                f"Person page: {getattr(settings, 'SITE_URL', '').rstrip('/')}/manage/people/{person.pk}/"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=emails,
            fail_silently=True,
        )
    return len(emails)
