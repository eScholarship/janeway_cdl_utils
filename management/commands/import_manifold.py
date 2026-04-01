from django.core.management.base import BaseCommand, CommandError

import csv
import os
from pathlib import Path
from bs4 import BeautifulSoup
from datetime import datetime

from django.core.files.base import ContentFile

from core.models import Galley, Account
from journal.models import Journal, Issue
from submission.models import Article, FrozenAuthor, Licence, Section, STAGE_PUBLISHED
from core.files import save_file_to_article

LANGUAGES = {"english": "eng", "portuguese": "por", "spanish": "spa", "french": "fra"}

class Command(BaseCommand):
    help = "Command to import manifold items"

    def add_arguments(self, parser):
        parser.add_argument(
            "journal_code", help="`code` of the journal to import to", type=str
        )
        parser.add_argument(
            "file_path",
            help="path to directory that contains csv files and export files",
            type=str
        )
        parser.add_argument(
            "owner_id",
            help="pk of the owner",
            type=int
        )
        parser.add_argument(
           "--issue-id",
           help="pk of the issue to import to"
           type=int,
        )

    def get_ingestion_dir(self, path, s):
        languages = ["english", "french", "portuguese", "spanish"]
        iid = Path(s).stem
        for l in languages:
            import_path = path.joinpath(l, iid)
            if import_path.exists() and import_path.is_dir():
                return l, import_path
        return None, None

    def get_files(self, row, import_path):
        images = [x for x in import_path.iterdir() if x.suffix == ".gif"]
        html = [x for x in import_path.iterdir() if x.suffix == ".html"]
        if len(html) > 1:
            print(f"{row['iid']} multiple html files")
        return html[0], images

    def get_file_obj(self, article, path, owner):
        with open(path, 'rb') as local_file:
            fobj = ContentFile(local_file.read(), name=path.name)
        return save_file_to_article(fobj, article, owner)

    def fix_html(self, html_path):
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()

        soup = BeautifulSoup(html_content, 'html.parser')

        # Remove extraneous title header
        for h in soup.find_all("h2"):
            h.decompose()

        # the first h3 header is the article title
        soup.find("h3").name = "h1"

        # reduce the level of all the following headers
        for tag in soup.find_all(["h3","h4"]):
            level = int(tag.name[1])
            tag.name = f"h{level-1}"
            for strong in tag.find_all("strong"):
                strong.unwrap()

        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(str(soup))

    def import_files(self, item, html_path, image_paths, owner, css_path):
        css_file = self.get_file_obj(item, css_path, owner)
        self.fix_html(html_path)
        html_file = self.get_file_obj(item, html_path, owner)
        html_file.is_galley = True
        html_file.label = "HTML"
        html_file.save()

        g = Galley.objects.create(
            article=item,
            file=html_file,
            label="HTML Galley",
            type="html",
            sequence=item.get_next_galley_sequence(),
            public=True,
            css_file=css_file
        )

        for img_path in image_paths:
            img_file = self.get_file_obj(item, img_path, owner)
            img_file.is_galley = False
            img_file.save()
            g.images.add(img_file)

        item.render_galley = g
        item.save()
 
 
    def import_item(self, j, row, makers_map, collaborators_map, owner, lang):
        license = Licence.objects.get(journal=j, short_name="Copyright")
        section, _ = Section.objects.get_or_create(journal=j, name=row["section"])
        # created_at is the only date we seem to have
        date_published = datetime.strptime(
            row["created_at"],
            "%Y-%m-%d %H:%M:%S.%f"
        )
        a, _created = Article.objects.get_or_create(
            journal=j,
            title=row["title"],
            abstract=row["description"],
            owner=owner,
            license=license,
            section=section,
            language=LANGUAGES[lang],
            stage=STAGE_PUBLISHED,
            date_published=date_published
        )
        if row["id"] in collaborators_map:
            for c in collaborators_map[row["id"]]:
                maker = makers_map[c["maker_id"]]
                fa = FrozenAuthor.objects.get_or_create(
                    article=a,
                    first_name=maker["first_name"],
                    middle_name=maker["middle_name"],
                    last_name=maker["last_name"],
                    name_suffix=maker["suffix"],
                    name_prefix=maker["prefix"],
                    order=c["position"]
                )
        return a

    def handle(self, *args, **options):
        journal_code = options.get("journal_code")
        file_path = options.get("file_path")
        owner_id = options.get("owner_id")
        issue_id = options.get("issue_id")

        j = Journal.objects.get(code=journal_code)
        owner = Account.objects.get(pk=owner_id)
        issue = Issue.objects.get(pk=issue_id) if issue_id else None

        with open(os.path.join(file_path, "makers.csv"), mode='r', newline='') as f:
            r = csv.DictReader(f, delimiter="|")
            makers_map = {row["id"]: row for row in r}

        with open(os.path.join(file_path, "collaborators.csv"), mode='r', newline='') as f:
            r = csv.DictReader(f, delimiter="|")
            collaborators_map = {}
            for row in r:
                item_id = row["collaboratable_id"]
                if not item_id in collaborators_map:
                    collaborators_map[item_id] = [row]
                else:
                    collaborators_map[item_id].append(row)

        with open(os.path.join(file_path, "test.csv"), mode='r', newline='') as f:
            r = csv.DictReader(f, delimiter="|")
            for row in r:
                lang, import_path = self.get_ingestion_dir(Path(file_path), row["iid"])
                item = self.import_item(j, row, makers_map, collaborators_map, owner, lang)
                if issue:
                    issue.articles.add(item)
                    issue.save()
                html_path, img_paths = self.get_files(row, import_path)
                self.import_files(item, html_path, img_paths, owner, import_path.joinpath("md.css"))
