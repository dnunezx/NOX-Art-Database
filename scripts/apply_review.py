"""Read human decisions from workflow input and refresh delivery/review pages."""
import os
import re
from pathlib import Path

from scripts.review_artwork import review
from scripts.check_public import check
from noxart.release import prepare_public, validate
from noxart.individual import individual_index
from noxart.reporting import reports


if __name__ == "__main__":
    root = Path.cwd()
    ids = [ident for ident in re.split(r"[\s,]+", os.environ.get("NOX_REVIEW_IDS", "").strip()) if ident]
    review(root, ids, os.environ.get("NOX_REVIEW_DECISION", "approve"))
    prepare_public(root)
    validate(root)
    check(root)
    individual_index(root)
    reports(root)
    print(f"Recorded review decisions for {len(ids)} Title IDs")
