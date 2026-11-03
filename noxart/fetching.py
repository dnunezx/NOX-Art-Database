from __future__ import annotations

from pathlib import Path

from providers import gametdb, local, steamgriddb
from .common import advance_queue, digest, file_hash, load_games, queued_games, read_json, safe_path, write_json
from .http import HttpClient
from .imaging import inspect_source

PROVIDERS = {"local": local, "gametdb": gametdb, "steamgriddb": steamgriddb}


def fetch(root, limit=None, refresh=False, client=None):
    root = Path(root)
    config = read_json(root / "config.json")
    games = load_games(root / "database/games.json")
    client = client or HttpClient(root, config)
    count, events = 0, []
    maximum = config["batch_size"] if limit is None else limit
    if not 1 <= maximum <= 1000:
        raise ValueError("Batch size must be between 1 and 1000")
    last_attempted = None
    for game in queued_games(root, games, "fetch"):
        if game.get("shared_with") or (not refresh and game.get("artwork_status") in {"generated", "restricted"}):
            continue
        if count >= maximum:
            break
        count += 1
        last_attempted = game["title_id"]
        selected = False
        order = config["provider_order"]
        preference = config.get("overrides", {}).get(game["title_id"], {}).get("source_preference")
        if preference:
            if preference not in order:
                raise ValueError("Unknown preferred provider")
            order = [preference] + [name for name in order if name != preference]
        for name in order:
            adapter = PROVIDERS.get(name)
            if adapter is None:
                raise ValueError("Unknown provider")
            provider = config["providers"].get(name, {})
            if name != "local" and not provider.get("enabled"):
                continue
            try:
                candidates = adapter.candidates(game, root, client, config, refresh)
                for candidate in candidates:
                    candidate = dict(candidate)
                    try:
                        if name == "local":
                            path = safe_path(root / "sources", candidate["path"])
                        else:
                            # API access and image download permission are separate decisions.
                            if candidate.get("download_approved") is not True or not candidate.get("download_permission_evidence"):
                                raise ValueError("Image download requires explicit provider permission and evidence")
                            url = candidate["url"]
                            cache_path = root / ".cache/downloads" / (digest(url.encode()) + ".json")
                            cached = read_json(cache_path) if cache_path.exists() else None
                            path = safe_path(root / "sources", cached["path"]) if cached else None
                            if refresh or path is None or not path.exists() or file_hash(path) != cached["sha256"]:
                                data = client.get(url, provider["allowed_hosts"])
                                checksum = digest(data)
                                path = safe_path(root / "sources", "downloads/" + checksum + ".image")
                                path.parent.mkdir(parents=True, exist_ok=True)
                                if not path.exists():
                                    path.write_bytes(data)
                                inspect_source(path, config)
                                write_json(cache_path, {"path": path.relative_to(root / "sources").as_posix(), "sha256": checksum})
                            candidate["path"] = path.relative_to(root / "sources").as_posix()
                        inspect_source(path, config)
                        if game.get("artwork_status") == "generated":
                            if file_hash(path) != game.get("source_sha256"):
                                game["pending_source"] = candidate
                                events.append({"title_id": game["title_id"], "status": "source_changed", "message": "Explicit replacement required"})
                        else:
                            game["source"] = candidate
                        events.append({"title_id": game["title_id"], "provider": name, "status": "selected", "source_sha256": file_hash(path)})
                        selected = True
                        break
                    except (ValueError, OSError) as error:
                        events.append({"title_id": game["title_id"], "provider": name, "status": "candidate_rejected", "message": str(error)})
                if selected:
                    break
            except (ValueError, OSError, KeyError, TypeError) as error:
                events.append({"title_id": game["title_id"], "provider": name, "status": "unavailable", "message": str(error)})
        if not selected:
            events.append({"title_id": game["title_id"], "status": "missing"})
    write_json(root / "database/games.json", games)
    if last_attempted:
        advance_queue(root, "fetch", last_attempted)
    write_json(root / "reports/fetch.json", events)
    return events
