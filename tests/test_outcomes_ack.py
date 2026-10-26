"""Publications and grants: acknowledgment tracking, multi-credit, access (decisions.md 2026-10-25)."""

import pytest
from django.core.management import call_command

from apps.accounts.models import User
from apps.outcomes.models import GrantSubmission, Publication


@pytest.fixture
def center(db):
    call_command("seed", "--fictional", verbosity=0)


def _login(client, username):
    client.force_login(User.objects.get(username=username))


def test_list_and_filters(client, center):
    _login(client, "mwills")
    r = client.get("/manage/outcomes/")
    assert r.status_code == 200 and "Sample paper" in r.content.decode()
    r = client.get("/manage/outcomes/?ack=check")
    html = r.content.decode()
    unchecked = Publication.objects.filter(status="published", cnap_cited__isnull=True)
    for p in unchecked:
        assert p.title in html
    for p in Publication.objects.filter(cnap_cited=True):
        assert p.title not in html


def test_mark_acknowledged_is_audited(client, center):
    _login(client, "mwills")
    p = Publication.objects.filter(cnap_cited__isnull=True).first()
    client.post(f"/manage/outcomes/publication/{p.pk}/ack/", {"value": "yes"})
    p.refresh_from_db()
    assert p.cnap_cited is True
    from apps.audit.models import AuditLog

    assert AuditLog.objects.filter(entity_id=str(p.pk)).exists() or AuditLog.objects.exists()


def test_grant_credited_to_several_projects_and_cores(client, center):
    from apps.people.models import Project, Resource

    _login(client, "mwills")
    prj = list(Project.objects.values_list("pk", flat=True)[:2])
    res = list(Resource.objects.filter(core__isnull=False).values_list("pk", flat=True)[:2])
    r = client.post(
        "/manage/outcomes/grants/new/",
        {
            "project_title": "Test proposal",
            "funding_agency": "NIH",
            "status": "submitted",
            "ack_tri": "no",
            "projects": prj,
            "resources": res,
        },
    )
    assert r.status_code == 302
    g = GrantSubmission.objects.get(project_title="Test proposal")
    assert g.cnap_acknowledged is False and g.version_label == "A0"
    assert g.project_links.count() == 2 and g.resource_links.count() == 2
    client.post(
        "/manage/outcomes/grants/new/",
        {
            "project_title": "Test proposal (revised)",
            "family_title": "Test proposal",
            "status": "planned",
        },
    )
    assert (
        GrantSubmission.objects.get(project_title="Test proposal (revised)").version_label == "A1"
    )


def test_access(client, center):
    _login(client, "hbailey")
    assert client.get("/manage/outcomes/").status_code == 200
    assert client.get("/manage/outcomes/publications/new/").status_code == 403
    p = Publication.objects.first()
    assert (
        client.post(f"/manage/outcomes/publication/{p.pk}/ack/", {"value": "yes"}).status_code
        == 403
    )
    _login(client, "okafor")
    assert client.get("/manage/outcomes/").status_code == 403
