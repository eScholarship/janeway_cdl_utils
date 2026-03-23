from django.core.management.base import BaseCommand, CommandError

import csv
import os
from pathlib import Path

from django.core.files.base import ContentFile

from core.models import Galley, Account
from journal.models import Journal
from submission.models import Article, FrozenAuthor, Licence, Section
from core.files import save_file_to_article

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

    def get_ingestion_dir(self, path, s):
        languages = ["english", "french", "portuguese", "spanish"]
        iid = Path(s).stem
        for l in languages:
            import_path = path.joinpath(l, iid)
            if import_path.exists() and import_path.is_dir():
                return l, import_path
        return None, None

    def get_files(self, row, path):
        lang, import_path = self.get_ingestion_dir(path, row["iid"])
        images = [x for x in import_path.iterdir() if x.suffix == ".gif"]
        html = [x for x in import_path.iterdir() if x.suffix == ".html"]
        if len(html) > 1:
            print(f"{row['iid']} multiple html files")
        return html[0], images

    def get_file_obj(self, article, path, owner):
        with open(path, 'rb') as local_file:
            fobj = ContentFile(local_file.read(), name=path.name)
        return save_file_to_article(fobj, article, owner)

    def import_files(self, item, html_path, image_paths, owner):
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
        )

        for img_path in image_paths:
            img_file = self.get_file_obj(item, img_path, owner)
            img_file.is_galley = False
            img_file.save()
            g.images.add(img_file)
 
 
    def import_item(self, j, row, makers_map, collaborators_map, owner):
        license = Licence.objects.get(journal=j, short_name="Copyright")
        section = Section.objects.get(journal=j, name=row["section"])
        a, _created = Article.objects.get_or_create(
            journal=j,
            title=row["title"],
            abstract=row["description"],
            owner=owner,
            license=license,
            section=section
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

        j = Journal.objects.get(code=journal_code)
        owner = Account.objects.get(pk=owner_id)

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
                item = self.import_item(j, row, makers_map, collaborators_map, owner)
                html_path, img_paths = self.get_files(row, Path(file_path))
                self.import_files(item, html_path, img_paths, owner)
