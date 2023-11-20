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

    def handle(self, *args, **options):
        cloudwatch = boto3.client('cloudwatch')

        data = [ {'MetricName': 'JANEWAY_DB_COUNTS',
                  'Dimensions': [{'Name': 'JOURNAL',
                                  'Value': 'COUNT'},],
                  'Unit': 'None',
                  'Value': Journal.objects.all().count()},
                {'MetricName': 'JANEWAY_DB_COUNTS',
                  'Dimensions': [{'Name': 'ARTICLE',
                                  'Value': 'COUNT'},],
                  'Unit': 'None',
                  'Value': Article.objects.all().count()},
                {'MetricName': 'JANEWAY_DB_COUNTS',
                  'Dimensions': [{'Name': 'FILE',
                                  'Value': 'COUNT'},],
                  'Unit': 'None',
                  'Value': File.objects.all().count()}]

        response = cloudwatch.put_metric_data(MetricData=data, Namespace="Janeway/DBCounts")

        if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
            logger.info("Send metrics: success")
        else:
            logger.error(f'Send metrics: failed with code {response["ResponseMetadata"]["HTTPStatusCode"]}')
