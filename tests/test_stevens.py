"""Stevens Amendment statement in the "How to acknowledge CNAP" box (MW 2026-11-02)."""

import pytest
from django.core.management import call_command

from apps.accounts.models import User
from apps.outcomes.models import FundingStatement


@pytest.fixture
def center(db):
    call_command("seed", "--fictional", verbosity=0)


def test_statement_uses_the_saved_figures(client, center):
    client.force_login(User.objects.get(username="okafor"))
    page = client.get("/outcomes/new/pub/").content.decode()
    assert "award number P20GM113109" in page and "does not necessarily represent" in page
    assert "Ask the CNAP office" in page  # no figures yet
    client.force_login(User.objects.get(username="mwills"))
    client.post("/manage/funding/", {"federal_total": "$11,250,000", "nonfederal_total": "250,000"})
    f = FundingStatement.current()
    assert f.federal_total == 11250000 and f.nonfederal_total == 250000
    client.force_login(User.objects.get(username="okafor"))
    page = client.get("/outcomes/new/presentation/").content.decode()
    assert "Research reported in this presentation" in page
    assert "Federal funds paid for 98% ($11,250,000)" in page and "2% ($250,000)" in page
    assert "Ask the CNAP office" not in page
    # view-only administrators can't change it; bad input is refused
    client.force_login(User.objects.get(username="hbailey"))
    assert client.post("/manage/funding/", {"federal_total": "1"}).status_code == 403
    client.force_login(User.objects.get(username="mwills"))
    client.post("/manage/funding/", {"federal_total": "lots"})
    assert FundingStatement.current().federal_total == 11250000
