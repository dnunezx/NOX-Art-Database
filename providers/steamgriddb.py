"""Official API v2. A human-verified game ID is required before selecting images."""
import os
from urllib.parse import quote

BASE = "https://www.steamgriddb.com/api/v2"


def candidates(game, root, client, config, refresh=False):
    token = os.environ.get("STEAMGRIDDB_API_KEY")
    if not token:
        raise ValueError("STEAMGRIDDB_API_KEY is not configured")
    headers = {"Authorization": "Bearer " + token}
    ident = game.get("steamgriddb_game_id")
    if ident is None:
        response = client.json(BASE + "/search/autocomplete/" + quote(game["title"], safe=""), ["www.steamgriddb.com"], headers, refresh)
        if not response.get("success"):
            raise ValueError("SteamGridDB search was unsuccessful")
        matches = [{"id": row["id"], "name": row["name"]} for row in response.get("data", [])[:10]]
        # Do not infer equivalence between a PC game, remake or PS3 release.
        raise ValueError("Verify steamgriddb_game_id before download; candidates: " + str(matches))
    if type(ident) is not int or ident <= 0:
        raise ValueError("steamgriddb_game_id must be a positive integer")
    response = client.json(BASE + f"/grids/game/{ident}?dimensions=512x512,1024x1024&types=static&mimes=image/png",
                           ["www.steamgriddb.com"], headers, refresh)
    if not response.get("success"):
        raise ValueError("SteamGridDB grid lookup was unsuccessful")
    rights = game.get("provider_permissions", {}).get("steamgriddb", {})
    rows = [row for row in response.get("data", []) if not row.get("nsfw") and not row.get("humor")]
    rows.sort(key=lambda row: (-row.get("score", 0), row["id"]))
    return [{**rights, "provider": "steamgriddb", "url": row["url"], "provider_artwork_id": row["id"],
             "attribution": row.get("author", {}).get("name", "Unknown SteamGridDB contributor"),
             "source_page": f"https://www.steamgriddb.com/grid/{row['id']}"} for row in rows[:5]]
