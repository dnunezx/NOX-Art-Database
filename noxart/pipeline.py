from __future__ import annotations

import json
import io
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from .common import advance_queue, digest, file_hash, load_games, queued_games, read_json, safe_path, settings_for, write_json
from .imaging import inspect_source, save_png, square_image, validate_png


def generate(root, database="database/games.json", config_file="config.json", limit=None, replace=()):
    root = Path(root)
    config = read_json(safe_path(root, config_file))
    games = load_games(safe_path(root, database))
    batch = limit if limit is not None else config["batch_size"]
    if not 1 <= batch <= 1000:
        raise ValueError("Batch size must be between 1 and 1000")
    replacement_ids = set(replace)
    if replacement_ids - {g["title_id"] for g in games}:
        raise ValueError("Unknown replacement Title ID")
    events = []
    count = 0
    last_attempted = None
    for game in queued_games(root, games, "generate"):
        if game.get("shared_with"):
            continue
        ident = game["title_id"]
        output = safe_path(root / "art", ident + ".png")
        source = (game.get("pending_source") if ident in replacement_ids else None) or game.get("source") or {}
        source_path = safe_path(root / "sources", source["path"]) if source.get("path") else None
        if game.get("artwork_status") == "restricted" and not (source_path and source_path.is_file()):
            continue
        if not output.exists() and (not source_path or not source_path.is_file()):
            # Lookup state reports missing art; don't spend processing slots on
            # titles for which this runner has no downloaded source.
            continue
        if output.exists() and ident not in replacement_ids:
            validate_png(output, 512, config)
            if not game.get("artwork"):
                # Adopt pre-existing valid NOX art without inventing rights or approval.
                checksum = file_hash(output)
                thumb_path = ident + ".png" if config["thumbnails"] else None
                if thumb_path:
                    with Image.open(output) as existing:
                        save_png(existing.resize((256, 256), Image.Resampling.LANCZOS), safe_path(root / "thumbnails", thumb_path))
                game.update(artwork_status="generated", artwork=ident + ".png", thumbnail=thumb_path,
                            sha256=checksum, source_sha256=checksum,
                            thumbnail_sha256=file_hash(safe_path(root / "thumbnails", thumb_path)) if thumb_path else None,
                            source={"provider": "existing", "attribution": "Existing NOX artwork; provenance requires review", "redistribution": "unverified"},
                            source_dimensions=[512, 512], generated_at=datetime.now(timezone.utc).isoformat(),
                            processing_method="preserved", processing_settings={}, review_status="pending")
            message = "Existing artwork preserved"
            if source_path and source_path.exists() and game.get("source_sha256") != file_hash(source_path):
                message += "; source changed, explicit replacement required"
            if game.get("pending_source"):
                message += "; changed remote source awaits explicit replacement"
            if game.get("processing_settings") != settings_for(config, game):
                message += "; processing settings changed, explicit replacement required"
            events.append({"title_id": ident, "status": "preserved", "message": message})
            continue
        if count >= batch:
            continue
        count += 1
        last_attempted = ident
        try:
            if not source_path or not source_path.is_file():
                raise ValueError("No permitted source image available")
            info = inspect_source(source_path, config)
            settings = settings_for(config, game)
            image, method = square_image(source_path, settings)
            encoded = io.BytesIO()
            image.save(encoded, format="PNG", optimize=True)
            output_hash = digest(encoded.getvalue())
            conflict = next((other for other in games if other is not game and not other.get("shared_with")
                             and other.get("sha256") == output_hash), None)
            if conflict:
                # Unverified duplicate content is a per-title review task, never
                # a reason to discard the progress of an entire catalog batch.
                game["fetch_state"] = {**game.get("fetch_state", {}), "status": "duplicate_review"}
                events.append({"title_id": ident, "status": "duplicate_review", "conflicts_with": conflict["title_id"]})
                continue
            save_png(image, output)
            thumb_path = None
            if config["thumbnails"]:
                thumb_path = ident + ".png"
                save_png(image.resize((256, 256), Image.Resampling.LANCZOS), safe_path(root / "thumbnails", thumb_path))
            game.update(artwork_status="generated", artwork=ident + ".png", thumbnail=thumb_path,
                        source=source,
                        source_sha256=file_hash(source_path), sha256=file_hash(output),
                        thumbnail_sha256=file_hash(safe_path(root / "thumbnails", thumb_path)) if thumb_path else None,
                        generated_at=datetime.now(timezone.utc).isoformat(), processing_method=method,
                        processing_settings=settings, processing_sha256=digest(json.dumps(settings, sort_keys=True).encode()),
                        source_dimensions=info["dimensions"], quality_warnings=info["warnings"], review_status="pending")
            game.pop("pending_source", None)
            game.pop("publication_status", None)
            game.pop("review_method", None)
            game.pop("approval_reason", None)
            approval = config.get("overrides", {}).get(ident, {})
            if (approval.get("asset_id") == source.get("provider_artwork_id")
                    and approval.get("approved_sha256") == game["sha256"]):
                game.update(review_status="approved", reviewed_sha256=game["sha256"], review_method="manual",
                            approval_reason="Explicit asset and checksum override")
            events.append({"title_id": ident, "status": "generated", **info})
        except (ValueError, OSError) as error:
            events.append({"title_id": ident, "status": "missing", "message": str(error)})
            if not output.exists():
                game["artwork_status"] = "missing"
    # Resolve verified aliases after canonical artwork, independent of entry order.
    by_id = {g["title_id"]: g for g in games}
    for game in games:
        if not game.get("shared_with"):
            continue
        canonical = by_id[game["shared_with"]]
        while canonical.get("shared_with"):
            canonical = by_id[canonical["shared_with"]]
        if canonical.get("artwork_status") in {"generated", "restricted"}:
            for key in ("artwork", "thumbnail", "sha256", "thumbnail_sha256", "source", "source_sha256", "generated_at",
                        "processing_method", "processing_settings", "processing_sha256", "source_dimensions", "quality_warnings",
                        "steamgriddb_game_id", "match_confidence"):
                game[key] = canonical.get(key)
            if game.get("sha256") != game.get("reviewed_sha256"):
                game["review_status"] = "pending"
                game.pop("review_method", None)
                game.pop("approval_reason", None)
            game["artwork_status"] = canonical["artwork_status"]
    write_json(safe_path(root, database), games)
    if last_attempted:
        advance_queue(root, "generate", last_attempted)
    write_json(root / "reports/processing.json", events)
    return events
