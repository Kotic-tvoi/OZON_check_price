# Local Price Checker — Ozon + Wildberries

Windows desktop app for collecting storefront prices from OZON and WB.

## Current prototype

- Select OZON or WB in the app.
- Enter a seller page and a delivery location.
- Save results as `OZON_JKeratin_YYYY-MM-DD_HH-MM.xlsx` or `WB_JKeratin_YYYY-MM-DD_HH-MM.xlsx` in `exports`. The store label can be edited in the interface. Repeated exports in the same minute receive `_2`, `_3`, etc.
- Google Sheets upload is optional and disabled by default so the first checks run locally.
- WB currently uses an internal catalog endpoint without cookies or login; **HTTP 403 has been observed locally**. This endpoint cannot be considered working until another supported/publicly accessible source is verified. The app stops and explains the restriction.

For WB, pick Moscow, Saint Petersburg, Kazan or Syktyvkar from the dropdown, or type a numeric `dest` value. Default is the JKeratin seller and Moscow (`-1257786`). This selects a region, not a specific pickup point. A true PVZ-level selection needs a separate validation against WB's location flow and should not be inferred from the `dest` code.

## Run on Windows

1. Copy or unpack the project to a stable folder. A local folder is recommended; a network drive can hold the project files if each Windows user has write access.
2. Double-click `ЗАПУСК.bat`. Python and Chrome need to be installed. The first run can download Python packages and Selenium Manager may download ChromeDriver.
3. Choose a marketplace, confirm the store link and location, and click **Проверить цены**.
4. Excel files are saved under `exports` next to the project.

This test branch creates a **separate test virtual environment** at `%LOCALAPPDATA%\JKeratinPriceParser-Test\.venv` for the current Windows user and installs dependencies only there. It does not install packages globally or keep a shared environment on a network drive. The first launch needs internet access to create the environment and download packages.

Each colleague needs their own Windows account/profile and local virtual environment. Do not run two copies of setup that share the same environment. On a network drive, use a folder with stable availability and individual write permissions; simultaneous runs are supported by separate environments, but files should not be edited or replaced while another user is running the app.

## OZON browser

The OZON parser opens a visible Chrome window by default, as in the original working version. No command-line environment variable is needed to display it. The GUI shows brief progress statuses without per-stage timings. If OZON displays an access restriction at PVZ selection, the parser stops rather than pretending that prices have been collected.

## Google Sheets

Google upload is currently kept for OZON and remains opt-in. It requires administrator-provided `service-account.json` and `config.local.json` alongside the launcher. These files are ignored by Git. Do not commit, email, or put these credentials in a shared folder unless every person with access is authorized to use the spreadsheet.

WB Google Sheets upload is not implemented in this prototype; first validate WB collection and Excel output locally.

## Pre-release

See [PRE_RELEASE_CHECKLIST.md](PRE_RELEASE_CHECKLIST.md) for the test matrix and security findings.
