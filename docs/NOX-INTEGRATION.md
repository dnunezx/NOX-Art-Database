# NOX artwork integration

`database/individual_manifest.json` is the individual download index. It gives
`download_url` and SHA-256 for each hosted PNG, or a provider source link and explicit
unavailable status when the image is not hosted. Use only available download entries.

`database/artwork_manifest.json` is the lightweight approved local-path index. Each available
entry maps a verified PS3 Title ID to a 512px PNG, optional 256px thumbnail, SteamGridDB
game/asset IDs and actual SHA-256 checksums. Paths are relative to the separate
`artwork_root` and `thumbnail_root` fields. Verified regional aliases can share a file.

The launcher should read the installed game's exact Title ID, check its local cache,
and display a bundled fallback when no image exists. Online artwork is optional and
must default to off. Offline use must remain fully functional.

Public delivery should use this repository's rights-approved packs or another trusted
authorized host. Individual artwork follows CosmicScale's layout: `art/TITLEID.png`
on the repository's main branch, with `thumbnails/TITLEID.png` separately. Download
one matching game at a time using its raw GitHub URL; no ZIP is required.
A user-owned PC companion may fetch personal images using that
user's own SteamGridDB API key. Never embed a shared key in a public PS3 binary.

For online use, retrieve the manifest over trusted HTTPS with a timeout and byte
limit; validate version, keys and relative paths. Reject absolute paths, backslashes,
traversal and unexpected hosts. Download to a temporary file, enforce byte limits,
verify SHA-256 and PNG dimensions, then atomically install into the cache. Keep the
last valid cached image on all network and validation errors.

Hashes protect against corruption, not a malicious manifest; trust the manifest origin.
PS3 TLS, memory limits and PNG decoder compatibility still require hardware testing.
This repository implements the data pipeline and contract, not the NOX executable.
