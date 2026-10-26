"""manage.py load_forms [--draft] : load fixtures/forms/*.json into versioned forms. Idempotent."""

from django.core.management.base import BaseCommand

from apps.forms_engine.loader import load_all


class Command(BaseCommand):
    help = "Load the CNAP instruments from fixtures/forms. Changed files become new versions."

    def add_arguments(self, parser):
        parser.add_argument(
            "--draft",
            action="store_true",
            help="Create changed versions as drafts; activate them later from the Forms screen.",
        )

    def handle(self, *args, **options):
        results = load_all(draft=options["draft"], stdout=self.stdout)
        changed = sum(1 for *_, s in results if s != "unchanged")
        self.stdout.write(self.style.SUCCESS(f"{len(results)} forms checked, {changed} changed."))
