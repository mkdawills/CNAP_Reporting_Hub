"""
Import prior-year item means (manage.py import_aggregates FILE).

The file has one row per item per period:
    form_code, measure_code, measure_name, scale, period, grant_year, sequence, mean, source

Each period becomes a finalized ReportingPeriod (if it doesn't exist) with one
finalized snapshot of kind 'imported_aggregate' and provenance
'aggregate_import'. Means (and the SD where the report gives one) are stored as historical_item_mean
results with no n and no drill-down. Measures not in any current form are created inactive
(retired items). Running the import again updates values in place and removes
imported values the file no longer contains.
"""

import csv
import datetime as dt
from pathlib import Path

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditLog, record_event
from apps.common.enums import (
    PeriodStatus,
    PeriodType,
    Provenance,
    ScaleKind,
    SnapshotKind,
    SnapshotStatus,
)
from apps.forms_engine.models import Measure
from apps.reporting.models import ReportingPeriod

from .models import ReportingSnapshot, SnapshotResult

SCALES = {
    "Quality": ScaleKind.QUALITY,
    "Frequency": ScaleKind.FREQUENCY,
    "Agreement": ScaleKind.AGREEMENT,
}


def _period(label, grant_year, sequence):
    """
    Grant Year N runs June (2015+N) to May (2016+N): Year 6 is June 2022 - May 2023.
    The first semiannual period (Fall) covers June-November and is surveyed in January;
    the second (Spring) covers December-May and is surveyed in May or June.
    The Year 9 site-visit reports called these "Jan" and "May"/"June"; the Center calls them Fall and Spring.
    """
    p = ReportingPeriod.objects.filter(grant_year=grant_year, sequence=sequence).first()
    if p:
        return p
    season = "Fall" if sequence == 1 else "Spring"
    label = f"Y{grant_year} {season}"
    month = 1 if sequence == 1 else 5
    survey_year = 2017 + grant_year
    if sequence == 1:
        start, end = dt.date(survey_year - 1, 6, 1), dt.date(survey_year - 1, 11, 30)
    else:
        start, end = dt.date(survey_year - 1, 12, 1), dt.date(survey_year, 5, 31)
    opens = dt.datetime(survey_year, month, 1, 9, tzinfo=timezone.get_current_timezone())
    return ReportingPeriod.objects.create(
        name=f"Year {grant_year} {season}",
        short_label=label,
        period_type=PeriodType.SEMIANNUAL,
        grant_year=grant_year,
        sequence=sequence,
        start_date=start,
        end_date=end,
        opens_at=opens,
        due_at=opens + dt.timedelta(days=21),
        status=PeriodStatus.FINALIZED,
        closed_at=opens + dt.timedelta(days=30),
        finalized_at=opens + dt.timedelta(days=45),
        notes="Historical period: imported item means only (no responses).",
    )


@transaction.atomic
def import_file(path, actor=None):
    rows = list(csv.DictReader(Path(path).open()))
    snaps, n, kept = {}, 0, {}
    for r in rows:
        key = (int(r["grant_year"]), int(r["sequence"]))
        if key not in snaps:
            period = _period(r["period"], *key)
            snap = period.snapshots.filter(kind=SnapshotKind.IMPORTED_AGGREGATE).first()
            if not snap:
                last = period.snapshots.order_by("-version_no").first()
                snap = ReportingSnapshot.objects.create(
                    reporting_period=period,
                    version_no=(last.version_no + 1) if last else 1,
                    kind=SnapshotKind.IMPORTED_AGGREGATE,
                    status=SnapshotStatus.FINALIZED,
                    provenance=Provenance.AGGREGATE_IMPORT,
                    finalized_at=timezone.now(),
                    definitions={"source": Path(path).name},
                )
            snaps[key] = snap
        scale = SCALES[r["scale"]]
        measure, created = Measure.objects.get_or_create(
            code=r["measure_code"],
            defaults={
                "name": r["measure_name"][:255],
                "scale_kind": scale,
                "is_active": "retired" not in r["measure_code"],
            },
        )
        SnapshotResult.objects.update_or_create(
            snapshot=snaps[key],
            metric_code="historical_item_mean",
            subject_type="measure",
            subject_id=measure.pk,
            group_key=r["form_code"],
            defaults={
                "value": float(r["mean"]),
                "n": None,
                "detail": {
                    "prompt": r["measure_name"],
                    "source": r["source"],
                    "sd": float(r["sd"]) if r.get("sd") not in (None, "") else None,
                },
                "is_confidential": r["form_code"] in ("mentee_survey", "mentor_questionnaire"),
            },
        )
        n += 1
        kept.setdefault(snaps[key].pk, set()).add((r["form_code"], measure.pk))
    # The file is the whole truth for imported periods: drop rows it no longer contains.
    removed = 0
    for snap_pk, keep in kept.items():
        for res in SnapshotResult.objects.filter(
            snapshot_id=snap_pk, metric_code="historical_item_mean"
        ):
            if (res.group_key, res.subject_id) not in keep:
                res.delete()
                removed += 1
    record_event(
        actor,
        AuditLog.Action.IMPORT,
        "analytics.historical_aggregates",
        new={"values": n, "periods": len(snaps), "removed": removed, "file": Path(path).name},
    )
    return n, len(snaps)


def import_overall(path, actor=None):
    """Prior-year section overall means and SDs as printed in the site-visit reports ("Overall Means" rows).
    Only the reports' own overall SDs: they can't be rebuilt from item SDs without each period's n."""
    rows = list(csv.DictReader(Path(path).open()))
    n = 0
    for r in rows:
        period = _period(r["period"], int(r["grant_year"]), int(r["sequence"]))
        snap = period.snapshots.filter(kind=SnapshotKind.IMPORTED_AGGREGATE).first()
        if not snap:
            continue  # item means come first (import_file); overall rows only add to those periods
        SnapshotResult.objects.update_or_create(
            snapshot=snap,
            metric_code="historical_section_overall",
            subject_type="section",
            subject_id=0,
            group_key=f"{r['form_code']}|{r['section_code']}",
            defaults={
                "value": float(r["mean"]),
                "n": None,
                "detail": {"sd": float(r["sd"]) if r.get("sd") else None, "source": r["source"]},
                "is_confidential": False,
            },
        )
        n += 1
    record_event(
        actor,
        AuditLog.Action.IMPORT,
        "analytics.historical_overall",
        new={"values": n, "file": Path(path).name},
    )
    return n
