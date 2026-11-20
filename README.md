# Local Price Checker — Ozon + Wildberries

Windows desktop app for collecting storefront prices from OZON and WB.

## Current prototype

- Select OZON or WB in the app.
- Enter a seller page and a delivery location.
- Save results as `OZON_JKeratin_DD-MM-YYYY_HH-MM.xlsx` or `WB_JKeratin_DD-MM-YYYY_HH-MM.xlsx` in `exports`. The store label can be edited in the interface. Repeated exports in the same minute receive `_2`, `_3`, etc.
- Google Sheets upload is optional and disabled by default so the first checks run locally.
- WB (experimental): the existing seller-catalog HTTP parser is retained. It first loads a per-Windows-user encrypted cookie cache and requests the catalog as before. If there is no cache or the first request returns HTTP 401/403, it opens a dedicated persistent Chrome profile through the Chrome DevTools Protocol (CDP), refreshes WB cookies, stores them encrypted with Windows DPAPI under `%LOCALAPPDATA%`, and retries the same catalog request once. HTTP 429 is treated as rate limiting and does not trigger a browser refresh. The optional **Ручной вход в WB** checkbox lets the user sign in or complete a site-provided check manually in that dedicated browser and then press **Готово — продолжить**. The app does not read the user's everyday Chrome profile, collect passwords or SMS codes, or automate CAPTCHA. If WB continues to show a challenge or the retried request is denied, collection stops.

For WB, pick Moscow, Saint Petersburg, Kazan or Syktyvkar from the dropdown, or type a numeric `dest` value. Default is the JKeratin seller and Moscow (`-1257786`). This selects a region, not a specific pickup point. A true PVZ-level selection needs a separate validation against WB's location flow and should not be inferred from the `dest` code.

## Run on Windows

1. Copy or unpack the project to a stable folder. A local folder is recommended; a network drive can hold the project files if each Windows user has write access.
2. Double-click `ЗАПУСК.bat`. Python and Chrome need to be installed. The first run can download Python packages and Selenium Manager may download ChromeDriver.
3. Choose a marketplace, confirm the store link and location, and click **Проверить цены**.
4. Excel files are saved under `exports` next to the project.

This test branch creates a **separate test virtual environment** at `%LOCALAPPDATA%\JKeratinPriceParser-Test\.venv` for the current Windows user and installs dependencies only there. It does not install packages globally or keep a shared environment on a network drive. The first launch needs internet access to create the environment and download packages.

Each colleague needs their own Windows account/profile and local virtual environment. Do not run two copies of setup that share the same environment. On a network drive, use a folder with stable availability and individual write permissions; simultaneous runs are supported by separate environments, but files should not be edited or replaced while another user is running the app.

## OZON browser

The OZON parser always opens a smaller visible Chrome window positioned on the right-hand side of the desktop. There is no compact-mode checkbox or command-line flag. The GUI shows brief progress statuses without per-stage timings. If OZON displays an access restriction at PVZ selection, the parser stops rather than pretending that prices have been collected.

## WB browser and cookie lifecycle

- The original catalog endpoint, destination parameters, pagination, price parsing and Excel output remain unchanged.
- The parser first uses the encrypted cookie cache at `%LOCALAPPDATA%\\JKeratinPriceParser-Test\\wb_cookies.dpapi`. Windows DPAPI protects cookie values for the current Windows user; cookies are not written to the project folder or logs.
- If there is no cache, or the first catalog request returns HTTP 401/403, the app launches a dedicated persistent Chrome profile at `%LOCALAPPDATA%\\JKeratinPriceParser-Test\\WB-Chrome-Profile` and attaches over CDP. It reads cookies only from that dedicated profile, refreshes the encrypted cache and retries the same API request once.
- HTTP 429 does not trigger a refresh. A detected WB protection/challenge page stops the process. The optional **Ручной вход в WB** checkbox allows a user to sign in or complete a site-provided check manually and confirm in the app; passwords and SMS codes are not captured.
- The dedicated browser profile persists between runs to retain the user's WB session. It is separate from the user's everyday Chrome profile. To reset the test session, close the app and remove the dedicated WB profile and encrypted cache under the current Windows user's LocalAppData.
- A successful browser launch or cookie refresh does not guarantee the catalog endpoint will accept the request. If the single retry is still denied, the app stops with an explicit error.


## Google Sheets

Google upload is currently kept for OZON and remains opt-in. It requires administrator-provided `service-account.json` and `config.local.json` alongside the launcher. These files are ignored by Git. Do not commit, email, or put these credentials in a shared folder unless every person with access is authorized to use the spreadsheet.

WB Google Sheets upload is not implemented in this prototype; first validate WB collection and Excel output locally.

## Pre-release

See [PRE_RELEASE_CHECKLIST.md](PRE_RELEASE_CHECKLIST.md) for the test matrix and security findings.
