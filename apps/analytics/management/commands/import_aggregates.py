"""manage.py import_aggregates [FILE] : load prior-year item means (default: the Year 6-9 file)."""

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.analytics.historical import import_file, import_overall


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
        overall = settings.BASE_DIR / "fixtures" / "historical" / "overall_y6_y9.csv"
        if overall.exists():
            self.stdout.write(f"{import_overall(overall)} section overall means/SDs.")
        self.stdout.write(
            self.style.SUCCESS(f"{n} item means across {periods} periods are in place.")
        )
