# US disc catalog and automation

Scope: US **disc releases only**, identified by `BCUS`/`BLUS` serials. PSN-only
releases, DLC and explicit demo/trial/sampler titles are excluded. Multiple disc
serials or editions can represent the same game; these are Title ID counts, not
claims about the number of unique game names.

Imported 1,238 entries from [GameDB-PS3](https://github.com/niemasd/GameDB-PS3)'s
[2025-07-17 release](https://github.com/niemasd/GameDB-PS3/releases/tag/2025-07-17_21-26-13).
GameDB credits [MiSTer Addons](https://misteraddons.com/) and [Redump](http://redump.org/).
The upstream license is included in [GameDB-LICENSE.txt](GameDB-LICENSE.txt).
No game files or game download links were imported, only title/serial metadata.

`reports/us_catalog_import.json` records the dataset SHA-256, exclusions and eleven
US serials whose upstream region field conflicts with their serial prefix. Those
records remain included with an explicit catalog warning for review. A catalog is
only as complete as its upstream data; this is not an independently verified list
of every US release. New or corrected serials can be imported without overwriting
approved artwork or existing metadata.

## Run behavior

- GitHub Actions starts a batch hourly, at minute 17 UTC; scheduled starts can be delayed by GitHub.
- Each batch attempts up to 100 eligible titles, with a 20-minute soft processing budget and 25-minute job timeout.
- Progress, mappings, provider cooldowns and reports are committed to `main` at the end of a successful batch.
- Successful processing is not downloaded again merely because its image still awaits publication approval.
- Missing games or square images are retried after seven days. Ambiguous matches and duplicate conflicts wait for an identity/configuration change or explicit refresh.
- HTTP 429 stops the batch and records `Retry-After` for subsequent runs. No extra keys or parallel jobs are used to evade a provider limit.
- API calls are sequential, spaced by at least one second. Transient network errors use bounded exponential retries; credential and programming errors are fatal.
- Identical assets for the same verified SteamGridDB game can create explicit canonical aliases. Unrelated duplicate content goes to review instead of invalidating the whole batch.
- Schedule runs do not upload repeated artifact snapshots. Use the committed individual indexes and progress reports; manual/push runs still provide short-lived review artifacts.

`reports/progress.json` and `reports/progress.md` show totals, processed artwork,
hosted PNGs, manual-review items, missing/retry items and the next eligible batch.
The same progress is displayed in the workflow summary. When no entries are due,
an hourly run makes no artwork requests. After the initial pass it acts as maintenance
for missing entries and any newly imported titles.

At 100 attempts per batch, 1,238 IDs need approximately 13 hourly batches for an
initial pass if provider availability permits. That does not promise matching art
for every title, visual approval, or redistribution permission. Publication remains
a separate count in the progress report.

SteamGridDB's published materials reviewed here did not establish a numeric daily
quota. The system does not assume unlimited access: actual 429 responses and reset
times take precedence. GitHub-hosted jobs have a six-hour maximum, while this project
intentionally uses shorter resumable jobs. Standard runners for public repositories
currently have free compute usage; storage and service limits still apply.

Sources: [SteamGridDB API](https://www.steamgriddb.com/api/v2),
[GitHub Actions limits](https://docs.github.com/en/actions/reference/limits),
[GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

## Import an updated catalog

```sh
gh release download --repo niemasd/GameDB-PS3 --pattern PS3.data.json --dir catalog-update
python -m scripts.import_us_discs catalog-update/PS3.data.json
python -m scripts.generate_report
python -m scripts.publish_individual
```

Review the import report before pushing. A source conflict is reported rather than
silently replacing an existing title record.
