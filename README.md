# NOX Art Database v2

PS3 Title ID → SteamGridDB game → native square grid → validated PNG → review → pack.
SteamGridDB is the **only online artwork provider**. Sources must already be static
512 × 512 or 1024 × 1024 squares. Native 512px grids take priority; 1024px grids are
downscaled with Lanczos. No rectangular-cover fallback, cropping, effects or AI.

## Individual downloads (default)

NOX follows [CosmicScale's art database](https://github.com/CosmicScale/psbbn-art-database/tree/main/art):
one PNG per game, named by its exact Title ID, in a flat `art/` directory.

```text
art/BCUS98111.png
thumbnails/BCUS98111.png
database/individual_manifest.json
```

Once an image is approved for public distribution, its individual URL is:
`https://raw.githubusercontent.com/dnunezx/NOX-Art-Database/main/art/BCUS98111.png`.
The individual manifest supplies actual download URLs and SHA-256 hashes, plus
per-title source links when an image is not hosted. Unavailable files never get
fabricated download URLs. Regional aliases use their canonical artwork path.

The fetch workflow writes permitted artwork and provenance directly to `main`.
It no longer requires pull requests or ZIP downloads. ZIP packaging is optional:
select `build_zip` on a manual fetch, or run **NOX — Package Artwork** separately.
GitHub's workflow artifact is merely a review snapshot; clients use individual
raw PNG URLs for normal operation.

## Run on GitHub

1. Add `STEAMGRIDDB_API_KEY` under **Settings → Secrets and variables → Actions**.
   Obtain your key from [SteamGridDB API preferences](https://www.steamgriddb.com/profile/preferences/api).
2. Open **Actions → NOX — Fetch PS3 Artwork → Run workflow**. The initial list has
   five real PS3 titles, including God of War III (`BCUS98111`). Set `limit` to 1
   for a single-game test or 10 for the initial catalog.
3. Download the `nox-steamgriddb-…` artifact. It contains full database records,
   cached mappings, reports, a contact sheet and individual download indexes. ZIPs are optional.
4. Open `reports/contact-sheet.html` to inspect selected square art. Its images load
   directly from SteamGridDB; the HTML does not embed a private image cache.

Missing artwork is reported without failing the batch. Missing/invalid credentials,
malformed API responses, programming errors and invalid packages fail clearly.
No secrets are logged or included in artifacts. Validation jobs use read-only GitHub permissions. The fetch job has content-write
permission to commit validated public images and metadata directly to `main`; no PR
is created. API secrets are available only to the fetch step.

The fetch workflow also runs on catalog/code changes and weekly, bounded to ten
games by default. It caches API metadata, mappings and a rotating queue cursor;
unavailable titles cannot starve later entries. It never caches private source images
on GitHub. API access is sequential, paced and retried at most twice for transient
failures. HTTP 429 defers the host for the batch.

## What the artifact includes

- `database/games.json`: attribution, source URL, SteamGridDB IDs, source/output
  hashes, processing method, validation and review status.
- `database/steamgriddb_mapping.json`: matched identities, selected assets, confidence
  and alternate preview links.
- `reports/missing_artwork.json`, `ambiguous_matches.json`, `download_results.json`,
  `artwork_selections.json`, and `contact-sheet.html`.
- Optional ZIP mode: `dist/NOX-PS3-Artwork-v2-test.zip`, `NOX-PS3-Thumbnails-v2-test.zip`,
  `NOX-Artwork-Manifest.json`, `NOX-Missing-Artwork.json` and `SHA256SUMS`.

**Public packs include only visually approved artwork with documented redistribution
permission.** Until rights are established, individual records contain metadata and source links,
and previews link to the provider. This public repository does not automatically
upload unverified image files, including in Actions artifacts. Test processing still
downloads, decodes, converts, validates and hashes the actual images on the runner.

For an authorized personal cache, run locally with your own API credentials. After
visual review, `NOX_PRIVATE_PACK=true` creates a pack under `private-dist/`.
On Actions the `private_pack` option requires a **private repository**; public
repositories reject it. Private packs still require explicit visual approval and
must be used under applicable provider and artwork terms. No private cache is
published automatically.

## Catalog and matching

`database/games.json` is a JSON array. For example:

```json
[
  {
    "title_id": "BCUS98111",
    "title": "God of War III",
    "platform": "PS3",
    "region": "US",
    "release_year": 2010,
    "alternate_titles": []
  }
]
```

Names are normalized for case, punctuation, accents, trademark symbols and Roman
sequel numbers. The matcher searches all supplied aliases and verifies game details.
Only a unique exact name with matching `release_year` (when supplied) is accepted
automatically. Remaster and edition words are preserved. Fuzzy or multiple exact
matches require review. Never infer Title ID equivalence from filenames.

To resolve an ambiguous match, set `steamgriddb_game_id` after inspecting report
suggestions. A different regional name requires verified `alternate_titles`, or
`mapping_approved: true` with the explicit game ID. Regional entries can use
`shared_with: "BCUS98111"` only after equivalence is verified; aliases retain
independent visual approval. Unknown targets, cycles and unintended duplicate
images fail validation.

Import more verified IDs/names without replacing existing entries:

```sh
python -m scripts.import_games incoming-games.json
```

## Artwork selection and approval

The API requests static square grids with `nsfw=false`, `humor=false` and
`epilepsy=false`. Returned flags, dimensions and actual decoded content are checked.
Candidates rank by native 512px first, available numeric community score second,
then asset ID for reproducibility. Absent scores count as zero. The system cannot
prove that an unflagged image is official-looking or contains the right logo; every
automatic choice remains pending visual review. Alternative previews are reported.

Choose a specific asset in `config.json`:

```json
{
  "overrides": {
    "BCUS98111": {
      "asset_id": 123456,
      "approved_sha256": "the actual generated PNG SHA-256 after visual review",
      "rights": {
        "redistribution": "approved",
        "license": "actual applicable license or permission",
        "permission_evidence": "actual rights evidence"
      }
    }
  }
}
```

The asset ID and hash above are illustrative. Set real values from the downloaded
reports; omit `rights` until redistribution is established. Rights approval is scoped
to that asset, not to every image for a game. Visual approval can also be recorded
using `python -m scripts.review_artwork BCUS98111`. It does not grant redistribution
rights. Existing valid images are preserved. To replace explicitly, use the manual
workflow's `replace` field or `python -m scripts.generate_squares --replace BCUS98111`
after fetching a new candidate. New bytes reset visual approval. `refresh` checks
remote changes while retaining existing provenance until replacement is requested.

## Local use and tests

Python 3.11+ is supported. Set `STEAMGRIDDB_API_KEY` in your environment using your
normal secret manager; never put it in code, JSON or command history.

```sh
python -m pip install -r requirements.txt
python -m unittest discover -v
python -m scripts.run_pipeline
```

Individual modules remain available: `scripts.fetch_artwork`, `generate_squares`
(now square-only normalization), `validate_artwork`, `generate_report`,
`generate_manifest`, `publish_individual` and optional `package_artwork`. The implementation lives in `noxart/`
and `providers/steamgriddb.py`, rather than duplicate wrapper implementations.

Unit tests use original geometric fixtures created in memory and mocked HTTP/API
responses; no key is needed. An optional live test runs only with both
`NOX_LIVE_TEST=true` and `STEAMGRIDDB_API_KEY` set. The production Actions workflow
is the full real-API integration test.

## Validation, safety and delivery

Downloads use HTTPS with exact host allowlists, public-address checks, validated
redirects, 15-second timeouts, byte limits and bounded exponential retry. Authenticated
redirects are rejected. API response schemas are validated; Bearer headers are sent
only to the official API host. Sources are capped at 20 MiB and 1024px square, reject
animation and corrupt/blank images, and decode PNG/JPEG/WebP by actual content.
RGB/RGBA PNG conversion preserves composition and transparency. Low color variation
is a warning rather than grounds to reject intentionally dark art.

Outputs are 512px PNGs and optional 256px thumbnails, with SHA-256 checksums. Manifest
paths are validated and duplicate files require explicit aliases. ZIP names are safe,
entries sorted and timestamps fixed. `NOX — Package Artwork` validates again before
building. Set its publish option only after recording rights; versioned public releases
are gated by the same approval and permission checks. No release is automatic.

The future NOX launcher can use the lightweight approved manifest, verified cached
downloads, and an offline fallback. Online retrieval stays optional. Never embed a
shared SteamGridDB key in a public launcher. Use approved public packs or a user-owned
companion fetcher with that user's credentials. See [integration notes](docs/NOX-INTEGRATION.md)
and [API research](docs/RESEARCH.md). Hardware integration remains future work.
