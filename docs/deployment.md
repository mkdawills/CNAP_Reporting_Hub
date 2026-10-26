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
