FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir "Django==5.2.18" "psycopg[binary]==3.3.6" "django-environ==0.12.0" \
    "openpyxl==3.1.5" "gunicorn==23.0.0" "whitenoise==6.11.0" \
    "pytest==8.4.2" "pytest-django==4.11.1" "factory-boy==3.3.3" "ruff==0.14.2"

COPY . .
RUN mkdir -p /data/media

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
