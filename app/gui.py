"""Combined local Ozon and Wildberries price-checking app."""
from __future__ import annotations

import logging
import queue
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from config import DEFAULT_PVZ, DEFAULT_STORE
from core import pvz_url, store_url

WB_STORE = "https://www.wildberries.ru/seller/215484/"
WB_DEST = "-1257786"


def export_excel(items: list[dict], marketplace: str) -> Path:
    from xlsx_export import to_xlsx

    base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    destination = base / "exports"
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    path = destination / f"{marketplace.lower()}_{stamp}.xlsx"
    path.write_bytes(to_xlsx(items))
    return path


class PricesApp:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.busy = False
        self.market = tk.StringVar(value="Ozon")
        self.store = tk.StringVar(value=DEFAULT_STORE)
        self.region = tk.StringVar(value=DEFAULT_PVZ)
        self.save_excel = tk.BooleanVar(value=True)
        # Local-first mode: Google upload is deliberately opt-in.
        self.upload_google = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Готово к проверке")

        root.title("Проверка цен Ozon и Wildberries")
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
                                          values=("Ozon", "Wildberries"),
                                          state="readonly", font=("Segoe UI", 10))
        self.market_choice.pack(fill="x", pady=(5, 13))
        self.market_choice.bind("<<ComboboxSelected>>", self.on_market_change)

        self.store_label = ttk.Label(panel, text="Ссылка на магазин Ozon",
                                     style="Main.TLabel")
        self.store_label.pack(anchor="w")
        self.store_entry = ttk.Entry(panel, textvariable=self.store, font=("Segoe UI", 10))
        self.store_entry.pack(fill="x", pady=(5, 3))
        self._bind_editing(self.store_entry)

        self.region_label = ttk.Label(panel, text="Ссылка на пункт выдачи (ПВЗ) Ozon",
                                      style="Main.TLabel")
        self.region_label.pack(anchor="w", pady=(11, 0))
        self.region_entry = ttk.Entry(panel, textvariable=self.region, font=("Segoe UI", 10))
        self.region_entry.pack(fill="x", pady=(5, 3))
        self._bind_editing(self.region_entry)
        self.region_note = ttk.Label(panel, text="Для Ozon укажите ссылку на ПВЗ.",
                                     style="Note.TLabel")
        self.region_note.pack(anchor="w", pady=(0, 10))

        ttk.Checkbutton(panel, text="Сохранить Excel в папку exports",
                        variable=self.save_excel).pack(anchor="w", pady=(2, 3))
        self.google_check = ttk.Checkbutton(
            panel, text="Отправить результат Ozon в Google Таблицу (необязательно)",
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
        self.write_log("WB-прототип запрашивает открытый каталог без cookies/авторизации.")
        root.after(120, self.consume_events)

    def _bind_editing(self, entry):
        entry.bind("<Control-KeyPress>", self._control_shortcut)
        entry.bind("<Shift-Insert>", self._paste_entry)
        entry.bind("<Button-3>", self._show_edit_menu)

    def on_market_change(self, _event=None):
        if self.market.get() == "Wildberries":
            self.store.set(WB_STORE)
            self.region.set(WB_DEST)
            self.store_label.configure(text="Ссылка на магазин Wildberries")
            self.region_label.configure(text="Код региона WB (dest)")
            self.region_note.configure(
                text="Стандартные коды: Москва −1257786, Санкт-Петербург −1205339, Казань −2133462. "
                     "Укажите другой числовой dest вручную. Это регион выдачи, не конкретный ПВЗ.")
            self.google_check.configure(state="disabled")
            self.upload_google.set(False)
        else:
            self.store.set(DEFAULT_STORE)
            self.region.set(DEFAULT_PVZ)
            self.store_label.configure(text="Ссылка на магазин Ozon")
            self.region_label.configure(text="Ссылка на пункт выдачи (ПВЗ) Ozon")
            self.region_note.configure(text="Для Ozon укажите ссылку на ПВЗ.")
            self.google_check.configure(state="normal")

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
        marketplace = self.market.get()
        try:
            if marketplace == "Ozon":
                store, region = store_url(self.store.get().strip() or DEFAULT_STORE), pvz_url(
                    self.region.get().strip() or DEFAULT_PVZ)
            else:
                from wb_scraper import normalize_destination, normalize_store_url
                store = normalize_store_url(self.store.get())
                region = normalize_destination(self.region.get())
        except ValueError as exc:
            messagebox.showerror("Проверьте данные", str(exc))
            return
        self.busy = True
        self.start_button.configure(state="disabled")
        self.status.set("Подготовка...")
        self.write_log(f"Маркетплейс: {marketplace}")
        self.write_log(f"Магазин: {store}")
        self.write_log(f"Регион/ПВЗ: {region}")
        thread = threading.Thread(
            target=self.collect_prices,
            args=(marketplace, store, region, bool(self.save_excel.get()),
                  bool(self.upload_google.get())),
            daemon=True,
        )
        thread.start()

    def collect_prices(self, marketplace, store, region, include_excel, include_google):
        try:
            if marketplace == "Ozon":
                from scraper import collect
                self.events.put(("status", "Собираем каталог Ozon в Chrome..."))
                catalog = collect(store, region)
            else:
                from wb_scraper import collect
                self.events.put(("status", "Проверяем открытый каталог WB без авторизации..."))
                catalog = collect(store, region)
            self.events.put(("log", f"Найдено товаров: {len(catalog.items)}; "
                                    f"время: {catalog.elapsed_seconds} с."))
            if include_excel:
                path = export_excel(catalog.items, marketplace)
                self.events.put(("log", f"Excel сохранён: {path}"))
            if include_google:
                if marketplace != "Ozon":
                    raise ValueError("Выгрузка WB в Google Таблицу будет добавлена после локального теста.")
                from google_sheets import load_connection, upload_catalog
                self.events.put(("status", "Отправляем данные Ozon в Google Таблицу..."))
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
