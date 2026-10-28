# Deployment

One Linux VM, Docker Compose, nginx in front for TLS. No other infrastructure.

1. Install Docker and Docker Compose on the VM (K-State IT provisions and patches the VM).
2. `git clone` the repository; `cp .env.example .env`; set `SECRET_KEY`, `DEBUG=false`, `DJANGO_SETTINGS_MODULE=config.settings.prod`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, a real database password (also in `docker-compose.yml`), `MEDIA_ROOT=/data/media`.
3. `make up` — the web container applies migrations and collects static files on start.
4. `make seed`, `make superuser`.
5. nginx: proxy `https://<host>/` to `http://127.0.0.1:8000/` (the app listens only on 127.0.0.1), serve TLS with a K-State certificate. The application sets secure cookies and HSTS in `prod.py`. Required headers and logging:

   ```nginx
   location / {
       proxy_pass http://127.0.0.1:8000;
       proxy_set_header Host $host;
       proxy_set_header X-Forwarded-Proto $scheme;
       proxy_set_header X-Forwarded-For $remote_addr;   # replace, don't append: sign-in throttling relies on it
   }
   location /accounts/link/ {                          # sign-in links carry a token in the path
       access_log off;
       proxy_pass http://127.0.0.1:8000;
       proxy_set_header Host $host;
       proxy_set_header X-Forwarded-Proto $scheme;
       proxy_set_header X-Forwarded-For $remote_addr;
   }
   ```
6. Schedule `make backup` nightly (docs/backup-and-restore.md).

Upgrades: `git pull && docker compose build && make up && make test`.

Before real data: the decisions in Architecture Review section 5 (hosting, SSO, data classification, retention, security review) must be settled with K-State IT.

## Scheduled jobs

Run once a day (cron, systemd timer, or the host's scheduler), from the project directory with the production settings:

```
# 07:00 every day: e-mail people whose publications or grants haven't been reviewed in OUTCOME_STALE_DAYS days
0 7 * * *  python manage.py send_outcome_reminders
# 08:00 every day: scheduled period e-mails (opening day; every 4 days to the due date; daily after it)
0 8 * * *  python manage.py send_scheduled_emails
# 03:00 every day: remove expired sign-in sessions
0 3 * * *  python manage.py clearsessions
```

Settings in `.env`: `OUTCOME_STALE_DAYS` (default 120), `OUTCOME_REMINDER_EVERY_DAYS` (default 30), `SITE_URL` (links in the e-mail), `DEFAULT_FROM_EMAIL`, and the mail server as one URL, `EMAIL_URL` (e.g. `smtp+tls://user:password@relay:587`, K-State's SMTP relay). Production refuses to start without an SMTP `EMAIL_URL`, and the development settings refuse to run when `.env` says `DEBUG=false`. Use `--dry-run` to see who would be reminded.

PubMed look-ups ("Fill in from PubMed") call `https://eutils.ncbi.nlm.nih.gov`; the server needs outbound HTTPS to that host. Set `PUBMED_CONTACT_EMAIL` (NCBI asks for one) and `CNAP_GRANT_NUMBERS` (CNAP's COBRE award, `P20GM113109`, is the default) so the form can tell people whether PubMed lists CNAP in the paper's grant index.


Period e-mails ("your forms are open", reminders) go out on a schedule (above) while a period is open for answers, unless the evaluator pauses them on Reporting periods → E-mails, where she can also send one by hand. `python manage.py send_scheduled_emails --dry-run` says what today's run would send; `python manage.py send_period_emails "<period>" open|reminder|overdue --dry-run` lists who would get one.

Operator tasks: `docs/runbook.md`.
