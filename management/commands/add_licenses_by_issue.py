from django.core.management.base import BaseCommand

import csv

# You can create the expected input file with the following query to the jschol DB
# SELECT volume, issue, attrs->>'$.rights' as rights FROM issues WHERE unit_id = '';

from journal.models import Journal, Issue
from submission.models import Licence

class Command(BaseCommand):
    """Adds cc license information to a given journal from a jschol export"""
    help = "Adds cc license information to a given journal from a jschol export"

    def add_arguments(self, parser):
        parser.add_argument(
            "journal_code", help="`code` of the journal to add arks", type=str
        )
        parser.add_argument(
            "import_file", help="path to an export file containing the ojs ids and arks", type=str
        )

    def handle(self, *args, **options):
        # janeway journal codes are limited to 24 chars
        # truncate it if the user doesn't
        journal_code = options.get("journal_code")[:24]
        import_file = options.get("import_file")

        j = Journal.objects.get(code=journal_code)

        with open(import_file, 'r') as csvfile:
            reader = csv.DictReader(csvfile, delimiter="\t")
            for i in reader:
                license, created = Licence.objects.get_or_create(journal=j, url=i["rights"].rstrip("/"))
                if created:
                    print(f'Added license: {j} {i["rights"]}')
                else:
                    print(f'Found license: {j} {i["rights"]}')
                
                i_set = Issue.objects.filter(journal=j, volume=i["volume"], issue=i["issue"]).exclude(articles=None)
                if not i_set.exists():
                    print(f'ERROR issue not found: {i["volume"]} {i["issue"]}')
                else:
                    if i_set.count() > 1:
                        print(f'Found multiple issues ({i_set.count()}): {i["volume"]} {i["issue"]}')
                    else:
                        print(f'Found issue: {i["volume"]} {i["issue"]}')

                    for issue in i_set.all():
                        for a in issue.articles.all():
                            a.license = license
                            a.save()
