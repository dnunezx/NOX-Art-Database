"""Persistent eligibility, cooldowns and completion state for bounded batches."""
import json
from datetime import datetime, timedelta, timezone

from .common import digest
from .publication import enabled


def fingerprint(game, config):
    return digest(json.dumps({"title": game["title"], "aliases": game.get("alternate_titles", []),
        "release_year": game.get("release_year"), "game_id": game.get("steamgriddb_game_id"),
        "mapping_approved": game.get("mapping_approved", False),
        "override": config.get("overrides", {}).get(game["title_id"], {})}, sort_keys=True).encode())


def eligible(game, config, now=None, refresh=False, replace=()):
    now = now or datetime.now(timezone.utc)
    if game.get("shared_with"):
        return False
    if (game.get("artwork_status") == "restricted" and enabled(config)
            and (game.get("source") or {}).get("provider") == "steamgriddb"
            and (game.get("source") or {}).get("redistribution") != "denied"
            and game.get("review_status") != "rejected"):
        return True
    if refresh or game["title_id"] in replace:
        return True
    state = game.get("fetch_state") or {}
    if state.get("fingerprint") != fingerprint(game, config):
        return True
    if state.get("status") in {"selected", "ambiguous_match", "duplicate_review"}:
        return False
    retry = state.get("retry_after")
    return not retry or datetime.fromisoformat(retry) <= now


def record(game, config, event, now=None):
    now = now or datetime.now(timezone.utc)
    status = event["status"]
    state = {"status": status, "fingerprint": fingerprint(game, config), "checked_at": now.isoformat()}
    if status in {"missing_game", "missing_square"}:
        state["retry_after"] = (now + timedelta(days=config.get("missing_retry_days", 7))).isoformat()
    elif status == "provider_unavailable":
        state["retry_after"] = (now + timedelta(hours=1)).isoformat()
    game["fetch_state"] = state
