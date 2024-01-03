from django.core.management.base import BaseCommand, CommandError

import csv, os

# The expected input file need to contain journal DOI and preprint DOI column in a csv

from repository.models import Preprint

class Command(BaseCommand):
    """Adds journal doi to preprint given preprint doi"""
    help = "Adds journal doi to preprint given preprint doi"

    def add_arguments(self, parser):
        parser.add_argument(
            "import_file", help="path to a file containing the journal ids and preprint id", type=str
        )

    def handle(self, *args, **options):
        import_file = options.get("import_file")

        if not os.path.exists(import_file):
            raise CommandError(f'File {import_file} not found.')

        doi_updated_count = 0
        alreadyexists_count = 0
        specialstring_count = 0
        doi_errors = 0
        notfound_errors = 0
        with open(import_file, 'r') as csvfile:
            reader = csv.DictReader(csvfile, delimiter=",")
            for i in reader:
                if i["journal DOI"] and i["preprint DOI"]:
                    jdoi = i["journal DOI"]
                    pdoi = i["preprint DOI"]
                    print(jdoi)
                    print(pdoi)
                    # make sure both dois start with https://doi.org
                    if not jdoi.startswith("https://doi.org") or not pdoi.startswith("https://doi.org"):

                        self.stdout.write(self.style.ERROR(f'ERROR invalid doi detected: {jdoi} {pdoi}'))
                        doi_errors += 1
                        continue
                    pdoi = pdoi[len("https://doi.org/"):]
                    # preprint doi is saved without the doi.org prefix
                    preprint = Preprint.objects.filter(preprint_doi=pdoi)
                    print(preprint)
                    if not preprint or len(preprint) != 1:
                        self.stdout.write(self.style.ERROR(f'ERROR preprint not found: {pdoi}'))
                        notfound_errors += 1
                        continue
                    if preprint[0].doi:
                        self.stdout.write(self.style.NOTICE(f"Skipping because publisher DOI already exists for {pdoi}"))
                        alreadyexists_count += 1
                        continue
                    if 'osf.io' in jdoi or 'ssrn' in jdoi:
                        self.stdout.write(self.style.NOTICE(f"Skipping because journal DOI has specific strings for {pdoi}"))
                        specialstring_count += 1
                        continue

                    preprint[0].doi = jdoi
                    preprint[0].save()
                    doi_updated_count += 1

        if doi_updated_count > 0:
            self.stdout.write(self.style.SUCCESS(f'✅ Publisher doi added to {doi_updated_count}.'))
        
        if doi_errors > 0:
            self.stdout.write(self.style.ERROR(f"{doi_errors} invalid doi(s) provided."))

        if notfound_errors > 0:
            self.stdout.write(self.style.ERROR(f"{notfound_errors} preprint(s) not found."))

        if alreadyexists_count > 0:
            self.stdout.write(self.style.NOTICE(f'Publisher doi already exists and hence skipped {alreadyexists_count}.'))
        
        if specialstring_count > 0:
            self.stdout.write(self.style.NOTICE(f"Publisher doi contains special string and hence skipped  {specialstring_count}."))
