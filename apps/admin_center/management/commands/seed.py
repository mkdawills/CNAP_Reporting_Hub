"""
manage.py seed            -> reference data (roles, cores, resources, relationship
                             types, shared scales, completion pathways). Idempotent.
manage.py seed --fictional -> also the fictional sample center (Milestone 9).
"""

from django.core.management.base import BaseCommand

from apps.admin_center.reference_data import seed_reference_data


class Command(BaseCommand):
    help = "Load reference data (and, with --fictional, the sample center). Safe to run repeatedly."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fictional", action="store_true", help="Also load the fictional sample center."
        )

    def handle(self, *args, **options):
        seed_reference_data(self.stdout)
        if options["fictional"]:
            self.stdout.write(
                "Fictional sample data arrives in Milestone 9; reference data is loaded."
            )
        self.stdout.write(self.style.SUCCESS("Reference data is in place."))
