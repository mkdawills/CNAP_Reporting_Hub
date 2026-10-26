"""Self-entry of publications and grants, following MW's Publication flow and Grant flow (decisions.md 2026-10-26)."""

import pytest
from django.core.management import call_command

from apps.accounts.models import User
from apps.outcomes.models import GrantSubmission, OutcomeCheckin, Publication
from apps.people.models import Resource


@pytest.fixture
def center(db):
    call_command("seed", "--fictional", verbosity=0)


def login(client, u):
    user = User.objects.get(username=u)
    client.force_login(user)
    return user


def test_only_awardees_and_their_delegates(client, center):
    login(
        client, "lee"
    )  # on the roster: can open the page (decisions.md 2026-10-26, everyone on the roster)
    assert client.get("/outcomes/").status_code == 200
    client.logout()
    from apps.people.models import Person

    nobody = Person.objects.create(first_name="No", last_name="Roles")
    nobody_user = (
        User.objects.create_user(username="noroles", password="x", person=nobody)
        if hasattr(User.objects, "create_user")
        else None
    )
    if nobody_user:
        client.force_login(nobody_user)
        assert client.get("/outcomes/").status_code == 403
    login(client, "okafor")
    assert client.get("/outcomes/").status_code == 200


def test_first_prompt_no_plans_completes(client, center):
    u = login(client, "adeyemi")
    Publication.objects.filter(people__person=u.person).delete()
    GrantSubmission.objects.filter(people__person=u.person).delete()
    client.post("/outcomes/plans/pubs/", {"answer": "no"})
    client.post("/outcomes/plans/grants/", {"answer": "no"})
    c = OutcomeCheckin.objects.get(person=u.person)
    assert c.plans_publications is False and c.plans_grants is False
    assert "All caught up" in client.get("/outcomes/").content.decode()


def test_publication_lifecycle(client, center):
    u = login(client, "okafor")
    bn = Resource.objects.get(code="bn_core")
    client.post(
        "/outcomes/new/pub/",
        {
            "title": "Test paper",
            "journal": "J Test",
            "publication_type": "journal_article",
            "resources": [bn.pk],
        },
    )
    p = Publication.objects.get(title="Test paper")
    assert p.status == "planned" and p.resource_links.get().is_anticipated
    # Submitted requires Center resources
    r = client.post(
        f"/outcomes/pub/{p.pk}/",
        {
            "to": "submitted",
            "journal": "J Test",
            "title": "Test paper",
            "submission_date": "2026-11-01",
        },
    )
    assert r.status_code == 200 and "Choose at least one Center resource" in r.content.decode()
    client.post(
        f"/outcomes/pub/{p.pk}/",
        {
            "to": "submitted",
            "journal": "J Test",
            "title": "Test paper",
            "submission_date": "2026-11-01",
            "resources": [bn.pk],
        },
    )
    p.refresh_from_db()
    assert p.status == "submitted"
    client.post(
        f"/outcomes/pub/{p.pk}/",
        {
            "to": "published",
            "submission_date": "2026-11-01",
            "journal": "J Test",
            "title": "Test paper",
            "pubmed_url": "https://pubmed.ncbi.nlm.nih.gov/1/",
            "cnap_cited": "yes",
            "cnap_in_grant_index": "no",
            "has_foreign_authors": "no",
            "has_non_idea_coauthors": "no",
            "resources": [bn.pk],
        },
    )
    p.refresh_from_db()
    assert p.status == "published" and p.cnap_cited is True and p.cnap_in_grant_index is False
    assert list(p.status_history.values_list("to_status", flat=True)) == [
        "planned",
        "submitted",
        "published",
    ]
    assert u.person in [x.person for x in p.people.all()]


def test_declined_with_resubmit_creates_planned(client, center):
    login(client, "okafor")
    client.post("/outcomes/new/pub/", {"title": "Paper D", "publication_type": "journal_article"})
    p = Publication.objects.get(title="Paper D")
    Publication.objects.filter(pk=p.pk).update(status="submitted")
    client.post(
        f"/outcomes/pub/{p.pk}/",
        {
            "to": "declined",
            "decline_date": "2027-01-05",
            "journal": "J X",
            "comments": "Reviewers wanted more data",
            "resubmission_intent": "yes",
        },
    )
    assert Publication.objects.filter(title="Paper D", status="planned", resubmission_of=p).exists()


def test_grant_not_funded_resubmission_is_a1(client, center):
    login(client, "okafor")
    cn = Resource.objects.get(code="cn_core")
    client.post(
        "/outcomes/new/grant/",
        {
            "funding_agency": "NIH",
            "project_title": "Grant G",
            "role": "pi",
            "anticipated_total": "100000",
            "resources": [cn.pk],
        },
    )
    g = GrantSubmission.objects.get(project_title="Grant G")
    assert g.version_label == "A0"
    client.post(
        f"/outcomes/grant/{g.pk}/",
        {
            "to": "submitted",
            "funding_agency": "NIH",
            "project_title": "Grant G",
            "role": "pi",
            "submission_date": "2026-10-05",
            "funding_source_type": "nih",
            "requested_total": "120000",
            "resources": [cn.pk],
        },
    )
    client.post(
        f"/outcomes/grant/{g.pk}/",
        {
            "to": "not_funded",
            "decision_date": "2027-02-01",
            "discussed_with_program_officer": "yes",
            "feedback_shared_with_cnap": "no",
            "plans_to_resubmit": "yes",
        },
    )
    g.refresh_from_db()
    assert (
        g.status == "not_funded"
        and g.discussed_with_program_officer
        and g.feedback_shared_with_cnap is False
    )
    a1 = GrantSubmission.objects.get(grant_family=g.grant_family, version_no=1)
    assert a1.status == "planned" and a1.version_label == "A1" and a1.anticipated_total == 120000
    assert a1.resubmission_of == g and a1.resource_links.filter(resource=cn).exists()


def test_delegate_can_enter_for_owner(client, center):
    owner = login(client, "okafor").person
    student = User.objects.get(username="lee").person
    client.post("/outcomes/delegates/add/", {"person": student.pk})
    login(client, "lee")
    assert client.get(f"/outcomes/?for={owner.pk}").status_code == 200
    client.post(
        f"/outcomes/new/pub/?for={owner.pk}",
        {"title": "Entered by student", "publication_type": "journal_article", "for": owner.pk},
    )
    p = Publication.objects.get(title="Entered by student")
    assert owner in [x.person for x in p.people.all()]
    # the student can't add delegates for the owner
    assert (
        client.post("/outcomes/delegates/add/", {"person": student.pk, "for": owner.pk}).status_code
        == 403
    )


def test_task_counts_on_my_tasks(client, center):
    login(client, "okafor")
    html = client.get("/tasks/").content.decode()
    assert "publications and grants" in html.lower()


def test_exports_have_spec_columns(client, center):
    login(client, "mwills")
    head = client.get("/manage/outcomes/export/pubs/").content.decode("utf-8-sig").splitlines()[0]
    for col in [
        "Project ID",
        "Anticipated Center Resources Utilized",
        "CNAP Grant Index",
        "Declined Date (timestamp)",
    ]:
        assert col in head
    head = client.get("/manage/outcomes/export/grants/").content.decode("utf-8-sig").splitlines()[0]
    for col in [
        "Parent Grant ID",
        "Submission Version",
        "Reviewer Feedback Shared with CNAP",
        "Not Funded Date (timestamp)",
    ]:
        assert col in head
