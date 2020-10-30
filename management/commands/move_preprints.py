from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from core.models import Account

# https://stackoverflow.com/a/39257511/1763984
def boolean_input(question, default=None):
    result = input("%s " % question)
    if not result and default is not None:
        return default
    while len(result) < 1 or result[0].lower() not in "yn":
        result = input("Please answer yes or no: ")
    return result[0].lower() == "y"


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

        # sanity checks
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

        # echo what will happen, and ask the operator to okay

        prompt = """active_user
	{} ({})
will become the owner of preprints from the proxy user
	{} ({})
Are you sure? (yes/no)
""".format(
            active_user.full_name(),
            active_user.email,
            proxy_user.full_name(),
            proxy_user.email,
        )
        if not boolean_input(prompt):
            raise CommandError("preprint move aborted")

        update_preprints = "update janeway.repository_preprint set owner_id={} where owner_id={};".format(
            active_user.id, proxy_user.id
        )
        delete_proxy = "delete from core_account where id={};".format(proxy_user.id)

        with connection.cursor() as cursor:
            cursor.execute(update_preprints)
            cursor.execute(delete_proxy)
            cursor.fetchall()
        self.stdout.write(self.style.SUCCESS("✅ process complete"))
