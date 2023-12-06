from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

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
