from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.forms.models import model_to_dict

from core.models import Account
from repository.models import Author, PreprintAuthor

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
    help = "update author email"

    def add_arguments(self, parser):
        parser.add_argument(
            "active_user", help="`email` of new active account", type=str
        )
        parser.add_argument("proxy_user", help="`email` of old proxy account", type=str)

    def handle(self, *args, **options):

        # working on the author metadata now
        if not Author.objects.filter(email_address=options["active_user"]).exists():
            # the new email address does not already have an associated author entry
            update_authors = "update janeway.repository_author set email_address='{}' where email_address='{}';".format(
                options["active_user"], options["proxy_user"]
            )
        else:
            # two author metadata records need to be merged
            update_authors = None
            active_author = Author.objects.get(email_address=options["active_user"])
            proxy_author = Author.objects.get(email_address=options["proxy_user"])
            new_author_dict = merge_author_metadata(model_to_dict(active_author), model_to_dict(proxy_author))


        # echo what will happen, and ask the operator to okay

        if update_authors:
            self.stdout.write(self.style.NOTICE("email will be updated in author metadata"))
        else:
            self.stdout.write(self.style.NOTICE("author metadata for active_user and proxy_user will be merged"))
            self.stdout.write(str(new_author_dict))

        if not boolean_input("Are you sure? (yes/no)"):
            raise CommandError("preprint move aborted")

        # merge authors as needed
        if update_authors is None:
            Author.objects.filter(pk=active_author.pk).update(**new_author_dict)
            PreprintAuthor.objects.filter(author=proxy_author).update(author=active_author)
            proxy_author.delete()

        # run raw SQL with a cursor
        with connection.cursor() as cursor:
            if update_authors is not None:
                cursor.execute(update_authors)
                cursor.fetchall()

        # done!
        self.stdout.write(self.style.SUCCESS("✅ process complete"))
