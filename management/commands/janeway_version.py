from django.core.management.base import BaseCommand

import git
from utils.logic import get_janeway_version

class Command(BaseCommand):
    """
    Prints the current version of Janeway, the git remote, the current git branch, commit hash,
    and last log line
    """

    help = "Prints version information for this Janeway installation. Requires gitpython module: pip install gitpython"

    def handle(self, *args, **options):
        """Prints Janeway version information

        :param args: None
        :param options: dict
        :return: None
        """
    version = get_janeway_version()
    repo = git.Repo(search_parent_directories=True)
    remote_url = repo.remotes.origin.url
    branch = repo.head.ref
    commit_hash = repo.head.object.hexsha
    last_log_line = repo.head.log()[-1]

    print("Janeway Version:", version)
    print("Remote URL:", remote_url)
    print("Current branch:", branch)
    print("Commit hash:", commit_hash)
    print("Last log line:", last_log_line)
