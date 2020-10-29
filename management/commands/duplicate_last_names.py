from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from core.models import Account

SQL = """
SELECT last_name, first_name, middle_name, email, id
FROM janeway.core_account 
WHERE last_name in (
   SELECT last_name
   FROM janeway.core_account
   WHERE is_active=1
   GROUP BY last_name HAVING COUNT(*) > 1 
)
ORDER BY last_name;
"""


class Command(BaseCommand):
    help = "product report of duplicate last names"

    def handle(self, *args, **options):

        with connection.cursor() as cursor:
            cursor.execute(SQL)
            columns = [col[0] for col in cursor.description]
            print(','.join(columns))
            for line in cursor.fetchall():
                print(','.join(map(str,line)))
