import io
import json
import os
import socket
import unittest
import urllib.error
from unittest.mock import Mock, patch

from noxart.common import read_json, write_json
from noxart.fetching import fetch
from noxart.http import HttpClient
from providers import steamgriddb
from tests.support import ArtworkFixture


class Response(io.BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(data)
        self.headers = headers or {}


class ProviderTests(ArtworkFixture, unittest.TestCase):
    def client(self, data=b"test"):
        opener = Mock()
        opener.open.return_value = Response(data)
        resolver = Mock(return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))])
        return HttpClient(self.root, self.config, opener=opener, sleeper=Mock(), resolver=resolver)

    def test_https_host_and_private_address_protection(self):
        client = self.client()
        for url in ("http://cdn.test/a", "https://evil.test/a", "https://cdn.test:444/a", "https://user:secret@cdn.test/a"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                client.get(url, ["cdn.test"])
        client.resolve.return_value = [(2, 1, 6, "", ("127.0.0.1", 443))]
        with self.assertRaisesRegex(ValueError, "non-public"):
            client.get("https://cdn.test/a", ["cdn.test"])

    def test_redirect_is_validated_before_following(self):
        client = self.client()
        client.opener.open.side_effect = urllib.error.HTTPError("https://cdn.test/a", 302, "redirect", {"Location": "https://evil.test/a"}, None)
        with self.assertRaisesRegex(ValueError, "allowlist"):
            client.get("https://cdn.test/a", ["cdn.test"])
        self.assertEqual(client.opener.open.call_count, 1)

    def test_authenticated_redirect_rejected(self):
        client = self.client()
        client.opener.open.side_effect = urllib.error.HTTPError("https://cdn.test/a", 302, "redirect", {"Location": "/b"}, None)
        with self.assertRaisesRegex(ValueError, "Authenticated"):
            client.get("https://cdn.test/a", ["cdn.test"], {"Authorization": "Bearer secret"})

    def test_size_limit_even_without_content_length(self):
        client = self.client(b"x" * 100)
        with self.assertRaisesRegex(ValueError, "file-size"):
            client.get("https://cdn.test/a", ["cdn.test"], max_bytes=10)

    def test_timeout_retries_are_bounded(self):
        client = self.client()
        client.opener.open.side_effect = TimeoutError("network timeout")
        with self.assertRaisesRegex(ValueError, "bounded retries"):
            client.get("https://cdn.test/a", ["cdn.test"])
        self.assertEqual(client.opener.open.call_count, self.config["retries"] + 1)

    def test_rate_limit_defers_entire_host(self):
        client = self.client()
        client.opener.open.side_effect = urllib.error.HTTPError("https://cdn.test/a", 429, "slow down", {"Retry-After": "600"}, None)
        with self.assertRaisesRegex(ValueError, "rate limit"):
            client.get("https://cdn.test/a", ["cdn.test"])
        with self.assertRaisesRegex(ValueError, "deferred"):
            client.get("https://cdn.test/b", ["cdn.test"])
        self.assertEqual(client.opener.open.call_count, 1)

    def test_metadata_cache_avoids_repeated_api_calls(self):
        client = self.client(json.dumps({"success": True, "data": []}).encode())
        first = client.json("https://cdn.test/a", ["cdn.test"])
        second = client.json("https://cdn.test/a", ["cdn.test"])
        self.assertEqual(first, second)
        self.assertEqual(client.opener.open.call_count, 1)

    def test_steamgriddb_requires_verified_mapping_and_token(self):
        client = Mock()
        client.json.return_value = {"success": True, "data": [{"id": 12, "name": "Different release"}]}
        with patch.dict(os.environ, {"STEAMGRIDDB_API_KEY": "test-secret"}):
            with self.assertRaisesRegex(ValueError, "Verify steamgriddb_game_id"):
                steamgriddb.candidates(self.games[0], self.root, client, self.config)
            game = {**self.games[0], "steamgriddb_game_id": 12}
            client.json.return_value = {"success": True, "data": [{"id": 2, "score": 10, "url": "https://cdn2.steamgriddb.com/a.png", "author": {"name": "Artist"}}]}
            result = steamgriddb.candidates(game, self.root, client, self.config)
            self.assertEqual(result[0]["attribution"], "Artist")
            self.assertNotIn("redistribution", result[0])
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, "not configured"):
            steamgriddb.candidates(game, self.root, client, self.config)

    def test_remote_download_requires_permission_and_records_failure(self):
        self.games[0]["source"] = {"provider": "gametdb", "url": "https://art.gametdb.com/verified.png"}
        write_json(self.root / "database/games.json", [self.games[0]])
        self.config["providers"]["gametdb"]["enabled"] = True
        write_json(self.root / "config.json", self.config)
        client = Mock()
        result = fetch(self.root, client=client)
        self.assertEqual(result[-1]["status"], "missing")
        client.get.assert_not_called()

    def test_authorized_download_and_checksum_cache(self):
        self.games[0]["source"] = {"provider": "gametdb", "url": "https://art.gametdb.com/verified.png", "download_approved": True,
                                   "download_permission_evidence": "Provider permission recorded by maintainer"}
        write_json(self.root / "database/games.json", [self.games[0]])
        self.config["providers"]["gametdb"]["enabled"] = True
        write_json(self.root / "config.json", self.config)
        client = Mock()
        client.get.return_value = (self.root / "sources/samples/square.png").read_bytes()
        fetch(self.root, client=client)
        self.assertEqual(client.get.call_count, 1)
        entry = read_json(self.root / "database/games.json")[0]
        self.assertTrue(entry["source"]["path"].startswith("downloads/"))
        # Remove the path hint to exercise URL cache, not just local-file priority.
        entry["source"].pop("path")
        write_json(self.root / "database/games.json", [entry])
        fetch(self.root, client=client)
        self.assertEqual(client.get.call_count, 1)

    def test_remote_refresh_retains_old_provenance_until_replaced(self):
        from noxart.pipeline import generate
        self.games[0]["source"] = {"provider": "gametdb", "path": "samples/square.png",
                                   "url": "https://art.gametdb.com/verified.png", "download_approved": True,
                                   "download_permission_evidence": "Recorded permission"}
        write_json(self.root / "database/games.json", [self.games[0]])
        self.config["providers"]["gametdb"]["enabled"] = True
        write_json(self.root / "config.json", self.config)
        generate(self.root)
        before = self.database()[0]
        client = Mock()
        client.get.return_value = (self.root / "sources/samples/portrait.png").read_bytes()
        fetch(self.root, refresh=True, client=client)
        after = self.database()[0]
        self.assertEqual(before["source"], after["source"])
        self.assertEqual(before["sha256"], after["sha256"])
        self.assertIn("pending_source", after)
        generate(self.root, replace=["NOXS00001"])
        self.assertNotEqual(before["sha256"], self.database()[0]["sha256"])
