"""
manage.py seed            -> reference data (roles, cores, resources, relationship
                             types, shared scales, completion pathways) and the CNAP
                             instruments from fixtures/forms. Idempotent.
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
        from apps.forms_engine.loader import load_all

        load_all(stdout=self.stdout)
        from apps.outcomes import funding

        funding.load_questions(self.stdout)  # MW's seven questions (2026-11-10)
        funding.load_catalog(self.stdout)  # the public opportunity catalog; no people, no matches
        funding.load_updates(self.stdout)  # public K-State and NIH news, opportunities, and events
        if options["fictional"]:
            from apps.admin_center.demo import seed_demo

            seed_demo(self.stdout)
        self.stdout.write(self.style.SUCCESS("Reference data is in place."))
