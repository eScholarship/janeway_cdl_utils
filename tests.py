from django.test import TestCase
from django.core.management.base import CommandError

from utils.testing import helpers

from submission.models import Article
from journal.models import Journal, Issue
from core.models import Account
from repository.models import PreprintAuthor, Author, Preprint

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

test_no_order = """Preprint ID,Author Order,First Name,Middle Name,Last Name,Email,Affiliation,CDL Notes
{id},,No,,Order,no-order@test.org,Test University,"new user, no order"
"""

test_no_email = """Preprint ID,Author Order,First Name,Middle Name,Last Name,Email,Affiliation,CDL Notes
{id},,No,,Email,,Test University,"new user, no email"
"""

test_no_id_column = """Author Order,First Name,Middle Name,Last Name,Email,Affiliation
4,Wei,,Zhang,eaauthor-test2@mailinator.com,Test University
"""

class TestMovePreprints(TestCase):
    def setUp(self):
        self.user = helpers.create_user("manager@test.edu")
        self.press = helpers.create_press()
        self.repo, subject = helpers.create_repository(self.press, [self.user], [self.user])
        self.author = helpers.create_user("author@test.edu")
        self.preprint = helpers.create_preprint(self.repo, self.author, subject)
        self.active_user = helpers.create_user("active@test.edu")
        self.proxy_user = helpers.create_user("proxy@test.edu")

    def call_command(self, *args, **kwargs):
        out = StringIO()
        call_command(
            "move_preprints",
            *args,
            stdout=out,
            stderr=StringIO(),
            **kwargs,
        )
        return out.getvalue()

    def test_merge_accounts(self):
        out = self.call_command(self.active_user.email, self.author.email, "--no-prompt")
        self.assertTrue(PreprintAuthor.objects.filter(preprint=self.preprint, account=self.active_user).exists())
        self.assertFalse(Account.objects.filter(pk=self.author.pk).exists())
        self.assertEqual(Preprint.objects.get(pk=self.preprint.pk).owner.pk, self.active_user.pk)

    def test_old_authors(self):
        active_author = Author.objects.create(email_address=self.active_user.email, first_name="Active", last_name="Author")
        proxy_author = Author.objects.create(email_address=self.proxy_user.email, first_name="Proxy", last_name="Author")
        out = self.call_command(self.active_user.email, self.proxy_user.email, "--no-prompt")
        # just ignore the "Author" table now
        # this test can just be deleted with the Authors table is fully deleted
        self.assertTrue(Author.objects.filter(email_address=self.active_user.email).exists())
        self.assertTrue(Author.objects.filter(email_address=self.proxy_user.email).exists())

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
        out = self.call_command(self.preprint.pk, "test.csv")

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
        self.assertEqual(p1.order, 3)
        self.assertEqual(p1.affiliation, "Test University")

        u2 = Account.objects.get(email="eaauthor-test3@mailinator.com")
        self.assertEqual(u2.first_name, "Fatima")
        self.assertEqual(u2.middle_name, "")
        self.assertEqual(u2.last_name, "Kumari")
        self.assertEqual(u2.institution, "Test University")

        p2 = PreprintAuthor.objects.get(preprint=self.preprint, account=u2)
        self.assertEqual(p2.order, 6)
        self.assertEqual(p2.affiliation, "Test University")

        p3 = PreprintAuthor.objects.get(preprint=self.preprint, account__email="tinguru@mac.com")
        self.assertEqual(p3.order, 2)

        p4 = PreprintAuthor.objects.get(preprint=self.preprint, account__email="bobresearcher@mailinator.com")
        self.assertEqual(p4.order, 4)

        p5 = PreprintAuthor.objects.get(preprint=self.preprint, account__email="eaauthor-test2@mailinator.com")
        self.assertEqual(p5.order, 5)

        p6 = PreprintAuthor.objects.get(preprint=self.preprint, account__email="bobresearcher+3@mailinator.com")
        self.assertEqual(p6.order, 7)

    def test_overwrite_authors(self):
        with open("test.csv", 'w') as t:
            t.write(test_users.format(id=self.preprint.pk))
        out = self.call_command(self.preprint.pk, "test.csv", "--overwrite")
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
        with self.assertRaises(CommandError) as e:
            out = self.call_command(1000, "test.csv")

        self.assertEqual(str(e.exception), 'Preprint 1000 does not exist')
        self.assertEqual(len(self.preprint.authors), 1)

    def test_preprint_mismatch(self):
        with open("test.csv", 'w') as t:
            t.write(test_users.format(id=1000))
        with self.assertRaises(CommandError) as e:
            out = self.call_command(self.preprint.pk, "test.csv")

        self.assertEqual(str(e.exception), f'Preprint ID 1000 does not match {self.preprint.pk}')
        self.assertEqual(len(self.preprint.authors), 1)

    def test_author_exists(self):
        with open("test.csv", 'w') as t:
            t.write(test_users.format(id=self.preprint.pk))
        author = PreprintAuthor.objects.create(preprint=self.preprint, account=self.user0, order=1)
        with self.assertRaises(CommandError) as e:
            out = self.call_command(self.preprint.pk, "test.csv")

        self.assertEqual(str(e.exception), f'Account with email bobresearcher@mailinator.com is already an author on Preprint {self.preprint.pk}. Did you mean to use *overwrite*?')
        self.assertEqual(len(self.preprint.authors), 2)

    def test_no_email(self):
        with open("test.csv", 'w') as t:
            t.write(test_no_email.format(id=self.preprint.pk))
        with self.assertRaises(CommandError) as e:
            out = self.call_command(self.preprint.pk, "test.csv")

        self.assertEqual(str(e.exception), 'No email address specified for No Email')
        self.assertEqual(len(self.preprint.authors), 1)

    def test_no_order(self):
        with open("test.csv", 'w') as t:
            t.write(test_no_order.format(id=self.preprint.pk))
        with self.assertRaises(CommandError) as e:
            out = self.call_command(self.preprint.pk, "test.csv")

        self.assertEqual(str(e.exception), 'No author order specified for no-order@test.org')
        self.assertEqual(len(self.preprint.authors), 1)

    def test_no_id_column(self):
        with open("test.csv", 'w') as t:
            t.write(test_no_id_column)
        out = self.call_command(self.preprint.pk, "test.csv")

        self.assertEqual(len(self.preprint.authors), 2)

    def test_author_exists_overwrite(self):
        with open("test.csv", 'w') as t:
            t.write(test_users.format(id=self.preprint.pk))
        author = PreprintAuthor.objects.create(preprint=self.preprint, account=self.user0, order=1)
        out = self.call_command(self.preprint.pk, "test.csv", "--overwrite")

        self.assertEqual(len(self.preprint.authors), 6)

        self.assertFalse(PreprintAuthor.objects.filter(preprint=self.preprint, account=self.user4).exists())

        self.assertTrue(PreprintAuthor.objects.filter(preprint=self.preprint, account=self.user3).exists())
        self.assertTrue(PreprintAuthor.objects.filter(preprint=self.preprint, account=self.user2).exists())
        self.assertTrue(PreprintAuthor.objects.filter(preprint=self.preprint, account=self.user1).exists())
        self.assertTrue(PreprintAuthor.objects.filter(preprint=self.preprint, account=self.user0).exists())

        self.assertTrue(PreprintAuthor.objects.filter(preprint=self.preprint, account__email="eaauthor-test2@mailinator.com").exists())
        self.assertTrue(PreprintAuthor.objects.filter(preprint=self.preprint, account__email="eaauthor-test3@mailinator.com").exists())
