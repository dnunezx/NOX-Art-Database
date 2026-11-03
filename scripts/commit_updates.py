"""Persist verified individual artwork and public metadata directly to main."""
import os
import subprocess
from pathlib import Path

from scripts.check_public import check
from noxart.release import validate


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


if __name__ == "__main__":
    if os.environ.get("GITHUB_REF") != "refs/heads/main":
        raise SystemExit("Database updates are only written from main")
    validate(Path.cwd())
    check(Path.cwd())
    run("git", "config", "user.name", "github-actions[bot]")
    run("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    run("git", "add", "--", "art", "thumbnails", "database", "reports")
    result = subprocess.run(["git", "diff", "--cached", "--quiet"])
    if result.returncode == 0:
        print("Individual artwork database is already up to date")
    elif result.returncode == 1:
        run("git", "commit", "-m", "Update individual NOX artwork and source metadata [skip ci]")
        run("git", "push", "origin", "HEAD:main")
    else:
        raise SystemExit("Could not inspect staged database changes")
