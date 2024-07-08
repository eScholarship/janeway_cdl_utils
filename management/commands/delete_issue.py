from django.core.management.base import BaseCommand, CommandError
from django.contrib.contenttypes.models import ContentType
from django.conf import settings

from journal.models import Issue
from core.models import File
from utils.models import LogEntry

import os
from .boolean_input import *

class Command(BaseCommand):
    """Fully delete an issue including articles and associated objects"""
    help = "Fully delete an issue including articles and associated objects"

    def add_arguments(self, parser):
        parser.add_argument(
            "issue_id", help="`id` of the issue to to delete", type=int
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Print the output but don't delete",
        )

    def handle(self, *args, **options):
        issue_id = options.get("issue_id")
        delete = not options["dry_run"]

        issue = Issue.objects.get(pk=issue_id)

        prompt = f'You are deleting {issue} and all associated files.'
        self.stdout.write(self.style.NOTICE(prompt))

        if not boolean_input("Are you sure? (yes/no)"):
            raise CommandError("delete issue aborted")

        for a in issue.article_set.all():
            print(f'Article {a}')
            for f in File.objects.filter(article_id=a.pk):
                print(f'\tFile: {f}')
                for h in f.history.all():
                    print(f'\t\tFile history: {h}')
                    path = os.path.join(settings.BASE_DIR, 'files', 'articles', str(a.pk), str(h.uuid_filename))
                    if os.path.exists(path):
                        print(f'\t\t\tFound path to delete: {path}')
                        if delete:
                            os.unlink(path)
                    print(f'\t\tDelete file history object: {h.pk}')
                    if delete:
                        h.delete()
                print(f'\tDelete file object: {f.pk}')
                if delete:
                    f.delete()
            content_type = ContentType.objects.get_for_model(a)
            log_entries = LogEntry.objects.filter(content_type=content_type, object_id=a.pk)
            print(f"\tDelete {log_entries.count()} log entries")
            print(f"\tDelete {a}")
            if delete:
                log_entries.delete()
                a.delete()
        if delete:
            print(f'Deleting issue {issue}')
            issue.delete()
