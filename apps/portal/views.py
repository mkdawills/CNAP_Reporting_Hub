from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.accounts import access


@login_required
def home(request):
    """Send people where they work: respondents to My tasks, administrators to their home."""
    person = request.user.person
    if person.current_relationships().exists():
        return redirect("portal:tasks")
    if access.can_view_admin(request.user):
        return redirect("manage:home")
    return render(request, "portal/no_tasks.html")


@login_required
def tasks(request):
    return render(request, "portal/placeholder.html", {"title": "My tasks"})


@login_required
def history(request):
    return render(request, "portal/placeholder.html", {"title": "My history"})


@login_required
def center_results(request):
    return render(request, "portal/placeholder.html", {"title": "Center results"})


@login_required
def profile(request):
    return render(request, "portal/placeholder.html", {"title": "Profile"})
