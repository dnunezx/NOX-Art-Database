# Launcher integration contract

The ZIP layout is `artwork/PS3/TITLEID.png`, `thumbnails/PS3/TITLEID.png`, and
`database/artwork_manifest.json`. The manifest has separate `artwork_root` and
`thumbnail_root`, so both fields can contain `PS3/TITLEID.png` without ambiguity.
Each entry includes the SHA-256 of the PNG and, if present, its thumbnail. Only
visually approved artwork with recorded redistribution approval enters the manifest.
Regional aliases point to their verified canonical file and share its checksums.

The future launcher should:

1. Read the exact Title ID from the game's PARAM.SFO (or existing ISO metadata parser).
2. Look up a local cached image first. Missing artwork must fall back to a bundled icon.
3. If the user enables online artwork, fetch the manifest from a configured trusted HTTPS release URL, with a timeout and size limit.
4. Accept only the known manifest version and valid Title ID keys. Reject absolute paths, backslashes, traversal and unexpected hosts before fetching a file.
5. Combine `artwork_root` or `thumbnail_root` with the corresponding entry path. Download into a temporary file, enforce a byte limit, verify the manifest SHA-256 and validate the PNG before atomically installing it in the cache.
6. Retain the last valid cache on any network, schema or checksum error.

Offline installation consists of copying the approved ZIP contents to the artwork
cache. Regional entries may share files; the launcher must follow manifest paths
rather than assume every ID has a separate PNG. Online retrieval defaults to off.

Hashes detect corruption; they do not authenticate a manifest obtained from an
untrusted server. Use a trusted release origin and HTTPS. PS3 firmware, TLS and PNG
decoder behavior still need testing on hardware. This repository implements the
artwork data contract, not changes to the NOX launcher executable.
