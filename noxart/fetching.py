"""Match PS3 entries, fetch native squares, and record reviewable selections."""
from pathlib import Path
import time
from datetime import datetime, timezone

from providers.steamgriddb import SteamGridDB
from .common import advance_queue, digest, file_hash, load_games, queued_games, read_json, safe_path, write_json
from .http import DownloadError, HttpClient, RateLimitError
from .imaging import inspect_source
from .matching import resolve
from .selection import ranked, score
from .queue import eligible, record
from .publication import enabled


def needs_restore(game, config):
    return (enabled(config) and game.get("artwork_status") == "restricted" and not game.get("shared_with")
            and (game.get("source") or {}).get("provider") == "steamgriddb"
            and (game.get("source") or {}).get("redistribution") != "denied" and game.get("review_status") != "rejected"
            and bool(game.get("source_sha256")))


def restore_source(game, root, client, config):
    """Rehydrate a previously validated selection without choosing a new asset."""
    source = game["source"]
    data = client.get(source["url"], config["allowed_hosts"])
    checksum = digest(data)
    if checksum != game["source_sha256"]:
        raise ValueError("Recorded source has changed; fresh API selection required")
    relative = "downloads/" + checksum + ".image"
    path = safe_path(root / "sources", relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    info = inspect_source(path, config)
    source.update(path=relative, format=info["format"], dimensions=info["dimensions"])
    return {"title_id": game["title_id"], "status": "restored", "asset_id": source["provider_artwork_id"],
            "dimensions": info["dimensions"], "source_sha256": checksum}


def fetch(root, limit=None, refresh=False, client=None, replace=()):
    root = Path(root)
    config = read_json(root / "config.json")
    games = load_games(root / "database/games.json")
    queue_path = root / "reports/provider_cooldown.json"
    if queue_path.exists() and not refresh:
        cooldown = read_json(queue_path).get("retry_after")
        if cooldown and datetime.fromisoformat(cooldown) > datetime.now(timezone.utc):
            print("SteamGridDB cooldown active; saved progress retained until", cooldown)
            return []
    client = client or HttpClient(root, config)
    api = SteamGridDB(client, refresh=refresh)  # Missing keys are fatal even for empty batches.
    mapping_path = root / "database/steamgriddb_mapping.json"
    mappings = read_json(mapping_path) if mapping_path.exists() else {}
    maximum = config["batch_size"] if limit is None else limit
    if not 1 <= maximum <= 1000:
        raise ValueError("Batch size must be between 1 and 1000")
    events, ambiguous, count, last_attempted = [], [], 0, None
    started = time.monotonic()
    previous_ambiguous = root / "reports/ambiguous_matches.json"
    review_by_id = {row["title_id"]: row for row in read_json(previous_ambiguous)} if previous_ambiguous.exists() else {}
    ordered = queued_games(root, games, "fetch")
    restoration_batch = any(needs_restore(game, config) for game in ordered)
    if restoration_batch:
        ordered = [game for game in ordered if needs_restore(game, config)]
    for game in ordered:
        ident = game["title_id"]
        if game.get("artwork_status") == "generated" and ident not in replace and not refresh:
            continue
        if not eligible(game, config, refresh=refresh, replace=replace):
            continue
        if count >= maximum or time.monotonic() - started >= config.get("batch_time_seconds", 1200):
            break
        count += 1
        last_attempted = ident
        try:
            if needs_restore(game, config):
                try:
                    event = restore_source(game, root, client, config)
                    record(game, config, {"status": "selected"})
                    events.append(event)
                    continue
                except RateLimitError:
                    raise
                except (DownloadError, ValueError, OSError):
                    # Fall through to the official API if the old URL changed.
                    pass
            mapping, suggestions = resolve(game, api, mappings.get(ident))
            if not mapping:
                review_by_id[ident] = {"title_id": ident, "title": game["title"], "candidates": suggestions,
                                      "reason": "No unique exact title and release match; verify game ID manually"}
                events.append({"title_id": ident, "status": "ambiguous_match" if suggestions else "missing_game"})
                record(game, config, events[-1])
                continue
            review_by_id.pop(ident, None)
            previous_asset = mappings.get(ident, {}).get("asset_id") if not refresh else None
            mappings[ident] = mapping
            game["match_confidence"] = mapping["confidence"]
            game["steamgriddb_game_id"] = mapping["game_id"]
            override = config.get("overrides", {}).get(ident, {})
            asset_id = override.get("asset_id")
            if asset_id is not None and (type(asset_id) is not int or asset_id <= 0):
                raise ValueError("Override asset_id must be a positive integer")
            selected = False
            previews = []
            # 1024 is queried if 512 is absent or every 512 candidate fails decoding.
            for size in (512, 1024):
                all_rows = api.grids(mapping["game_id"], size)
                rows = ranked(all_rows, size)
                if not asset_id and previous_asset:
                    rows.sort(key=lambda row: row["id"] != previous_asset)
                previews.extend({"asset_id": r["id"], "url": r["url"], "score": score(r),
                                 "page": f"https://www.steamgriddb.com/grid/{r['id']}"} for r in rows[:10])
                if asset_id:
                    rows = [r for r in rows if r["id"] == asset_id]
                    if not rows and size == 1024:
                        # A manual asset may be beyond the API's first page. The asset
                        # detail must explicitly identify this game before accepting it.
                        row = api.grid(asset_id)
                        row_game = row.get("game")
                        belongs = row_game.get("id") if isinstance(row_game, dict) else row.get("game_id")
                        if belongs == mapping["game_id"]:
                            rows = ranked([row])
                for row in rows[:5]:
                    try:
                        url = row["url"]
                        client.check_url(url, config["allowed_hosts"])
                        cache_path = root / ".cache/downloads" / (digest(url.encode()) + ".json")
                        cached = read_json(cache_path) if cache_path.exists() else None
                        path = safe_path(root / "sources", cached["path"]) if cached else None
                        if refresh or path is None or not path.exists() or file_hash(path) != cached["sha256"]:
                            data = client.get(url, config["allowed_hosts"])
                            checksum = digest(data)
                            path = safe_path(root / "sources", "downloads/" + checksum + ".image")
                            path.parent.mkdir(parents=True, exist_ok=True)
                            path.write_bytes(data)
                            write_json(cache_path, {"path": path.relative_to(root / "sources").as_posix(), "sha256": checksum})
                        info = inspect_source(path, config)
                        if info["dimensions"] != [row["width"], row["height"]]:
                            raise ValueError("Downloaded dimensions disagree with API metadata")
                        source = {"provider": "steamgriddb", "url": url, "provider_artwork_id": row["id"],
                                  "format": info["format"], "dimensions": info["dimensions"],
                                  "path": path.relative_to(root / "sources").as_posix(),
                                  "source_page": f"https://www.steamgriddb.com/grid/{row['id']}",
                                  "attribution": (row.get("author") or {}).get("name", "Unknown SteamGridDB contributor"),
                                  "license": "Third-party artwork; redistribution unverified", "redistribution": "unverified"}
                        rights = override.get("rights", {})
                        # Rights approval is scoped to one specific asset, never a whole game.
                        if asset_id == row["id"]:
                            source.update({k: rights[k] for k in ("redistribution", "license", "permission_evidence") if k in rights})
                        if game.get("artwork_status") == "generated":
                            if file_hash(path) != game.get("source_sha256") or row["id"] != (game.get("source") or {}).get("provider_artwork_id"):
                                game["pending_source"] = source
                        else:
                            game["source"] = source
                        # The same verified SGDB identity + exact asset is an explicit
                        # equivalence, independent of filename similarity.
                        for canonical in games:
                            if canonical is game or canonical.get("shared_with"):
                                continue
                            if (canonical.get("steamgriddb_game_id") == mapping["game_id"]
                                    and (canonical.get("source") or {}).get("provider_artwork_id") == row["id"]
                                    and canonical.get("match_confidence") in {"exact", "manual"}
                                    and (canonical.get("artwork_status") in {"generated", "restricted"}
                                         or canonical.get("fetch_state", {}).get("status") == "selected")):
                                game["shared_with"] = canonical["title_id"]
                                break
                        mapping["asset_id"] = row["id"]
                        mapping["asset_selection"] = "manual" if asset_id else "ranked-pending-review"
                        mapping["previews"] = previews
                        events.append({"title_id": ident, "status": "selected", "asset_id": row["id"],
                                       "game_id": mapping["game_id"], "url": url, "source_sha256": file_hash(path),
                                       "dimensions": info["dimensions"], "match_confidence": mapping["confidence"],
                                       "selection": mapping["asset_selection"], "warnings": info["warnings"]})
                        record(game, config, events[-1])
                        selected = True
                        break
                    except RateLimitError:
                        raise
                    except (DownloadError, ValueError, OSError) as error:
                        events.append({"title_id": ident, "status": "candidate_rejected", "asset_id": row["id"], "message": str(error)})
                if selected:
                    break
            if not selected:
                events.append({"title_id": ident, "status": "missing_square", "previews": previews})
                record(game, config, events[-1])
        except RateLimitError as error:
            events.append({"title_id": ident, "status": "provider_unavailable", "message": str(error)})
            record(game, config, events[-1])
            write_json(queue_path, {"retry_after": error.retry_after or game["fetch_state"]["retry_after"]})
            break
        except DownloadError as error:
            events.append({"title_id": ident, "status": "provider_unavailable", "message": str(error)})
            record(game, config, events[-1])
    write_json(root / "database/games.json", games)
    write_json(mapping_path, mappings)
    if last_attempted:
        advance_queue(root, "fetch", last_attempted)
    write_json(root / "reports/ambiguous_matches.json", list(review_by_id.values()))
    write_json(root / "reports/download_results.json", events)
    return events
