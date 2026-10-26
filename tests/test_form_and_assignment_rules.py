"""Review 15.1, 15.3, 15.7: assignments, scales, measures and rules."""

import datetime as dt

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.enums import ContextKind, QuestionType, RuleScope, ScaleKind
from apps.forms_engine.models import FormAssignmentRule, Measure, QuestionOption
from apps.reporting.models import Answer, Assignment, Response

from .conftest import make_form, make_question


def refused(func):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            func()


def assign(person, version, period, **kw):
    a = Assignment(
        person=person,
        form_version=version,
        reporting_period=period,
        source="manual",
        due_at=period.due_at,
        **kw,
    )
    a.save()
    return a


# --- assignments ------------------------------------------------------------


def test_duplicate_assignment_key_refused(okafor, forms, period):
    _, ni_v = forms["ni_survey"]
    assign(okafor, ni_v, period)
    refused(lambda: assign(okafor, ni_v, period))


def test_duplicate_assignment_key_refused_with_project(okafor, forms, period, projects):
    _, pmr_v = forms["pmr"]
    assign(okafor, pmr_v, period, project=projects["B"])
    refused(lambda: assign(okafor, pmr_v, period, project=projects["B"]))
    # a different project is a different assignment
    assign(okafor, pmr_v, period, project=projects["C"])


def test_universal_form_with_project_refused(okafor, forms, period, projects):
    _, ni_v = forms["ni_survey"]
    refused(lambda: assign(okafor, ni_v, period, project=projects["B"]))


def test_project_form_without_project_refused(okafor, forms, period):
    _, pmr_v = forms["pmr"]
    refused(lambda: assign(okafor, pmr_v, period))


def test_copied_form_definition_cannot_lie(okafor, forms, period):
    _, ni_v = forms["ni_survey"]
    mq, _ = forms["mq"]
    a = Assignment(
        person=okafor,
        form_version=ni_v,
        reporting_period=period,
        source="manual",
        due_at=period.due_at,
    )
    a.fill_copied_columns()
    a.form_definition = mq  # lie: version belongs to the NI survey
    refused(lambda: Assignment.objects.bulk_create([a]))


def test_exempt_needs_reason(okafor, forms, period):
    _, ni_v = forms["ni_survey"]
    a = assign(okafor, ni_v, period)
    a.status = "exempt"
    refused(a.save)
    a.exempt_reason = "Left CNAP in March"
    a.save()


def test_done_needs_pathway(okafor, forms, period):
    _, ni_v = forms["ni_survey"]
    a = assign(okafor, ni_v, period)
    a.status = "submitted"
    refused(a.save)


def test_response_must_match_assignment_version(okafor, forms, period):
    _, ni_v = forms["ni_survey"]
    _, mq_v = forms["mq"]
    a = assign(okafor, ni_v, period)
    r = Response(assignment=a)
    r.form_version = mq_v  # bypass save() which copies the right version
    refused(lambda: Response.objects.bulk_create([r]))


def test_one_current_response_per_assignment(okafor, forms, period):
    _, ni_v = forms["ni_survey"]
    a = assign(okafor, ni_v, period)
    Response.objects.create(assignment=a, is_current=True)
    refused(lambda: Response.objects.create(assignment=a, is_current=True))
    Response.objects.create(assignment=a, is_current=False)


# --- form assignment rules --------------------------------------------------


def test_universal_rule_on_project_form_refused(reference):
    fd, _, _ = make_form("bad_form", "Bad form", context=ContextKind.PROJECT)
    refused(
        lambda: FormAssignmentRule.objects.create(form_definition=fd, scope=RuleScope.UNIVERSAL)
    )


def test_per_context_rule_with_mismatched_context_refused(reference):
    """A Core survey (context none) cannot be assigned per project to Pilot Mentors."""
    fd, _, _ = make_form("plain_form", "Plain form")
    t = reference["types"]
    refused(
        lambda: FormAssignmentRule.objects.create(
            form_definition=fd,
            scope=RuleScope.RELATIONSHIP,
            relationship_type=t["pilot_mentor"],
            per_context=True,
        )
    )


def test_per_context_rule_copied_context_cannot_lie(reference):
    fd, _, _ = make_form("proj_form", "Project form", context=ContextKind.PROJECT)
    t = reference["types"]
    rule = FormAssignmentRule(
        form_definition=fd,
        scope=RuleScope.RELATIONSHIP,
        relationship_type=t["core_director"],
        per_context=True,
    )
    rule.form_context_kind = "project"
    rule.relationship_context_kind = "project"  # lie: core_director is core-scoped
    refused(lambda: FormAssignmentRule.objects.bulk_create([rule]))


def test_same_form_same_type_rule_once(reference, forms):
    mq, _ = forms["mq"]
    t = reference["types"]
    refused(
        lambda: FormAssignmentRule.objects.create(
            form_definition=mq, scope=RuleScope.RELATIONSHIP, relationship_type=t["pilot_mentor"]
        )
    )


# --- scales and measures ----------------------------------------------------


def test_option_question_needs_answer_set(forms, reference):
    _, _, section = make_form("scale_form", "Scale form")
    refused(lambda: make_question(section, "q1", answer_set=None, qtype=QuestionType.LIKERT))


def test_text_question_cannot_have_answer_set(forms, reference):
    _, _, section = make_form("scale_form", "Scale form")
    refused(
        lambda: make_question(
            section, "q1", answer_set=reference["scales"]["Agreement"], qtype=QuestionType.LONG_TEXT
        )
    )


def test_measure_scale_must_match_answer_set(reference):
    _, _, section = make_form("scale_form", "Scale form")
    freq_measure = Measure.objects.create(
        code="m_freq", name="Frequency measure", scale_kind=ScaleKind.FREQUENCY
    )
    refused(
        lambda: make_question(
            section, "q1", answer_set=reference["scales"]["Agreement"], measure=freq_measure
        )
    )
    agree_measure = Measure.objects.create(
        code="m_agree", name="Agreement measure", scale_kind=ScaleKind.AGREEMENT
    )
    make_question(section, "q1", answer_set=reference["scales"]["Agreement"], measure=agree_measure)


def test_copied_scale_kind_cannot_lie(reference):
    _, _, section = make_form("scale_form", "Scale form")
    from apps.forms_engine.models import Question

    q = Question(
        form_section=section,
        code="q1",
        prompt="p",
        question_type=QuestionType.LIKERT,
        answer_set=reference["scales"]["Agreement"],
    )
    q.fill_copied_columns()
    q.scale_kind = "quality"  # lie
    refused(lambda: Question.objects.bulk_create([q]))


def test_na_option_has_no_value(reference):
    refused(
        lambda: QuestionOption.objects.create(
            answer_set=reference["scales"]["Agreement"],
            code="bad",
            label="bad",
            value=3,
            is_na_option=True,
        )
    )


def test_frozen_option_cannot_be_relabelled(okafor, forms, period, reference):
    """The trigger: once an answer references an option, its label/value/code are frozen."""
    ni, ni_v = forms["ni_survey"]
    section = ni_v.sections.get()
    q = make_question(section, "q_quality", answer_set=reference["scales"]["Quality"])
    good = reference["scales"]["Quality"].options.get(code="good")
    a = Assignment(
        person=okafor,
        form_version=ni_v,
        reporting_period=period,
        source="manual",
        due_at=period.due_at,
    )
    a.save()
    r = Response.objects.create(assignment=a)
    Answer.objects.create(response=r, question=q, option=good)
    good.label = "4 - Pretty good"
    refused(good.save)
    # Untouched options in the same set can still be edited (sort order is not frozen either).
    poor = reference["scales"]["Quality"].options.get(code="poor")
    poor.sort_order = 99
    poor.save()


def test_answer_uses_at_most_one_value(okafor, forms, period, reference):
    ni, ni_v = forms["ni_survey"]
    section = ni_v.sections.get()
    q = make_question(section, "q_quality", answer_set=reference["scales"]["Quality"])
    a = Assignment(
        person=okafor,
        form_version=ni_v,
        reporting_period=period,
        source="manual",
        due_at=period.due_at,
    )
    a.save()
    r = Response.objects.create(assignment=a)
    good = reference["scales"]["Quality"].options.get(code="good")
    refused(
        lambda: Answer.objects.create(response=r, question=q, option=good, value_text="also text")
    )


def test_one_active_version_per_form(reference):
    from apps.forms_engine.models import FormVersion

    fd, v1, _ = make_form("one_active", "One active")
    refused(lambda: FormVersion.objects.create(form_definition=fd, version_no=2, status="active"))
    FormVersion.objects.create(form_definition=fd, version_no=2, status="draft")


def test_grant_submission_versions_are_system_set(db):
    from apps.outcomes.models import GrantFamily, GrantSubmission

    fam = GrantFamily.objects.create(title="Plasticity R01")
    a0 = GrantSubmission.objects.create(grant_family=fam, project_title="Plasticity R01")
    a1 = GrantSubmission.objects.create(
        grant_family=fam, project_title="Plasticity R01", resubmission_of=a0
    )
    assert (a0.version_label, a1.version_label) == ("A0", "A1")


def test_publication_substatus_only_when_submitted(db):
    from apps.outcomes.models import Publication

    refused(
        lambda: Publication.objects.create(
            title="T", publication_type="journal_article", status="planned", substatus="accepted"
        )
    )
    Publication.objects.create(
        title="T", publication_type="journal_article", status="submitted", substatus="accepted"
    )


def test_period_display_order_and_status_checks(db):
    from apps.reporting.models import ReportingPeriod

    now = timezone.now()
    p = ReportingPeriod.objects.create(
        name="Y9 June",
        short_label="Y9B",
        grant_year=9,
        sequence=2,
        start_date=dt.date(2025, 12, 1),
        end_date=dt.date(2026, 5, 31),
        opens_at=now,
        due_at=now,
        status="open",
    )
    assert p.display_order == 92
    p.status = "closed"
    refused(p.save)  # closed needs closed_at
    p.closed_at = now
    p.save()
