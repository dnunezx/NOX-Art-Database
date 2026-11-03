# Verified runs

SteamGridDB live test, 2026-11-02 (client date):

- [Fetch artwork](https://github.com/dnunezx/NOX-Art-Database/actions/runs/41573547594): passed. God of War III (`BCUS98111`) matched game `38217`, selected grid `263645` by Prabhjot19, downloaded a native 512px square, generated a 512px PNG and 256px thumbnail, and validated their hashes. No key was exposed.
- Uncharted 2 and LittleBigPlanet also used native 512px grids. The Last of Us used a 1024px square downscaled to 512px.
- Uncharted 3 was queued for manual identity review because SteamGridDB did not supply its expected release date. No remastered edition was silently substituted.
- [Validation](https://github.com/dnunezx/NOX-Art-Database/actions/runs/41573547555) and [optional packaging](https://github.com/dnunezx/NOX-Art-Database/actions/runs/41573732180) passed. All three downloaded ZIP checksums and archive integrity were independently verified.

The selected artwork still requires visual approval and redistribution evidence
before it is hosted publicly as a PNG. The source links and actual generated
checksums are retained in the per-title metadata. No public release was created.

The subsequent individual-file layout is verified by dedicated path/link tests and
its own live workflow. It replaces default ZIP delivery with `art/TITLEID.png`,
`thumbnails/TITLEID.png` and `database/individual_manifest.json`.
