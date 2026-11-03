"""Import US disc metadata from GameDB, without fetching games or artwork."""
import argparse
import re
from pathlib import Path

from noxart.common import file_hash, load_games, read_json, write_json

SOURCE = "https://github.com/niemasd/GameDB-PS3"
RELEASE = "https://github.com/niemasd/GameDB-PS3/releases/latest/download/PS3.data.json"
NON_GAME = re.compile(r"\b(demo|demos|sampler|kiosk|trial)\b", re.IGNORECASE)


def import_catalog(root, catalog):
    games = load_games(root / "database/games.json")
    by_id = {game["title_id"]: game for game in games}
    data = read_json(catalog)
    if not isinstance(data, dict):
        raise ValueError("Expected a GameDB serial-to-game object")
    added, skipped, conflicts = [], [], []
    for serial, row in sorted(data.items()):
        if not re.fullmatch(r"(?:BCUS|BLUS)-?[0-9]{5}", serial):
            continue
        title = row.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("Catalog contains an invalid title")
        ident = serial.replace("-", "")
        if NON_GAME.search(title):
            skipped.append({"title_id": ident, "title": title, "reason": "Demo/trial/non-retail sampler"})
            continue
        warning = None
        if row.get("region") != "NTSC-U":
            warning = f"US disc serial but upstream region is {row.get('region')!r}; verify catalog metadata"
            conflicts.append({"title_id": ident, "title": title, "warning": warning})
        if ident in by_id:
            continue
        game = {"title_id": ident, "title": title, "platform": "PS3", "region": "US", "distribution": "disc",
                "artwork_status": "missing", "review_status": "pending", "catalog_source": SOURCE,
                "catalog_serial": serial, "title_id_evidence": SOURCE + "/tree/main/games/" + serial}
        if warning:
            game["catalog_warning"] = warning
        by_id[ident] = game
        games.append(game)
        added.append(ident)
    for game in games:
        if game["title_id"].startswith(("BCUS", "BLUS")):
            game.setdefault("distribution", "disc")
    write_json(root / "database/games.json", sorted(games, key=lambda game: game["title_id"]))
    report = {"source": SOURCE, "download": RELEASE, "source_sha256": file_hash(catalog),
              "metadata_attribution": "Niema's GameDB-PS3; upstream sources MiSTer Addons and Redump",
              "scope": "US BCUS/BLUS disc serials in upstream metadata; excludes explicit demo/trial/sampler entries",
              "catalog_total": len(by_id), "added": len(added), "excluded": skipped, "region_conflicts": conflicts,
              "coverage": "Upstream catalog coverage; not a claim that every US retail release has been independently verified"}
    write_json(root / "reports/us_catalog_import.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("catalog_json", type=Path)
    args = parser.parse_args()
    result = import_catalog(Path.cwd(), args.catalog_json)
    print(f"Imported {result['added']} US disc entries; catalog now contains {result['catalog_total']} Title IDs")
