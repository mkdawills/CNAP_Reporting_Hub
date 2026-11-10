# Handoff: start here in a new session

Read this file, then `docs/decisions.md`, then the milestone you are asked for. Do not ask for the
master prompt, the Architecture Review or the source forms to be re-uploaded: everything a milestone
needs is in this repository. Ask only for a specific document if a task names it.

## What this is

The CNAP Evaluation and Reporting Platform: a Django 5.2 LTS + PostgreSQL 16 web application that
replaces Piestar for the CNAP Center at Kansas State University. It collects the Center's evaluation
instruments on a reporting-period cycle, assigns them from people's current CNAP relationships,
computes survey results with stable longitudinal identity, and records what was officially reported.

Owner and product decision-maker: Morgan (MW), CNAP grants administrator. Build 1 is in progress.

## Where things are

| Thing | Where |
| --- | --- |
| Schema of record | `apps/*/models.py` and each app's `migrations/0002_constraints.py` (composite FKs, exclusion constraints, views, trigger) |
| Closed sets (statuses, kinds, scales) | `apps/common/enums.py` |
| Reference data (cores, relationship types, answer sets, pathways, roles) | `apps/admin_center/reference_data.py`; `manage.py seed` |
| Decisions made during the build | `docs/decisions.md` (append one paragraph per choice) |
| Data dictionary | `docs/data-dictionary.md` (regenerate with `manage.py data_dictionary`) |
| Tests | `tests/` (51 passing at Milestone 1; `make test`) |
| Deployment, SSO, backups | `docs/deployment.md`, `docs/sso.md`, `docs/backup-and-restore.md` |
| Architecture Review and Build 1 plan (Claude Doc) | https://claude.ai/artifact/1taVbRzVkdixkHBNVcLHb6 (tabs: review, implementation plan, analytics addendum) |
| Data-model canvas | https://claude.ai/artifact/AD2CpuorLViEvWcodKvj8n |
| Clickable prototype of the Build 1 screens | https://claude.ai/artifact/7D8ozEZoyNeTuuM77mnCdt |

The Claude links are owned by MW's original account; if they are not shared with the account you are
working in, this repository is sufficient on its own.

## Settled decisions you must not reopen

- Fictional test data only until K-State hosting and security review. Never reproduce names or
  e-mails from any uploaded Piestar export or Year 9 spreadsheet; never seed from them.
- Preserve source form wording exactly. Section titles are data (a renamed section is a form edit).
- Respondents never see another respondent's answers. They see aggregates only after results are
  finalized, hidden below 5 responses, never for mentoring forms (decisions.md, 2026-10-22).
- The evaluator (holder of `reporting.view_confidential_mentoring_data`, MW) reads every response.
- Center Leadership (Center Director, Associate Director) reads mentoring forms and Project Progress
  Reports identified, and all other surveys de-identified (decisions.md, 2026-10-22).
- Mentor Questionnaire, Mentee Survey, Pilot Mentor Report and Primary Mentor Report are
  confidential: individual and aggregate results are visible only to holders of that permission.
- Project Progress Reports are read by administrators for official reporting. No role carries it; superuser does not
  imply it; Evaluation Staff never have it. In Build 1 only MW holds it.
- `core_director` is NOT single-holder (co-directors are allowed). Project Leader and Pilot Awardee
  are single-holder per project.
- A Core Director does not receive their own core's survey (rule: `excluded_relationship_type` +
  `form_definitions.about_core`); they still receive the other two core surveys.
- Core and NeuroSync surveys have structured opt-out paths (`core_non_use`, `non_attendance`) whose
  answers are ordinary survey data and count the assignment as complete.
- Options always come from answer sets; questions carry a measure for longitudinal identity;
  `scale_kind` must agree across question, answer set and measure (enforced in the database).
- One assignment per (person, form, period, project, core) with NULLS NOT DISTINCT; generation is
  INSERT … ON CONFLICT DO NOTHING; regeneration never duplicates or deletes.
- Reporting periods are records (grant_year, sequence, short_label, display_order); nothing in code
  is named Y6 or Y9. Period close: open → closed → results generated (snapshot v1) → reviewed →
  finalized; a later correction creates a new snapshot version by explicit, audited action.
- Column is `provenance`, not `source`, for where a response/assignment came from.
- Never fabricate row-level data from aggregates. Imported Year 6–9 aggregates are stored as
  aggregates with provenance `historical` and have no drill-down.

## Next up (2026-11-10)

Phase 1 of `docs/funding-follow-up-spec.md` is built on branch `feature/funding-follow-up` (funding page,
letter page, not-funded follow-up letters, suggestions, news, the seven questions). MW approved it and it is
on main (2026-11-10). Next: resources (spec section "Resources"), then phase 2, the discussion, whose posts must
allow links to other websites.

## Milestone status

| # | Milestone | Status |
| --- | --- | --- |
| 1 | Scaffold, database with integrity rules, auth, roles, audit, admin | Done 2026-10-21 |
| 2 | People, relationships, projects, cores: admin workflows, roster import, director handoff | Done |
| 3 | Forms engine: definitions, versions, questions, answer sets, measures, conditional rules | Done |
| 4 | Form runner: My Tasks, drafts, repeatable sections, opt-out pathways, My History | Done |
| 5 | Assignment engine and reporting-period lifecycle (incl. "open for preview") | Done |
| 6 | Portal: profile, rich profile, dashboards for respondents | Done |
| 7 | Administrator home, drill-downs, exemptions, reopen, data-quality checks | Done |
| 8 | Analytics: survey results, snapshots, themes, year-over-year tables with Y6–Y9 averages, exports | Done |
| — | Publications, presentations, grants (MW's flows), RPPR C.1 / Tables 1A, 1B, 2 / D.1, site-visit tables | Done 2026-10-26 |
| 9 | Deployment hardening, emailed sign-in links, period e-mails, SSO switch, backups, operator runbook | Links, codes, throttling, period e-mails and hardening done 2026-10-26; SSO adapter waits for K-State IT; runbook in `docs/runbook.md` |

Each milestone ends with: tests passing (`make test`), `ruff check .` clean, `docs/decisions.md`
updated, data dictionary regenerated if models changed, one commit, and a zip for MW.

## Working rules (MW, 2026-10-26: accuracy and thoroughness come first; never trade them for speed or cost)

1. Check anything that must match a source (MW's specs, NIH guidance, the site-visit reports) line by line
   against that source before building it. If the source isn't in the workspace, ask MW for it; don't work
   from memory or notes, and say so whenever something rests on an assumption.
2. Run the full test suite and look at the real screens (desktop and phone width) before calling anything done.
3. High-stakes checks (privacy review, final sanity check, numbers that go to NIH) get an independent review by
   a reviewer who hasn't seen the work.
4. Do not re-derive settled decisions. If one seems wrong, say so in one line and ask.
5. Put findings and choices in `docs/decisions.md`. Follow MW's design preferences (clean, low cognitive load,
   plain words for respondents, consistent spacing; see decisions.md) on every screen, and carry every
   prototype tweak into the real build.

## Running it

```
cp .env.example .env            # set DATABASE_URL, SECRET_KEY
make up                          # docker compose: web + postgres
make migrate && make seed        # schema, reference data
make superuser                   # first administrator (creates the Person too)
make test                        # pytest, reuse-db
```

Without Docker: a local PostgreSQL 16 with the btree_gist extension available, `pip install -e .[dev]`,
and the same `make` targets.
