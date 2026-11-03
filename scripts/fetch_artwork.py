import argparse
from pathlib import Path
from noxart.fetching import fetch

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    parser.add_argument("--refresh", action="store_true", help="Refresh missing-title lookup metadata and downloaded sources")
    args = parser.parse_args()
    print(f"Recorded {len(fetch(Path.cwd(), args.limit, args.refresh))} provider events")
