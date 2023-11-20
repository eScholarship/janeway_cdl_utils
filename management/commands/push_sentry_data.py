from django.core.management.base import BaseCommand, CommandError
from django.conf.settings import SENTRY_TOKEN, SENTRY_ORG, SENTRY_PROJECT

import requests, boto3, json

from utils.logger import get_logger
logger = get_logger(__name__)

class Command(BaseCommand):
    """Grabs performance metrics from Sentry and pushes them to CloudWatch"""
    help = "Grabs performance metrics from Sentry and pushes them to CloudWatch"

    def handle(self, *args, **options):
        url = f"https://sentry.io/api/0/organizations/{SENTRY_ORG}/events/?field=avg(transaction.duration)&project={SENTRY_PROJECT}&environment=production&statsPeriod=24h"
        headers = {"Authorization": f"Bearer {SENTRY_TOKEN}"}
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            rdata = json.loads(response.text)
            avg_time = rdata["data"][0]["avg(transaction.duration)"]
            units = rdata["units"]["avg(transaction.duration)"]
 
            data = [ {'MetricName': 'JANEWAY_TRANSACTIONS',
                  'Dimensions': [{'Name': 'Transaction',
                                  'Value': 'Average'},],
                  'Unit': units,
                  'Value': avg_time}]

            cloudwatch = boto3.client('cloudwatch')

            response = cloudwatch.put_metric_data(MetricData=data, Namespace="Janeway/Metrics")

            if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
                logger.info("Send metrics: success")
            else:
                logger.error(f'Send metrics: failed with code {response["ResponseMetadata"]["HTTPStatusCode"]}')
