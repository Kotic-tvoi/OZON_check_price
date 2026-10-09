"""OzonPrices Windows GUI: a single manual run, then upload to Google Sheets.

All URLs are entered here. Blank values mean the default store and Moscow PVZ.
No background agent, spreadsheet checkbox, Apps Script, or local HTTP server.
"""
from __future__ import annotations

import logging
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

from config import DEFAULT_PVZ, DEFAULT_STORE
from core import pvz_url, store_url


def resolved_urls(store_input: str, pvz_input: str) -> tuple[str, str]:
    return store_url(store_input.strip() or DEFAULT_STORE), pvz_url(pvz_input.strip() or DEFAULT_PVZ)


def export_excel(items: list[dict], complete: bool) -> Path:
    from datetime import datetime

    from google_sheets import folder
    from xlsx_export import to_xlsx

    destination = folder() / "exports"
    destination.mkdir(parents=True, exist_ok=True)
    suffix = "" if complete else "_НЕПОЛНЫЙ"
    name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = destination / f"ozon_{name}{suffix}.xlsx"
    path.write_bytes(to_xlsx(items))
    return path


class UiLogHandler(logging.Handler):
    def __init__(self, messages):
        super().__init__()
        self.messages = messages

    def emit(self, record):
        try:
            self.messages.put(("log", self.format(record)))
        except Exception:
            self.handleError(record)


class PricesApp:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.busy = False
        self.store = tk.StringVar()
        self.pvz = tk.StringVar()
        self.save_excel = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Готово к проверке")
        root.title("OzonPrices — проверка конечных цен")
        root.geometry("780x610")
        root.minsize(700, 535)
        root.configure(bg="#F5F7FB")
        root.protocol("WM_DELETE_WINDOW", self.close)

        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Main.TFrame", background="#F5F7FB")
        style.configure("Main.TLabel", background="#F5F7FB", font=("Segoe UI", 10))
        style.configure("Title.TLabel", background="#F5F7FB",
                        font=("Segoe UI Semibold", 18), foreground="#18263A")
        style.configure("Note.TLabel", background="#F5F7FB",
                        foreground="#66758A", font=("Segoe UI", 9))
        style.configure("Run.TButton", font=("Segoe UI Semibold", 11), padding=(18, 11))
        style.configure("TEntry", padding=7)

        panel = ttk.Frame(root, style="Main.TFrame", padding=22)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="Проверка цен Ozon", style="Title.TLabel").pack(anchor="w")
        ttk.Label(panel, text="Откроется Chrome, затем цены автоматически появятся в Google Таблице.",
                  style="Note.TLabel").pack(anchor="w", pady=(3, 17))

        self.add_input(panel, "Ссылка на магазин Ozon", self.store, DEFAULT_STORE)
        self.add_input(panel, "Ссылка на пункт выдачи (ПВЗ)", self.pvz, DEFAULT_PVZ)

        ttk.Checkbutton(panel, text="Дополнительно сохранить Excel на компьютере",
                        variable=self.save_excel).pack(anchor="w", pady=(7, 12))

        actions = ttk.Frame(panel, style="Main.TFrame")
        actions.pack(fill="x", pady=(0, 12))
        self.start_button = ttk.Button(actions, text="Проверить цены и отправить",
                                       style="Run.TButton", command=self.start)
        self.start_button.pack(side="left")
        ttk.Label(actions, textvariable=self.status, style="Main.TLabel",
                  wraplength=370).pack(side="left", padx=(18, 0))
        ttk.Label(panel, text="Ход проверки", style="Main.TLabel").pack(anchor="w")
        self.log = scrolledtext.ScrolledText(panel, height=12, font=("Consolas", 9),
                                             wrap="word", state="disabled",
                                             relief="flat", bg="#FFFFFF",
                                             fg="#27384B", padx=10, pady=9)
        self.log.pack(fill="both", expand=True, pady=(6, 0))
        self.write_log("Пустые поля используют магазин JKeratin и московский ПВЗ.")
        self.write_log("Для начала нажмите «Проверить цены и отправить».")
        root.after(120, self.consume_events)

    def add_input(self, parent, label, variable, example):
        ttk.Label(parent, text=label, style="Main.TLabel").pack(anchor="w")
        entry = ttk.Entry(parent, textvariable=variable, font=("Segoe UI", 10))
        entry.pack(fill="x", pady=(5, 3))
        ttk.Label(parent, text=f"По умолчанию: {example}",
                  style="Note.TLabel").pack(anchor="w", pady=(0, 14))

    def write_log(self, message):
        self.log.configure(state="normal")
        self.log.insert("end", str(message) + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def start(self):
        if self.busy:
            return
        try:
            store, pvz = resolved_urls(self.store.get(), self.pvz.get())
        except ValueError as exc:
            messagebox.showerror("Неверная ссылка", str(exc))
            return
        self.busy = True
        self.start_button.configure(state="disabled")
        self.status.set("Подготовка...")
        self.write_log(f"Магазин: {store}")
        self.write_log(f"ПВЗ: {pvz}")
        thread = threading.Thread(target=self.collect_and_upload,
                                  args=(store, pvz, bool(self.save_excel.get())),
                                  daemon=True)
        thread.start()

    def collect_and_upload(self, store, pvz, include_excel):
        from google_sheets import check_target, load_connection, session_for, upload_catalog
        from scraper import collect

        logger = logging.getLogger("ozon.storefront")
        handler = UiLogHandler(self.events)
        handler.setFormatter(logging.Formatter("%(message)s"))
        old_level = logger.level
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        try:
            self.events.put(("status", "Проверяем подключение к Google..."))
            connection = load_connection()
            http = session_for(connection)
            try:
                check_target(http, connection["sheet_id"])
            finally:
                http.close()

            self.events.put(("status", "Собираем цены в Chrome..."))
            catalog = collect(store, pvz, headed=True)
            self.events.put(("log", f"Найдено: {len(catalog.items)}; "
                                      f"время: {catalog.elapsed_seconds} с."))
            if not catalog.complete:
                self.events.put(("log", "Внимание: полнота каталога не подтверждена. "
                                          "Отсутствующие позиции не считаются удалёнными."))

            self.events.put(("status", "Отправляем данные в Google Таблицу..."))
            result = upload_catalog(connection, catalog)
            self.events.put(("log", f"Google Таблица, лист «{result['sheet']}»: "
                                      f"записано {result['rows']} строк."))
            if include_excel:
                path = export_excel(catalog.items, catalog.complete)
                self.events.put(("log", f"Excel сохранён: {path}"))

            self.events.put(("done", (
                f"Готово. Проверено: {result['checked']}; в таблице: {result['rows']}. "
                + ("Каталог полный." if result["complete"] else "Каталог неполный.")
            )))
        except Exception as exc:
            self.events.put(("error", str(exc)))
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)

    def consume_events(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "log":
                    self.write_log(data)
                elif kind == "status":
                    self.status.set(data)
                elif kind == "done":
                    self.busy = False
                    self.start_button.configure(state="normal")
                    self.status.set(data)
                    self.write_log(data)
                    messagebox.showinfo("Проверка завершена", data)
                elif kind == "error":
                    self.busy = False
                    self.start_button.configure(state="normal")
                    self.status.set("Ошибка")
                    self.write_log("Ошибка: " + data)
                    messagebox.showerror("Не удалось выполнить проверку", data)
        except queue.Empty:
            pass
        self.root.after(120, self.consume_events)

    def close(self):
        if self.busy:
            messagebox.showinfo("Проверка выполняется",
                                "Дождитесь завершения проверки и закрытия Chrome.")
            return
        self.root.destroy()


def main():
    if "--check-build" in sys.argv:
        import google.auth
        import selenium
        destination = Path(sys.argv[sys.argv.index("--check-build") + 1])
        destination.write_text("OK", encoding="utf-8")
        return
    root = tk.Tk()
    PricesApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
