"""
Reporting snapshots: what the Center officially reported for a period (Milestone 8).

    closed period -> generate (v1, generated) -> review (reviewed)
    -> finalize (finalized; the period becomes finalized)

A correction after finalizing is an explicit, audited new version: it is
generated, reviewed and finalized like the first, and on finalizing it the
earlier finalized version becomes 'superseded'. Nothing is overwritten.

Stored results (SnapshotResult):
    completion   per form:      n = assigned (not exempt), value = complete %,
                                detail = submitted, opted_out, by pathway
    item_mean    per measure:   n, value = mean, detail = sd, na, counts by value
"""

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog, record_event
from apps.common.enums import PeriodStatus, Provenance, SnapshotKind, SnapshotStatus
from apps.forms_engine.models import FormDefinition

from .metrics import REGISTRY_VERSION
from .models import ReportingSnapshot, SnapshotMember, SnapshotNote, SnapshotResult
from .results import completion, full_responses, item_stats


class SnapshotError(ValueError):
    pass


def latest(period):
    return period.snapshots.order_by("-version_no").first()


def official(period):
    """The finalized snapshot that is currently the record for `period`."""
    return period.snapshots.filter(status=SnapshotStatus.FINALIZED).order_by("-version_no").first()


@transaction.atomic
def generate(actor, period, reason=""):
    if period.status not in (PeriodStatus.CLOSED, PeriodStatus.FINALIZED):
        raise SnapshotError("Close the period before generating results.")
    prev = latest(period)
    if prev and prev.status in (SnapshotStatus.GENERATED, SnapshotStatus.REVIEWED):
        raise SnapshotError("Finish reviewing the current results first.")
    if period.status == PeriodStatus.FINALIZED and not reason.strip():
        raise SnapshotError("A correction needs a reason; it is recorded in the audit log.")
    snap = ReportingSnapshot.objects.create(
        reporting_period=period,
        version_no=(prev.version_no + 1) if prev else 1,
        kind=SnapshotKind.PERIOD_CLOSE,
        generated_by=actor if getattr(actor, "pk", None) else None,
        supersedes=official(period),
        regeneration_reason=reason,
        definitions={"registry_version": REGISTRY_VERSION},
    )
    forms = FormDefinition.objects.filter(assignments__reporting_period=period).distinct()
    versions = {}
    for fd in forms:
        comp = completion(fd, period)
        SnapshotResult.objects.create(
            snapshot=snap,
            metric_code="completion",
            subject_type="form",
            subject_id=fd.pk,
            n=comp["assigned"],
            value=comp["rate"],
            detail={
                k: comp[k]
                for k in (
                    "submitted",
                    "opted_out",
                    "exempt",
                    "in_progress",
                    "not_started",
                    "opt_out_by_pathway",
                )
            },
            is_confidential=fd.is_confidential_mentoring,
        )
        responses = full_responses(fd, period)
        versions[fd.code] = sorted(
            set(responses.values_list("form_version__version_no", flat=True))
        )
        for st in item_stats(fd, period, responses):
            q = st.question
            SnapshotResult.objects.create(
                snapshot=snap,
                metric_code="item_mean",
                subject_type="measure" if q.measure_id else "question",
                subject_id=q.measure_id or q.pk,
                group_key=fd.code,
                n=st.n,
                value=round(st.mean, 4) if st.mean is not None else None,
                detail={
                    "sd": round(st.sd, 4) if st.sd is not None else None,
                    "na": st.na,
                    "counts": {str(k): v for k, v in st.counts.items()},
                    "prompt": q.prompt,
                },
                is_confidential=fd.is_confidential_mentoring,
            )
        SnapshotMember.objects.bulk_create(
            [
                SnapshotMember(snapshot=snap, record_type="response", record_id=r)
                for r in responses.values_list("pk", flat=True)
            ],
            ignore_conflicts=True,
        )
    snap.definitions["form_versions"] = versions
    snap.save(update_fields=["definitions", "updated_at"])
    record_event(
        actor,
        AuditLog.Action.SNAPSHOT,
        snap,
        new={"version": snap.version_no, "status": "generated"},
        reason=reason,
    )
    return snap


@transaction.atomic
def mark_reviewed(actor, snap):
    if snap.status != SnapshotStatus.GENERATED:
        raise SnapshotError("Only newly generated results can be marked reviewed.")
    snap.status = SnapshotStatus.REVIEWED
    snap.save(update_fields=["status", "updated_at"])
    record_event(actor, AuditLog.Action.SNAPSHOT, snap, new={"status": "reviewed"})


@transaction.atomic
def finalize(actor, snap):
    if snap.status != SnapshotStatus.REVIEWED:
        raise SnapshotError("Mark the results reviewed before finalizing.")
    period = snap.reporting_period
    now = timezone.now()
    ReportingSnapshot.objects.filter(
        reporting_period=period, status=SnapshotStatus.FINALIZED
    ).exclude(pk=snap.pk).update(status=SnapshotStatus.SUPERSEDED)
    snap.status = SnapshotStatus.FINALIZED
    snap.finalized_at = now
    snap.finalized_by = actor if getattr(actor, "pk", None) else None
    snap.save(update_fields=["status", "finalized_at", "finalized_by", "updated_at"])
    if period.status != PeriodStatus.FINALIZED:
        period.status = PeriodStatus.FINALIZED
        period.finalized_at = now
        period.save(update_fields=["status", "finalized_at", "updated_at"])
    record_event(
        actor,
        AuditLog.Action.SNAPSHOT,
        snap,
        new={"status": "finalized", "version": snap.version_no},
    )


def set_theme_summary(actor, snap, form_code, body):
    """The evaluator's themes for one instrument in one snapshot (shown above verbatims)."""
    note, _ = SnapshotNote.objects.get_or_create(
        snapshot=snap,
        kind="theme_summary",
        section_ref=form_code,
        defaults={"body": body, "author": actor},
    )
    note.body, note.author = body, actor
    note.save()
    record_event(actor, AuditLog.Action.UPDATE, snap, new={"themes_for": form_code})
    return note


def is_historical(snap):
    return snap.provenance == Provenance.AGGREGATE_IMPORT
