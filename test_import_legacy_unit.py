"""
Tests for the import_legacy_unit management command.

Fixtures mirror the real 'westjem' rows. The legacy MySQL database is never
touched: Command.fetch is patched to return the fixture rows.

Run with:  python manage.py test <app>.tests.test_import_legacy_unit

Adjust COMMAND_MODULE to wherever you put the command.
"""
import base64
import importlib
import json
import tempfile
from io import StringIO
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings

from cms.models import NavigationItem, Page, MediaFile
from core.models import HomepageElement
from journal.models import Journal
from utils.testing import helpers

from plugins.media_carousel.models import MediaCarouselSlide, MediaCarousel

COMMAND_MODULE = "plugins.cdl_utils.management.commands.import_legacy_unit"
M = importlib.import_module(COMMAND_MODULE)

UNIT_ID = "westjem"
PREFIX = "https://bucket.s3.amazonaws.com/assets/"

# Valid 1x1 PNG so ImageField handling can't choke on fake bytes.
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

LOGO_ID = "466fe0e616c874b13314f93d549c0c56b1a3694c3091a0b967c8fbe27522d103"
SLIDE_IDS = [
    "ca67629cd44e2aa21ec7154168d1f51c80d6c2dce25e9fd20f04a23540f4394b",
    "83b08ca8482d59c1263dedadfabb4e21c2803789e8eb4bbd4f834cb4e39c31f5",
    "6c6917708659c1a8d4afc02ffc7faebc8fce4bb458a20d3f7b1ca64c1470a795",
    "3107d7927fc4b690753c228353d3d74e7e107de2473a09d22b7878015787e4bc",
]

# --------------------------------------------------------------------------- #
# Fixtures (taken from the real westjem rows; abridged "about" text)
# --------------------------------------------------------------------------- #
ABOUT = (
    '<p><em><a href="http://www.westjem.com">Western Journal of Emergency Medicine</a></em>'
    ": Integrating Emergency Care with Population Health</p>\n"
    "<p>Emergency Medicine is the specialty which most closely reflects societal "
    "challenges and consequences of public policy decisions.</p>"
)

NAV_BAR = [
    {"id": 22, "name": "Migration Notice", "slug": "migration", "type": "page", "hidden": True},
    {"id": 13, "name": "WestJEM", "type": "folder", "sub_nav": [
        {"id": 2, "url": "http://www.westjem.com", "name": "WestJEM Home", "type": "link"},
        {"id": 3, "url": "/uc/uciem_westjem/0/0", "name": "Articles In Press", "type": "link"},
        {"id": 20, "url": "https://westjem.com/wp-content/uploads/2013/03/2018-WestJEM-Media-Kit-1.pdf",
         "name": "Advertising", "type": "link"},
        {"id": 11, "url": "http://westjem.com/subscribe", "name": "Subscribe to WestJEM", "type": "link"},
    ]},
    {"id": 16, "name": "Submission", "type": "folder", "sub_nav": [
        {"id": 17, "url": "http://westjem.com/article-processing-fee",
         "name": "Article Processing Fee", "type": "link"},
        {"id": 4, "url": "http://westjem.com/submission-guidelines",
         "name": "Submission Guidelines", "type": "link"},
        {"id": 18, "url": "http://westjem.com/submission-requirements",
         "name": "Submission Conditions of Acceptance", "type": "link"},
        {"id": 21, "url": "https://publicationethics.org/files/retraction%20guidelines_0.pdf",
         "name": "Retraction Guidelines", "type": "link"},
    ]},
    {"id": 15, "name": "Reviewers & Editors", "type": "folder", "sub_nav": [
        {"id": 7, "url": "http://westjem.com/peer-review-policy", "name": "Reviewer", "type": "link"},
        {"id": 8, "url": "http://www.annemergmed.com/pb/assets/raw/Health%20Advance/journals/ymem/index.html",
         "name": "Peer Review Training Module", "type": "link"},
        {"id": 19, "url": "http://westjem.com/section-editor-requirements",
         "name": "Section Editor Requirements", "type": "link"},
        {"id": 10, "url": "http://westjem.com/editors-editorial-board",
         "name": "Editorial Board", "type": "link"},
    ]},
    {"id": 1, "name": "About", "type": "folder", "sub_nav": [
        {"id": 5, "url": "http://westjem.com/copyright", "name": "Copyright", "type": "link"},
        {"id": 6, "name": "Journal Policies", "slug": "journal_policies", "type": "page"},
        {"id": 9, "url": "http://westjem.com/indexing-information-2",
         "name": "Indexing Information", "type": "link"},
    ]},
    {"id": 12, "name": "Contact Us", "slug": "contactus", "type": "page"},
]

ATTRS = {
    "issn": "1936-900X",
    "eissn": "1936-9018",
    "logo": {"width": 675, "height": 75, "asset_id": LOGO_ID, "is_banner": True, "image_type": "png"},
    "about": ABOUT,
    "indexed": ["doaj", "scopus"],
    "nav_bar": NAV_BAR,
    "pub_freq": "incremental",
    "altmetrics_ok": True,
    "carousel": True,
    "twitter": "westjem",
    "doaj": True,
}

SLIDES = [
    {"header": "CALL FOR SECTION EDITORS", "text": "<p>Currently looking for Editors in:&nbsp;</p>",
     "image": {"width": 899, "height": 318, "asset_id": SLIDE_IDS[0], "image_type": "gif"}},
    {"header": "CALL FOR REVIEWERS", "text": "<p>to <strong>editor@westjem.org</strong></p>",
     "image": {"width": 900, "height": 318, "asset_id": SLIDE_IDS[1], "image_type": "gif"}},
    {"header": "Advertising", "text": '<p>Click <a href="http://westjem.com/media-kit.pdf">here</a></p>',
     "image": {"width": 900, "height": 318, "asset_id": SLIDE_IDS[2], "image_type": "gif"}},
    {"header": "ARTICLES IN PRESS", "text": "<p>See the articles before publication</p>",
     "image": {"width": 713, "height": 338, "asset_id": SLIDE_IDS[3], "image_type": "jpeg"}},
]


def unit_row(attrs=None):
    return {
        "id": UNIT_ID,
        "name": "Western Journal of Emergency Medicine",
        "type": "journal",
        "status": "active",
        "attrs": json.dumps(ATTRS if attrs is None else attrs),
    }


PAGE_ROWS = [
    {"id": 9802, "unit_id": UNIT_ID, "name": "Contact Us", "title": "Contact Us", "slug": "contactus",
     "attrs": json.dumps({"html": '<h2><em>West</em>JEM Submissions</h2><p><a href="mailto:editor@westjem.org">'
                                  "editor@westjem.org</a></p>"})},
    {"id": 9801, "unit_id": UNIT_ID, "name": "Journal Policies", "title": "Consent",
     "slug": "journal_policies",
     "attrs": json.dumps({"html": '<p><a href="http://westjem.com/conflicts-interest">Conflicts of Interest</a></p>'})},
    {"id": 13126, "unit_id": UNIT_ID, "name": "Migration Notice", "title": "Migration Notice",
     "slug": "migration",
     "attrs": json.dumps({"html": "<p>eScholarship Publishing is currently migrating WestJEM.</p>"})},
]

WIDGET_ROWS = [
    {"id": 5048, "unit_id": UNIT_ID, "kind": "RecentArticles", "ordering": 2,
     "attrs": "{}", "region": "sidebar"},
    {"id": 5994, "unit_id": UNIT_ID, "kind": "Carousel", "ordering": 0,
     "attrs": json.dumps({"slides": SLIDES}), "region": "marquee"},
    {"id": 6413, "unit_id": UNIT_ID, "kind": "TwitterFeed", "ordering": 1,
     "attrs": json.dumps({"title": "Follow Us On Twitter", "twitter_handle": "westjem"}),
     "region": "sidebar"},
]


def make_urlopen(files):
    """Fake urlopen: ``files`` maps URL -> bytes; anything else is a 404."""
    requested = []

    def fake(url, timeout=None):
        requested.append(url)
        if url not in files:
            raise HTTPError(url, 404, "Not Found", {}, None)
        response = MagicMock()
        response.__enter__.return_value.read.return_value = files[url]
        return response

    fake.requested = requested
    return fake


# --------------------------------------------------------------------------- #
# Pure helper tests (no DB)
# --------------------------------------------------------------------------- #
class HelperTests(SimpleTestCase):
    def test_as_json_accepts_str_bytes_dict_and_empty(self):
        self.assertEqual(M.as_json('{"a": 1}'), {"a": 1})
        self.assertEqual(M.as_json(b'{"a": 1}'), {"a": 1})
        self.assertEqual(M.as_json({"a": 1}), {"a": 1})
        self.assertEqual(M.as_json(None), {})
        self.assertEqual(M.as_json(""), {})

    def test_as_json_roundtrips_escaped_html(self):
        # The mysql CLI shows quotes as \\" in batch mode; the real column holds \".
        raw = json.dumps({"about": '<a href="x">y</a>'})
        self.assertEqual(M.as_json(raw)["about"], '<a href="x">y</a>')

    def test_to_setting_value_bool(self):
        spec = {"type": "bool"}
        for truthy in (True, "on", "true", "1", "yes"):
            self.assertEqual(M.to_setting_value(spec, truthy), "on")
        for falsy in (False, "off", "false", "", None):
            self.assertEqual(M.to_setting_value(spec, falsy), "")

    def test_to_setting_value_string(self):
        self.assertEqual(M.to_setting_value({}, "incremental"), "incremental")
        self.assertEqual(M.to_setting_value({}, None), "")

class ReadAssetTests(SimpleTestCase):
    def setUp(self):
        self.cmd = M.Command()
        self.cmd.stderr = StringIO()
        self.cmd.assets_url_prefix = PREFIX

    def read(self, asset, files):
        fake = make_urlopen(files)
        with patch.object(M, "urlopen", fake):
            return self.cmd.read_asset(asset), fake.requested

    def test_downloads_from_prefix_plus_asset_id(self):
        result, requested = self.read(
            {"asset_id": LOGO_ID, "image_type": "png"},
            {PREFIX + LOGO_ID: b"png-bytes"}
        )
        self.assertEqual(result, (f"{LOGO_ID[:16]}.png", b"png-bytes"))
        self.assertEqual(requested, [PREFIX + LOGO_ID])

    def test_prefix_without_trailing_slash_is_normalised(self):
        self.cmd.assets_url_prefix = PREFIX.rstrip("/")
        result, requested = self.read({"asset_id": LOGO_ID}, {PREFIX + LOGO_ID: b"x"})
        self.assertIsNotNone(result)
        self.assertEqual(requested, [PREFIX + LOGO_ID])

    def test_accepts_bare_asset_id_string(self):
        result, _ = self.read(LOGO_ID, {PREFIX + LOGO_ID: b"x"})
        self.assertEqual(result, (LOGO_ID[:16], b"x"))

    def test_http_error_returns_none_and_warns(self):
        result, _ = self.read({"asset_id": LOGO_ID, "image_type": "png"}, {})
        self.assertIsNone(result)
        self.assertIn("Could not fetch", self.cmd.stderr.getvalue())
        self.assertIn("404", self.cmd.stderr.getvalue())

    def test_empty_download_returns_none(self):
        result, _ = self.read({"asset_id": LOGO_ID}, {PREFIX + LOGO_ID: b""})
        self.assertIsNone(result)
        self.assertIn("empty", self.cmd.stderr.getvalue())

    def test_no_prefix_returns_none_without_fetching(self):
        self.cmd.assets_url_prefix = None
        result, requested = self.read({"asset_id": LOGO_ID}, {})
        self.assertIsNone(result)
        self.assertEqual(requested, [])
        self.assertIn("--assets-url-prefix", self.cmd.stderr.getvalue())

    def test_asset_without_id_returns_none(self):
        result, requested = self.read({"image_type": "png"}, {})
        self.assertIsNone(result)
        self.assertEqual(requested, [])

    def test_empty_asset_returns_none(self):
        self.assertIsNone(self.cmd.read_asset(None))
        self.assertIsNone(self.cmd.read_asset({}))


# --------------------------------------------------------------------------- #
# Command tests (Janeway DB, legacy DB mocked)
# --------------------------------------------------------------------------- #
class ImportLegacyUnitTests(TestCase):
    def setUp(self):
        self.journal, _ = helpers.create_journals()
        self.journal.code = UNIT_ID
        self.journal.save()
        self.ct = ContentType.objects.get_for_model(Journal)

        self.unit_rows = [unit_row()]
        self.page_rows = PAGE_ROWS
        self.widget_rows = WIDGET_ROWS

        def fake_fetch(cmd, sql, params):
            return {
                M.JOURNAL_Q: self.unit_rows,
                M.PAGE_Q: self.page_rows,
                M.WIDGET_Q: self.widget_rows,
            }[sql]

        for patcher in (
            patch.object(M.Command, "configure_legacy_db", lambda cmd, opts: None),
            patch.object(M.Command, "fetch", fake_fetch),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

        p1 = patch.object(M, "save_setting")
        p2 = patch.object(M, "save_plugin_setting")
        self.save_setting = p1.start()
        self.save_plugin_setting = p2.start()
        self.addCleanup(p1.stop)
        self.addCleanup(p2.stop)

    # -- helpers ----------------------------------------------------------- #
    def run_command(self, *extra, unit_id=UNIT_ID):
        out, err = StringIO(), StringIO()
        call_command(
            "import_legacy_unit", unit_id, "--db-name", "x", "--db-user", "u", *extra,
            stdout=out, stderr=err,
        )
        return out.getvalue(), err.getvalue()

    def scoped(self, model):
        return model.objects.filter(content_type=self.ct, object_id=self.journal.pk)

    def settings_saved(self):
        return {(c[0][0], c[0][1]): c[0][3] for c in self.save_setting.call_args_list}

    # -- journal ----------------------------------------------------------- #
    def test_description_is_set_from_about(self):
        self.run_command()
        self.journal.refresh_from_db()
        self.assertEqual(self.journal.description, ABOUT)

    def test_unknown_journal_raises(self):
        with self.assertRaisesMessage(CommandError, "No Janeway journal"):
            self.run_command(unit_id="nope")

    def test_unknown_unit_raises(self):
        self.unit_rows = []
        with self.assertRaisesMessage(CommandError, "No unit with id"):
            self.run_command()

    # -- settings ---------------------------------------------------------- #
    def test_settings_mapped_from_westjem_attrs(self):
        self.run_command()
        self.assertEqual(self.settings_saved(), {
            ("article", "display_altmetric_badge"): "on",
            ("plugin", "doaj_publish_push"): "on",
            ("general", "journal_issn"): "1936-9018",    # eissn
            ("general", "print_issn"): "1936-900X",      # issn
            ("plugin:health_dashboard", "publication_frequency"): "incremental",
        })

    def test_settings_use_defaults_and_skip_missing_optional_attrs(self):
        self.unit_rows = [unit_row({"about": "x"})]
        self.run_command()
        saved = self.settings_saved()
        self.assertEqual(saved[("article", "display_altmetric_badge")], "on")
        self.assertEqual(saved[("plugin", "doaj_publish_push")], "")
        self.assertNotIn(("general", "journal_issn"), saved)
        self.assertNotIn(("general", "print_issn"), saved)

    def test_explicit_false_overrides_default(self):
        self.unit_rows = [unit_row({"altmetrics_ok": False})]
        self.run_command()
        self.assertEqual(self.settings_saved()[("article", "display_altmetric_badge")], "")

    def test_setting_failure_is_reported_not_raised(self):
        self.save_setting.side_effect = Exception("no such setting")
        _, err = self.run_command()
        self.assertIn("Could not save", err)

    # -- pages ------------------------------------------------------------- #
    def test_pages_created_with_html_from_attrs(self):
        self.run_command()
        pages = {p.name: p for p in self.scoped(Page)}
        self.assertEqual(set(pages), {"contactus", "journal_policies", "migration"})
        self.assertIn("editor@westjem.org", pages["contactus"].content)
        self.assertEqual(pages["journal_policies"].display_name, "Consent")
        self.assertIn("Conflicts of Interest", pages["journal_policies"].content)

    def test_page_display_name_falls_back_to_name(self):
        self.page_rows = [dict(PAGE_ROWS[0], title=None)]
        self.run_command()
        self.assertEqual(self.scoped(Page).get(name="contactus").display_name, "Contact Us")

    # -- navigation -------------------------------------------------------- #
    def test_top_level_nav_skips_hidden_and_preserves_order(self):
        self.run_command()
        top = self.scoped(NavigationItem).filter(top_level_nav=None).order_by("sequence")
        self.assertEqual(
            [n.link_name for n in top],
            ["WestJEM", "Submission", "Reviewers & Editors", "About", "Contact Us"],
        )
        self.assertFalse(self.scoped(NavigationItem).filter(link_name="Migration Notice").exists())

    def test_folders_have_sub_nav_and_children(self):
        self.run_command()
        about = self.scoped(NavigationItem).get(link_name="About")
        self.assertTrue(about.has_sub_nav)
        children = NavigationItem.objects.filter(top_level_nav=about).order_by("sequence")
        self.assertEqual(
            [c.link_name for c in children],
            ["Copyright", "Journal Policies", "Indexing Information"],
        )

    def test_page_nav_item_points_at_page(self):
        self.run_command()
        nav = self.scoped(NavigationItem).get(link_name="Journal Policies")
        self.assertEqual(nav.page, self.scoped(Page).get(name="journal_policies"))
        self.assertFalse(nav.is_external)

    def test_link_nav_items_are_external(self):
        self.run_command()
        nav = self.scoped(NavigationItem).get(link_name="Copyright")
        self.assertTrue(nav.is_external)
        self.assertEqual(nav.link, "http://westjem.com/copyright")

    def test_relative_legacy_link_triggers_warning(self):
        _, err = self.run_command()
        self.assertIn("/uc/uciem_westjem/0/0", err)

    def test_page_nav_with_unknown_slug_is_skipped_with_warning(self):
        self.unit_rows = [unit_row(dict(ATTRS, nav_bar=[
            {"id": 1, "name": "Ghost", "slug": "ghost", "type": "page"}]))]
        _, err = self.run_command()
        self.assertIn("ghost", err)
        self.assertFalse(self.scoped(NavigationItem).filter(link_name="Ghost").exists())

    # -- widgets ----------------------------------------------------------- #
    def test_homepage_elements_created_for_supported_widgets(self):
        self.run_command()
        elements = {e.name: e for e in self.scoped(HomepageElement)}
        self.assertEqual(set(elements), {"Carousel", "Recent Articles"})
        self.assertEqual(elements["Carousel"].sequence, 0)
        self.assertEqual(elements["Carousel"].template_path, "media_carousel/media_carousel.html")
        self.assertEqual(elements["Carousel"].configure_url, "media_carousel_config")
        self.assertTrue(elements["Carousel"].has_config)
        self.assertEqual(elements["Recent Articles"].sequence, 2)
        self.assertEqual(elements["Recent Articles"].template_path, "recent_articles/recent_articles.html")
        self.assertFalse(elements["Recent Articles"].has_config)

    def test_unsupported_widget_is_reported_and_skipped(self):
        _, err = self.run_command()
        self.assertIn("TwitterFeed", err)
        self.assertFalse(self.scoped(HomepageElement).filter(name__icontains="twitter").exists())

    def test_carousel_slides(self):
        self.run_command()
        items = self.journal.media_carousel.mediacarouselslide_set.all()
        self.assertEqual([i.header for i in items], [s["header"] for s in SLIDES])
        self.assertEqual([i.order for i in items], [0, 1, 2, 3])
        self.assertIn("Currently looking for Editors", items[0].text)

    def test_carousel_slides(self):
        self.run_command()
        self.journal.refresh_from_db()
        carousel = self.journal.media_carousel
        self.assertEqual(carousel.mediacarouselslide_set.count(), 4)

    def test_text_widget_saves_html_block_from_attrs(self):
        self.widget_rows = [{"id": 1, "unit_id": UNIT_ID, "kind": "Text", "ordering": 0,
                             "attrs": json.dumps({"html": "<p>Hello</p>"}), "region": "main"}]
        self.run_command()
        self.save_plugin_setting.assert_called_once_with(
            None, "html_block_content", "<p>Hello</p>", self.journal)
        element = self.scoped(HomepageElement).get()
        self.assertEqual(element.name, "Text Block")
        self.assertEqual(element.configure_url, "html_settings")

    def test_duplicate_widget_names_are_disambiguated(self):
        self.widget_rows = [
            {"id": 1, "unit_id": UNIT_ID, "kind": "Text", "ordering": 0,
             "attrs": json.dumps({"html": "a"}), "region": "main"},
            {"id": 2, "unit_id": UNIT_ID, "kind": "Text", "ordering": 1,
             "attrs": json.dumps({"html": "b"}), "region": "main"},
        ]
        self.run_command()
        self.assertEqual(
            set(self.scoped(HomepageElement).values_list("name", flat=True)),
            {"Text Block", "Text Block (2)"},
        )

    # -- images ------------------------------------------------------------ #
    def test_header_image_and_slide_images_are_imported(self):
        files = {PREFIX + LOGO_ID: PNG_1X1}
        files.update({PREFIX + i: b"GIF89afake" for i in SLIDE_IDS})
        fake = make_urlopen(files)

        with tempfile.TemporaryDirectory() as media, \
                override_settings(MEDIA_ROOT=media), \
                patch.object(M, "urlopen", fake):
            self.run_command("--assets-url-prefix", PREFIX)

            self.journal.refresh_from_db()
            self.assertIsNotNone(self.journal.header_image)

        self.assertEqual(fake.requested, [PREFIX + LOGO_ID] + [PREFIX + i for i in SLIDE_IDS])
        self.assertEqual(MediaFile.objects.filter(journal=self.journal).count(), 4)
        uploaded = [str(x) for x in MediaFile.objects.filter(journal=self.journal).values_list('file', flat=True)]
        self.assertEqual(
            uploaded,
            [f"journals/17/{SLIDE_IDS[0][:16]}.gif", f"journals/17/{SLIDE_IDS[1][:16]}.gif",
             f"journals/17/{SLIDE_IDS[2][:16]}.gif", f"journals/17/{SLIDE_IDS[3][:16]}.jpeg"],
        )

    def test_failed_download_does_not_abort_import(self):
        # Logo 404s; slides still import (without images).
        with patch.object(M, "urlopen", make_urlopen({})):
            _, err = self.run_command("--assets-url-prefix", PREFIX)
        self.assertIn("Could not fetch", err)
        self.assertEqual(self.journal.media_carousel.mediacarouselslide_set.count(), 4)
        self.assertEqual(self.scoped(Page).count(), 3)

    def test_dry_run_fetches_images_but_saves_nothing(self):
        fake = make_urlopen({PREFIX + LOGO_ID: PNG_1X1})
        with patch.object(M, "urlopen", fake), \
                patch.object(M.core_files, "save_file_to_journal") as save_file:
            self.run_command("--assets-url-prefix", PREFIX, "--dry-run")
        self.assertIn(PREFIX + LOGO_ID, fake.requested)
        save_file.assert_not_called()
        self.journal.refresh_from_db()
        self.assertFalse(self.journal.header_image)

    def test_missing_prefix_does_not_abort_import(self):
        _, err = self.run_command()  # no --assets-url-prefix
        self.assertIn("--assets-url-prefix", err)
        self.assertEqual(self.journal.media_carousel.mediacarouselslide_set.count(), 4)

    # -- idempotency / dry run -------------------------------------------- #
    def test_running_twice_creates_no_duplicates(self):
        self.run_command()
        counts = {m: self.scoped(m).count() for m in (Page, NavigationItem, HomepageElement)}
        slide_count = MediaCarouselSlide.objects.filter(carousel__journal=self.journal).count()
        self.run_command()
        self.assertEqual(
            counts,
            {m: self.scoped(m).count() for m in (Page, NavigationItem, HomepageElement)},
        )
        self.assertEqual(slide_count, MediaCarouselSlide.objects.filter(carousel__journal=self.journal).count())
        self.assertEqual(MediaCarousel.objects.all().count(), 1)
        self.journal.refresh_from_db()
        self.assertIsNotNone(self.journal.media_carousel)

    def test_dry_run_rolls_back_everything(self):
        original_description = self.journal.description
        out, _ = self.run_command("--dry-run")
        self.assertIn("Dry run", out)
        for model in (Page, NavigationItem, HomepageElement):
            self.assertEqual(self.scoped(model).count(), 0, model.__name__)
        self.assertEqual(MediaCarousel.objects.all().count(), 0)
        self.assertEqual(MediaCarouselSlide.objects.filter(carousel__journal=self.journal).count(), 0)
        self.journal.refresh_from_db()
        self.assertEqual(self.journal.description, original_description)
