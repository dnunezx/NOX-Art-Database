# SteamGridDB artwork and attribution

The NOX repository owner has instructed this project to redistribute its selected
SteamGridDB artwork with creator credit and source links. This is the recorded
maintainer authorization for this repository's publication policy, rather than a
claim that all artwork has a Creative Commons license or that NOX owns the artwork.

For each published image, NOX records the contributor name supplied by SteamGridDB,
the SteamGridDB grid ID and page URL, the original image URL, the PS3 Title ID and
the published file's SHA-256. Human-readable credits are in `CREDITS.md`, with the
same details in `database/artwork_credits.json` and the full game database.

Original creators and game publishers retain their rights. NOX makes no ownership
claim over the images. Missing contributor names are identified as unknown with a
source link, never replaced by an invented author. Specific denied or rejected
assets remain excluded from automatic publication.

Conclusive game matches with validated static square artwork are approved and
published automatically. Automatic approval records the exact output checksum and
`review_method: automatic`, rather than pretending a person inspected the image.
Manual approvals and rejections keep `review_method: manual` and are preserved.
Only inconclusive identities, quality warnings and unrelated duplicates require
review. Unsafe content and invalid images are rejected by validation.

Provider: [SteamGridDB](https://www.steamgriddb.com/).
