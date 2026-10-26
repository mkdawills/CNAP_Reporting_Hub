# Decisions log

One paragraph per choice made during the build, newest last. The Architecture Review is the design of record; this file records how it was carried out.

## 2026-10-21 — Milestone 1

**Django 5.2 LTS, not 6.x.** The review names 5.2 LTS. It receives security fixes until April 2028, and LTS-to-LTS upgrades are the path a university maintainer can follow.

**Closed sets are CharFields with CHECK constraints, not PostgreSQL ENUM types.** The review's DDL used ENUMs for illustration. A CharField plus `CheckConstraint` is readable in the migration, editable with an ordinary migration, and has the same effect on invalid data. `apps/common/enums.py` is the one place the sets are defined.

**Rules Django cannot express live in hand-written `0002_constraints.py` migrations.** Composite foreign keys, exclusion constraints, the two views and the freeze trigger. Django's migration state does not know about them, which is fine: they never change through `makemigrations`, and `tests/test_migrations.py` checks that they exist.

**Copied-and-checked columns are filled in `save()` and verified by the database.** `PersonRelationship.context_kind`, `is_single_holder`, `project_kind`; `Question.form_version`, `scale_kind`; `Assignment.form_definition`, `context_kind`; `FormAssignmentRule.form_context_kind`, `relationship_context_kind`. Model `clean()` methods repeat the rules in plain English for forms and the admin.

**The confidential-mentoring permission is explicit even for superusers.** `User.has_confidential_mentoring_access()` looks only at direct user permissions. Roles never include it (the seed asserts this; a test asserts it), and being a Django superuser does not imply it. The data-access layer will call this method, not `has_perm()`.

**`provenance`, not `source`, is the column that says where a response or assignment came from** (platform or Piestar import), because `assignments.source` already means which rule created the assignment (universal, relationship, manual). The addendum called both `source`; the data dictionary uses the names here.

**An `analytics` app holds the snapshot, theme and metric tables** rather than putting them in `reporting`, so the reporting-period close workflow (Milestone 8) has its own home. The plan's layout predates the analytics addendum.

**createsuperuser creates the Person.** The manager creates (or, by e-mail, finds) a Person for any user created without one, so the first administrator exists without a chicken-and-egg step. Ordinary users are created from an existing Person in the admin.

**Option-type question set is a tuple.** A Python set iterated inside a CHECK constraint produced a different column order on every run and a spurious "missing migration". Constraint definitions must be deterministic.

## 2026-10-22 — Assignment rules confirmed by MW

**Mentee Survey goes to Pilot Awardees and Primary Project Leaders only.** It is a relationship rule on `pilot_awardee` and `project_leader`, one assignment per project held. Students and trainees on projects (`project_student`) do not receive it.

**Core surveys go to the whole active roster, minus each core's own directors.** Each core survey is a universal rule with `excluded_relationship_type = core_director` and `about_core` set to that core. Holding a `core_user` relationship is not required. Non-users answer through the structured `core_non_use` pathway, which counts the assignment as complete.

**One Project Progress Report serves pilot and primary projects.** It is a single form definition with a relationship rule on `pilot_awardee` and `project_leader`, assigned per project. There is no separate report for each project kind.

## 2026-10-22 — Response privacy (MW decision, as clarified)

**Respondents never see another respondent's individual answers.** A respondent sees their own responses in My History and nothing row-level from anyone else. No respondent-facing screen, export or e-mail may contain another person's answers.

**The evaluator reads everything.** The holder of `reporting.view_confidential_mentoring_data` (MW in Build 1) may read every individual response and every aggregate, on every form including the four mentoring forms, at any time. This restores the original rule; it is not a new role.

**Other staff follow the original design.** Administrators and Evaluation / Reporting Staff may read individual responses and results on non-confidential forms. The four mentoring forms remain visible only to the evaluator. (Prototype implements this; MW to confirm.)

**Respondents see aggregates only after results are finalized, with a minimum group of 5.** The "Center results" page shows finalized periods only, hides any item with fewer than 5 responses, and never includes mentoring forms. The minimum-5 rule applies to respondent-facing results; staff with row-level access see full counts.

**Center Director and Associate Director.** A new application role, Center Leadership, held by the Center Director and Associate Director (CNAP relationships still grant no permissions). They also hold the confidential mentoring permission by name. They read: (a) the four mentoring forms (Mentee Survey, Mentor Questionnaire, Pilot and Primary Mentor Reports) identified; (b) Project Progress Reports (accomplishments written by Research Project Leaders and Pilot Project Leaders) identified; (c) every other survey (core surveys, NeuroSync) de-identified: no name, no project, listed as "Respondent n" in an order that is not alphabetical and is assigned per form and period, so one person cannot be followed across forms. They do not see the period dashboard. The confidential permission is therefore no longer MW-only. (Reading of "mentor and mentee reporting" as all four mentoring forms: MW to confirm.)

**Narrative reports.** Project Progress Reports are reports, not surveys: administrators read them and use them for official reporting (RPPR), and the form says so. Pilot and Primary Mentor Reports are readable only by the evaluator.


## 2026-10-22 — Instrument wording loaded into the prototype

**Source of record for Milestone 3 until Piestar exports arrive:** `fixtures/forms/source/CNAP_Forms_Reconstructed.md`. Item wording, scales and open-ended prompts are used exactly as written there, including apparent typos ("Enhances(s)", the missing period after "Make(s) time to regularly meet with me"), because changing wording is a form edit. Each is to be checked against Piestar before Milestone 3 loads the fixtures.

**Open items to verify against Piestar:** section titles (the reconstruction labels "Quality of services and functions", "Frequency of use", "Open-ended"; the prototype adds "Ratings" and "Mentoring" where none is known); NeuroSync item wording "NeuroSync" versus "brown bag" (measure stays the same either way); whether any items are required (the prototype requires none); "Progress Towards Graduation" on the Primary Research Grant Mentor Report.

**Not yet held:** Team Science / Synergy Survey (export from Piestar) and both Semiannual Progress Reports (Build 2). The prototype's Project Progress Report remains placeholder text and is labeled as such.

**Opt-out follow-ups.** Core surveys use MW's wording (warm intro, three optional questions). NeuroSync uses the architecture-review follow-ups (reason list, future attendance, optional comments) under the same intro.

**Mentor Questionnaire scope.** Its instructions ask mentors with several mentees to answer once for all of them, so Milestone 5 should assign it once per mentor per period (context none), not once per project.

## 2026-10-24 — Piestar exports loaded

**Team Science / Synergy Survey** loaded verbatim from the Piestar export (`Team_Science.pdf`): four rated sections (synergy 9 items, Administrative Core 9, Piestar Items 3, Grant Writing Program 3) and three open-ended prompts, all required as in Piestar. Its scale reads "3 - Neither Disagree nor Agree" and "N/A", which differs from the other agreement scales; kept as its own answer set. Universal rule (whole active roster).

**Progress reports are two forms, both file uploads.** Primary Project & Core Semi-Annual Progress Report (2–3 pages; project leaders) and Pilot Project Semiannual Progress Report (1–2 pages; pilot awardees), wording verbatim from Piestar. Each collects one required Word or PDF upload; the headings are guidance for the document, not questions. Both replace the placeholder "Project Progress Report". Center Leadership reads both identified; administrators read both.

**Open:** the "Piestar Items" section and the open-ended prompts name Piestar; they need new wording for the new platform. The primary report includes "For Cores" guidance, which implies core directors also file it; the prototype assigns it to project leaders only.

## 2026-10-24 — Progress reports: Word uploads only

MW reformats progress reports after submission, so both Semi-Annual Progress Reports accept Word files only (.docx or .doc). The instruction text is changed from "MS Word or PDF document" to "MS Word document", and the upload rejects any other file type with a message. This is a deliberate wording change from the Piestar source.

## 2026-10-24 — Core progress reports; who reads written answers; named leadership

**Core directors file the Primary Project & Core Semi-Annual Progress Report**, one assignment per core they direct (context: that core), in addition to project leaders (one per project). Co-directors each receive and file their own report (MW, 2026-10-24: undecided whether co-directed cores will file together, so separately for now). If that changes, the rule becomes one assignment per core rather than per director.

**Written answers of any kind** (every long-text answer, open-ended survey prompt, narrative report, meeting summary and uploaded file) are readable only by the person who wrote them, the evaluator (Morgan Wills), the Center Director (Dr. Heather Bailey) and the Associate Director (Dr. Carl Ade). Other administrators and Evaluation / Reporting Staff never see them; for them the field shows only that it is restricted. This supersedes the earlier rule that administrators read progress reports for the RPPR. The directors' view of non-mentoring surveys stays de-identified, including written answers.

**Named holders.** Evaluator: Morgan Wills. Center Leadership role: Dr. Heather Bailey (Center Director), Dr. Carl Ade (Associate Director). All three hold the confidential mentoring permission.

**Platform name:** pending; replaces "Piestar" in the Team Science section title, intro, items and open-ended prompts once chosen.

## 2026-10-24 — The Administrators are the three of them

The Administrator role is held by exactly three people: Morgan Wills (evaluator), Dr. Heather Bailey (Center Director) and Dr. Carl Ade (Associate Director). There is no separate Center Leadership role and no administrator without the confidential permission. All three manage people, periods and the audit log. Within the role, read access still differs: the evaluator reads everything identified; the Director and Associate Director read mentoring forms and progress reports identified, and the other surveys de-identified. Whether an Evaluation / Reporting Staff role is still needed is open.

## 2026-10-24 — Platform name: CNAP Reporting Hub (for now)

The platform is called the CNAP Reporting Hub. In the Team Science / Synergy Survey, "Piestar Items" becomes "CNAP Reporting Hub Items", and every mention of Piestar in that section's intro, its three items and the first two open-ended prompts now names the CNAP Reporting Hub. The measures keep their existing codes so year-over-year comparisons continue, with a note in reports that the system being rated changed from Piestar to the CNAP Reporting Hub starting Year 10.

## 2026-10-24 — Evaluation staff role removed; Director and Associate Director are view-only

**Roles.** There is no Evaluation / Reporting Staff role: MW does all of that work. The platform has respondents (Standard Users) and three Administrators.

**Only the evaluator changes anything.** Morgan Wills alone edits people, relationships, projects, periods, exemptions, reopenings, assignment generation and snapshots. Dr. Heather Bailey and Dr. Carl Ade are view-only: they can open every admin screen but see no edit controls, and the server must refuse any change from them (separate permission from viewing).

**What the Director and Associate Director see.**
- With names: all four mentoring forms (Mentee Survey, Mentor Questionnaire, Pilot and Primary Mentor Reports), including ratings and written answers, so they can see what mentors said about mentoring and what mentees said about their mentors; and both Semi-Annual Progress Reports.
- Without names: the three core user surveys, NeuroSync and Team Science / Synergy. Individual responses appear only as "Respondent n" in a shuffled order, and the period dashboard shows these surveys as completion counts only, never as a list of who completed them.

**Small-group safeguard for de-identified surveys (MW, 2026-10-24).** The Director and Associate Director see individual de-identified responses to the core, NeuroSync and Team Science surveys only when at least 5 people completed that survey in that period. Below 5, they see the combined results only. Applies per form and period; does not apply to the evaluator or to the identified mentoring forms and progress reports.

## 2026-10-24 — Core surveys also reach outside core users

Each core survey still goes to the whole active roster, minus that core's directors (MW: tracking actual use is too much work, and the survey reminds members the cores exist). It now also goes to anyone with an active `core_user` relationship to that core who is not on the roster, such as users from outside CNAP or outside K-State. Someone who is both is assigned once (the existing one-assignment rule). MW may add outside users to the roster later; nothing else changes when that happens.

Pending: how people without a K-State eID sign in.

## 2026-10-24 — Sign-in plan (pending K-State IT approval at security review)

**K-State people** sign in with their K-State eID through university single sign-on. No platform passwords.

**People without a K-State eID** (many mentors are at other universities; some core users are outside CNAP or K-State) sign in by emailed link:
- Each period-open and reminder email carries a personal link that opens only that person's own forms.
- Links are single-use and expire after 7 days. Anyone can request a fresh link at any time by entering their email; drafts are kept, so a long report can be finished across several sittings.
- Opening a link starts a working session of about 8 hours.
- Opening a confidential mentoring form (Mentor Questionnaire, Mentee Survey, Pilot or Primary Mentor Report) from a link also requires a 6-digit code sent to the same email.
- The email address MW records for an outside person is their identity; it should be the address they actually check (usually their university address).

**Administrators** (Morgan Wills, Dr. Heather Bailey, Dr. Carl Ade) sign in with K-State single sign-on plus two-factor authentication.

To confirm with K-State IT: approval of emailed links for outside users, and whether sponsored guest eIDs exist as an alternative that would let everyone use single sign-on.

## 2026-10-24 — Audiences, Team Science split, launch review

**Everyone with an active CNAP relationship gets every universal survey**, each with a one-click opt-out: internal members, external mentors and external core users alike. Mentoring forms and progress reports still come only from the relevant relationships. A core user sees the survey for the core they used pinned first ("The core you used"); the other core surveys are labeled "Did you also use this core?".

**Team Science / Synergy is now four surveys**, each with its own opt-out and its own Functioning Well / Changes / Additional Comments prompts worded for that topic: Team Synergy (9 items), Administrative Core (9), Grant Writing Program (3), CNAP Reporting Hub (3). Rating items keep their measure codes and stay required, as in Piestar. The open-ended prompts are new wording (previously one set spanning all topics); note this in Year 10 reports.

**Labels:** "Primary Project Leader" is now "Research Project Leader (RPL)"; "Pilot Awardee" is now "Pilot Project Leader (PPL)". Source form wording (e.g., "Pilot Grantee" on the Pilot Grant Mentor Report) is unchanged.

**Review before launch** is the first period stage. It lists everyone who will receive forms, grouped as General members, RPLs, PPLs, Mentors, Core directors and External core users (people can appear in several groups), with each person's forms, per-form totals, and warnings (project with no leader or mentor, outside person with no email). Nothing is sent until the evaluator approves. External people show whether they are on the roster, with an "Add to roster" action. The Director and Associate Director see this screen view-only.

**Groups follow relationships, not manual placement.** A person's group comes from their CNAP relationships, which is what decides their forms, so groups are changed by editing relationships rather than by dragging names between groups.
