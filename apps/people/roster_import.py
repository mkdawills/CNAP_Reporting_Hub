"""
Roster import: upload a CSV or Excel list of CNAP members, review every row,
then commit. Nothing changes until the evaluator commits.

Columns (header names are matched loosely, case and spacing ignored):
    first name, last name, email, institution (optional), department (optional),
    position (optional)

Each row is classified:
- matched: the e-mail belongs to an existing person;
- new: no person has the e-mail or the name;
- possible duplicate: no e-mail match, but a person with the same name exists;
- missing: on the roster now, but not in this file.

Default decisions: matched and new rows are accepted (put on the roster);
possible duplicates need a choice (merge into the existing person, create a
new person, or skip); missing people stay on the roster unless the evaluator
chooses to end their membership.
"""

import csv
import io
import re

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog, record_event
from apps.common.enums import ImportMatchKind, ImportStatus
from apps.reporting.models import RosterImport, RosterImportRow

from .models import Person, PersonEmail
from .services import (
    ROSTER_TYPE,
    RelationshipError,
    add_email,
    add_to_roster,
    create_person,
    is_on_roster,
    remove_from_roster,
)

COLUMN_ALIASES = {
    "first_name": {"first", "firstname", "first name", "given name", "given"},
    "last_name": {"last", "lastname", "last name", "surname", "family name"},
    "email": {"email", "e-mail", "email address", "e-mail address", "mail"},
    "institution": {"institution", "university", "organization", "affiliation"},
    "department": {"department", "dept", "unit"},
    "position_title": {"position", "title", "position title", "job title", "role"},
}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RosterFileError(ValueError):
    pass


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "").strip().lower().replace("_", " "))


def _map_header(header):
    mapping = {}
    for i, raw in enumerate(header):
        key = _norm(raw)
        for field, aliases in COLUMN_ALIASES.items():
            if key in aliases and field not in mapping:
                mapping[field] = i
    missing = [f for f in ("first_name", "last_name", "email") if f not in mapping]
    if missing:
        names = ", ".join(m.replace("_", " ") for m in missing)
        raise RosterFileError(
            f"The file needs columns for first name, last name and email. Missing: {names}."
        )
    return mapping


def read_rows(uploaded):
    """Return a list of dicts from a CSV or .xlsx upload."""
    name = (uploaded.name or "").lower()
    data = uploaded.read()
    if name.endswith(".xlsx"):
        from openpyxl import load_workbook

        try:
            wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as exc:  # noqa: BLE001 - any parse failure is a user-facing error
            raise RosterFileError("This Excel file could not be read.") from exc
        rows = [list(r) for r in wb.active.iter_rows(values_only=True)]
    elif name.endswith(".csv"):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
        rows = list(csv.reader(io.StringIO(text)))
    else:
        raise RosterFileError("Upload a .csv or .xlsx file.")
    rows = [r for r in rows if any(str(c or "").strip() for c in r)]
    if len(rows) < 2:
        raise RosterFileError("The file has no rows under the header.")
    mapping = _map_header(rows[0])
    out = []
    for r in rows[1:]:
        rec = {}
        for field, idx in mapping.items():
            rec[field] = str(r[idx] if idx < len(r) and r[idx] is not None else "").strip()
        out.append(rec)
    return out


@transaction.atomic
def parse(actor, uploaded):
    """Create a RosterImport in status 'parsed' with one row per line plus 'missing' rows."""
    records = read_rows(uploaded)
    imp = RosterImport.objects.create(uploaded_by=actor, original_filename=uploaded.name[:255])
    seen_people = set()
    counts = {k.value: 0 for k in ImportMatchKind}
    for n, rec in enumerate(records, start=1):
        email = rec.get("email", "")
        note = ""
        match_kind, matched, decision = ImportMatchKind.NEW, None, "accept"
        if email and not EMAIL_RE.match(email):
            note = "This e-mail does not look valid."
            decision = ""
        row = PersonEmail.objects.filter(email__iexact=email).select_related("person").first()
        if email and row:
            match_kind, matched = ImportMatchKind.MATCHED, row.person
            seen_people.add(row.person_id)
        else:
            same_name = Person.objects.filter(
                first_name__iexact=rec.get("first_name", ""),
                last_name__iexact=rec.get("last_name", ""),
                archived_at__isnull=True,
            ).first()
            if same_name:
                match_kind, matched, decision = ImportMatchKind.POSSIBLE_DUPLICATE, same_name, ""
                note = note or (
                    f"Same name as an existing person ({same_name.primary_email or 'no e-mail'})."
                )
        if not email:
            note = note or "No e-mail: this person could not receive sign-in links."
        counts[match_kind] += 1
        RosterImportRow.objects.create(
            roster_import=imp,
            row_number=n,
            email=email if EMAIL_RE.match(email or "") else "",
            first_name=rec.get("first_name", "")[:100],
            last_name=rec.get("last_name", "")[:100],
            raw=rec,
            match_kind=match_kind,
            matched_person=matched,
            decision=decision,
            note=note[:255],
        )
    on_roster = Person.objects.filter(
        relationships__relationship_type__code=ROSTER_TYPE,
        relationships__effective_to__isnull=True,
        archived_at__isnull=True,
    ).distinct()
    n = len(records)
    for person in on_roster:
        if person.pk in seen_people:
            continue
        n += 1
        counts[ImportMatchKind.MISSING] += 1
        RosterImportRow.objects.create(
            roster_import=imp,
            row_number=n,
            email=person.primary_email,
            first_name=person.first_name,
            last_name=person.last_name,
            match_kind=ImportMatchKind.MISSING,
            matched_person=person,
            decision="keep",
            note="On the roster now, but not in this file.",
        )
    imp.summary = {"counts": counts, "rows": len(records)}
    imp.save(update_fields=["summary", "updated_at"])
    record_event(actor, AuditLog.Action.CREATE, imp, new=imp.summary)
    return imp


VALID_DECISIONS = {
    ImportMatchKind.MATCHED: {"accept", "skip"},
    ImportMatchKind.NEW: {"accept", "skip"},
    ImportMatchKind.POSSIBLE_DUPLICATE: {"merge", "new", "skip"},
    ImportMatchKind.MISSING: {"keep", "end-membership"},
}


def set_decision(row, decision):
    allowed = VALID_DECISIONS[ImportMatchKind(row.match_kind)]
    if decision not in allowed:
        raise RosterFileError(f"Row {row.row_number}: choose one of {', '.join(sorted(allowed))}.")
    row.decision = decision
    row.save(update_fields=["decision"])


def undecided(imp):
    return imp.rows.filter(decision="")


@transaction.atomic
def commit(actor, imp):
    if imp.status != ImportStatus.PARSED:
        raise RosterFileError("This import has already been committed or discarded.")
    if undecided(imp).exists():
        raise RosterFileError("Choose what to do with every flagged row before committing.")
    done = {"added_to_roster": 0, "created": 0, "merged": 0, "ended": 0, "skipped": 0}
    for row in imp.rows.select_related("matched_person"):
        raw = row.raw or {}
        extra = {k: raw.get(k, "") for k in ("department", "position_title") if raw.get(k)}
        if row.decision == "skip" or row.decision == "keep":
            done["skipped"] += row.decision == "skip"
            continue
        if row.decision == "end-membership":
            try:
                remove_from_roster(actor, row.matched_person, reason=f"Roster import {imp.pk}")
                done["ended"] += 1
            except RelationshipError:
                pass
            continue
        person = None
        if row.decision == "accept" and row.matched_person:
            person = row.matched_person
        elif row.decision == "merge":
            person = row.matched_person
            if row.email and not PersonEmail.objects.filter(email__iexact=row.email).exists():
                add_email(actor, person, row.email)
            done["merged"] += 1
        else:  # accept new, or "new" for a possible duplicate
            person = create_person(
                actor,
                first_name=row.first_name,
                last_name=row.last_name,
                email=row.email,
                institution=raw.get("institution", ""),
                **extra,
            )
            done["created"] += 1
        if person and not is_on_roster(person):
            add_to_roster(actor, person)
            done["added_to_roster"] += 1
    imp.status = ImportStatus.COMMITTED
    imp.committed_at = timezone.now()
    imp.committed_by = actor
    imp.summary = {**imp.summary, "result": done}
    imp.save()
    record_event(actor, AuditLog.Action.IMPORT, imp, new=done)
    return done


def discard(actor, imp):
    if imp.status != ImportStatus.PARSED:
        raise RosterFileError("Only an import awaiting review can be discarded.")
    imp.status = ImportStatus.DISCARDED
    imp.save(update_fields=["status", "updated_at"])
    record_event(actor, AuditLog.Action.UPDATE, imp, new={"status": "discarded"})
