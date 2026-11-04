"""Person documents, such as a signed Statement of Work (MW 2026-11-03)."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from apps.accounts.models import User
from apps.people.models import Person, PersonDocument


@pytest.fixture
def center(db):
    call_command("seed", "--fictional", verbosity=0)


def _login(client, username):
    client.force_login(User.objects.get(username=username))


def _pdf():
    return SimpleUploadedFile("sow.pdf", b"%PDF-1.4 fictional", content_type="application/pdf")


def test_admin_adds_and_person_sees(client, center):
    _login(client, "mwills")
    p = Person.objects.get(user__username="okafor")
    r = client.post(
        f"/manage/people/{p.pk}/documents/add/",
        {"title": "Statement of Work, Year 10", "excerpt": "Deliver one presentation that cites CNAP support.", "file": _pdf()},
        follow=True,
    )
    assert r.status_code == 200
    d = PersonDocument.objects.get(person=p)
    assert d.title.startswith("Statement of Work")
    page = client.get(f"/manage/people/{p.pk}/").content.decode()
    assert "Documents on file" in page and "Statement of Work, Year 10" in page
    # the person sees it on their profile and My tasks
    _login(client, "okafor")
    page = client.get("/profile/").content.decode()
    assert "Your documents" in page and "Statement of Work, Year 10" in page
    page = client.get("/tasks/").content.decode()
    assert "Your commitments, from your Statement of Work" in page
    assert "one presentation that cites CNAP support" in page
    r = client.get(f"/profile/documents/{d.pk}/")
    assert r.status_code == 200


def test_document_is_private_to_its_person(client, center):
    _login(client, "mwills")
    p = Person.objects.get(user__username="okafor")
    client.post(
        f"/manage/people/{p.pk}/documents/add/",
        {"title": "Statement of Work", "excerpt": "", "file": _pdf()},
    )
    d = PersonDocument.objects.get(person=p)
    _login(client, "varga")
    assert client.get(f"/profile/documents/{d.pk}/").status_code == 403
