"""
Reference data every installation needs: roles, cores, resources, relationship
types, shared answer sets, completion pathways. Loaded by `manage.py seed`.
All of it is data an administrator may later edit; the seed only creates what
is missing and never overwrites an edited row.
"""

from django.contrib.auth.models import Permission
from django.db import transaction

from apps.accounts.models import ApplicationRole
from apps.common.enums import ContextKind, ProjectKind, ScaleKind
from apps.forms_engine.models import AnswerSet, CompletionPathway, QuestionOption
from apps.people.models import Core, RelationshipType, RelationshipTypeProjectKind, Resource

CONFIDENTIAL_CODENAME = "view_confidential_mentoring_data"
IDENTIFIED_CODENAME = "view_identified_survey_responses"
DIRECT_GRANT_CODENAMES = (CONFIDENTIAL_CODENAME, IDENTIFIED_CODENAME)

CORES = [
    ("BN", "Behavioral Neuroscience Core", 1),
    ("NI", "Neuroinformatics Core", 2),
    ("CN", "Cognitive Neuroscience Core", 3),
]

RESOURCES = [
    # code, name, core code, sort
    ("bn_core", "BN Core", "BN", 1),
    ("ni_core", "NI Core", "NI", 2),
    ("cn_core", "CN Core", "CN", 3),
    ("admin_core", "Administrative Core", None, 4),
    ("connect_lab", "Connect Lab", None, 5),
    ("research_project", "Research Project(s)", None, 6),
    ("pilot_project", "Pilot Project(s)", None, 7),
    ("mentorship", "Mentorship", None, 8),
    ("other", "Other", None, 9),
]

# code, name, context, allowed project kinds, single holder, rich profile, sort
RELATIONSHIP_TYPES = [
    (
        "project_leader",
        "Research Project Leader (RPL)",
        ContextKind.PROJECT,
        [ProjectKind.PRIMARY],
        True,
        True,
        1,
    ),
    (
        "pilot_awardee",
        "Pilot Project Leader (PPL)",
        ContextKind.PROJECT,
        [ProjectKind.PILOT],
        True,
        True,
        2,
    ),
    (
        "primary_mentor",
        "Primary Mentor",
        ContextKind.PROJECT,
        [ProjectKind.PRIMARY],
        False,
        False,
        3,
    ),
    ("pilot_mentor", "Pilot Mentor", ContextKind.PROJECT, [ProjectKind.PILOT], False, False, 4),
    (
        "project_staff",
        "Project Staff",
        ContextKind.PROJECT,
        [ProjectKind.PILOT, ProjectKind.PRIMARY],
        False,
        False,
        5,
    ),
    (
        "project_student",
        "Student / Trainee on a project",
        ContextKind.PROJECT,
        [ProjectKind.PILOT, ProjectKind.PRIMARY],
        False,
        False,
        6,
    ),
    (
        "collaborator",
        "Collaborator",
        ContextKind.PROJECT,
        [ProjectKind.PILOT, ProjectKind.PRIMARY],
        False,
        False,
        7,
    ),
    # Core Director is NOT single-holder: CNAP allows co-directors (review 15.10).
    ("core_director", "Core Director", ContextKind.CORE, [], False, True, 8),
    ("core_staff", "Core Staff", ContextKind.CORE, [], False, False, 9),
    ("core_user", "Core User", ContextKind.CORE, [], False, False, 10),
    ("student_trainee", "Student / Trainee (center-level)", ContextKind.NONE, [], False, False, 11),
    ("cnap_member", "General CNAP Member (active roster)", ContextKind.NONE, [], False, False, 12),
    ("event_participant", "Event / Training Participant", ContextKind.NONE, [], False, False, 13),
    # RPPR D.1 "PD/PI" and Table 1B "Core Staff (including the PD/PI)" (decisions.md 2026-10-26)
    ("pd_pi", "PD/PI (Center Director)", ContextKind.NONE, [], False, False, 14),
    ("associate_director", "Associate Director", ContextKind.NONE, [], False, False, 15),
]

# Shared answer sets: name, scale kind, options as (code, label, value, is_na)
ANSWER_SETS = {
    "Agreement": (
        ScaleKind.AGREEMENT,
        [
            ("strongly_disagree", "1 - Strongly Disagree", 1, False),
            ("disagree", "2 - Disagree", 2, False),
            ("neither", "3 - Neither Agree nor Disagree", 3, False),
            ("agree", "4 - Agree", 4, False),
            ("strongly_agree", "5 - Strongly Agree", 5, False),
            ("na", "Not Applicable", None, True),
        ],
    ),
    "Quality": (
        ScaleKind.QUALITY,
        [
            ("very_poor", "1 - Very Poor", 1, False),
            ("poor", "2 - Poor", 2, False),
            ("acceptable", "3 - Acceptable", 3, False),
            ("good", "4 - Good", 4, False),
            ("very_good", "5 - Very Good", 5, False),
            ("na", "N/A", None, True),
        ],
    ),
    "Frequency": (
        ScaleKind.FREQUENCY,
        [
            ("never", "1 - Never", 1, False),
            ("rarely", "2 - Rarely", 2, False),
            ("sometimes", "3 - Sometimes", 3, False),
            ("often", "4 - Often", 4, False),
            ("always", "5 - Always", 5, False),
            ("na", "N/A", None, True),
        ],
    ),
    "Yes / No": (
        ScaleKind.YES_NO,
        [
            ("yes", "Yes", 1, False),
            ("no", "No", 0, False),
        ],
    ),
    # NeuroSync rates on the agreement scale without N/A (source form).
    "Agreement (no N/A)": (
        ScaleKind.AGREEMENT,
        [
            ("strongly_disagree", "1 - Strongly Disagree", 1, False),
            ("disagree", "2 - Disagree", 2, False),
            ("neither", "3 - Neither Agree nor Disagree", 3, False),
            ("agree", "4 - Agree", 4, False),
            ("strongly_agree", "5 - Strongly Agree", 5, False),
        ],
    ),
    # Team Science / Synergy wording differs at the midpoint and N/A (Piestar export).
    "Agreement (Team Science)": (
        ScaleKind.AGREEMENT,
        [
            ("strongly_disagree", "1 - Strongly Disagree", 1, False),
            ("disagree", "2 - Disagree", 2, False),
            ("neither", "3 - Neither Disagree nor Agree", 3, False),
            ("agree", "4 - Agree", 4, False),
            ("strongly_agree", "5 - Strongly Agree", 5, False),
            ("na", "N/A", None, True),
        ],
    ),
}

COMPLETION_PATHWAYS = [
    ("full_response", "Full response", False, 1),
    ("non_attendance", "Did not attend (NeuroSync)", True, 2),
    ("core_non_use", "Did not use this core", True, 3),
    ("ts_not_involved", "Not involved enough to answer (Team Synergy)", True, 4),
    ("ts_no_admin", "Did not work with the Administrative Core", True, 5),
    ("ts_no_gw", "Did not use the grant writing program", True, 6),
]

ROLES = {
    ApplicationRole.Code.ADMINISTRATOR: (
        "Administrator",
        "Manages people, relationships, forms, periods, assignments, corrections and exports. "
        "Reading confidential mentoring data and identified survey responses needs separate, "
        "named grants.",
    ),
    ApplicationRole.Code.CENTER_LEADERSHIP: (
        "Administrator, view only",
        "Opens every administrator screen but changes nothing. Held by the Center Director "
        "and Associate Director.",
    ),
    ApplicationRole.Code.STANDARD_USER: (
        "Standard User",
        "Completes assigned forms; sees own tasks and history.",
    ),
}

CNAP_APPS = {"people", "accounts", "forms_engine", "reporting", "analytics", "outcomes", "audit"}


def _role_permissions(code):
    """Which permissions each role bundles. The direct-grant permissions are never included."""
    perms = Permission.objects.filter(content_type__app_label__in=CNAP_APPS).exclude(
        codename__in=DIRECT_GRANT_CODENAMES
    )
    if code == ApplicationRole.Code.ADMINISTRATOR:
        return perms
    if code == ApplicationRole.Code.CENTER_LEADERSHIP:
        return perms.filter(codename__startswith="view_")
    return Permission.objects.none()


@transaction.atomic
def seed_reference_data(stdout=None):
    log = (lambda m: stdout.write(m)) if stdout else (lambda m: None)

    for code, (name, description) in ROLES.items():
        role, created = ApplicationRole.objects.get_or_create(
            code=code, defaults={"name": name, "description": description}
        )
        role.permissions.set(_role_permissions(code))
        log(f"role {code}: {'created' if created else 'updated permissions'}")

    cores = {}
    for code, name, sort in CORES:
        cores[code], created = Core.objects.get_or_create(
            code=code, defaults={"name": name, "sort_order": sort}
        )
        log(f"core {code}: {'created' if created else 'exists'}")

    for code, name, core_code, sort in RESOURCES:
        _, created = Resource.objects.get_or_create(
            code=code, defaults={"name": name, "core": cores.get(core_code), "sort_order": sort}
        )
        log(f"resource {code}: {'created' if created else 'exists'}")

    for code, name, context, kinds, single, rich, sort in RELATIONSHIP_TYPES:
        rt, created = RelationshipType.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "context_kind": context,
                "is_single_holder": single,
                "grants_rich_profile": rich,
                "sort_order": sort,
            },
        )
        for kind in kinds:
            RelationshipTypeProjectKind.objects.get_or_create(
                relationship_type=rt, project_kind=kind
            )
        log(f"relationship type {code}: {'created' if created else 'exists'}")

    for name, (scale, options) in ANSWER_SETS.items():
        answer_set, created = AnswerSet.objects.get_or_create(
            name=name,
            is_shared=True,
            defaults={"scale_kind": scale, "description": "Shared scale seeded at install."},
        )
        if created:
            for order, (code, label, value, is_na) in enumerate(options, start=1):
                QuestionOption.objects.create(
                    answer_set=answer_set,
                    code=code,
                    label=label,
                    value=value,
                    is_na_option=is_na,
                    sort_order=order,
                )
        log(f"answer set {name}: {'created' if created else 'exists'}")

    for code, name, is_opt_out, sort in COMPLETION_PATHWAYS:
        _, created = CompletionPathway.objects.get_or_create(
            code=code, defaults={"name": name, "is_opt_out": is_opt_out, "sort_order": sort}
        )
        log(f"completion pathway {code}: {'created' if created else 'exists'}")
