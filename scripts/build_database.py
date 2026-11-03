import argparse
from pathlib import Path
from noxart.common import read_json
from noxart.release import manifest

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Fail if the committed manifest is stale")
    args = parser.parse_args()
    path = Path.cwd() / "database/artwork_manifest.json"
    previous = read_json(path) if path.exists() else None
    current = manifest(Path.cwd())
    if args.check and previous != current:
        raise SystemExit("Committed artwork manifest is stale; run python -m scripts.build_database")
    print(f"Manifest contains {len(current['games'])} approved entries")
