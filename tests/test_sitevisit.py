"""Site-visit outcome tables in the layout of MW's Year 9 workbooks (decisions.md 2026-10-26)."""

import datetime as dt

import pytest
from django.core.management import call_command

from apps.accounts.models import User
from apps.outcomes import sitevisit
from apps.outcomes.models import (
    GrantFamily,
    GrantSubmission,
    GrantSubmissionResource,
    Presentation,
    PresentationResource,
    Publication,
    PublicationResource,
)
from apps.people.models import Resource


@pytest.fixture
def center(db):
    call_command("seed", "--fictional", verbosity=0)
    Publication.objects.all().delete()
    Presentation.objects.all().delete()
    GrantSubmission.objects.all().delete()


def res(*codes):
    return [Resource.objects.get(code=c) for c in codes]


def pub(title, status, codes, **kw):
    p = Publication.objects.create(
        title=title, publication_type=kw.pop("ptype", "journal_article"), status=status, **kw
    )
    for r in res(*codes):
        PublicationResource.objects.create(publication=p, resource=r, is_anticipated=False)
    return p


def test_publications_by_core_type_status(center):
    pub("A", "published", ["bn_core", "ni_core"], publication_date=dt.date(2026, 3, 1))
    pub(
        "B", "submitted", ["bn_core"], substatus="under_review", submission_date=dt.date(2025, 7, 5)
    )  # submitted in Year 9, still under review
    pub("C", "declined", ["cn_core"], decline_date=dt.date(2025, 12, 1))
    pub("D", "published", [], publication_date=dt.date(2026, 2, 1), ptype="preprint")
    pub("E", "published", ["bn_core"], publication_date=dt.date(2024, 3, 1))  # other year
    pub("F", "planned", ["bn_core"])  # planned: not counted
    old = pub(
        "H", "submitted", ["bn_core"], substatus="under_review", submission_date=dt.date(2024, 3, 1)
    )
    t = sitevisit.publications(9)
    assert t["n_items"] == 4 and t["n_counted"] == 5 and len(t["multi_core"]) == 1
    # submitted in an earlier year and still under review: listed separately, not counted
    assert [it["obj"] for it in t["carried"]] == [old]
    bn = next(x for x in t["rows"] if x["core"] == "BN Core")
    ja = next(r for r in bn["rows"] if r["type"] == "Journal Article")
    cols = sitevisit.PUB_STATUSES
    assert ja["vals"][cols.index("Published")] == 1 and ja["vals"][cols.index("Under Review")] == 1
    cn = next(x for x in t["rows"] if x["core"] == "CN Core")
    assert cn["rows"][0]["vals"][cols.index("Not Published")] == 1
    none = next(x for x in t["rows"] if x["core"] == "No core")
    assert none["rows"][0]["type"] == "In Pre-Print"


def test_anticipated_resources_dont_count(center):
    p = pub("G", "published", [], publication_date=dt.date(2026, 3, 1))
    PublicationResource.objects.create(
        publication=p, resource=res("bn_core")[0], is_anticipated=True
    )
    assert sitevisit.cores_of(p) == ["NONE"]


def test_presentations_and_new_since(center):
    t1 = Presentation.objects.create(
        presentation_type="poster_or_flyer", title="P1", presented_on=dt.date(2025, 11, 4)
    )
    for r in res("bn_core", "admin_core"):
        PresentationResource.objects.create(presentation=t1, resource=r)
    Presentation.objects.create(
        presentation_type="invited_talk", title="P2", presented_on=dt.date(2025, 8, 9)
    )
    t = sitevisit.presentations(9, since=dt.date(2000, 1, 1))
    assert t["n_items"] == 2 and t["n_counted"] == 3 and len(t["new"]) == 2
    bn = next(r for r in t["rows"] if r["core"] == "BN Core")
    assert bn["vals"][0] == 1 and bn["total"] == 1
    assert next(r for r in t["rows"] if r["core"] == "Admin Core")["total"] == 1
    assert sum(t["col_totals"]) == 3


def test_grants_by_core_and_funder(center):
    def g(title, status, codes, agency="NIH", **kw):
        x = GrantSubmission.objects.create(
            grant_family=GrantFamily.objects.create(title=title),
            project_title=title,
            funding_agency=agency,
            status=status,
            **kw,
        )
        for r in res(*codes):
            GrantSubmissionResource.objects.create(
                grant_submission=x, resource=r, is_anticipated=False
            )
        return x

    g(
        "Won",
        "awarded",
        ["bn_core"],
        award_notice_date=dt.date(2025, 9, 1),
        submission_date=dt.date(2025, 2, 1),
        award_total=300000,
        requested_total=350000,
    )
    g(
        "Waiting",
        "submitted",
        ["bn_core", "ni_core"],
        submission_date=dt.date(2024, 10, 1),
        requested_total=100000,
        agency="National Science Foundation",
    )
    g(
        "No",
        "not_funded",
        [],
        decision_date=dt.date(2026, 1, 15),
        submission_date=dt.date(2025, 6, 10),
        requested_total=50000,
        agency="American Heart Association",
    )
    g(
        "Waiting now",
        "submitted",
        ["cn_core"],
        submission_date=dt.date(2025, 10, 1),
        requested_total=200000,
    )
    t = sitevisit.grants(9)
    # "Waiting" was submitted in Year 8: it's still pending, listed separately and not counted in Year 9
    assert [it["obj"].project_title for it in t["carried"]] == ["Waiting"] and t[
        "carried_dollars"
    ] == 100000.0
    assert t["status_counts"] == {"Awarded": 1, "Pending": 1, "Declined": 1}
    bn = next(r for r in t["rows"] if r["label"] == "BN Core")
    assert bn["cells"][0] == {"n": 1, "dollars": 300000.0} and bn["cells"][1]["n"] == 0
    f = {r["label"]: r for r in t["by_funder"]}
    assert (
        f["NIH"]["cells"][0]["dollars"] == 300000.0
        and f["NIH"]["cells"][1]["n"] == 1  # "Waiting now" (agency NIH, submitted in Year 9)
        and f["NSF"]["n"] == 0  # "Waiting" is carried, not counted
        and f["Other"]["cells"][2]["dollars"] == 50000.0
    )
    assert t["funder_totals"][0]["n"] + t["funder_totals"][1]["n"] + t["funder_totals"][2]["n"] == 3


def test_site_visit_tab_and_csv(client, center):
    client.force_login(User.objects.get(username="mwills"))
    pub("A", "published", ["bn_core"], publication_date=dt.date(2026, 3, 1))
    html = client.get("/manage/outcomes/?tab=sitevisit&year=9").content.decode()
    assert "Laid out like the Year 9 site-visit workbooks" in html and "Grants and awards" in html
    csv = client.get("/manage/outcomes/export/sitevisit/?year=9&since=2020-01-01").content.decode(
        "utf-8-sig"
    )
    assert (
        "Publications (duplicates counted)" in csv
        and "Awarded total $" in csv
        and "Publication,A," in csv
    )
