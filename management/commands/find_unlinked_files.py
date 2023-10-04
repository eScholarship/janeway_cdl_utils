from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from submission.models import Article
from core.models import File, FileHistory

import os, re

from .boolean_input import *

class Command(BaseCommand):
    """Searches journal file directories and looks for files that are not referenced in the database"""
    help = "Searches journal file directories and looks for files that are not referenced in the database"

    def search_dir(self, d, article_id, delete):
        count = 0
        article_exists = Article.objects.filter(pk=article_id).exists()
        missing_files = []
        for fname in os.listdir(d):
            files = File.objects.filter(uuid_filename=fname)
            fhistories = FileHistory.objects.filter(uuid_filename=fname)
            if not files.exists() and not fhistories.exists():
                missing_files.append(fname)
                count += 1
        if count > 0:
            if article_exists:
                print(f"Article {article_id} exists")
            else:
                print(f"Article {article_id} does not exist")
            for fname in missing_files:
                print(f"\t{d}/{fname}")
            if delete:
                prompt = f'You are deleting {count} files from {d} that were not found in the db.'
                self.stdout.write(self.style.NOTICE(prompt))

                if boolean_input("Are you sure? (yes/no)"):
                    for fname in missing_files:
                        os.remove(os.path.join(d, fname))
        return count

    def add_arguments(self, parser):
        parser.add_argument(
            '--delete',
            action='store_true',
            help="Delete all articles that aren't associated with a journal",
        )

    def handle(self, *args, **options):
        delete = options["delete"]

        count = 0
        # search article files directory
        af_dir = os.path.join(settings.BASE_DIR, 'files', 'articles')
        for d in os.listdir(af_dir):
            file_dir = os.path.join(af_dir, d)
            count += self.search_dir(file_dir, int(d), delete)

        # search 'auxillary' directories (I don't know where these come from and they might all be cruft)
        file_dir = os.path.join(settings.BASE_DIR, 'files')
        for d in os.listdir(file_dir):
            result = re.search(r'^(\d+) - .*', d)
            if result:
                i = int(result.groups(0)[0])
                dname = os.path.join(file_dir, d, str(i))
                if os.path.isdir(dname):
                    count += self.search_dir(dname, i, delete)
                else:
                    print(f"Directory not found: {dname}")

        print(f"Found {count} files not referenced in the database")
