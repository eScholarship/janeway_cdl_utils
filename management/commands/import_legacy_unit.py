"""
Management command: import a unit from a legacy MySQL database into Janeway.

Usage (live database):
    python manage.py import_legacy_unit my_unit_id \
        --db-name legacy --db-user reader --db-password secret \
        --assets-url-prefix https://my-bucket.s3.amazonaws.com/assets/ --dry-run

Usage (export files instead of a live database):
    python manage.py import_legacy_unit my_unit_id \
        --units-file units.tsv --pages-file pages.tsv --widgets-file widgets.tsv \
        --assets-url-prefix https://my-bucket.s3.amazonaws.com/assets/ --dry-run

Export files
------------
Each file holds the *whole* table (rows for other units are ignored; rows are
matched on units.id / pages.unit_id / widgets.unit_id). Supported formats,
chosen by file extension:

    .tsv / .txt     tab-separated. Default dialect "mysql" understands the escaping
                    used by `mysql -B` and SELECT ... INTO OUTFILE (\\n, \\t, \\\\, \\0
                    and NULL / \\N). Use --tsv-dialect plain for unescaped TSV.
    .csv            comma-separated, standard quoting (\\N is read as NULL).
    .json / .jsonl  a JSON array of row objects, or one JSON object per line.

CSV/TSV files need a header row naming the columns. If yours has none (e.g.
exported with `mysql -N`), pass the column names with --units-columns /
--pages-columns / --widgets-columns (comma-separated, in file order).

mysql --defaults-extra-file=~/.passwords/jschol_ro_pw.mysql -e "SELECT * FROM units WHERE id = 'unit_id'" > /tmp/unit.tsv
mysql --defaults-extra-file=~/.passwords/jschol_ro_pw.mysql -e "SELECT * FROM pages WHERE unit_id = 'unit_id'" > /tmp/pages.tsv
mysql --defaults-extra-file=~/.passwords/jschol_ro_pw.mysql -e "SELECT * FROM widgets WHERE unit_id = 'unit_id'" > /tmp/widgets.tsv

Columns the command reads:
    units    id, attrs
    pages    unit_id, slug, name, title, attrs
    widgets  unit_id, id, kind, ordering, region, attrs
(`attrs` holds JSON text.)  --units-file is required; the pages and widgets
files are optional (without them pages / widgets are simply not migrated).
"""
import csv
import io
import json
import mimetypes
import os
from urllib.error import URLError
from urllib.request import urlopen

from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction

from utils.setting_handler import save_plugin_setting, save_setting
from core import files as core_files

from cms.models import NavigationItem, Page, MediaFile
from core.models import HomepageElement
from journal.models import Journal

from plugins.health_dashboard.models import Category, JournalCategory
from plugins.Media_carousel.models import MediaCarousel, MediaCarouselSlide

from core.homepage_elements.html import plugin_settings as html_plugin

LEGACY_ALIAS = "legacy"
ASSET_TIMEOUT = 30  # seconds

JOURNAL_Q = "SELECT * FROM units WHERE id = %s"
PAGE_Q = "SELECT * FROM pages WHERE unit_id = %s"
WIDGET_Q = "SELECT * FROM widgets WHERE unit_id = %s"

# Each legacy table: the query used against a live DB, the column that holds the
# unit id (used to filter export files), and the columns we need to find in an export.
TABLES = {
    "units": {"sql": JOURNAL_Q, "key": "id", "required": ["id", "attrs"]},
    "pages": {"sql": PAGE_Q, "key": "unit_id", "required": ["unit_id", "slug"]},
    "widgets": {
        "sql": WIDGET_Q,
        "key": "unit_id",
        "required": ["unit_id", "id", "kind", "ordering"],
    },
}

# "type": "bool" -> stored as "on" / ""; anything else is stored as a string.
# Settings with no "default" are skipped when the source attr is missing.
SETTING_MAP = [
    {
        "attr": "altmetrics_ok",
        "group": "article",
        "setting": "display_altmetric_badge",
        "type": "bool",
        "default": "on",
    },
    {
        "attr": "doaj",
        "group": "plugin",
        "setting": "doaj_publish_push",
        "type": "bool",
        "default": "off",
    },
    {"attr": "eissn", "group": "general", "setting": "journal_issn"},
    {"attr": "issn", "group": "general", "setting": "print_issn"},
    {
        "attr": "pub_freq",
        "group": "plugin:health_dashboard",
        "setting": "publication_frequency",
    },
]

TRUTHY = ("on", "true", "1", "yes", "y")

WIDGET_LABELS = {
    "Text": "Text Block",
    "RecentArticles": "Recent Articles",
    "Carousel": "Carousel",
}


def as_json(value):
    """Columns may come back as JSON text, bytes, or already-parsed objects."""
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8")
    if isinstance(value, str):
        return json.loads(value) if value.strip() else {}
    return value or {}


def to_setting_value(spec, raw):
    if spec.get("type") == "bool":
        if isinstance(raw, str):
            raw = raw.strip().lower() in TRUTHY
        return "on" if raw else ""
    return "" if raw is None else str(raw)


# --------------------------------------------------------------------------- #
# Export-file readers (no Django / database access)
# --------------------------------------------------------------------------- #
_MYSQL_ESCAPES = {"\\": "\\", "n": "\n", "t": "\t", "0": "\0"}


def _unescape_mysql(value):
    """Undo the escaping done by `mysql -B` / INTO OUTFILE."""
    if "\\" not in value:
        return value
    out, i = [], 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value) and value[i + 1] in _MYSQL_ESCAPES:
            out.append(_MYSQL_ESCAPES[value[i + 1]])
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _mysql_cell(raw):
    if raw in ("NULL", "\\N"):
        return None
    cell = _unescape_mysql(raw)
    # If unescaping broke a JSON value but the raw text is valid JSON, the file
    # wasn't mysql-escaped after all; keep the raw text.
    if cell != raw and cell[:1] in ("{", "["):
        try:
            json.loads(cell)
        except ValueError:
            try:
                json.loads(raw)
                return raw
            except ValueError:
                pass
    return cell


def _load_json_rows(text, path):
    try:
        data = json.loads(text)
    except ValueError:  # not one JSON document -> JSON Lines
        data = []
        for lineno, line in enumerate(text.split("\n"), start=1):
            if line.strip():
                try:
                    data.append(json.loads(line))
                except ValueError as exc:
                    raise CommandError(f"{path}:{lineno}: invalid JSON: {exc}")
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        raise CommandError(f"{path}: expected a JSON array of objects (or one object per line).")
    return data


def load_export_file(path, columns=None, dialect="mysql"):
    """Read an export file into a list of {column: value} dicts.

    columns: names to use when the file has no header row.
    dialect: "mysql" (unescape mysql output, NULL -> None) or "plain" (TSV as-is).
    """
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            text = fh.read()
    except OSError as exc:
        raise CommandError(f"Cannot read {path}: {exc}")

    ext = os.path.splitext(path)[1].lower()
    if ext in (".json", ".jsonl", ".ndjson"):
        return _load_json_rows(text, path)

    if ext == ".csv":
        records = [r for r in csv.reader(io.StringIO(text, newline="")) if r]
        cell = lambda v: None if v == "\\N" else v  # noqa: E731
    else:  # .tsv, .txt, anything else
        # Split on "\n" only: str.splitlines() would also split on characters
        # (U+2028, \x0b, ...) that can legitimately appear inside HTML content.
        records = [ln.rstrip("\r").split("\t") for ln in text.split("\n") if ln.strip("\r")]
        cell = _mysql_cell if dialect == "mysql" else (lambda v: v)

    if not records:
        return []
    if columns:
        header, body, first_row = list(columns), records, 1
    else:
        header, body, first_row = [h.strip() for h in records[0]], records[1:], 2

    rows = []
    for offset, rec in enumerate(body):
        if len(rec) != len(header):
            raise CommandError(
                f"{path}: row {first_row + offset} has {len(rec)} columns, expected {len(header)} "
                f"({', '.join(header)})."
            )
        rows.append({name: cell(value) for name, value in zip(header, rec)})
    return rows


class Command(BaseCommand):
    help = "Migrate a unit (journal, pages, nav, settings) from a legacy MySQL DB or export files into Janeway."

    def add_arguments(self, parser):
        parser.add_argument("unit_id", help="Legacy unit id; must equal the Janeway journal code.")

        db = parser.add_argument_group("live legacy database")
        db.add_argument("--db-name")
        db.add_argument("--db-host", default="localhost")
        db.add_argument("--db-port", default="3306")
        db.add_argument("--db-user")
        db.add_argument(
            "--db-password",
            default=os.environ.get("LEGACY_DB_PASSWORD", ""),
            help="Defaults to $LEGACY_DB_PASSWORD.",
        )

        files = parser.add_argument_group(
            "export files (alternative to a live database)",
            "Whole-table exports in .tsv, .csv, .json or .jsonl format; see the module docstring.",
        )
        files.add_argument("--units-file", help="Export of the units table (enables file mode).")
        files.add_argument("--pages-file", help="Export of the pages table (optional).")
        files.add_argument("--widgets-file", help="Export of the widgets table (optional).")
        for table in ("units", "pages", "widgets"):
            files.add_argument(
                f"--{table}-columns",
                help=f"Comma-separated column names if the {table} file has no header row.",
            )
        files.add_argument(
            "--tsv-dialect",
            choices=["mysql", "plain"],
            default="mysql",
            help="mysql (default): undo `mysql -B` / INTO OUTFILE escaping and read NULL/\\N as null. "
                 "plain: use TSV values exactly as written.",
        )

        parser.add_argument(
            "--assets-url-prefix",
            help="URL prefix under which legacy assets are served from S3; an asset is "
                 "fetched from <prefix>/<asset_id>. Needed for the header image and slide images.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run everything, then roll back the database changes (images are fetched to check they exist, but not saved).",
        )

    # ------------------------------------------------------------------ #
    # Entry point
    # ------------------------------------------------------------------ #
    def handle(self, *args, **opts):
        self.dry_run = opts["dry_run"]
        self.assets_url_prefix = opts["assets_url_prefix"]
        unit_id = opts["unit_id"]

        self.use_files = bool(opts["units_file"])
        if self.use_files:
            if opts["db_name"]:
                raise CommandError(
                    "Use either export files (--units-file ...) or a live database (--db-name ...), not both."
                )
            self.export_rows = self.load_exports(opts)
        else:
            if opts["pages_file"] or opts["widgets_file"]:
                raise CommandError("--pages-file / --widgets-file require --units-file.")
            if not (opts["db_name"] and opts["db_user"]):
                raise CommandError(
                    "Provide either --db-name and --db-user (live database) or --units-file (export files)."
                )
            self.configure_legacy_db(opts)

        try:
            with transaction.atomic():
                self.migrate(unit_id)
                if self.dry_run:
                    transaction.set_rollback(True)
                    self.stdout.write(self.style.WARNING("Dry run: changes rolled back."))
        finally:
            if not self.use_files and LEGACY_ALIAS in connections.databases:
                connections[LEGACY_ALIAS].close()

        self.stdout.write(self.style.SUCCESS(f"Finished migrating unit {unit_id}."))

    # ------------------------------------------------------------------ #
    # Legacy data access: live DB or export files
    # ------------------------------------------------------------------ #
    def configure_legacy_db(self, opts):
        connections.databases[LEGACY_ALIAS] = {
            "ENGINE": "django.db.backends.mysql",
            "NAME": opts["db_name"],
            "HOST": opts["db_host"],
            "PORT": opts["db_port"],
            "USER": opts["db_user"],
            "PASSWORD": opts["db_password"],
            "OPTIONS": {"charset": "utf8mb4"},
        }

    def fetch(self, sql, params):
        with connections[LEGACY_ALIAS].cursor() as cur:
            cur.execute(sql, params)
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def load_exports(self, opts):
        """Read every supplied export file up front so format problems fail before any writes."""
        tables = {}
        for table, spec in TABLES.items():
            path = opts[f"{table}_file"]
            if not path:
                self.stderr.write(self.style.WARNING(
                    f"No --{table}-file given; {table} will not be migrated."
                ))
                continue
            raw_columns = opts[f"{table}_columns"]
            columns = [c.strip() for c in raw_columns.split(",") if c.strip()] if raw_columns else None
            rows = load_export_file(path, columns=columns, dialect=opts["tsv_dialect"])

            if rows:
                missing = [c for c in spec["required"] if c not in rows[0]]
                if missing:
                    raise CommandError(
                        f"{path}: missing column(s) {', '.join(missing)}; "
                        f"found {', '.join(rows[0])}. "
                        f"If the file has no header row, pass --{table}-columns."
                    )
            tables[table] = rows
            self.stdout.write(f"Read {len(rows)} {table} rows from {path}.")
        return tables

    def fetch_table(self, table, unit_id):
        """All rows of `table` belonging to this unit, from the live DB or the export files."""
        spec = TABLES[table]
        if not self.use_files:
            return self.fetch(spec["sql"], [unit_id])
        rows = self.export_rows.get(table) or []
        return [r for r in rows if str(r.get(spec["key"])) == str(unit_id)]

    # ------------------------------------------------------------------ #
    # Migration steps
    # ------------------------------------------------------------------ #
    def migrate(self, unit_id):
        try:
            self.journal = Journal.objects.get(code=unit_id)
        except Journal.DoesNotExist:
            raise CommandError(f"No Janeway journal with code '{unit_id}'.")
        self.journal_ct = ContentType.objects.get_for_model(Journal)

        rows = self.fetch_table("units", unit_id)
        if not rows:
            where = "in the units export file" if self.use_files else "in the legacy database"
            raise CommandError(f"No unit with id '{unit_id}' {where}.")
        attrs = as_json(rows[0]["attrs"])

        self.migrate_journal(attrs)
        self.migrate_category(attrs)
        self.migrate_settings(attrs)
        self.migrate_pages(unit_id)
        self.migrate_nav(attrs.get("nav_bar") or [])
        self.migrate_widgets(unit_id)

    def migrate_journal(self, attrs):
        j = self.journal
        j.description = attrs.get("about", j.description)

        image = self.read_asset(attrs.get("logo"))
        if image and not self.dry_run:
            name, data = image
            j.header_image.save(name, ContentFile(data), save=False)

        j.save()
        self.stdout.write("Updated journal description / header image.")

    def asset_url(self, asset_id):
        prefix = self.assets_url_prefix
        return (prefix if prefix.endswith("/") else prefix + "/") + asset_id

    def read_asset(self, asset):
        """Download a legacy asset from S3. Returns (filename, bytes) or None.

        ``asset`` is a dict like {"asset_id": "<sha256>", "image_type": "png", ...}
        (or just the asset id string). The file is fetched from
        <assets-url-prefix>/<asset_id>. Failures are logged, not raised, so one
        missing image doesn't abort the whole import.
        """
        if not asset:
            return None
        if not self.assets_url_prefix:
            self.stderr.write("Image asset found but --assets-url-prefix not given; skipping.")
            return None

        if isinstance(asset, str):
            asset = {"asset_id": asset}
        asset_id = asset.get("asset_id")
        image_type = asset.get("image_type")
        if not asset_id:
            self.stderr.write(f"Asset has no asset_id: {asset}")
            return None

        url = self.asset_url(asset_id)
        try:
            with urlopen(url, timeout=ASSET_TIMEOUT) as response:
                data = response.read()
        except (URLError, OSError) as e:  # HTTPError is a URLError
            self.stderr.write(f"Could not fetch asset {url}: {e}")
            return None
        if not data:
            self.stderr.write(f"Asset {url} was empty; skipping.")
            return None

        # Short name: the full sha256 can overflow ImageField's max_length.
        ext = f".{image_type}" if image_type else ""
        return f"{asset_id[:16]}{ext}", data

    def get_media_file(self, asset, label):
        """Store a legacy asset as a Janeway core.File (what NewsItem.large_image_file needs).

        Returns None on dry runs or if the asset can't be read.
        """
        image = self.read_asset(asset)
        if not image or self.dry_run:
            return None
        name, data = image
        upload = SimpleUploadedFile(
            name, data, content_type=mimetypes.guess_type(name)[0] or "application/octet-stream"
        )
        f = MediaFile.objects.create(
            label=label,
            file=upload,
            journal=self.journal
        )
        return f

    def migrate_category(self, attrs):
        if attrs.get("is_undergrad"):
            category, _ = Category.objects.get_or_create(name="Undergrad")
            JournalCategory.objects.get_or_create(category=category, journal=self.journal)
            self.stdout.write("Assigned 'Undergrad' category.")

    def migrate_settings(self, attrs):
        for spec in SETTING_MAP:
            if attrs.get(spec["attr"]) is not None:
                raw = attrs[spec["attr"]]
            elif "default" in spec:
                raw = spec["default"]
            else:
                continue
            try:
                save_setting(
                    spec["group"],
                    spec["setting"],
                    self.journal,
                    to_setting_value(spec, raw),
                )
            except Exception as e:  # e.g. plugin setting not installed
                self.stderr.write(
                    f"Could not save {spec['group']}/{spec['setting']}: {e}"
                )

    def migrate_pages(self, unit_id):
        rows = self.fetch_table("pages", unit_id)
        for prow in rows:
            pattrs = as_json(prow.get("attrs"))
            Page.objects.update_or_create(
                content_type=self.journal_ct,
                object_id=self.journal.pk,
                name=prow["slug"],
                defaults={
                    "display_name": prow.get("title") or prow.get("name") or prow["slug"],
                    "content": pattrs.get("html", ""),
                    "is_draft": False,
                },
            )
        self.stdout.write(f"Migrated {len(rows)} pages.")

    # ------------------------------------------------------------------ #
    # Widgets -> homepage elements
    # ------------------------------------------------------------------ #
    def migrate_widgets(self, unit_id):
        rows = self.fetch_table("widgets", unit_id)
        count = 0
        seen_names = set()
        for wrow in rows:
            kind = wrow["kind"]
            wattrs = as_json(wrow.get("attrs"))
            has_config = True

            if kind == "Text":
                # NOTE: this setting is one value per journal, so a second
                # Text widget would overwrite the first.
                save_plugin_setting(
                    html_plugin.get_self(),
                    "html_block_content",
                    wattrs.get("html", ""),
                    self.journal,
                )
                template_path = "journal/homepage_elements/html_block.html"
                configure_url = "html_settings"

            elif kind == "RecentArticles":
                template_path = "recent_articles/recent_articles.html"
                configure_url = None
                has_config = False
            elif kind == "Carousel":
                carousel = self.get_carousel()
                slides = wattrs.get("slides") or []
                for seq, slide in enumerate(slides):
                    header = slide.get("header", f"Slide {seq + 1}")
                    defaults = {"text": slide.get("text", ""),
                                "header": header,
                                "image": self.get_media_file(slide.get("image"), header)}
                    MediaCarouselSlide.objects.update_or_create(
                        carousel=carousel,
                        order=seq,
                        defaults=defaults
                    )
                template_path = "media_carousel/media_carousel.html"
                configure_url = "media_carousel_config"

            else:
                self.stderr.write(
                    f"Unsupported widget kind '{kind}' (id {wrow['id']}, "
                    f"region '{wrow.get('region')}'); skipped."
                )
                continue

            name = wattrs.get("title") or WIDGET_LABELS[kind]
            if name in seen_names:
                name = f"{name} ({wrow['id']})"
            seen_names.add(name)

            HomepageElement.objects.update_or_create(
                content_type=self.journal_ct,
                object_id=self.journal.pk,
                name=name,
                defaults={
                    "template_path": template_path,
                    # Export files give strings; the DB driver gives ints.
                    "sequence": int(wrow["ordering"] or 0),
                    "configure_url": configure_url,
                    "has_config": has_config,
                    "active": True,
                },
            )
            count += 1
        self.stdout.write(f"Migrated {count} of {len(rows)} widgets.")

    def get_carousel(self):
        c, _ = MediaCarousel.objects.get_or_create(journal=self.journal)
        return c

    # ------------------------------------------------------------------ #
    # Navigation
    # ------------------------------------------------------------------ #
    def migrate_nav(self, items):
        for seq, item in enumerate(items):
            self.process_item(item, None, seq)

    def process_item(self, item, parent, sequence):
        if item.get("hidden", False):
            return None

        item_type = item.get("type")
        base = {
            "content_type": self.journal_ct,
            "object_id": self.journal.pk,
            "link_name": item["name"],
            "top_level_nav": parent,
        }

        if item_type == "link":
            if item["url"].startswith("/"):
                self.stderr.write(
                    f"Nav link '{item['name']}' is a legacy-relative URL ({item['url']}); "
                    "it will not resolve in Janeway."
                )
            nav, _ = NavigationItem.objects.update_or_create(
                **base,
                defaults={
                    "link": item["url"],
                    "is_external": True,
                    "has_sub_nav": False,
                    "sequence": sequence,
                },
            )

        elif item_type == "page":
            try:
                page = Page.objects.get(
                    content_type=self.journal_ct,
                    object_id=self.journal.pk,
                    name=item["slug"],
                )
            except Page.DoesNotExist:
                self.stderr.write(f"Nav item '{item['name']}': no page with slug '{item['slug']}'.")
                return None
            nav, _ = NavigationItem.objects.update_or_create(
                **base,
                defaults={
                    "page": page,
                    "link": f"{self.journal.code}/site/{page.name}/",
                    "is_external": False,
                    "has_sub_nav": False,
                    "sequence": sequence,
                },
            )

        elif item_type == "folder":
            nav, _ = NavigationItem.objects.update_or_create(
                **base,
                defaults={
                    "is_external": False,
                    "has_sub_nav": True,
                    "sequence": sequence,
                },
            )
            for sub_seq, sub in enumerate(item.get("sub_nav") or []):
                self.process_item(sub, nav, sub_seq)

        else:
            self.stderr.write(f"Unknown nav item type '{item_type}' ({item.get('name')}).")
            return None

        return nav