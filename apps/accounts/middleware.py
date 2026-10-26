"""End link sessions that must not exist (decisions.md 2026-10-26, security review)."""

from django.contrib.auth import logout
from django.shortcuts import redirect

from . import signin


class LinkSessionGuard:
    """A session started by an emailed link ends if its account becomes an administrator, staff, superuser or is
    disabled; administrators must sign in with single sign-on and two-factor."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and request.session.get("signed_in_by_link")
            and not signin.link_session_allowed(user)
        ):
            logout(request)
            return redirect("login")
        return self.get_response(request)
