from django.core.management.base import BaseCommand, CommandError
from core.models import Account


class Command(BaseCommand):
    """Find users with no preferred_timezone and set it to US/Pacific"""
    help = "Find users with no preferred_timezone and set it to US/Pacific"



    def handle(self, *args, **options):

        try:
            num_updated = (Account.objects
                .filter(preferred_timezone__isnull=True)
                .update(preferred_timezone="US/Pacific")
            )
        except Exception as e:
            raise CommandError('Unable to set preferred_timezones for new users due to error\n %s' % e)
        
        print(f"Preferred Timezone updated to US/Pacific for {num_updated} users.")
