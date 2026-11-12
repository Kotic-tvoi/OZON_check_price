# Pre-release checklist: Ozon + Wildberries price checker

Run the checklist on a clean Windows 10/11 workstation before sharing a release. Keep Google upload disabled during the initial local WB validation.

## 1. Installation and virtual-environment isolation

- [ ] Start from a folder with no existing environment; run `ЗАПУСК.bat`.
- [ ] Confirm `%LOCALAPPDATA%\JKeratinPriceParser\.venv` is created and packages install there.
- [ ] Confirm the Python executable invoked by the launcher is the venv executable.
- [ ] Confirm no package is installed into global Python (compare global and venv `pip list` before/after).
- [ ] Start again with all dependencies present; confirm it skips installation.
- [ ] Remove one dependency from the venv and start again; confirm the launcher repairs the venv.
- [ ] Test Python missing, pip failure, offline first launch, and a path containing spaces/non-ASCII characters. Errors should be readable and must not fall through to global Python.
- [ ] Run the app as a standard Windows user without administrator rights.

## 2. Wildberries access without authentication — highest priority

- [ ] On a normal office/home network, choose WB and run against a public seller page with an empty browser login state.
- [ ] Inspect the implementation/request in a controlled local debug session: no `Cookie`, `Authorization`, browser profile, or saved session is sent.
- [ ] Verify HTTP 200 returns product IDs, names, list prices, and discounted prices in rubles.
- [ ] Compare a sample of at least 10 products with the same seller page in a regular browser for the selected destination.
- [ ] Compare page 1 and later pages; confirm pagination stops at the first empty page and duplicate IDs are not duplicated.
- [ ] Check a seller with one page, several pages, no products, hidden/unavailable products, and products without a price.
- [ ] Repeat with Moscow, Saint Petersburg, Kazan, and a valid custom `dest`; note that this is regional destination selection, not a specific PVZ.
- [ ] Test invalid seller URLs, wrong host, query string, non-numeric destination, network timeout, DNS failure, malformed JSON, HTTP 401/403/429, and other 5xx statuses. The app should stop with a clear message and should not retry in a way that bypasses an access block.
- [ ] Check whether price/availability differences by destination match WB's user-facing storefront; record if WB ignores or changes the supplied `dest`.
- [ ] Repeat a small check several hours later and on another network to identify transient access restrictions and rate limits. Keep request volume conservative.

**Environment test note:** the WB endpoint could not be reached through the current hosted review environment, so unauthenticated WB access has not been confirmed live. The local Windows test above is a release blocker for WB support.

## 3. Ozon regression checks

- [ ] Verify store and PVZ links still validate and the configured PVZ is confirmed on the storefront.
- [ ] Collect a complete Ozon catalog and compare a sample of prices with visible product tiles.
- [ ] Test CAPTCHA/access restriction handling, empty catalog, timeout, and retry behavior.
- [ ] Confirm no Ozon product pages are opened one-by-one and catalog loading completes as before.
- [ ] Confirm the Google checkbox starts unchecked and Ozon collection + Excel work without Google credentials.
- [ ] With administrator credentials, separately verify opt-in upload writes only the expected Ozon sheet/range.

## 4. GUI and usability

- [ ] Switch repeatedly between Ozon and WB; confirm default URL and region fields update correctly.
- [ ] Confirm WB location label explains that `dest` is a region code, not a pickup point.
- [ ] Test paste, select-all, copy, cut, right-click paste, and long URLs in both fields.
- [ ] Confirm a second run cannot start while the first is active and the window cannot close mid-run.
- [ ] Test long runs, errors, and completion messages without a frozen or unresponsive window.
- [ ] Test display scaling (100%, 125%, 150%), minimum window size, and Russian Windows locale.

## 5. Excel and file handling

- [ ] Confirm Excel is created under `exports` with a timestamp and the correct marketplace prefix.
- [ ] Open the result in Excel and LibreOffice; verify Cyrillic headers, article IDs, numeric prices, and missing-price labels.
- [ ] Compare output row count and sample values with the collected catalog.
- [ ] Run twice and confirm earlier exports are not overwritten.
- [ ] Test read-only project folder, full disk, antivirus file lock, and network-drive interruption; show a useful error and preserve any completed file.

## 6. Network-drive / multi-user checks

- [ ] Run the source from the intended shared drive with two Windows users; verify each creates and uses their own `%LOCALAPPDATA%` venv.
- [ ] Run both instances concurrently and verify no shared browser profile, environment, log, or temporary file collision.
- [ ] Interrupt the network drive during launch and during export; verify safe failure and no corrupted shared files.
- [ ] Check drive permissions, offline-cache behavior, antivirus scanning, path length, and startup latency.
- [ ] Confirm the shared folder is limited to authorized colleagues. Treat any Google service-account JSON copied there as an exposed credential.

## 7. Security review before release

- [ ] Keep `service-account.json`, `config.local.json`, cookies, tokens, logs with headers, and exports out of Git.
- [ ] Confirm the repository history and release archive contain no credentials or session cookies.
- [ ] Limit Google service-account sharing to the exact spreadsheet and authorized users; rotate the key if it was ever shared more broadly.
- [ ] Do not log request headers, cookies, authorization tokens, full service-account JSON, or personal data.
- [ ] Check all user-entered URLs are host-validated before network requests; do not accept arbitrary URLs.
- [ ] Keep dependencies pinned/upper-bounded and review updates before release.
- [ ] Confirm the app contacts only the expected marketplace and Google endpoints; use least-privilege Google scopes.

## 8. Remaining integration work

- [ ] Decide the final Google Sheets layout for WB and whether it should use a separate sheet.
- [ ] Add WB upload only after local WB collection and Excel results are accepted.
- [ ] If exact WB pickup-point comparison is required, investigate a supported/observable PVZ selection flow separately; do not treat city-level `dest` as a PVZ.
- [ ] Create a clean release package and test it from a new folder/profile before distribution.
