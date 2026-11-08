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
    "form:progress_pilot": "proto/progress_form.html",  # Screen 21; Batch 1 extends it to every form
    "preview": "proto/progress_form.html",  # Batch 1, screen 29: the same page in preview mode
    "dashboard": "proto/dashboard.html",  # Screen 53
    "results:mentee_survey": "proto/report.html",  # Screen 90; Batch 2 extends it to every form
    "outcomes": "proto/outcomes.html",  # Screen 36, progress tracks (prototype screen 5)
    # Batch 1 (MW 2026-11-05)
    "login": "proto/registration/login.html",  # screen 1
    "link": "proto/registration/link_request.html",  # screen 2
    "cp_check": "proto/portal/cp_check.html",  # screen 30
    # Batch 2 (MW 2026-11-05): results
    "results_list": "proto/results.html",  # screen 65
    "response": "proto/progress_form.html",  # screen 66: one response, read-only, in the form design
    "center_results": "proto/center_results.html",  # screens 32 and 33
    "builder": "proto/builder.html",  # Build a download (MW 2026-11-06)
    "launch": "proto/launch.html",
    # Core reports for core directors (MW 2026-11-08): the same templates, in the prototype look.
    "core_reports": "portal/core_reports.html",
    "core_report": "portal/core_report.html",  # Review before launch, redesigned (MW 2026-11-06)
}


def enabled(request):
    return bool(getattr(settings, "UI_PROTOTYPE", False)) and request.session.get("ui_view", "after") == "after"


def template(request, key, default):
    """The prototype template for a redesigned screen, or the original one."""
    if key.startswith("form:"):
        key = "form:progress_pilot"  # Batch 1 (MW 2026-11-05): every respondent form uses the Screen 21 design
    if key.startswith("results:"):
        key = "results:mentee_survey"  # Batch 2 (MW 2026-11-05): every form's results use the Screen 90 design
    if key in SCREENS and getattr(settings, "UI_PROTOTYPE", False):
        request.proto_screen = key  # lets base.html offer the before/after switch
        if enabled(request):
            request.proto_active = True
            request.proto_own = True  # this page has its own prototype template, so the admin skin stays off
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


class AdminSkin:
    """Batch 3 (MW 2026-11-06): every administration page takes the prototype look through one shared
    design layer, with its own template, data, and actions unchanged. Off unless UI_PROTOTYPE is on, and
    the reviewer can flip any page back to the current design. Pages that already have their own
    prototype template (the dashboard, results) keep it."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if getattr(settings, "UI_PROTOTYPE", False) and request.path.startswith("/manage/"):
            request.proto_screen = getattr(request, "proto_screen", None) or "admin"
            if enabled(request):
                request.proto_active = True
                request.proto_admin = True
        return self.get_response(request)
