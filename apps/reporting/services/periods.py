"""
Reporting-period lifecycle (Milestone 5; snapshots in Milestone 8):

    draft (review before launch) -> open -> closed -> results generated
    -> reviewed -> finalized

Launching generates assignments; nothing is sent while a period is a draft.
"""

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog, record_event
from apps.common.enums import PeriodStatus

from . import assignments

STAGES = [
    ("draft", "Review before launch"),
    ("open", "Open"),
    ("closed", "Closed"),
    ("generated", "Results generated"),
    ("reviewed", "Reviewed"),
    ("finalized", "Finalized"),
]


class PeriodError(ValueError):
    pass


def stage(period):
    """Where the period is in the six-step lifecycle."""
    if period.status in (PeriodStatus.DRAFT, PeriodStatus.OPEN):
        return period.status
    if period.status == PeriodStatus.FINALIZED:
        return "finalized"
    snap = (
        period.snapshots.order_by("-version_no").first() if hasattr(period, "snapshots") else None
    )
    if not snap:
        return "closed"
    return "reviewed" if snap.status == "reviewed" else "generated"


@transaction.atomic
def launch(actor, period):
    if period.status != PeriodStatus.DRAFT:
        raise PeriodError("Only a period under review can be launched.")
    result = assignments.generate(period, actor)
    period.status = PeriodStatus.OPEN
    period.save(update_fields=["status", "updated_at"])
    record_event(
        actor,
        AuditLog.Action.STATUS_CHANGE,
        period,
        new={"status": "open", "assignments": result.created},
    )
    return result


@transaction.atomic
def close(actor, period):
    if period.status != PeriodStatus.OPEN:
        raise PeriodError("Only an open period can be closed.")
    period.status = PeriodStatus.CLOSED
    period.closed_at = timezone.now()
    period.save(update_fields=["status", "closed_at", "updated_at"])
    record_event(actor, AuditLog.Action.STATUS_CHANGE, period, new={"status": "closed"})


@transaction.atomic
def reopen(actor, period, reason=""):
    if period.status != PeriodStatus.CLOSED or period.snapshots.exists():
        raise PeriodError(
            "A period can be reopened only while closed and before results are generated."
        )
    period.status = PeriodStatus.OPEN
    period.closed_at = None
    period.save(update_fields=["status", "closed_at", "updated_at"])
    record_event(
        actor, AuditLog.Action.STATUS_CHANGE, period, new={"status": "open"}, reason=reason
    )
