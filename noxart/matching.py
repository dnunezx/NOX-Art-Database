"""Conservative exact identity matching; no first-result or fuzzy auto-selection."""
import re
import unicodedata
from datetime import datetime, timezone

ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10"}


def normalize(title):
    title = title.replace("™", "").replace("®", "").replace("©", "")
    text = unicodedata.normalize("NFKD", title.casefold().replace("&", " and "))
    text = "".join(c for c in text if not unicodedata.combining(c))
    tokens = re.findall(r"[^\W_]+", text, flags=re.UNICODE)
    return " ".join(ROMAN.get(token, token) for token in tokens)


def release_year(row):
    value = row.get("release_date")
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value, timezone.utc).year
    except (OverflowError, OSError, ValueError):
        return None


def resolve(game, api, cached=None):
    names = [game["title"], *game.get("alternate_titles", [])]
    normalized = {normalize(name) for name in names}
    explicit = game.get("steamgriddb_game_id")
    fingerprint = {"titles": sorted(normalized), "release_year": game.get("release_year")}
    cached_id = cached.get("game_id") if cached and cached.get("identity") == fingerprint else None
    if explicit or cached_id:
        ident = explicit or cached_id
        if type(ident) is not int or ident <= 0:
            raise ValueError("steamgriddb_game_id must be a positive integer")
        row = api.game(ident)
        manual = bool(explicit and game.get("mapping_approved") is True)
        same_name = normalize(row["name"]) in normalized
        same_year = not game.get("release_year") or release_year(row) == game["release_year"]
        if manual or (same_name and same_year):
            return {"game_id": ident, "name": row["name"], "release_year": release_year(row),
                    "confidence": "manual" if manual else "exact", "identity": fingerprint}, []
        return None, [row]
    candidates = {}
    for name in names:
        for row in api.search(normalize(name)):
            candidates[row["id"]] = row
    exact = [r for r in candidates.values() if normalize(r["name"]) in normalized]
    confirmed = [api.game(row["id"]) for row in exact]
    confirmed = [r for r in confirmed if normalize(r["name"]) in normalized
                 and (not game.get("release_year") or release_year(r) == game["release_year"])]
    if len(confirmed) == 1:
        row = confirmed[0]
        return {"game_id": row["id"], "name": row["name"], "release_year": release_year(row),
                "confidence": "exact", "identity": fingerprint}, []
    return None, list(candidates.values())[:20]
