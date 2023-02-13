from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from core.models import Account

SQL = """
select id,date_submitted,current_step from submission_article where date_submitted is not null and id not in (select article_id from core_workflowlog);
"""


class Command(BaseCommand):
    help = "generates a report of missing workflowlogs for published articles on stdout"

    def handle(self, *args, **options):

        with connection.cursor() as cursor:
            cursor.execute(SQL)
            missing_workflowlogs = cursor.fetchall()
            if len(missing_workflowlogs) > 0:
                for line in missing_workflowlogs:
                    print(line)
            cursor.close()
            exit(0)
