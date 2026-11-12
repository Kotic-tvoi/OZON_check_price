"""Combined local Ozon and Wildberries price-checking app."""
from __future__ import annotations

import re
import queue
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk
from urllib.parse import urlparse

from config import DEFAULT_PVZ, DEFAULT_STORE
from core import pvz_url, store_url

WB_STORE = "https://www.wildberries.ru/seller/215484/"
WB_DEST = "-1257786"
WB_REGIONS = ("Москва", "Санкт-Петербург", "Казань", "Сыктывкар")


def suggest_store_name(marketplace: str, url: str) -> str:
    """Best-effort default; a user may override it for another store."""
    path = urlparse(url.strip()).path
    if marketplace == "WB":
        match = re.fullmatch(r"/seller/(\d+)/?", path)
        if match:
            return "JKeratin" if match.group(1) == "215484" else f"seller_{match.group(1)}"
    else:
        if path.rstrip("/") in ("/seller/jkeratin",):
            return "JKeratin"
        match = re.match(r"/seller/([^/]+)", path)
        if match:
            return match.group(1)
    return "Магазин"


def export_excel(items: list[dict], marketplace: str, shop_name: str) -> Path:
    from xlsx_export import to_xlsx

    base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    destination = base / "exports"
    destination.mkdir(parents=True, exist_ok=True)
    clean_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", shop_name).strip(" ._")[:70] or "Магазин"
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    payload = to_xlsx(items, sheet_name=f"Цены {marketplace}")
    # Exclusive creation avoids accidental replacement, even in the same minute.
    for number in range(1, 1000):
        suffix = "" if number == 1 else f"_{number}"
        path = destination / f"{marketplace}_{clean_name}_{stamp}{suffix}.xlsx"
        try:
            with path.open("xb") as output:
                output.write(payload)
            return path
        except FileExistsError:
            continue
        except OSError:
            if path.exists():
                path.unlink(missing_ok=True)
            raise
    raise OSError("Не удалось выбрать уникальное имя для файла Excel.")


class PricesApp:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.busy = False
        self.market = tk.StringVar(value="OZON")
        self.store = tk.StringVar(value=DEFAULT_STORE)
        self.region = tk.StringVar(value=DEFAULT_PVZ)
        self.shop_name = tk.StringVar(value="JKeratin")
        self._auto_store_name = "JKeratin"
        self.save_excel = tk.BooleanVar(value=True)
        # Local-first mode: Google upload is deliberately opt-in.
        self.upload_google = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Готово к проверке")

        root.title("Проверка цен OZON и WB")
        root.geometry("800x650")
        root.minsize(720, 585)
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
        ttk.Label(panel, text="Проверка цен маркетплейсов",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(panel, text="Сначала соберите данные локально. Выгрузка в Google Таблицу выключена по умолчанию.",
                  style="Note.TLabel", wraplength=740).pack(anchor="w", pady=(3, 15))

        ttk.Label(panel, text="Маркетплейс", style="Main.TLabel").pack(anchor="w")
        self.market_choice = ttk.Combobox(panel, textvariable=self.market,
                                          values=("OZON", "WB"),
                                          state="readonly", font=("Segoe UI", 10))
        self.market_choice.pack(fill="x", pady=(5, 13))
        self.market_choice.bind("<<ComboboxSelected>>", self.on_market_change)

        self.store_label = ttk.Label(panel, text="Ссылка на магазин OZON",
                                     style="Main.TLabel")
        self.store_label.pack(anchor="w")
        self.store_entry = ttk.Entry(panel, textvariable=self.store, font=("Segoe UI", 10))
        self.store_entry.pack(fill="x", pady=(5, 3))
        self._bind_editing(self.store_entry)
        self.store_entry.bind("<FocusOut>", self._update_store_name)

        self.region_label = ttk.Label(panel, text="Ссылка на пункт выдачи (ПВЗ) OZON",
                                      style="Main.TLabel")
        self.region_label.pack(anchor="w", pady=(11, 0))
        self.region_entry = ttk.Combobox(panel, textvariable=self.region, values=(), font=("Segoe UI", 10))
        self.region_entry.pack(fill="x", pady=(5, 3))
        self._bind_editing(self.region_entry)
        self.region_note = ttk.Label(panel, text="Для OZON укажите ссылку на ПВЗ.",
                                     style="Note.TLabel")
        self.region_note.pack(anchor="w", pady=(0, 10))

        ttk.Label(panel, text="Название магазина для файла Excel", style="Main.TLabel").pack(anchor="w")
        self.shop_entry = ttk.Entry(panel, textvariable=self.shop_name, font=("Segoe UI", 10))
        self.shop_entry.pack(fill="x", pady=(5, 10))
        self._bind_editing(self.shop_entry)

        ttk.Checkbutton(panel, text="Сохранить Excel в папку exports",
                        variable=self.save_excel).pack(anchor="w", pady=(2, 3))
        self.google_check = ttk.Checkbutton(
            panel, text="Отправить результат OZON в Google Таблицу (необязательно)",
            variable=self.upload_google)
        self.google_check.pack(anchor="w", pady=(2, 10))

        actions = ttk.Frame(panel, style="Main.TFrame")
        actions.pack(fill="x", pady=(0, 12))
        self.start_button = ttk.Button(actions, text="Проверить цены",
                                       style="Run.TButton", command=self.start)
        self.start_button.pack(side="left")
        ttk.Label(actions, textvariable=self.status, style="Main.TLabel",
                  wraplength=390).pack(side="left", padx=(18, 0))
        ttk.Label(panel, text="Ход проверки", style="Main.TLabel").pack(anchor="w")
        self.log = scrolledtext.ScrolledText(panel, height=12, font=("Consolas", 9),
                                             wrap="word", state="disabled",
                                             relief="flat", bg="#FFFFFF",
                                             fg="#27384B", padx=10, pady=9)
        self.log.pack(fill="both", expand=True, pady=(6, 0))
        self.write_log("Выберите маркетплейс и проверьте ссылку магазина и регион.")
        self.write_log("WB: публичный каталог может отвечать HTTP 403; доступ пока не подтверждён.")
        root.after(120, self.consume_events)

    def _bind_editing(self, entry):
        entry.bind("<Control-KeyPress>", self._control_shortcut)
        entry.bind("<Shift-Insert>", self._paste_entry)
        entry.bind("<Button-3>", self._show_edit_menu)

    def on_market_change(self, _event=None):
        if self.market.get() == "WB":
            self.store.set(WB_STORE)
            self.shop_name.set("JKeratin")
            self._auto_store_name = "JKeratin"
            self.region.set("Москва")
            self.region_entry.configure(values=WB_REGIONS)
            self.store_label.configure(text="Ссылка на магазин WB")
            self.region_label.configure(text="Город доставки WB")
            self.region_note.configure(
                text="Выберите город из списка или введите числовой код dest. Это регион, не конкретный ПВЗ.")
            self.google_check.configure(state="disabled")
            self.upload_google.set(False)
        else:
            self.store.set(DEFAULT_STORE)
            self.region.set(DEFAULT_PVZ)
            self.region_entry.configure(values=())
            self.store_label.configure(text="Ссылка на магазин OZON")
            self.region_label.configure(text="Ссылка на пункт выдачи (ПВЗ) OZON")
            self.region_note.configure(text="Для OZON укажите ссылку на ПВЗ.")
            self.google_check.configure(state="normal")
        self.shop_name.set("JKeratin")
        self._auto_store_name = "JKeratin"

    def _update_store_name(self, _event=None):
        suggested = suggest_store_name(self.market.get(), self.store.get())
        if not self.shop_name.get().strip() or self.shop_name.get() == self._auto_store_name:
            self.shop_name.set(suggested)
        self._auto_store_name = suggested

    @staticmethod
    def _paste_entry(event):
        widget = event.widget
        try:
            value = widget.clipboard_get()
            if widget.selection_present():
                widget.delete("sel.first", "sel.last")
            widget.insert("insert", value)
        except tk.TclError:
            pass
        return "break"

    @staticmethod
    def _control_shortcut(event):
        widget = event.widget
        key = event.keycode
        if key == 86:
            return PricesApp._paste_entry(event)
        if key == 65:
            widget.select_range(0, "end")
            widget.icursor("end")
            return "break"
        if key == 67 and widget.selection_present():
            widget.clipboard_clear()
            widget.clipboard_append(widget.selection_get())
            return "break"
        if key == 88 and widget.selection_present():
            widget.clipboard_clear()
            widget.clipboard_append(widget.selection_get())
            widget.delete("sel.first", "sel.last")
            return "break"

    def _show_edit_menu(self, event):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Вставить", command=lambda: self._paste_entry(event))
        menu.add_command(label="Выделить всё",
                         command=lambda: event.widget.select_range(0, "end"))
        menu.tk_popup(event.x_root, event.y_root)
        menu.grab_release()

    def write_log(self, message):
        self.log.configure(state="normal")
        self.log.insert("end", str(message) + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def start(self):
        if self.busy:
            return
        self._update_store_name()
        marketplace = self.market.get()
        shop_name = self.shop_name.get().strip()
        if not shop_name:
            messagebox.showerror("Проверьте данные", "Укажите название магазина для файла Excel.")
            return
        try:
            if marketplace == "OZON":
                store, region = store_url(self.store.get().strip() or DEFAULT_STORE), pvz_url(
                    self.region.get().strip() or DEFAULT_PVZ)
            else:
                from wb_scraper import normalize_destination, normalize_store_url, DESTINATIONS
                store = normalize_store_url(self.store.get())
                selected = self.region.get().strip()
                region = normalize_destination(DESTINATIONS.get(selected, selected))
        except ValueError as exc:
            messagebox.showerror("Проверьте данные", str(exc))
            return
        self.busy = True
        self.start_button.configure(state="disabled")
        self.status.set("Подготовка...")
        self.write_log(f"Маркетплейс: {marketplace}")
        self.write_log(f"Магазин: {store}")
        self.write_log(f"Имя для Excel: {shop_name}")
        self.write_log(f"Регион/ПВЗ: {region}")
        thread = threading.Thread(
            target=self.collect_prices,
            args=(marketplace, store, region, bool(self.save_excel.get()),
                  bool(self.upload_google.get()), shop_name),
            daemon=True,
        )
        thread.start()

    def collect_prices(self, marketplace, store, region, include_excel, include_google, shop_name):
        try:
            if marketplace == "OZON":
                from scraper import collect
                self.events.put(("status", "Запускаем Chrome для OZON в фоновом режиме..."))
                def report(message):
                    self.events.put(("status", message))
                    self.events.put(("log", "[OZON] " + message))
                catalog = collect(store, region, progress=report)
            else:
                from wb_scraper import collect
                self.events.put(("status", "Проверяем открытый каталог WB без авторизации..."))
                catalog = collect(store, region)
            self.events.put(("log", f"Найдено товаров: {len(catalog.items)}; "
                                    f"время: {catalog.elapsed_seconds} с."))
            if include_excel:
                path = export_excel(catalog.items, marketplace, shop_name)
                self.events.put(("log", f"Excel сохранён: {path}"))
            if include_google:
                if marketplace != "OZON":
                    raise ValueError("Выгрузка WB в Google Таблицу будет добавлена после локального теста.")
                from google_sheets import load_connection, upload_catalog
                self.events.put(("status", "Отправляем данные OZON в Google Таблицу..."))
                connection = load_connection()
                result = upload_catalog(connection, catalog)
                self.events.put(("log", f"В Google Таблицу записано строк: {result['rows']}."))
            self.events.put(("done", f"Готово. Проверено товаров: {len(catalog.items)}."))
        except Exception as exc:
            self.events.put(("error", str(exc)))

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
        import requests
        destination = Path(sys.argv[sys.argv.index("--check-build") + 1])
        destination.write_text("OK", encoding="utf-8")
        return
    root = tk.Tk()
    PricesApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
