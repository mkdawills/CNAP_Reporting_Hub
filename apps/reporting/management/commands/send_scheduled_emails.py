"""manage.py send_scheduled_emails [--dry-run]: run once a day. Sends each open period's scheduled emails."""

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.common.enums import PeriodStatus
from apps.reporting.models import ReportingPeriod
from apps.reporting.services import emails


class Command(BaseCommand):
    help = "Send today's scheduled period emails (opening day, every 4 days to the due date, then daily)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="Say what would be sent; send nothing."
        )

    def handle(self, *args, dry_run, **kw):
        today = timezone.localdate()
        for p in ReportingPeriod.objects.filter(status=PeriodStatus.OPEN).order_by("display_order"):
            kind = emails.scheduled_kind(p, today)
            if not kind:
                self.stdout.write(f"{p.short_label}: nothing scheduled today.")
                continue
            if dry_run:
                n = sum(1 for r in emails.plan(p, kind) if not r["skip"])
                self.stdout.write(f"{p.short_label}: would send {n} {kind} email(s).")
                continue
            for k, n, skipped in emails.run_schedule(p, today):
                self.stdout.write(f"{p.short_label}: sent {n} {k}; {skipped} skipped.")
        from apps.reporting.services import roster_check

        if not dry_run:
            n = roster_check.run(today)
            if n:
                self.stdout.write(f"Roster check: sent {n}.")
        from apps.outcomes import cpcheck

        if not dry_run:
            n = cpcheck.run(today)
            if n:
                self.stdout.write(f"Current and Pending check: sent {n}.")
