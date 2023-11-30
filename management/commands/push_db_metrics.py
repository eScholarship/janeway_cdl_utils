from django.core.management.base import BaseCommand, CommandError

from journal.models import Journal
from submission.models import Article
from core.models import File

import boto3

from utils.logger import get_logger
logger = get_logger(__name__)

class Command(BaseCommand):
    """Pushes db counts to AWS CloudWatch metrics"""
    help = "Pushes db counts to AWS CloudWatch metrics"

    def add_arguments(self, parser):
        parser.add_argument("-p", "--profile", type=str)
 
    def handle(self, *args, **options):
        profile = options.get("profile", False)
        if profile:
          session = boto3.Session(profile_name=profile, region_name="us-west-2")
          cloudwatch = session.client('cloudwatch')
        else:
          cloudwatch = boto3.client('cloudwatch')

        data = [ {'MetricName': 'TOTAL_JOURNALS',
                  'Dimensions': [{'Name': 'DB_COUNT',
                                  'Value': 'COUNT'},],
                  'Unit': 'None',
                  'Value': Journal.objects.all().count()},
                {'MetricName': 'TOTAL_ARTICLES',
                  'Dimensions': [{'Name': 'DB_COUNT',
                                  'Value': 'COUNT'},],
                  'Unit': 'None',
                  'Value': Article.objects.all().count()},
                {'MetricName': 'TOTAL_FILES',
                  'Dimensions': [{'Name': 'DB_COUNT',
                                  'Value': 'COUNT'},],
                  'Unit': 'None',
                  'Value': File.objects.all().count()}]

        response = cloudwatch.put_metric_data(MetricData=data, Namespace="Janeway/Metrics")

        if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
            logger.info("Send metrics: success")
        else:
            logger.error(f'Send metrics: failed with code {response["ResponseMetadata"]["HTTPStatusCode"]}')
