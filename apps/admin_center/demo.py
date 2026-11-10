"""
The fictional sample center (manage.py seed --fictional).

Every respondent here is invented. The three Administrator accounts use the
real names MW gave (decisions.md) with example.edu addresses; give them real
addresses and K-State sign-in when the site goes live.

Creates: people and relationships, logins (password DEMO_PASSWORD), the
Year 10 Fall period (open, with assignments and some fictional answers)
and Year 10 Spring (waiting for review before launch).
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
    ("brandt", "Hana", "Brandt", KSU),
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
    ("rowe", "Imogen", "Rowe", "University of Kansas"),
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
    ("brandt", "project_leader", "rp1"),
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
    ("rowe", "osc", None),  # advises on methods, no measurable effort: D.1 at 0.0 months
]
NOT_ON_ROSTER = {"santos", "ferris", "rowe"}


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


SAMPLE_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<<"
    b"/Font<</F1<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>>>>>>>endobj\n"
    b"4 0 obj<</Length 58>>stream\nBT /F1 18 Tf 72 700 Td (Fictional sample document) Tj ET\nendstream endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


def _sciencv_like(person, code):
    """A fictional biosketch or Current and Pending laid out like SciENcv output, so the sample center shows
    the certification check and the degrees/months suggestions. Everything in it is made up."""
    import io

    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    who = f"{person.last_name}, {person.first_name}"
    if code == "biosketch":
        lines = [
            "NIH BIOGRAPHICAL SKETCH COMMON FORM",
            f"Name: {who}",
            "Persistent Identifier (PID) of the Senior/Key",
            "Person:",
            "https://orcid.org/0000-0002-1825-0097",
            "Position Title: Associate Professor (fictional)",
            "PROFESSIONAL PREPARATION",
            "INSTITUTION AND LOCATION",
            "DEGREE",
            "FIELD OF STUDY",
            "Sample University, Sampletown, Kansas, United States",
            "Doctor of Philosophy (PHD)",
            "05/2012",
            "Sample College, Sampleburg, Iowa, United States",
            "Bachelor of Science (BS)",
            "05/2006",
            "APPOINTMENTS AND POSITIONS",
            "2020 - present Associate Professor (fictional)",
            f"Certified by {who} in SciENcv on 2026-10-20 09:00:00",
            "NIH BIOGRAPHICAL SKETCH SUPPLEMENT",
        ]
    elif code == "current_pending":
        lines = [
            "NIH Current and Pending (Other) Support Common Form",
            "CURRENT AND PENDING (OTHER) SUPPORT INFORMATION",
            "*NAME:",
            who,
            "PERSISTENT IDENTIFIER (PID):",
            "https://orcid.org/0000-0002-1825-0097",
            "*Proposal/Active Project Title:",
            "Cognitive and Neurobiological Approaches to Plasticity (CNAP) Center",
            "*Status of Support:",
            "Current",
            "Proposal/Award Number:",
            "5P20GM113109-10",
            "*Proposal/Active Project Start Date: (MM/YYYY):",
            "07/2022",
            "*Proposal/Active Project End Date: (MM/YYYY):",
            "05/2027",
            "* Person Months per budget period Devoted to the Proposal/Active Project:",
            "Year",
            "Person Months",
            "2022",
            "1.5",
            "2023",
            "3",
            "2024",
            "3",
            "2025",
            "3",
            "2026",
            "3",
            "2027",
            "1.5",
            "*Overall Objectives:",
            "(Fictional sample.)",
            "Certification:",
            f"Certified by {who} in SciENcv on 2026-10-20 09:00:00",
        ]
    else:
        return None
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    y = 760
    for line in lines:
        c.drawString(48, y, line)
        y -= 14
    c.save()
    return buf.getvalue()


def _sample_pdf(resp, q, user, a):
    """A one-page fictional PDF, so sample NIH documents can be downloaded like real ones."""
    import hashlib

    from django.core.files.base import ContentFile

    from apps.reporting.models import AnswerFile, File

    name = f"{a.person.last_name}_{q.code}_sample.pdf"
    data = _sciencv_like(a.person, q.code) or SAMPLE_PDF
    f = File(
        original_filename=name,
        content_type="application/pdf",
        byte_size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        uploaded_by=user,
    )
    f.storage_key.save(name, ContentFile(data), save=False)
    f.save()
    ans = Answer.objects.create(response=resp, question=q)
    AnswerFile.objects.create(answer=ans, file=f)


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
            elif q.question_type == "file" and q.config.get("accept") == [".pdf"] and q.is_required:
                _sample_pdf(resp, q, user, a)
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
            # Answers are due on the last day of the reporting period (MW 2026-11-05). Sample data
            # falls back to a date three weeks out once that day has passed, so the demo stays open.
            due_at=max(dt.datetime(2026, 11, 30, 17, tzinfo=tz), now + dt.timedelta(days=21)),
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
            due_at=dt.datetime(2027, 5, 31, 17, tzinfo=tz),
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
    _seed_outcomes(people)
    _seed_funding(people, users)
    log(f"Sample center ready. Logins use the password {DEMO_PASSWORD}.")


def _seed_outcomes(people):
    """A few fictional papers and proposals so the Publications and grants page has something to check."""
    from apps.outcomes.models import (
        GrantFamily,
        GrantSubmission,
        GrantSubmissionPerson,
        GrantSubmissionProject,
        GrantSubmissionResource,
        Publication,
        PublicationPerson,
        PublicationProject,
        PublicationResource,
    )
    from apps.people.models import Project, Resource

    if Publication.objects.exists():
        return
    projects = list(Project.objects.order_by("pk"))
    res = {r.code: r for r in Resource.objects.all()}
    core_res = [r for r in res.values() if r.core_id]
    P = people
    pubs = [
        (
            "Sample paper: attention shifts measured with EEG in young adults",
            "Journal of Sample Neuroscience",
            dt.date(2026, 3, 1),
            True,
            ["okafor", "moreau"],
            [0],
            ["CN"],
        ),
        (
            "Sample paper: a shared pipeline for behavioral video scoring",
            "Sample Methods Letters",
            dt.date(2026, 5, 1),
            None,
            ["varga", "brandt"],
            [1],
            ["BN", "NI"],
        ),
        (
            "Sample paper: mentoring networks in a COBRE center",
            "Sample Journal of Research Development",
            dt.date(2025, 11, 1),
            False,
            ["brandt"],
            [1, 2],
            [],
        ),
        (
            "Sample paper: open data practices for small labs",
            "Sample Data Science Review",
            dt.date(2026, 1, 1),
            None,
            ["natarajan"],
            [],
            ["NI"],
        ),
    ]
    # Sample RRIDs (fictional numbers) for two cores; the CN Core has none, so its question stays hidden.
    for x in core_res:
        if x.core.code in ("BN", "NI") and not x.core.rrid:
            x.core.rrid = {"BN": "RRID:SCR_990001", "NI": "RRID:SCR_990002"}[x.core.code]
            x.core.save(update_fields=["rrid"])
    rrid_turn = iter(["yes", "no", "yes", "unsure", "yes", "yes"] * 5)
    for title, journal, when, cited, who, prj, cores in pubs:
        p = Publication.objects.create(
            title=title,
            publication_type="journal_article",
            status="published",
            journal=journal,
            publication_date=when,
            cnap_cited=cited,
        )
        for i, u in enumerate(who):
            if u in P:
                PublicationPerson.objects.create(publication=p, person=P[u], author_order=i)
        for k in prj:
            if k < len(projects):
                PublicationProject.objects.create(publication=p, project=projects[k])
        for c in cores:
            r = next((x for x in core_res if x.core.code == c), None)
            if r:
                PublicationResource.objects.create(
                    publication=p, resource=r, rrid_cited=next(rrid_turn) if r.core.rrid else ""
                )
    grants = [
        (
            "Sample R01: circuits of sustained attention",
            "NIH",
            "R01",
            "awarded",
            dt.date(2025, 10, 5),
            1250000,
            True,
            "okafor",
            [0],
            ["CN"],
        ),
        (
            "Sample R21: low-cost behavioral phenotyping",
            "NIH",
            "R21",
            "submitted",
            dt.date(2026, 2, 16),
            None,
            None,
            "varga",
            [1],
            ["BN"],
        ),
        (
            "Sample NSF CAREER: data stewardship for neuroscience",
            "NSF",
            "CAREER",
            "not_funded",
            dt.date(2025, 7, 25),
            None,
            False,
            "natarajan",
            [],
            ["NI"],
        ),
    ]
    for title, agency, mech, status, sub, award, ack, pi, prj, cores in grants:
        fam = GrantFamily.objects.create(title=title)
        g = GrantSubmission.objects.create(
            grant_family=fam,
            project_title=title,
            funding_agency=agency,
            mechanism=mech,
            status=status,
            submission_date=sub,
            award_total=award,
            cnap_acknowledged=ack,
        )
        if pi in P:
            GrantSubmissionPerson.objects.create(
                grant_submission=g, person=P[pi], role="pi", is_primary_cnap_contact=True
            )
        for k in prj:
            if k < len(projects):
                GrantSubmissionProject.objects.create(grant_submission=g, project=projects[k])
        for c in cores:
            r = next((x for x in core_res if x.core.code == c), None)
            if r:
                GrantSubmissionResource.objects.create(grant_submission=g, resource=r)


def _seed_funding(people, users):
    """Fictional funding samples (MW 2026-11-10): matches for fictional people only, one fictional Not funded
    proposal with a follow-up to review, one suggestion, and a few news items. Real matches are MW's to enter."""
    from apps.outcomes import funding
    from apps.outcomes.models import (
        FundingMatch,
        FundingNewsItem,
        FundingOpportunity,
        FundingSuggestion,
        GrantFamily,
        GrantSubmission,
        GrantSubmissionPerson,
    )

    funding.load_questions()
    funding.load_catalog()
    if FundingMatch.objects.exists() or "okafor" not in people:
        return
    mw = users.get("mwills")
    okafor = people["okafor"]
    title = "Sample R01: sleep and the consolidation of fear extinction in adolescent rats"
    fam = GrantFamily.objects.create(title=title)
    g = GrantSubmission.objects.create(
        grant_family=fam,
        project_title=title,
        funding_agency="National Institute of Mental Health",
        funding_source_type="nih",
        mechanism="R01",
        status="not_funded",
        submission_date=dt.date(2026, 6, 5),
        decision_date=dt.date(2026, 11, 4),
        decision_comments="Reviewers valued the design and questioned the sample size in Aim 2.",
        plans_to_resubmit=True,
    )
    GrantSubmissionPerson.objects.create(grant_submission=g, person=okafor, role="pi", is_primary_cnap_contact=True)
    funding.ensure_followup(g, mw)
    picks = [
        ("bbrf", "Fear extinction research relates directly to anxiety disorders, a stated focus of the foundation."),
        ("katz", "A second R01 on a new direction, separate from the sleep work, would not need preliminary data."),
        ("whitehall", "The sleep and memory work fits the foundation’s interest in basic neurobiology."),
    ]
    for key, why in picks:
        o = FundingOpportunity.objects.filter(tracker_id=key).first()
        if o:
            funding.add_match(o, okafor, why, mw)
    if "brandt" in people:
        o = FundingOpportunity.objects.filter(tracker_id="fraxa").first()
        if o:
            funding.add_match(o, people["brandt"], "A fellow in the lab could carry the treatment work forward.", mw)
    FundingSuggestion.objects.create(
        person=okafor,
        name="Sample Foundation Early Career Award",
        sponsor="Sample Foundation",
        deadline_text="March 1, 2027",
        why="The award funds sleep research by early-career faculty.",
        for_everyone=True,
    )
    for d, head, summary, src, url, pinned in [
        (dt.date(2026, 10, 8), "NIH reports a record number of R01-equivalent awards to Early Stage Investigators",
         "NIH made 1,648 R01-equivalent awards to Early Stage Investigators in fiscal year 2026, the most on record.\n"
         "The record came in a year with fewer awards overall.", "Granted News",
         "https://grantedai.com/blog/nih-1648-early-stage-investigator-r01-record-fy2026-generation-discovery-100-intramural-pis-60924-awards-11-percent-below-average-strategy", True),
        (dt.date(2026, 8, 11), "NIH ended continuous submission",
         "NIH stopped accepting continuous submissions on August 11, 2026.\nApplications now follow the standard due dates.",
         "Chapman University research policy updates", "https://www.chapman.edu/research/policies-and-guidance/federal-research-policies/", False),
        (dt.date(2026, 1, 1), "NIH accepts up to six applications from one investigator each year",
         "Each principal investigator may submit six new, renewal, resubmission, or revision applications across all council rounds in a calendar year.\n"
         "Plan the year’s submissions with the limit in mind.", "NIH Grants and Funding", "https://grants.nih.gov/node/1192", False),
        (dt.date(2026, 2, 24), "Early Stage Investigator success rates fell in fiscal year 2025",
         "Success rates for Early Stage Investigators dropped from 26% to 19%, as applications rose 11%.\n"
         "NIH’s shift to funding more grants for several years at once reduced the money available for new awards.",
         "Granted News", "https://grantedai.com/news/nih-grant-success-rates-plunge-to-20-as-multiyear-funding-squeezes-early-career-", False),
    ]:
        FundingNewsItem.objects.create(
            headline=head, news_date=d, summary=summary, source_name=src, source_url=url, pinned=pinned, posted_by=mw,
            date_text="Calendar year 2026" if head.startswith("NIH accepts up to six") else "",
        )
