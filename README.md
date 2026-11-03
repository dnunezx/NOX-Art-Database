# NOX Art Database

Individual 512px square artwork for the NOX PlayStation 3 launcher, supplied through
[SteamGridDB](https://www.steamgriddb.com/), with contributor credits and source links.

## Individual downloads

The layout follows [CosmicScale's art database](https://github.com/CosmicScale/psbbn-art-database/tree/main/art):

```text
art/BCUS98111.png
thumbnails/BCUS98111.png
database/individual_manifest.json
CREDITS.md
```

Direct URL: `https://raw.githubusercontent.com/dnunezx/NOX-Art-Database/main/art/BCUS98111.png`.
The [individual manifest](database/individual_manifest.json) supplies actual download
URLs and SHA-256 hashes. Verified equivalents can share a canonical file. ZIPs are optional.

Every hosted image is credited in [CREDITS.md](CREDITS.md),
`database/artwork_credits.json`, and its full game record. Credits include the API's
contributor name, SteamGridDB asset page, original URL and PS3 Title ID. The repository
owner has authorized publication with attribution; the [artwork policy](docs/ARTWORK-POLICY.md)
records this without claiming NOX ownership or inventing a Creative Commons license.

Conclusive game matches with validated square images are approved and published
automatically. Only inconclusive matches, quality warnings or duplicate conflicts
need review. Rejected assets,
ambiguous identities, unsafe content flags and invalid images remain excluded.

## Automation

The catalog contains **1,238 US disc Title IDs**, excluding explicit demos and PSN-only
titles. [Catalog provenance and scope](docs/US-CATALOG.md) document the source and
metadata warnings; this reflects upstream coverage, not independently verified completeness.

**NOX — Fetch PS3 Artwork** runs hourly, attempts up to 100 eligible titles, saves
progress and pushes images and metadata directly to `main`. Previously removed
images are restored first from recorded source URLs, with source checksums verified.
Normal batches then resume. No automated pull request is required.

Completed images are skipped. Missing artwork retries after seven days; ambiguous
matches wait for a mapping change or explicit refresh. Requests are sequential and
paced. HTTP 429 stops a batch and persists the provider's cooldown. Each job has a
20-minute soft processing budget and 25-minute timeout.

Follow [progress](reports/progress.md), [matching review](reports/ambiguous_matches.json),
and [download results](reports/download_results.json). Workflow review artifacts contain
`reports/contact-sheet.html`. Scheduled runs avoid repeated artifact uploads.

Browse the [artwork review gallery](reports/artwork-review.md) directly on GitHub.
It separates inconclusive, approved and rejected selections, with thumbnails, full-size
images and creator/source links. To save your decisions, open **Actions → NOX —
Review Artwork → Run workflow**, enter the reviewed Title IDs and choose approve
or reject. Approved selections stay in place; rejection removes that entry from
delivery while retaining its source metadata. The [matching review page](reports/matching-review.md)
lists candidate game identities separately.

## Setup and use

1. Add `STEAMGRIDDB_API_KEY` to **Settings → Secrets and variables → Actions**.
   Get a key from [SteamGridDB API preferences](https://www.steamgriddb.com/profile/preferences/api).
2. Run **Actions → NOX — Fetch PS3 Artwork**, or let the hourly schedule continue.
3. Browse `art/` and `thumbnails/`. Files, indexes and credits update in the same commit.

The fetch job has content-write permission; validation jobs are read-only. API keys
are used only by the fetch step and never logged, committed or embedded in NOX.
**NOX — Package Artwork** optionally creates versioned ZIPs; no release is automatic.

SteamGridDB is the only online image provider. Sources must already be static 512px
or 1024px squares; native 512px grids have priority. Larger squares use Lanczos
downscaling, with no cropping, stretching, background composition or AI. Outputs are
RGB/RGBA PNG, plus optional 256px thumbnails. Content flags, actual file decoding,
dimensions, format, size, hashes, duplicate identity and paths are validated.

Matching requires a unique exact normalized name and release year when supplied.
Remaster/edition words are preserved. Use `alternate_titles`, or a verified
`steamgriddb_game_id` with `mapping_approved: true`, to resolve uncertain matches.
Choose an image in `config.json` → `overrides` → `TITLEID` → `asset_id`. Existing
valid artwork is preserved; use the workflow's `replace` field to authorize replacement.
Manual review can override automatic approval and is checksum-bound. Explicitly rejected or denied assets
are not automatically published. Image ranking is based on metadata, not visual AI.

## Development

Python 3.11+ is supported. Set the API key in your environment through a secret manager.

```sh
python -m pip install -r requirements.txt
python -m unittest discover -v
python -m scripts.run_pipeline
```

Offline tests use original synthetic fixtures and mocked APIs. A live test requires
explicit `NOX_LIVE_TEST=true` plus credentials. Tools include `fetch_artwork`,
`generate_squares` (native-square normalization only), `validate_artwork`,
`generate_report`, `publish_individual`, `generate_manifest` and optional `package_artwork`.
Use `import_us_discs` for an updated GameDB catalog, or `import_games` for verified JSON.

Downloads enforce HTTPS host allowlists, public addresses, safe redirects, byte limits
and timeouts. Credential failures, malformed API responses and programming errors
fail clearly. Attribution is checked before committing images. The optional packs
also contain credits.

NOX should remain functional offline, with optional individual cached downloads.
Never distribute a shared SteamGridDB API key in the launcher. See
[integration](docs/NOX-INTEGRATION.md), [API research](docs/RESEARCH.md) and
[verification history](docs/VERIFICATION.md). PS3 hardware integration remains future work.
