# Deployment

One Linux VM, Docker Compose, nginx in front for TLS. No other infrastructure.

1. Install Docker and Docker Compose on the VM (K-State IT provisions and patches the VM).
2. `git clone` the repository; `cp .env.example .env`; set `SECRET_KEY`, `DEBUG=false`, `DJANGO_SETTINGS_MODULE=config.settings.prod`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, a real database password (also in `docker-compose.yml`), `MEDIA_ROOT=/data/media`.
3. `make up` — the web container applies migrations and collects static files on start.
4. `make seed`, `make superuser`.
5. nginx: proxy `https://<host>/` to `http://127.0.0.1:8000/`, forward `X-Forwarded-Proto`, serve TLS with a K-State certificate. The application sets secure cookies and HSTS in `prod.py`.
6. Schedule `make backup` nightly (docs/backup-and-restore.md).

Upgrades: `git pull && docker compose build && make up && make test`.

Before real data: the decisions in Architecture Review section 5 (hosting, SSO, data classification, retention, security review) must be settled with K-State IT.

## Scheduled jobs

Run once a day (cron, systemd timer, or the host's scheduler), from the project directory with the production settings:

```
# 07:00 every day: e-mail people whose publications or grants haven't been reviewed in OUTCOME_STALE_DAYS days
0 7 * * *  python manage.py send_outcome_reminders
# 03:00 every day: remove expired sign-in sessions
0 3 * * *  python manage.py clearsessions
```

Settings in `.env`: `OUTCOME_STALE_DAYS` (default 120), `OUTCOME_REMINDER_EVERY_DAYS` (default 30), `SITE_URL` (links in the e-mail), `DEFAULT_FROM_EMAIL`, and the mail server (`EMAIL_HOST` and friends, K-State's SMTP relay). Use `--dry-run` to see who would be reminded.

PubMed look-ups ("Fill in from PubMed") call `https://eutils.ncbi.nlm.nih.gov`; the server needs outbound HTTPS to that host. Set `PUBMED_CONTACT_EMAIL` (NCBI asks for one) and `CNAP_GRANT_NUMBERS` (CNAP's COBRE award, `P20GM113109`, is the default) so the form can tell people whether PubMed lists CNAP in the paper's grant index.


Period e-mails ("your forms are open", reminders) are sent by the evaluator from Reporting periods → E-mails, not on a schedule. `python manage.py send_period_emails "<period>" open|reminder --dry-run` lists who would get one.

Operator tasks: `docs/runbook.md`.
