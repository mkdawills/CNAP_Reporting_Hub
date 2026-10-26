from django.core.management.base import BaseCommand

from apps.outcomes import reminders


class Command(BaseCommand):
    help = "E-mail people whose publications or grants haven't been reviewed for OUTCOME_STALE_DAYS days (run daily)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true", help="List who would get a reminder; send nothing."
        )

    def handle(self, *args, **opts):
        sent = reminders.send(dry_run=opts["dry_run"])
        verb = "Would remind" if opts["dry_run"] else "Reminded"
        for person, n, to in sent:
            self.stdout.write(f"{verb} {person} about {n} record{'s' if n != 1 else ''} ({to})")
        self.stdout.write(
            f"{len(sent)} reminder{'s' if len(sent) != 1 else ''} {'due' if opts['dry_run'] else 'sent'}."
        )
