from __future__ import annotations

import json
import zipfile
from pathlib import Path

from .common import file_hash, load_games, publishable, read_json, redistribution_allowed, safe_path, write_json
from .imaging import validate_png


def canonical_id(game, by_id):
    while game.get("shared_with"):
        game = by_id[game["shared_with"]]
    return game["title_id"]


def validate(root, database="database/games.json", config_file="config.json"):
    root = Path(root)
    config = read_json(safe_path(root, config_file))
    games = load_games(safe_path(root, database))
    by_id = {g["title_id"]: g for g in games}
    hashes, referenced = {}, set()
    for game in games:
        if game.get("artwork_status") != "generated":
            if game.get("artwork") or game.get("thumbnail"):
                raise ValueError("Non-generated entry references artwork")
            continue
        canonical = canonical_id(game, by_id)
        expected = f"PS3/{canonical}.png"
        if game.get("artwork") != expected:
            raise ValueError("Artwork reference must match canonical Title ID")
        for directory, key, size, checksum in (("artwork", "artwork", 512, "sha256"), ("thumbnails", "thumbnail", 256, "thumbnail_sha256")):
            if key == "thumbnail" and not game.get(key):
                continue
            if game.get(key) != expected:
                raise ValueError("Invalid thumbnail reference")
            path = safe_path(root / directory, game[key])
            validate_png(path, size, config)
            if file_hash(path) != game.get(checksum):
                raise ValueError(f"Checksum mismatch for {game['title_id']} {key}")
            referenced.add(path.resolve())
        if not game.get("source_sha256") or not game.get("generated_at") or not game.get("source"):
            raise ValueError("Missing artwork provenance")
        if game.get("review_status") == "approved" and game.get("reviewed_sha256") != game["sha256"]:
            raise ValueError("Review approval must be bound to the generated checksum")
        previous = hashes.setdefault(game["sha256"], canonical)
        if previous != canonical:
            raise ValueError("Exact duplicate artwork requires explicit shared_with mapping")
        if canonical != game["title_id"]:
            target = by_id[canonical]
            if target.get("sha256") != game["sha256"] or target.get("source") != game.get("source"):
                raise ValueError("Shared artwork metadata conflicts with canonical entry")
    for directory in ("artwork", "thumbnails"):
        for path in (root / directory).glob("PS3/*"):
            if path.is_file() and path.suffix != ".gitkeep" and path.resolve() not in referenced:
                raise ValueError(f"Unreferenced output: {path.relative_to(root)}")
    return games


def manifest(root, database="database/games.json", config_file="config.json"):
    games = validate(root, database, config_file)
    by_id = {g["title_id"]: g for g in games}
    result = {"version": 1, "platform": "PS3", "artwork_size": 512, "thumbnail_size": 256,
              "artwork_root": "artwork/", "thumbnail_root": "thumbnails/", "games": {}}
    for game in sorted(games, key=lambda g: g["title_id"]):
        if publishable(game) and publishable(by_id[canonical_id(game, by_id)]):
            result["games"][game["title_id"]] = {key: game.get(key) for key in ("artwork", "thumbnail", "sha256", "thumbnail_sha256")}
    write_json(Path(root) / "database/artwork_manifest.json", result)
    return result


def package(root, database="database/games.json", config_file="config.json"):
    root = Path(root)
    index = manifest(root, database, config_file)
    games = load_games(safe_path(root, database))
    paths = set()
    for entry in index["games"].values():
        paths.add("artwork/" + entry["artwork"])
        if entry.get("thumbnail"):
            paths.add("thumbnails/" + entry["thumbnail"])
    public_metadata = []
    for game in games:
        entry = dict(game)
        if game["title_id"] not in index["games"]:
            entry.update(artwork=None, thumbnail=None)
        public_metadata.append(entry)
    payloads = {"database/artwork_manifest.json": (json.dumps(index, indent=2) + "\n").encode(),
                "database/games.json": (json.dumps(public_metadata, indent=2) + "\n").encode()}
    for relative in paths:
        payloads[relative] = safe_path(root, relative).read_bytes()
    for name in ("missing.json", "processing.json", "fetch.json", "review.md"):
        report = root / "reports" / name
        if report.is_file():
            payloads["reports/" + name] = report.read_bytes()
    destination = root / "dist/nox-artwork.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Fixed timestamps and ordering make equal inputs produce identical ZIP bytes.
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, data in sorted(payloads.items()):
            info = zipfile.ZipInfo(relative, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    (root / "dist/SHA256SUMS").write_text(file_hash(destination) + "  nox-artwork.zip\n", encoding="utf-8")
    return destination


def prepare_public(root, database="database/games.json"):
    """Remove restricted images before creating a public PR or uploading reports."""
    root = Path(root)
    games = load_games(safe_path(root, database))
    by_id = {g["title_id"]: g for g in games}
    for game in games:
        canonical = by_id[canonical_id(game, by_id)]
        if not redistribution_allowed(canonical):
            for directory, key in (("artwork", "artwork"), ("thumbnails", "thumbnail")):
                if game.get(key):
                    safe_path(root / directory, game[key]).unlink(missing_ok=True)
                    game[key] = None
            if game.get("artwork_status") == "generated":
                game["artwork_status"] = "restricted"
    write_json(safe_path(root, database), games)
