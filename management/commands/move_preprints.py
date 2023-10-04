from django.core.management.base import BaseCommand, CommandError

from core.models import Account
from repository.models import PreprintAuthor, Preprint
from utils.models import LogEntry

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
        parser.add_argument(
            '--no-prompt',
            action='store_true',
            help="Don't prompt the user (used for testing)",
        )

    def handle(self, *args, **options):
        do_prompt = not options["no_prompt"]
        if not Account.objects.filter(email=options["active_user"]).exists():
            raise CommandError(
                "active_user does not exist"
            )
        if not Account.objects.filter(email=options["proxy_user"]).exists():
            raise CommandError(
                "proxy_user does not exist"
            )

        active_user = Account.objects.get(email=options["active_user"])
        proxy_user = Account.objects.get(email=options["proxy_user"])

        # sanity checks
        if proxy_user == active_user:
            raise CommandError(
                "active_user and proxy_user have the same id, nothing to do"
            )

        # echo what will happen, and ask the operator to okay
        prompt = """user
	{} ({}) **{} USER**
will become the owner of preprints from the proxy user
	{} ({}) **{} USER**
""".format(
            active_user.full_name(),
            active_user.email,
            "ACTIVE" if active_user.is_active else "INACTIVE",
            proxy_user.full_name(),
            proxy_user.email,
            "ACTIVE" if proxy_user.is_active else "INACTIVE",
        )
        self.stdout.write(self.style.NOTICE(prompt))

        if proxy_user.is_active is True:
            self.stdout.write(self.style.NOTICE("{} ({}) is active and will be deleted\n".format(proxy_user.full_name(),
                                                                                                 proxy_user.email)))
        if do_prompt and not boolean_input("Are you sure? (yes/no)"):
            raise CommandError("preprint move aborted")

        for pa in PreprintAuthor.objects.filter(account=proxy_user):
            if PreprintAuthor.objects.filter(preprint=pa.preprint, account=active_user).exists():
                pa.delete()
            else:
                pa.account = active_user
                pa.save()

        LogEntry.objects.filter(actor=proxy_user).update(actor=active_user)

        Preprint.objects.filter(owner=proxy_user).update(owner=active_user)

        proxy_user.delete()

        # done!
        self.stdout.write(self.style.SUCCESS("✅ process complete"))
