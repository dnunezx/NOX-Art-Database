# Reference study

Inspected 2026-11-02 before implementation. This is an independent Pillow/stdlib
implementation; no source code or artwork was copied from the reference projects.

- [PSBBN art downloader](https://github.com/CosmicScale/PSBBN-Definitive-Project/blob/main/scripts/helper/art_downloader.py): maps IDs through a pipe-delimited CSV to IGN title pages, parses image elements against a fixed domain priority, skips known generic images, then downloads to a temporary directory.
- [PSBBN installer](https://github.com/CosmicScale/PSBBN-Definitive-Project/blob/main/scripts/Game-Installer.sh): preserves local artwork first, tries its art database, then converts temporary images with ImageMagick. Squares are resized to 256px; rectangular images use a fixed 256px crop offset. Generated assets are reused by ID. It also submits missing-art reports and contributed artwork.
- [PSBBN art database README](https://github.com/CosmicScale/psbbn-art-database): describes community ID-tagged contributions, missing-art logs and reduced reliance on IGN. No general artwork redistribution license was established. NOX copies none of those images and uses no IGN scraping or automatic external submissions.

NOX adopts local-first preservation, explicit ID mapping, caching and missing-art
reporting. It uses configurable focal points and full-image compositions instead
of a fixed crop, produces 512px PNGs, records provenance and checksums, and requires
separate visual approval and redistribution permission before packaging.

## Providers

[GameTDB PS3 Downloads](https://www.gametdb.com/PS3/Downloads) advertises PS3 cover
packs and a downloadable database. Direct access returned HTTP 403 during research,
so automated download interfaces and redistribution terms could not be verified.
The adapter therefore accepts only a maintainer-supplied, Title-ID-matched HTTPS
image URL with recorded download permission. It does not invent an API, construct
CDN paths or scrape pages. Automatic GameTDB title lookup remains unavailable until
a documented authorized interface is established.

[SteamGridDB official API v2](https://www.steamgriddb.com/api/v2) and its
[official TypeScript client](https://github.com/SteamGridDB/node-steamgriddb/blob/master/src/index.ts)
were inspected. The client confirms Bearer authentication, autocomplete search,
game-ID grid queries and dimensions filtering. NOX uses square static PNG grids
and displays title-search suggestions until a maintainer verifies the game ID.
Other categories (heroes, logos and icons) are intentionally not downloaded by this
adapter. API availability grants no blanket image redistribution license. Review
[provider terms](https://www.steamgriddb.com/terms) and obtain relevant permission.
Requests are sequential and paced; HTTP 429 defers that host for the entire batch.
