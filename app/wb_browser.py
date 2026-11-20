"""Launch a persistent, dedicated Chrome profile and attach through CDP.

This mirrors the colleague's browser-profile + remote-debugging approach. It does
not read the user's personal Chrome profile and does not attempt to defeat WB
CAPTCHA or access restrictions.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
import urllib.request
import json
from pathlib import Path



class WBBrowserError(RuntimeError):
    pass


def profile_path() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return root / "JKeratinPriceParser-Test" / "WB-Chrome-Profile"


def _find_chrome() -> str:
    candidates = [
        shutil.which("chrome"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise WBBrowserError("Не найден Google Chrome. Установите Chrome и повторите попытку.")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class WBBrowserSession:
    def __init__(self, store_url: str, progress=None):
        self.store_url = store_url
        self.progress = progress
        self.process = None
        self.driver = None
        self.debugger_address = None

    def __enter__(self):
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        port = _free_port()
        profile = profile_path()
        profile.mkdir(parents=True, exist_ok=True)
        executable = _find_chrome()
        args = [
            executable,
            f"--remote-debugging-port={port}",
            "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--disable-blink-features=AutomationControlled",
            "--window-size=1100,760",
            self.store_url,
        ]
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
        try:
            self.process = subprocess.Popen(
                args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=creationflags
            )
            self.debugger_address = f"127.0.0.1:{port}"
            version_url = f"http://{self.debugger_address}/json/version"
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise WBBrowserError("Chrome завершился до запуска интерфейса CDP.")
                try:
                    with urllib.request.urlopen(version_url, timeout=1) as response:
                        json.load(response)
                    break
                except Exception:
                    time.sleep(0.25)
            else:
                raise WBBrowserError("Не удалось подключиться к Chrome через CDP.")
            options = Options()
            options.add_experimental_option("debuggerAddress", self.debugger_address)
            self.driver = webdriver.Chrome(options=options)
            self.driver.set_page_load_timeout(30)
            if self.progress:
                self.progress("Chrome запущен с постоянным профилем WB через CDP.")
            return self
        except Exception:
            self._terminate()
            raise

    def _terminate(self):
        if self.driver is not None:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
        if self.process is not None and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass

    def __exit__(self, exc_type, exc, tb):
        self._terminate()

    def cookies(self) -> list[dict]:
        if self.driver is None:
            return []
        return self.driver.get_cookies()

    def user_agent(self) -> str:
        if self.driver is None:
            return ""
        try:
            return str(self.driver.execute_script("return navigator.userAgent") or "")
        except Exception:
            return ""

    def page_text(self) -> str:
        if self.driver is None:
            return ""
        try:
            return str(self.driver.execute_script(
                "return (document.body && document.body.innerText || '').slice(0,6000)"
            ) or "").casefold()
        except Exception:
            return ""
