"""Individual PNG delivery following CosmicScale's flat art/<ID>.png layout."""
import os
from pathlib import Path

from .common import load_games, read_json, safe_path, write_json
from .release import manifest


def individual_index(root):
    root = Path(root)
    public = manifest(root)
    games = load_games(root / "database/games.json")
    repo = os.environ.get("GITHUB_REPOSITORY", "dnunezx/NOX-Art-Database")
    if len(repo.split("/")) != 2 or any(not part.replace("-", "").replace("_", "").replace(".", "").isalnum() for part in repo.split("/")):
        raise ValueError("Invalid GitHub repository for individual artwork links")
    raw = f"https://raw.githubusercontent.com/{repo}/main/"
    index = {"version": 2, "platform": "PS3", "artwork_size": 512,
             "artwork_base_url": raw + "art/", "thumbnail_base_url": raw + "thumbnails/", "games": {}}
    for game in games:
        ident = game["title_id"]
        source = game.get("source") or {}
        entry = {"title": game["title"], "steamgriddb_id": game.get("steamgriddb_game_id"),
                 "asset_id": source.get("provider_artwork_id"), "status": game.get("artwork_status", "missing"),
                 "artwork": None, "thumbnail": None, "download_url": None, "sha256": None,
                 "source_url": source.get("url"), "source_page": source.get("source_page"),
                 "source_sha256": game.get("source_sha256"), "source_dimensions": game.get("source_dimensions"),
                 "attribution": source.get("attribution"), "license": source.get("license"),
                 "review_status": game.get("review_status", "pending"), "redistribution": source.get("redistribution", "unverified")}
        if ident in public["games"]:
            selected = public["games"][ident]
            entry.update(status="available", artwork="art/" + selected["artwork"],
                         download_url=raw + "art/" + selected["artwork"], sha256=selected["sha256"],
                         thumbnail="thumbnails/" + selected["thumbnail"] if selected.get("thumbnail") else None)
        index["games"][ident] = entry
    write_json(root / "database/individual_manifest.json", index)
    return index
