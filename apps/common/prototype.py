"""The four-screen design prototype (MW 2026-11-05).

Everything here is off unless settings.UI_PROTOTYPE is True. With it off, every page renders
its original template and no prototype styles load. With it on, only these four screens switch
to their prototype templates, and the reviewer can flip each one back to the current design.

Prototype templates are presentation only: the views, data, questions, permissions, and form
actions are the same objects the original templates use.
"""

from django.conf import settings
from django.http import Http404
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

# screen key -> prototype template
SCREENS = {
    "tasks": "proto/tasks.html",  # Screen 3
    "form:progress_pilot": "proto/progress_form.html",  # Screen 21 (this form only)
    "dashboard": "proto/dashboard.html",  # Screen 53
    "results:mentee_survey": "proto/report.html",  # Screen 90 (this form only)
}


def enabled(request):
    return bool(getattr(settings, "UI_PROTOTYPE", False)) and request.session.get("ui_view", "after") == "after"


def template(request, key, default):
    """The prototype template for one of the four screens, or the original one."""
    if key in SCREENS and getattr(settings, "UI_PROTOTYPE", False):
        request.proto_screen = key  # lets base.html offer the before/after switch
        if enabled(request):
            request.proto_active = True
            return SCREENS[key]
    return default


def switch(request, view):
    """Flip between the current design ("before") and the prototype ("after") for review."""
    if not getattr(settings, "UI_PROTOTYPE", False) or view not in ("before", "after"):
        raise Http404
    request.session["ui_view"] = view
    nxt = request.GET.get("next") or "/"
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        nxt = "/"
    return redirect(nxt)
