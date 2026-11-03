import copy
import io
import json
import os
import shutil
import socket
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw

from noxart.common import file_hash, load_games, read_json, safe_path, write_json
from noxart.fetching import fetch
from noxart.http import AuthenticationError, DownloadError, HttpClient
from noxart.imaging import inspect_source, save_png, square_image, validate_png
from noxart.matching import normalize, resolve
from noxart.pipeline import generate
from noxart.release import manifest, package, prepare_public, validate
from noxart.reporting import reports
from noxart.selection import ranked
from noxart.individual import individual_index
from noxart.queue import eligible, record
from datetime import datetime, timedelta, timezone
from noxart.http import RateLimitError
from scripts.import_us_discs import import_catalog
from providers.steamgriddb import ResponseError, SteamGridDB
from scripts.import_games import import_games
from scripts.review_artwork import approve

REPO = Path(__file__).resolve().parents[1]
GAME = {"title_id": "BCUS98111", "title": "God of War III", "platform": "PS3", "region": "US", "release_year": 2010}
API_GAME = {"id": 12, "name": "God of War III", "release_date": 1268697600}


class Fixture(unittest.TestCase):
    def setUp(self):
        # All test data lives under the workspace; compatible with constrained hosts.
        base = REPO / ".cache/tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copy(REPO / "config.json", self.root / "config.json")
        self.config = read_json(self.root / "config.json")
        self.config["publication"] = {"steamgriddb_with_attribution": False}
        write_json(self.root / "config.json", self.config)
        write_json(self.root / "database/games.json", [GAME])
        self.image = Image.new("RGB", (512, 512), (30, 40, 70))
        ImageDraw.Draw(self.image).rectangle((20, 100, 400, 300), fill=(180, 100, 20))
        self.buffer = io.BytesIO()
        self.image.save(self.buffer, format="PNG")

    def row(self, ident=100, size=512, **extra):
        return {"id": ident, "width": size, "height": size, "url": f"https://cdn2.steamgriddb.com/{ident}.png",
                "score": 10, "author": {"name": "Test artist"}, **extra}

    def api(self, rows=None):
        api = Mock()
        api.search.return_value = [API_GAME]
        api.game.return_value = API_GAME
        api.grids.side_effect = lambda ident, size: (rows if rows is not None else [self.row()]) if size == 512 else []
        return api

    def fetch(self, api=None, **kwargs):
        client = Mock()
        client.get.return_value = self.buffer.getvalue()
        with patch("noxart.fetching.SteamGridDB", return_value=api or self.api()):
            result = fetch(self.root, client=client, **kwargs)
        return result, client

    def build(self):
        self.fetch()
        generate(self.root)
        return read_json(self.root / "database/games.json")[0]


class MatchingTests(Fixture):
    def test_normalization(self):
        self.assertEqual(normalize("God of War™ III"), "god of war 3")
        self.assertEqual(normalize("  Résumé & Me: II "), "resume and me 2")

    def test_unique_exact_match_is_not_first_result(self):
        api = self.api()
        api.search.return_value = [{"id": 99, "name": "God of War III Remastered"}, API_GAME]
        result, suggestions = resolve(GAME, api)
        self.assertEqual(result["game_id"], 12)
        self.assertEqual(suggestions, [])

    def test_ambiguous_exact_names_require_review(self):
        api = self.api()
        api.search.return_value = [API_GAME, {**API_GAME, "id": 13}]
        api.game.side_effect = lambda ident: {**API_GAME, "id": ident}
        result, suggestions = resolve(GAME, api)
        self.assertIsNone(result)
        self.assertEqual(len(suggestions), 2)

    def test_remaster_and_wrong_year_not_accepted(self):
        api = self.api()
        api.game.return_value = {**API_GAME, "release_date": 1436918400}
        self.assertIsNone(resolve(GAME, api)[0])
        api.search.return_value = [{"id": 13, "name": "God of War III Remastered"}]
        self.assertIsNone(resolve(GAME, api)[0])

    def test_alternate_title_and_manual_mapping(self):
        api = self.api()
        result, _ = resolve({**GAME, "title": "Regional title", "alternate_titles": ["God of War III"]}, api)
        self.assertEqual(result["game_id"], 12)
        result, _ = resolve({**GAME, "title": "Regional title", "steamgriddb_game_id": 12, "mapping_approved": True}, api)
        self.assertEqual(result["confidence"], "manual")

    def test_empty_search_is_missing(self):
        api = self.api()
        api.search.return_value = []
        self.assertEqual(resolve(GAME, api), (None, []))


class APITests(Fixture):
    def test_missing_secret_fails_without_printing_key(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(AuthenticationError, "missing"):
            SteamGridDB(Mock())

    def test_response_validation(self):
        client = Mock()
        api = SteamGridDB(client, "dummy")
        for response in ({"success": False}, {"success": True, "data": {}}, {"success": True, "data": ["bad"]}):
            client.json.return_value = response
            with self.assertRaises(ResponseError):
                api.search("God of War III")

    def test_encoding_auth_and_filters(self):
        client = Mock()
        client.json.return_value = {"success": True, "data": []}
        api = SteamGridDB(client, "dummy")
        api.search("Ratchet & Clank")
        self.assertIn("Ratchet%20%26%20Clank", client.json.call_args.args[0])
        self.assertEqual(client.json.call_args.args[2], {"Authorization": "Bearer dummy"})
        api.grids(12, 512)
        url = client.json.call_args.args[0]
        for term in ("dimensions=512x512", "types=static", "nsfw=false", "humor=false", "epilepsy=false"):
            self.assertIn(term, url)


class SelectionTests(Fixture):
    def test_512_precedes_higher_scored_1024(self):
        self.assertEqual(ranked([self.row(2, 1024, score=100), self.row(1, score=1)])[0]["id"], 1)

    def test_unsafe_rectangular_animated_and_flagged_rejected(self):
        rows = [self.row(1, nsfw=True), self.row(2, humor=True), self.row(3, epilepsy=True),
                self.row(4, height=900), self.row(5, mime="image/gif"), self.row(6, animated=True), self.row(7)]
        self.assertEqual([r["id"] for r in ranked(rows)], [7])


class PipelineTests(Fixture):
    def test_512_download_and_pixels_preserved(self):
        entry = self.build()
        output = self.root / "art" / entry["artwork"]
        with Image.open(output) as image:
            self.assertEqual(image.tobytes(), self.image.tobytes())
        self.assertEqual(entry["processing_method"], "native-square")
        validate(self.root)

    def test_1024_fallback_downscales(self):
        large = self.image.resize((1024, 1024))
        self.buffer = io.BytesIO()
        large.save(self.buffer, format="JPEG")
        api = self.api()
        api.grids.side_effect = lambda ident, size: [] if size == 512 else [self.row(size=1024)]
        self.fetch(api)
        generate(self.root)
        entry = read_json(self.root / "database/games.json")[0]
        self.assertEqual(entry["processing_method"], "downscale-square")
        validate_png(self.root / "art" / entry["artwork"], 512, self.config)

    def test_empty_grids_generate_missing_report(self):
        result, _ = self.fetch(self.api([]))
        self.assertEqual(result[-1]["status"], "missing_square")
        generate(self.root)
        reports(self.root)
        self.assertEqual(len(read_json(self.root / "reports/missing_artwork.json")), 1)

    def test_download_failure_is_nonfatal(self):
        client = Mock()
        client.get.side_effect = DownloadError("timeout")
        with patch("noxart.fetching.SteamGridDB", return_value=self.api()):
            result = fetch(self.root, client=client)
        self.assertEqual(result[-1]["status"], "missing_square")

    def test_programming_and_auth_errors_are_fatal(self):
        api = self.api()
        for error in (AuthenticationError("bad key"), TypeError("bug"), ResponseError("bad schema")):
            api.search.side_effect = error
            with self.subTest(error=type(error)), patch("noxart.fetching.SteamGridDB", return_value=api), self.assertRaises(type(error)):
                fetch(self.root, client=Mock())

    def test_actual_dimensions_must_match(self):
        api = self.api([self.row(size=512)])
        self.buffer = io.BytesIO()
        self.image.resize((1024, 1024)).save(self.buffer, format="PNG")
        result, _ = self.fetch(api)
        self.assertEqual(result[0]["status"], "candidate_rejected")

    def test_manual_asset_selection(self):
        self.config["overrides"] = {"BCUS98111": {"asset_id": 101}}
        write_json(self.root / "config.json", self.config)
        result, _ = self.fetch(self.api([self.row(100), self.row(101, score=1)]))
        self.assertEqual(result[-1]["asset_id"], 101)

    def test_existing_approved_output_never_overwritten(self):
        before = self.build()
        approve(self.root, ["BCUS98111"])
        api = self.api()
        self.fetch(api)
        api.search.assert_not_called()
        generate(self.root)
        after = read_json(self.root / "database/games.json")[0]
        self.assertEqual(before["sha256"], after["sha256"])
        self.assertEqual(after["review_status"], "approved")

    def test_cache_avoids_duplicate_download(self):
        self.fetch()
        _, client = self.fetch()
        client.get.assert_not_called()

    def test_public_pack_excludes_unverified_and_private_pack_requires_review(self):
        self.build()
        path = package(self.root)
        with zipfile.ZipFile(path) as archive:
            self.assertFalse(any(n.endswith(".png") for n in archive.namelist()))
        path = package(self.root, private=True)
        with zipfile.ZipFile(path) as archive:
            self.assertFalse(any(n.endswith(".png") for n in archive.namelist()))
        approve(self.root, ["BCUS98111"])
        path = package(self.root, private=True)
        with zipfile.ZipFile(path) as archive:
            self.assertIn("art/BCUS98111.png", archive.namelist())
        self.assertEqual(manifest(self.root)["games"], {})

    def test_approved_manifest_real_hashes_and_reproducible_zip(self):
        entry = self.build()
        games = read_json(self.root / "database/games.json")
        games[0]["source"].update(redistribution="approved", license="Test fixture", permission_evidence="Original synthetic fixture")
        write_json(self.root / "database/games.json", games)
        approve(self.root, ["BCUS98111"])
        index = manifest(self.root)
        self.assertEqual(index["games"]["BCUS98111"]["asset_id"], 100)
        self.assertEqual(index["games"]["BCUS98111"]["sha256"], entry["sha256"])
        first = package(self.root).read_bytes()
        self.assertEqual(first, package(self.root).read_bytes())
        index = individual_index(self.root)
        entry = index["games"]["BCUS98111"]
        self.assertEqual(entry["artwork"], "art/BCUS98111.png")
        self.assertTrue(entry["download_url"].endswith("/main/art/BCUS98111.png"))
        self.assertEqual(entry["sha256"], file_hash(self.root / entry["artwork"]))

    def test_individual_index_has_no_broken_public_links(self):
        self.build()
        prepare_public(self.root)
        index = individual_index(self.root)
        self.assertIsNone(index["games"]["BCUS98111"]["download_url"])
        self.assertIn("steamgriddb.com", index["games"]["BCUS98111"]["source_url"])

    def test_prepare_public_keeps_metadata_removes_image(self):
        self.build()
        prepare_public(self.root)
        validate(self.root)
        self.assertFalse((self.root / "art/BCUS98111.png").exists())
        reports(self.root)
        self.assertIn("cdn2.steamgriddb.com", (self.root / "reports/contact-sheet.html").read_text())

    def test_same_verified_identity_and_asset_create_explicit_alias(self):
        write_json(self.root / "database/games.json", [GAME, {**GAME, "title_id": "BCES00510"}])
        self.fetch()
        generate(self.root)
        games = validate(self.root)
        self.assertEqual(games[1]["shared_with"], "BCUS98111")

    def test_unrelated_duplicate_output_is_queued_for_review(self):
        self.build()
        games = read_json(self.root / "database/games.json")
        second = copy.deepcopy(games[0])
        second.update(title_id="BLUS99999", title="Unrelated game", artwork_status="missing", steamgriddb_game_id=99)
        for key in ("artwork", "thumbnail", "sha256", "thumbnail_sha256"):
            second.pop(key, None)
        games.append(second)
        write_json(self.root / "database/games.json", games)
        generate(self.root)
        games = validate(self.root)
        self.assertEqual(games[1]["fetch_state"]["status"], "duplicate_review")

    def test_verified_region_alias(self):
        write_json(self.root / "database/games.json", [GAME, {"title_id": "BCES00510", "title": "God of War III", "shared_with": "BCUS98111"}])
        self.fetch()
        generate(self.root)
        games = validate(self.root)
        self.assertEqual(games[0]["artwork"], games[1]["artwork"])

    def test_bad_ids_cycles_paths_and_checksums(self):
        for value in ("../secret", "C:/secret", "a/../../b"):
            with self.assertRaises(ValueError):
                safe_path(self.root, value)
        write_json(self.root / "database/games.json", [{**GAME, "title_id": "bad"}])
        with self.assertRaises(ValueError):
            load_games(self.root / "database/games.json")
        write_json(self.root / "database/games.json", [GAME])
        self.build()
        save_png(Image.new("RGB", (512, 512), "red"), self.root / "art/BCUS98111.png")
        with self.assertRaisesRegex(ValueError, "Checksum"):
            validate(self.root)

    def test_import_preserves_existing_entries(self):
        incoming = self.root / "import.json"
        write_json(incoming, [{**GAME, "title": "Wrong name"}, {**GAME, "title_id": "BCES00510"}])
        import_games(self.root, incoming)
        result = load_games(self.root / "database/games.json")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["title"], GAME["title"])


class ImageTests(Fixture):
    def test_rectangular_tiny_blank_and_corrupt_rejected(self):
        path = self.root / "source.png"
        for dimensions in ((600, 900), (900, 600), (64, 64), (512, 512)):
            Image.new("RGB", dimensions).save(path)
            with self.assertRaises(ValueError):
                inspect_source(path, self.config)
        path.write_bytes(b"bad image" * 100)
        with self.assertRaises(ValueError):
            inspect_source(path, self.config)

    def test_transparency_and_palette_preserved(self):
        path = self.root / "source.png"
        image = self.image.convert("RGBA")
        image.putalpha(128)
        image.save(path)
        inspect_source(path, self.config)
        result, _ = square_image(path)
        self.assertEqual(result.tobytes(), image.tobytes())
        image = self.image.convert("P")
        image.save(path)
        inspect_source(path, self.config)
        self.assertEqual(square_image(path)[0].mode, "RGB")


class AttributionPublicationTests(Fixture):
    def enable(self):
        self.config["publication"] = {"steamgriddb_with_attribution": True}
        write_json(self.root / "config.json", self.config)

    def test_validated_image_published_with_credit_without_fake_visual_approval(self):
        from scripts.check_public import check
        self.enable()
        self.build()
        prepare_public(self.root)
        check(self.root)
        game = read_json(self.root / "database/games.json")[0]
        self.assertTrue((self.root / "art/BCUS98111.png").is_file())
        self.assertEqual(game["review_status"], "pending")
        self.assertEqual(game["publication_status"], "validated-with-attribution")
        entry = individual_index(self.root)["games"]["BCUS98111"]
        self.assertTrue(entry["download_url"].endswith("/art/BCUS98111.png"))
        credit = read_json(self.root / "database/artwork_credits.json")["games"]["BCUS98111"]
        self.assertEqual(credit["creator"], "Test artist")
        self.assertIn("steamgriddb.com/grid/100", credit["source_page"])
        self.assertIn("Test artist", (self.root / "CREDITS.md").read_text())
        with zipfile.ZipFile(package(self.root)) as archive:
            self.assertIn("art/BCUS98111.png", archive.namelist())
            self.assertIn("CREDITS.md", archive.namelist())

    def test_removed_images_restored_from_recorded_source_without_new_game_search(self):
        self.build()
        prepare_public(self.root)  # Legacy behavior, with publication disabled.
        self.enable()
        api = self.api()
        result, _ = self.fetch(api)
        self.assertEqual(result[0]["status"], "restored")
        api.search.assert_not_called()
        api.grids.assert_not_called()
        generate(self.root)
        prepare_public(self.root)
        self.assertTrue((self.root / "art/BCUS98111.png").exists())

    def test_denied_and_rejected_images_are_not_auto_published(self):
        self.enable()
        self.build()
        games = read_json(self.root / "database/games.json")
        games[0]["source"]["redistribution"] = "denied"
        write_json(self.root / "database/games.json", games)
        prepare_public(self.root)
        self.assertFalse((self.root / "art/BCUS98111.png").exists())

    def test_credit_is_required(self):
        self.enable()
        self.build()
        games = read_json(self.root / "database/games.json")
        games[0]["source"]["attribution"] = ""
        write_json(self.root / "database/games.json", games)
        with self.assertRaisesRegex(ValueError, "credit"):
            prepare_public(self.root)

    def test_explicit_rejection_removes_previously_published_image(self):
        self.enable()
        self.build()
        prepare_public(self.root)
        games = read_json(self.root / "database/games.json")
        games[0]["review_status"] = "rejected"
        write_json(self.root / "database/games.json", games)
        prepare_public(self.root)
        self.assertFalse((self.root / "art/BCUS98111.png").exists())


class QueueTests(Fixture):
    def test_finished_title_is_not_downloaded_on_next_run(self):
        self.build()
        prepare_public(self.root)
        api = self.api()
        self.fetch(api)
        api.search.assert_not_called()
        api.game.assert_not_called()
        api.grids.assert_not_called()

    def test_missing_retry_and_configuration_change(self):
        game = dict(GAME)
        now = datetime(2026, 11, 2, tzinfo=timezone.utc)
        record(game, self.config, {"status": "missing_square"}, now)
        self.assertFalse(eligible(game, self.config, now + timedelta(hours=1)))
        self.assertTrue(eligible(game, self.config, now + timedelta(days=8)))
        self.assertTrue(eligible(game, self.config, now, refresh=True))
        self.config["overrides"] = {game["title_id"]: {"asset_id": 9}}
        self.assertTrue(eligible(game, self.config, now))

    def test_ambiguous_waits_for_manual_mapping_and_keeps_report(self):
        api = self.api()
        api.search.return_value = [{"id": 9, "name": "Unrelated"}]
        self.fetch(api)
        self.fetch(self.api())
        self.assertEqual(len(read_json(self.root / "reports/ambiguous_matches.json")), 1)
        game = read_json(self.root / "database/games.json")[0]
        self.assertFalse(eligible(game, self.config))
        game.update(steamgriddb_game_id=12, mapping_approved=True)
        self.assertTrue(eligible(game, self.config))

    def test_rate_limit_stops_batch_and_persists_cooldown(self):
        api = self.api()
        api.search.side_effect = RateLimitError((datetime.now(timezone.utc) + timedelta(hours=2)).isoformat())
        self.fetch(api)
        self.assertTrue((self.root / "reports/provider_cooldown.json").exists())
        api = self.api()
        self.fetch(api)
        api.search.assert_not_called()

    def test_disc_import_filters_regions_and_demo_word_boundaries(self):
        catalog = self.root / "catalog.json"
        write_json(catalog, {"BLUS-30443": {"title": "Demon's Souls", "region": "NTSC-U"},
                            "BCUS-90660": {"title": "Game Demo Disc", "region": "NTSC-U"},
                            "NPUB-12345": {"title": "PSN Game", "region": "NTSC-U"},
                            "BLES-12345": {"title": "European Disc", "region": "PAL"}})
        result = import_catalog(self.root, catalog)
        games = read_json(self.root / "database/games.json")
        self.assertEqual(result["added"], 1)
        self.assertEqual(len(result["excluded"]), 1)
        self.assertEqual(games[-1]["title"], "Demon's Souls")


class Response(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {}


class HTTPTests(Fixture):
    def client(self, data=b"ok"):
        opener = Mock()
        opener.open.return_value = Response(data)
        resolver = Mock(return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))])
        return HttpClient(self.root, self.config, opener=opener, sleeper=Mock(), resolver=resolver)

    def test_auth_errors_fatal_without_key_in_message(self):
        client = self.client()
        client.opener.open.side_effect = urllib.error.HTTPError("https://api.test/a", 401, "bad", {}, None)
        with self.assertRaises(AuthenticationError) as error:
            client.get("https://api.test/a", ["api.test"], {"Authorization": "Bearer secret-value"})
        self.assertNotIn("secret-value", str(error.exception))

    def test_size_timeout_and_rate_limits(self):
        client = self.client(b"x" * 100)
        with self.assertRaisesRegex(ValueError, "file-size"):
            client.get("https://cdn.test/a", ["cdn.test"], max_bytes=10)
        client = self.client()
        client.opener.open.side_effect = TimeoutError()
        with self.assertRaises(DownloadError):
            client.get("https://cdn.test/a", ["cdn.test"])
        self.assertEqual(client.opener.open.call_count, 3)
        client = self.client()
        client.opener.open.side_effect = urllib.error.HTTPError("https://cdn.test/a", 429, "rate", {"Retry-After": "600"}, None)
        with self.assertRaises(DownloadError):
            client.get("https://cdn.test/a", ["cdn.test"])
        with self.assertRaises(DownloadError):
            client.get("https://cdn.test/a", ["cdn.test"])
        self.assertEqual(client.opener.open.call_count, 1)

    def test_url_and_redirect_security(self):
        client = self.client()
        for url in ("http://cdn.test/a", "https://evil.test/a", "https://u:p@cdn.test/a"):
            with self.assertRaises(ValueError):
                client.get(url, ["cdn.test"])
        client.opener.open.side_effect = urllib.error.HTTPError("https://cdn.test/a", 302, "redirect", {"Location": "https://evil.test/a"}, None)
        with self.assertRaises(ValueError):
            client.get("https://cdn.test/a", ["cdn.test"])
        self.assertEqual(client.opener.open.call_count, 1)


@unittest.skipUnless(os.environ.get("NOX_LIVE_TEST") == "true" and os.environ.get("STEAMGRIDDB_API_KEY"), "Live API test requires explicit opt-in and credentials")
class IntegrationTests(unittest.TestCase):
    def test_god_of_war_search(self):
        api = SteamGridDB(HttpClient(REPO, read_json(REPO / "config.json")), refresh=True)
        self.assertTrue(api.search("God of War III"))
