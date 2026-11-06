"""NeuroSync speakers (MW 2026-11-03): list each talk; the speaker gets the Speaker Survey when it ends."""

import datetime as dt

from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.audit.models import AuditLog, record_event
from apps.people import services as people
from apps.people.models import Person
from apps.reporting.models import SpeakerTalk
from apps.reporting.services import speakers

from ..decorators import admin_view, manage_action


class TalkForm(forms.Form):
    speaker = forms.ModelChoiceField(
        queryset=Person.objects.filter(is_active=True, archived_at__isnull=True).order_by(
            "last_name", "first_name"
        ),
        required=False,
        label="Speaker already in the Hub",
        empty_label="Choose a person, or add a new speaker below",
    )
    first_name = forms.CharField(required=False, label="First name")
    last_name = forms.CharField(required=False, label="Last name")
    email = forms.EmailField(required=False, label="Email")
    institution = forms.CharField(required=False, label="Institution")
    title = forms.CharField(max_length=300, label="Talk title")
    day = forms.DateField(label="Date of the talk", widget=forms.DateInput(attrs={"type": "date"}))
    ends = forms.TimeField(label="Time the talk ends", widget=forms.TimeInput(attrs={"type": "time"}))
    auto_send = forms.BooleanField(
        required=False, initial=True, label="Send the survey automatically when the talk ends"
    )

    def clean(self):
        d = super().clean()
        if not d.get("speaker"):
            missing = [f for f in ("first_name", "last_name", "email") if not d.get(f)]
            if missing:
                raise forms.ValidationError(
                    "Choose a speaker who is already in the Hub, or give a new speaker’s first name, "
                    "last name and email."
                )
        return d


@admin_view
def talks(request):
    form = TalkForm(initial={"auto_send": True})
    now = timezone.now()
    rows = SpeakerTalk.objects.select_related("speaker", "assignment").order_by("-ends_at")[:200]
    return render(
        request,
        "manage/speakers.html",
        {
            "form": form,
            "upcoming": [t for t in rows if t.ends_at > now and not t.sent_at],
            "past": [t for t in rows if t.ends_at <= now or t.sent_at],
            "open_period": speakers.period_for(now),
            "now": now,
        },
    )


@manage_action
def talk_add(request):
    form = TalkForm(request.POST)
    if not form.is_valid():
        for e in form.non_field_errors() + [
            f"{form.fields[k].label}: {v[0]}" for k, v in form.errors.items() if k != "__all__"
        ]:
            messages.error(request, e)
        return redirect("manage:speakers")
    d = form.cleaned_data
    p = d["speaker"]
    if not p:
        try:
            p = people.create_person(
                request.user,
                first_name=d["first_name"],
                last_name=d["last_name"],
                email=d["email"],
                institution=d["institution"],
            )
        except people.RelationshipError as exc:
            messages.error(request, str(exc))
            return redirect("manage:speakers")
    ends = timezone.make_aware(dt.datetime.combine(d["day"], d["ends"]))
    t = SpeakerTalk.objects.create(
        speaker=p, title=d["title"].strip(), ends_at=ends, auto_send=d["auto_send"], created_by=request.user
    )
    record_event(request.user, AuditLog.Action.CREATE, t, new={"talk": t.title})
    if d["auto_send"]:
        messages.success(
            request,
            f"Added. {p.first_name} gets the survey at {timezone.localtime(ends):%-I:%M %p} on "
            f"{ends:%B} {ends.day}, when the talk ends.",
        )
    else:
        messages.success(request, "Added. Use Send the survey now when the talk is over.")
    return redirect("manage:speakers")


@manage_action
def talk_send(request, pk):
    t = get_object_or_404(SpeakerTalk, pk=pk)
    try:
        email = speakers.send(t, request.user)
    except speakers.SpeakerError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"Sent the survey to {email}.")
    return redirect("manage:speakers")


@manage_action
def talk_remove(request, pk):
    t = get_object_or_404(SpeakerTalk, pk=pk)
    if t.sent_at:
        messages.error(request, "This survey has already been sent, so the talk stays on the list.")
    else:
        record_event(request.user, AuditLog.Action.ARCHIVE, t, old={"talk": t.title, "removed": True})
        t.delete()
        messages.success(request, "Removed.")
    return redirect("manage:speakers")


TALK_COLS = [
    "First name",
    "Last name",
    "Email",
    "Institution",
    "Talk title",
    "Date of the talk",
    "Time the talk ends",
    "Send the survey automatically (Yes or No)",
]


@admin_view
def talk_template(request):
    """An Excel template for a whole semester of talks (MW 2026-11-03)."""
    import io

    from django.http import HttpResponse
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "NeuroSync talks"
    for col, name in enumerate(TALK_COLS, start=1):
        c = ws.cell(row=1, column=col, value=name)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="4B2A84")
        c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[c.column_letter].width = 22
    for r in range(2, 202):
        ws.cell(row=r, column=6).number_format = "mm/dd/yyyy"
        ws.cell(row=r, column=7).number_format = "h:mm AM/PM"
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "A2"
    out = io.BytesIO()
    wb.save(out)
    resp = HttpResponse(
        out.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = 'attachment; filename="NeuroSync_talks_template.xlsx"'
    return resp


@manage_action
def talk_upload(request):
    """Create talks from a filled-in template. Existing people are matched by email."""
    import datetime as _dt

    from openpyxl import load_workbook

    from apps.people.models import PersonEmail

    up = request.FILES.get("sheet")
    if not up or not up.name.lower().endswith((".xlsx", ".xlsm")):
        messages.error(request, "Upload the filled-in Excel template (.xlsx).")
        return redirect("manage:speakers")
    try:
        ws = load_workbook(up, read_only=True, data_only=True).worksheets[0]
    except Exception:  # noqa: BLE001 - any unreadable workbook
        messages.error(request, "That Excel file couldn’t be opened. Use the template.")
        return redirect("manage:speakers")
    it = ws.iter_rows(values_only=True)
    header = [str(h or "").strip().lower() for h in (next(it, None) or ())]

    def col(name, alts=()):
        for key in (name.lower(), *[a.lower() for a in alts]):
            for i, h in enumerate(header):
                if key in h:
                    return i
        return None

    idx = {
        "first": col("first"),
        "last": col("last"),
        "email": col("email", ("email",)),
        "inst": col("institution"),
        "title": col("talk title", ("title",)),
        "day": col("date"),
        "ends": col("time"),
        "auto": col("automatic", ("send",)),
    }
    if idx["last"] is None or idx["title"] is None or idx["day"] is None:
        messages.error(
            request,
            "The first row doesn’t match the template’s column names. Download the template and copy your list into it.",
        )
        return redirect("manage:speakers")
    made, problems = 0, []
    for n, values in enumerate(it, start=2):
        values = list(values or ())

        def v(key):
            i = idx[key]
            return values[i] if i is not None and i < len(values) else None

        if not any(str(x or "").strip() for x in values):
            continue
        first, last = str(v("first") or "").strip(), str(v("last") or "").strip()
        email = str(v("email") or "").strip()
        title = str(v("title") or "").strip()
        day, ends = v("day"), v("ends")
        if not (last and title and day):
            problems.append(f"Row {n}: it needs at least a last name, a talk title, and a date.")
            continue
        if isinstance(day, _dt.datetime):
            day = day.date()
        elif not isinstance(day, _dt.date):
            try:
                day = _dt.datetime.strptime(str(day).strip(), "%m/%d/%Y").date()
            except ValueError:
                problems.append(f"Row {n}: the date needs to look like 09/30/2026.")
                continue
        if isinstance(ends, _dt.datetime):
            ends = ends.time()
        elif not isinstance(ends, _dt.time):
            t = str(ends or "").strip().upper().replace(".", "")
            ends = None
            for fmt in ("%I:%M %p", "%H:%M", "%I %p"):
                try:
                    ends = _dt.datetime.strptime(t, fmt).time()
                    break
                except ValueError:
                    pass
            if ends is None:
                ends = _dt.time(17, 0)  # no time given: 5:00 PM
        p = None
        if email:
            row = PersonEmail.objects.filter(email__iexact=email).select_related("person").first()
            p = row.person if row else None
        if p is None:
            if not (first and email):
                problems.append(
                    f"Row {n}: {last} isn’t in the Hub yet, so the row needs a first name and an email."
                )
                continue
            try:
                p = people.create_person(
                    request.user,
                    first_name=first,
                    last_name=last,
                    email=email,
                    institution=str(v("inst") or "").strip(),
                )
            except people.RelationshipError as exc:
                problems.append(f"Row {n}: {exc}")
                continue
        auto = str(v("auto") or "yes").strip().lower() not in ("no", "n", "false", "0")
        t = SpeakerTalk.objects.create(
            speaker=p,
            title=title,
            ends_at=timezone.make_aware(dt.datetime.combine(day, ends)),
            auto_send=auto,
            created_by=request.user,
        )
        record_event(request.user, AuditLog.Action.CREATE, t, new={"talk": t.title, "sheet": True})
        made += 1
    if made:
        messages.success(request, f"Added {made} talk{'s' if made != 1 else ''} from your sheet.")
    for pb in problems[:8]:
        messages.error(request, pb)
    if len(problems) > 8:
        messages.error(request, f"...and {len(problems) - 8} more rows had problems.")
    if not made and not problems:
        messages.error(request, "Your sheet has no rows filled in under the column names.")
    return redirect("manage:speakers")
