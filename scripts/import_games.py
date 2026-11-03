"""Import a JSON array of verified Title IDs and names; never overwrite entries."""
import argparse
from pathlib import Path
from noxart.common import load_games, write_json


def import_games(root, incoming):
    games = load_games(root / "database/games.json")
    additions = load_games(incoming)
    known = {g["title_id"] for g in games}
    games.extend(g for g in additions if g["title_id"] not in known)
    write_json(root / "database/games.json", games)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("json_file", type=Path)
    args = parser.parse_args()
    import_games(Path.cwd(), args.json_file)
