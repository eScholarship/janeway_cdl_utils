import json

from django.core.management.base import BaseCommand

from core.models import PGFileText, File


class Command(BaseCommand):
    """Import MySQL FileText objects into PGFileText objects"""
    help = "Import MySQL FileText objects into PGFileText objects"

    def add_arguments(self, parser):
        parser.add_argument(
            "text_export", help="Export of FileText objs from mysql", type=str
        )
        parser.add_argument(
            "relation_file", help="File containing the file to file text relations", type=str
        )

    def handle(self, *args, **options):
        text_export = options.get("text_export")
        relation_file = options.get("relation_file")

        with open(relation_file, 'r') as f:
            relations = json.load(f)

        with open(text_export, 'r') as f:
            file_texts_objs = json.load(f)

        for obj in file_texts_objs:
            if obj["model"] == "core.filetext":
                file_obj_pk = relations.get(str(obj['pk']), None)
                if file_obj_pk is not None and File.objects.filter(pk=file_obj_pk).exists():
                    file_obj = File.objects.get(pk=file_obj_pk)
                    if file_obj.text is None:
                        pg_filetext = PGFileText.objects.create(
                            contents=obj["fields"]["contents"]
                        )
                        file_obj.text = pg_filetext
                        file_obj.save()
