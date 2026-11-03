"""The same end-to-end entry point used by GitHub Actions."""
import os
from pathlib import Path

from noxart.fetching import fetch
from noxart.pipeline import generate
from noxart.release import package, prepare_public, validate
from noxart.reporting import reports


def main():
    root = Path.cwd()
    limit = int(os.environ.get("NOX_LIMIT", "50"))
    fetch(root, limit, refresh=os.environ.get("NOX_REFRESH", "false").lower() == "true")
    generate(root, limit=limit, replace=os.environ.get("NOX_REPLACE", "").split())
    validate(root)
    prepare_public(root)
    validate(root)
    reports(root)
    package(root)
    print("Validated pack, reports and manifest are ready in dist/, reports/ and database/")


if __name__ == "__main__":
    main()
