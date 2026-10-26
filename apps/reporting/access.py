"""
Who may read another person's responses (decisions.md, 2026-10-22 and 2026-10-24).

- Respondents: never another person's answers. Their own only, on the portal.
- The evaluator (view_identified_survey_responses + view_confidential_mentoring_data):
  every response, with names.
- The Center Director and Associate Director (confidential grant, no identified grant):
  * the four mentoring forms and both progress reports: with names;
  * core, NeuroSync and Team Science surveys: de-identified ("Respondent n",
    shuffled per form and period), and only when at least SMALL_N_THRESHOLD
    people completed that survey in that period.
- Anyone else (no such person today): nothing row-level.

Written answers follow the same rule: they are readable only by the writer and
these three Administrators.
"""

import hashlib

from django.conf import settings

from apps.accounts import access
from apps.common.enums import COMPLETE_STATUSES, ConfidentialityClass, FormCategory

IDENTIFIED = "identified"
DEIDENTIFIED = "deidentified"


def form_access(user, form_definition):
    """How `user` may read other people's responses to this form: IDENTIFIED, DEIDENTIFIED or None."""
    if not access.can_view_admin(user):
        return None
    mentoring = form_definition.confidentiality_class == ConfidentialityClass.MENTORING
    if mentoring and not user.has_confidential_mentoring_access():
        return None
    if user.has_identified_survey_access():
        return IDENTIFIED
    if mentoring or form_definition.category == FormCategory.REPORT:
        return IDENTIFIED if user.has_confidential_mentoring_access() else None
    return DEIDENTIFIED if user.has_confidential_mentoring_access() else None


def response_access(user, assignment):
    if assignment.person_id == getattr(user, "person_id", None):
        return IDENTIFIED
    return form_access(user, assignment.form_definition)


def deidentified_rows_allowed(form_definition, period):
    """Small-group safeguard: de-identified individual responses only when n >= threshold."""
    done = form_definition.assignments.filter(
        reporting_period=period, status__in=COMPLETE_STATUSES
    ).count()
    return done >= settings.SMALL_N_THRESHOLD


def respondent_label_order(assignments, form_definition, period):
    """A stable shuffle per form and period, so "Respondent 3" can't be followed across forms."""
    salt = f"{settings.SECRET_KEY}:{form_definition.pk}:{period.pk}"
    return sorted(assignments, key=lambda a: hashlib.sha256(f"{salt}:{a.pk}".encode()).hexdigest())


def can_see_names_on_dashboard(user, form_definition):
    """The period dashboard lists names only where the viewer may read those responses with names."""
    return form_access(user, form_definition) == IDENTIFIED
