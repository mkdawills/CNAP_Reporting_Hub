"""manage.py sync_metrics : refresh metric_definitions from the code registry."""

from django.core.management.base import BaseCommand

from apps.analytics.metrics import sync


class Command(BaseCommand):
    help = "Mirror apps/analytics/metrics.py into metric_definitions."

    def handle(self, *args, **options):
        sync()
        self.stdout.write(self.style.SUCCESS("Metric definitions are up to date."))
