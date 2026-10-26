"""Open for preview: forms are readable before opens_at, but nothing can be answered (decisions.md 2026-10-25)."""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.common.enums import PeriodStatus
from apps.reporting.models import ReportingPeriod
from apps.reporting.services import periods as ps
from apps.reporting.services import responses as rs


@pytest.fixture
def preview_period(db):
    from django.core.management import call_command

    call_command("seed", "--fictional", verbosity=0)
    p = ReportingPeriod.objects.get(status=PeriodStatus.DRAFT)
    now = timezone.now()
    p.opens_at = now + dt.timedelta(days=30)
    p.due_at = now + dt.timedelta(days=50)
    p.save()
    from apps.accounts.models import User

    ps.launch(User.objects.get(username="mwills"), p)
    return p


def test_preview_stage_and_locking(preview_period):
    p = preview_period
    assert p.in_preview and not p.accepting_responses
    assert ps.stage(p) == "preview"
    a = (
        p.assignments.filter(form_definition__code="bn_core_survey")
        .select_related("person__user")
        .first()
    )
    user = a.person.user
    assert not rs.is_editable(a, user)
    with pytest.raises(rs.LockedError):
        rs.quick_opt_out(a, user)


def test_preview_pages(client, preview_period):
    a = preview_period.assignments.select_related("person__user").first()
    client.force_login(a.person.user)
    r = client.get(reverse("portal:form", args=[a.pk]))
    assert r.status_code == 302 and r.url.endswith("/preview/")
    r = client.get(reverse("portal:preview", args=[a.pk]))
    assert r.status_code == 200 and "Answering opens" in r.content.decode()


def test_opens_by_itself(preview_period):
    p = preview_period
    p.opens_at = timezone.now() - dt.timedelta(minutes=1)
    p.save()
    assert p.accepting_responses and ps.stage(p) == "open"
