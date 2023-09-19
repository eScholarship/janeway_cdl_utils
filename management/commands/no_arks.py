from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from submission.models import Article
from plugins.eschol.models import EscholArticle
from journal.models import Journal


class Command(BaseCommand):
    """Reports published articles that don't have an ark from a given journal"""
    help = "Reports published articles that don't have an ark from a given journal"

    def add_arguments(self, parser):
        parser.add_argument(
            "journal_code", help="`code` of the journal to report on", type=str
        )

    def handle(self, *args, **options):
        code = options.get("journal_code")

        if not Journal.objects.filter(code=code).exists():
            raise CommandError(f"No journal code = {code} found")

        ids = EscholArticle.objects.filter(article__journal__code=code).values_list('article__pk', flat=True)
        articles = Article.objects.filter(journal__code="uccllt_l2", stage="Published").exclude(pk__in=ids)
        if articles.count() == 0:
            print(f"There are no articles in {code} without an escholarship ark assigned")
        else:
            for a in articles:
                print(f'{a.stage}\t{a.pk}\t{a.url}')
