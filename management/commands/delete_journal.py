from django.core.management.base import BaseCommand, CommandError

from journal.models import Journal
from core.models import File
import os
from django.conf import settings

def boolean_input(question, default=None):
    result = input("%s " % question)
    if not result and default is not None:
        return default
    while len(result) < 1 or result[0].lower() not in "yn":
        result = input("Please answer yes or no: ")
    return result[0].lower() == "y"

class Command(BaseCommand):
    """Fully deletes a journal including all associated files and objects"""
    help = "Fully deletes a journal including all associated files and objects"

    def add_arguments(self, parser):
        parser.add_argument(
            "journal_code", help="`code` of the journal to add arks", type=str
        )

    def handle(self, *args, **options):
        journal_code = options.get("journal_code")

        j = Journal.objects.get(code=journal_code)

        prompt = f'You are deleting {j} and all associated files.'
        self.stdout.write(self.style.NOTICE(prompt))

        if not boolean_input("Are you sure? (yes/no)"):
            raise CommandError("delete journal aborted")

        for a in j.article_set.all():
            aux_dir = os.path.join(settings.BASE_DIR, 'files', f'{a.pk - {}}', str(a.pk))
            for f in File.objects.filter(article_id=a.pk):
                for h in f.history.all():
                    path = os.path.join(settings.BASE_DIR, 'files', 'articles', str(a.pk), str(h.uuid_filename))
                    if os.path.exists(path):
                        os.unlink(path)
                    else:
                        path = os.path.join(aux_dir , str(h.uuid_filename))
                        if os.path.exists(path):
                            os.unlink(path)
                f.delete()
            if os.path.exists(aux_dir):
                os.unlink(aux_dir)
        j.delete()
