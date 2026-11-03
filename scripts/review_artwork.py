"""Explicit human review operation; approvals are bound to output bytes."""
import argparse
from pathlib import Path

from noxart.common import load_games, safe_path, write_json
from noxart.release import validate


def approve(root, ids, database="database/games.json"):
    games = validate(root, database)
    selected = set(ids)
    by_id = {g["title_id"]: g for g in games}
    if not selected or selected - by_id.keys():
        raise ValueError("Specify known Title IDs to approve")
    for ident in selected:
        game = by_id[ident]
        if game.get("artwork_status") != "generated":
            raise ValueError("Only generated artwork can be reviewed")
        game.update(review_status="approved", reviewed_sha256=game["sha256"])
    write_json(safe_path(root, database), games)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Approve artwork you have visually inspected; does not grant redistribution permission")
    parser.add_argument("title_ids", nargs="+")
    parser.add_argument("--database", default="database/games.json")
    args = parser.parse_args()
    approve(Path.cwd(), args.title_ids, args.database)
