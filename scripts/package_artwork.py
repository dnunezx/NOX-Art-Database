from pathlib import Path
from noxart.release import package

if __name__ == "__main__":
    print(package(Path.cwd()))
