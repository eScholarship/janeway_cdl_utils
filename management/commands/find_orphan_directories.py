from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from .boolean_input import boolean_input

from submission.models import Article

import os, shutil

class Command(BaseCommand):
    """Find directories that reference an article that no longer exists"""
    help = "Find directories that reference an article that no longer exists"

    def add_arguments(self, parser):
        parser.add_argument(
            '--delete-all',
            action='store_true',
            help="Delete all directories matching the name format 'PK - Title'",
        )

    def handle(self, *args, **options):
        delete = options["delete_all"]

        unlinked_dirs = []
        linked_dirs = []
        empty_dirs = []

        file_dir = os.path.join(settings.BASE_DIR, 'files', 'articles')
        for d in os.listdir(file_dir):
            pk = int(d)
            if not Article.objects.filter(pk=pk).exists():
                if len(os.listdir(os.path.join(file_dir, d))) == 0:
                    empty_dirs.append(d)
                else:
                    unlinked_dirs.append(d)
            else:
                linked_dirs.append(d)
 
        if delete:
            print(f"Found {len(linked_dirs)} directories that are linked to existing articles.")
            if len(empty_dirs):
                prompt = f'You are deleting {len(empty_dirs)} empty directories that reference an article that no longer exists.'
                self.stdout.write(self.style.NOTICE(prompt))
                if boolean_input("Are you sure? (yes/no)"):
                    for d in empty_dirs:
                        shutil.rmtree(os.path.join(file_dir, d))
            else:
                print("There are no empty directories associated with deleted articles.")
            
            if len(unlinked_dirs):
                prompt = f'You are deleting {len(unlinked_dirs)} directories that contain files and reference an article that no longer exists.'
                self.stdout.write(self.style.NOTICE(prompt))
                if boolean_input("Are you sure? (yes/no)"):
                    for d in unlinked_dirs:
                        shutil.rmtree(os.path.join(file_dir, d))
            else:
                print("There are no directories that contain files and are associated with deleted articles.")
        else:
            print(f"Found {len(linked_dirs)} directories that are linked to existing articles.")
            print(f"Found {len(empty_dirs)} empty directories that reference an article that no longer exists.")
            print(f"Found {len(unlinked_dirs)} directories that contain files and reference an article that no longer exists.")
