"""
Closed sets used across the schema. Each is a CharField with choices plus a
CHECK constraint, which a maintainer can read in the migration; PostgreSQL
ENUM types would need ALTER TYPE for every change and gain nothing here.
"""

from django.db import models


class ContextKind(models.TextChoices):
    NONE = "none", "No context"
    PROJECT = "project", "A project"
    CORE = "core", "A core"


class ProjectKind(models.TextChoices):
    PILOT = "pilot", "Pilot project"
    PRIMARY = "primary", "Primary research project"


class ScaleKind(models.TextChoices):
    AGREEMENT = "agreement", "Agreement (Strongly Disagree to Strongly Agree)"
    QUALITY = "quality", "Quality (Very Poor to Very Good)"
    FREQUENCY = "frequency", "Frequency (Never to Always)"
    YES_NO = "yes_no", "Yes / No"
    COUNT = "count", "Count"
    OTHER = "other", "Other"


class FormCategory(models.TextChoices):
    SURVEY = "survey", "Survey (category A)"
    REPORT = "report", "Periodic narrative report (category B)"


class ConfidentialityClass(models.TextChoices):
    STANDARD = "standard", "Standard"
    MENTORING = "mentoring", "Confidential mentoring data"


class VersionStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    RETIRED = "retired", "Retired"


class QuestionType(models.TextChoices):
    SHORT_TEXT = "short_text", "Short text"
    LONG_TEXT = "long_text", "Long narrative text"
    SINGLE_SELECT = "single_select", "Single select (radio)"
    MULTI_SELECT = "multi_select", "Multi-select (checkboxes)"
    YES_NO = "yes_no", "Yes / No"
    LIKERT = "likert", "Likert / rating scale"
    DATE = "date", "Date"
    MONTH_YEAR = "month_year", "Month and year"
    URL = "url", "URL"
    NUMBER = "number", "Number"
    CURRENCY = "currency", "Currency"
    FILE = "file", "File upload"
    PERSON = "person", "Person selector"
    PROJECT = "project", "Project selector"
    INSTRUCTIONS = "instructions", "Instructional text (no answer)"


# Question types whose answer is one or more options from an answer set.
# A tuple, not a set: constraint definitions must be deterministic across runs.
OPTION_QUESTION_TYPES = (
    QuestionType.SINGLE_SELECT,
    QuestionType.MULTI_SELECT,
    QuestionType.YES_NO,
    QuestionType.LIKERT,
)


class RuleOperator(models.TextChoices):
    EQUALS = "equals", "Equals option"
    NOT_EQUALS = "not_equals", "Does not equal option"
    IS_ANSWERED = "is_answered", "Is answered"
    IS_NOT_ANSWERED = "is_not_answered", "Is not answered"


class RuleAction(models.TextChoices):
    SHOW = "show", "Show target"
    HIDE = "hide", "Hide target"
    REQUIRE = "require", "Require target"
    SET_PATHWAY = "set_pathway", "Set completion pathway"


class RuleScope(models.TextChoices):
    UNIVERSAL = "universal", "Universal (active roster)"
    RELATIONSHIP = "relationship", "By CNAP relationship"


class PeriodType(models.TextChoices):
    SEMIANNUAL = "semiannual", "Semiannual evaluation"
    ANNUAL = "annual", "Annual (RPPR)"
    OTHER = "other", "Other"


class PeriodStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"
    FINALIZED = "finalized", "Finalized"


class AssignmentSource(models.TextChoices):
    UNIVERSAL = "universal", "Universal rule"
    RELATIONSHIP = "relationship", "Relationship rule"
    MANUAL = "manual", "Created by an administrator"


class AssignmentStatus(models.TextChoices):
    NOT_STARTED = "not_started", "Not started"
    IN_PROGRESS = "in_progress", "In progress"
    SUBMITTED = "submitted", "Submitted"
    COMPLETED_OPT_OUT = "completed_opt_out", "Completed via structured opt-out"
    EXEMPT = "exempt", "Exempt"


COMPLETE_STATUSES = {AssignmentStatus.SUBMITTED, AssignmentStatus.COMPLETED_OPT_OUT}


class Provenance(models.TextChoices):
    PLATFORM = "platform", "Entered in this platform"
    PIESTAR_IMPORT = "piestar_import", "Imported from Piestar (row level)"
    AGGREGATE_IMPORT = "aggregate_import", "Imported historical aggregate"


class ImportStatus(models.TextChoices):
    PARSED = "parsed", "Parsed, awaiting review"
    COMMITTED = "committed", "Committed"
    DISCARDED = "discarded", "Discarded"


class ImportMatchKind(models.TextChoices):
    MATCHED = "matched", "Matched an existing person"
    NEW = "new", "New person"
    POSSIBLE_DUPLICATE = "possible_duplicate", "Possible duplicate"
    MISSING = "missing", "On the roster before, missing from this file"


class SnapshotKind(models.TextChoices):
    PERIOD_CLOSE = "period_close", "Period close"
    IMPORTED_AGGREGATE = "imported_aggregate", "Imported historical aggregate"


class SnapshotStatus(models.TextChoices):
    GENERATED = "generated", "Generated, under review"
    REVIEWED = "reviewed", "Reviewed, ready to finalize"
    FINALIZED = "finalized", "Finalized"
    SUPERSEDED = "superseded", "Superseded by a later version"


class NoteKind(models.TextChoices):
    THEME_SUMMARY = "theme_summary", "Theme summary (administrator)"
    SYSTEM_OBSERVATION = "system_observation", "Observation (system-generated)"
    ADMIN_INTERPRETATION = "admin_interpretation", "Interpretation (administrator)"


class PublicationType(models.TextChoices):
    JOURNAL_ARTICLE = "journal_article", "Journal article"
    CONFERENCE_PAPER = "conference_paper", "Conference paper or proceeding"
    BOOK_CHAPTER = "book_chapter", "Book chapter"
    THESIS = "thesis", "Thesis or dissertation"
    PREPRINT = "preprint", "Preprint (not peer reviewed)"
    OTHER = "other", "Other"


class PublicationStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    SUBMITTED = "submitted", "Submitted"
    PUBLISHED = "published", "Published"
    DECLINED = "declined", "Declined"


class PublicationSubstatus(models.TextChoices):
    UNDER_REVIEW = "under_review", "Under review"
    ACCEPTED = "accepted", "Accepted"
    IN_PRESS = "in_press", "In press / awaiting publication"


class PresentationType(models.TextChoices):
    CONFERENCE = "conference", "Conference presentation"
    INVITED_TALK = "invited_talk", "Invited talk"
    POSTER_OR_FLYER = "poster_or_flyer", "Poster or flyer"
    OTHER = "other", "Other"


class GrantStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    SUBMITTED = "submitted", "Submitted / pending"
    AWARDED = "awarded", "Awarded"
    NOT_FUNDED = "not_funded", "Not funded"


class GrantRole(models.TextChoices):
    PI = "pi", "Principal Investigator"
    MPI = "mpi", "Multiple PI"
    CO_I = "co_i", "Co-Investigator"
    KEY_PERSONNEL = "key_personnel", "Key personnel"
    CONSULTANT = "consultant", "Consultant"
    OTHER = "other", "Other"


class PrimeOrSubaward(models.TextChoices):
    PRIME = "prime", "Prime institution"
    SUBAWARD = "subaward", "Subaward"


class FundingSourceType(models.TextChoices):
    """RPPR Table 1A columns."""

    NIH = "nih", "NIH"
    FEDERAL_OTHER = "federal_other", "Federal, non-NIH"
    NON_FEDERAL = "non_federal", "Non-federal"
