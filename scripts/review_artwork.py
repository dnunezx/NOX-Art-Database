"""Explicit human review operation; approvals are bound to output bytes."""
import argparse
from pathlib import Path

from noxart.common import load_games, safe_path, write_json
from noxart.release import validate


def review(root, ids, decision="approve", database="database/games.json"):
    games = validate(root, database)
    selected = set(ids)
    by_id = {g["title_id"]: g for g in games}
    if not selected or selected - by_id.keys():
        raise ValueError("Specify known Title IDs to approve")
    for ident in selected:
        game = by_id[ident]
        if game.get("artwork_status") != "generated":
            raise ValueError("Only generated artwork can be reviewed")
        if decision not in {"approve", "reject"}:
            raise ValueError("Review decision must be approve or reject")
        game.update(review_status="approved" if decision == "approve" else "rejected",
                    reviewed_sha256=game["sha256"], review_method="manual", approval_reason="Repository owner review")
    write_json(safe_path(root, database), games)


def approve(root, ids, database="database/games.json"):
    review(root, ids, "approve", database)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Approve artwork you have visually inspected; does not grant redistribution permission")
    parser.add_argument("title_ids", nargs="+")
    parser.add_argument("--database", default="database/games.json")
    parser.add_argument("--decision", choices=["approve", "reject"], default="approve")
    args = parser.parse_args()
    review(Path.cwd(), args.title_ids, args.decision, args.database)
