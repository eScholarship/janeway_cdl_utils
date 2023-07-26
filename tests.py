from django.test import TestCase

from utils.testing import helpers

from submission.models import Article
from journal.models import Journal

from io import StringIO
from django.core.management import call_command

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
