from django.test import TestCase
from django.core.management.base import CommandError

from utils.testing import helpers

from submission.models import Article
from journal.models import Journal
from core.models import Account
from repository.models import PreprintAuthor

from io import StringIO
from django.core.management import call_command

import os

test_users = """Preprint ID,Author Order,First Name,Middle Name,Last Name,Email,Affiliation,CDL Notes
{id},1,Brian,Test,Tester,tinguru@mac.com,Test University,"existing user, same acct data"
{id},2,Test,Q,Test,tester2@mailinator.com,Test University,"existing user, different acct data"
{id},3,Bob,,Tester,bobresearcher@mailinator.com,Test University,existing user (preprint owner)
{id},4,Wei,,Zhang,eaauthor-test2@mailinator.com,Test University,new user
{id},5,Fatima,,Kumari,eaauthor-test3@mailinator.com,Test University,new user
{id},6,Bobby,B.,Researcher,bobresearcher+3@mailinator.com,Test University,"existing user, different acct data"
"""

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

class TestAddPreprintAuthors(TestCase):

    def create_account(self, email, fname, mname, lname, institution):
        a = Account.objects.create_user(email=email)
        a.first_name = fname
        a.middle_name = mname
        a.last_name = lname
        a.institution = institution
        a.save()
        return a

    def setUp(self):
        self.press = helpers.create_press()
        self.repo, subject = helpers.create_repository(self.press, [], [])
        self.user0 = self.create_account("bobresearcher@mailinator.com", "Bob", "", "Tester", "Test University")
        self.user1 = self.create_account("tinguru@mac.com", "Brian", "Test", "Tester", "Test University")
        self.user2 = self.create_account("tester2@mailinator.com", "Other", "M", "Name", "Other University")
        self.user3 = self.create_account("bobresearcher+3@mailinator.com", "Robert", "B", "Researcher", "Test University")
        self.user4 = self.create_account("other.user@test.org", "Other", "", "User", "Other University")

        self.preprint = helpers.create_preprint(self.repo, self.user4, subject)
        self.preprint.owner = self.user0
        self.preprint.save()

    def call_command(self, *args, **kwargs):
        out = StringIO()
        call_command(
            "add_preprint_authors",
            *args,
            stdout=out,
            stderr=StringIO(),
            **kwargs,
        )
        return out.getvalue()


    def test_append_authors(self):
        with open("test.csv", 'w') as t:
            t.write(test_users.format(id=self.preprint.pk))
        out = self.call_command("test.csv")

        self.assertEqual(len(self.preprint.authors), 7)

        self.assertEqual(PreprintAuthor.objects.filter(preprint=self.preprint, account=self.user4).count(), 1)
        self.assertEqual(PreprintAuthor.objects.filter(preprint=self.preprint, account=self.user3).count(), 1)
        self.assertEqual(PreprintAuthor.objects.filter(preprint=self.preprint, account=self.user2).count(), 1)
        self.assertEqual(PreprintAuthor.objects.filter(preprint=self.preprint, account=self.user1).count(), 1)
        self.assertEqual(PreprintAuthor.objects.filter(preprint=self.preprint, account=self.user0).count(), 1)

        self.assertEqual(PreprintAuthor.objects.filter(preprint=self.preprint, account__email="eaauthor-test2@mailinator.com").count(), 1)
        self.assertEqual(PreprintAuthor.objects.filter(preprint=self.preprint, account__email="eaauthor-test3@mailinator.com").count(), 1)

        u1 = Account.objects.get(email="tester2@mailinator.com")
        self.assertEqual(u1.first_name, "Other")
        self.assertEqual(u1.middle_name, "M")
        self.assertEqual(u1.last_name, "Name")
        self.assertEqual(u1.institution, "Other University")

        p1 = PreprintAuthor.objects.get(preprint=self.preprint, account=u1)
        self.assertEqual(p1.order, 2)
        self.assertEqual(p1.affiliation, "Test University")

        u2 = Account.objects.get(email="eaauthor-test3@mailinator.com")
        self.assertEqual(u2.first_name, "Fatima")
        self.assertEqual(u2.middle_name, "")
        self.assertEqual(u2.last_name, "Kumari")
        self.assertEqual(u2.institution, "Test University")

        p2 = PreprintAuthor.objects.get(preprint=self.preprint, account=u2)
        self.assertEqual(p2.order, 5)
        self.assertEqual(p2.affiliation, "Test University")

    def test_overwrite_authors(self):
        with open("test.csv", 'w') as t:
            t.write(test_users.format(id=self.preprint.pk))
        out = self.call_command("test.csv", "--overwrite")
        self.assertEqual(len(self.preprint.authors), 6)

        self.assertFalse(PreprintAuthor.objects.filter(preprint=self.preprint, account=self.user4).exists())

        self.assertEqual(PreprintAuthor.objects.filter(preprint=self.preprint, account=self.user3).count(), 1)
        self.assertEqual(PreprintAuthor.objects.filter(preprint=self.preprint, account=self.user2).count(), 1)
        self.assertEqual(PreprintAuthor.objects.filter(preprint=self.preprint, account=self.user1).count(), 1)
        self.assertEqual(PreprintAuthor.objects.filter(preprint=self.preprint, account=self.user0).count(), 1)

        self.assertEqual(PreprintAuthor.objects.filter(preprint=self.preprint, account__email="eaauthor-test2@mailinator.com").count(), 1)
        self.assertEqual(PreprintAuthor.objects.filter(preprint=self.preprint, account__email="eaauthor-test3@mailinator.com").count(), 1)

    def test_no_preprint(self):
        with open("test.csv", 'w') as t:
            t.write(test_users.format(id=1000))
        with self.assertRaises(CommandError):
            out = self.call_command("test.csv")

        self.assertEqual(len(self.preprint.authors), 1)

    def test_author_exists(self):
        with open("test.csv", 'w') as t:
            t.write(test_users.format(id=self.preprint.pk))
        author = PreprintAuthor.objects.create(preprint=self.preprint, account=self.user0, order=1)
        with self.assertRaises(CommandError):
            out = self.call_command("test.csv")

        self.assertEqual(len(self.preprint.authors), 2)

    def test_author_exists_overwrite(self):
        with open("test.csv", 'w') as t:
            t.write(test_users.format(id=self.preprint.pk))
        author = PreprintAuthor.objects.create(preprint=self.preprint, account=self.user0, order=1)
        out = self.call_command("test.csv", "--overwrite")

        self.assertEqual(len(self.preprint.authors), 6)

        self.assertFalse(PreprintAuthor.objects.filter(preprint=self.preprint, account=self.user4).exists())

        self.assertTrue(PreprintAuthor.objects.filter(preprint=self.preprint, account=self.user3).exists())
        self.assertTrue(PreprintAuthor.objects.filter(preprint=self.preprint, account=self.user2).exists())
        self.assertTrue(PreprintAuthor.objects.filter(preprint=self.preprint, account=self.user1).exists())
        self.assertTrue(PreprintAuthor.objects.filter(preprint=self.preprint, account=self.user0).exists())

        self.assertTrue(PreprintAuthor.objects.filter(preprint=self.preprint, account__email="eaauthor-test2@mailinator.com").exists())
        self.assertTrue(PreprintAuthor.objects.filter(preprint=self.preprint, account__email="eaauthor-test3@mailinator.com").exists())
