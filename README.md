# Local Price Checker — Ozon + Wildberries

Windows desktop app for collecting storefront prices from Ozon and Wildberries.

## Current prototype

- Select Ozon or Wildberries in the app.
- Enter a seller page and a delivery location.
- Save results to an Excel file in `exports`.
- Google Sheets upload is optional and disabled by default so the first checks run locally.
- Wildberries prototype reads the public seller catalog without cookies, bearer tokens, or a logged-in browser session. If WB returns an access restriction or rate limit, the app stops and displays the status.

For Wildberries, the location field accepts a numeric `dest` region code. Presets shown in the app include Moscow (`-1257786`), Saint Petersburg (`-1205339`), and Kazan (`-2133462`). This selects a region, not a specific pickup point. A true PVZ-level selection needs a separate validation against WB's location flow and should not be inferred from the `dest` code.

## Run on Windows

1. Copy or unpack the project to a stable folder. A local folder is recommended; a network drive can hold the project files if each Windows user has write access.
2. Double-click `ЗАПУСК.bat`.
3. Choose a marketplace, confirm the store link and location, and click **Проверить цены**.
4. Excel files are saved under `exports` next to the project.

The launcher creates a separate virtual environment at `%LOCALAPPDATA%\JKeratinPriceParser\.venv` for the current Windows user and installs dependencies only there. It does not install packages globally or keep a shared environment on a network drive. The first launch needs internet access to create the environment and download packages.

Each colleague needs their own Windows account/profile and local virtual environment. Do not run two copies of setup that share the same environment. On a network drive, use a folder with stable availability and individual write permissions; simultaneous runs are supported by separate environments, but files should not be edited or replaced while another user is running the app.

## Google Sheets

Google upload is currently kept for Ozon and remains opt-in. It requires administrator-provided `service-account.json` and `config.local.json` alongside the launcher. These files are ignored by Git. Do not commit, email, or put these credentials in a shared folder unless every person with access is authorized to use the spreadsheet.

WB Google Sheets upload is not implemented in this prototype; first validate WB collection and Excel output locally.

## Pre-release

See [PRE_RELEASE_CHECKLIST.md](PRE_RELEASE_CHECKLIST.md) for the test matrix and security findings.
