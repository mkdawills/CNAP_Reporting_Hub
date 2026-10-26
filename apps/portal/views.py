from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def home(request):
    """Landing page. My Tasks arrives in Milestone 5; the administrator home in Milestone 7."""
    return render(request, "portal/home.html")
