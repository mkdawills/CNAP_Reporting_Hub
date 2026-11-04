"""Roster import: upload, review each row, commit (Milestone 2)."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.common.enums import ImportMatchKind, ImportStatus
from apps.people import roster_import
from apps.reporting.models import RosterImport

from ..decorators import admin_view, manage_action
from ..forms import RosterUploadForm


@admin_view
def roster_imports(request):
    form = RosterUploadForm()
    return render(
        request,
        "manage/roster_imports.html",
        {"form": form, "imports": RosterImport.objects.select_related("uploaded_by")[:20]},
    )


@manage_action
def roster_upload(request):
    form = RosterUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Choose a .csv or .xlsx file to upload.")
        return redirect("manage:roster_imports")
    try:
        imp = roster_import.parse(request.user, form.cleaned_data["file"])
    except roster_import.RosterFileError as exc:
        messages.error(request, str(exc))
        return redirect("manage:roster_imports")
    return redirect("manage:roster_import", imp.pk)


@admin_view
def roster_review(request, pk):
    imp = get_object_or_404(RosterImport, pk=pk)
    rows = imp.rows.select_related("matched_person").order_by("match_kind", "row_number")
    groups = []
    for kind, title, note in [
        (
            ImportMatchKind.POSSIBLE_DUPLICATE,
            "Possible duplicates",
            "Same name as someone already here, but a different email. Choose for each one.",
        ),
        (
            ImportMatchKind.NEW,
            "New people",
            "Not in the Reporting Hub yet. They’ll be added and put on the roster.",
        ),
        (
            ImportMatchKind.MATCHED,
            "Already here",
            "Matched by email. Anyone not already on the roster will be added to it.",
        ),
        (
            ImportMatchKind.MISSING,
            "On the roster but not in this file",
            "They stay on the roster unless you choose to end their membership.",
        ),
    ]:
        g = [r for r in rows if r.match_kind == kind]
        if g:
            groups.append(
                {
                    "kind": kind,
                    "title": title,
                    "note": note,
                    "rows": g,
                    "choices": sorted(roster_import.VALID_DECISIONS[kind]),
                }
            )
    return render(
        request,
        "manage/roster_review.html",
        {
            "imp": imp,
            "groups": groups,
            "parsed": imp.status == ImportStatus.PARSED,
            "undecided": roster_import.undecided(imp).count(),
        },
    )


@manage_action
def roster_decide(request, pk):
    imp = get_object_or_404(RosterImport, pk=pk, status=ImportStatus.PARSED)
    errors = []
    for row in imp.rows.all():
        val = request.POST.get(f"row-{row.pk}")
        if val is not None and val != row.decision:
            try:
                roster_import.set_decision(row, val)
            except roster_import.RosterFileError as exc:
                errors.append(str(exc))
    if errors:
        messages.error(request, " ".join(errors))
    if request.POST.get("commit"):
        try:
            done = roster_import.commit(request.user, imp)
        except roster_import.RosterFileError as exc:
            messages.error(request, str(exc))
            return redirect("manage:roster_import", pk)
        messages.success(
            request,
            f"Import committed. {done['created']} people created. {done['added_to_roster']} added to the roster. "
            f"{done['merged']} merged. {done['ended']} memberships ended.",
        )
        return redirect("manage:roster_import", pk)
    if request.POST.get("discard"):
        roster_import.discard(request.user, imp)
        messages.success(request, "Import discarded. Nothing was changed.")
        return redirect("manage:roster_imports")
    messages.success(request, "Choices saved.")
    return redirect("manage:roster_import", pk)
