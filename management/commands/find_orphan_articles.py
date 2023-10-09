from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from submission.models import Article
from core.models import File

from .boolean_input import *

import os

class Command(BaseCommand):
    """Reports articles that are not assigned to a journal, deletes them if specified"""
    help = "Reports articles that are not assigned to a journal, deletes them if specified"

    def add_arguments(self, parser):
        parser.add_argument(
            '--delete-all',
            action='store_true',
            help="Delete all articles that aren't associated with a journal",
        )

    def delete_article(self, article):
        file_dir = os.path.join(settings.BASE_DIR, 'files', 'articles', str(article.pk))
        aux_dir = os.path.join(settings.BASE_DIR, 'files', f'{article.pk} - {article.title}', str(article.pk))

        for f in File.objects.filter(article_id=article.pk):
            for h in f.history.all():
                path = os.path.join(file_dir, str(h.uuid_filename))
                if os.path.exists(path):
                    os.unlink(path)
                else:
                    path = os.path.join(aux_dir , str(h.uuid_filename))
                    if os.path.exists(path):
                        os.unlink(path)
                h.delete()
            # File objs delete their own file when deleted.
            f.delete()
            if os.path.exists(aux_dir):
                os.unlink(aux_dir)
        article.delete()

    def handle(self, *args, **options):
        delete = options["delete_all"]

        articles = Article.objects.filter(journal=None)
        if articles.count() == 0:
            print("No articles are not associated with a journal")
        else:
            print(f'Found {articles.count()} articles:')
            for a in articles:
                print(f'\t{a.pk}: {a}')

            if delete:
                prompt = f'You are deleting {articles.count()} articles that are not associated with journals.'
                self.stdout.write(self.style.NOTICE(prompt))

                if not boolean_input("Are you sure? (yes/no)"):
                    raise CommandError("delete articles aborted")

                for a in articles:
                    self.delete_article(a)
