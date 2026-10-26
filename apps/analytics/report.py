"""
One form's results for one period, laid out like the Center's site-visit reports
(decisions.md, 2026-10-25):

  intro sentence
  Table n.   <section>: items x Mean (SD), count and % per answer, Total; grand mean; counts row
  Table n+1. mean ratings by reporting period (prior years + this platform), heat-shaded
  themes and verbatim responses by prompt (administrators only)

`audience` is "admin" (every item, full counts) or "respondent" (Center results:
items with fewer than SMALL_N_THRESHOLD numeric answers are left out, no codes,
no verbatims).
"""

import math
import re
from collections import defaultdict

from django.conf import settings

from apps.common.enums import AssignmentStatus, QuestionType, SnapshotStatus
from apps.forms_engine.models import Measure
from apps.forms_engine.runtime import FormSchema
from apps.reporting.models import Answer, ReportingPeriod

from .models import ReportingSnapshot, SnapshotNote, SnapshotResult
from .results import completion, full_responses


def heat(pct, top=100.0):
    """Background for a heat-shaded cell: darker green for higher values."""
    if pct is None:
        return ""
    a = max(0.0, min(1.0, pct / top))
    if a <= 0:
        return ""
    return f"background:rgba(44,122,104,{0.08 + a * 0.55:.2f})"


def heat_var(style):
    """The same shade as a CSS custom property, so the counts can take it in 'n only' view."""
    return style.replace("background:", "--h:") if style else ""


def heat_mean(mean, lo=1.0, hi=5.0):
    if mean is None:
        return ""
    a = max(0.0, min(1.0, (mean - lo) / (hi - lo)))
    return f"background:rgba(44,122,104,{0.06 + a * 0.5:.2f})"


def heat_rel(mean, lo, hi):
    """Year-over-year shading stretched across the table's own range (Excel-style color scale)."""
    if mean is None:
        return ""
    a = 0.5 if hi <= lo else max(0.0, min(1.0, (mean - lo) / (hi - lo)))
    css = f"background:rgba(31,104,87,{0.04 + a * 0.86:.2f})"
    return css + (";color:#fff" if a > 0.62 else "")


def _restyle(lon):
    vals = [c["mean"] for r in lon["rows"] for c in r["cells"] if c["mean"] is not None]
    vals += [c["mean"] for c in lon["overall"] if c["mean"] is not None]
    if not vals:
        return
    lo, hi = min(vals), max(vals)
    for c in [c for r in lon["rows"] for c in r["cells"]] + lon["overall"]:
        c["style"] = heat_rel(c["mean"], lo, hi)


SEGMENT_COLORS = {
    5: ["#b2432f", "#e8a38c", "#a9a9ad", "#7db5a4", "#1f6857"],
    4: ["#b2432f", "#e8a38c", "#7db5a4", "#1f6857"],
    3: ["#b2432f", "#a9a9ad", "#1f6857"],
}


def _glance(scale, totals, total, mean):
    """Summary for reading in one look: mean in words, top-two and bottom-two shares, one stacked bar."""
    if not total:
        return None
    k = len(scale)
    colors = SEGMENT_COLORS.get(k) or ["#7db5a4"] * k
    segs = []
    for s, c, col in zip(scale, totals, colors, strict=False):
        pct = 100 * c / total
        segs.append(
            {
                "text": s["text"],
                "pct": round(pct),
                "w": f"{pct:.2f}",
                "color": col,
                "dark": col in ("#b2432f", "#1f6857"),
                "inside": pct >= 7,
            }
        )
    top_pct = max(float(sg["w"]) for sg in segs) or 1
    for sg in segs:
        sg["h"] = f"{100 * float(sg['w']) / top_pct:.2f}"
    two = 2 if k >= 4 else 1
    word = (
        scale[min(k - 1, max(0, math.floor(mean + 0.5) - int(scale[0]["value"])))]["text"]
        if mean is not None
        else ""
    )
    return {
        "segments": segs,
        "word": word,
        "top_pct": round(100 * sum(totals[-two:]) / total),
        "top_label": " or ".join(s["text"] for s in scale[-two:]),
        "bot_pct": round(100 * sum(totals[:two]) / total),
        "bot_label": " or ".join(s["text"] for s in scale[:two]),
    }


def _sd(vals):
    if len(vals) < 2:
        return 0.0
    m = sum(vals) / len(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))


def _scale(question):
    pts = [
        o for o in question.answer_set.options.all() if not o.is_na_option and o.value is not None
    ]
    pts.sort(key=lambda o: o.value)
    out = []
    for o in pts:
        num, _, text = o.label.partition(" - ")
        out.append(
            {"value": o.value, "num": num if text else str(o.value), "text": text or o.label}
        )
    return out


def _period_means(form_definition, measure_ids, upto):
    """{period: {measure_id: mean}} from imported aggregates and finalized platform snapshots."""
    periods = list(
        ReportingPeriod.objects.filter(display_order__lte=upto.display_order).order_by(
            "display_order"
        )
    )
    out = {}
    for p in periods:
        snap = (
            ReportingSnapshot.objects.filter(reporting_period=p, status=SnapshotStatus.FINALIZED)
            .order_by("-version_no")
            .first()
        )
        if not snap:
            continue
        rows = SnapshotResult.objects.filter(
            snapshot=snap,
            metric_code__in=["item_mean", "historical_item_mean"],
            subject_type="measure",
            group_key=form_definition.code,
        )
        vals = {r.subject_id: float(r.value) for r in rows if r.value is not None}
        if vals:
            out[p] = vals
    return out


def build(form_definition, period, *, audience="admin"):
    min_n = settings.SMALL_N_THRESHOLD
    respondent = audience == "respondent"
    comp = completion(form_definition, period)
    responses = full_responses(form_definition, period)
    version = form_definition.active_version
    any_assignment = (
        form_definition.assignments.filter(reporting_period=period)
        .select_related("form_version")
        .first()
    )
    if any_assignment:
        version = any_assignment.form_version
    schema = FormSchema(version)
    optout_q = schema.optout_question
    answers = (
        Answer.objects.filter(response__in=responses)
        .select_related("question", "option")
        .order_by("question__form_section__sort_order", "question__sort_order")
    )
    by_key = defaultdict(list)
    texts = defaultdict(list)
    for a in answers:
        q = a.question
        key = q.measure_id or q.code
        if q.question_type == QuestionType.LIKERT and a.option_id:
            by_key[key].append(a.option.value)  # None for N/A
        elif (
            q.question_type == QuestionType.LONG_TEXT
            and a.value_text
            and not q.config.get("narrative")
        ):
            texts[q.code].append(a.value_text)

    tables, tno = [], 0
    upto_means = None
    for sec in schema.sections:
        qs = [q for q in sec.questions.all() if q.question_type == QuestionType.LIKERT]
        if not qs:
            continue
        scale = _scale(qs[0])
        rows, left_out = [], 0
        for i, q in enumerate(qs, start=1):
            vals = by_key.get(q.measure_id or q.code, [])
            nums = [v for v in vals if v is not None]
            n = len(nums)
            if respondent and n < min_n:
                left_out += 1
                continue
            counts = [sum(1 for v in nums if v == s["value"]) for s in scale]
            rows.append(
                {
                    "no": i,
                    "q": q,
                    "n": n,
                    "na": len(vals) - n,
                    "mean": (sum(nums) / n) if n else None,
                    "sd": _sd(nums),
                    "cells": [
                        {
                            "count": c,
                            "pct": round(100 * c / n) if n else 0,
                            "style": heat(round(100 * c / n) if n else 0),
                        }
                        for c in counts
                    ],
                    "nums": nums,
                }
            )
        all_nums = [v for r in rows for v in r["nums"]]
        total = len(all_nums)
        totals = [sum(r["cells"][j]["count"] for r in rows) for j in range(len(scale))]
        top = max(totals) if totals and max(totals) else 1
        tno += 1
        table = {
            "no": tno,
            "section": sec,
            "scale": scale,
            "rows": rows,
            "left_out": left_out,
            "grand_mean": (sum(all_nums) / total) if total else None,
            "grand_sd": _sd(all_nums),
            "scale_top": len(scale),
            "glance": _glance(scale, totals, total, (sum(all_nums) / total) if total else None),
            "total": total,
            "totals": [
                {
                    "count": c,
                    "pct": round(100 * c / total) if total else 0,
                    "style": heat(round(100 * c / total) if total else 0),
                    "bar": round(100 * c / top),
                    "num": sc["num"],
                    "text": sc["text"],
                }
                for c, sc in zip(totals, scale, strict=True)
            ],
            "has_na": any(o.is_na_option for o in qs[0].answer_set.options.all()),
        }
        # Year over year: prior periods (imported or finalized) plus this period live.
        measure_ids = [q.measure_id for q in qs if q.measure_id]
        if upto_means is None:
            upto_means = _period_means(form_definition, measure_ids, period)
        cols = [
            p
            for p in upto_means
            if p.pk != period.pk and any(m in upto_means[p] for m in measure_ids)
        ]
        retired = []
        if not respondent:
            hist_ids = {m for p in cols for m in upto_means[p]}
            retired = list(
                Measure.objects.filter(
                    pk__in=hist_ids - set(measure_ids), scale_kind=qs[0].scale_kind, is_active=False
                )
            )
        if cols or rows:
            live = {r["q"].measure_id: r["mean"] for r in rows if r["q"].measure_id}
            col_objs = cols + [period]
            lon_rows = []
            for r in rows:
                cells = []
                for p in col_objs:
                    m = (
                        live.get(r["q"].measure_id)
                        if p.pk == period.pk
                        else upto_means.get(p, {}).get(r["q"].measure_id)
                    )
                    cells.append(
                        {
                            "mean": m,
                            "style": heat_mean(m, 1, len(scale)),
                            "latest": p.pk == period.pk,
                            "year_start": p.sequence == 1,
                        }
                    )
                lon_rows.append({"no": r["no"], "prompt": r["q"].prompt, "cells": cells})
            for m in retired:
                cells = [
                    {
                        "mean": upto_means.get(p, {}).get(m.pk),
                        "style": heat_mean(upto_means.get(p, {}).get(m.pk), 1, len(scale)),
                        "latest": p.pk == period.pk,
                        "year_start": p.sequence == 1,
                    }
                    for p in col_objs
                ]
                lon_rows.append({"no": "", "prompt": f"{m.name} (no longer asked)", "cells": cells})
            years = []
            for p in col_objs:
                if years and years[-1]["year"] == p.grant_year:
                    years[-1]["span"] += 1
                else:
                    years.append({"year": p.grant_year, "span": 1})
            table["lon"] = {
                "no": tno + 1,
                "periods": col_objs,
                "years": years,
                "rows": lon_rows,
                "overall": [
                    _overall(
                        upto_means.get(p) if p.pk != period.pk else live, measure_ids, len(scale)
                    )
                    for p in col_objs
                ],
            }
            _restyle(table["lon"])
            table["lon"]["trend"] = _trend(table["lon"])
            tno += 1
        tables.append(table)

    verbatims = []
    if not respondent:
        for sec in schema.sections:
            for q in sec.questions.all():
                if (
                    q.question_type == QuestionType.LONG_TEXT
                    and not q.config.get("narrative")
                    and (not schema.followup_section or sec.pk != schema.followup_section.pk)
                ):
                    verbatims.append({"prompt": q.prompt, "answers": texts.get(q.code, [])})
    followups = []
    if not respondent and schema.followup_section:
        fs = schema.followup_section
        optouts = Answer.objects.filter(
            response__assignment__form_definition=form_definition,
            response__assignment__reporting_period=period,
            response__assignment__status=AssignmentStatus.COMPLETED_OPT_OUT,
            response__is_current=True,
            question__form_section__code=fs.code,
        ).select_related("question", "option")
        agg = defaultdict(lambda: defaultdict(int))
        reasons = []
        for a in optouts:
            if a.option_id:
                agg[a.question.prompt][a.option.label] += 1
            elif a.value_text:
                reasons.append(a.value_text)
        followups = {
            "title": fs.title,
            "counts": {k: dict(v) for k, v in agg.items()},
            "texts": reasons,
        }

    snap = (
        period.snapshots.order_by("-version_no").first() if hasattr(period, "snapshots") else None
    )
    themes = None
    if snap:
        note = SnapshotNote.objects.filter(
            snapshot=snap, kind="theme_summary", section_ref=form_definition.code
        ).first()
        themes = note.body if note else ""
    opened = comp["complete"]
    pw = schema.optout_pathway
    return {
        "fd": form_definition,
        "period": period,
        "completion": comp,
        "opened": opened,
        "opted_out": comp["opted_out"],
        "optout_label": optout_q.prompt.rstrip(".") if optout_q else "",
        "full": comp["submitted"],
        "optout_name": (lambda n: n[:1].lower() + n[1:])(re.sub(r"\s*\(.*\)$", "", pw.name))
        if pw
        else "",
        "tables": tables,
        "verbatims": verbatims,
        "followups": followups,
        "snapshot": snap,
        "themes": themes,
        "min_n": min_n,
        "is_report": form_definition.category == "report",
    }


def _trend(lon, w=640, h=170, pad_l=34, pad_r=16, pad_t=22, pad_b=34):
    """Overall-mean line (SVG coordinates) plus call-outs: biggest gain, biggest drop, lowest item now."""
    pts = [(p, c["mean"]) for p, c in zip(lon["periods"], lon["overall"], strict=True)]
    vals = [m for _, m in pts if m is not None]
    if not vals:
        return None
    lo, hi = min(vals), max(vals)
    lo, hi = (lo - 0.25, hi + 0.25) if hi - lo >= 0.2 else (lo - 0.5, hi + 0.5)
    step = (w - pad_l - pad_r) / max(1, len(pts) - 1)

    def y(m):
        return pad_t + (hi - m) / (hi - lo) * (h - pad_t - pad_b)

    points = []
    for i, (p, m) in enumerate(pts):
        x = pad_l + i * step if len(pts) > 1 else w / 2
        points.append(
            {
                "x": round(x, 1),
                "y": round(y(m), 1) if m is not None else None,
                "mean": m,
                "label": p.short_label,
                "latest": i == len(pts) - 1,
            }
        )
    path = " ".join(f"{pt['x']},{pt['y']}" for pt in points if pt["y"] is not None)
    grid = []
    g = math.ceil(lo * 2) / 2
    while g <= hi:
        grid.append({"y": round(y(g), 1), "v": f"{g:.1f}"})
        g += 0.5
    # Call-outs compare the last two columns, current items only (retired rows have no number).
    gain = drop = low = None
    if len(lon["periods"]) >= 2:
        prev_label = lon["periods"][-2].short_label
        deltas = []
        for r in lon["rows"]:
            if not r["no"]:
                continue
            a, b = r["cells"][-2]["mean"], r["cells"][-1]["mean"]
            if a is not None and b is not None:
                deltas.append((round(b - a, 1), r["prompt"]))
        if deltas:
            up = max(deltas)
            dn = min(deltas)
            gain = {"d": up[0], "prompt": up[1], "since": prev_label} if up[0] > 0 else None
            drop = {"d": dn[0], "prompt": dn[1], "since": prev_label} if dn[0] < 0 else None
    now = [
        (r["cells"][-1]["mean"], r["prompt"])
        for r in lon["rows"]
        if r["no"] and r["cells"][-1]["mean"] is not None
    ]
    if now:
        m, prompt = min(now)
        low = {"mean": m, "prompt": prompt}
    return {
        "w": w,
        "h": h,
        "points": points,
        "path": path,
        "grid": grid,
        "base": h - pad_b,
        "pad_l": pad_l,
        "right": w - pad_r,
        "gain": gain,
        "drop": drop,
        "low": low,
    }


def _overall(means, measure_ids, top):
    if not means:
        return {"mean": None, "style": ""}
    vals = [means[m] for m in measure_ids if means.get(m) is not None]
    m = sum(vals) / len(vals) if vals else None
    return {"mean": m, "style": heat_mean(m, 1, top)}
