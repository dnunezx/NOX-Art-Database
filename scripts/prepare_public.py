from pathlib import Path
from noxart.release import prepare_public

if __name__ == "__main__":
    prepare_public(Path.cwd())
