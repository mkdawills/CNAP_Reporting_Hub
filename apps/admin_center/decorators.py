"""
Two gates for the administrator screens:
- @admin_view: any of the three Administrators may open the page;
- @manage_action: only the evaluator may change anything. The Director and
  Associate Director are refused on the server, not just shown no buttons.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_POST

from apps.accounts import access


def admin_view(fn):
    @login_required
    @wraps(fn)
    def wrapper(request, *args, **kwargs):
        if not access.can_view_admin(request.user):
            raise PermissionDenied
        return fn(request, *args, **kwargs)

    return wrapper


def manage_action(fn):
    @login_required
    @require_POST
    @wraps(fn)
    def wrapper(request, *args, **kwargs):
        if not access.can_manage(request.user):
            raise PermissionDenied("View-only administrators cannot make changes.")
        return fn(request, *args, **kwargs)

    return wrapper


def manage_page(fn):
    """A page whose GET shows a form for a change (new person, new period): evaluator only."""

    @login_required
    @wraps(fn)
    def wrapper(request, *args, **kwargs):
        if not access.can_manage(request.user):
            raise PermissionDenied("View-only administrators cannot make changes.")
        return fn(request, *args, **kwargs)

    return wrapper
