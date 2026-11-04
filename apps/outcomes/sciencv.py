"""
Read what the site needs from SciENcv Common Form PDFs (MW 2026-10-27). Built against the layout of real
SciENcv output (NIH-BGS26 biosketch, NIH-CPOS25 Current and Pending), read for structure only; tests use
made-up text in the same layout.

What is read, and nothing else:
- the form type (biosketch Common Form, or Current and Pending (Other) Support Common Form);
- the "Certified by ... in SciENcv on YYYY-MM-DD" line, so an uncertified or preview copy is caught early;
- the ORCID iD in the Persistent Identifier (PID) section;
- biosketch: degree abbreviations in Professional Preparation, e.g. (PHD), (MA), (BS);
- Current and Pending: the person months by year listed under the CNAP award (P20GM113109).

Everything read is a suggestion shown to a person, never saved over what someone typed. If the layout changes,
fields come back empty and the page says it couldn't read them.
"""

import re

from django.conf import settings

DEGREES = {
    "PHD": "PhD",
    "MD": "MD",
    "DO": "DO",
    "PSYD": "PsyD",
    "EDD": "EdD",
    "DRPH": "DrPH",
    "SCD": "ScD",
    "DVM": "DVM",
    "DDS": "DDS",
    "DMD": "DMD",
    "PHARMD": "PharmD",
    "DNP": "DNP",
    "DPT": "DPT",
    "JD": "JD",
    "MA": "MA",
    "MS": "MS",
    "MSC": "MSc",
    "MPH": "MPH",
    "MBA": "MBA",
    "MSW": "MSW",
    "MSN": "MSN",
    "MFA": "MFA",
    "MED": "MEd",
    "MPHIL": "MPhil",
    "MENG": "MEng",
    "MPA": "MPA",
    "MAT": "MAT",
    "BA": "BA",
    "BS": "BS",
    "BSC": "BSc",
    "BSN": "BSN",
    "BFA": "BFA",
    "BENG": "BEng",
    "AB": "AB",
    "SB": "SB",
    "AA": "AA",
    "AS": "AS",
}
ORCID_RE = re.compile(r"orcid\.org/(\d{4}-\d{4}-\d{4}-\d{3}[\dX])", re.I)
CERT_RE = re.compile(r"Certified by .{1,120}? in SciENcv on (\d{4}-\d{2}-\d{2})")


def text_of(file_obj, max_pages=40):
    """Plain text of a stored PDF, or "" if it can't be read."""
    from pypdf import PdfReader

    try:
        with file_obj.storage_key.open("rb") as fh:
            r = PdfReader(fh)
            return "\n".join((p.extract_text() or "") for p in r.pages[:max_pages])
    except Exception:  # a damaged or encrypted file: nothing to suggest
        return ""


def _common(text):
    m = ORCID_RE.search(text)
    c = CERT_RE.search(text)
    return {"orcid": m.group(1).upper() if m else "", "certified": c.group(1) if c else ""}


def read_biosketch(text):
    out = _common(text)
    out["form_ok"] = "BIOGRAPHICAL SKETCH COMMON FORM" in text
    degrees = []
    if "PROFESSIONAL PREPARATION" in text:
        seg = text.split("PROFESSIONAL PREPARATION", 1)[1]
        for stop in (
            "APPOINTMENTS AND POSITIONS",
            "PRODUCTS",
            "NIH BIOGRAPHICAL SKETCH SUPPLEMENT",
        ):
            if stop in seg:
                seg = seg.split(stop, 1)[0]
        for tok in re.findall(r"\(([A-Za-z.]{2,7})\)", seg):
            d = DEGREES.get(tok.replace(".", "").upper())
            if d and d not in degrees:
                degrees.append(d)
    out["degrees"] = degrees
    return out


def read_current_pending(text, awards=None):
    out = _common(text)
    out["form_ok"] = "CURRENT AND PENDING (OTHER) SUPPORT" in text
    awards = [re.sub(r"[^A-Z0-9]", "", a.upper()) for a in (awards or settings.CNAP_GRANT_NUMBERS)]
    keys = [a[-8:] for a in awards]  # GM113109: matches 5P20GM113109-09, P20 GM113109, ...
    out["cnap_months"] = []
    out["cnap_found"] = False
    out["cnap_start"] = out["cnap_end"] = None
    entries = re.split(r"\*Proposal/Active Project Title:", text)[1:]
    for e in entries:
        num = re.search(r"Proposal/Award Number:\s*(\S[^\n]*)", e)
        flat = re.sub(r"[^A-Z0-9]", "", (num.group(1) if num else "").upper())
        if not any(k and k in flat for k in keys):
            continue
        out["cnap_found"] = True
        st = re.search(r"Start Date:\s*\(MM/YYYY\):\s*(\d{1,2})/(\d{4})", e)
        en = re.search(r"End Date:\s*\(MM/YYYY\):\s*(\d{1,2})/(\d{4})", e)
        out["cnap_start"] = (int(st.group(2)), int(st.group(1))) if st else None
        out["cnap_end"] = (int(en.group(2)), int(en.group(1))) if en else None
        block = e.split("Devoted to the Proposal/Active Project:", 1)
        if len(block) == 2:
            table = block[1].split("*Overall Objectives", 1)[0]
            table = table.replace("Year", " ").replace("Person Months", " ")
            nums = re.findall(r"\d+(?:\.\d+)?", table)
            pairs = []
            for i in range(0, len(nums) - 1, 2):
                y, m = nums[i], nums[i + 1]
                if len(y) == 4 and 1990 < int(y) < 2100:
                    pairs.append((int(y), m))
            out["cnap_months"] = pairs
        break
    return out


def message(code, info):
    """What to tell the uploader about one NIH document, or "" if it looks right."""
    kind = "biosketch" if code == "biosketch" else "Current and Pending (Other) Support"
    if not info.get("readable", True):
        return "We couldn’t read this PDF. Please upload the PDF downloaded from SciENcv."
    if not info["form_ok"]:
        return f"This doesn’t look like the NIH Common Form {kind} from SciENcv. Please check the file."
    if not info["certified"]:
        return "This copy isn’t certified in SciENcv yet. Please certify it there, download it again, and upload the new PDF. NIH rejects uncertified forms."
    return ""


def read_file(file_obj, kind):
    """read_biosketch / read_current_pending for a stored file, cached by its SHA-256 (files never change)."""
    from django.core.cache import cache

    key = f"sciencv:{kind}:{file_obj.sha256}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    text = text_of(file_obj)
    info = read_biosketch(text) if kind == "biosketch" else read_current_pending(text)
    info["readable"] = bool(text.strip())
    cache.set(key, info, 60 * 60 * 24 * 30)
    return info


def latest_for(person):
    """The newest biosketch and Current and Pending this person uploaded to an NIH documents task."""
    from apps.reporting.models import AnswerFile

    out = {}
    for code in ("biosketch", "current_pending"):
        link = (
            AnswerFile.objects.filter(
                answer__question__code=code,
                answer__question__form_version__form_definition__code="nih_documents",
                answer__response__assignment__person=person,
                answer__response__is_current=True,
            )
            .select_related("file", "answer__response__assignment__reporting_period")
            .order_by("-file__created_at")
            .first()
        )
        if link:
            out[code] = {
                "file": link.file,
                "period": link.answer.response.assignment.reporting_period,
                "info": read_file(link.file, code),
            }
    return out


MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()


def _idx(ym):
    return ym[0] * 12 + ym[1] - 1


def _ym(i):
    return (i // 12, i % 12 + 1)


def spans(start, end, pairs):
    """What each listed year covers, worked out from the project's start and end months (MW 2026-10-27).

    SciENcv lists person months by year. Two readings are possible: calendar years (cut at the project's start
    and end), or 12-month budget periods counted from the start month and named by the year they begin. The
    reading whose list of years matches the one in the PDF is used; if neither matches, None.
    """
    if not (start and end and pairs) or _idx(end) < _idx(start):
        return None
    s, e = _idx(start), _idx(end)
    years = [y for y, _ in pairs]
    cal = list(range(start[0], end[0] + 1))
    budget = [_ym(i)[0] for i in range(s, e + 1, 12)]
    if years == cal:
        how = "calendar"
        rng = {y: (max(s, y * 12), min(e, y * 12 + 11)) for y in cal}
    elif years == budget:
        how = "budget"
        rng = {_ym(i)[0]: (i, min(e, i + 11)) for i in range(s, e + 1, 12)}
    else:
        return None
    out = []
    for y, m in pairs:
        a, b = rng[y]
        out.append(
            {
                "year": y,
                "months": m,
                "from": a,
                "to": b,
                "how": how,
                "label": f"{MONTHS[_ym(a)[1] - 1]} {_ym(a)[0]} – {MONTHS[_ym(b)[1] - 1]} {_ym(b)[0]}",
            }
        )
    return out


def budget_year_estimate(sp, gy):
    """Person months falling in CNAP budget year `gy` (June 1, 2016+gy – May 31, 2017+gy), spread evenly within
    each listed period. An estimate for checking D.1, not a figure from the form."""
    from decimal import Decimal

    if not sp:
        return None
    lo, hi = (2016 + gy) * 12 + 5, (2017 + gy) * 12 + 4  # June .. May
    total = Decimal(0)
    hit = False
    for x in sp:
        ov = min(hi, x["to"]) - max(lo, x["from"]) + 1
        if ov > 0:
            hit = True
            total += Decimal(str(x["months"])) * ov / (x["to"] - x["from"] + 1)
    from decimal import ROUND_HALF_UP

    return total.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) if hit else None
