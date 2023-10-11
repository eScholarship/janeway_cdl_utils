from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from core.models import File, FileHistory

from .boolean_input import boolean_input

import os

class Command(BaseCommand):
    """Reports file objs and file history objs not related to a file on disk. Deletes if indicated."""
    help = "Reports file objs and file history objs not related to a file on disk. Deletes if indicated."

    def add_arguments(self, parser):
        parser.add_argument(
            '--delete-all',
            action='store_true',
            help="Delete all file objs that aren't associated with an article",
        )

    def find_files(self, path):
        journal_files = []
        for root, dirs, files in os.walk(path):
            path = root.split(os.sep)
            journal_files += files
        return journal_files

    def handle(self, *args, **options):
        delete = options["delete_all"]

        article_files = self.find_files(os.path.join(settings.BASE_DIR, 'files', 'articles'))
        journal_files = self.find_files(os.path.join(settings.BASE_DIR, 'files', 'journals'))
        press_files = self.find_files(os.path.join(settings.BASE_DIR, 'files', 'press'))
        repo_files = self.find_files(os.path.join(settings.BASE_DIR, 'files', 'repos'))

        all_files = article_files + journal_files + press_files + repo_files

        file_objs = File.objects.exclude(uuid_filename__in=all_files)
        if file_objs.exists():
            for f in file_objs:
                print(f'File {f.pk}\tArticle {f.article_id}\t{f.original_filename}\t{f.uuid_filename}')

            if delete:
                prompt = f'You are deleting {file_objs.count()} file objects for which no file was found on disk.'
                self.stdout.write(self.style.NOTICE(prompt))
                if boolean_input("Are you sure? (yes/no)"):
                    file_objs.delete()
            else:
                print(f"Found {file_objs.count()} file objects with no matching file on disk")
        else:
            print("All file objects have a file on disk")

        fhistories = FileHistory.objects.exclude(uuid_filename__in=all_files)
        if fhistories.exists():
            for f in fhistories:
                print(f'History {f.pk}\tFile {f.file_set.all()}\tArticle {f.article_id}\t{f.original_filename}\t{f.uuid_filename}')

            if delete:
                prompt = f'You are deleting {fhistories.count()} file histories for which no file was found on disk.'
                self.stdout.write(self.style.NOTICE(prompt))
                if boolean_input("Are you sure? (yes/no)"):
                    fhistories.delete()
            else:
                print(f"Found {fhistories.count()} file histories with no matching file on disk")
        else:
            print("All file histories have a file on disk")

