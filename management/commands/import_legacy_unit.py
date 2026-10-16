"""
Management command: import a unit from a legacy MySQL database into Janeway.

Place at: <some_app>/management/commands/import_legacy_unit.py
(each of management/ and management/commands/ needs an __init__.py)

Usage:
    python manage.py import_legacy_unit my_unit_id \
        --db-name legacy --db-user reader --db-password secret \
        --assets-url-prefix https://my-bucket.s3.amazonaws.com/assets/ --dry-run
"""
import json
import mimetypes
import os
from types import SimpleNamespace
from urllib.error import URLError
from urllib.request import urlopen

from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction

from cms.models import NavigationItem, Page
from comms.models import NewsItem
from core import files as core_files
from core.models import HomepageElement
from core.homepage_elements.carousel.models import Carousel
from journal.models import Journal
from plugins.health_dashboard.models import Category, JournalCategory
from utils.setting_handler import save_plugin_setting, save_setting

LEGACY_ALIAS = "legacy"
ASSET_TIMEOUT = 30  # seconds

# Parameterised (never string-format user input into SQL).
JOURNAL_Q = "SELECT * FROM units WHERE id = %s"
PAGE_Q = "SELECT * FROM pages WHERE unit_id = %s"
WIDGET_Q = "SELECT * FROM widgets WHERE unit_id = %s"  # not used yet

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
        "group": "plugin:doaj",
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


class Command(BaseCommand):
    help = "Migrate a unit (journal, pages, nav, settings) from a legacy MySQL DB into Janeway."

    def add_arguments(self, parser):
        parser.add_argument("unit_id", help="Legacy unit id; must equal the Janeway journal code.")
        parser.add_argument("--db-name", required=True)
        parser.add_argument("--db-host", default="localhost")
        parser.add_argument("--db-port", default="3306")
        parser.add_argument("--db-user", required=True)
        parser.add_argument(
            "--db-password",
            default=os.environ.get("LEGACY_DB_PASSWORD", ""),
            help="Defaults to $LEGACY_DB_PASSWORD.",
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

        self.configure_legacy_db(opts)

        try:
            with transaction.atomic():
                self.migrate(unit_id)
                if self.dry_run:
                    transaction.set_rollback(True)
                    self.stdout.write(self.style.WARNING("Dry run: changes rolled back."))
        finally:
            if LEGACY_ALIAS in connections.databases:
                connections[LEGACY_ALIAS].close()

        self.stdout.write(self.style.SUCCESS(f"Finished migrating unit {unit_id}."))

    # ------------------------------------------------------------------ #
    # Legacy DB access
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

    # ------------------------------------------------------------------ #
    # Migration steps
    # ------------------------------------------------------------------ #
    def migrate(self, unit_id):
        try:
            self.journal = Journal.objects.get(code=unit_id)
        except Journal.DoesNotExist:
            raise CommandError(f"No Janeway journal with code '{unit_id}'.")
        self.journal_ct = ContentType.objects.get_for_model(Journal)

        rows = self.fetch(JOURNAL_Q, [unit_id])
        if not rows:
            raise CommandError(f"No unit with id '{unit_id}' in the legacy database.")
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

    def get_core_file(self, asset, label):
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
        # save_file_to_journal only reads request.journal / request.user.
        fake_request = SimpleNamespace(journal=self.journal, user=None, press=None)
        return core_files.save_file_to_journal(fake_request, upload, label, "")

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
        rows = self.fetch(PAGE_Q, [unit_id])
        for prow in rows:
            pattrs = as_json(prow.get("attrs"))
            Page.objects.update_or_create(
                content_type=self.journal_ct,
                object_id=self.journal.pk,
                name=prow["slug"],
                defaults={
                    "display_name": prow.get("title") or prow["name"],
                    "content": pattrs.get("html", ""),
                },
            )
        self.stdout.write(f"Migrated {len(rows)} pages.")

    # ------------------------------------------------------------------ #
    # Widgets -> homepage elements
    # ------------------------------------------------------------------ #
    def migrate_widgets(self, unit_id):
        rows = self.fetch(WIDGET_Q, [unit_id])
        count = 0
        seen_names = set()
        for wrow in rows:
            kind = wrow["kind"]
            wattrs = as_json(wrow.get("attrs"))

            if kind == "Text":
                # NOTE: this setting is one value per journal, so a second
                # Text widget would overwrite the first.
                save_plugin_setting(
                    "homepage_element",
                    "html_block_content",
                    wattrs.get("html", ""),
                    self.journal,
                )
                template_path = "journal/homepage_elements/html_block.html"
                configure_url = "html_settings"

            elif kind == "RecentArticles":
                carousel = self.get_carousel()
                carousel.latest_articles = True
                carousel.article_limit = 5
                carousel.save()
                template_path = "journal/homepage_elements/carousel.html"
                configure_url = "carousel_settings"

            elif kind == "Carousel":
                carousel = self.get_carousel()
                slides = wattrs.get("slides") or []
                news_items = []
                for seq, slide in enumerate(slides):
                    defaults = {"body": slide.get("text", ""), "sequence": seq}
                    image = self.get_core_file(slide.get("image"), slide.get("header", "Slide"))
                    if image:
                        defaults["large_image_file"] = image
                    item, _ = NewsItem.objects.update_or_create(
                        content_type=self.journal_ct,
                        object_id=self.journal.pk,
                        title=slide.get("header", f"Slide {seq + 1}"),
                        defaults=defaults,
                    )
                    news_items.append(item)
                carousel.news_articles.set(news_items)
                carousel.news_limit = 5
                carousel.save()
                template_path = "journal/homepage_elements/carousel.html"
                configure_url = "carousel_settings"

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
                    "sequence": wrow["ordering"],
                    "configure_url": configure_url,
                    "has_config": True,
                    "active": True,
                },
            )
            count += 1
        self.stdout.write(f"Migrated {count} of {len(rows)} widgets.")

    def get_carousel(self):
        """One carousel per journal, shared by RecentArticles and Carousel widgets."""
        if self.journal.carousel is None:
            self.journal.carousel = Carousel.objects.create()
            self.journal.save()

        return self.journal.carousel

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
                    "link": page.name,
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
