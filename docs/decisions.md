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

## 2026-10-25 — Milestone 2: people, relationships, roster import, roles

**Roles as built.** Three application roles: Administrator (manages everything), "Administrator, view only" (code `center_leadership`; the Director and Associate Director) and Standard User. The Evaluation Staff and Reviewer roles are removed, and so is the unused `review_responses` permission. Two permissions are direct grants only, never part of a role: `view_confidential_mentoring_data` (all three Administrators) and the new `view_identified_survey_responses` (the evaluator only; without it, core, NeuroSync and Team Science responses are shown de-identified). `apps/accounts/access.py` is the one place every screen asks who may see or change what.

**View-only is enforced on the server.** Every change is a POST through `@manage_action` (or a GET form page through `@manage_page`), which refuses anyone without the Administrator role and `manage_center`. View-only administrators see the same screens with no edit controls and a "View only" banner; tests post changes as the Director and expect 403.

**Ending a relationship "now" means it was held through yesterday.** Relationship dates are inclusive, so a relationship ending today would still count today. "End" with no date sets the end to yesterday (or the start date if it began today), matching handoffs, where the old holder ends the day before the new one starts.

**External means not at Kansas State University.** A person whose institution is anything other than Kansas State University (or empty) is external: they sign in by emailed link. The institution field is the switch; it defaults to Kansas State University when adding a person.

**Roster import** accepts .csv or .xlsx with first name, last name and e-mail columns (institution, department, position optional). Every row is reviewed before commit; possible duplicates (same name, different e-mail) need an explicit merge, add or skip; people on the roster but missing from the file stay unless their membership is ended. Committing is audited.

**Visual design carried from the prototype** into `static/css/app.css`: K-State purple, vertical dividers between columns and parts, sentences of every direction stacked one per line (the `stack` template filter), uppercase gray group bands, quiet rating scales with larger question text.

## 2026-10-25 — Center results: small items left out, with a note

On the respondent-facing Center results page, any item rated by fewer than 5 people is left out, and a short note under that survey says some items aren't shown because fewer than 5 people rated them. Administrators see every item on their own Results page.

## 2026-10-25 — Prior-year averages loaded (MW overrides the real-data rule for these)

MW asked for the Year 6–9 results to be in the platform now, and said the "fictional data until K-State hosting" rule does not apply to them. Only item averages are loaded: `fixtures/historical/aggregates_y6_y9.csv` (757 values) was extracted from the comparison tables of the Year 9 site-visit reports (BN, NI and CN Tables 2 and 4; the NeuroSync, Mentor and Mentee comparison sheets) by `fixtures/historical/extract_from_y9_reports.py`. No names, e-mails, respondent rows or written comments were taken; the reports' raw-data sheets were not used. They are stored as historical aggregate snapshots (provenance `aggregate_import`) with no drill-down, one reporting period per column (Y6 Jan through Y9 May).

Assumptions to verify: the Year 9 Mentee report's comparison sheet prints mentor-worded item labels; its values differ from the mentor sheet, so they are taken as mentee ratings and mapped by item number. Items no longer asked are kept as retired measures (BN "Planning and execution of alterations and renovations", one NI and one CN frequency item).

## 2026-10-25 — Layout and display choices from MW's review

- **Results mirror the site-visit report layout**: per section, a table of items with Mean (SD), a count and percent for each answer and a Total, a grand-mean row, a column chart of response counts, then a year-over-year table of means. Percent and mean cells are heat-shaded (darker green for higher values).
- **My history** uses the My tasks layout: one gray band per reporting period, rows with View and a quiet submitted date.
- **Form pages**: every divider has the same space above and below; the question text is larger and bolder, and the rating scale is borderless and quiet until hovered or chosen; a light line also sits above the first question after a section's intro.
- **Sidebar**: more spacing, a centered line under "Kansas State University", and the person's CNAP roles (e.g. "BN Core Director") instead of "Standard User".
- Reports say "You previously started this report"; surveys say "survey".
- **Team Science surveys**: the single rating section of each of the four is titled "Survey Questions:" (MW, 2026-10-25). Core surveys keep "Quality of services and functions" and "Frequency of use".
- **Form title block**: centered, on a light purple panel, with no divider inside it.
- **Rating answers are a vertical list on every screen** ("1 Strongly Disagree" … with N/A below), chosen by MW over the side-by-side scale: each answer reads as one line, long labels don't wrap, and the whole row is the target.
- **Section directions** for rating sections sit right under the heading, in parentheses without the trailing colon, with one line below them.
- **Opt-out box** is quiet (gray text, thin border) until ticked; ticking turns it yellow.
- **Questions are numbered**, restarting in each section, matching the site-visit report tables.
- **Open-ended sections** are titled "Open-ended questions:" (MW, 2026-10-25). The opt-out note under the checkbox is in parentheses.
- **No serif type anywhere** (MW, 2026-10-25): headings use Public Sans at heavier weights.
- **Results tables**: every number is centered; a stronger vertical line separates Mean (SD) from each answer group (count and percent) and from Total.
- **Numbered items hang**: numbers sit right-aligned in their own column and wrapped lines start under the first letter of the text, in results tables and on form pages. The response-count bars sit in a row under the totals, each bar under its own answer column.
- **Results table structure** (as approved in the prototype): header row one holds Item, Mean (SD), each answer as "(1)" over "Very Poor" (never wrapping), and Total, all words on one line; row two holds the small sub-labels Mean · SD, n · %, n. Lines are logical: a heavy outer border and heavy lines after the Item column, between groups and under the header; faint lines inside a group (n | %). The response-count row merges its first three cells into one right-aligned label, "Response counts across all items:". In year-over-year tables, a heavy line starts each grant year.
- **Results table lines, final** (MW, 2026-10-25): a double line between SD and the first answer's n, and between the last answer's % and Total; a bold single line between answer groups (after each %); a faint line inside a group (n | %). "Grand mean, totals and %:" is right-aligned against the line.
- **Percent cells** are quieter than the counts: the whole percentage is 75% of the count's size, in gray (heat shading still applies).
- **Answer columns are equal width** in results tables (each n and % column 48px), whatever the label length.
- **Each results table sits in its own floating card** (white, rounded, soft shadow), with its title inside.

## 2026-10-25 — Year-over-year table: prior years, contrast, column widths

- The prototype now carries the same Year 6–9 item averages as the real site (matched by table and item wording), so Table 2 shows every period from Y6 Jan onward. Prototype demo periods were relabelled to the real convention (Y10 Jan, Y10 June, Y11 Jan).
- Heat shading in the year-over-year table is stretched across that table's own lowest-to-highest average (Excel-style color scale), not the whole 1–5 scale: lowest is nearly white, highest is deep green with white text. MW asked for more noticeable contrast; averages cluster between 3 and 5, so a 1–5 scale left everything the same shade.
- Period columns in the year-over-year table share equal width (the Item column's width rule no longer hits the first period header).
- The intro sentence reads "Table 1 data captures …" (capital T), and the opt-out label's own period is dropped so the sentence doesn't end in ".”.".

## 2026-10-25 — n / % switch on result tables

- A "Show: n and % · n only · % only" switch sits above Table 1 on every results page (admin report and Center results). It hides the other column under each answer; group lines stay (the % column takes over the bold/double line when n is hidden), answer columns become equal width, and in "% only" the percentages return to full size and ink colour. The Grand mean label follows the view ("Grand mean and totals:" / "Grand mean and %:"). The choice is remembered per browser (localStorage, wrapped in try/catch); the CSV export always has both.
- Table 2 (year over year) shows finalized periods up to the period being viewed, plus that period itself; later or unfinished periods are never shown.

## 2026-10-25 — Summary first, table on demand; heat follows the view

- Each results table opens as a summary: the grand mean (SD, ratings, items) and the response-count chart with n · % per answer. A "Show item-by-item table" button drops down the full table (native details/summary, no script needed). The n / % switch sits inside the drop-down. Table 2 (year over year) has no chart and stays open.
- Heat shading follows what's showing: on % in "n and %" and "% only", on the counts in "n only" (same shade, since it is set by each count's share of the item's ratings).
- In "% only" the bold/double group lines move to the % column so the dividers stay.

## 2026-10-25 — Year-over-year roll-up and grand mean tile

- Table 2 opens as a roll-up: a line of the overall mean rating for every period (labelled points, latest filled and bold) plus three call-outs comparing the last two periods: biggest gain, biggest drop, and lowest-rated item now (current items only). "Show item-by-item trends" drops down the heat-map table.
- Table 1 summary: grand mean tile ("GRAND MEAN" label, bold value "/ 5", a 1–5 track with a marker at the mean, then SD · ratings · items). Each bar shows the % in bold with "n ratings" under it, captioned "Share of all ratings for each answer (all items combined)".

## 2026-10-25 — Results summary, cognitive-load pass

MW: "make it possible to instantly understand." The summary now answers three questions in reading order (how good, how many happy, how many unhappy), using the scale's own words.
- Page facts replace the opening paragraph: "7 took part · 6 answered all the survey items · 1 did not use this core" (opt-out wording from the completion pathway). The site-visit sentence ("Table 1 data captures …") is kept word for word under "Show site-visit report wording" for copying into the report.
- Table card: small "TABLE 1" label above a plain title. Three headline numbers: average "3.9 / 5 · Good" (mean rounded to the nearest answer label), "% Good or Very Good" (top two answers, green), "% Very Poor or Poor" (bottom two, red). Below, one 100% bar split by answer (red → grey → green; % printed inside segments of 7% or more) with a legend giving every answer's %. "All 15 items combined." The 1–5 marker line, the five-bar chart and the "share of all ratings" caption are gone.
- Table 2 title reads "<section> over time"; chart caption "Average rating, all items, each reporting period". Call-outs sit three across when they wrap under the chart.
- (same day) The stacked bar + legend didn't line up for MW ("is it lining up with the bar?"). Replaced with one row per answer: label · bar on a light track · % right after it. No colour matching, and 0% answers still show. "Acceptable" grey darkened (#a9a9ad) so it reads against the track.
- (same day) MW preferred vertical bars after all: one column per answer, % on top, answer name under a baseline, red → grey → green; the tallest bar fills the space. No counts or caption.
- (same day) Facts row replaced by one sentence that adds up for a newcomer: "11 people responded: 10 answered all the survey items and 1 skipped them because they did not use this core." (Without opt-outs: "10 people answered all the survey items.")
- (same day) Headline numbers sit in rings that fill by value: average fills mean/5 (dark), "Good or Very Good" fills its % (green), "Very Poor or Poor" fills its % (red). Label under each ring.
- (same day) "All 15 items combined" now says what it means: "These bars combine every answer to the 15 survey items in this section, such as “Booking of shared facilities”. See each item" — the link opens the item-by-item table.
- (same day) The facts sentence starts from who received the survey: "18 people received the survey and 7 responded: 6 answered all the survey items and 1 skipped them because they did not use this core." ("Received" = assigned for the period.)
- (same day) Note under the bars leads with why (MW: "In order to understand the BN Core performance…"): "To see the BN Core’s overall quality of services and functions, these bars combine every answer to its 15 survey items, such as “Booking of shared facilities”. See each item." The section name is used instead of "performance" so it also fits Frequency of use. Non-core surveys: "To see the overall picture, these bars combine every answer to the 7 survey items in this section, …". A quoted item's own trailing period is dropped.
- (same day) Table titles are grey (the numbers lead); a thin rule separates the headline rings from the bars; the average's label is plain text on one line ("Average rating: Good"), matching the other two labels.
- (same day) Rings spaced evenly across the card; the answer bars always span the card's full width (equal columns, bar width capped at 140px).
