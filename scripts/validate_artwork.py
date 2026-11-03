from pathlib import Path
from noxart.release import validate

if __name__ == "__main__":
    print(f"Validated {len(validate(Path.cwd()))} game entries")
