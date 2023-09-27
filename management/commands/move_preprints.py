from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.forms.models import model_to_dict

from core.models import Account
from repository.models import Author, PreprintAuthor
from utils.models import LogEntry

# https://stackoverflow.com/a/39257511/1763984
def boolean_input(question, default=None):
    result = input("%s " % question)
    if not result and default is not None:
        return default
    while len(result) < 1 or result[0].lower() not in "yn":
        result = input("Please answer yes or no: ")
    return result[0].lower() == "y"


def merge_author_metadata(active_author_dict, proxy_author_dict):
    """ merge metadata, taking from the active author metadata first, then filling in from the proxy author """
    # there has got to be a more pretty way to do this?
    return {
        "affiliation": active_author_dict["affiliation"]
        if active_author_dict["affiliation"]
        else proxy_author_dict["affiliation"],
        "email_address": active_author_dict["email_address"]
        if active_author_dict["email_address"]
        else proxy_author_dict["email_address"],
        "first_name": active_author_dict["first_name"]
        if active_author_dict["first_name"]
        else proxy_author_dict["first_name"],
        "last_name": active_author_dict["last_name"]
        if active_author_dict["last_name"]
        else proxy_author_dict["last_name"],
        "middle_name": active_author_dict["middle_name"]
        if active_author_dict["middle_name"]
        else proxy_author_dict["middle_name"],
        "orcid": active_author_dict["orcid"]
        if active_author_dict["orcid"]
        else proxy_author_dict["orcid"],
    }

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

        # sql for moving the preprints
        update_preprints = "update janeway.repository_preprint set owner_id={} where owner_id={};".format(
            active_user.id, proxy_user.id
        )

        # working on the author metadata now

        update_authors = None
        proxy_author = None
        if Author.objects.filter(email_address=options["proxy_user"]).exists():
            if Author.objects.filter(email_address=options["active_user"]).exists():
                # two author metadata records need to be merged
                active_author = Author.objects.get(email_address=options["active_user"])
                proxy_author = Author.objects.get(email_address=options["proxy_user"])
                new_author_dict = merge_author_metadata(model_to_dict(active_author), model_to_dict(proxy_author))
            else:
                # the new email address does not already have an associated author entry
                update_authors = "update janeway.repository_author set email_address='{}' where email_address='{}';".format(
                    active_user.email, proxy_user.email
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

        if update_authors:
            self.stdout.write(self.style.NOTICE("email will be updated in author metadata"))
        elif not proxy_author is None:
            self.stdout.write(self.style.NOTICE("author metadata for active_user and proxy_user will be merged"))
            self.stdout.write(str(new_author_dict))

        if do_prompt and not boolean_input("Are you sure? (yes/no)"):
            raise CommandError("preprint move aborted")

        # merge authors as needed
        if update_authors is None and not proxy_author is None:
            Author.objects.filter(pk=active_author.pk).update(**new_author_dict)
            PreprintAuthor.objects.filter(author=proxy_author).update(author=active_author)
            proxy_author.delete()

        for pa in PreprintAuthor.objects.filter(account=proxy_user):
            if PreprintAuthor.objects.filter(preprint=pa.preprint, account=active_user).exists():
                pa.delete()
            else:
                pa.account = active_user
                pa.save()

        LogEntry.objects.filter(actor=proxy_user).update(actor=active_user)

        # run raw SQL with a cursor
        with connection.cursor() as cursor:
            cursor.execute(update_preprints)
            if update_authors is not None:
                cursor.execute(update_authors)
            cursor.fetchall()

        proxy_user.delete()

        # done!
        self.stdout.write(self.style.SUCCESS("✅ process complete"))
