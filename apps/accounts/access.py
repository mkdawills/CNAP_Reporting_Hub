"""
Who may do what. Every view and service asks these questions instead of
checking roles or permissions directly, so the rules live in one place.

The three Administrators (decisions.md, 2026-10-24):
- the evaluator (Morgan Wills) manages the Center and reads everything with
  names: Administrator role + both direct grants;
- the Center Director and Associate Director view every administrator screen
  but change nothing: Center Leadership role + the confidential grant only.

Respondents are everyone else; they see their own tasks and history only.
"""

from apps.accounts.models import ApplicationRole

ADMIN_ROLES = (ApplicationRole.Code.ADMINISTRATOR, ApplicationRole.Code.CENTER_LEADERSHIP)


def _roles(user):
    if not getattr(user, "is_authenticated", False):
        return set()
    cache = user.__dict__.get("_role_code_cache")
    if cache is None:
        cache = set(user.user_roles.values_list("role__code", flat=True))
        user.__dict__["_role_code_cache"] = cache
    return cache


def can_view_admin(user):
    """May open the administrator screens at all (all three Administrators)."""
    return bool(_roles(user) & set(ADMIN_ROLES)) and user.is_enabled


def can_manage(user):
    """May change anything: people, relationships, periods, assignments, snapshots."""
    return (
        can_view_admin(user)
        and ApplicationRole.Code.ADMINISTRATOR in _roles(user)
        and user.has_perm("reporting.manage_center")
    )


def is_view_only_admin(user):
    return can_view_admin(user) and not can_manage(user)


def can_read_mentoring(user):
    """The four confidential mentoring forms: direct grant only."""
    return can_view_admin(user) and user.has_confidential_mentoring_access()


def can_read_identified_surveys(user):
    """Core, NeuroSync and Team Science responses with names: the evaluator only."""
    return can_view_admin(user) and user.has_identified_survey_access()


def admin_label(user):
    """Short description of the user's access for the sidebar."""
    if can_manage(user):
        return (
            "Administrator · full access"
            if can_read_identified_surveys(user)
            else ("Administrator")
        )
    if can_view_admin(user):
        return "Administrator · view only"
    return "Respondent"
