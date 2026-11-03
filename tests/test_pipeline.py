import copy
import json
import unittest
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

from noxart.common import file_hash, load_games, read_json, safe_path, write_json
from noxart.imaging import inspect_source, save_png, square_image, validate_png
from noxart.pipeline import generate
from noxart.release import manifest, package, prepare_public, validate
from noxart.reporting import reports
from scripts.review_artwork import approve
from tests.support import ArtworkFixture

class PipelineTests(ArtworkFixture, unittest.TestCase):
    def test_square_portrait_landscape_and_transparent(self):
        events = self.build()
        self.assertEqual([e["status"] for e in events], ["generated"] * 4)
        for game in validate(self.root):
            validate_png(self.root / "artwork" / game["artwork"], 512, self.config)
            validate_png(self.root / "thumbnails" / game["thumbnail"], 256, self.config)
        self.assertEqual([g["processing_method"] for g in self.database()], ["crop", "fit", "fit", "fit"])

    def test_focal_crop_keeps_selected_subject(self):
        path = self.root / "focus.png"
        image = Image.new("RGB", (1000, 400), "red")
        ImageDraw.Draw(image).rectangle((600, 0, 999, 399), fill="blue")
        image.save(path)
        left, _ = square_image(path, {"method": "crop", "focal_point": [0, 0.5]})
        right, _ = square_image(path, {"method": "crop", "focal_point": [1, 0.5], "zoom": 1.5})
        self.assertEqual(left.getpixel((256, 256)), (255, 0, 0))
        self.assertEqual(right.getpixel((256, 256)), (0, 0, 255))

    def test_portrait_crop_and_rotation_are_deterministic(self):
        source = self.root / "sources/samples/portrait.png"
        settings = {"method": "crop", "focal_point": [0.5, 0.15], "rotation": 90, "zoom": 1.2}
        first, method = square_image(source, settings)
        second, _ = square_image(source, settings)
        self.assertEqual(first.tobytes(), second.tobytes())
        self.assertEqual(method, "crop")

    def test_blank_tiny_corrupt_and_aspect_rejected(self):
        for name, dimensions in (("blank", (512, 512)), ("tiny", (32, 32)), ("wide", (3000, 128))):
            path = self.root / (name + ".png")
            Image.new("RGB", dimensions, "black").save(path)
            with self.subTest(name=name), self.assertRaises(ValueError):
                inspect_source(path, self.config)
        path.write_bytes(b"bad image" * 100)
        with self.assertRaises(ValueError):
            inspect_source(path, self.config)

    def test_dark_minimalist_is_warning_not_rejection(self):
        path = self.root / "dark.png"
        image = Image.new("RGB", (512, 512), (1, 1, 1))
        ImageDraw.Draw(image).rectangle((200, 200, 300, 300), fill=(4, 4, 4))
        image.save(path)
        self.assertTrue(inspect_source(path, self.config)["warnings"])

    def test_existing_art_is_preserved_and_changed_source_reported(self):
        self.build()
        before = self.database()
        image = Image.open(self.root / "sources/samples/square.png").convert("RGB")
        ImageDraw.Draw(image).rectangle((0, 0, 200, 200), fill="yellow")
        save_png(image, self.root / "sources/samples/square.png")
        events = self.build()
        self.assertIn("source changed", events[0]["message"])
        self.assertEqual(before, self.database())
        generate(self.root, replace=["NOXS00001"])
        self.assertNotEqual(before[0]["sha256"], self.database()[0]["sha256"])
        self.assertEqual(self.database()[0]["review_status"], "pending")

    def test_title_id_duplicate_and_shared_cycles(self):
        for bad in ("../../bad", "BLUS1234", "blus12345", "BLUS12345.png"):
            games = copy.deepcopy(self.games)
            games[0]["title_id"] = bad
            write_json(self.root / "database/games.json", games)
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                load_games(self.root / "database/games.json")
        self.games[1]["title_id"] = self.games[0]["title_id"]
        write_json(self.root / "database/games.json", self.games)
        with self.assertRaises(ValueError):
            self.build()
        write_json(self.root / "database/games.json", [
            {"title_id": "NOXS00001", "title": "A", "shared_with": "NOXS00002"},
            {"title_id": "NOXS00002", "title": "B", "shared_with": "NOXS00001"}])
        with self.assertRaisesRegex(ValueError, "cyclic"):
            self.build()

    def test_existing_untracked_art_is_adopted_without_approval(self):
        output = self.root / "artwork/PS3/NOXS00001.png"
        image, _ = square_image(self.root / "sources/samples/square.png", {})
        save_png(image, output)
        before = output.read_bytes()
        self.build()
        self.assertEqual(output.read_bytes(), before)
        self.assertEqual(self.database()[0]["source"]["provider"], "existing")
        self.assertEqual(self.database()[0]["review_status"], "pending")
        validate(self.root)

    def test_safe_paths_reject_traversal_and_windows_paths(self):
        for path in ("../secret", "C:/secret", "\\server\\secret", "/tmp/a", "a/../../b"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                safe_path(self.root, path)

    def test_duplicate_requires_verified_alias(self):
        self.games[1]["source"] = self.games[0]["source"]
        write_json(self.root / "database/games.json", self.games)
        self.build()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate(self.root)

    def test_shared_regions_and_manifest(self):
        alias = {"title_id": "NOXS00005", "title": "Verified equivalent region", "shared_with": "NOXS00001"}
        write_json(self.root / "database/games.json", [alias] + self.games)
        self.build()
        approve(self.root, ["NOXS00001", "NOXS00005"])
        result = manifest(self.root)
        self.assertEqual(len(result["games"]), 2)
        self.assertEqual(result["games"]["NOXS00005"]["artwork"], "PS3/NOXS00001.png")
        self.assertEqual(len(result["games"]["NOXS00001"]["sha256"]), 64)

    def test_package_requires_review_and_permission(self):
        self.build()
        archive = package(self.root)
        with zipfile.ZipFile(archive) as z:
            self.assertFalse(any(name.endswith(".png") for name in z.namelist()))
        approve(self.root, ["NOXS00001"])
        archive = package(self.root)
        before = archive.read_bytes()
        with zipfile.ZipFile(archive) as z:
            self.assertIn("artwork/PS3/NOXS00001.png", z.namelist())
            index = json.loads(z.read("database/artwork_manifest.json"))
            self.assertEqual(index["games"]["NOXS00001"]["sha256"], file_hash(self.root / "artwork/PS3/NOXS00001.png"))
        self.assertEqual(before, package(self.root).read_bytes())
        games = self.database()
        games[0]["source"]["redistribution"] = "unverified"
        write_json(self.root / "database/games.json", games)
        self.assertEqual(manifest(self.root)["games"], {})

    def test_missing_reports_and_bounded_batches(self):
        self.games[0]["source"]["path"] = "samples/not-present.png"
        write_json(self.root / "database/games.json", self.games)
        generate(self.root, limit=2)
        reports(self.root)
        self.assertEqual(len(read_json(self.root / "reports/missing.json")), 3)
        self.assertEqual(sum(g.get("artwork_status") == "generated" for g in self.database()), 1)
        generate(self.root, limit=2)
        self.assertEqual(sum(g.get("artwork_status") == "generated" for g in self.database()), 3)

    def test_checksum_and_orphan_files_fail_validation(self):
        self.build()
        target = self.root / "artwork/PS3/NOXS00001.png"
        Image.new("RGB", (512, 512), "red").save(target)
        with self.assertRaisesRegex(ValueError, "Checksum"):
            validate(self.root)

    def test_orphan_rejected(self):
        self.build()
        orphan = self.root / "artwork/PS3/NOXS99999.png"
        save_png(Image.new("RGB", (512, 512), "red"), orphan)
        with self.assertRaisesRegex(ValueError, "Unreferenced"):
            validate(self.root)

    def test_public_preparation_removes_unverified_images(self):
        self.games[0]["source"]["redistribution"] = "unverified"
        write_json(self.root / "database/games.json", self.games)
        self.build()
        prepare_public(self.root)
        reports(self.root)
        self.assertFalse((self.root / "artwork/PS3/NOXS00001.png").exists())
        self.assertEqual(self.database()[0]["artwork_status"], "restricted")
        validate(self.root)


if __name__ == "__main__":
    unittest.main()
