# Operator runbook

For whoever runs the CNAP Reporting Hub day to day (the evaluator) and whoever looks after the server
(K-State IT or a designated technician). Setup is in `docs/deployment.md`, backups in
`docs/backup-and-restore.md`, single sign-on in `docs/sso.md`.

## Each reporting session (Fall in January, Spring in May/June)

All of these are on **Reporting periods** in the administrator screens.

1. **Add the period** ("Add a period"): name, dates it covers, opens, due and closes. New periods start as a draft.
2. **Review before launch**: check who gets which forms and why. Fix roles on **People** first; the review
   updates as you go. Nothing is sent while the period is a draft.
3. **Open for preview** (optional): people can sign in and read their forms, but can't answer yet.
4. **Open**: answers are accepted from the opening date.
5. **E-mail people their forms**: Reporting periods → *E-mails* → "Forms are open". The page lists exactly
   who gets the e-mail, who doesn't and why (no e-mail on file, nothing to do). Send once.
6. **Watch progress** on the Period dashboard. Exempt anyone who shouldn't fill a form in (with a reason).
7. **Reminders**: E-mails → "Reminder" lists only people with forms left, and only what's left. Nobody gets
   more than one reminder in 3 days.
8. **Close** after the due date. Reopen if needed (the reason is recorded).
9. **Generate results** → review them (Results) → **Mark reviewed** → **Finalize**. Finalized results are what
   respondents see on Center results (surveys only, groups of 5 or more). A later correction creates a new,
   audited version.
10. **Publications and grants**: entry pauses for 7 days after a period closes so the period's numbers can be
    finished, then reopens for the rest of the year.

## The yearly NIH progress report (RPPR, due about April 1)

Publications and grants → **RPPR** tab, budget year June 1 – May 31.
1. If this is the first year on the site, open the **previous** year first and mark its lists as reported
   (otherwise items that already went in last year's RPPR show up again).
2. Check C.1, Tables 1A/1B, Table 2 (Core Usage Reports) and D.1 (eRA Commons IDs, calendar months, career
   levels). Fix records from the links; the "left out" and "not counted" lists say why each item is excluded.
3. Download the CSVs for the RPPR.
4. **Mark these as reported** once the RPPR is submitted, so nothing is reported twice. Items dated after the
   RPPR goes in (April 1 – May 31) are carried into next year's lists automatically.
5. The **Site visit** tab has the counts in the layout of the site-visit workbooks.

## Routine

| When | What | How |
| --- | --- | --- |
| Daily 07:00 | Reminders for papers and proposals not reviewed in 120 days | `python manage.py send_outcome_reminders` (cron) |
| Daily 08:00 | Period e-mails on schedule: opening day, every 4 days to the due date, daily after it until the period closes | `python manage.py send_scheduled_emails` (cron) |
| Daily 03:00 | Remove expired sessions | `python manage.py clearsessions` (cron) |
| Nightly | Database backup, copied off the server | `make backup` (cron; see backup-and-restore.md) |
| Each period | Restore a backup to a scratch machine and open it | backup-and-restore.md, record the date |
| Monthly | Data checks page: fix or dismiss each item | Administrator screens → Data checks |
| Monthly | Operating system and container updates | K-State IT; then `make test` |

## People and access

- **Someone new**: People → Add a person (e-mail is their sign-in identity for emailed links) → add their
  CNAP relationships. Forms follow from relationships.
- **Someone leaves**: end their relationships (dates are kept), and take them off the roster. To stop them
  signing in at all, use "Turn off sign-in" on their person page (records stay; it can be turned back on).
- **"I didn't get my link"**: they can request one any time at `/accounts/link/` with the address the Center
  has for them. Check that address on their person page. Links work once and last 7 days; codes for
  confidential forms last 15 minutes.
- **Locked out after wrong passwords**: sign-in pauses for 15 minutes after 10 failures; they can use an
  emailed link meanwhile.
- **Administrators** (the evaluator, Center Director, Associate Director) never sign in by emailed link; they
  use K-State single sign-on with two-factor once it's switched on.

## If something goes wrong

- **E-mails aren't arriving**: check `EMAIL_URL` and the relay with K-State IT; the E-mails page shows what was
  sent and when (each send is in the audit log).
- **A page errors**: the server log has the traceback (`docker compose logs web`). Nothing is lost: drafts save
  as people go.
- **Suspected account misuse**: "Turn off sign-in" on the person page (open sessions end on their next page), check the
  audit log for that person, and tell K-State IT security.
- **Restore from backup**: backup-and-restore.md. Restoring replaces everything entered since that backup.
