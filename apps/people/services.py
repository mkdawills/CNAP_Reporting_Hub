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


def is_external(person):
    """Outside K-State: signs in by emailed link rather than K-State single sign-on."""
    return (person.institution or "").strip() not in ("", KSU_INSTITUTION, "K-State")


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
            f"({ctx}).{who} Use Hand off to transfer it."
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
