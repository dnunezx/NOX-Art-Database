"""The same end-to-end entry point used by GitHub Actions."""
import os
from pathlib import Path

from noxart.fetching import fetch
from noxart.common import read_json, write_json
from noxart.pipeline import generate
from noxart.release import package, prepare_public, validate
from noxart.reporting import reports


def main():
    root = Path.cwd()
    state = root / ".cache/state"
    mapping_file = root / "database/steamgriddb_mapping.json"
    queue_file = root / "reports/queue.json"
    # Explicit committed mappings take precedence over restored automatic mappings.
    if (state / "mapping.json").exists():
        write_json(mapping_file, {**read_json(state / "mapping.json"), **(read_json(mapping_file) if mapping_file.exists() else {})})
    if (state / "queue.json").exists():
        write_json(queue_file, read_json(state / "queue.json"))
    limit = int(os.environ.get("NOX_LIMIT", "50"))
    replacement = os.environ.get("NOX_REPLACE", "").split()
    fetch(root, limit, refresh=os.environ.get("NOX_REFRESH", "false").lower() == "true", replace=replacement)
    generate(root, limit=limit, replace=replacement)
    validate(root)
    reports(root)
    if os.environ.get("NOX_PRIVATE_PACK") == "true":
        if os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("NOX_REPOSITORY_PRIVATE") != "true":
            raise ValueError("Private artwork packs cannot be uploaded from a public repository")
        package(root, private=True)
    prepare_public(root)
    validate(root)
    reports(root)
    package(root, version=os.environ.get("NOX_VERSION", "v2-test"))
    write_json(state / "mapping.json", read_json(mapping_file))
    if queue_file.exists():
        write_json(state / "queue.json", read_json(queue_file))
    from collections import Counter
    print("Batch results:", dict(Counter(g.get("artwork_status", "missing") for g in read_json(root / "database/games.json"))))
    print("Validated public packs, reports and manifest are ready in dist/, reports/ and database/")


if __name__ == "__main__":
    main()
