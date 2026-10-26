# Daily commands. Run `make help` to list them.
.DEFAULT_GOAL := help
COMPOSE ?= docker compose

help:           ## Show this list
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-14s %s\n", $$1, $$2}'

up:             ## Start the database and the web application
	$(COMPOSE) up -d

down:           ## Stop everything (data stays in the volumes)
	$(COMPOSE) down

migrate:        ## Apply database migrations
	$(COMPOSE) exec web python manage.py migrate

seed:           ## Load roles, relationship types, scales and fictional sample data
	$(COMPOSE) exec web python manage.py seed

superuser:      ## Create the first administrator account
	$(COMPOSE) exec web python manage.py createsuperuser

test:           ## Run the test suite against PostgreSQL
	$(COMPOSE) exec web pytest

lint:           ## Check code style
	$(COMPOSE) exec web ruff check .

backup:         ## Dump the database to backups/<timestamp>.sql.gz
	mkdir -p backups && $(COMPOSE) exec -T db pg_dump -U cnap cnap | gzip > backups/$$(date +%Y%m%d-%H%M%S).sql.gz

restore:        ## Restore from a dump: make restore FILE=backups/x.sql.gz
	gunzip -c $(FILE) | $(COMPOSE) exec -T db psql -U cnap cnap

logs:           ## Follow application logs
	$(COMPOSE) logs -f web
