# Four-screen design prototype (MW 2026-11-05)

Branch: `feature/cnap-ui-redesign`. Baseline: `83de15a` on `main` (unchanged).

## Turn it on (local only)

    UI_PROTOTYPE=1 python manage.py runserver

With `UI_PROTOTYPE` unset (the default, and in every test except `tests/test_prototype.py`),
every page renders exactly as on `main`. With it on, only these screens switch:

| Screen | Page | Prototype template | Original template |
|---|---|---|---|
| 3 | My tasks | `templates/proto/tasks.html` | `templates/portal/tasks.html` |
| 21 | Pilot Project Semiannual Progress Report (this form only) | `templates/proto/progress_form.html` | `templates/portal/form.html` |
| 53 | Period dashboard | `templates/proto/dashboard.html` | `templates/manage/dashboard.html` |
| 90 | Mentee Survey results (this form only) | `templates/proto/report.html` | `templates/manage/report.html` |

A "Design preview" switch at the bottom of those four pages flips between Current and Prototype
(`/ui-preview/before/` and `/ui-preview/after/`; 404 when the setting is off).

## What did not change

Models, migrations, survey questions and wording, form field names, validation, autosave, the
Save draft and Submit actions, assignment generation, exemptions, reopening, counts, confidentiality
checks, exports, permissions, and every other page.

## Files

- New: `apps/common/prototype.py`, `static/css/proto.css` (every rule starts with `body.proto`),
  `static/js/proto.js`, `static/fonts/Lora-Variable.ttf` (SIL Open Font License), `templates/proto/*`,
  `tests/test_prototype.py`.
- Small edits: one setting, one URL, `base.html` (prototype stylesheet and switch only when on),
  one line in each of the four views to choose the template, and display-only template filters
  (`status_count`, `minus`, `pct`, `days_until`, `sum_key`, `at`).
