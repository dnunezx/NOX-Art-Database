from pathlib import Path
from noxart.common import load_games, redistribution_allowed


def check(root):
    for game in load_games(root / "database/games.json"):
        if game.get("artwork_status") == "generated" and not redistribution_allowed(game):
            raise ValueError(f"Unverified image must not be committed publicly: {game['title_id']}; run prepare_public")


if __name__ == "__main__":
    check(Path.cwd())
