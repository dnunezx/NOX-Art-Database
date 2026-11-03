"""Repository-owner-authorized publication with mandatory contributor credits."""
from pathlib import Path
from urllib.parse import urlsplit

from .common import file_hash, safe_path, write_json
from .imaging import validate_png

POLICY = "docs/ARTWORK-POLICY.md"


def enabled(config):
    return config.get("publication", {}).get("steamgriddb_with_attribution") is True


def apply_policy(root, games, config):
    if not enabled(config):
        return
    for game in games:
        source = game.get("source") or {}
        if (game.get("artwork_status") != "generated" or game.get("review_status") == "rejected"
                or game.get("match_confidence") not in {"exact", "manual"}
                or source.get("provider") != "steamgriddb" or source.get("redistribution") == "denied"):
            continue
        ident = source.get("provider_artwork_id")
        page = urlsplit(source.get("source_page", ""))
        if (type(ident) is not int or page.scheme != "https" or page.netloc != "www.steamgriddb.com"
                or page.path != f"/grid/{ident}" or not isinstance(source.get("attribution"), str)
                or not source["attribution"].strip()):
            raise ValueError(f"Missing creator credit or valid source link: {game['title_id']}")
        path = safe_path(Path(root) / "art", game["artwork"])
        validate_png(path, 512, config)
        if file_hash(path) != game["sha256"]:
            raise ValueError("Artwork checksum changed before publication")
        source.update(redistribution="approved", permission_evidence=POLICY,
                      publication_basis="repository-owner-authorized-with-attribution")
        if not source.get("license") or source["license"] == "Third-party artwork; redistribution unverified":
            source["license"] = "Original creator and publisher rights retained; see attribution policy"
        game["publication_status"] = "validated-with-attribution"
        inconclusive = (bool(game.get("quality_warnings"))
                        or game.get("fetch_state", {}).get("status") in {"ambiguous_match", "duplicate_review"})
        if game.get("review_status", "pending") == "pending" and not inconclusive:
            game.update(review_status="approved", reviewed_sha256=game["sha256"],
                        review_method="automatic", approval_reason="Confirmed game identity and validated static square artwork")
    write_credits(root, games)


def write_credits(root, games):
    rows = ["# Artwork credits", "", "Artwork supplied through [SteamGridDB](https://www.steamgriddb.com/).",
            "Original creators, contributors and game publishers retain their rights.", "",
            "| PS3 Title ID | Game | Contributor | SteamGridDB asset |", "|---|---|---|---|"]
    credits = {}
    for game in sorted(games, key=lambda g: g["title_id"]):
        source = game.get("source") or {}
        if game.get("artwork_status") != "generated" or source.get("provider") != "steamgriddb":
            continue
        entry = {"title": game["title"], "creator": source.get("attribution"), "provider": "SteamGridDB",
                 "source_page": source.get("source_page"), "source_url": source.get("url"),
                 "asset_id": source.get("provider_artwork_id"), "artwork": "art/" + game["artwork"],
                 "sha256": game["sha256"]}
        credits[game["title_id"]] = entry
        def clean(value):
            return str(value).replace("|", "&#124;").replace("\n", " ").replace("\r", " ")
        rows.append(f"| {game['title_id']} | {clean(game['title'])} | {clean(entry['creator'])} | [#{entry['asset_id']}]({entry['source_page']}) |")
    root = Path(root)
    (root / "CREDITS.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    write_json(root / "database/artwork_credits.json", {"provider": "SteamGridDB", "games": credits})
