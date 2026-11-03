"""manage.py send_speaker_surveys: run every 10 minutes. E-mails the NeuroSync Speaker Survey to each speaker whose
talk has just ended (MW 2026-11-03)."""

from django.core.management.base import BaseCommand

from apps.reporting.services import speakers


class Command(BaseCommand):
    help = "Send the NeuroSync Speaker Survey to speakers whose talks have ended."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="List who would get it; send nothing.")

    def handle(self, *args, dry_run, **kw):
        if dry_run:
            for t in speakers.due_talks():
                self.stdout.write(f"Would send: {t}")
            return
        n, problems = speakers.run_due()
        self.stdout.write(f"Sent {n} speaker survey(s).")
        for p in problems:
            self.stdout.write(f"Not sent: {p}")
