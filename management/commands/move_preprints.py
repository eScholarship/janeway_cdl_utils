from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from core.models import Account


class Command(BaseCommand):
    help = "move preprints from a proxy account to a new account"

    def add_arguments(self, parser):
        parser.add_argument(
            "active_user", help="`email` of new active account", type=str
        )
        parser.add_argument("proxy_user", help="`email` of old proxy account", type=str)

    def handle(self, *args, **options):
        active_user = Account.objects.get(email=options["active_user"])
        proxy_user = Account.objects.get(email=options["proxy_user"])

        if proxy_user == active_user:
            raise CommandError(
                "active_user and proxy_user have the same id, nothing to do"
            )

        if active_user.is_active is False:
            raise CommandError(
                "active_user {} must have an active account".format(
                    options["active_user"]
                )
            )

        if proxy_user.is_active is True:
            raise CommandError(
                "proxy_user {} must not have an active account".format(
                    options["proxy_user"]
                )
            )

        update_preprints = (
            "update janeway.repository_preprint set owner_id={} where owner_id={};".format(
                active_user.id, proxy_user.id
            )
        )
        delete_proxy = "delete from core_account where id={};".format(proxy_user.id)

        with connection.cursor() as cursor:
            cursor.execute(update_preprints)
            cursor.execute(delete_proxy)
            cursor.fetchall()
