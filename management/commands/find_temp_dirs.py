from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from .boolean_input import boolean_input

import os, re, shutil

class Command(BaseCommand):
    """Find all directories in the files/ directory that match the name format 'PK - Title'. Delete if indicated."""
    help = "Find all directories in the files/ directory that match the name format 'PK - Title'. Delete if indicated."

    def add_arguments(self, parser):
        parser.add_argument(
            '--delete-all',
            action='store_true',
            help="Delete all directories matching the name format 'PK - Title'",
        )

    def handle(self, *args, **options):
        delete = options["delete_all"]

        dirs = []

        file_dir = os.path.join(settings.BASE_DIR, 'files')
        for d in os.listdir(file_dir):
            result = re.search(r'^(\d+) - .*', d)
            if result:
                print(d)
                dirs.append(d) 

        if delete:
            prompt = f'You are deleting {len(dirs)} directories that match the zip file staging directory name format.'
            self.stdout.write(self.style.NOTICE(prompt))
            if boolean_input("Are you sure? (yes/no)"):
                for d in dirs:
                    shutil.rmtree(os.path.join(file_dir, d))
        else:
            print(f"Found {len(dirs)} directories that match the zip file staging directory name format")
