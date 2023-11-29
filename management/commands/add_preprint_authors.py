from django.core.management.base import BaseCommand, CommandError

import csv, os

from repository.models import Preprint, PreprintAuthor
from core.models import Account

class Command(BaseCommand):
    """Adds a list of authors to preprints given a csv"""
    help = "Adds a list of authors to preprints given a csv"

    def add_arguments(self, parser):
        parser.add_argument(
            "preprint_id", help="ID of the preprint to add authors to", type=int
        )
        parser.add_argument(
            "import_file", help="path to an import file containing the authors to add", type=str
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help="Remove existing authors from a preprint before importing",
        )


    def handle(self, *args, **options):
        preprint_id = int(options.get("preprint_id"))
        import_file = options.get("import_file")
        overwrite = options["overwrite"]
        rows = []

        if not Preprint.objects.filter(pk=preprint_id).exists():
            raise CommandError(f'Preprint {preprint_id} does not exist')

        if not os.path.exists(import_file):
            raise CommandError(f'File {import_file} not found.')

        with open(import_file, 'r') as csvfile:
            reader = csv.DictReader(csvfile, delimiter=",")
            for r in reader:
                if "Preprint ID" in r and not int(r["Preprint ID"]) == preprint_id:
                    raise CommandError(f'Preprint ID {r["Preprint ID"]} does not match {preprint_id}')
                if not overwrite and PreprintAuthor.objects.filter(preprint__pk=preprint_id, account__email=r["Email"]).exists():
                    raise CommandError(f'Account with email {r["Email"]} is already an author on Preprint {preprint_id}. Did you mean to use *overwrite*?')
                if not r["Email"] or len(r["Email"]) == 0:
                    raise CommandError(f'No email address specified for {r["First Name"]} {r["Last Name"]}')
                if not r["Author Order"] or len(r["Author Order"]) == 0:
                    raise CommandError(f'No author order specified for {r["Email"]}')
                rows.append(r)
 
        preprint = Preprint.objects.get(pk=preprint_id)

        if overwrite:
            for a in preprint.preprintauthor_set.all():
                a.delete()

        if preprint.preprintauthor_set.count() > 0:
            order_start = max(preprint.preprintauthor_set.all().values_list('order', flat=True))
        else:
            order_start = 0

        for r in rows:
            defaults = {'username': r["Email"], 'first_name': r["First Name"], 'middle_name': r["Middle Name"], 'last_name': r["Last Name"], 'institution': r["Affiliation"]}
            account, created = Account.objects.get_or_create(email=r["Email"], defaults=defaults)
            author, created = PreprintAuthor.objects.get_or_create(preprint=preprint,
                                                                   account=account,
                                                                   defaults= {'order': int(r["Author Order"]) + order_start,
                                                                              'affiliation': r["Affiliation"]})
            if created:
                author.save()

        if overwrite:
            self.stdout.write(self.style.SUCCESS(f"✅ Preprint {preprint_id} author list successfully overwritten."))
        else:
            self.stdout.write(self.style.SUCCESS(f"✅ Preprint {preprint_id} author list successfully appended."))
