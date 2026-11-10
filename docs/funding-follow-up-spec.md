# Funding opportunities and the not-funded follow-up (build spec)

Requested by MW on 2026-11-10. Written in a chat that could not install packages, so nothing here has been
built or tested yet. The next session builds it on branch `feature/funding-follow-up`, following the
working rules in `docs/handoff.md` (full test suite, real screens at desktop and phone width, decisions.md,
data dictionary, ruff clean, one commit, a zip for MW).

The source material for the opportunity list is MW's standalone tracker, a claude.ai artifact named
"CNAP Funding Tracker" (https://claude.ai/artifact/YUGQVm8yfhrrbi5kkUQyzJ), and its sources. The public
opportunity facts are copied into `fixtures/funding/opportunities.json` with a source link for each row.

## What MW asked for, in her words

1. A funding tab for each investigator in the Reporting Hub.
2. "When someone updated their proposal product to not funded, we can immediately direct them to this page."
3. "After I review it, there was a newsletter type email that was sent to the applicant, but that also
   traces back to this page, with perhaps more info and fuller explanation."
4. "A portion of the page for general awards matched to a large number or anyone. Maybe there
   researchers can submit their own suggestions?"
5. "I would like a section for the latest grant funding news."

## Settled rules that apply

- Fictional data only until K-State hosting and security review (handoff.md). The opportunity catalog is
  public information and may be seeded. Matches to real investigators are NOT seeded; MW enters them in
  the live system. Demo matches use the fictional sample people from `manage.py seed`.
- A person sees only their own matches and their own letters. No respondent sees another person's
  matches, letters, or grant details.
- The design rules below, and the prototype look for new screens (`apps/common/prototype.py`; new
  screens get a `proto/` template and are listed in `SCREENS`).
- Every create, change, send, and decision goes through `record_event`.
- Respondents' editing is subject to `entry_open` (closed for a few days after a period closes) only
  where it already applies; reading the funding page is always open.

## Design rules (binding)

Every new screen and the email follow MW's "CNAP Hub Design Rules" Claude Doc
(https://claude.ai/artifact/FhUSSs2whcKJeUom1sxUuq, rev 55 read 2026-11-10), including its page
checklist A to Z. Where this spec and the rules differ, the rules win. Points that matter most here:

- Start from an approved screen; no new layouts. Respondent "Funding opportunities" starts from My tasks
  (Screen 3); the letter page from the progress report (Screen 21) reading view; the admin Funding pages
  from the reporting session dashboard (Screen 53) and its record lists (checklist V).
- Things no approved screen has go to MW as a choice before they are built (checklist Y): the
  opportunity row design, the news list, the suggestion form, and the newsletter email layout.
- Title panel: gray, purple dot and context line ("Funding," "Administration"), Lora title stating the
  subject as a fact, one purpose sentence, facts row (for example "12 opportunities · 3 matched to you ·
  Next deadline December 1, 2026"). One white page below it, sections divided by thin lines, no boxes
  inside boxes. "On this page" list on the left for the long pages.
- Roll-ups with counts in the headers (For you, Open to everyone, Funding news, Letters from the
  Center, Suggest an opportunity), one Show all and Collapse all, spacing per checklist Z.
- Lists of records are stacked rows (name first as the link, then a status word, then the facts),
  never two columns; tables that repeat share column widths; on phones each row becomes a short block.
- Color only with a word beside it. Status and milestone labels are words: "Counts toward the R01
  milestone," "Ask your program officer," "Bridge funding." Deadlines written out ("December 1, 2026"),
  with "45 days left" as words, not a colored chip alone.
- Only the main action is dark purple: Send on the composer, Send suggestion on the form. Send asks
  first in a lavender note under the button: "Yes, send the letter to [name]" and "No, go back." Success
  messages use the button's word: "Sent," "Added," "Declined," "Archived."
- Writing: one sentence per line, no italics, no semicolons, Oxford commas, abbreviations spelled out
  (Early Stage Investigator, program officer), CNAP and RPPR in capitals, "email," nouns not pronouns,
  directions start with the verb (never "Please"), professional tone ("a follow-up letter," never a
  "nudge"). Respondents see "members" where the Hub describes what people entered.
- The email follows the period-email pattern decided 2026-11-08: HTML with a plain-text fallback; four
  editable parts (subject, opening, closing, sign-off) plus MW's optional personal paragraph; the
  featured opportunities as a two-column table (opportunity, deadline); the button and sign-in
  directions fill in automatically. The name of the letter is identical in the email, the queue, and the
  letter page.
- Every button and link has a hover description; every "i" and "?" follows the rules' placement.
- Before MW's review: side-by-side with the approved screen, every word read against section C,
  before-and-after screenshots at desktop and phone width, full test suite.

## Data model (new tables in `apps/outcomes`, migration 0017)

`FundingOpportunity` (`funding_opportunities`), archivable:
- `name`, `sponsor`, `source_kind` (closed set in `apps/common/enums.py`: `nih`, `federal_other`,
  `foundation`, `institutional`, `center`), `mechanism` (blank ok), `amount_text`,
  `deadline` (date, null), `deadline_text` (for "annual, early March" style dates), `url` (blank ok),
  `summary` (one or two plain sentences), `fuller_text` (the longer explanation for the letter page),
  `counts_toward_milestone` (closed set: `yes` R01-equivalent, `ask_po`, `no` bridge),
  `esi_only` (bool), `audience` (closed set: `matched` shown only to matched people, `everyone` shown in
  "Open to everyone"), `checked_on` (date the facts were last confirmed), `source_url`,
  `suggested_by` (FK Person, null), `created_by`.
- Check constraints for the closed sets, as elsewhere.

`FundingMatch` (`funding_matches`): `opportunity` FK, `person` FK, `why` (one sentence MW writes:
why it fits this person), `added_by`, `added_at`, `ended_at` (null; ending hides it, never deletes).
Unique open match per (opportunity, person), the same partial-unique pattern as `outcome_delegates_one_open`.

`FundingSuggestion` (`funding_suggestions`), following the `roster_suggestions` pattern: `person` FK
(who suggested), `name`, `sponsor`, `url`, `deadline_text`, `why`, `for_everyone` (bool: "this could help
others too"), `status` (`to_review`, `added`, `declined`), `handled_by`, `handled_at`, `opportunity` FK
(null; set when MW adds it), `note_to_person` (optional, shown back to the suggester).

`FundingNewsItem` (`funding_news`), archivable: `headline`, `news_date`, `summary` (two or three
sentences in MW's own words, never copied text), `source_name`, `source_url`, `pinned` (bool),
`posted_by`, `posted_at`. Everyone signed in reads published items; only admins write.

`FundingFollowUp` (`funding_followups`): one per grant submission marked Not funded.
- `grant` FK GrantSubmission (unique), `person` FK (the lead, from `nudges.lead`), `created_at`,
  `status` (`to_review`, `sent`, `dismissed`), `subject`, `opening`, `body_note` (MW's personal
  paragraph), `opportunities` (M2M to FundingOpportunity: the ones featured in the letter),
  `sent_at`, `sent_to`, `sent_by`, `dismissed_reason`, `letter_token` (random; see Letter page).
- Re-saving a Not funded proposal never creates a second follow-up (get_or_create on `grant`).
- A follow-up whose proposal later changes away from Not funded shows "Status changed since" in the queue.

Regenerate the data dictionary after the migration.

## Screens

### 1. Respondent: "Funding opportunities" (new portal page)

URL `/funding/`, name `portal:funding`. Linked from the Publications, talks, and grants page header and
from My tasks' helpful links. Delegates entering for someone see that person's page, the same as `_owner`.

Sections, in this order:
1. **For you** (only if the person has open matches): each opportunity as a row with name (links out to
   the sponsor), sponsor, deadline with days left, amount, a milestone label (R01-equivalent / Ask your
   program officer / Bridge funding), and MW's one-sentence "why." Sorted by deadline, undated last.
2. **Open to everyone**: every opportunity with `audience=everyone`, same row design. This is where
   center-wide items live (IDeA co-funding, the R01 standard due dates, career-stage awards).
3. **Funding news**: the latest items, pinned first, then newest; five shown with "Show all". Each:
   headline, date, the short summary, and the source link. Examples of what belongs here: NIH policy
   changes that affect applicants (the six-applications-a-year limit, the end of continuous submission),
   payline and success-rate news, new or reissued programs, deadline changes.
4. **Letters from the Center**: links to any follow-up letters sent to this person (see 4).
5. **Suggest an opportunity**: a short form (name, sponsor, link, deadline, why it is worth a look,
   "This could help other CNAP researchers too" checkbox). After sending: "Sent. The CNAP team will review
   the suggestion." The person's own suggestions list below with their status and MW's note.

A short note at the top for anyone who has never had a match: "The CNAP team adds opportunities picked
for you here. Everything below is open to all CNAP researchers."

### 2. Not funded: send the person here

In `apps/portal/outcome_views.update`, when `kind == "grant"` and `to == "not_funded"`:
- Keep MW's existing `NOT_FUNDED_NOTE` message (her words, unchanged).
- Create the `FundingFollowUp` (get_or_create) for the lead person.
- If a resubmission was created (`created`), keep the current redirect to the new A-version's planned
  details, and add one info message with a link: "When you're ready, your funding opportunities page
  has options picked for this moment." Otherwise redirect to `portal:funding` instead of the outcomes list.
- Add one line under the encouragement on the funding page when arriving from a not-funded update
  (`?from=not_funded`): "The CNAP team will follow up with you personally."
- The same applies to the admin `grant_edit` path only for creating the follow-up (no redirect for MW).

### 3. MW: "Funding" in the manage area (new admin screens, `@admin_view`)

URL `/manage/funding/` with four tabs:
- **Follow-ups**: the queue. Each row: person, proposal title and version, agency and mechanism, date
  marked Not funded, decision comments, discussed with a program officer (and name/date), plans to
  resubmit, and status. Opening a row shows the composer (below). "Dismiss" asks for a reason.
- **Opportunities**: the catalog. Add, edit, archive. Each row shows how many people it is matched to
  and its `checked_on` date; rows not checked in 90 days get a "Check dates" chip. A per-person matching
  control: on the opportunity page, add or end matches with the existing people search
  (`os.people_search`), each with a "why" sentence. Also a "Funding" panel on the admin person page
  (`manage/person.html`) listing that person's matches with Add and End.
- **Suggestions**: researcher suggestions to review. "Add to the list" opens the opportunity form
  pre-filled (audience defaults to `everyone` if the person ticked "could help others"), then marks it
  `added`. "Decline" with an optional note to the person.

- **News**: add, edit, pin, archive news items. A summary field note reminds MW to write it in her own
  words and link the source.

The home dashboard gets a count chip: "Funding follow-ups to review: N" and "Suggestions: N".

### 4. The follow-up letter (email + Hub page)

**Composer** (MW only), on the follow-up's page:
- Pre-filled subject: "Your next steps after {proposal title}".
- Pre-filled opening (editable): warm, in MW's voice, adapted from `NOT_FUNDED_NOTE`.
- MW's personal paragraph (blank, optional).
- Featured opportunities: tick boxes, pre-ticked with the person's open matches plus any
  `audience=everyone` item whose deadline is within 120 days. Each shows its summary.
- Automatic sections (not editable, always included when they apply):
  - If the proposal was an NIH R01, R15, or R35 (mechanism text) and single-PI: the IDeA co-funding note
    and "talk to your program officer about co-funding" (Handbook ch. 19; text in the fixture's center
    items). If `discussed_with_program_officer` is No or empty, say so gently.
  - If `plans_to_resubmit`: the A1 is already started, with a link to it.
  - The CNAP grant-writing supports (`nudges.SUPPORTS`).
  - "Funding news": the three newest news items, headline and one line each, linking to the Hub.
- **Preview** shows the email exactly as it will go (HTML with plain-text fallback, as period emails
  do since 2026-11-08) and the Hub letter page.
- **Send** sends to the person's primary email, cc delegates (same as `nudges.due`), records
  `sent_*`, writes the audit event, and marks the follow-up `sent`. Nothing is ever sent automatically.

**Email** (newsletter style, short): greeting, the opening, MW's paragraph, up to three featured
opportunities as compact cards (name, deadline, one line), a button "Read your full funding update", and
the sign-off. The button is a sign-in link (`signin.make_link(..., purpose="funding_letter",
next_path=...)`) when `signin.may_use_link(person)`, else the plain site URL, exactly as nudges do.

**Letter page** `/funding/letter/<pk>/` (respondent, sign-in required, owner or their delegates only;
403 otherwise): the full version. Every featured opportunity with its `fuller_text`, eligibility notes,
milestone label, deadline, and source link; the automatic sections in full; MW's paragraph; and a link
to the person's Funding opportunities page. Letters are listed under "Letters from the Center".

Templates: `email/funding_letter.html` and `.txt`, `proto/portal/funding.html`,
`proto/portal/funding_letter.html`, `manage/funding*.html` (admin pages follow the current manage look).

## Wording to confirm with MW before building

- The pre-filled opening sentence for the letter.
- The three milestone labels (proposed above under Design rules).
- The "For you" empty-state sentence.

Show MW these on a preview before the commit, per working rule 5.

## Seeding

- `manage.py seed` loads `fixtures/funding/opportunities.json` (idempotent, keyed on `name`).
- Sample matches only to fictional seeded people, plus one fictional Not funded proposal with a
  `to_review` follow-up and one `to_review` suggestion, so every screen has something to show.

## Tests (new `tests/test_funding.py`)

1. Marking a grant Not funded creates exactly one follow-up; saving again does not create another.
2. Not funded without resubmission redirects to `portal:funding`; with resubmission keeps the existing
   redirect and adds the info message.
3. A person sees their own matches and `everyone` items, never another person's matches or letters
   (letter page returns 403 to others, 200 to owner and active delegates).
4. Ended matches and archived opportunities are hidden from respondents.
5. Suggestion submit creates `to_review`; "Add to the list" creates the opportunity and links it.
6. Send: one email, correct recipients (person + delegates), sign-in link when allowed, follow-up marked
   sent, audit event written; a second Send is refused.
7. The co-funding section appears only for NIH R01/R15/R35 single-PI proposals.
8. Fixture loads twice without duplicates.
9. `test_migrations.py` still passes (models and migrations agree).
10. News: archived items are hidden; pinned items list first; only admins can create or edit.
11. Admin pages refuse non-admins (same pattern as other `@admin_view` tests).

## Not in this build (say so to MW)

- Automatic matching by keywords. Matches are MW's choices.
- Scheduled deadline-reminder emails for opportunities (a natural next step, using the daily job).
- Pulling opportunities or news from Grants.gov or the NIH Guide automatically. A later option: a
  weekly scheduled Claude task that drafts news items and new opportunities for MW to review and post;
  nothing would appear in the Hub until she approves it.
