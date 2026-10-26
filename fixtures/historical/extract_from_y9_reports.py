# ruff: noqa  (one-time extraction script; kept for the record of how the prior-year file was made)
"""Extract Year 6-9 item means (only) from the Year 9 site-visit reports into fixtures/historical/aggregates_y6_y9.csv."""

import csv
import json
import re
from pathlib import Path

from openpyxl import load_workbook

Y9 = Path("/tmp/claude-0/y9")
FIX = Path("/home/claude/cnap-platform/fixtures/forms")
OUT = Path("/home/claude/cnap-platform/fixtures/historical/aggregates_y6_y9.csv")
PERIODS = [
    ("Y6 Fall", 6, 1),
    ("Y6 Spring", 6, 2),
    ("Y7 Fall", 7, 1),
    ("Y7 Spring", 7, 2),
    ("Y8 Fall", 8, 1),
    ("Y8 Spring", 8, 2),
    ("Y9 Fall", 9, 1),
    ("Y9 Spring", 9, 2),
]


def norm(s):
    s = re.sub(r"^\s*\d+\.\s*", "", str(s or "").replace("\xa0", " "))
    return re.sub(r"[^a-z0-9]", "", s.lower().replace("brown bag", "neurosync"))


def fixture_items(code, section):
    spec = json.loads((FIX / f"{code}.json").read_text())
    sec = next(s for s in spec["sections"] if s["code"] == section)
    return [
        (q["measure"], q["prompt"], q["answer_set"]) for q in sec["questions"] if q.get("measure")
    ]


def md_tables(path):
    tables, cur = [], []
    for line in Path(path).read_text().splitlines():
        if line.startswith("|"):
            cur.append(
                [c.strip().replace("**", "").strip() for c in line.strip().strip("|").split("|")]
            )
        elif cur:
            tables.append(cur)
            cur = []
    if cur:
        tables.append(cur)
    return [t for t in tables if any("Jan" in r and ("June" in r or "May" in r) for r in t[:4])]


rows_out = []


SDS = {}  # (form, measure, period label) -> sd, where the reports give one
ALIASES = {"cncoresharedfacilityspacebluemonthall426": "cn_frequency_02"}


def emit(form, measure, name, scale, values, source, sds=None):
    for i, ((label, gy, seq), v) in enumerate(zip(PERIODS, values)):
        sd = sds[i] if sds and i < len(sds) else None
        if isinstance(sd, (int, float)):
            SDS[(form, measure, label)] = round(float(sd), 3)
        if (
            v in (None, "", "--", "-")
            or isinstance(v, str)
            and not re.match(r"^\d+(\.\d+)?$", v.strip())
        ):
            continue
        rows_out.append(
            {
                "form_code": form,
                "measure_code": measure,
                "measure_name": name,
                "scale": scale,
                "period": label,
                "grant_year": gy,
                "sequence": seq,
                "mean": round(float(v), 3),
                "source": source,
            }
        )


for core, doc in (
    ("bn", "BN Core User Survey Data - Year 9 Site Visit.docx"),
    ("ni", "NI Core Survey Data - Year 9 Site Visit.docx"),
    ("cn", "CN Core User Survey Data - Year 9 Site Visit.docx"),
):
    import subprocess

    md = Y9 / f"{core}.md"
    md.write_text(
        subprocess.run(["extract-text", str(Y9 / doc)], capture_output=True, text=True).stdout
    )
    tabs = md_tables(md)
    assert len(tabs) >= 2, (core, len(tabs))
    for tab, section, scale in (
        (tabs[0], "quality", "Quality"),
        (tabs[1], "frequency", "Frequency"),
    ):
        items = fixture_items(f"{core}_core_survey", section)
        lookup = {norm(p): (m, p) for m, p, _ in items}
        # Same item, room number dropped from today's wording (the Y9 Spring report lists it as current).
        for old, code in ALIASES.items():
            hit = next(((m, p) for m, p, _ in items if m == code), None)
            if hit:
                lookup[old] = hit
        # NI's trend tables pair every mean with its SD: Mean | (SD) | Mean | (SD) ...
        paired = any(sum(c == "(SD)" for c in row) >= 4 for row in tab[:6])
        retired = 0
        for r in tab:
            label = r[0]
            if (
                not label
                or label in ("Question", "Phase II")
                or label.lower().startswith("overall")
                or label.lower().startswith("grand")
            ):
                continue
            if paired:
                vals = [r[i] if i < len(r) else "" for i in range(1, 17, 2)]
                sds = [(r[i] if i < len(r) else "").strip("()") for i in range(2, 18, 2)]
                sds = [float(x) if re.match(r"^\d+(\.\d+)?$", x or "") else None for x in sds]
            else:
                vals, sds = r[1:9], None
            if not any(re.match(r"^\d", v or "") for v in vals):
                continue
            hit = lookup.get(norm(label))
            if hit:
                emit(f"{core}_core_survey", hit[0], hit[1], scale, vals, doc, sds)
            else:
                retired += 1
                emit(
                    f"{core}_core_survey",
                    f"{core}_{section}_retired_{retired:02d}",
                    re.sub(r"^\d+\.\s*", "", label),
                    scale,
                    vals,
                    doc + " (retired item)",
                    sds,
                )


def table1_sds(core, md):
    """Table 1 of each core report is the latest period (Y9 Spring): Mean | (SD) per item."""
    cur, tabs = [], []
    for line in Path(md).read_text().splitlines():
        if line.startswith("|"):
            cur.append(
                [c.strip().replace("**", "").strip() for c in line.strip().strip("|").split("|")]
            )
        elif cur:
            tabs.append(cur)
            cur = []
    t1 = [
        t
        for t in tabs
        if any(
            ("(SD)" in r or "SD" in r) and "Mean" in r and sum(c == "(SD)" for c in r) < 2
            for r in t[:2]
        )
    ]
    for tab, section in zip(t1[:2], ("quality", "frequency")):
        lookup = {norm(p): m for m, p, _ in fixture_items(f"{core}_core_survey", section)}
        lookup.update({k: v for k, v in ALIASES.items() if v in lookup.values()})
        for r in tab:
            m = lookup.get(norm(r[0]))
            if m and len(r) > 2 and re.match(r"^\(?\d+(\.\d+)?\)?$", r[2]):
                SDS[(f"{core}_core_survey", m, "Y9 Spring")] = float(r[2].strip("()"))


for core in ("bn", "ni", "cn"):
    table1_sds(core, Y9 / f"{core}.md")


def comparison(xlsx, sheet, form, section, scale, mean_cols, sd_cols=None):
    ws = load_workbook(Y9 / xlsx, read_only=True, data_only=True)[sheet]
    items = fixture_items(form, section)
    i = 0
    for r in ws.iter_rows(values_only=True):
        label = r[0]
        if not label or not re.match(r"^\s*\d+\.", str(label)):
            continue
        m, prompt, _ = items[i]
        i += 1
        emit(
            form,
            m,
            prompt,
            scale,
            [r[c] for c in mean_cols],
            xlsx,
            [r[c] for c in sd_cols] if sd_cols else None,
        )
    assert i == len(items), (form, i)


comparison(
    "Neurosync Survey Data - Year 9 Site Visit.xlsx",
    "Comparison (Y6-Y10)",
    "neurosync_survey",
    "ratings",
    "Agreement",
    [1, 3, 5, 7, 9, 11, 13, 15],
    [2, 4, 6, 8, 10, 12, 14, 16],
)
comparison(
    "Mentor Survey - Year 9 Site Visit.xlsx",
    "Comparison",
    "mentor_questionnaire",
    "mentoring",
    "Agreement",
    [1, 2, 3, 4, 5, 6, 7, 8],
)
comparison(
    "Mentee Survey - Year 9 Site Visit.xlsx",
    "Comparison",
    "mentee_survey",
    "mentors",
    "Agreement",
    [1, 2, 3, 4, 5, 6, 7, 8],
)

for r in rows_out:
    r["sd"] = SDS.get((r["form_code"], r["measure_code"], r["period"]), "")
OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows_out[0]))
    w.writeheader()
    w.writerows(rows_out)
from collections import Counter

print(len(rows_out), "values")
print(Counter(r["form_code"] for r in rows_out))
print(Counter(r["period"] for r in rows_out))
print(sorted({r["measure_code"] for r in rows_out if "retired" in r["measure_code"]}))
