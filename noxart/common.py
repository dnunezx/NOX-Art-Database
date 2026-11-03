from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

TITLE_ID = re.compile(r"[A-Z]{4}[0-9]{5}\Z")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_path(root, relative):
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise ValueError("Invalid relative path")
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Path must remain inside its designated directory")
    root = Path(root).resolve()
    result = (root / relative).resolve()
    if not result.is_relative_to(root):
        raise ValueError("Path escapes its designated directory")
    return result


def title_id(value):
    if not isinstance(value, str) or not TITLE_ID.fullmatch(value):
        raise ValueError(f"Invalid PS3 Title ID: {value!r}")
    return value


def load_games(path):
    games = read_json(path)
    if not isinstance(games, list):
        raise ValueError("games.json must contain an array")
    seen = {}
    for game in games:
        if not isinstance(game, dict):
            raise ValueError("Each game must be an object")
        ident = title_id(game["title_id"])
        if ident in seen:
            raise ValueError(f"Duplicate Title ID: {ident}")
        if game.get("platform", "PS3") != "PS3" or not isinstance(game.get("title"), str) or not game["title"].strip():
            raise ValueError(f"Invalid PS3 title: {ident}")
        if game.get("review_status", "pending") not in {"pending", "approved", "rejected"}:
            raise ValueError(f"Invalid review status: {ident}")
        if game.get("artwork_status", "missing") not in {"missing", "generated", "restricted"}:
            raise ValueError(f"Invalid artwork status: {ident}")
        for source_key in ("source", "pending_source"):
            source = game.get(source_key)
            if source is not None and not isinstance(source, dict):
                raise ValueError("Source metadata must be an object or null")
            if source and source.get("redistribution", "unverified") not in {"approved", "unverified", "denied"}:
                raise ValueError("Invalid redistribution status")
        if "provider_permissions" in game and not isinstance(game["provider_permissions"], dict):
            raise ValueError("provider_permissions must be an object")
        seen[ident] = game
    for game in games:
        chain = {game["title_id"]}
        current = game
        while current.get("shared_with"):
            target = title_id(current["shared_with"])
            if target not in seen or target in chain:
                raise ValueError("Unknown or cyclic shared_with reference")
            chain.add(target)
            current = seen[target]
    return games


def redistribution_allowed(game):
    source = game.get("source") or {}
    return (source.get("redistribution") == "approved"
            and all(isinstance(source.get(key), str) and source[key].strip()
                    for key in ("license", "attribution", "permission_evidence")))


def publishable(game):
    return (game.get("artwork_status") == "generated"
            and game.get("review_status") == "approved"
            and redistribution_allowed(game))


def settings_for(config, game):
    return {**config["processing"], **config.get("overrides", {}).get(game["title_id"], {})}


def queued_games(root, games, stage):
    """Resume after the last attempted ID, so missing sources cannot starve a batch."""
    path = Path(root) / "reports/queue.json"
    state = read_json(path) if path.exists() else {}
    previous = state.get(stage)
    ids = [g["title_id"] for g in games]
    start = (ids.index(previous) + 1) % len(ids) if previous in ids else 0
    return games[start:] + games[:start]


def advance_queue(root, stage, ident):
    path = Path(root) / "reports/queue.json"
    state = read_json(path) if path.exists() else {}
    state[stage] = ident
    write_json(path, state)
