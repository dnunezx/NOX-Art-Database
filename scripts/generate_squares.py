import argparse
from pathlib import Path

from noxart.pipeline import generate


def main():
    parser = argparse.ArgumentParser(description="Generate deterministic 512px NOX artwork")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--database", default="database/games.json")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--replace", nargs="*", default=[])
    args = parser.parse_args()
    events = generate(args.root, args.database, args.config, args.limit, args.replace)
    print(f"Processed {len(events)} entries; see reports/processing.json")


if __name__ == "__main__":
    main()
