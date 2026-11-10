"""
manage.py seed_funding -> the funding catalog, MW's seven questions, and (with --fictional) the fictional
funding samples, for a copy that was seeded before the funding work arrived (MW 2026-11-10). Safe to run
repeatedly: nothing is added twice.
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Load the funding catalog and questions (and, with --fictional, the fictional funding samples)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fictional", action="store_true", help="Also load the fictional funding samples."
        )

    def handle(self, *args, **options):
        from apps.outcomes import funding

        funding.load_questions(self.stdout)
        funding.load_catalog(self.stdout)
        funding.load_updates(self.stdout)
        if options["fictional"]:
            from apps.accounts.models import User
            from apps.admin_center.demo import PEOPLE, _seed_funding

            people = {}
            for username, *_ in PEOPLE:
                u = User.objects.filter(username=username).select_related("person").first()
                if u and u.person:
                    people[username] = u.person
            _seed_funding(people, {"mwills": User.objects.filter(username="mwills").first()})
        self.stdout.write(self.style.SUCCESS("Funding data is in place."))
