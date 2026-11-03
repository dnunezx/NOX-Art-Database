from pathlib import Path
from noxart.common import load_games, redistribution_allowed
from noxart.common import read_json


def check(root):
    path = root / "database/artwork_credits.json"
    credits = read_json(path).get("games", {}) if path.exists() else {}
    for game in load_games(root / "database/games.json"):
        if game.get("artwork_status") == "generated" and not redistribution_allowed(game):
            raise ValueError(f"Unverified image must not be committed publicly: {game['title_id']}; run prepare_public")
        if game.get("artwork_status") == "generated" and (game.get("source") or {}).get("provider") == "steamgriddb":
            credit = credits.get(game["title_id"])
            source = game["source"]
            if not credit or credit.get("creator") != source.get("attribution") or credit.get("source_page") != source.get("source_page"):
                raise ValueError(f"Missing artwork credit: {game['title_id']}")


if __name__ == "__main__":
    check(Path.cwd())
