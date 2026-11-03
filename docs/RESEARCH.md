# SteamGridDB v2 API verification

The current implementation uses SteamGridDB exclusively. The earlier GameTDB,
IGN and PSBBN conversion approaches are retired. No webpages are scraped for art.

Checked against the [official API documentation](https://www.steamgriddb.com/api/v2)
and [SteamGridDB's official TypeScript client](https://github.com/SteamGridDB/node-steamgriddb/blob/master/src/index.ts)
on 2026-11-02. The docs page requires browser rendering and returned 403 to the
command-line reader; the official client source provides the endpoint and parameter
definitions. End-to-end workflow results should be consulted for runtime verification.

- Bearer authentication to `https://www.steamgriddb.com/api/v2`.
- `GET /search/autocomplete/{encoded-query}` for game discovery.
- `GET /games/id/{game-id}` for game identity and release-date confirmation.
- `GET /grids/game/{game-id}` with `dimensions=512x512` first, then `1024x1024`.
- `types=static`, `nsfw=false`, `humor=false`, `epilepsy=false`. The official client
  supports those filter keys. MIME is checked on downloaded content; returned format
  metadata is also filtered. PNG, JPEG and static WebP are accepted.
- `GET /grids/{asset-id}` for an explicit selected asset beyond the first query page;
  such a detail result must identify the correct game or the selection is rejected.

The API supplies game release timestamps, numeric IDs, dimensions, URLs, contributor
metadata and optional community scores. None of these establish redistribution
rights or prove an image's visual suitability. Under the repository owner's recorded
attribution policy, conclusive matches that pass validation are automatically
approved. Inconclusive identities, quality warnings and unrelated duplicates remain
in the review queue; manual decisions retain their own provenance.
See [SteamGridDB terms](https://www.steamgriddb.com/terms).

Matching preserves remake/remaster/edition words, supports explicit regional aliases
and checks supplied release years. A unique exact normalized title is required;
similar names and the first autocomplete result are never sufficient.

The initial catalog's PS3 Title IDs are recorded with evidence URLs in games.json.
GameTDB is used only as a title metadata citation there, never as an artwork provider.
