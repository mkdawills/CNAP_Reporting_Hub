"""
Shared fixtures. Tests run against a real PostgreSQL 16 database (never
SQLite): the constraints under test exist only there. pytest-django creates a
test database from DATABASE_URL in .env and applies every migration.
"""

import datetime as dt

import pytest
from django.utils import timezone

from apps.accounts.models import ApplicationRole, User, UserRole
from apps.admin_center.reference_data import seed_reference_data
from apps.common.enums import (
    ContextKind,
    FormCategory,
    PeriodStatus,
    ProjectKind,
    QuestionType,
    RuleScope,
)
from apps.forms_engine.models import (
    AnswerSet,
    FormAssignmentRule,
    FormDefinition,
    FormSection,
    FormVersion,
    Question,
)
from apps.people.models import (
    Core,
    Person,
    PersonEmail,
    PersonRelationship,
    Project,
    RelationshipType,
)
from apps.reporting.models import ReportingPeriod


@pytest.fixture
def reference(db):
    """Roles, cores, resources, relationship types, shared scales, pathways."""
    seed_reference_data()
    return {
        "cores": {c.code: c for c in Core.objects.all()},
        "types": {t.code: t for t in RelationshipType.objects.all()},
        "scales": {a.name: a for a in AnswerSet.objects.filter(is_shared=True)},
        "roles": {r.code: r for r in ApplicationRole.objects.all()},
    }


def make_person(first, last, email=None):
    person = Person.objects.create(first_name=first, last_name=last, institution="K-State")
    PersonEmail.objects.create(
        person=person, email=email or f"{first}.{last}@k-state.example".lower(), is_primary=True
    )
    return person


def make_user(person, username=None, password="Test-Password-2026", role=None):
    user = User.objects.create_user(
        username=username or person.last_name.lower(),
        email=person.primary_email,
        password=password,
        person=person,
        first_name=person.first_name,
        last_name=person.last_name,
    )
    if role:
        UserRole.objects.create(user=user, role=role)
    return user


def relate(person, rtype, *, project=None, core=None, start=dt.date(2026, 1, 1), end=None):
    rel = PersonRelationship(
        person=person,
        relationship_type=rtype,
        project=project,
        core=core,
        effective_from=start,
        effective_to=end,
    )
    rel.save()
    return rel


@pytest.fixture
def projects(db):
    return {
        "A": Project.objects.create(title="Project A (primary)", kind=ProjectKind.PRIMARY),
        "B": Project.objects.create(title="Project B (pilot)", kind=ProjectKind.PILOT),
        "C": Project.objects.create(title="Project C (pilot)", kind=ProjectKind.PILOT),
    }


@pytest.fixture
def okafor(reference, projects):
    """
    Dr. Nadia Okafor (fictional, review 15.8): Primary Project Leader on A,
    Pilot Mentor on B, NI Core Director, General CNAP Member.
    """
    t = reference["types"]
    person = make_person("Nadia", "Okafor")
    relate(person, t["project_leader"], project=projects["A"])
    relate(person, t["pilot_mentor"], project=projects["B"])
    relate(person, t["core_director"], core=reference["cores"]["NI"])
    relate(person, t["cnap_member"])
    return person


@pytest.fixture
def period(db):
    now = timezone.now()
    return ReportingPeriod.objects.create(
        name="Year 10, January 2027",
        short_label="Y10A",
        grant_year=10,
        sequence=1,
        start_date=dt.date(2026, 6, 1),
        end_date=dt.date(2026, 11, 30),
        opens_at=now,
        due_at=now + dt.timedelta(days=30),
        status=PeriodStatus.OPEN,
    )


def make_form(
    code,
    name,
    *,
    context=ContextKind.NONE,
    category=FormCategory.SURVEY,
    about_core=None,
    activate=True,
):
    fd = FormDefinition.objects.create(
        code=code, name=name, category=category, context_kind=context, about_core=about_core
    )
    fv = FormVersion.objects.create(
        form_definition=fd, version_no=1, status="active" if activate else "draft"
    )
    section = FormSection.objects.create(form_version=fv, code="main", title="Main", sort_order=1)
    return fd, fv, section


@pytest.fixture
def forms(reference):
    """A universal survey, a per-project mentor report, and a per-person mentor questionnaire."""
    t = reference["types"]
    ni = reference["cores"]["NI"]
    ni_survey, ni_v, _ = make_form("ni_core_survey", "NI Core Survey", about_core=ni)
    FormAssignmentRule.objects.create(
        form_definition=ni_survey,
        scope=RuleScope.UNIVERSAL,
        excluded_relationship_type=t["core_director"],
    )
    pmr, pmr_v, _ = make_form(
        "pilot_mentor_report",
        "Pilot Mentor Report",
        context=ContextKind.PROJECT,
        category=FormCategory.REPORT,
    )
    FormAssignmentRule.objects.create(
        form_definition=pmr,
        scope=RuleScope.RELATIONSHIP,
        relationship_type=t["pilot_mentor"],
        per_context=True,
    )
    mq, mq_v, _ = make_form("mentor_questionnaire", "Mentor Questionnaire")
    FormAssignmentRule.objects.create(
        form_definition=mq, scope=RuleScope.RELATIONSHIP, relationship_type=t["pilot_mentor"]
    )
    FormAssignmentRule.objects.create(
        form_definition=mq, scope=RuleScope.RELATIONSHIP, relationship_type=t["primary_mentor"]
    )
    return {"ni_survey": (ni_survey, ni_v), "pmr": (pmr, pmr_v), "mq": (mq, mq_v)}


def make_question(section, code, answer_set=None, qtype=QuestionType.LIKERT, measure=None, **kw):
    q = Question(
        form_section=section,
        code=code,
        prompt=f"Prompt {code}",
        question_type=qtype,
        answer_set=answer_set,
        measure=measure,
        **kw,
    )
    q.save()
    return q
