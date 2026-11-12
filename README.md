# Local Price Checker — Ozon + Wildberries

Windows desktop app for collecting storefront prices from OZON and WB.

## Current prototype

- Select OZON or WB in the app.
- Enter a seller page and a delivery location.
- Save results as `OZON_JKeratin_DD-MM-YYYY_HH-MM.xlsx` or `WB_JKeratin_DD-MM-YYYY_HH-MM.xlsx` in `exports`. The store label can be edited in the interface. Repeated exports in the same minute receive `_2`, `_3`, etc.
- Google Sheets upload is optional and disabled by default so the first checks run locally.
- WB (experimental): the app opens its own temporary Chrome session on the public seller page, using the same visible Chrome launch settings as OZON. If the WB page loads normally, it reads only WB cookies from that session into memory and requests the catalog. An optional **Ручной вход в WB** checkbox lets the user sign in or register themselves in the opened browser (no automated account creation, password capture or SMS handling) and then press **Готово — продолжить** in the app. If WB shows a protective challenge, the parser stops without reusing those cookies. A session or login does not guarantee API access; HTTP 403 may still occur.

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

## WB browser-session test

- WB uses its **own** Selenium-launched browser, not cookies from your existing Chrome profile. It matches OZON launch options (compact visible window, no proxy server, no extensions, images disabled, eager page load, and the same browser flags).
- By default the WB Chrome window remains open for 15 seconds so you can inspect any message. Optionally, turn on **Ручной вход в WB (при необходимости)** before starting. If the store page opens without a protection warning, manually sign in or register in that browser and click **Готово — продолжить** in the application within 3 minutes. No password or phone verification code is collected by the application. The temporary browser is automatically closed after reading session cookies; they stay in memory only and are never added to the repository or logs.
- The test proves whether this particular endpoint accepts a fresh browser session. It does not confirm PVZ-level selection: `dest` remains a region code.
- If WB returns HTTP 403, stop and revisit the acquisition approach. Do not paste authentication cookies or tokens into support chats or GitHub issues.

## Google Sheets

Google upload is currently kept for OZON and remains opt-in. It requires administrator-provided `service-account.json` and `config.local.json` alongside the launcher. These files are ignored by Git. Do not commit, email, or put these credentials in a shared folder unless every person with access is authorized to use the spreadsheet.

WB Google Sheets upload is not implemented in this prototype; first validate WB collection and Excel output locally.

## Pre-release

See [PRE_RELEASE_CHECKLIST.md](PRE_RELEASE_CHECKLIST.md) for the test matrix and security findings.
