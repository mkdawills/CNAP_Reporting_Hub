"""Stevens Amendment statements in the "How to acknowledge CNAP" box (MW 2026-11-03): the funding level is the
author's own project, normally 100% federal, with their project's total award filled in by them."""

import pytest
from django.core.management import call_command

from apps.accounts.models import User


@pytest.fixture
def center(db):
    call_command("seed", "--fictional", verbosity=0)


def test_three_statements_with_a_fill_in_funding_level(client, center):
    client.force_login(User.objects.get(username="okafor"))
    page = client.get("/outcomes/new/pub/").content.decode()
    assert "Under the Stevens Amendment" in page and "award number P20GM113109" in page
    assert "100% of the total costs of this project ($[your project’s total award])" in page
    assert "0% ($0) were financed by nongovernmental sources" in page
    assert "does not necessarily represent the official views" in page
    page = client.get("/outcomes/presentations/new/").content.decode()
    assert "Research reported in this presentation" in page
