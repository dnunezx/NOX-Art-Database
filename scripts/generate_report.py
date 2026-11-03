from pathlib import Path
from noxart.reporting import reports

if __name__ == "__main__":
    reports(Path.cwd())
