from django.core.management.base import BaseCommand, CommandError

import csv

from repository.models import Preprint, PreprintAuthor
from core.models import Account

class Command(BaseCommand):
    """Adds a list of authors to preprints given a csv"""
    help = "Adds a list of authors to preprints given a csv"

    def add_arguments(self, parser):
        parser.add_argument(
            "import_file", help="path to an import file containing the authors to add", type=str
        )
        parser.add_argument(
            '--overwrite',
            action='store_true',
            help="Remove existing authors from a preprint before importing",
        )


    def handle(self, *args, **options):
        import_file = options.get("import_file")
        overwrite = options["overwrite"]
        rows = []
        preprints = []

        with open(import_file, 'r') as csvfile:
            reader = csv.DictReader(csvfile, delimiter=",")
            for r in reader:
                pk = r["Preprint ID"]
                if not Preprint.objects.filter(pk=pk).exists():
                    raise CommandError(f'Preprint {pk} does not exist')
                if not overwrite and PreprintAuthor.objects.filter(preprint__pk=pk, account__email=r["Email"]).exists():
                    raise CommandError(f'Account with email {r["Email"]} is already an author on Preprint {pk}. Did you mean to use *overwrite*?')
                if not r["Email"] or len(r["Email"]) == 0:
                    raise CommandError(f'No email address specified for {r["First Name"]} {r["Last Name"]}')
                if not r["Author Order"] or len(r["Author Order"]) == 0:
                    raise CommandError(f'No author order specified for {r["Email"]}')
                rows.append(r)
                if overwrite and not pk in preprints:
                    preprints.append(pk)
 
        if overwrite:
            for p in preprints:
                preprint = Preprint.objects.get(pk=p)
                for a in preprint.preprintauthor_set.all():
                    a.delete()
        
        for r in rows:
            preprint = Preprint.objects.get(pk=r["Preprint ID"])
            defaults = {'username': r["Email"], 'first_name': r["First Name"], 'middle_name': r["Middle Name"], 'last_name': r["Last Name"], 'institution': r["Affiliation"]}
            account, created = Account.objects.get_or_create(email=r["Email"], defaults=defaults)
            author, created = PreprintAuthor.objects.get_or_create(preprint=preprint,
                                                                   account=account,
                                                                   defaults= {'order': r["Author Order"],
                                                                              'affiliation': r["Affiliation"]})
            if created:
                author.save()
