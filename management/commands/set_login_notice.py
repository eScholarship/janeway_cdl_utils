import os

from django.core.management.base import BaseCommand, CommandError

from core.models import SettingValue
from journal.models import Journal

class Command(BaseCommand):
    """sets login notice and activates/deactivates display"""
    help = "sets login notice and activates/deactivates display"

    def add_arguments(self, parser):
        parser.add_argument(
            "value", help="`on` or `off` to activate/deactivate login notice", type=str
        )
        parser.add_argument(
            "journal", help="journal code for the journal in question or `all` for all journals", type=str
        )
        parser.add_argument(
            '-m',
            '--message',
            type=str,
            help='path to a file containing the message to add'
        )

    def handle(self, *args, **options):
        value = options.get("value")
        journal = options.get("journal")
        path = options.get("message", None)

        if path is not None:
            if not os.path.exists(path):
                raise CommandError(f'File at {path} not found.')
            with open(path, "r", encoding="utf-8") as f:
                msg = f.read()

        if journal == "all":
            SettingValue.objects.filter(
                setting__name="display_login_page_notice"
            ).update(value=value)
            if path is not None:
                SettingValue.objects.filter(
                    setting__name="login_page_notice"
                ).update(value=msg)
        else:
            if not Journal.objects.filter(code=journal).exists():
                raise CommandError(f'No journal with code {journal} found.')
            SettingValue.objects.filter(
                journal__code=journal,
                setting__name="display_login_page_notice"
            ).update(value=value)
            if path is not None:
                SettingValue.objects.filter(
                    journal__code=journal,
                    setting__name="login_page_notice"
                ).update(value=msg)
