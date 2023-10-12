from django.core.management.base import BaseCommand, CommandError

from journal.models import Journal
from core.models import File
import os
from django.conf import settings

from .boolean_input import *

class Command(BaseCommand):
    """Fully deletes a journal including all associated files and objects"""
    help = "Fully deletes a journal including all associated files and objects"

    def add_arguments(self, parser):
        parser.add_argument(
            "journal_code", help="`code` of the journal to to delete", type=str
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Print the output but don't delete",
        )
        parser.add_argument(
            '--no-prompt',
            action='store_true',
            help="Don't prompt the user (used for testing)",
        )

    def handle(self, *args, **options):
        journal_code = options.get("journal_code")
        delete = not options["dry_run"]
        do_prompt = not options["no_prompt"]

        j = Journal.objects.get(code=journal_code)


        if do_prompt:
            prompt = f'You are deleting {j.name} and all associated files.'
            self.stdout.write(self.style.NOTICE(prompt))

            if not boolean_input("Are you sure? (yes/no)"):
                raise CommandError("delete journal aborted")

        for a in j.article_set.all():
            print(f'Article {a}')
            aux_dir = os.path.join(settings.BASE_DIR, 'files', f'{a.pk} - {a.title}', str(a.pk))
            for f in File.objects.filter(article_id=a.pk):
                print(f'\tFile: {f}')
                for h in f.history.all():
                    print(f'\t\tFile history: {h}')
                    path = os.path.join(settings.BASE_DIR, 'files', 'articles', str(a.pk), str(h.uuid_filename))
                    if os.path.exists(path):
                        print(f'\t\t\tFound path to delete: {path}')
                        if delete:
                            os.unlink(path)
                    else:
                        path = os.path.join(aux_dir , str(h.uuid_filename))
                        if os.path.exists(path):
                            print(f'\t\t\tFound path to delete: {path}')
                            if delete:
                                os.unlink(path)
                        else:
                            print("\t\t\tNo file history found")
                    print(f'\t\tDelete file history object: {h.pk}')
                    if delete:
                        h.delete()
                print(f'\tDelete file object: {f.pk}')
                if delete:
                    f.delete()
            if os.path.exists(aux_dir):
                print(f'\tdelete aux dir: {aux_dir}')
                if delete:
                    os.unlink(aux_dir)
            else:
                print(f'No aux dir {aux_dir} found.')
            if delete:
                a.delete()
        if delete:
            print(f'Deleting journal {j.name}')
            j.delete()
