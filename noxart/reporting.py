import html
from pathlib import Path
from urllib.parse import urlsplit

from .common import load_games, read_json, safe_path, write_json
from .queue import eligible


def reports(root, database="database/games.json"):
    root = Path(root)
    games = load_games(safe_path(root, database))
    destination = root / "reports"
    destination.mkdir(parents=True, exist_ok=True)
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
                "awaiting_review": sum(g.get("fetch_state", {}).get("status") in {"ambiguous_match", "duplicate_review"} for g in games),
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
