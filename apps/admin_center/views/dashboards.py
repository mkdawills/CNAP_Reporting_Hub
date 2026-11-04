"""
Product dashboards (MW 2026-11-03): live recreations of MW's Publication, Presentations, and
Grants dashboards (Y6-Y9 Word and Excel workbooks). Same tables and graphs, generated from the
Hub's own records, so they are always current. Observations stay the evaluator's to write.
Structure only was taken from MW's files; no names or numbers were copied.
"""

from django.shortcuts import render
from django.utils.safestring import mark_safe

from apps.common.enums import GrantStatus, PresentationType, PublicationStatus
from apps.outcomes.models import GrantSubmission, Presentation, Publication

from ..decorators import admin_view
from .outcomes import grant_year

# Categorical series colors (dataviz reference palette, fixed order), matching MW's own
# blue/orange/green/yellow/magenta dashboards. "No core involved" was magenta in hers too.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#6250d6"]
STATUS = {"awarded": "#0ca30c", "pending": "#eda100", "declined": "#d03b3b"}
INK = "#3a3a48"
MUTED = "#6b6878"
GRID = "#e4e2ea"

NO_CORE = "No core involved"


# --------------------------------------------------------------------------- tiny SVG charts


def _fmt(v, dollars=False):
    if dollars:
        return f"${v:,.0f}"
    return f"{v:,}" if isinstance(v, int) else f"{v:,.0f}"


def _tick(v, dollars=False):
    """Short axis-tick label."""
    if dollars:
        if v >= 1_000_000:
            return f"${v / 1_000_000:.1f}M".replace(".0M", "M")
        if v >= 1_000:
            return f"${v / 1_000:.0f}K"
        return f"${v:,.0f}"
    return f"{v:,.0f}"


BORDER = "#c9c5d4"


def _axis(peak, dollars):
    """The axis top and its tick values: whole-number steps for counts, quarters for dollars."""
    import math

    if dollars:
        return peak, [peak * f for f in (0.25, 0.5, 0.75, 1.0)]
    step = max(1, math.ceil(peak / 4))
    top = step * max(1, math.ceil(peak / step))
    return top, [step * i for i in range(1, top // step + 1)]


def _frame(out, pad_l, pad_t, plot_w, plot_h, peak, ticks, dollars, x_label, y_label, width, height):
    """Horizontal gridlines with y-tick labels, the outer border, and both axis titles."""
    for t in ticks:
        y = pad_t + plot_h * (1 - t / peak)
        out.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{pad_l + plot_w}" y2="{y:.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{pad_l - 7}" y="{y + 3.5:.1f}" text-anchor="end" font-size="10.5" '
            f'fill="{MUTED}">{_tick(t, dollars)}</text>'
        )
    out.append(
        f'<text x="{pad_l - 7}" y="{pad_t + plot_h + 3.5:.1f}" text-anchor="end" '
        f'font-size="10.5" fill="{MUTED}">0</text>'
    )
    out.append(
        f'<rect x="{pad_l}" y="{pad_t}" width="{plot_w:.1f}" height="{plot_h:.1f}" '
        f'fill="none" stroke="{BORDER}" stroke-width="1"/>'
    )
    out.append(
        f'<text x="{pad_l + plot_w / 2:.1f}" y="{height - 6}" text-anchor="middle" '
        f'font-size="11.5" font-weight="600" fill="{INK}">{x_label}</text>'
    )
    out.append(
        f'<text x="13" y="{pad_t + plot_h / 2:.1f}" text-anchor="middle" font-size="11.5" '
        f'font-weight="600" fill="{INK}" '
        f'transform="rotate(-90 13 {pad_t + plot_h / 2:.1f})">{y_label}</text>'
    )


def _dividers(out, pad_l, pad_t, plot_h, group_w, n_cat):
    """Vertical dividing lines between the category groups."""
    for i in range(1, n_cat):
        x = pad_l + i * group_w
        out.append(
            f'<line x1="{x:.1f}" y1="{pad_t}" x2="{x:.1f}" y2="{pad_t + plot_h:.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )


def _trend(out, points):
    """A quiet trend line over the per-category totals."""
    if len(points) < 2:
        return
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(points))
    out.append(
        f'<path d="{path}" fill="none" stroke="{INK}" stroke-width="2" stroke-dasharray="5 4" '
        f'opacity=".65"/>'
    )
    for x, y in points:
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{INK}" opacity=".75"/>')


def grouped_bars(
    categories, series, dollars=False, height=300, x_label="Grant year", y_label="Count",
    trend=False,
):
    """Grouped vertical bars: value on top, the series name written vertically inside each bar,
    y-axis ticks, both axis titles, group dividers, and an outside border."""
    n_cat, n_ser = len(categories), len(series)
    if not n_cat or not n_ser:
        return ""
    pad_l = 74 if dollars else 52
    pad_r = 46 if dollars else 14
    width = max(480, min(880, (160 if dollars else 130) * n_cat + pad_l + pad_r))
    pad_b, pad_t = 48, 24
    plot_w, plot_h = width - pad_l - pad_r, height - pad_b - pad_t
    peak = max((max(s["vals"]) for s in series if s["vals"]), default=0) or 1
    peak, ticks = _axis(peak, dollars)
    group_w = plot_w / n_cat
    bar_w = min(46, (group_w - 18) / n_ser - 2)
    out = [
        f'<svg viewBox="0 0 {width} {height}" role="img" class="dash-svg" '
        f'style="max-width:{width}px">'
    ]
    _frame(out, pad_l, pad_t, plot_w, plot_h, peak, ticks, dollars, x_label, y_label, width, height)
    _dividers(out, pad_l, pad_t, plot_h, group_w, n_cat)
    trend_pts = []
    for i, cat in enumerate(categories):
        gx = pad_l + i * group_w
        total_bars = bar_w * n_ser + 2 * (n_ser - 1)
        x0 = gx + (group_w - total_bars) / 2
        for j, s in enumerate(series):
            v = s["vals"][i]
            h = plot_h * (v / peak)
            x = x0 + j * (bar_w + 2)
            y = pad_t + plot_h - h
            label = f"{cat} · {s['label']}: {_fmt(v, dollars)}"
            out.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{max(h, 1):.1f}" '
                f'rx="3" fill="{s["color"]}"><title>{label}</title></rect>'
            )
            out.append(
                f'<text x="{x + bar_w / 2:.1f}" y="{y - 5:.1f}" text-anchor="middle" '
                f'font-size="11" fill="{INK}">{_fmt(v, dollars)}</text>'
            )
            if h >= 52:  # the series name, written vertically inside the bar
                cx, cy = x + bar_w / 2, y + h / 2
                name = s["label"]
                if len(name) * 6.2 > h - 10:
                    name = name[: max(3, int((h - 14) / 6.2))] + "…"
                out.append(
                    f'<text x="{cx:.1f}" y="{cy:.1f}" text-anchor="middle" font-size="10.5" '
                    f'fill="#fff" transform="rotate(-90 {cx:.1f} {cy:.1f})">{name}</text>'
                )
        if trend:
            tot = sum(s["vals"][i] for s in series)
            trend_pts.append((gx + group_w / 2, pad_t + plot_h - plot_h * (tot / peak)))
        out.append(
            f'<text x="{gx + group_w / 2:.1f}" y="{height - 26}" text-anchor="middle" '
            f'font-size="12" fill="{MUTED}">{cat}</text>'
        )
    if trend:
        _trend(out, trend_pts)
    out.append("</svg>")
    return mark_safe("".join(out))


def stacked_bars(
    categories, series, height=330, x_label="Grant year", y_label="Count", trend=False
):
    """Stacked vertical bars with the same frame: axis ticks and titles, group dividers,
    an outside border, and the series name written inside each segment that has room."""
    n_cat = len(categories)
    if not n_cat or not series:
        return ""
    pad_l, pad_r = 52, 14
    width = max(480, min(880, 150 * n_cat + pad_l + pad_r))
    pad_b, pad_t = 48, 24
    plot_w, plot_h = width - pad_l - pad_r, height - pad_b - pad_t
    totals = [sum(s["vals"][i] for s in series) for i in range(n_cat)]
    peak = max(totals) or 1
    peak, ticks = _axis(peak, False)
    group_w = plot_w / n_cat
    bar_w = min(96, group_w - 44)
    out = [
        f'<svg viewBox="0 0 {width} {height}" role="img" class="dash-svg" '
        f'style="max-width:{width}px">'
    ]
    _frame(out, pad_l, pad_t, plot_w, plot_h, peak, ticks, False, x_label, y_label, width, height)
    _dividers(out, pad_l, pad_t, plot_h, group_w, n_cat)
    trend_pts = []
    for i, cat in enumerate(categories):
        x = pad_l + (i + 0.5) * group_w - bar_w / 2
        y = pad_t + plot_h
        for s in series:
            v = s["vals"][i]
            if not v:
                continue
            h = plot_h * (v / peak)
            y -= h
            label = f"{cat} · {s['label']}: {v:,}"
            out.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
                f'height="{max(h - 2, 1):.1f}" rx="2" fill="{s["color"]}">'
                f"<title>{label}</title></rect>"
            )
            if h >= 18:
                out.append(
                    f'<text x="{x + bar_w / 2:.1f}" y="{y + h / 2 + 3:.1f}" '
                    f'text-anchor="middle" font-size="10.5" fill="#fff">'
                    f"{s['label'][:14]}{'…' if len(s['label']) > 14 else ''}, {v:,}</text>"
                )
        top = pad_t + plot_h - plot_h * (totals[i] / peak)
        trend_pts.append((x + bar_w / 2, top))
        out.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{top - 6:.1f}" '
            f'text-anchor="middle" font-size="11" font-weight="600" fill="{INK}">{totals[i]:,}</text>'
        )
        out.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{height - 26}" text-anchor="middle" '
            f'font-size="12" fill="{MUTED}">{cat}</text>'
        )
    if trend:
        _trend(out, trend_pts)
    out.append("</svg>")
    return mark_safe("".join(out))


def flip(categories, series):
    """Transpose a chart: the old series become the categories, the old categories the series."""
    new_cats = [s["label"] for s in series]
    new_series = [
        {
            "label": cat,
            "vals": [s["vals"][i] for s in series],
            "color": SERIES[i % len(SERIES)],
        }
        for i, cat in enumerate(categories)
    ]
    return new_cats, new_series



def gpair(categories, series, kind="g", flip_x="", **kw):
    """A graph plus, when it has two or more series, the same data with the axes flipped."""
    fn = grouped_bars if kind == "g" else stacked_bars
    out = {"svg": fn(categories, series, **kw), "alt": "", "note": ""}
    if kw.get("trend") and len(categories) < 2:
        out["note"] = "The dashed trend line appears once there are two or more grant years to compare."
    if flip_x and len(series) > 1:
        fc, fs = flip(categories, series)
        kw2 = dict(kw)
        kw2["x_label"] = flip_x
        out["alt"] = fn(fc, fs, **kw2)
    return out


# --------------------------------------------------------------------------- data


def _years(*value_lists):
    ys = sorted({y for vals in value_lists for y in vals if y is not None})
    return ys


def _table(row_labels, per_row_year_counts, years, dollars=False):
    """rows: [{label, vals (one per year), total}] plus a column-total row."""
    rows = []
    for label in row_labels:
        counts = per_row_year_counts.get(label, {})
        vals = [counts.get(y, 0) for y in years]
        rows.append({"label": label, "vals": vals, "total": sum(vals), "dollars": dollars})
    col_totals = [sum(r["vals"][i] for r in rows) for i in range(len(years))]
    return {
        "years": years,
        "rows": rows,
        "col_totals": col_totals,
        "grand": sum(col_totals),
        "dollars": dollars,
    }


def _bump(d, label, year, value=1):
    if year is None:
        return
    d.setdefault(label, {})
    d[label][year] = d[label].get(year, 0) + value


def _core_groups(obj):
    names = [x.resource.name for x in obj.resource_links.all()]
    return names or [NO_CORE]


def _series_from_table(t, palette=None, status_keys=None):
    out = []
    for i, r in enumerate(t["rows"]):
        color = (
            STATUS[status_keys[i]]
            if status_keys
            else SERIES[i % len(SERIES)]
        )
        out.append({"label": r["label"], "vals": r["vals"], "color": color})
    return out


def pubs_dashboard():
    pubs = list(
        Publication.objects.filter(archived_at__isnull=True).prefetch_related(
            "resource_links__resource"
        )
    )
    counts, core_counts, per_core = {}, {}, {}
    for p in pubs:
        published = p.status == PublicationStatus.PUBLISHED
        y = grant_year(
            p.publication_date if published else (p.submission_date or p.created_at.date())
        )
        _bump(counts, "Published" if published else "Non-published statuses", y)
        for name in _core_groups(p):
            _bump(core_counts, name, y)
            per_core.setdefault(name, {})
            _bump(per_core[name], "Published" if published else "All other statuses", y)
    years = _years(*counts.values(), *core_counts.values())
    t1 = _table(["Published", "Non-published statuses"], counts, years)
    core_names = sorted(n for n in core_counts if n != NO_CORE) + (
        [NO_CORE] if NO_CORE in core_counts else []
    )
    t_core = _table(core_names, core_counts, years)
    pipeline = []
    for a, b in zip(years, years[1:]):
        prior = counts.get("Non-published statuses", {}).get(a, 0)
        nxt = counts.get("Published", {}).get(b, 0)
        pipeline.append(
            {
                "step": f"Y{a} to Y{b}",
                "prior": prior,
                "published": nxt,
                "ratio": f"{round(100 * nxt / prior)}%" if prior else "—",
            }
        )
    cores = []
    for name in core_names:
        if name == NO_CORE:
            continue
        t = _table(["Published", "All other statuses"], per_core.get(name, {}), years)
        cores.append(
            {
                "name": name,
                "table": t,
                "graph": gpair(
                    [f"Y{y}" for y in years],
                    _series_from_table(t),
                    flip_x="Status",
                    y_label="Papers",
                ),
                "legend": [("Published", SERIES[0]), ("All other statuses", SERIES[1])],
            }
        )
    return {
        "years": years,
        "t1": t1,
        "g1": gpair(
            [f"Y{y}" for y in years], _series_from_table(t1), flip_x="Status", y_label="Papers"
        ),
        "g1_legend": [("Published", SERIES[0]), ("Non-published statuses", SERIES[1])],
        "pipeline": pipeline,
        "t_core": t_core,
        "g_core": gpair(
            [f"Y{y}" for y in years],
            _series_from_table(t_core),
            kind="s",
            flip_x="Core",
            y_label="Papers",
            trend=True,
        ),
        "core_legend": [(n, SERIES[i % len(SERIES)]) for i, n in enumerate(core_names)],
        "cores": cores,
    }


def talks_dashboard():
    talks = list(
        Presentation.objects.filter(archived_at__isnull=True).prefetch_related(
            "resource_links__resource"
        )
    )
    by_type, core_counts, totals = {}, {}, {}
    type_labels = [label for _, label in PresentationType.choices]
    for t in talks:
        y = grant_year(t.presented_on)
        _bump(totals, "All presentations", y)
        _bump(by_type, t.get_presentation_type_display(), y)
        for name in _core_groups(t):
            _bump(core_counts, name, y)
    years = _years(*totals.values(), *core_counts.values())
    t1 = _table(["All presentations"], totals, years)
    used_types = [lab for lab in type_labels if lab in by_type]
    t2 = _table(used_types, by_type, years)
    core_names = sorted(n for n in core_counts if n != NO_CORE) + (
        [NO_CORE] if NO_CORE in core_counts else []
    )
    t3 = _table(core_names, core_counts, years)
    return {
        "years": years,
        "t1": t1,
        "g1": gpair(
            [f"Y{y}" for y in years],
            _series_from_table(t1),
            y_label="Presentations",
            trend=True,
        ),
        "t2": t2,
        "g2": gpair(
            [f"Y{y}" for y in years],
            _series_from_table(t2),
            flip_x="Type",
            y_label="Presentations",
        ),
        "t2_legend": [(n, SERIES[i % len(SERIES)]) for i, n in enumerate(used_types)],
        "t3": t3,
        "g3": gpair(
            [f"Y{y}" for y in years],
            _series_from_table(t3),
            kind="s",
            flip_x="Core",
            y_label="Presentations",
            trend=True,
        ),
        "core_legend": [(n, SERIES[i % len(SERIES)]) for i, n in enumerate(core_names)],
    }


GRANT_BUCKETS = [
    (GrantStatus.AWARDED, "Awarded", "awarded"),
    (GrantStatus.SUBMITTED, "Pending", "pending"),
    (GrantStatus.NOT_FUNDED, "Declined", "declined"),
]


def grants_dashboard():
    grants = list(
        GrantSubmission.objects.filter(archived_at__isnull=True)
        .exclude(status=GrantStatus.PLANNED)
        .prefetch_related("resource_links__resource")
    )
    counts, dollars = {}, {}
    per_core_counts, per_core_dollars = {}, {}
    for g in grants:
        bucket = next((lab for st, lab, _ in GRANT_BUCKETS if g.status == st), None)
        if not bucket:
            continue
        if g.status == GrantStatus.AWARDED:
            y = grant_year(g.award_notice_date or g.submission_date)
            amount = float(g.award_total or 0)
        elif g.status == GrantStatus.NOT_FUNDED:
            y = grant_year(g.decision_date or g.submission_date)
            amount = float(g.requested_total or 0)
        else:
            y = grant_year(g.submission_date)
            amount = float(g.requested_total or 0)
        _bump(counts, bucket, y)
        _bump(dollars, bucket, y, amount)
        for name in _core_groups(g):
            per_core_counts.setdefault(name, {})
            per_core_dollars.setdefault(name, {})
            _bump(per_core_counts[name], bucket, y)
            _bump(per_core_dollars[name], bucket, y, amount)
    years = _years(*counts.values(), *dollars.values())
    labels = [lab for _, lab, _ in GRANT_BUCKETS]
    keys = [k for _, _, k in GRANT_BUCKETS]
    t_counts = _table(labels, counts, years)
    t_dollars = _table(labels, dollars, years, dollars=True)
    cores = []
    for name in sorted(n for n in per_core_counts if n != NO_CORE) + (
        [NO_CORE] if NO_CORE in per_core_counts else []
    ):
        tc = _table(labels, per_core_counts.get(name, {}), years)
        td = _table(labels, per_core_dollars.get(name, {}), years, dollars=True)
        cores.append(
            {
                "name": name,
                "t_counts": tc,
                "t_dollars": td,
                "graph": gpair(
                    [f"Y{y}" for y in years],
                    _series_from_table(tc, status_keys=keys),
                    flip_x="Status",
                    y_label="Proposals",
                ),
            }
        )
    legend = [(lab, STATUS[k]) for _, lab, k in GRANT_BUCKETS]
    return {
        "years": years,
        "t_counts": t_counts,
        "t_dollars": t_dollars,
        "g_counts": gpair(
            [f"Y{y}" for y in years],
            _series_from_table(t_counts, status_keys=keys),
            flip_x="Status",
            y_label="Proposals",
        ),
        "g_dollars": gpair(
            [f"Y{y}" for y in years],
            _series_from_table(t_dollars, status_keys=keys),
            flip_x="Status",
            y_label="Dollars",
            dollars=True,
        ),
        "legend": legend,
        "cores": cores,
    }


TITLES = {
    "pubs": "Publications dashboard",
    "talks": "Presentations dashboard",
    "grants": "Grants dashboard",
}


@admin_view
def dashboard(request, kind):
    data = {"pubs": pubs_dashboard, "talks": talks_dashboard, "grants": grants_dashboard}[
        kind
    ]()
    return render(
        request,
        "manage/dashboard_products.html",
        {"kind": kind, "title": TITLES[kind], "d": data},
    )
