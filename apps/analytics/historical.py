"""
Import prior-year item means (manage.py import_aggregates FILE).

The file has one row per item per period:
    form_code, measure_code, measure_name, scale, period, grant_year, sequence, mean, source

Each period becomes a finalized ReportingPeriod (if it doesn't exist) with one
finalized snapshot of kind 'imported_aggregate' and provenance
'aggregate_import'. Means are stored as historical_item_mean results with no n
and no drill-down. Measures not in any current form are created inactive
(retired items). Running the import again updates values in place.
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
MONTHS = {"Jan": (1, "January"), "June": (6, "June"), "May": (5, "May")}


def _period(label, grant_year, sequence):
    """
    Grant Year N runs June (2015+N) to May (2016+N): Year 6 is June 2022 - May 2023.
    The first semiannual period covers June-November and is surveyed in January;
    the second covers December-May and is surveyed in May or June.
    """
    p = ReportingPeriod.objects.filter(grant_year=grant_year, sequence=sequence).first()
    if p:
        return p
    month, month_name = MONTHS.get(label.split()[-1], (6, "June"))
    survey_year = 2017 + grant_year
    if sequence == 1:
        start, end = dt.date(survey_year - 1, 6, 1), dt.date(survey_year - 1, 11, 30)
    else:
        start, end = dt.date(survey_year - 1, 12, 1), dt.date(survey_year, 5, 31)
    opens = dt.datetime(survey_year, month, 1, 9, tzinfo=timezone.get_current_timezone())
    return ReportingPeriod.objects.create(
        name=f"Year {grant_year}, {month_name} {survey_year}",
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
    snaps, n = {}, 0
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
                "detail": {"prompt": r["measure_name"], "source": r["source"]},
                "is_confidential": r["form_code"] in ("mentee_survey", "mentor_questionnaire"),
            },
        )
        n += 1
    record_event(
        actor,
        AuditLog.Action.IMPORT,
        "analytics.historical_aggregates",
        new={"values": n, "periods": len(snaps), "file": Path(path).name},
    )
    return n, len(snaps)
