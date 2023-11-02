from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from submission.models import Article
from journal.models import Journal

class Command(BaseCommand):
    """Reports the articles that don't have correspondence authors from a given journal"""
    help = "Reports the articles that don't have correspondence authors from a given journal"

    def add_arguments(self, parser):
        parser.add_argument(
            "journal_code", help="`code` of the journal to report on", type=str
        )

    def handle(self, *args, **options):
        # janeway journal codes are limited to 24 chars
        # truncate it if the user doesn't
        code = options.get("journal_code")[:24]

        if not Journal.objects.filter(code=code).exists():
            raise CommandError(f"No journal code = {code} found")

        articles = Article.objects.filter(journal__code=code, correspondence_author=None)
        if articles.count() == 0:
            print(f"There are no articles in {code} without a correspondence author")
        else:
            for a in articles:
                print(f'{a.stage}\t{a.pk}\t{a.title}\t{a.url}')
