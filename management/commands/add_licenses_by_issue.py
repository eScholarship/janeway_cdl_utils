from django.core.management.base import BaseCommand, CommandError

import csv, os

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

        if not Journal.objects.filter(code=journal_code).exists():
            raise CommandError(f'Journal does not exist {journal_code}')

        j = Journal.objects.get(code=journal_code)

        if not os.path.exists(import_file):
            raise CommandError(f'File {import_file} not found.')

        cc_licenses = 0
        issue_count = 0
        article_count = 0
        errors = 0
        with open(import_file, 'r') as csvfile:
            reader = csv.DictReader(csvfile, delimiter="\t")
            for i in reader:
                if i["rights"] != "NULL":
                    cc_licenses += 1
                    license, created = Licence.objects.get_or_create(journal=j, url=i["rights"].rstrip("/"))
                    i_set = Issue.objects.filter(journal=j, volume=i["volume"], issue=i["issue"]).exclude(articles=None)
                    if not i_set.exists():
                        self.stdout.write(self.style.ERROR(f'ERROR issue not found: {i["volume"]} {i["issue"]}'))
                        errors += 1
                    else:
                        issue_count += i_set.count()
                        for issue in i_set.all():
                            article_count += issue.articles.count()
                            for a in issue.articles.all():
                                a.license = license
                                a.save()

        if cc_licenses == 0:
            self.stdout.write(self.style.NOTICE(f"No CC licenses found for {journal_code}"))
        else:
            if issue_count > 0:
                self.stdout.write(self.style.SUCCESS(f'✅ CC licenses added to {article_count} articles in {issue_count} issues.'))
                self.stdout.write(self.style.NOTICE("Note: if duplicate issues were found licenses were added to both"))
            if errors > 0:
                self.stdout.write(self.style.ERROR(f"{errors} issues not found."))
