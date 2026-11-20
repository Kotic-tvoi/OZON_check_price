"""Encrypted per-Windows-user cache for Wildberries browser cookies.

Cookie values are protected with Windows DPAPI and never written in plaintext.
The cache lives under the current user's LOCALAPPDATA, outside the project folder.
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import time
from pathlib import Path
from ctypes import wintypes

LOG = logging.getLogger("wb.cookies")
CACHE_VERSION = 1
COOKIE_DOMAINS = ("wildberries.ru",)


class CookieCacheError(RuntimeError):
    """The local encrypted cookie cache cannot be read or written."""


def cookie_cache_path() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        base = Path(root)
    else:
        base = Path.home() / "AppData" / "Local"
    return base / "JKeratinPriceParser-Test" / "wb_cookies.dpapi"


def active_cookie_records(cookies: list[dict], now: float | None = None) -> list[dict]:
    """Keep unexpired cookies belonging to Wildberries; never expose values in logs."""
    current = time.time() if now is None else now
    result: list[dict] = []
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        name = cookie.get("name")
        value = cookie.get("value")
        domain = str(cookie.get("domain") or "").lstrip(".").casefold()
        if not name or value is None or not any(
                domain == item or domain.endswith("." + item) for item in COOKIE_DOMAINS):
            continue
        try:
            expires = float(cookie.get("expires", -1))
        except (TypeError, ValueError):
            expires = -1
        if expires > 0 and expires <= current:
            continue
        record = {
            "name": str(name),
            "value": str(value),
            "domain": str(cookie.get("domain") or ".wildberries.ru"),
            "path": str(cookie.get("path") or "/"),
            "secure": bool(cookie.get("secure", True)),
            "httpOnly": bool(cookie.get("httpOnly", False)),
            "expires": expires,
            "sameSite": str(cookie.get("sameSite") or ""),
        }
        result.append(record)
    return result


def _dpapi(data: bytes, *, protect: bool) -> bytes:
    if os.name != "nt":
        raise CookieCacheError("Зашифрованное хранилище cookies доступно только в Windows.")

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte)),
        ]

    crypt32 = ctypes.WinDLL("Crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("Kernel32", use_last_error=True)
    input_buffer = ctypes.create_string_buffer(data)
    input_blob = DATA_BLOB(
        len(data), ctypes.cast(input_buffer, ctypes.POINTER(ctypes.c_byte))
    )
    output_blob = DATA_BLOB()
    flags = 0x1  # CRYPTPROTECT_UI_FORBIDDEN

    if protect:
        function = crypt32.CryptProtectData
        function.argtypes = [
            ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR,
            ctypes.POINTER(DATA_BLOB), wintypes.LPVOID, wintypes.LPVOID,
            wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
        ]
        function.restype = wintypes.BOOL
        ok = function(
            ctypes.byref(input_blob), "JKeratin WB cookie cache",
            None, None, None, flags, ctypes.byref(output_blob)
        )
    else:
        function = crypt32.CryptUnprotectData
        function.argtypes = [
            ctypes.POINTER(DATA_BLOB), ctypes.POINTER(wintypes.LPWSTR),
            ctypes.POINTER(DATA_BLOB), wintypes.LPVOID, wintypes.LPVOID,
            wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
        ]
        function.restype = wintypes.BOOL
        ok = function(
            ctypes.byref(input_blob), None, None, None, None,
            flags, ctypes.byref(output_blob)
        )

    if not ok:
        raise CookieCacheError(
            "Windows не смог расшифровать локальный кэш cookies."
            if not protect else
            "Windows не смог зашифровать локальный кэш cookies."
        )
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        kernel32.LocalFree.restype = wintypes.HLOCAL
        kernel32.LocalFree(output_blob.pbData)


def load_cookie_cache() -> dict | None:
    path = cookie_cache_path()
    if not path.is_file():
        return None
    try:
        raw = _dpapi(path.read_bytes(), protect=False)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("version") != CACHE_VERSION:
            return None
        cookies = active_cookie_records(payload.get("cookies") or [])
        if not cookies:
            return None
        return {
            "cookies": cookies,
            "user_agent": str(payload.get("user_agent") or ""),
            "saved_at": payload.get("saved_at"),
        }
    except (OSError, ValueError, TypeError, CookieCacheError) as exc:
        LOG.warning("WB cookie cache is unavailable (%s); browser refresh will be used",
                    type(exc).__name__)
        return None


def save_cookie_cache(cookies: list[dict], user_agent: str = "") -> None:
    records = active_cookie_records(cookies)
    if not records:
        raise CookieCacheError("WB не передал cookies для сохранения.")
    payload = json.dumps({
        "version": CACHE_VERSION,
        "saved_at": time.time(),
        "user_agent": str(user_agent or ""),
        "cookies": records,
    }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    encrypted = _dpapi(payload, protect=True)
    path = cookie_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(encrypted)
    os.replace(temporary, path)
