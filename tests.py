from django.test import TestCase

from utils.testing import helpers

from submission.models import Article
from journal.models import Journal, Issue

from io import StringIO
from django.core.management import call_command
import os

class TestDeleteJournals(TestCase):

    def setUp(self):
        self.journal1, self.journal2 = helpers.create_journals()
        self.article = helpers.create_article(self.journal1)

    def call_command(self, *args, **kwargs):
        out = StringIO()
        call_command(
            "delete_journal",
            *args,
            stdout=out,
            stderr=StringIO(),
            **kwargs,
        )
        return out.getvalue()

    def test_delete_journal(self):
        article_id = self.article.pk
        self.journal1.delete()
        self.article = Article.objects.get(pk=article_id)
        self.assertEqual(Journal.objects.count(), 1)
        self.assertEqual(Article.objects.filter(journal=None).count(), 1)
        self.assertEqual(Article.objects.count(), 1)

    def test_delete_command(self):
        out = self.call_command(self.journal1.code, "--no-prompt")
        self.assertEqual(Journal.objects.count(), 1)
        self.assertEqual(Article.objects.filter(journal=None).count(), 0)
        self.assertEqual(Article.objects.count(), 0)

    def test_delete_dry_run(self):
        out = self.call_command(self.journal1.code, "--no-prompt", "--dry-run")
        self.assertEqual(Journal.objects.count(), 2)
        self.assertEqual(Article.objects.filter(journal=None).count(), 0)
        self.assertEqual(Article.objects.count(), 1)

class TestAddLicenses(TestCase):

    def setUp(self):
        self.journal, _ = helpers.create_journals()
        self.article1 = helpers.create_article(self.journal)
        self.article2 = helpers.create_article(self.journal)
        self.issue1 = helpers.create_issue(self.journal, articles=[self.article1])
        self.issue2 = self.create_duplicate_issue(self.issue1)
        self.issue2.articles.add(self.article2)
        self.issue2.save()

    def call_command(self, *args, **kwargs):
        out = StringIO()
        call_command(
            "add_licenses_by_issue",
            *args,
            stdout=out,
            stderr=StringIO(),
            **kwargs,
        )
        return out.getvalue()

    def create_duplicate_issue(self, issue):
        issue2 = Issue.objects.create(journal=issue.journal,
                                      issue=issue.issue,
                                      volume=issue.volume,
                                      issue_title='Duplicate Issue',
                                      issue_type=issue.issue_type,
                                      date=issue.date)
        return issue2

    def get_file_path(self, filename):
        return f'{os.path.dirname(__file__)}/test_files/{filename}'

    def test_duplicate_issues(self):
        out = self.call_command(self.journal.code, self.get_file_path("test_cc.tsv"))
        self.assertEqual(Article.objects.get(pk=self.article1.pk).license.short_name, "CC BY-NC 4.0")
        self.assertEqual(Article.objects.get(pk=self.article2.pk).license.short_name, "CC BY-NC 4.0")

