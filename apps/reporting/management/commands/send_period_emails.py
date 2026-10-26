"""manage.py send_period_emails <period short label> open|reminder [--dry-run]: e-mail people their forms."""

from django.core.management.base import BaseCommand, CommandError

from apps.reporting.models import ReportingPeriod
from apps.reporting.services import emails


class Command(BaseCommand):
    help = "E-mail people their forms for a reporting period (open or reminder)."

    def add_arguments(self, parser):
        parser.add_argument("period", help="Short label, e.g. 'Y10 Fall'")
        parser.add_argument("kind", choices=["open", "reminder"])
        parser.add_argument(
            "--dry-run", action="store_true", help="List who would get an e-mail; send nothing."
        )

    def handle(self, *args, period, kind, dry_run, **kw):
        try:
            p = ReportingPeriod.objects.get(short_label=period)
        except ReportingPeriod.DoesNotExist as exc:
            raise CommandError(f"No period '{period}'.") from exc
        if dry_run:
            for r in emails.plan(p, kind):
                state = r["skip"] or ("link" if r["with_link"] else "K-State sign-in")
                self.stdout.write(
                    f"{r['person']} <{r['email'] or '-'}>: {len(r['forms'])} forms · {state}"
                )
            return
        try:
            n, skipped = emails.send(p, kind)
        except emails.EmailError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"Sent {n}; {skipped} skipped.")
