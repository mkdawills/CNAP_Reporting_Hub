"""Core RRIDs (MW 2026-10-28, handbook chapter 14): stored per core, asked when a published paper used the core."""

import pytest
from django.core.management import call_command

from apps.accounts.models import User
from apps.admin_center import quality
from apps.outcomes.models import Publication, PublicationResource
from apps.people.models import Core, Resource
from apps.people.services import normalize_rrid


@pytest.fixture
def center(db):
    call_command("seed", "--fictional", verbosity=0)


@pytest.mark.parametrize(
    "raw, want",
    [
        ("SCR_012345", "RRID:SCR_012345"),
        ("rrid: scr_012345", "RRID:SCR_012345"),
        ("https://scicrunch.org/resolver/RRID:SCR_012345", "RRID:SCR_012345"),
        ("", ""),
    ],
)
def test_normalize(raw, want):
    assert normalize_rrid(raw) == want


@pytest.mark.parametrize("raw", ["AB_123456", "hello", "SCR_12"])
def test_normalize_refuses(raw):
    with pytest.raises(ValueError):
        normalize_rrid(raw)


def test_evaluator_saves_an_rrid_and_duplicates_are_refused(client, center):
    client.force_login(User.objects.get(username="mwills"))
    cn = Core.objects.get(code="CN")
    client.post(f"/manage/cores/{cn.pk}/rrid/", {"rrid": "scr_123456"})
    cn.refresh_from_db()
    assert cn.rrid == "RRID:SCR_123456"
    bn = Core.objects.get(code="BN")
    r = client.post(f"/manage/cores/{bn.pk}/rrid/", {"rrid": "RRID:SCR_123456"}, follow=True)
    assert "already saved" in r.content.decode()
    bn.refresh_from_db()
    assert bn.rrid != "RRID:SCR_123456"
    assert "RRID:SCR_123456" in client.get("/manage/projects/").content.decode()
    # view-only administrators can't change it
    client.force_login(User.objects.get(username="hbailey"))
    assert client.post(f"/manage/cores/{cn.pk}/rrid/", {"rrid": ""}).status_code == 403


def _published(client, p, resources, **extra):
    return client.post(
        f"/outcomes/pub/{p.pk}/",
        {
            "to": "published",
            "submission_date": "2026-11-01",
            "journal": "J Test",
            "title": "RRID paper",
            "pubmed_url": "https://pubmed.ncbi.nlm.nih.gov/1/",
            "cnap_cited": "yes",
            "cnap_in_grant_index": "no",
            "has_foreign_authors": "no",
            "has_non_idea_coauthors": "no",
            "resources": [r.pk for r in resources],
            **extra,
        },
    )


def test_asked_only_for_ticked_cores_that_have_an_rrid(client, center):
    u = User.objects.get(username="okafor")
    client.force_login(u)
    client.post("/outcomes/new/pub/", {"title": "RRID paper", "publication_type": "journal_article"})
    p = Publication.objects.get(title="RRID paper")
    Publication.objects.filter(pk=p.pk).update(status="submitted")
    bn = Resource.objects.get(code="bn_core")
    cn = Resource.objects.get(code="cn_core")
    assert bn.core.rrid and not cn.core.rrid
    page = client.get(f"/outcomes/pub/{p.pk}/?to=published").content.decode()
    assert f"Did you cite the {bn.core.name}’s Research Resource Identifier (RRID), {bn.core.rrid}," in page
    assert f"data-show-res=\"{bn.pk}\"" in page and f"{cn.core.name}’s RRID" not in page
    assert bn.core.rrid in page  # in the "how to acknowledge" box too
    # ticked but unanswered: asked to answer
    r = _published(client, p, [bn, cn])
    assert "Answer, or choose Not sure." in r.content.decode()
    _published(client, p, [bn, cn], **{f"rrid_{bn.pk}": "no"})
    links = {x.resource_id: x.rrid_cited for x in PublicationResource.objects.filter(publication=p)}
    assert links == {bn.pk: "no", cn.pk: ""}
    # the evaluator sees it, can filter on it, and gets a data check
    client.force_login(User.objects.get(username="mwills"))
    tab = client.get("/manage/outcomes/?tab=pubs").content.decode()
    assert "RRID not cited" in tab and "Core RRID not cited" in tab
    assert "RRID paper" in client.get("/manage/outcomes/?tab=pubs&ack=rrid").content.decode()
    rows = next(c for c in quality.run() if c["code"] == "rrid_not_cited")["rows"]
    assert p.pk in [r[1] for r in rows]
    csv = client.get("/manage/outcomes/export/pubs/").content.decode()
    assert f"{bn.name}: No" in csv
    # answering Yes later clears it
    client.force_login(u)
    _published(client, p, [bn], **{f"rrid_{bn.pk}": "yes"})
    assert PublicationResource.objects.get(publication=p, resource=bn).rrid_cited == "yes"
    rows = next(c for c in quality.run() if c["code"] == "rrid_not_cited")["rows"]
    assert p.pk not in [r[1] for r in rows]


def test_no_rrid_no_question(client, center):
    Core.objects.update(rrid="")
    client.force_login(User.objects.get(username="okafor"))
    client.post("/outcomes/new/pub/", {"title": "Plain", "publication_type": "journal_article"})
    p = Publication.objects.get(title="Plain")
    Publication.objects.filter(pk=p.pk).update(status="submitted")
    page = client.get(f"/outcomes/pub/{p.pk}/?to=published").content.decode()
    assert "’s RRID (" not in page and "data-show-res=\"" not in page


def test_foreign_coauthor_citing_the_grant_is_flagged(center):
    p = Publication.objects.create(
        title="Abroad", publication_type="journal_article", status="published",
        has_foreign_authors=True, cnap_cited=True, foreign_component_approved=False,
    )
    rows = next(c for c in quality.run() if c["code"] == "foreign_cites_grant")["rows"]
    assert p.pk in [r[1] for r in rows]
