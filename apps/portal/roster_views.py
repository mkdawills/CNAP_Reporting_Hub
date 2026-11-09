"""The roster check page behind each emailed link (MW 2026-11-06). No sign-in: the link is the key.

Shows names and roles only, never email addresses. Takes suggestions; changes nothing on the roster.
"""

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache

from apps.people.models import Core, Person, Project
from apps.reporting.models import RosterCheckLink, RosterSuggestion
from apps.reporting.services import roster_check as rc


@never_cache
def roster_check(request, token):
    link = get_object_or_404(
        RosterCheckLink.objects.select_related("person", "reporting_period"), token=token
    )
    p = link.reporting_period
    if not rc.is_open(link):
        return render(request, "portal/roster_check_closed.html", {"p": p}, status=410)
    if request.method == "POST":
        action = request.POST.get("action", "")
        from_name = request.POST.get("from_name", "").strip()[:200]
        note = request.POST.get("note", "").strip()[:2000]
        if action == "none":
            rc.mark_no_changes(link)
            messages.success(request, "Thank you. The evaluator now knows the roster looks right to you.")
        elif action == "left":
            person = Person.objects.filter(pk=request.POST.get("person") or 0).first()
            if not person:
                raise Http404
            rc.suggest(link, RosterSuggestion.Kind.LEFT, person=person, note=note, from_name=from_name)
            messages.success(request, f"Thank you. The evaluator will review your note about {person.full_name}.")
        elif action in ("new", "core_user", "other"):
            name = request.POST.get("name", "").strip()[:200]
            if action != "other" and not name:
                messages.error(request, "Write the person’s name.")
                return redirect(f"{request.path}#rc-add")
            if action == "other" and not note:
                messages.error(request, "Write what should change.")
                return redirect(f"{request.path}#rc-add")
            rc.suggest(
                link,
                action,
                name=name,
                role=request.POST.get("role", "").strip()[:200],
                project=Project.objects.filter(pk=request.POST.get("project") or 0).first(),
                core=Core.objects.filter(pk=request.POST.get("core") or 0).first(),
                note=note,
                from_name=from_name,
            )
            messages.success(request, "Thank you. The evaluator will review your suggestion.")
        return redirect(request.path)
    near, others = rc.roster(link)
    left_ids = set(link.suggestions.filter(kind=RosterSuggestion.Kind.LEFT).values_list("person_id", flat=True))
    return render(
        request,
        "portal/roster_check.html",
        {
            "link": link,
            "p": p,
            "near": near,
            "others": others,
            "left_ids": left_ids,
            "mine": link.suggestions.all(),
            "projects": Project.objects.filter(is_active=True).order_by("title"),
            "cores": Core.objects.order_by("name"),
            "closes": p.opens_at,
        },
    )
