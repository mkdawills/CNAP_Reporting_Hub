from django.core.management.base import BaseCommand

from apps.outcomes import nudges, reminders


class Command(BaseCommand):
    help = (
        "Email the stale-record reminders and the monthly planned-proposal check-ins (run daily)."
    )

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
        nudged = nudges.send(dry_run=opts["dry_run"])
        verb = "Would check in with" if opts["dry_run"] else "Checked in with"
        for grant, person, to in nudged:
            self.stdout.write(f'{verb} {person} about "{grant.project_title[:60]}" ({to})')
        self.stdout.write(
            f"{len(nudged)} monthly check-in{'s' if len(nudged) != 1 else ''} {'due' if opts['dry_run'] else 'sent'}."
        )
