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
    email = forms.EmailField(required=False, label="E-mail")
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
                    "last name and e-mail."
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
