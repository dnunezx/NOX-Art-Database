from __future__ import annotations

import json
import zipfile
from pathlib import Path

from .common import file_hash, load_games, publishable, read_json, redistribution_allowed, safe_path, write_json
from .imaging import validate_png
from .publication import apply_policy, write_credits


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
        expected = f"{canonical}.png"
        if game.get("artwork") != expected:
            raise ValueError("Artwork reference must match canonical Title ID")
        for directory, key, size, checksum in (("art", "artwork", 512, "sha256"), ("thumbnails", "thumbnail", 256, "thumbnail_sha256")):
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
    for directory in ("art", "thumbnails"):
        for path in (root / directory).glob("*"):
            if path.is_file() and path.name != ".gitkeep" and path.resolve() not in referenced:
                raise ValueError(f"Unreferenced output: {path.relative_to(root)}")
    return games


def manifest(root, database="database/games.json", config_file="config.json"):
    games = validate(root, database, config_file)
    by_id = {g["title_id"]: g for g in games}
    result = {"version": 1, "platform": "PS3", "artwork_size": 512, "thumbnail_size": 256,
              "artwork_root": "art/", "thumbnail_root": "thumbnails/", "games": {}}
    for game in sorted(games, key=lambda g: g["title_id"]):
        if publishable(game) and publishable(by_id[canonical_id(game, by_id)]):
            result["games"][game["title_id"]] = {key: game.get(key) for key in ("artwork", "thumbnail", "sha256", "thumbnail_sha256")}
            result["games"][game["title_id"]].update(steamgriddb_id=game.get("steamgriddb_game_id"),
                asset_id=(game.get("source") or {}).get("provider_artwork_id"), resolution="512x512", status="available")
    write_json(Path(root) / "database/artwork_manifest.json", result)
    return result


def package(root, database="database/games.json", config_file="config.json", version="v2-test", private=False):
    root = Path(root)
    index = manifest(root, database, config_file)
    games = load_games(safe_path(root, database))
    if private:
        # Explicit user-owned private-use pack. Never uploaded from a public repo.
        by_id = {g["title_id"]: g for g in games}
        index["delivery"] = "private-use-only"
        index["games"] = {g["title_id"]: {key: g.get(key) for key in ("artwork", "thumbnail", "sha256", "thumbnail_sha256")}
                          for g in games if g.get("artwork_status") == "generated" and g.get("review_status") == "approved"
                          and by_id[canonical_id(g, by_id)].get("review_status") == "approved"}
    paths = set()
    for entry in index["games"].values():
        paths.add("art/" + entry["artwork"])
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
    for name in ("missing_artwork.json", "processing.json", "download_results.json", "ambiguous_matches.json", "artwork_selections.json", "review.md"):
        report = root / "reports" / name
        if report.is_file():
            payloads["reports/" + name] = report.read_bytes()
    for name in ("CREDITS.md", "database/artwork_credits.json", "docs/ARTWORK-POLICY.md"):
        if (root / name).is_file():
            payloads[name] = (root / name).read_bytes()
    import re
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", version):
        raise ValueError("Unsafe package version")
    destination = root / ("private-dist" if private else "dist") / "nox-artwork.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Fixed timestamps and ordering make equal inputs produce identical ZIP bytes.
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, data in sorted(payloads.items()):
            info = zipfile.ZipInfo(relative, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    versioned = destination.parent / f"NOX-PS3-Artwork-{version}.zip"
    versioned.write_bytes(destination.read_bytes())
    thumbs = destination.parent / f"NOX-PS3-Thumbnails-{version}.zip"
    with zipfile.ZipFile(thumbs, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(payloads.items()):
            if name.startswith("thumbnails/") or name.startswith("database/") or name in {"CREDITS.md", "docs/ARTWORK-POLICY.md"}:
                info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data)
    write_json(destination.parent / "NOX-Artwork-Manifest.json", index)
    missing = root / "reports/missing_artwork.json"
    write_json(destination.parent / "NOX-Missing-Artwork.json", read_json(missing) if missing.exists() else [])
    (destination.parent / "SHA256SUMS").write_text("".join(file_hash(p) + "  " + p.name + "\n" for p in (destination, versioned, thumbs)), encoding="utf-8")
    return destination


def prepare_public(root, database="database/games.json"):
    """Apply the owner's attributed publication policy and prepare public files."""
    root = Path(root)
    games = load_games(safe_path(root, database))
    config = read_json(root / "config.json")
    apply_policy(root, games, config)
    by_id = {g["title_id"]: g for g in games}
    for game in games:
        canonical = by_id[canonical_id(game, by_id)]
        if not redistribution_allowed(canonical) or canonical.get("review_status") == "rejected" or game.get("review_status") == "rejected":
            for directory, key in (("art", "artwork"), ("thumbnails", "thumbnail")):
                if game.get(key):
                    # Rejecting one regional alias must not delete a canonical
                    # image still used by another approved or pending entry.
                    if not game.get("shared_with") or not redistribution_allowed(canonical) or canonical.get("review_status") == "rejected":
                        safe_path(root / directory, game[key]).unlink(missing_ok=True)
                    game[key] = None
            if game.get("artwork_status") == "generated":
                game["artwork_status"] = "restricted"
    write_json(safe_path(root, database), games)
    write_credits(root, games)
