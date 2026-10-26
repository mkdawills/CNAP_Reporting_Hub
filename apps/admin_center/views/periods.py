"""Reporting periods, review before launch, and the period dashboard (Milestones 5 and 7)."""

import datetime as dt

from django import forms
from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts import access
from apps.analytics import snapshots
from apps.audit.models import AuditLog, record_event
from apps.common.enums import COMPLETE_STATUSES, AssignmentStatus, PeriodStatus
from apps.forms_engine.models import FormDefinition
from apps.people.models import Person, Project
from apps.people.services import is_external, is_on_roster
from apps.reporting.access import can_see_names_on_dashboard
from apps.reporting.models import Assignment, ReportingPeriod
from apps.reporting.services import assignments as asg
from apps.reporting.services import periods as ps
from apps.reporting.services import responses as rs

from ..decorators import admin_view, manage_action, manage_page


def _period_from(request):
    label = request.GET.get("period")
    qs = ReportingPeriod.objects.order_by("-display_order")
    p = qs.filter(short_label=label).first() if label else None
    return (
        p
        or qs.filter(status=PeriodStatus.OPEN).first()
        or qs.exclude(status=PeriodStatus.DRAFT).first()
        or qs.first()
    )


def lifecycle(period):
    current = ps.stage(period)
    keys = [k for k, _ in ps.STAGES]
    idx = keys.index(current)
    return [
        {
            "n": i + 1,
            "label": label,
            "state": "done" if i < idx or current == "finalized" else ("now" if i == idx else ""),
        }
        for i, (_, label) in enumerate(ps.STAGES)
    ]


# --------------------------------------------------------------------------- periods


class PeriodForm(forms.ModelForm):
    class Meta:
        model = ReportingPeriod
        fields = [
            "name",
            "short_label",
            "grant_year",
            "sequence",
            "start_date",
            "end_date",
            "opens_at",
            "due_at",
            "notes",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "opens_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "due_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {
            "opens_at": "Opens",
            "due_at": "Due",
            "sequence": "Sequence (1 = January, 2 = June)",
        }


@admin_view
def periods(request):
    rows = []
    for p in ReportingPeriod.objects.order_by("-display_order"):
        historical = (
            p.snapshots.filter(provenance="aggregate_import").exists()
            and not p.assignments.exists()
        )
        rows.append(
            {
                "p": p,
                "steps": lifecycle(p),
                "stage": ps.stage(p),
                "historical": historical,
                "snapshots": list(p.snapshots.order_by("version_no")),
            }
        )
    return render(request, "manage/periods.html", {"rows": rows})


@manage_page
def period_new(request):
    last = ReportingPeriod.objects.order_by("-display_order").first()
    initial = {}
    if last:
        gy, seq = (last.grant_year, 2) if last.sequence == 1 else (last.grant_year + 1, 1)
        initial = {
            "grant_year": gy,
            "sequence": seq,
            "short_label": f"Y{gy} {'Jan' if seq == 1 else 'June'}",
        }
    form = PeriodForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        p = form.save(commit=False)
        p.status = PeriodStatus.DRAFT
        p.save()
        record_event(request.user, AuditLog.Action.CREATE, p)
        messages.success(
            request, f"{p.short_label} created. Review who will receive forms before you launch it."
        )
        return redirect("manage:launch", p.pk)
    return render(request, "manage/period_new.html", {"form": form})


@manage_action
def period_action(request, pk):
    p = get_object_or_404(ReportingPeriod, pk=pk)
    action = request.POST.get("action")
    try:
        if action == "close":
            ps.close(request.user, p)
            messages.success(
                request, f"{p.short_label} is closed. Generate results when you’re ready."
            )
        elif action == "reopen":
            ps.reopen(request.user, p, reason=request.POST.get("reason", ""))
            messages.success(request, f"{p.short_label} is open again.")
        elif action == "generate":
            snap = snapshots.generate(request.user, p, reason=request.POST.get("reason", ""))
            messages.success(
                request,
                f"Results generated (version {snap.version_no}). Review them, then mark them reviewed.",
            )
        elif action == "reviewed":
            snapshots.mark_reviewed(request.user, snapshots.latest(p))
            messages.success(
                request, "Marked reviewed. Finalize to make these the official results."
            )
        elif action == "finalize":
            snapshots.finalize(request.user, snapshots.latest(p))
            messages.success(
                request,
                f"{p.short_label} results are finalized. Respondents can now see the combined results.",
            )
        else:
            messages.error(request, "Unknown action.")
    except (ps.PeriodError, snapshots.SnapshotError) as exc:
        messages.error(request, str(exc))
    return redirect("manage:periods")


# --------------------------------------------------------------------------- review before launch

GROUPS = [
    ("member", "General members", "On the roster, with no project, mentoring or core role."),
    ("rpl", "Research Project Leaders (RPL)", "Also mentees: they receive the Mentee Survey."),
    ("ppl", "Pilot Project Leaders (PPL)", "Also mentees: they receive the Mentee Survey."),
    (
        "mentor",
        "Mentors",
        "Internal and external. People outside K-State sign in with an emailed link.",
    ),
    ("director", "Core directors", "They don’t receive the survey about their own core."),
    (
        "extcore",
        "External core users",
        "Not on the roster. Their own core’s survey is pinned first.",
    ),
]


def _groups_for(codes):
    g = []
    if "project_leader" in codes:
        g.append("rpl")
    if "pilot_awardee" in codes:
        g.append("ppl")
    if codes & {"pilot_mentor", "primary_mentor"}:
        g.append("mentor")
    if "core_director" in codes:
        g.append("director")
    if "core_user" in codes and "cnap_member" not in codes:
        g.append("extcore")
    return g or ["member"]


@admin_view
def launch(request, pk):
    p = get_object_or_404(ReportingPeriod, pk=pk)
    on = asg.generation_date(p)
    plan = asg.plan(p, on)
    forms_by_id = {f.pk: f for f in FormDefinition.objects.all()}
    projects = {pr.pk: pr for pr in Project.objects.all()}
    by_person = {}
    for x in plan:
        by_person.setdefault(x.person_id, []).append(x)
    people = {
        pp.pk: pp for pp in Person.objects.filter(pk__in=by_person).prefetch_related("emails")
    }
    rows_by_group = {k: [] for k, *_ in GROUPS}
    for pid in sorted(by_person, key=lambda i: (people[i].last_name, people[i].first_name)):
        person = people[pid]
        codes = set(
            person.current_relationships(on).values_list("relationship_type__code", flat=True)
        )
        groups = _groups_for(codes)
        chips = []
        for x in by_person[pid]:
            fd = forms_by_id[x.form_definition_id]
            ctx = projects[x.project_id].title if x.project_id else ""
            chips.append(
                {
                    "label": (fd.display or {}).get("short_name") or fd.name,
                    "ctx": ctx,
                    "report": fd.category == "report",
                }
            )
        row = {
            "person": person,
            "chips": chips,
            "external": is_external(person),
            "on_roster": "cnap_member" in codes,
            "also": [t for k, t, _ in GROUPS if k in groups],
        }
        for g in groups:
            rows_by_group[g].append(row)
    warnings = []
    for pr in Project.objects.active().filter(is_active=True):
        lead = "pilot_awardee" if pr.kind == "pilot" else "project_leader"
        ment = "pilot_mentor" if pr.kind == "pilot" else "primary_mentor"
        current = pr.relationships.filter(effective_from__lte=on).filter(
            Q(effective_to__isnull=True) | Q(effective_to__gte=on)
        )
        if not current.filter(relationship_type__code=lead).exists():
            warnings.append(
                {
                    "text": f"{pr.title} has no project leader, so no progress report or Mentee Survey will go out for it.",
                    "url": f"/manage/projects/{pr.pk}/",
                }
            )
        if not current.filter(relationship_type__code=ment).exists():
            warnings.append(
                {
                    "text": f"{pr.title} has no mentor recorded, so no mentor report will go out for it.",
                    "url": f"/manage/projects/{pr.pk}/",
                }
            )
    for pid, person in people.items():
        if not person.primary_email:
            warnings.append(
                {
                    "text": f"{person} has no e-mail on file, so they can’t receive their forms or sign-in link.",
                    "url": f"/manage/people/{pid}/",
                }
            )
    totals = {}
    for x in plan:
        totals[x.form_definition_id] = totals.get(x.form_definition_id, 0) + 1
    total_rows = sorted(
        ((forms_by_id[k], v) for k, v in totals.items()), key=lambda t: t[0].sort_order
    )
    groups = [
        {"key": k, "title": t, "note": n, "rows": rows_by_group[k]}
        for k, t, n in GROUPS
        if rows_by_group[k]
    ]
    return render(
        request,
        "manage/launch.html",
        {
            "p": p,
            "groups": groups,
            "warnings": warnings,
            "totals": total_rows,
            "people_n": len(by_person),
            "forms_n": len(plan),
            "draft": p.status == PeriodStatus.DRAFT,
            "on": on,
        },
    )


@manage_action
def launch_go(request, pk):
    p = get_object_or_404(ReportingPeriod, pk=pk)
    try:
        result = ps.launch(request.user, p)
    except ps.PeriodError as exc:
        messages.error(request, str(exc))
        return redirect("manage:launch", pk)
    messages.success(request, f"{p.short_label} is open. {result.created} forms were assigned.")
    return redirect(f"/manage/dashboard/?period={p.short_label}")


@manage_action
def roster_from_launch(request, pk, person_pk):
    from apps.people.services import RelationshipError, add_to_roster

    person = get_object_or_404(Person, pk=person_pk)
    try:
        add_to_roster(request.user, person)
        messages.success(request, f"{person} is now on the CNAP roster.")
    except RelationshipError as exc:
        messages.error(request, str(exc))
    return redirect("manage:launch", pk)


# --------------------------------------------------------------------------- dashboard


@admin_view
def dashboard(request):
    p = _period_from(request)
    if not p:
        return render(request, "manage/dashboard.html", {"p": None})
    qs = Assignment.objects.filter(reporting_period=p).select_related(
        "form_definition", "person", "project", "core", "completion_pathway"
    )
    by_form = qs.values("form_definition").annotate(
        assigned=Count("id", filter=~Q(status=AssignmentStatus.EXEMPT)),
        done=Count("id", filter=Q(status__in=COMPLETE_STATUSES)),
        optout=Count("id", filter=Q(status=AssignmentStatus.COMPLETED_OPT_OUT)),
        exempt=Count("id", filter=Q(status=AssignmentStatus.EXEMPT)),
    )
    forms_by_id = {f.pk: f for f in FormDefinition.objects.all()}
    form_rows = sorted(
        [
            {
                "fd": forms_by_id[r["form_definition"]],
                **r,
                "pct": round(100 * r["done"] / r["assigned"]) if r["assigned"] else 0,
            }
            for r in by_form
        ],
        key=lambda r: r["fd"].sort_order,
    )
    named = {fd.pk for fd in forms_by_id.values() if can_see_names_on_dashboard(request.user, fd)}
    f_form = request.GET.get("form", "")
    f_status = request.GET.get("status", "")
    rows = qs.filter(form_definition_id__in=named)
    if f_form:
        rows = rows.filter(form_definition__code=f_form)
    if f_status == "complete":
        rows = rows.filter(status__in=COMPLETE_STATUSES)
    elif f_status:
        rows = rows.filter(status=f_status)
    rows = rows.order_by("person__last_name", "form_definition__sort_order")
    total = qs.exclude(status=AssignmentStatus.EXEMPT).count()
    done = qs.filter(status__in=COMPLETE_STATUSES).count()
    return render(
        request,
        "manage/dashboard.html",
        {
            "p": p,
            "periods": ReportingPeriod.objects.exclude(status=PeriodStatus.DRAFT)
            .filter(assignments__isnull=False)
            .distinct()
            .order_by("-display_order"),
            "steps": lifecycle(p),
            "form_rows": form_rows,
            "rows": rows[:300],
            "rows_n": rows.count(),
            "total": total,
            "done": done,
            "pct": round(100 * done / total) if total else 0,
            "exempt_n": qs.filter(status=AssignmentStatus.EXEMPT).count(),
            "named_forms": [
                forms_by_id[i] for i in sorted(named, key=lambda i: forms_by_id[i].sort_order)
            ],
            "hidden_names": len(named) < len(form_rows) or not named,
            "f_form": f_form,
            "f_status": f_status,
            "is_open": p.status == PeriodStatus.OPEN,
        },
    )


@manage_action
def assignment_action(request, pk):
    a = get_object_or_404(Assignment, pk=pk)
    action = request.POST.get("action")
    try:
        if action == "exempt":
            asg.exempt(request.user, a, request.POST.get("reason", ""))
            messages.success(request, f"Exempted {a.person} from {a.form_definition.name}.")
        elif action == "unexempt":
            asg.remove_exemption(request.user, a)
            messages.success(request, "Exemption removed.")
        elif action == "reopen":
            rs.reopen(request.user, a, reason=request.POST.get("reason", ""))
            messages.success(
                request,
                f"Reopened {a.form_definition.name} for {a.person}. Their answers are kept.",
            )
        elif action == "generate":
            result = asg.generate(a.reporting_period, request.user)
            messages.success(
                request, f"{result.created} new forms assigned; {result.existing} already existed."
            )
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect(
        request.POST.get("next") or f"/manage/dashboard/?period={a.reporting_period.short_label}"
    )


@manage_action
def generate_assignments(request, pk):
    p = get_object_or_404(ReportingPeriod, pk=pk)
    if p.status != PeriodStatus.OPEN:
        messages.error(request, "Assignments can be generated only while the period is open.")
    else:
        result = asg.generate(p, request.user)
        messages.success(
            request,
            f"{result.created} new forms assigned. {result.existing} already existed and were left as they were.",
        )
    return redirect(f"/manage/dashboard/?period={p.short_label}")


def _unused():
    return dt, timezone, access, is_on_roster
