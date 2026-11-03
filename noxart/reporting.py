import base64
import html
from pathlib import Path

from .common import load_games, redistribution_allowed, safe_path, write_json


def reports(root, database="database/games.json"):
    root = Path(root)
    games = load_games(safe_path(root, database))
    destination = root / "reports"
    destination.mkdir(parents=True, exist_ok=True)
    missing = [{"title_id": g["title_id"], "title": g["title"], "status": g.get("artwork_status", "missing")}
               for g in games if g.get("artwork_status") != "generated"]
    write_json(destination / "missing.json", missing)
    rows = ["# Artwork review", "", "| Title | Title ID | Original size | Output | Validation | Provider | Redistribution | Review |",
            "|---|---|---|---|---|---|---|---|"]
    cards = []
    for game in games:
        source = game.get("source") or {}
        def clean(value):
            return str(value).replace("|", "&#124;").replace("\n", " ").replace("\r", " ")
        generated = game.get("artwork_status") == "generated"
        output = game.get("artwork") or "unavailable"
        rows.append("| " + " | ".join(clean(v) for v in (game["title"], game["title_id"], game.get("source_dimensions", "unknown"),
                    output, "validated by workflow" if generated else "not generated", source.get("provider", "none"),
                    source.get("redistribution", "unverified"), game.get("review_status", "pending"))) + " |")
        thumb = game.get("thumbnail")
        if thumb and redistribution_allowed(game):
            path = safe_path(root / "thumbnails", thumb)
            if path.exists():
                encoded = base64.b64encode(path.read_bytes()).decode()
                cards.append(f'<figure><img width="160" height="160" src="data:image/png;base64,{encoded}" alt="">'
                             f'<figcaption>{html.escape(game["title"])}<br>{html.escape(game["title_id"])}</figcaption></figure>')
    (destination / "review.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (destination / "contact-sheet.html").write_text('<!doctype html><meta charset="utf-8"><title>NOX artwork review</title>'
        '<style>body{background:#15151c;color:#eee;font:16px system-ui}main{display:flex;flex-wrap:wrap}figure{width:180px}</style>'
        '<h1>NOX artwork review</h1><p>Only images with explicit redistribution permission appear here.</p><main>' + "".join(cards) + "</main>", encoding="utf-8")
