"""
Fill in publication details from a PubMed link (Publication flow 4.2, "optional system enhancement":
attempt metadata extraction from the PubMed link; if it fails, allow manual entry).

Uses NCBI E-utilities (efetch, XML). Accepts a PubMed URL, "PMID: 123", a bare PMID, or a DOI / doi.org link
(looked up with esearch). Returns title, journal, publication date, author list, grant IDs and author
affiliations. Nothing is saved here: the form shows the values for the person to check.
"""

import datetime as dt
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from django.conf import settings

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
    )
}


class LookupError_(Exception):
    """PubMed couldn't be reached or the link wasn't recognised; the person types the details instead."""


def pmid_from(text):
    t = (text or "").strip()
    for pat in (
        r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)",
        r"ncbi\.nlm\.nih\.gov/pubmed/(\d+)",
        r"PMID:?\s*(\d+)",
        r"^(\d{5,9})$",
    ):
        m = re.search(pat, t, re.I)
        if m:
            return m.group(1)
    return None


def doi_from(text):
    m = re.search(r"(10\.\d{4,9}/[^\s?#]+)", text or "")
    return m.group(1).rstrip(".") if m else None


def _get(url, timeout=8):
    params = {"tool": "cnap-reporting-hub"}
    if getattr(settings, "PUBMED_CONTACT_EMAIL", ""):
        params["email"] = settings.PUBMED_CONTACT_EMAIL
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(
        url + sep + urllib.parse.urlencode(params), headers={"User-Agent": "cnap-reporting-hub"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (fixed https host)
        return r.read()


def _pmid_for_doi(doi, get):
    data = json.loads(
        get(f"{EUTILS}/esearch.fcgi?db=pubmed&retmode=json&term={urllib.parse.quote(doi)}[doi]")
    )
    ids = data.get("esearchresult", {}).get("idlist", [])
    return ids[0] if ids else None


def _date(article):
    """Electronic date if given, else the journal issue date (year, month, day as available)."""
    ad = article.find(".//ArticleDate")
    if ad is not None and ad.findtext("Year"):
        try:
            return dt.date(
                int(ad.findtext("Year")),
                int(ad.findtext("Month") or 1),
                int(ad.findtext("Day") or 1),
            )
        except ValueError:
            pass
    pd = article.find(".//Journal/JournalIssue/PubDate")
    if pd is None:
        return None
    y = pd.findtext("Year") or (re.match(r"\d{4}", pd.findtext("MedlineDate") or "") or [None])[0]
    if not y:
        return None
    mon = (pd.findtext("Month") or "1").strip()
    m = int(mon) if mon.isdigit() else MONTHS.get(mon[:3].lower(), 1)
    d = int(pd.findtext("Day") or 1)
    try:
        return dt.date(int(y), m, d)
    except ValueError:
        return dt.date(int(y), m, 1)


def parse_efetch(xml_bytes):
    root = ET.fromstring(xml_bytes)
    art = root.find(".//PubmedArticle")
    if art is None:
        raise LookupError_("PubMed has no article with that ID.")
    a = art.find(".//Article")
    title = (
        "".join(a.find("ArticleTitle").itertext()).strip()
        if a.find("ArticleTitle") is not None
        else ""
    )
    journal = (a.findtext("Journal/Title") or "").strip()
    authors, affs = [], []
    for au in a.findall(".//AuthorList/Author"):
        last, init = au.findtext("LastName"), au.findtext("Initials")
        if last:
            authors.append(f"{last} {init or ''}".strip())
        elif au.findtext("CollectiveName"):
            authors.append(au.findtext("CollectiveName"))
        for af in au.findall(".//AffiliationInfo/Affiliation"):
            if af.text and af.text not in affs:
                affs.append(af.text.strip())
    grants = [
        g.findtext("GrantID").strip()
        for g in a.findall(".//GrantList/Grant")
        if g.findtext("GrantID")
    ]
    pmid = art.findtext(".//MedlineCitation/PMID") or ""
    return {
        "pmid": pmid,
        "title": title.rstrip("."),
        "journal": journal,
        "publication_date": _date(a),
        "authors": ", ".join(authors),
        "grants": grants,
        "affiliations": affs,
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
    }


def _norm_grant(g):
    return re.sub(r"[^A-Z0-9]", "", g.upper())


def lookup(link, get=None):
    """Details for a PubMed link; raises LookupError_ with a plain message when it can't."""
    get = get or _get
    pmid = pmid_from(link)
    if not pmid:
        doi = doi_from(link)
        if not doi:
            raise LookupError_("That doesn’t look like a PubMed link, PMID or DOI.")
        try:
            pmid = _pmid_for_doi(doi, get)
        except Exception as exc:  # network, JSON
            raise LookupError_(
                "Couldn’t reach PubMed right now. Please type the details in."
            ) from exc
        if not pmid:
            raise LookupError_(
                "PubMed has no article with that DOI yet. Please type the details in."
            )
    try:
        out = parse_efetch(get(f"{EUTILS}/efetch.fcgi?db=pubmed&retmode=xml&id={pmid}"))
    except LookupError_:
        raise
    except Exception as exc:
        raise LookupError_("Couldn’t reach PubMed right now. Please type the details in.") from exc
    cnap = set()
    for g in getattr(settings, "CNAP_GRANT_NUMBERS", []):
        n = _norm_grant(g)
        if n:
            # PubMed writes it many ways ("P20 GM113109", "GM113109", "P20GM113109/GM/NIGMS NIH HHS"): match the core part.
            cnap.add(re.sub(r"^[A-Z]\d{2}(?=[A-Z]{2}\d)", "", n))
    out["cnap_in_grant_index"] = (
        any(any(c in _norm_grant(g) for c in cnap) for g in out["grants"]) if cnap else None
    )
    return out
