from pathlib import Path
from noxart.release import manifest

if __name__ == "__main__":
    print(f"Manifest contains {len(manifest(Path.cwd())['games'])} approved entries")
