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
- (same day) Headline rings left-aligned and closer together so they read as a summary, not as labels for the bars below.
- (same day) Table titles: "Year 10 January Quality of Services and Functions Survey Responses" (period in words + section in title case); the trend table is "Quality of Services and Functions Over Time".
- (same day) Each ring sits on its own light grey square tile (so the rings read as summary cards, not chart marks) and is smaller (76px).
- (same day) One spacing rhythm inside result cards: 40px at every break (title → tiles → rule → bars, note → button, card → card). The note under the bars sits 14px below them because it explains them.
- (same day) Headline tiles shrunk to compact chips (small ring left, number and label right) sitting 12px under the title, so they read as title information. 40px rhythm resumes below them.
- (same day) Every Table 2 shows all three call-out cards. When nothing rose or fell since the previous period the card says so quietly ("No item went up" / "No item went down") instead of disappearing.

## 2026-10-25 — Period names: Fall and Spring

MW: the two collections are Fall (surveyed in January) and Spring (surveyed in May/June); the latest real data is Year 9 Spring; nothing should be labelled Year 10 Spring.
- Imported periods renamed Y6 Fall … Y9 Spring (migration reporting 0004 relabels existing databases; the prior-year CSV and the importer use the new names; the Year 9 reports' "Jan"/"May"/"June" map to Fall/Spring). Period names read "Year 9 Spring".
- The next collection is Year 10 Fall (surveyed January 2027). The fictional demo seed (development only) uses Y10 Fall (open) and Y10 Spring (draft, no data).
- An averages-only period has no Table 1; its results page opens with the trend, ending at that period. Center results lists every finalized period, imported ones included; the small-group rule doesn't hide imported averages (they have no per-person counts).
- Prototype: no made-up results at all (MW's choice). The fake finished period is gone; Results and Center results list Y6 Fall … Y9 Spring (real averages), default Y9 Spring. Fictional answers exist only in the open Y10 Fall period so the tasks and dashboard screens work, and never appear in results.
- The site-visit report sentence ("Table 1 data captures …") moved off the page into the CSV download's second line; the sentence at the top of the page covers it for readers.
- (same day) After submitting: the "Submitted:/Recorded:" line is grey; "Next: …" is bold black. A short confetti burst plays when a survey or report is finished (submitted or recorded as opt-out); skipped for people who ask their system for reduced motion, and shown once per finished task (sessionStorage).

## 2026-10-25 — Sanity check, required-question message, task headings

- Full check (MW asked; Year 9 Spring is the latest real session): every page for every demo user returns 200 or the expected 403, no server errors; all 757 prior-year averages match across the CSV, the database and the prototype; NeuroSync Table 2 matches the Year 9 PDF exactly. Fixed: new-period suggestions now read "Y11 Fall"/"Year 11 Fall"; admin Results opens on the latest finalized period (Y9 Spring), with the open period still selectable and marked "(open: live, not final)"; field help and docstrings use Fall/Spring. Open question for MW: is the current CN item "CN Core Shared facility space" the same as the retired "… (Bluemont Hall 426)"? If so, link their history.
- When a submit is blocked, the message lists each unanswered required question by name with a link, and each one is outlined in red with "Needs an answer". Hidden questions are never counted.
- Task groups on My tasks are plain section headings (uppercase label, rule underneath), not tinted cards, so they don't look clickable.

## 2026-10-25 — Open for preview

MW: set up the next session right away so people can sign in and look at the surveys any time, without being able to answer yet.
- New lifecycle step between review and open: launching a period before its opens_at puts it in "Open for preview" (seven steps now). Assignments exist and people see their full list on My tasks, but every row offers only Preview; a banner says "Year 10 Fall opens Monday, January 11. You can read every form now with Preview. Answering opens that day; nothing you do here before then is saved."
- Nothing can be answered in preview: drafts, submit and opt-out are refused (is_editable checks the period), and opening a form redirects to its preview. "Close period" isn't offered.
- It opens by itself at opens_at (derived from the date; no job or button needed). Tests: tests/test_preview_period.py.
- Prototype: a "Demo: show as preview / open answering now" switch on Reporting periods (prototype only) shows both states.
- Footnote under My tasks ("* Opt out of any survey …") has clear space above so it reads as applying to the whole list. Task summary is one line: "5 of 10 remaining. About 34 min in total. Due in 102 days (Feb 1)."

## 2026-10-25 — Who gets what, before launch

MW was worried about assignments being right. The launch review now shows, for every person, each form with the reason under it ("Everyone on the roster", "Research Project Leader (RPL)", "Core Director (CN Core)" …), what was deliberately not sent and why ("Not sent: CN Core, because they are core director of the CN Core"), and a warning for anyone active with no current CNAP role ("won’t receive anything").

Outcomes (grants, awards, publications, presentations) — MW's direction so far: both people and administrators enter them; faculty can let a student enter on their behalf; the person can credit one outcome to several projects and/or cores (the schema already links one outcome to many projects and resources). UI is Build 2 per the original plan; a short plan goes to MW before building.

## 2026-10-25 — Publications and grants, part 1: acknowledgment tracking

MW chose acknowledgment checking first (then counts for the NIH report, exportable lists, and each person's outcomes on their page, in any order).
- New admin page "Publications and grants" (sidebar). Two summary tiles: % of checked published papers that acknowledge CNAP, and % of checked submitted proposals that do, each with "n of N still to check"; clicking a tile switches tabs.
- Publications tab lists published papers; Grants tab lists submitted proposals (planned ones appear under All). Filters: All · Needs checking · Not acknowledged · Acknowledged. Each row shows CNAP people, every project and core it is credited to, status, and "Acknowledges CNAP?" Yes / No / Not checked with one-click buttons (audited).
- Add/edit forms for a publication and a grant. Credit: any number of CNAP people, projects, and cores/resources. A resubmission is entered with the earlier proposal's title and becomes A1, A2, … in the same grant family. Status changes write history rows. Publications record two checks: the paper acknowledges CNAP's grant (cnap_cited) and it is linked to the grant in NIH's records (cnap_in_grant_index).
- Access: the evaluator adds, edits and marks; Center leadership sees the list read-only; respondents can't open it. Self-entry by faculty (and students entering for them) comes in a later part.
- Fictional sample papers and proposals are added by `seed --fictional`.

## 2026-10-25 — Publications and grants, part 2: counts, lists, person pages

- Counts tab: by grant year (June–May; June 2025–May 2026 is Year 9) for All CNAP, by project, and by core/resource: papers published, presentations, grants submitted, grants awarded, awarded dollars. An outcome credited to several projects or cores counts once in each, so those rows can exceed All CNAP (said on the page). Grants count in the year submitted; awards in the year of the award notice (submission date if none).
- Downloads (CSV, opens in Excel): citation list (with a ready-made citation column, links, both acknowledgment checks, people, projects, cores), grant list (agency, mechanism, A0/A1, status, dates, amounts, PI, people, projects, cores, acknowledgment), and the counts. Each download is audited.
- Each person's admin page lists their papers and grants with acknowledgment status.
- Still to come: faculty entering their own outcomes (and students entering for them), presentations entry, and the matching prototype screens.

## 2026-10-25 — Year-over-year table like the Year 9 reports; NI import fixed

- Table 2's item table has three header rows (school year "2022–2023", "Year 6", Fall/Spring), red-to-blue shading centered on the table's middle value (red below, blue above, deeper = further; note under the table), and a "Means / Means and SD" switch. SDs come from the reports where given (NeuroSync all periods; NI all periods; BN and CN for Y9 Spring from Table 1); otherwise "–". Live periods use the computed SD.
- Data fix: NI's trend tables pair each mean with its SD, and the first extraction read alternating columns, so NI means sat under the wrong periods and Y8 Spring–Y9 Spring were missing. The extractor now reads pairs; NI has 8 periods per item, checked against the report. The earlier sanity check compared the database to the extracted file, not to the reports, so it couldn't catch this.
- CN "CN Core Shared facility space (Bluemont Hall 426)" is the same item as today's "CN Core Shared facility space" (MW confirmed; the Y9 Spring report lists it as current), so its Y6–Y9 history is joined to cn_frequency_02.
- The importer stores the SD with each mean and removes imported values the file no longer contains. File now: 797 means, 186 SDs.

## 2026-10-26 — Publications and grants, part 3: self-entry per MW's Publication flow and Grant flow

MW supplied the two framework documents (Publication flow; Grant flow with its later revisions). Parts 1–2 were built before they arrived; this part brings everything in line with them.
- Who: project awardees (RPL, PPL) keep their own records; a faculty member can let someone (usually a student) enter for them ("Who can enter for you"; delegates see and edit only that person's publications and grants, never surveys). Administrators can still add and correct anything.
- Check-in each reporting period, shown as one item on My tasks ("Update your publications and grants", counted in "remaining"; read-only while a period is in preview): with no records of a kind, "Do you plan to submit any publications?" / "… grant proposals?" (Yes → planned entry; No → recorded for the period); every Planned or Submitted record not reviewed since the period opened shows "Confirm no changes" or "Update status". Done when nothing is left; reviewed records don't come back until the next period.
- Status questions exactly per the flows. Publications: Planned (anticipated title, journal, submission month/year, anticipated Center resources, optional) → Submitted (journal and title prefilled, submission date required, anticipated publication date, Center resources required) → Published (submission date, journal, PubMed link required, cited CNAP? listed in grant index? foreign authors? all Yes/No required, resources prefilled) or Declined (decline date, journal, comments, "Do you plan to resubmit?" → a new Planned entry prefilled from it). Grants: Planned (agency, funding opportunity link, mechanism, anticipated month/year, title, role, anticipated total budget and estimated direct costs, optional) → Submitted / pending (submission date and total requested budget required; estimated direct/indirect optional; resources required) → Awarded (notice/start/end dates, total/direct/indirect required, grant number, prime vs subaward, acknowledged CNAP? CNAP credited in publications? foreign components?) or Not funded (decision date, comments, discussed with a Program Officer? with optional name/date shown only after Yes, reviewer feedback provided to the CNAP project manager?, plan to resubmit? → the system creates the linked A1/A2 Planned record, prefilled; users never manage versions).
- Center resources use the flows' list (BN, NI, CN, Connect Lab, Research Project(s), Pilot Project(s), Mentorship, Other with text); anticipated (Planned) and actual (Submitted onward) are kept separately. Specific projects can also be ticked (MW: credit to several projects or cores).
- Every status change is timestamped in the status history; records are never deleted.
- Exports: one row per publication / per submission, with the flows' column lists (Project ID, dates, PubMed link, CNAP Cited, CNAP Grant Index, Foreign Authors, anticipated and actual resources, decline comments, the four status timestamps; for grants Parent Grant ID, Submission Version, estimated vs final budget columns, Program Officer and reviewer-feedback fields, resources, and status timestamps).
- New fields: grant anticipated total and planned estimated direct costs; "Other" resource text; last-reviewed time; delegates; per-period check-ins (migration outcomes 0002).
- Not yet: PubMed metadata auto-fill and reminder e-mails for stale records (optional enhancements in the flows); the prototype screens.

## 2026-10-26 — PubMed fill-in, stale-record reminders, presentations, year-round entry, encouraging note

- **Fill in from PubMed** (Publication flow optional enhancement): on "Mark as published", a button next to the PubMed link looks the paper up with NCBI E-utilities (efetch; a DOI is resolved with esearch) and fills the title, journal, publication date and authors for the person to check; nothing is saved until Save. If CNAP_GRANT_NUMBERS is set, it also says whether PubMed lists CNAP's grant in the paper's grant index and pre-answers that question. Author affiliations are shown (collapsed) above the foreign-authors question as a hint; the person still answers it. If PubMed can't be reached or the link isn't recognised, a plain message asks them to type the details in (the flow's manual fallback). Note: this workspace can't reach PubMed; it was tested against saved E-utilities responses and needs outbound HTTPS to eutils.ncbi.nlm.nih.gov on the server.
- **Reminder e-mails for stale records** (both flows' optional enhancement): a Planned or Submitted paper or proposal nobody has reviewed for OUTCOME_STALE_DAYS (default 120) is stale. Its owner gets one e-mail listing all their stale records with a link to the page, copied to anyone who enters for them, at most once every OUTCOME_REMINDER_EVERY_DAYS (default 30). `manage.py send_outcome_reminders` runs daily (docs/deployment.md; `--dry-run` lists who'd get one). Admin page: Reminders tab shows who is due, what they'd be reminded about, a "Send reminders now" button, and the last 20 sent (each send is recorded and audited).
- **Presentations** (MW): people add presentations (type, title, event, location, date, presenters/authors, "Did your presentation acknowledge CNAP?", Center resources, projects). No lifecycle: one entry each, editable. Admin Presentations tab with the same Yes/No acknowledgment check, and a presentation list download. Counts already included presentations.
- **Year-round entry** (MW): between reporting periods people can add or update papers, presentations and proposals any time; the check-in task appears only while a period is open. Entry is paused for OUTCOME_REOPEN_DAYS (default 7) after a period closes while no period is open, so the Center can finish that period's numbers ("Adding and updating opens again on …"); records stay readable.
- **Encouraging note** (MW's wording, lightly edited for typos) shown when a proposal is marked Not funded: "Thank you for updating us. Although a not-funded decision is always challenging feedback, please be heartened and assured that it is part of the journey all researchers take toward securing funding. We are very proud of you and excited for your opportunity to take the free reviewer feedback and incorporate it into the next cycle."
- Sidebar: "Publications, talks and grants".
- (same day) MW revised the not-funded note: "Thank you for the update. We hope you’ll still celebrate your great accomplishment; a not-funded decision is part of every researcher’s journey toward funding. We are very proud of you and excited for your next steps!"
- (same day) Final not-funded note (MW): "Thank you for the update. Submitting a proposal is a real accomplishment and something that should always be celebrated! A not-funded decision is part of every researcher’s journey toward funding. Your reviewers’ feedback is valuable for the next round, and we’re here to help you think through its application. We are very proud of you and excited for your next steps!"
- (same day) CNAP's grant number from MW: P20GM113109 (FAIN), now the default for CNAP_GRANT_NUMBERS. PubMed grant-index matching uses the core part (GM113109) so "P20 GM113109", "P20GM113109/GM/NIGMS NIH HHS" and "GM113109" all count.
- (same day) MW: CNAP's NIH budget period runs June 1 to May 31, the same as the grant year, so outcome counts by grant year are counts by RPPR budget period (Year 9 = June 1, 2025 – May 31, 2026).

## 2026-10-26 — RPPR guidance (FY27 COBRE) applied to publications, presentations and grants

MW shared the FY27 RPPR guidance for COBRE awards and approved these changes.
- **Who:** everyone on the CNAP roster can record papers, presentations and proposals. The per-period check-in goes to the RPPR Table 1 roles (PD/PI, Associate Director, RPLs, PPLs, core directors and core staff) and to core users (Table 2 asks whether core data went into publications and grant applications), plus anyone with papers or proposals to review. New Center-level relationship types: "PD/PI (Center Director)" and "Associate Director". No SPL role exists yet; Table 1B shows SPLs as 0 until one is added.
- **Foreign co-authors:** after "Any foreign authors? Yes", the form asks "Has NIGMS given prior approval for the foreign component?" (required). If No, the person is told NIH rules say the paper can't be listed in C.1 or cite P20GM113109, and the paper is left out of C.1 with that reason. "Any co-authors from non-IDeA states?" is asked of every published paper; C.1 flags those that need the PI's B.2 affirmation.
- **Never twice:** papers carry the RPPR year they were reported in; proposals carry the year counted as submitted and the year counted as awarded. "Mark these as reported in the Year N RPPR" sets them after the lists are downloaded.
- **RPPR tab** (admin), by budget period (June 1 – May 31): the C.1 list (published in the period, peer reviewed, not reported before, foreign rule) with the left-out items and reasons; Tables 1A (by funding source: NIH / Federal non-NIH / Non-federal) and 1B (by the lead's role on the submission date: RPLs, PPLs, SPLs, Core staff incl. the PD/PI, Others), following the guidance's notes: an application submitted and funded in the same period counts once, as an award; awards count once ever; the parent COBRE award (grant number containing GM113109) and anything marked as a supplement are never counted; for MPI/Co-PI/collaborator/subaward the CNAP investigator's portion is used (flagged when missing). Funding source comes from the person's answer (new question on grant forms), otherwise it's guessed from the agency name and marked "guessed". Downloads: C.1 list and Tables 1A/1B with what was and wasn't counted.
- **Preprints:** new publication type "Preprint (not peer reviewed)", never in C.1.
- **Acknowledgment help:** paper, presentation and grant forms show copyable NIH acknowledgment wording with P20GM113109 and the guidance's core fee-for-service sentence.
- Admin edit forms can correct every new field.

## 2026-10-26 — RPPR Table 2 (COBRE Core Users), D.1 participants, calendar months, eRA Commons help

Checked line by line against the FY27 COBRE Reporting Guidance (MW re-attached it the same day).
- **Core Usage Report** (new form, `core_usage_report`): assigned to each core director every collection (per core). One row per project with the guidance's Table 2 columns: type of user (RPL, PPL, Former RPL, Former PPL, Students, Other institutional, External), project name, technology/instruments/services, individual users per project (not students), student users (all levels), payment type (in-kind, voucher, fee-for-service, other), and whether core-generated data went into a grant application or publication. One added field, "User lab (PI's name)", is used only to count Total User Labs ("a user lab may be listed more than once if different projects were supported"); it is not a Table 2 column. About 10 minutes.
- Repeating rows now support dropdowns, Yes/No and whole numbers, laid out on an even grid (one column on phones). Whole numbers come back as "3", not "3.00".
- **Table 2 on the RPPR tab**: Table 2A, 2B, … for each research core (any core named "Admin…" is left out, per the guidance), with a totals row (Total User Labs = distinct labs; Total Users = individual + student users; the per-column sums are shown too), the guidance's suggested sentence ("There were N users of the … Core. N fee-for-service users; N voucher users …"), cores or collections not yet reported, a warning when both directors of a core submitted (possible duplicates), and the papers and proposals this budget year that say they used the core, to check against the last column. "Reports included" picks the collections; the default is the budget year's own Fall and Spring (MW: "This year's Fall + Spring", knowing Spring arrives after the RPPR is due about April 1). The CSV uses NIH's full column wording.
- **D.1 participants**: only the guidance's six categories: PD/PI, Core Director, Mentor, Project Leader (RP / PP / SP Leader), Trainee (Postdoc, Graduate student, Undergraduate student, High school student), Other. Associate Director, core staff, project staff and collaborators are "Other" ("research staff, … consultants"). Core users, general roster members and event participants are not listed. A person with several roles is listed once, in the first of: PD/PI, Project Leader, Core Director, Mentor, Trainee, Other (MW: RP Leader first; she expects a core director can't also be an RPL or PPL). New data check "Core directors who are also a project leader", and a warning when such a role is added; neither blocks it.
- **Calendar months** (MW asked whether to track them; D.1 lists people who worked at least 1.0 calendar month): new `PersonEffort` (person, budget year, calendar months 0–12). People in a D.1 role enter it on their Profile ("share of full-time effort × 12"); the evaluator can enter or correct it on the person page. People under 1.0 are set aside; people with none entered stay listed and are flagged. The CSV has the months column.
- **eRA Commons**: Person gets eRA Commons ID and trainee career level (Profile and admin). Under the field, "I need help with eRA Commons, or I'm not sure I need one" opens a short who-needs-one explanation and two buttons ("I need help setting up eRA Commons", "I'm not sure I need eRA Commons"); either records the request and e-mails the Administrator(s). The D.1 list shows who asked.
- **Table 1 fixes found in the re-check**: the award form never actually showed "your portion" (field listed but not defined); it does now, and it is required when the person is not the sole PI or the award is a subaward; total must equal direct + indirect and is described as the entire project period. Core-staff awards carry the guidance's note "report only if related to IDeA support (e.g., equipment grants)"; "Leave out of Table 1" (renamed) covers that case too. Column heading "Non-Federal Sources" as in the template.
- **Late items go in the next RPPR** (MW): papers and proposals dated in the previous budget year and never marked reported (typically April 1 – May 31, after that RPPR went in) are included in this year's C.1 and Table 1, marked "from Year N−1". Two years back is not carried. If nothing was ever marked reported for the previous year (the first year on this site), a banner says to open that year and mark its lists first, so items that already went in the earlier RPPR aren't counted twice. When an award is marked reported, its application is marked too, so it's never counted separately later.
- Two directors on one core: MW says BN has one director in reality (the sample data has two). The page still warns if two reports come in for one core and collection.
- When C.1 has papers with non-IDeA-state co-authors, the RPPR tab shows the guidance's required B.2 statement with a Copy button.

## 2026-10-26 — Milestone 9 (part 1): emailed sign-in links, codes, throttling, period e-mails

Implements the sign-in plan of 2026-10-24.
- **Emailed sign-in links** (`/accounts/link/`): enter an address; if it belongs to someone who may use links, a link is e-mailed. The page says the same thing either way (no way to test which addresses are on file). At most 3 links per address per hour. Links are single-use, last 7 days, and only a SHA-256 of the token is stored. Opening a link shows a "Sign in" button and the link is used only when it's pressed, so e-mail security scanners that pre-open links can't use it up. First sign-in creates the account (no password). Sessions last 8 hours.
- **Who may use links:** people outside K-State always; K-State people until single sign-on is switched on (`SIGNIN_LINKS_FOR_KSTATE`, default: not `SSO_ENABLED`). Administrators and superusers never: they use K-State single sign-on with two-factor.
- **6-digit code** before a link-signed-in person opens a confidential mentoring form (already enforced by the form view): sent automatically, valid 15 minutes, 5 tries, at most 3 codes per 15 minutes; stored as an HMAC.
- **Password sign-in throttle:** 10 failures for a username (30 for an address) in 15 minutes pauses sign-in for that username/address; the page offers an emailed link instead.
- **Period e-mails** (Reporting periods → E-mails; or `manage.py send_period_emails "<period>" open|reminder [--dry-run]`): "forms are open" goes once per person per period, listing their forms and the due date; the reminder lists only what's left, at most once every 3 days. People who use links get a personal link that opens My tasks; others get the site address and "sign in with your K-State eID". The page lists exactly who gets it, who doesn't and why (no e-mail on file, nothing left, already sent), and shows the wording. Sending is possible only while the period is open for answers. Every e-mail sent is recorded (`period_emails`) and audited. Wording is a draft for MW's review.
- **Production hardening:** mail server from `EMAIL_URL` (production refuses to start without one, so e-mails with sign-in links are never printed to logs); referrer and cross-origin-opener policies; client address for throttling from nginx's X-Forwarded-For; `check --deploy` clean except HSTS preload, which is a decision for the whole k-state.edu domain (silenced, documented).

## 2026-10-26 — Site-visit outcome tables (from MW's Year 9 workbooks)

MW shared her Year 9 site-visit workbooks for Publications, Presentations and Awards (read for layout and formulas only; no names or titles were imported).
- New **Site visit** tab (Publications and grants): publications by core × type × status in the workbooks' words (Submitted, Under Review, Accepted, Awaiting Publication, In Pre-Print, Published, Not Published); presentations by core × type; grants by core × Awarded/Pending/Declined with counts and dollars, and by funder (NIH / NSF / Other). Cores: BN, CN, NI, Admin, No core; an item crediting two cores counts under each ("duplicates counted") and each section states the number of distinct items. A date marks entries added after it (the workbooks' peach rows); the CSV flags items using two or more cores (the sand rows) and lists every item.
- Choices to confirm with MW: a year includes anything submitted, published, declined, presented, awarded or decided in it, plus papers and proposals still under review at its end (her Year 9 awards list carried Year 7–8 proposals); dollars are total costs (award total for awards, requested total otherwise); Admin Core counts only when "Administrative Core" is ticked as a resource (respondents can't pick it today).
- Told MW about three formula issues in the workbooks (swapped arguments in one publications count; "Total Awards" and "Total Pending" dollar cells that add every status; a column of always-zero counts and #REF! cells in the awards summary).

## 2026-10-26 — Independent security review of sign-in and e-mail (all findings fixed)

A separate reviewer, who hadn't seen the build reasoning, reviewed the sign-in and e-mail code against the sign-in plan. Fixed:
- The 6-digit code now also guards Preview, opt-out and file downloads of confidential mentoring forms (before, only the form page did; Preview showed submitted answers).
- `/admin/login/` (Django's database admin) now goes through the same throttled sign-in page.
- Failure counting uses the username as Django's login form sees it (Unicode-normalised, trimmed, any case), so "okafor " no longer dodges the limit.
- The client address is taken from X-Forwarded-For only if it's a valid address (a bad value used to cause an error page); nginx must replace that header with `$remote_addr` (deployment.md shows the config); the app container listens only on 127.0.0.1.
- Staff accounts can't get links; a link session ends at once if the account becomes an administrator, staff or superuser, or is disabled (middleware).
- A link stops working if its address no longer belongs to that person (corrected or moved address).
- Code tries are counted atomically (parallel guesses can't share a count); two links used at once can't cause an error when creating the account.
- The code goes to the address the person signed in with.
- Link requests: at most 20 per address of origin per hour, and the e-mail is sent off the request so a known address doesn't answer more slowly than an unknown one.
- Production refuses any mail backend except SMTP; the development settings refuse to run when `.env` says `DEBUG=false`; docs corrected (`EMAIL_URL`, not `EMAIL_HOST`); nginx doesn't log sign-in link paths.
- K-State is recognised however the institution is spelled ("kansas state university", "KSU", "K-State").
- "Turn off sign-in" for someone who has never signed in explains how to stop them (untick Active: inactive people can't use any link).
- Tests added for each.
Known trade-off kept: anyone can pause password sign-in for a username for 15 minutes with 10 wrong tries. Respondents can still use a link; administrators will use single sign-on, which this doesn't affect.

## 2026-10-26 — Site-visit choices confirmed (MW)

- **No double counting across years:** a year's numbers count only papers and proposals with something that happened in that year (submitted, published, declined, presented, awarded, decided). Ones submitted earlier and still waiting are listed separately, "Still pending from earlier years" / "Still under review from earlier years", with their count and requested dollars, and are not in the numbers (MW agreed counting them in both years would inflate the tables).
- **Dollars:** award total for awards; amount requested for pending and declined proposals; always total costs (direct + indirect).
- **Admin Core** is now on the respondents' list of Center resources for papers, presentations and grants (it was left off the flows' list), so the Admin Core column fills in like the workbooks'.
- **Design preference (MW):** avoid two-column layouts almost always. The screens gallery is now a single list. Profile and the person page still show two panels side by side; asked MW whether to stack them.
- **Writing preference (MW):** messages to MW use short sentences with plenty of space between them, explain each choice with an example and a recommendation, and avoid italics.
- (same day) Earlier-year pending items show when they were submitted (and in which grant year) and when they were first entered on the site. A "Pending proposals" table tallies pending submitted this year, pending from earlier years, and all pending, with requested dollars; only "submitted this year" is in the main tables. The CSV has the same tally and list.
- (same day) MW asked for a slightly faster pace: run the tests that cover a change while working, the full suite at each checkpoint, and screenshots only for visual changes.
- (same day) Paired panels (Profile, person page, project form) stack in one column; the menu highlight for the current page was broken (escaped attribute) and is fixed.
- (same day) eRA Commons help uses MW's wording. K-State people are pointed to K-State's central research office (research@k-state.edu) to create an ID or move one to K-State; people outside K-State are pointed to their own institution's research office. The "I need help" buttons stay.
- (same day) Wherever respondents are told to contact the evaluator, the address is shown: mkwills@ksu.edu (setting `EVALUATOR_EMAIL`).
- (same day) Quieter look across the site and the prototype (MW: about 13% calmer): all sizes scale to 87%, body text 14px, slimmer text fields, a softer focus ring. Open-ended questions use smaller, lighter question text, shorter boxes and no dividers between them.
- (same day) The Means / Means and SD switch keeps the button in place when the table changes width (it used to jump). SDs show by default.
- (same day) Core Usage Report: "User lab (PI's first and last name)"; the intro's first sentence split in two.
- (same day) Papers and proposals that are Published, Awarded, Declined or Not funded get "View or edit" on the person's list, opening their details prefilled. Re-saving a declined paper or a not-funded proposal never creates a second resubmission record.
- (same day) Prototype fixes found while matching the NeuroSync report: its Table 2 now has the school-year and Year header rows, SDs (Means / Means and SD), the red/blue shading, and the report's overall SDs; its NI Core prior-year averages were the old misread values (mean and SD columns swapped in the first import, fixed in the real site on 2026-10-25) and are now rebuilt from the same file as the real site.
- (same day) RPPR tab redesigned for low cognitive load (MW): four summary tiles at the top (C.1, Table 1, Table 2, D.1) that jump to their sections; each section has lots of space above it, its key numbers rolled up into the header, a one-line "what it is and why NIH asks" description, and its CSV link on the right. Tables in a section share column widths so they line up (Table 1A over 1B; the per-core Table 2 tables; the D.1 category table). D.1 shows a category roll-up with what's still needed; the full list of people opens on request. "Mark as reported" sits in its own section at the end. Wide tables no longer widen the page (they scroll inside their box).

## 2026-10-27: NIH documents, ORCID, research teams, quick RPPR items (MW)

- **NIH documents** (form `nih_documents`): once a year, in the Fall period (`display.yearly_sequence = 1`), for the PD/PI, RP Leaders, PP Leaders and core directors; one task per person. RPPR D.2.a in NIH's wording (checked against the Year 9 RPPR); a Yes requires an explanation. Certified SciENcv biosketch and Current and Pending (Other) Support (required), signed MFTRP certification (required; the blank form is still to come from MW), foreign-activity documents (optional). PDFs only, and the file must start like a PDF. Always a new upload each year (no "no changes" option). RPPR tab: who turned in what, a "Download all" zip named Last_First_Document.pdf with a summary sheet. SciENcv Common Forms are required for RPPRs from Jan 25, 2026.
- **ORCID iD** on the Profile for those roles and on the person page; ISO 7064 check digit; in the D.1 CSV.
- **Progress reports** (RPL, PPL, core): a research team list (name, email, eRA Commons ID, role, calendar/academic/summer months: the D.1 columns), seven quick RPPR yes/no items (B.1.a, C.3, C.4, C.5.a, C.5.c, F.3, G.9) with one details box required when an answer needs attention, and an optional upload for the suggested RPPR tables. Shown on the RPPR tab under "From progress reports".
- From MW's Year 9 RPPR (read for structure only; nothing copied; working copy deleted): D.1 also has Degree(s), academic and summer months, foreign organization and country, and supplement support, which the site does not collect yet. Budget items (G.10, G.12) stay with the grants office.
- Open: reading degrees and person months from the uploaded SciENcv PDFs (needs sample PDFs from MW); a February "has your Current and Pending changed?" check.
- **NOT-OD-26-018 / NOT-OD-26-033** (MW sent the notice, 2026-10-27): wording updated. Biosketch PDF includes the NIH Biographical Sketch Supplement; don't flatten certified SciENcv PDFs; ORCID must be linked to eRA Commons and show in the PID section; the annual MFTRP certification goes in RPPR G.1 as a flattened PDF named MFTRPcert_[Name].pdf (the zip uses MFTRPcert_Last_First.pdf); foreign-contract supporting documentation is a separate flattened attachment. Common Forms enforced from May 8, 2026. The Current and Pending Common Form gives effort only as total person months (no calendar/academic/summer split), so D.1's split still comes from the site (team lists, Profile), not the PDF.
- **Reading SciENcv PDFs** (MW sent a sample biosketch and Current and Pending, 2026-10-27; read for layout only, copies deleted, tests use made-up text): on upload the NIH documents task says at once if a biosketch or Current and Pending isn't the Common Form or isn't certified ("Certified by … in SciENcv on …"). The person page shows what the documents say (degrees from Professional Preparation, the ORCID iD, the CNAP award's person months by year) with "Use these" buttons; nothing is saved without the evaluator choosing it. The RPPR tab marks each file "certified YYYY-MM-DD" or "not certified". The Current and Pending lists person months by year without saying which budget period each year means, so the months are shown for checking, not filled in. reportlab and pypdf added to dependencies.
- **Which months a Current and Pending "year" covers** (MW: read it from the project's start and end months): the years listed are matched to calendar years (cut at the start and end months) or to 12-month periods counted from the start month, whichever reading gives exactly the years in the PDF; if neither does, the years are shown unmatched. MW's sample (Jul 2022 – May 2026, five years with half-size first and last entries) reads as calendar years. The person page then estimates the person months in the current and previous CNAP budget years, spreading each listed year evenly over its months, for checking D.1.
- **Who gives what** (MW 2026-10-27, "an annual look at all people involved"): Current and Pending from everyone asked (PD/PI, RP Leaders, PP Leaders, core directors); biosketch and MFTRP certification only from people named on the Notice of Award. Person.senior_key (person page: Automatic / Yes / No); automatic means the PD/PI and RP Leaders (FY27: senior/key = those named on the NoA). The form uses a hidden, site-set question so the forms engine shows and requires those sections only for NoA-named people. D.1 download gets a Sr/Key column.

## 2026-10-28: automatic period e-mails (MW)

- While a period accepts answers, a daily job (`send_scheduled_emails`, 08:00) sends: the "forms are open" e-mail on opening day (and to anyone added later); a reminder every 4 days until the due date, counted from each person's last e-mail; then, after the due date, a reminder every day until the period closes ("your forms were due …, and the session is still open"). Only people with forms still to do get reminders; nobody gets two in a day. Each period has a pause switch on its E-mails page, which also lists the dates and still sends one by hand. Manual reminders follow the same 4-day gap.
- **February Current and Pending check**: everyone who turned in fall NIH documents is e-mailed on February 1 (of the budget year's second calendar year): "Has your Current and Pending changed since the fall?" "Nothing has changed" is one click; "It changed" takes the new certified PDF (uncertified or wrong forms are refused with the reason). Reminders every 4 days to February 15, then daily until March 1; also shown at the top of My tasks. The RPPR tab shows each answer, and an updated copy replaces the fall one there and in the zip. Run by the same daily job; dates in settings (CP_CHECK_ASK / _DUE / _STOP).

## 2026-10-28: look and form experience (MW)

- New look: light lavender sidebar; colour moved to actions and progress; welcome with a progress ring on My tasks; white panels lifted with a faint purple-tinted shadow and fewer rules; Bricolage Grotesque for headings only (Google Fonts for now; self-host on the K-State server); line icons per task group; a calm finish with a neuron drawing; form titles in K-State purple with white text.
- Forms: answers save as people go (autosave endpoint; files still save with Save draft/Submit); "(optional)" marks the few optional questions instead of a star on every required one (conditionally required questions get neither); a slim strip follows the reader ("Section 2 of 4 · about 5 min left"); rating scales are one row of rounded choices (stacked on phones); a thank-you after submitting.
- Intros shortened for ten forms, with MW's approval; question wording unchanged. Each original is kept in the form's _source note.
- One motion moment when a form opens: a light line traces the title once and the directions appear line by line. Nothing moves while people read; all of it is off for reduced-motion users.
- The name in the sidebar links to the Profile.

## 2026-10-28 · My tasks: year by year
- The "What CNAP produced this year" band has a "See year by year" button. It opens, in place, four small bar charts (papers published, talks and posters, proposals submitted, proposals awarded) from the earliest budget year with an entry to now; empty years are kept so the trend is honest, and the current year is marked as still in progress. Counts only, no names. The button is hidden until there is an earlier year to compare.
- Labels now read "proposals submitted" and "proposals awarded" (MW).

## 2026-10-28 · Center results: Products tab
- Respondents get a Products tab under Center results: papers published, talks and posters, and proposals awarded, by budget year, with a year picker. Submitted proposals are a count only; pending and unfunded proposals stay private. Linked from the My tasks band ("See the full list"). A line now separates this year's numbers from the year-by-year button.

## 2026-10-28 · PL Guidelines retired
- The CNAP Phase 2 PL Guidelines are removed from Helpful documents as outdated (MW). add_default_documents now hides it if present.

## 2026-10-28 · Core RRIDs (handbook chapter 14)
- Each core has an RRID (Core.rrid), set on Projects and cores. Input is normalized to RRID:SCR_nnnn; other RRID kinds are refused; two cores can't share one. Changes are audited.
- Marking a paper Published asks, for each ticked core that has an RRID: "Did you cite the [core]'s RRID (RRID:SCR_…) in your methods?" Yes / No / Not sure, required once that core is ticked; hidden otherwise. Saved on PublicationResource.rrid_cited. The evaluator can correct it on the paper's edit page.
- The "How to acknowledge CNAP" box now gives the RRID citation for each core. The fee-for-service wording no longer cites the grant number and says "No IDeA funds were used to support this work" (handbook ch. 14, NIH's suggested approach). Old wording: "We acknowledge the CNAP COBRE (P20GM113109) for the use of the [BN / NI / CN] Core as fee-for-service. The Core was used for [describe the use of the Core]."
- Evaluator: RRID tags on the Papers tab, a "Core RRID not cited" filter and summary line, a "Papers citing its RRID" row per core on Counts, a column in the citation CSV, and two data checks: published papers that used a core without citing its RRID, and papers with foreign co-authors that cite the grant without NIGMS approval.
- The sample center uses fictional RRIDs (SCR_990001, SCR_990002) for BN and NI; CN has none so its question stays hidden.

## 2026-10-28 · Other Significant Contributors (handbook ch. 6)
- New relationship type "Other Significant Contributor (OSC)", center-level. Added from a person's page like any role.
- RPPR D.1 lists OSCs at any effort, under the guidance's "Other" category, labeled "Other (Other Significant Contributor)"; an OSC with no months entered shows 0.0 (the 2026 RPPR accepts 0.0). The D.1 note says a new OSC needs a biosketch in the RPPR.
- The OSC role alone brings no forms: it is left out of the audience for universal surveys. Someone who is an OSC and also holds another role gets that role's forms as before.
- The sample center has one fictional OSC (Imogen Rowe, University of Kansas), not on the roster.

## 2026-11-02 · OSCs give a biosketch (MW: yes)
- Other Significant Contributors get the yearly NIH documents task. A hidden site-set answer (osc_only: an OSC holding none of PD/PI, RPL, PPL, core director) hides the effort, Current and Pending and foreign sections and shows the biosketch section only. Someone who is also in a full-task role keeps the full task.
- The RPPR tab marks them "OSC"; only the biosketch counts as missing for them. nih_documents v9; the intro and biosketch instructions are worded for both groups.

## 2026-11-02 · February Current and Pending check: dates and the fall copy
- The question, its page and the first e-mail now say the progress report is due April 1 (60 days before the June 1 budget start) and to answer by February 15, and link to the Current and Pending they turned in so they can look it over first.
- My tasks line reads as a sentence: "You have 2 tasks left, about 4 minutes in all."

## 2026-11-02 · Review-round edits (MW)
- Full-sentence status lines throughout the respondent pages ("You have 4 tasks left, about 37 minutes in all."; "They’re due in 16 days, on November 18."; "You’ve finished 2 of 3 sections."). Dense admin counters stay short.
- Core directors: "Since you’re the Behavioral Neuroscience (BN) Core Director, you do not receive the BN Core user survey." plus MW's note about opting out of the other core user surveys.
- Welcome: bigger, thicker ring that fills once; a "Next up" card with the first task and a Start button; a "Keep it up!" note with a thumbs-up that fades after a few seconds (only once something is done and something is left).
- Group headers 1.3rem; "To do" and "Done" 1.55rem. The time half-moon spans the row's height and hugs the time; its edge is light purple.
- Produced band: "What CNAP has produced this year"; the art is a brain drawn as a network, with one pathway that lights up once when the band comes into view (plasticity). Reduced motion: no animation.
- Rating scales: N/A sits on the same line as 1–5, after a dashed divider, as a dashed tile, so it's seen but not read as a scale point.
