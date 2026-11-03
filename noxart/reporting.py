import html
import os
from pathlib import Path
from urllib.parse import urlsplit

from .common import load_games, read_json, safe_path, write_json
from .queue import eligible


def review_gallery(root, games, destination):
    def clean(value):
        return html.escape(str(value)).replace("|", "&#124;").replace("\n", " ").replace("\r", " ")
    repo = os.environ.get("GITHUB_REPOSITORY", "dnunezx/NOX-Art-Database")
    lines = ["# Artwork review gallery", "", "Click a thumbnail to open the full-size PNG. Creator credits and source links are saved with every image.", "",
             f"[Record approval or rejection in GitHub Actions](https://github.com/{repo}/actions/workflows/review-artwork.yml)", "",
             "Conclusive matches that pass validation are approved automatically. Only inconclusive cases need your review. Use **Run workflow** to override a decision by Title ID. Approved images are kept and never replaced automatically.", "",
             "[Games needing an identity match](matching-review.md) · [Progress](progress.md) · [All credits](../CREDITS.md)", ""]
    for status, heading in (("pending", "Needs review (inconclusive)"), ("approved", "Approved artwork"), ("rejected", "Rejected artwork")):
        selected = [g for g in games if g.get("review_status", "pending") == status and
                    (g.get("artwork_status") == "generated" or (status == "rejected" and g.get("source")))]
        lines.extend([f"## {heading} ({len(selected)})", ""])
        if not selected:
            lines.extend(["No entries in this section yet.", ""])
            continue
        lines.extend(["| Preview | Game | Title ID | Approval | Contributor / source |", "|---|---|---|---|---|"])
        for game in sorted(selected, key=lambda g: (g["title"].casefold(), g["title_id"])):
            source = game.get("source") or {}
            preview = "Image removed; source retained for reference"
            if game.get("artwork"):
                artwork = safe_path(root / "art", game["artwork"])
                thumb = game.get("thumbnail")
                if artwork.exists():
                    image_path = "../thumbnails/" + thumb if thumb else "../art/" + game["artwork"]
                    preview = f"[![{game['title_id']}]({image_path})](../art/{game['artwork']})"
            creator = clean(source.get("attribution", "Unknown contributor"))
            page = source.get("source_page", "")
            source_link = f"[asset #{source.get('provider_artwork_id')}]({page})" if page.startswith("https://www.steamgriddb.com/grid/") else "Source not supplied"
            method = game.get("review_method", "manual" if status == "approved" else "needs review")
            lines.append(f"| {preview} | {clean(game['title'])} | `{game['title_id']}` | {clean(method)} | {creator}<br>{source_link} |")
        lines.append("")
    (destination / "artwork-review.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    pending_path = destination / "ambiguous_matches.json"
    pending = read_json(pending_path) if pending_path.exists() else []
    match_lines = ["# Game matching review", "", "These titles have not been assigned artwork automatically. Compare the original game and its release with the candidate SteamGridDB pages.", "",
                   "[Back to artwork gallery](artwork-review.md)", ""]
    for row in pending:
        match_lines.extend([f"## {clean(row['title'])} — {row['title_id']}", ""])
        for candidate in row.get("candidates", []):
            ident = candidate.get("id")
            if type(ident) is int:
                match_lines.append(f"- [{clean(candidate.get('name', 'Unnamed game'))}](https://www.steamgriddb.com/game/{ident}) — game ID `{ident}`")
        match_lines.append("")
    (destination / "matching-review.md").write_text("\n".join(match_lines).rstrip() + "\n", encoding="utf-8")


def reports(root, database="database/games.json"):
    root = Path(root)
    games = load_games(safe_path(root, database))
    destination = root / "reports"
    destination.mkdir(parents=True, exist_ok=True)
    review_gallery(root, games, destination)
    events_path = destination / "download_results.json"
    events = read_json(events_path) if events_path.exists() else []
    results = {e["title_id"]: e for e in events}
    missing = [{"title_id": g["title_id"], "title": g["title"], "status": results.get(g["title_id"], {}).get("status", g.get("artwork_status", "missing"))}
               for g in games if g.get("artwork_status") not in {"generated", "restricted"}]
    write_json(destination / "missing_artwork.json", missing)
    config = read_json(root / "config.json")
    progress = {"total_title_ids": len(games),
                "processed_artwork": sum(g.get("artwork_status") in {"generated", "restricted"} for g in games),
                "hosted_pngs": sum(g.get("artwork_status") == "generated" for g in games),
                "awaiting_review": sum(g.get("fetch_state", {}).get("status") in {"ambiguous_match", "duplicate_review"}
                                       or (g.get("artwork_status") == "generated" and g.get("review_status") == "pending") for g in games),
                "automatically_approved": sum(g.get("review_status") == "approved" and g.get("review_method") == "automatic" for g in games),
                "manually_approved": sum(g.get("review_status") == "approved" and g.get("review_method", "manual") == "manual" for g in games),
                "missing_retry": sum(g.get("fetch_state", {}).get("status") in {"missing_game", "missing_square", "provider_unavailable"} for g in games),
                "ready_for_next_batch": sum(eligible(g, config) and g.get("artwork_status") != "generated" for g in games),
                "batch_size": config["batch_size"]}
    write_json(destination / "progress.json", progress)
    summary = "\n".join(f"- {key.replace('_', ' ')}: {value}" for key, value in progress.items()) + "\n"
    (destination / "progress.md").write_text("# US disc artwork progress\n\n" + summary, encoding="utf-8")
    rows = ["# NOX artwork review", "", "| Title | Title ID | Asset | Match | Validation | Review | Redistribution |",
            "|---|---|---|---|---|---|---|"]
    cards = []
    for game in games:
        source = game.get("source") or {}
        event = results.get(game["title_id"], {})
        generated = game.get("artwork_status") in {"generated", "restricted"}
        validation = "validated" if generated else event.get("status", "missing")
        values = (game["title"], game["title_id"], source.get("provider_artwork_id", "none"),
                  game.get("match_confidence", "unknown"), validation, game.get("review_status", "pending"), source.get("redistribution", "unverified"))
        rows.append("| " + " | ".join(str(v).replace("|", "&#124;").replace("\n", " ").replace("\r", " ") for v in values) + " |")
        url = source.get("url", "")
        parsed = urlsplit(url)
        preview = ""
        if parsed.scheme == "https" and parsed.hostname in {"cdn2.steamgriddb.com", "cdn.steamgriddb.com"}:
            preview = f'<img width="200" height="200" loading="lazy" src="{html.escape(url, quote=True)}" alt="Square artwork">'
        label = "<br>".join(html.escape(str(v)) for v in (game["title"], game["title_id"],
                f"Asset {source.get('provider_artwork_id', 'none')} · {game.get('match_confidence', 'unknown')}",
                source.get("attribution", ""), validation, game.get("review_status", "pending")))
        cards.append(f"<figure>{preview}<figcaption>{label}</figcaption></figure>")
    mapping = read_json(root / "database/steamgriddb_mapping.json") if (root / "database/steamgriddb_mapping.json").exists() else {}
    review_assets = [{"title_id": ident, "selected_asset_id": item.get("asset_id"), "confidence": item.get("confidence"),
                      "selection": item.get("asset_selection"), "previews": item.get("previews", [])}
                     for ident, item in mapping.items()]
    write_json(destination / "artwork_selections.json", review_assets)
    (destination / "review.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (destination / "contact-sheet.html").write_text('<!doctype html><meta charset="utf-8"><title>NOX artwork review</title>'
        '<style>body{background:#15151c;color:#eee;font:16px system-ui}main{display:flex;flex-wrap:wrap}figure{width:240px}img{object-fit:contain}</style>'
        '<h1>NOX artwork review</h1><p>Previews load directly from SteamGridDB. Visual selection and redistribution rights require separate review.</p><main>'
        + "".join(cards) + "</main>", encoding="utf-8")
