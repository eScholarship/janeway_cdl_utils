from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

import requests, boto3, json
from datetime import date, timedelta, datetime

from utils.logger import get_logger
logger = get_logger(__name__)

class Command(BaseCommand):
    """Grabs performance metrics from Sentry and pushes them to CloudWatch"""
    help = "Grabs performance metrics from Sentry and pushes them to CloudWatch"

    def add_arguments(self, parser):
        parser.add_argument("-p", "--profile", type=str)
        parser.add_argument("-d", "--daysago", type=int, default=0)

    def handle(self, *args, **options):
        profile = options.get("profile")

        days_ago = options.get("daysago")
        today = date.today()
        timestamp = datetime(today.year, today.month, today.day) - timedelta(days=days_ago)
        start = timestamp - timedelta(hours=24)

        url = f"https://sentry.io/api/0/organizations/{settings.SENTRY_ORG}/events/?field=avg(transaction.duration)&project={settings.SENTRY_PROJECT}&environment=production&statsPeriod=24h&start={start}"
        headers = {"Authorization": f"Bearer {settings.SENTRY_TOKEN}"}
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            rdata = json.loads(response.content)
            units = rdata["meta"]["units"]["avg(transaction.duration)"]
            if units == "millisecond":
                units = "Milliseconds"
            data = []
            for i in rdata["data"]:
              avg_time = i["avg(transaction.duration)"]
 
              data.append({'MetricName': 'JANEWAY_TRANSACTIONS',
                           'Dimensions': [{'Name': 'Transaction',
                                           'Value': 'Average'},],
                           'Unit': units,
                           'Value': avg_time,
                           'Timestamp': timestamp})

            region = "us-west-2"
            if profile: # if a profile is indicated use that
                session = boto3.Session(profile_name=profile, region_name=region)
                cloudwatch = session.client('cloudwatch')
            elif hasattr(settings, 'METRICS_ROLE'): # else look for a role
                sts = boto3.client('sts', region_name=region)
                resp = sts.assume_role(RoleArn=settings.METRICS_ROLE,
                                       RoleSessionName="push_janeway_db_metrics")
                cred = resp['Credentials']
                subsession = boto3.session.Session(aws_access_key_id=cred['AccessKeyId'],
                                                   aws_secret_access_key=cred['SecretAccessKey'],
                                                   aws_session_token=cred['SessionToken'],
                                                   region_name=region)
                cloudwatch = subsession.client('cloudwatch', region_name=region)
            else: # else try the default behavior (on ec2 use the local role)
                cloudwatch = boto3.client('cloudwatch', region_name=region)

            response = cloudwatch.put_metric_data(MetricData=data, Namespace="Janeway/Metrics")

            if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
                logger.info("Send metrics: success")
            else:
                logger.error(f'Send metrics: failed with code {response["ResponseMetadata"]["HTTPStatusCode"]}')
