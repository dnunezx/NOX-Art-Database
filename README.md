# NOX Art Database

Automated square artwork for the NOX PlayStation 3 launcher. Python 3.11+ and
Pillow generate deterministic **512 × 512 PNGs** and optional **256 × 256 thumbnails**.
Everything runs on GitHub Actions; a local PC is optional.

The initial database contains **four original geometric demos**, with synthetic
`NOXS` IDs. These are not real PS3 games. No third-party game artwork or credentials
are included. Replace the demo entries and remove their outputs when adding your
real catalog. See [reference research](docs/RESEARCH.md) and the
[NOX integration contract](docs/NOX-INTEGRATION.md).

## Quick start

```sh
python -m pip install -r requirements.txt
python -m unittest discover -v
python -m scripts.run_pipeline
```

The result is `dist/nox-artwork.zip`, `dist/SHA256SUMS`,
`database/artwork_manifest.json` and review reports in `reports/`.
The bundled demo outputs are already approved. Newly generated artwork always
starts with pending visual review and is excluded from the ZIP until approved.

## GitHub setup

1. Merge the implementation into the repository's default branch.
2. Enable GitHub Actions. Under **Settings → Actions → General**, allow Actions to create pull requests. Workflows request write access only for the generation PR job and release job; other jobs have read access.
3. Open **Actions → Generate Artwork → Run workflow**. It also runs when relevant inputs change and every Monday at 07:17 UTC, with a default batch of 50 games and a 25-minute timeout. Change or remove the schedule as desired.
4. Download the `nox-artwork-…` artifact from the successful run. It contains the approved ZIP, checksum, manifest and reports. Review `contact-sheet.html` locally.
5. Review and merge the `automation/artwork-update` PR. The PR body lists title, ID, source dimensions, output, validation, provider, usage status and review state. Existing valid artwork is preserved; no workflow silently commits to main.
6. To publish, run **Publish Database** from the default branch with a version such as `v1.0.0`. Leave `publish` unchecked to build only an artifact. Check it to create a versioned release after validation. Optionally configure required reviewers on the `artwork-releases` environment to add a release approval gate.

PR validation uses no external API secrets. PRs opened by `GITHUB_TOKEN` may not
trigger another workflow automatically; generation already runs tests and output
validation. Dispatch Validate Artwork on the update branch or use the repository's
normal protected-branch review process. API keys must never be placed in game JSON.

## Add sources and games

Place images under `sources/`. Map each exact Title ID in `database/games.json`:

```json
[
  {
    "title_id": "BLUS12345",
    "title": "Your verified game title",
    "platform": "PS3",
    "region": "US",
    "artwork_status": "missing",
    "source": {
      "provider": "local",
      "path": "BLUS12345/ICON0.PNG",
      "attribution": "Actual rights holder or contributor",
      "redistribution": "unverified"
    }
  }
]
```

That ID is illustrative. Use actual IDs verified against your game metadata.
Local discovery also checks `TITLEID.png`, then `TITLEID/ICON0.PNG`, `PIC0.PNG`,
and `PIC1.PNG`; an explicit path takes priority. Generic source folders are ignored
by git. Commit a permitted source intentionally with `git add -f` when you want
Actions to process it; placing a file only on your PC does not upload it to Actions.
Do not commit an extracted game asset without redistribution permission.

Run the individual tools from the repository root:

```sh
python -m scripts.fetch_artwork --limit 50
python -m scripts.generate_squares --limit 50
python -m scripts.validate_artwork
python -m scripts.generate_report
python -m scripts.review_artwork BLUS12345
python -m scripts.build_database
python -m scripts.package_artwork
```

Record `source.redistribution: "approved"`, the real `license`, `attribution` and
`permission_evidence` only after establishing redistribution rights. Visual
approval and permission are separate: the review command records `reviewed_sha256`
but does not grant rights. Editing a checksum or replacing bytes invalidates review.
Run `prepare_public` before committing metadata for restricted artwork; it removes
restricted image files and clears their public output paths. Keep private sources
outside public Git history. The Actions entry point does this automatically, and
public validation rejects generated images with unverified permissions.

For verified regional equivalents, add `shared_with: "CANONICAL_TITLE_ID"` instead
of a source. Aliases have independent visual approval and require the canonical
entry to be approved too. Unknown targets and cycles fail validation. Filename or
title similarity never establishes equivalence.

## Cropping and preservation

`config.json` controls batch size, provider order, limits and thumbnails. Overrides
are keyed by Title ID:

```json
{
  "BLUS12345": {
    "method": "crop",
    "focal_point": [0.5, 0.25],
    "zoom": 1.1,
    "rotation": 0,
    "background": "blur",
    "preserve_full": false,
    "source_preference": "local"
  }
}
```

Put that object inside `overrides`. Focal points use normalized source coordinates.
`method` supports `auto`, `crop` or `fit`; `background` supports `blur` or `dark`.
Auto crops near-squares and fits rectangular sources over a darkened background,
preserving logos and characters. Crop is a proportional square crop, never a stretch.
`preserve_full` forces fit; zoom applies to crop only. Rotation is counterclockwise.
There is no AI generation or subject detector in this version; use focal points or
full-image fit for difficult art. Inspect artwork with embedded borders manually.

Existing valid artwork is preserved, including when a source or settings change.
Changes are reported, then require an explicit replacement:

```sh
python -m scripts.fetch_artwork --refresh
python -m scripts.generate_squares --replace BLUS12345
```

Refresh records changed remote candidates as `pending_source` without changing
existing output provenance. Replacement resets visual approval. Restricted entries
are skipped during routine lookups; use refresh after updating their permissions.
The manual Generate Artwork workflow has a `replace` field for the same explicit
approval, so replacements do not require a local PC. Batch cursors in
`reports/queue.json` rotate past failed entries so one missing source cannot prevent
later games from being processed.

## Online providers

Providers run in configured order, sequentially (concurrency one). Local sources
work without credentials. Online providers are disabled by default.

**SteamGridDB:** create an API key in your SteamGridDB account's API preferences,
save it as the repository Actions secret `STEAMGRIDDB_API_KEY`, then enable the
provider in config. For local use set the environment variable securely. Without a
verified `steamgriddb_game_id`, autocomplete results are reported as suggestions;
nothing is automatically matched to a PS3 release. Set a verified numeric game ID
and record `provider_permissions.steamgriddb.download_approved: true` plus
`download_permission_evidence` before image retrieval. Optional redistribution
fields use the same source schema. Per-image attribution and grid page are recorded.
Download permission alone does not authorize publication.

**GameTDB:** direct site access was blocked during research. Set an explicit,
verified GameTDB image `source.url`, provider `gametdb`, `download_approved: true`
and `download_permission_evidence`, then enable the adapter. Only allowlisted HTTPS
hosts are accepted. There is no automatic GameTDB title lookup or undocumented CDN
endpoint. See [the research notes](docs/RESEARCH.md).

New adapters implement `candidates(game, root, client, config, refresh=False)` and
register in `noxart/fetching.py`. Discovery must not imply permission. Configure an
exact host allowlist and use the shared bounded HTTP client.

## Quality, security and scaling

Source validation rejects corrupt, blank, fully transparent, excessively small,
oversized, animated or extreme-aspect images. Low color variation and small files
produce review warnings; dark or minimalist art is not rejected just for low
variation. Outputs are validated for PNG format, dimensions, mode, size, checksums,
provenance, duplicate IDs, orphan files and unverified duplicate content. Intentional
duplicates require `shared_with`. Perceptual hashing is not implemented.

Downloads have a 20 MiB limit, 15-second per-request timeout, at most two retries,
public-IP checks, exact HTTPS host allowlists and validated redirects. Bearer tokens
are only sent to the API host and authenticated redirects are rejected. HTTP 429
defers the host for the batch; provider failures are reported without hiding errors
in local configuration. Images are capped at 40 million pixels. Nothing downloaded
is executed, and the generator extracts no archives.

Metadata is cached under `.cache/metadata`; source downloads use URL-indexed,
checksum-verified content-addressed files. Routine generation preserves existing
outputs and avoids recompression. Actions caches provider metadata only; restricted
source images are never uploaded as artifacts or caches. Larger databases should
retain conservative batch sizes and monitor storage and runtime.

The JSON schema is `database/games.schema.json`; runtime validation additionally
checks cross-entry constraints, filesystem references and checksums. ZIP contents
are selected from the approved manifest, with sorted names and fixed ZIP timestamps.
The ZIP hash is recorded in `SHA256SUMS`. Release consumers must trust their manifest
origin as well as checking image hashes.

## Development and scope

The offline tests synthesize legal sample art and mock provider APIs. They cover
conversion, focal crops, transparency, quality failures, duplicates, IDs, aliases,
source changes, metadata updates, manifests, rights gates, packages and network
failures. `scripts/create_samples.py` reproduces the four CC0 demo sources;
`examples/games.json` contains their initial mappings.

The implementation provides local generation, optional authorized provider lookup,
database/review automation, release packaging and the launcher manifest contract.
It does not supply a verified complete PS3 title catalog, provider permission grants,
or a hardware-tested NOX downloader. Those require real catalog contributions,
rights verification and launcher integration work.
