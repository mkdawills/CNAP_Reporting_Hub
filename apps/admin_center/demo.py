"""
The fictional sample center (manage.py seed --fictional).

Every respondent here is invented. The three Administrator accounts use the
real names MW gave (decisions.md) with example.edu addresses; give them real
addresses and K-State sign-in when the site goes live.

Creates: people and relationships, logins (password DEMO_PASSWORD), the
Year 10 January period (open, with assignments and some fictional answers)
and Year 10 June (waiting for review before launch).
"""

import datetime as dt
import random

from django.contrib.auth.models import Permission
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import ApplicationRole, User, UserRole
from apps.common.enums import AssignmentStatus, PeriodStatus, ProjectKind
from apps.forms_engine.runtime import FormSchema
from apps.people import services
from apps.people.models import Core, Person, PersonEmail, Project
from apps.reporting.models import Answer, Assignment, ReportingPeriod, Response
from apps.reporting.services import assignments as asg

DEMO_PASSWORD = "Demo-Password-2026"
KSU = "Kansas State University"

PEOPLE = [
    # username, first, last, institution
    ("okafor", "Amara", "Okafor", KSU),
    ("varga", "Elena", "Varga", KSU),
    ("reyes", "Tomás", "Reyes", KSU),
    ("natarajan", "Priya", "Natarajan", KSU),
    ("whitfield", "Samuel", "Whitfield", KSU),
    ("kim", "Hana", "Kim", KSU),
    ("bell", "Marcus", "Bell", KSU),
    ("lee", "Jordan", "Lee", KSU),
    ("chen", "Riley", "Chen", KSU),
    ("adeyemi", "Tobi", "Adeyemi", KSU),
    ("moreau", "Claire", "Moreau", KSU),
    ("santos", "Luis", "Santos", "University of Nebraska Medical Center"),
    ("ferris", "Nadia", "Ferris", "Wichita State University"),
    ("lindqvist", "Ingrid", "Lindqvist", KSU),
    ("osei", "Kofi", "Osei", KSU),
    ("patel", "Ravi", "Patel", KSU),
    ("dubois", "Margot", "Dubois", KSU),
    ("tanaka", "Ken", "Tanaka", KSU),
    ("haddad", "Leila", "Haddad", KSU),
    ("novak", "Petra", "Novak", KSU),
]
ADMINS = [
    ("mwills", "Morgan", "Wills", ApplicationRole.Code.ADMINISTRATOR, True),
    ("hbailey", "Heather", "Bailey", ApplicationRole.Code.CENTER_LEADERSHIP, False),
    ("cade", "Carl", "Ade", ApplicationRole.Code.CENTER_LEADERSHIP, False),
]
PROJECTS = [
    ("pp1", "Sleep-dependent memory consolidation in adolescent mice", ProjectKind.PILOT),
    ("pp2", "Dopaminergic signaling and cognitive flexibility", ProjectKind.PILOT),
    ("rp1", "Hippocampal plasticity across the aging lifespan", ProjectKind.PRIMARY),
    ("rp2", "Computational models of attentional control", ProjectKind.PRIMARY),
]
RELS = [
    ("okafor", "pilot_awardee", "pp1"),
    ("okafor", "core_user", "BN"),
    ("okafor", "core_user", "NI"),
    ("whitfield", "pilot_mentor", "pp1"),
    ("varga", "core_director", "BN"),
    ("reyes", "core_director", "BN"),
    ("natarajan", "core_director", "NI"),
    ("kim", "project_leader", "rp1"),
    ("bell", "primary_mentor", "rp1"),
    ("lee", "project_student", "pp1"),
    ("lee", "student_trainee", None),
    ("chen", "core_staff", "CN"),
    ("adeyemi", "pilot_awardee", "pp2"),
    ("adeyemi", "core_user", "CN"),
    ("moreau", "project_leader", "rp2"),
    ("moreau", "core_director", "CN"),
    ("santos", "pilot_mentor", "pp2"),
    ("ferris", "core_user", "NI"),
    ("lindqvist", "core_user", "CN"),
    ("osei", "core_user", "BN"),
    ("patel", "collaborator", "rp2"),
    ("dubois", "core_user", "NI"),
    ("tanaka", "project_staff", "rp1"),
    ("haddad", "core_user", "BN"),
    ("novak", "collaborator", "rp1"),
]
NOT_ON_ROSTER = {"santos", "ferris"}


def _person(first, last, institution, username):
    p = Person.objects.filter(first_name=first, last_name=last).first()
    if not p:
        p = Person.objects.create(first_name=first, last_name=last, institution=institution)
        PersonEmail.objects.create(person=p, email=f"{username}@example.edu", is_primary=True)
    return p


def _user(person, username, role_code=None):
    user = User.objects.filter(username=username).first()
    if not user:
        user = User.objects.create_user(
            username,
            person.primary_email,
            DEMO_PASSWORD,
            person=person,
            first_name=person.first_name,
            last_name=person.last_name,
        )
    role = ApplicationRole.objects.get(code=role_code or ApplicationRole.Code.STANDARD_USER)
    UserRole.objects.get_or_create(user=user, role=role, scope_core=None)
    return user


def _answer_like(q, rng, lean=4):
    opts = [o for o in q.answer_set.options.all()]
    nums = [o for o in opts if o.value is not None]
    na = [o for o in opts if o.is_na_option]
    if na and rng.random() < 0.08:
        return na[0]
    if not nums:
        return rng.choice(opts)
    target = min(max(round(rng.gauss(lean, 0.8)), 1), len(nums))
    return next((o for o in nums if o.value == target), nums[-1])


def _fill(a, user, rng, *, opt_out=False):
    schema = FormSchema(a.form_version)
    resp = Response.objects.create(assignment=a)
    if opt_out and schema.optout_question:
        Answer.objects.create(
            response=resp,
            question=schema.optout_question,
            option=schema.optout_question.answer_set.options.get(code="yes"),
        )
        pathway = schema.optout_pathway
        status = AssignmentStatus.COMPLETED_OPT_OUT
    else:
        for q in schema.questions:
            if q.question_type in ("likert",):
                Answer.objects.create(response=resp, question=q, option=_answer_like(q, rng))
            elif (
                q.question_type == "long_text"
                and not q.config.get("narrative")
                and rng.random() < 0.3
            ):
                Answer.objects.create(
                    response=resp,
                    question=q,
                    value_text="(Fictional comment for the sample center.)",
                )
        pathway = schema.pathway({})
        status = AssignmentStatus.SUBMITTED
    now = timezone.now()
    resp.submitted_at, resp.submitted_by = now, user
    resp.save()
    a.status, a.completion_pathway, a.submitted_at = status, pathway, now
    a.started_at = now
    a.save()


@transaction.atomic
def seed_demo(stdout=None):
    log = stdout.write if stdout else (lambda m: None)
    people, users = {}, {}
    for username, first, last, inst in PEOPLE:
        people[username] = _person(first, last, inst, username)
        users[username] = _user(people[username], username)
    for username, first, last, role, evaluator in ADMINS:
        p = _person(first, last, KSU, username)
        u = _user(p, username, role)
        u.user_permissions.add(Permission.objects.get(codename="view_confidential_mentoring_data"))
        if evaluator:
            u.user_permissions.add(
                Permission.objects.get(codename="view_identified_survey_responses")
            )
        users[username] = u
    projects = {}
    for key, title, kind in PROJECTS:
        projects[key], _ = Project.objects.get_or_create(
            title=title, defaults={"kind": kind, "start_date": dt.date(2025, 6, 1)}
        )
    cores = {c.code: c for c in Core.objects.all()}
    start = dt.date(2025, 8, 1)
    for username, rtype, ctx in RELS:
        try:
            services.add_relationship(
                None,
                people[username],
                rtype,
                project=projects.get(ctx),
                core=cores.get(ctx),
                start=start,
            )
        except services.RelationshipError:
            pass
    for username, p in people.items():
        if username not in NOT_ON_ROSTER and not services.is_on_roster(p):
            services.add_to_roster(None, p, start=start)
    tz = timezone.get_current_timezone()
    now = timezone.now()
    y10a, _ = ReportingPeriod.objects.get_or_create(
        grant_year=10,
        sequence=1,
        defaults=dict(
            name="Year 10 Fall",
            short_label="Y10 Fall",
            start_date=dt.date(2026, 6, 1),
            end_date=dt.date(2026, 11, 30),
            opens_at=now - dt.timedelta(days=10),
            due_at=now + dt.timedelta(days=24),
            status=PeriodStatus.OPEN,
        ),
    )
    ReportingPeriod.objects.get_or_create(
        grant_year=10,
        sequence=2,
        defaults=dict(
            name="Year 10 Spring",
            short_label="Y10 Spring",
            start_date=dt.date(2026, 12, 1),
            end_date=dt.date(2027, 5, 31),
            opens_at=dt.datetime(2027, 5, 1, 8, tzinfo=tz),
            due_at=dt.datetime(2027, 6, 1, 17, tzinfo=tz),
            status=PeriodStatus.DRAFT,
        ),
    )
    created = asg.generate(y10a).created
    log(f"Y10 Fall: {created} assignments")
    if not Response.objects.filter(assignment__reporting_period=y10a).exists():
        rng = random.Random(2026)
        for a in Assignment.objects.filter(reporting_period=y10a).select_related(
            "person", "form_definition", "form_version"
        ):
            uname = next((k for k, v in people.items() if v.pk == a.person_id), None)
            if uname is None:
                continue
            if uname == "okafor":  # the demo respondent: two done, one started, the rest to do
                if a.form_definition.code in ("bn_core_survey", "ts_reporting_hub"):
                    _fill(a, users[uname], rng)
                elif a.form_definition.code == "ni_core_survey":
                    a.status, a.started_at = AssignmentStatus.IN_PROGRESS, now
                    a.save(update_fields=["status", "started_at"])
                    resp = Response.objects.create(assignment=a)
                    q = FormSchema(a.form_version).questions[1]
                    Answer.objects.create(response=resp, question=q, option=_answer_like(q, rng))
                continue
            r = rng.random()
            if r < 0.62:
                optout = bool(FormSchema(a.form_version).optout_question) and rng.random() < 0.2
                _fill(a, users[uname], rng, opt_out=optout)
            elif r < 0.75:
                a.status = AssignmentStatus.IN_PROGRESS
                a.started_at = now
                a.save(update_fields=["status", "started_at"])
                Response.objects.create(assignment=a)
    log(f"Sample center ready. Logins use the password {DEMO_PASSWORD}.")
