"""Explicit GameTDB URLs only, pending verification of bulk download permission.

Coverage: https://www.gametdb.com/PS3/Downloads
No scraping, guessed CDN paths, or blanket redistribution license.
"""


def candidates(game, root, client, config, refresh=False):
    source = game.get("source") or {}
    return [source] if source.get("provider") == "gametdb" and source.get("url") else []
