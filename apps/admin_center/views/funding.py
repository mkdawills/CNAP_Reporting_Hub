"""The CNAP office's Funding pages (MW 2026-11-10): follow-up letters, the opportunity catalog and each
person's matches, members' suggestions, and funding news. Nothing is emailed until MW presses Send and
confirms. Spec: docs/funding-follow-up-spec.md.
"""

from datetime import date

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts import access
from apps.audit.models import AuditLog, record_event
from apps.common.enums import FundingAudience, FundingMilestone, FundingSourceKind
from apps.outcomes import funding
from apps.outcomes.models import (
    FundingBulletin,
    FundingEvent,
    FundingFollowUp,
    FundingMatch,
    FundingNewsItem,
    FundingOpportunity,
    FundingQuestion,
    FundingSuggestion,
)
from apps.people.models import Person

from ..decorators import admin_view, manage_action

TABS = [
    ("followups", "Follow-ups"),
    ("opportunities", "Opportunities and matches"),
    ("suggestions", "Suggestions"),
    ("news", "News"),
    ("events", "Events and talks"),
    ("questions", "Questions"),
]


def _tab_url(tab, anchor=""):
    return f"{reverse('manage:funding_manage')}?tab={tab}{anchor}"


def _date(value):
    try:
        return date.fromisoformat((value or "").strip()) if value else None
    except ValueError:
        return None


BULLETIN_NAME = "K-State Research Weekly"


def _bulletin(request):
    """The newsletter issue an item came from: an existing issue, a new one, or none (MW 2026-11-10)."""
    pick = request.POST.get("bulletin", "")
    if pick.isdigit():
        return FundingBulletin.objects.filter(pk=pick).first()
    if pick == "new":
        day = _date(request.POST.get("bulletin_date"))
        if not day:
            return None
        name = request.POST.get("bulletin_name", "").strip()[:200] or BULLETIN_NAME
        url = request.POST.get("bulletin_url", "").strip()[:500]
        if url and not url.startswith(("http://", "https://")):
            url = "https://" + url
        b, _ = FundingBulletin.objects.get_or_create(
            name=name, issue_date=day, defaults={"url": url}
        )
        if url and not b.url:
            b.url = url
            b.save(update_fields=["url", "updated_at"])
        return b
    return None


def _bulletins():
    return FundingBulletin.objects.order_by("-issue_date")[:20]


@admin_view
def home(request):
    tab = request.GET.get("tab") if request.GET.get("tab") in dict(TABS) else "followups"
    today = timezone.localdate()
    show = request.GET.get("show", "open")
    fus = FundingFollowUp.objects.select_related("grant", "person").order_by("-created_at")
    if show == "open":
        fus = fus.filter(status=FundingFollowUp.Status.TO_REVIEW)
    opps = []
    for o in (
        FundingOpportunity.objects.active().order_by("name").prefetch_related("matches__person")
    ):
        who = sorted(
            (m.person for m in o.matches.all() if not m.ended_at),
            key=lambda p: (p.last_name, p.first_name),
        )
        opps.append(
            {
                "o": o,
                "n": len(who),
                "who": who,
                "stale": funding.stale(o, today),
                "row": funding.row(o, today=today),
            }
        )
    opps.sort(key=lambda x: (x["o"].audience != FundingAudience.EVERYONE, x["o"].name.lower()))
    people = {}
    for x in opps:
        for p in x["who"]:
            people.setdefault(p.pk, [p, 0])[1] += 1
    by_person = sorted(people.values(), key=lambda v: (v[0].last_name, v[0].first_name))
    # By member (MW 2026-11-10): each member with the opportunities picked for them, soonest deadline first.
    members = {}
    for m in FundingMatch.objects.filter(
        ended_at__isnull=True, opportunity__archived_at__isnull=True
    ).select_related("person", "opportunity"):
        members.setdefault(m.person_id, {"p": m.person, "rows": []})["rows"].append(
            {"m": m, "row": funding.row(m.opportunity, why=m.why, today=today)}
        )
    for v in members.values():
        v["rows"].sort(key=lambda r: funding._sort_key(r["row"]["o"]))
    members = sorted(members.values(), key=lambda v: (v["p"].last_name, v["p"].first_name))
    c = funding.counts()
    return render(
        request,
        "manage/funding.html",
        {
            "tab": tab,
            "tabs": TABS,
            "show": show,
            "followups": [(f, funding.status_changed(f)) for f in fus],
            "opps": opps,
            "n_stale": sum(1 for x in opps if x["stale"]),
            "by_person": by_person,
            "members": members,
            "view": "members" if request.GET.get("view") == "members" else "opps",
            "suggestions": FundingSuggestion.objects.select_related(
                "person", "opportunity"
            ).order_by("status", "-created_at"),
            "news": FundingNewsItem.objects.active()
            .select_related("bulletin")
            .order_by("-pinned", "-news_date"),
            "events": FundingEvent.objects.active()
            .select_related("bulletin")
            .order_by("starts_on"),
            "today": today,
            "questions": FundingQuestion.objects.active(),
            "counts": c,
            "can_manage": access.can_manage(request.user),
            "archived_opps": FundingOpportunity.objects.filter(archived_at__isnull=False).count(),
        },
    )


# --------------------------------------------------------------------------- follow-ups and the letter


@admin_view
def followup(request, pk):
    f = get_object_or_404(FundingFollowUp.objects.select_related("grant", "person"), pk=pk)
    featured = set(f.opportunities.values_list("pk", flat=True))
    mine = {m.opportunity_id: m.why for m in funding.open_matches(f.person)}
    choices = []
    for o in FundingOpportunity.objects.active():
        if o.pk in mine or o.audience == FundingAudience.EVERYONE:
            choices.append(
                {
                    "r": funding.row(o, why=mine.get(o.pk, "")),
                    "on": o.pk in featured,
                    "mine": o.pk in mine,
                }
            )
    choices.sort(key=lambda x: (not x["mine"], funding._sort_key(x["r"]["o"])))
    to, cc = funding.recipients(f)
    return render(
        request,
        "manage/funding_followup.html",
        {
            **funding.letter_parts(f),
            "choices": choices,
            "default_opening": funding.default_opening(f),
            "default_signoff": funding.SIGNOFF,
            "to": to,
            "cc": cc,
            "confirm": request.GET.get("confirm") == "send",
            "changed": funding.status_changed(f),
            "can_manage": access.can_manage(request.user),
        },
    )


@manage_action
def followup_post(request, pk):
    f = get_object_or_404(FundingFollowUp, pk=pk)
    action = request.POST.get("action", "save")
    back = reverse("manage:funding_followup", args=[f.pk])
    if f.status == FundingFollowUp.Status.SENT and action not in ("noop",):
        messages.error(request, "The letter was already sent, so it can no longer change.")
        return redirect(back)
    if action == "dismiss":
        reason = request.POST.get("reason", "").strip()
        if not reason:
            messages.error(request, "Write a reason, then select Dismiss again.")
            return redirect(back + "#fu-dismiss")
        f.status, f.dismissed_reason = FundingFollowUp.Status.DISMISSED, reason
        f.save(update_fields=["status", "dismissed_reason", "updated_at"])
        record_event(
            request.user, AuditLog.Action.UPDATE, f, new={"status": "dismissed", "reason": reason}
        )
        messages.success(request, "Dismissed.")
        return redirect(_tab_url("followups"))
    if action == "reopen":
        f.status, f.dismissed_reason = FundingFollowUp.Status.TO_REVIEW, ""
        f.save(update_fields=["status", "dismissed_reason", "updated_at"])
        record_event(request.user, AuditLog.Action.UPDATE, f, new={"status": "to_review"})
        messages.success(request, "Back on the list.")
        return redirect(back)
    if f.status == FundingFollowUp.Status.DISMISSED:
        messages.error(request, "Put the follow-up back on the list first.")
        return redirect(back)
    # Save the composer every time, so nothing typed is lost before Send.
    f.subject = request.POST.get("subject", "").strip()[:300]
    if f.subject == funding.letter_name(f.grant):
        f.subject = ""
    opening = request.POST.get("opening", "").strip()
    f.opening = "" if opening == funding.default_opening(f) else opening
    f.body_note = request.POST.get("body_note", "").strip()
    f.closing = request.POST.get("closing", "").strip()
    signoff = request.POST.get("signoff", "").strip()
    f.signoff = "" if signoff == funding.SIGNOFF else signoff
    f.save()
    ids = [int(x) for x in request.POST.getlist("opp") if x.isdigit()]
    f.opportunities.set(FundingOpportunity.objects.filter(pk__in=ids))
    record_event(request.user, AuditLog.Action.UPDATE, f, new={"saved": True, "featured": ids})
    if action == "send":
        return redirect(back + "?confirm=send#fu-send")
    if action == "send_yes":
        try:
            funding.send(f, request.user)
        except funding.AlreadySent:
            messages.error(request, "The letter was already sent.")
            return redirect(back)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect(back)
        messages.success(request, f"Sent. {f.person} can read the letter in the Hub.")
        return redirect(_tab_url("followups"))
    messages.success(request, "Saved.")
    return redirect(back)


@admin_view
def followup_email(request, pk):
    """The email exactly as it will go, for the preview frame."""
    f = get_object_or_404(FundingFollowUp, pk=pk)
    subject, text, html = funding.render_email(f)
    if request.GET.get("format") == "text":
        return HttpResponse(text, content_type="text/plain; charset=utf-8")
    return HttpResponse(html)


# --------------------------------------------------------------------------- the opportunity catalog and matches

FIELDS = [
    "name",
    "sponsor",
    "mechanism",
    "amount_text",
    "deadline_text",
    "url",
    "summary",
    "fuller_text",
    "source_url",
]


@admin_view
def opportunity(request, pk=None):
    o = get_object_or_404(FundingOpportunity, pk=pk) if pk else None
    initial = {}
    s = None
    if not o and request.GET.get("suggestion"):
        s = FundingSuggestion.objects.filter(pk=request.GET["suggestion"]).first()
        if s:
            initial = {
                "name": s.name,
                "sponsor": s.sponsor,
                "url": s.url,
                "deadline_text": s.deadline_text,
                "summary": s.why,
                "audience": FundingAudience.EVERYONE if s.for_everyone else FundingAudience.MATCHED,
            }
    matches = (
        o.matches.select_related("person").order_by("ended_at", "person__last_name") if o else []
    )
    taken = {m.person_id for m in matches if not m.ended_at}
    return render(
        request,
        "manage/funding_opportunity.html",
        {
            "o": o,
            "initial": initial,
            "suggestion": s,
            "kinds": FundingSourceKind.choices,
            "milestones": FundingMilestone.choices,
            "audiences": FundingAudience.choices,
            "matches": matches,
            "people": Person.objects.filter(archived_at__isnull=True, is_active=True)
            .exclude(pk__in=taken)
            .order_by("last_name", "first_name"),
            "can_manage": access.can_manage(request.user),
            "stale": funding.stale(o) if o else False,
            "bulletins": _bulletins(),
            "bulletin_name": BULLETIN_NAME,
        },
    )


@manage_action
def opportunity_post(request, pk=None):
    o = get_object_or_404(FundingOpportunity, pk=pk) if pk else None
    action = request.POST.get("action", "save")
    if o and action == "archive":
        o.archived_at = timezone.now()
        o.save(update_fields=["archived_at", "updated_at"])
        record_event(request.user, AuditLog.Action.UPDATE, o, new={"archived": True})
        messages.success(request, "Archived. Members no longer see the opportunity.")
        return redirect(_tab_url("opportunities"))
    if o and action == "restore":
        o.archived_at = None
        o.save(update_fields=["archived_at", "updated_at"])
        record_event(request.user, AuditLog.Action.UPDATE, o, new={"archived": False})
        messages.success(request, "Restored.")
        return redirect("manage:funding_opportunity", o.pk)
    if o and action == "match":
        person = Person.objects.filter(pk=request.POST.get("person") or 0).first()
        if not person:
            messages.error(request, "Choose a person, then select Add the match again.")
        elif FundingMatch.objects.filter(
            opportunity=o, person=person, ended_at__isnull=True
        ).exists():
            messages.error(request, f"{person} is already matched to the opportunity.")
        else:
            funding.add_match(o, person, request.POST.get("why", "").strip(), request.user)
            messages.success(
                request, f"Added. {person} now sees the opportunity under Picked for you."
            )
        return redirect(reverse("manage:funding_opportunity", args=[o.pk]) + "#fo-matches")
    if o and action == "end_match":
        m = get_object_or_404(
            FundingMatch, pk=request.POST.get("match"), opportunity=o, ended_at__isnull=True
        )
        m.ended_at = timezone.now()
        m.save(update_fields=["ended_at"])
        record_event(request.user, AuditLog.Action.UPDATE, m, new={"ended": True})
        messages.success(request, f"Ended. {m.person} no longer sees the opportunity.")
        if request.POST.get("back") == "person":
            return redirect(reverse("manage:person", args=[m.person_id]) + "#funding")
        return redirect(reverse("manage:funding_opportunity", args=[o.pk]) + "#fo-matches")
    data = {k: request.POST.get(k, "").strip() for k in FIELDS}
    if not data["name"]:
        messages.error(request, "Write the opportunity’s name, then select Save again.")
        return redirect(
            request.META.get("HTTP_REFERER") or reverse("manage:funding_opportunity_new")
        )
    for k in ("url", "source_url"):
        if data[k] and not data[k].startswith(("http://", "https://")):
            data[k] = "https://" + data[k]
    kind = request.POST.get("source_kind")
    ms = request.POST.get("counts_toward_milestone")
    aud = request.POST.get("audience")
    data.update(
        source_kind=kind if kind in FundingSourceKind.values else FundingSourceKind.FOUNDATION,
        counts_toward_milestone=ms if ms in FundingMilestone.values else FundingMilestone.NO,
        audience=aud if aud in FundingAudience.values else FundingAudience.MATCHED,
        esi_only=bool(request.POST.get("esi_only")),
        deadline=_date(request.POST.get("deadline")),
        checked_on=_date(request.POST.get("checked_on")),
        bulletin=_bulletin(request),
    )
    if o:
        old = {k: getattr(o, k) for k in data}
        for k, v in data.items():
            setattr(o, k, v)
        o.save()
        record_event(
            request.user,
            AuditLog.Action.UPDATE,
            o,
            old={k: str(v) for k, v in old.items()},
            new={k: str(v) for k, v in data.items()},
        )
        messages.success(request, "Saved.")
        return redirect("manage:funding_opportunity", o.pk)
    o = FundingOpportunity.objects.create(created_by=request.user, **data)
    record_event(request.user, AuditLog.Action.CREATE, o, new={"name": o.name})
    s = FundingSuggestion.objects.filter(
        pk=request.POST.get("suggestion") or 0, status=FundingSuggestion.Status.TO_REVIEW
    ).first()
    if s:
        o.suggested_by = s.person
        o.save(update_fields=["suggested_by", "updated_at"])
        s.status, s.opportunity, s.handled_by, s.handled_at = (
            FundingSuggestion.Status.ADDED,
            o,
            request.user,
            timezone.now(),
        )
        s.note_to_person = request.POST.get("note_to_person", "").strip() or s.note_to_person
        s.save()
        record_event(
            request.user, AuditLog.Action.UPDATE, s, new={"status": "added", "opportunity": o.pk}
        )
    messages.success(request, "Added.")
    return redirect("manage:funding_opportunity", o.pk)


@manage_action
def person_match(request, pk):
    """The Funding panel on a person's page: pick an opportunity for the person."""
    person = get_object_or_404(Person, pk=pk)
    o = FundingOpportunity.objects.active().filter(pk=request.POST.get("opportunity") or 0).first()
    if not o:
        messages.error(request, "Choose an opportunity, then select Add again.")
    elif FundingMatch.objects.filter(opportunity=o, person=person, ended_at__isnull=True).exists():
        messages.error(request, f"{person} is already matched to the opportunity.")
    else:
        funding.add_match(o, person, request.POST.get("why", "").strip(), request.user)
        messages.success(request, f"Added. {person} now sees the opportunity under Picked for you.")
    return redirect(reverse("manage:person", args=[person.pk]) + "#funding")


# --------------------------------------------------------------------------- suggestions


@manage_action
def suggestion_post(request, pk):
    s = get_object_or_404(FundingSuggestion, pk=pk)
    action = request.POST.get("action")
    if action == "decline":
        s.status, s.handled_by, s.handled_at = (
            FundingSuggestion.Status.DECLINED,
            request.user,
            timezone.now(),
        )
        s.note_to_person = request.POST.get("note", "").strip()
        s.save()
        record_event(request.user, AuditLog.Action.UPDATE, s, new={"status": "declined"})
        messages.success(request, "Declined.")
    elif action == "reopen":
        s.status, s.handled_by, s.handled_at = FundingSuggestion.Status.TO_REVIEW, None, None
        s.save()
        record_event(request.user, AuditLog.Action.UPDATE, s, new={"status": "to_review"})
        messages.success(request, "Back on the list.")
    return redirect(_tab_url("suggestions"))


# --------------------------------------------------------------------------- news


@admin_view
def news_edit(request, pk=None):
    n = get_object_or_404(FundingNewsItem, pk=pk) if pk else None
    return render(
        request,
        "manage/funding_news.html",
        {
            "n": n,
            "can_manage": access.can_manage(request.user),
            "bulletins": _bulletins(),
            "bulletin_name": BULLETIN_NAME,
        },
    )


@manage_action
def news_post(request, pk=None):
    n = get_object_or_404(FundingNewsItem, pk=pk) if pk else None
    action = request.POST.get("action", "save")
    if n and action in ("pin", "unpin"):
        n.pinned = action == "pin"
        n.save(update_fields=["pinned", "updated_at"])
        record_event(request.user, AuditLog.Action.UPDATE, n, new={"pinned": n.pinned})
        messages.success(request, "Pinned." if n.pinned else "Unpinned.")
        return redirect(_tab_url("news"))
    if n and action == "archive":
        n.archived_at = timezone.now()
        n.save(update_fields=["archived_at", "updated_at"])
        record_event(request.user, AuditLog.Action.UPDATE, n, new={"archived": True})
        messages.success(request, "Archived.")
        return redirect(_tab_url("news"))
    data = {
        "headline": request.POST.get("headline", "").strip()[:300],
        "summary": request.POST.get("summary", "").strip(),
        "news_date": _date(request.POST.get("news_date")),
        "date_text": request.POST.get("date_text", "").strip()[:100],
        "source_name": request.POST.get("source_name", "").strip()[:200],
        "source_url": request.POST.get("source_url", "").strip()[:500],
        "pinned": bool(request.POST.get("pinned")),
        "bulletin": _bulletin(request),
    }
    if not data["headline"] or not data["summary"]:
        messages.error(request, "Write the headline and the summary, then select Save again.")
        return redirect(request.META.get("HTTP_REFERER") or reverse("manage:funding_news_new"))
    if data["source_url"] and not data["source_url"].startswith(("http://", "https://")):
        data["source_url"] = "https://" + data["source_url"]
    if n:
        for k, v in data.items():
            setattr(n, k, v)
        n.save()
        record_event(request.user, AuditLog.Action.UPDATE, n, new={"headline": n.headline})
        messages.success(request, "Saved.")
    else:
        n = FundingNewsItem.objects.create(posted_by=request.user, **data)
        record_event(request.user, AuditLog.Action.CREATE, n, new={"headline": n.headline})
        messages.success(request, "Added.")
    return redirect(_tab_url("news"))


# --------------------------------------------------------------------------- events and talks


@admin_view
def event_edit(request, pk=None):
    e = get_object_or_404(FundingEvent, pk=pk) if pk else None
    return render(
        request,
        "manage/funding_event.html",
        {
            "e": e,
            "can_manage": access.can_manage(request.user),
            "bulletins": _bulletins(),
            "bulletin_name": BULLETIN_NAME,
        },
    )


@manage_action
def event_post(request, pk=None):
    e = get_object_or_404(FundingEvent, pk=pk) if pk else None
    if e and request.POST.get("action") == "archive":
        e.archived_at = timezone.now()
        e.save(update_fields=["archived_at", "updated_at"])
        record_event(request.user, AuditLog.Action.UPDATE, e, new={"archived": True})
        messages.success(request, "Archived.")
        return redirect(_tab_url("events"))
    starts, ends = _date(request.POST.get("starts_on")), _date(request.POST.get("ends_on"))
    title = request.POST.get("title", "").strip()[:300]
    if not title or not starts:
        messages.error(request, "Write the title and pick the date, then select Save again.")
        return redirect(request.META.get("HTTP_REFERER") or reverse("manage:funding_event_new"))
    if ends and ends < starts:
        messages.error(
            request,
            "The last day comes before the first day. Fix the dates, then select Save again.",
        )
        return redirect(request.META.get("HTTP_REFERER") or reverse("manage:funding_event_new"))
    url = request.POST.get("url", "").strip()[:500]
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    data = {
        "title": title,
        "starts_on": starts,
        "ends_on": ends if ends and ends != starts else None,
        "time_text": request.POST.get("time_text", "").strip()[:120],
        "place": request.POST.get("place", "").strip()[:300],
        "host": request.POST.get("host", "").strip()[:200],
        "summary": request.POST.get("summary", "").strip(),
        "url": url,
        "bulletin": _bulletin(request),
    }
    if e:
        for k, v in data.items():
            setattr(e, k, v)
        e.save()
        record_event(request.user, AuditLog.Action.UPDATE, e, new={"title": e.title})
        messages.success(request, "Saved.")
    else:
        e = FundingEvent.objects.create(posted_by=request.user, **data)
        record_event(request.user, AuditLog.Action.CREATE, e, new={"title": e.title})
        messages.success(request, "Added.")
    return redirect(_tab_url("events"))


# --------------------------------------------------------------------------- the seven questions


@manage_action
def questions_post(request):
    """MW edits the questions' titles and wording without a code change."""
    for q in FundingQuestion.objects.active():
        title = request.POST.get(f"title_{q.pk}", "").strip()
        text = request.POST.get(f"text_{q.pk}", "").strip()
        if title and text and (title != q.title or text != q.text):
            old = {"title": q.title, "text": q.text}
            q.title, q.text = title[:120], text
            q.save()
            record_event(
                request.user,
                AuditLog.Action.UPDATE,
                q,
                old=old,
                new={"title": q.title, "text": q.text},
            )
    messages.success(request, "Saved.")
    return redirect(_tab_url("questions"))
