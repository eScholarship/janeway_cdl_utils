from django.core.management.base import BaseCommand

from core.models import Account
from submission.models import Article, STAGE_ARCHIVED
from utils.models import LogEntry


class Command(BaseCommand):
    """Archives all articles given a list of ids from a file."""
    help = "Archives all articles given a list of ids from a file."

    def add_arguments(self, parser):
        parser.add_argument(
            "filepath", help="path to file with ids", type=str
        )
        parser.add_argument(
            "user_id", help="user to set as `actor`", type=str
        )

    def handle(self, *args, **options):
        filepath = options.get("filepath")
        user_id = options.get("user_id")

        user = Account.objects.get(id=user_id)

        with open(filepath, 'r') as f:
            for line in f:
                article = Article.objects.get(id=line.strip())
                LogEntry.add_entry(
                        types='Workflow',
                        description='Article has been archived.',
                        level='Info',
                        actor=user,
                        target=article,
                    )
                article.stage = STAGE_ARCHIVED
                article.save()
