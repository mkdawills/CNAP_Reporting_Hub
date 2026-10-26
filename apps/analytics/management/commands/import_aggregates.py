"""manage.py import_aggregates [FILE] : load prior-year item means (default: the Year 6-9 file)."""

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.analytics.historical import import_file


class Command(BaseCommand):
    help = "Import historical item means as finalized aggregate snapshots. Safe to run again."

    def add_arguments(self, parser):
        parser.add_argument(
            "file",
            nargs="?",
            default=str(settings.BASE_DIR / "fixtures" / "historical" / "aggregates_y6_y9.csv"),
        )

    def handle(self, *args, **options):
        n, periods = import_file(options["file"])
        self.stdout.write(
            self.style.SUCCESS(f"{n} item means across {periods} periods are in place.")
        )
