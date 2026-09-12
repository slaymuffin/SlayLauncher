import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import minecraft_launcher_lib
import subprocess
import threading
import os
import sys
import uuid
import json
import logging
import random
import ctypes
import shutil
import time
import webbrowser
from io import BytesIO
import urllib.request

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from modules.config import (
    APP_NAME, VERSION, ACCENTS, COLORS, QUOTES, THEMES, LAUNCHER_VERSION_URL,
    apply_theme, ACHIEVEMENTS,
)
from modules import settings as st_mod
from modules import java_manager, mods_manager, curseforge_manager
from modules import backups, discord_rpc, tray as tray_mod
from modules import achievements as ach_mod
from modules import autostart as auto_mod
from modules import stats as stats_mod
from modules import sounds as snd_mod
from modules import system_check, crash_analyzer
from modules.animation import AnimatedSpinner
from modules.toasts import Toast

logging.basicConfig(
    filename="slaylauncher.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    encoding="utf-8",
)
log = logging.getLogger("slay")
log.info(f"=== {APP_NAME} {VERSION} ===")

ctk.set_appearance_mode("dark")


def parse_vanilla(v):
    parts = []
    for chunk in v.split("."):
        num = ""
        for ch in chunk:
            if ch.isdigit():
                num += ch
            else:
                break
        parts.append(int(num) if num else 0)
    return tuple(parts)


def parse_forge(v):
    if "-" not in v:
        return ((), ())

    def to_tuple(s):
        parts = []
        for chunk in s.split("."):
            num = ""
            for ch in chunk:
                if ch.isdigit():
                    num += ch
                else:
                    break
            parts.append(int(num) if num else 0)
        return tuple(parts)

    return (to_tuple(v.split("-")[0]), to_tuple("-".join(v.split("-")[1:])))


def fetch_skin(nickname, size=64):
    if not HAS_PIL or not nickname:
        return None
    try:
        url = f"https://mc-heads.net/avatar/{nickname}/{size}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = resp.read()
        return Image.open(BytesIO(data)).convert("RGBA")
    except Exception:
        return None


def make_window_rectangular(window):
    try:
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 33, ctypes.byref(value), ctypes.sizeof(value)
        )
    except Exception:
        pass


class VersionDropdown(ctk.CTkFrame):
    def __init__(self, parent, variable, on_select=None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.variable = variable
        self.on_select = on_select
        self.values = []
        self.popup = None
        self._watch_id = None

        self.button = ctk.CTkButton(
            self, textvariable=variable, height=42,
            font=("Segoe UI", 12),
            fg_color=COLORS["bg2"], hover_color=COLORS["card_hover"],
            text_color=COLORS["text"], corner_radius=4,
            border_width=1, border_color=COLORS["border"],
            anchor="w", command=self.toggle_popup,
        )
        self.button.pack(fill="x")
        ctk.CTkLabel(self.button, text="v", font=("Segoe UI", 10),
                     text_color=COLORS["text_muted"]).place(relx=0.97, rely=0.5, anchor="e")

    def set_values(self, values):
        self.values = values or ["—"]
        if self.variable.get() not in self.values:
            self.variable.set(self.values[0])

    def toggle_popup(self):
        self.close_popup() if self.popup else self.open_popup()

    def open_popup(self):
        self.popup = ctk.CTkToplevel(self)
        self.popup.overrideredirect(True)
        self.popup.attributes("-topmost", True)
        try:
            self.popup.transient(self.winfo_toplevel())
        except Exception:
            pass

        self.update_idletasks()
        x = self.button.winfo_rootx()
        y = self.button.winfo_rooty() + self.button.winfo_height() + 4
        w = max(self.button.winfo_width(), 260)
        self.popup.geometry(f"{w}x340+{x}+{y}")
        self.popup.configure(fg_color=COLORS["card"])

        sf = ctk.CTkFrame(self.popup, fg_color="transparent")
        sf.pack(fill="x", padx=8, pady=(8, 4))
        self.search_entry = ctk.CTkEntry(
            sf, placeholder_text="Поиск версии...", height=34,
            font=("Segoe UI", 11),
            fg_color=COLORS["bg2"], border_color=COLORS["border"],
            text_color=COLORS["text"], corner_radius=4,
        )
        self.search_entry.pack(fill="x")
        self.search_entry.bind("<KeyRelease>", self._on_search)
        self.search_entry.bind("<Escape>", lambda e: self.close_popup())

        self.list_frame = ctk.CTkScrollableFrame(
            self.popup, fg_color=COLORS["bg2"], corner_radius=4,
            scrollbar_button_color=COLORS["accent"],
            scrollbar_button_hover_color=COLORS["accent_hover"],
        )
        self.list_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._render_items(self.values)
        self.popup.bind("<FocusOut>", lambda e: self.after(100, self._maybe_close))
        self.search_entry.focus_set()
        self._watch_parent()

    def _watch_parent(self):
        if self.popup is None:
            return
        try:
            parent = self.winfo_toplevel()
            if parent.state() == "iconic" or not parent.winfo_viewable():
                self.close_popup()
                return
        except Exception:
            self.close_popup()
            return
        try:
            self._watch_id = self.popup.after(150, self._watch_parent)
        except Exception:
            pass

    def _maybe_close(self):
        if self.popup is None:
            return
        try:
            focused = self.popup.focus_get()
            if focused is None:
                return
            w = focused
            while w is not None:
                if w == self.popup:
                    return
                w = getattr(w, "master", None)
            self.close_popup()
        except Exception:
            pass

    def _render_items(self, items):
        for w in self.list_frame.winfo_children():
            w.destroy()
        if not items:
            ctk.CTkLabel(self.list_frame, text="Ничего не найдено",
                         text_color=COLORS["text_muted"]).pack(pady=10)
            return
        for item in items[:500]:
            ctk.CTkButton(
                self.list_frame, text=item, anchor="w", height=30,
                font=("Segoe UI", 11),
                fg_color="transparent", hover_color=COLORS["card_hover"],
                text_color=COLORS["text"], corner_radius=4,
                command=lambda i=item: self._select(i),
            ).pack(fill="x", pady=1)

    def _on_search(self, event):
        q = self.search_entry.get().lower().strip()
        self._render_items(self.values if not q else [v for v in self.values if q in v.lower()])

    def _select(self, value):
        self.variable.set(value)
        if self.on_select:
            self.on_select(value)
        self.close_popup()

    def close_popup(self):
        if self._watch_id:
            try:
                self.after_cancel(self._watch_id)
            except Exception:
                pass
            self._watch_id = None
        if self.popup:
            try:
                self.popup.destroy()
            except Exception:
                pass
            self.popup = None


class SlayLauncher(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1100x720")
        self.resizable(False, False)
        self.withdraw()

        # Устанавливаем иконку окна (для панели задач и заголовка)
        try:
            icon_path = self._resource_path("icon.ico")
            self.iconbitmap(icon_path)
        except Exception as e:
            log.warning(f"icon load error: {e}")

        self.settings = st_mod.load_settings()

        # Авто-выбор сезонной темы
        if self.settings.get("seasonal_themes", True):
            import datetime
            now = datetime.datetime.now()
            if now.month == 10 and 20 <= now.day <= 31:
                self.settings["theme_name"] = "halloween"
            elif (now.month == 12 and now.day >= 15) or (now.month == 1 and now.day <= 10):
                self.settings["theme_name"] = "newyear"

        apply_theme(self.settings.get("accent", "pink"),
                    self.settings.get("theme_name", "vaporwave"))
        self.configure(fg_color=COLORS["bg"])

        mc_dir = self.settings.get("mc_dir")
        if not mc_dir or not os.path.isdir(mc_dir):
            mc_dir = os.path.expanduser("~/.slayminecraft")
            self.settings["mc_dir"] = mc_dir
        os.makedirs(mc_dir, exist_ok=True)

        self.type_var = ctk.StringVar(value=self.settings["version_type"])
        self.version_var = ctk.StringVar(value=self.settings["version"])
        self.show_releases = ctk.BooleanVar(value=self.settings["show_releases"])
        self.show_snapshots = ctk.BooleanVar(value=self.settings["show_snapshots"])
        self.show_old_beta = ctk.BooleanVar(value=self.settings["show_old_beta"])
        self.show_old_alpha = ctk.BooleanVar(value=self.settings["show_old_alpha"])
        self.forge_only_latest = ctk.BooleanVar(value=self.settings["forge_only_latest"])
        self.sounds_on = ctk.BooleanVar(value=self.settings["sounds_on"])

        self.current_page = "main"
        self.avatar_image = None
        self.rpc = discord_rpc.RPC()
        self.tray_icon = None
        self._particles = []
        self._pulse_state = 0

        self.build_ui()
        self.refresh_versions()
        self.update_main_button()
        self.refresh_installed()
        self.refresh_profiles()
        self.refresh_mods()
        self.refresh_backups()
        self.refresh_achievements()
        self.update_quote()
        self.load_avatar_async()
        self.bind_all("<Return>", lambda e: self.on_main_btn_click())

        self.after(200, lambda: make_window_rectangular(self))
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        if self.settings.get("splash_enabled", True):
            self.after(100, self._show_splash_then_main)
        else:
            self.deiconify()

        if self.settings.get("check_updates_on_start", True):
            self.after(3000, lambda: self.check_updates(silent=True))

        if self.settings.get("discord_rpc"):
            if self.rpc.connect():
                self.rpc.update(details="В лаунчере", state=f"{APP_NAME} v{VERSION}")

    def _resource_path(self, relative):
        try:
            base_path = sys._MEIPASS
        except AttributeError:
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative)

    # ---------------- СПЛЭШ ----------------
    def _show_splash_then_main(self):
        self.splash = ctk.CTkToplevel(self)
        self.splash.overrideredirect(True)

        w, h = 440, 280
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.splash.geometry(f"{w}x{h}+{x}+{y}")
        self.splash.configure(fg_color=COLORS["bg"])
        self.splash.attributes("-topmost", True)

        border = ctk.CTkFrame(
            self.splash, fg_color=COLORS["bg2"], corner_radius=0,
            border_width=2, border_color=COLORS["accent"],
        )
        border.pack(fill="both", expand=True)

        ctk.CTkLabel(border, text="⚡ SLAY", font=("Segoe UI Black", 28, "bold"),
                     text_color=COLORS["accent"]).pack(pady=(38, 4))
        ctk.CTkLabel(border, text="LAUNCHER", font=("Segoe UI", 15, "bold"),
                     text_color=COLORS["text"]).pack()

        self.splash_status = ctk.CTkLabel(
            border, text="Загрузка компонентов...",
            font=("Segoe UI", 10),
            text_color=COLORS["text_muted"],
        )
        self.splash_status.pack(pady=(20, 8))

        self.splash_progress = ctk.CTkProgressBar(
            border, width=300, height=6,
            progress_color=COLORS["accent"],
            fg_color=COLORS["card"],
        )
        self.splash_progress.set(0)
        self.splash_progress.pack(pady=(0, 10))

        ctk.CTkLabel(border, text=f"v{VERSION}", font=("Segoe UI", 8),
                     text_color=COLORS["text_muted"]).pack(side="bottom", pady=8)

        self._splash_value = 0.0
        self._splash_step()
        self.after(2400, self._close_splash)

    def _splash_step(self):
        if not hasattr(self, "splash") or not self.splash.winfo_exists():
            return
        self._splash_value = min(1.0, self._splash_value + 0.022)
        try:
            self.splash_progress.set(self._splash_value)
            texts = [
                "Загрузка компонентов...",
                "Проверка Java...",
                "Подготовка интерфейса...",
                "Почти готово...",
            ]
            idx = min(len(texts) - 1, int(self._splash_value * len(texts)))
            self.splash_status.configure(text=texts[idx])
        except Exception:
            pass

        if self._splash_value < 1.0:
            self.after(55, self._splash_step)
        else:
            self.after(200, self._close_splash)

    def _close_splash(self):
        try:
            if hasattr(self, "splash") and self.splash.winfo_exists():
                self.splash.destroy()
        except Exception:
            pass
        self.deiconify()
        self.lift()
        self.focus_force()

    # ---------------- ТЕМЫ / АКЦЕНТ ----------------
    def _on_theme_change(self, value):
        for key, theme in THEMES.items():
            if theme["name"] == value:
                self.settings["theme_name"] = key
                st_mod.save_settings(self.settings)

                apply_theme(self.settings.get("accent", "pink"), key)

                for widget in self.winfo_children():
                    widget.destroy()

                self.configure(fg_color=COLORS["bg"])

                self.build_ui()
                self.refresh_versions()
                self.update_main_button()
                self.refresh_installed()
                self.refresh_profiles()
                self.refresh_mods()
                self.refresh_backups()
                self.refresh_achievements()

                try:
                    self.switch_page(self.current_page)
                except Exception:
                    self.switch_page("main")

                self.toast(f"Тема: {value}", "success")
                return

    def set_accent(self, key):
        self.settings["accent"] = key
        st_mod.save_settings(self.settings)

        apply_theme(key, self.settings.get("theme_name", "vaporwave"))

        for widget in self.winfo_children():
            widget.destroy()

        self.configure(fg_color=COLORS["bg"])

        self.build_ui()
        self.refresh_versions()
        self.update_main_button()
        self.refresh_installed()
        self.refresh_profiles()
        self.refresh_mods()
        self.refresh_backups()
        self.refresh_achievements()

        try:
            self.switch_page(self.current_page)
        except Exception:
            self.switch_page("main")

        self.toast(f"Акцент: {key} применён", "success")

    def _toggle_splash(self):
        self.settings["splash_enabled"] = self.splash_var.get()
        st_mod.save_settings(self.settings)

    def _toggle_flash(self):
        self.settings["flash_on_launch"] = self.flash_var.get()
        st_mod.save_settings(self.settings)

    def _toggle_crash_check(self):
        self.settings["auto_crash_check"] = self.crash_check_var.get()
        st_mod.save_settings(self.settings)

    def _toggle_update_check(self):
        self.settings["check_updates_on_start"] = self.updates_check_var.get()
        st_mod.save_settings(self.settings)

    # ---------------- ИЗБРАННОЕ ----------------
    def toggle_favorite(self):
        v = self.version_var.get()
        if not v or v == "—":
            return
        favs = self.settings.setdefault("favorites", [])
        if v in favs:
            favs.remove(v)
            self.toast(f"Убрано из избранного: {v}", "info")
        else:
            favs.append(v)
            self.toast(f"Добавлено в избранное: {v}", "success")
        st_mod.save_settings(self.settings)
        self._update_fav_star()
        self.refresh_versions()

    def _update_fav_star(self):
        try:
            v = self.version_var.get()
            is_fav = v in self.settings.get("favorites", [])
            self.fav_btn.configure(
                text="*" if is_fav else "+",
                text_color=COLORS["accent"] if is_fav else COLORS["text_muted"],
            )
        except Exception:
            pass

    # ---------------- ВСПЫШКА ----------------
    def flash_animation(self):
        if not self.settings.get("flash_on_launch", True):
            return
        try:
            flash = tk.Toplevel(self)
            flash.overrideredirect(True)
            flash.configure(bg=COLORS["accent"])
            flash.attributes("-alpha", 0.0)
            flash.attributes("-topmost", True)

            x = self.winfo_rootx()
            y = self.winfo_rooty()
            w = self.winfo_width()
            h = self.winfo_height()
            flash.geometry(f"{w}x{h}+{x}+{y}")

            def step(alpha=0.6, direction=-1):
                alpha += direction * 0.08
                if alpha <= 0:
                    try:
                        flash.destroy()
                    except Exception:
                        pass
                    return
                try:
                    flash.attributes("-alpha", alpha)
                    flash.after(25, lambda: step(alpha, direction))
                except Exception:
                    pass

            step()
        except Exception as e:
            log.warning(f"flash error: {e}")

    # ---------------- ПРОВЕРКА СИСТЕМЫ ----------------
    def run_system_check(self):
        self.toast("Проверка системы...", "info")

        def worker():
            try:
                report = system_check.run_full_check(self.get_mc_dir())
                text = system_check.format_report(report)
                self.after(0, lambda t=text: self._show_system_report(t))
            except Exception as err:
                err_text = str(err)
                self.after(0, lambda t=err_text: messagebox.showerror("Ошибка", t))

        threading.Thread(target=worker, daemon=True).start()

    def _show_system_report(self, text):
        win = ctk.CTkToplevel(self)
        win.title("SlayLauncher - Проверка системы")
        win.geometry("680x580")
        win.configure(fg_color=COLORS["bg"])
        win.attributes("-topmost", True)

        ctk.CTkLabel(win, text="ПРОВЕРКА СИСТЕМЫ",
                     font=("Segoe UI Black", 16, "bold"),
                     text_color=COLORS["accent"]).pack(pady=(16, 8))

        txt = ctk.CTkTextbox(
            win, font=("Consolas", 11),
            fg_color=COLORS["card"],
            text_color=COLORS["text"],
            wrap="word",
            corner_radius=4,
        )
        txt.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        txt.insert("1.0", text)
        txt.configure(state="disabled")

        ctk.CTkButton(
            win, text="Закрыть", height=38,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#ffffff", corner_radius=4,
            command=win.destroy,
        ).pack(pady=(0, 16), padx=18, fill="x")

    # ---------------- ПРОВЕРКА ОБНОВЛЕНИЙ ----------------
    def check_updates(self, silent=False):
        if not silent:
            self.toast("Проверка обновлений...", "info")

        def worker():
            try:
                req = urllib.request.Request(
                    LAUNCHER_VERSION_URL,
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                remote_ver = data.get("version", "0.0")
                download_url = data.get("download_url", "")
                notes = data.get("release_notes", "")

                if remote_ver != VERSION:
                    self.after(0, lambda: self._show_update_window(
                        remote_ver, download_url, notes
                    ))
                else:
                    if not silent:
                        self.after(0, lambda: self.toast(
                            f"Установлена последняя версия ({VERSION})", "success"
                        ))
            except Exception as e:
                log.warning(f"Update check failed: {e}")
                if not silent:
                    err_text = str(e)
                    self.after(0, lambda t=err_text: self.toast(
                        f"Не удалось проверить: {t}", "error"
                    ))

        threading.Thread(target=worker, daemon=True).start()

    def _show_update_window(self, version, url, notes):
        win = ctk.CTkToplevel(self)
        win.title("Доступно обновление")
        win.geometry("520x420")
        win.configure(fg_color=COLORS["bg"])
        win.attributes("-topmost", True)

        ctk.CTkLabel(win, text=f"🎉 Доступна новая версия: {version}",
                     font=("Segoe UI Black", 16, "bold"),
                     text_color=COLORS["accent"]).pack(pady=(20, 6))

        ctk.CTkLabel(win, text=f"У тебя установлена: v{VERSION}",
                     font=("Segoe UI", 11),
                     text_color=COLORS["text_muted"]).pack(pady=(0, 12))

        ctk.CTkLabel(win, text="Что нового:",
                     font=("Segoe UI", 11, "bold"),
                     text_color=COLORS["accent"], anchor="w").pack(fill="x", padx=18)

        txt = ctk.CTkTextbox(
            win, font=("Segoe UI", 10),
            fg_color=COLORS["card"],
            text_color=COLORS["text"],
            wrap="word",
            corner_radius=4,
        )
        txt.pack(fill="both", expand=True, padx=18, pady=(4, 12))
        txt.insert("1.0", notes or "Без описания")
        txt.configure(state="disabled")

        bottom = ctk.CTkFrame(win, fg_color="transparent")
        bottom.pack(fill="x", padx=18, pady=(0, 16))

        ctk.CTkButton(
            bottom, text="⬇  Скачать обновление", height=42,
            font=("Segoe UI", 12, "bold"),
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            text_color="#ffffff", corner_radius=4,
            command=lambda u=url: webbrowser.open(u) if u else None,
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))

        ctk.CTkButton(
            bottom, text="Позже", height=42,
            fg_color=COLORS["card_hover"], hover_color=COLORS["card_hover"],
            text_color=COLORS["text"], corner_radius=4,
            command=win.destroy,
        ).pack(side="left", expand=True, fill="x", padx=(4, 0))

    # ---------------- КРАШ ----------------
    def watch_for_crash(self, start_time, version):
        if not self.settings.get("auto_crash_check", True):
            return
        time.sleep(5)
        mc_dir = self.get_mc_dir()
        for _ in range(20):
            time.sleep(3)
            try:
                path, text = crash_analyzer.find_recent_crash(mc_dir, start_time)
                if path and text:
                    title, explain, tips = crash_analyzer.analyze(text, version)
                    key_lines = crash_analyzer.extract_key_lines(text)
                    self.after(0, lambda t=title, e=explain, p=tips, f=path, k=key_lines:
                               self._show_crash_window(t, e, p, f, k))
                    return
            except Exception:
                pass

    def _show_crash_window(self, title, explain, tips, path, key_lines):
        win = ctk.CTkToplevel(self)
        win.title("SlayLauncher - Обнаружен краш")
        win.geometry("700x620")
        win.configure(fg_color=COLORS["bg"])
        win.attributes("-topmost", True)

        ctk.CTkLabel(win, text=title,
                     font=("Segoe UI Black", 16, "bold"),
                     text_color=COLORS["danger"]).pack(pady=(18, 6))

        ctk.CTkLabel(win, text=explain,
                     font=("Segoe UI", 11),
                     text_color=COLORS["text"],
                     wraplength=640, justify="left").pack(padx=18, pady=(0, 12))

        ctk.CTkLabel(win, text="Что попробовать:",
                     font=("Segoe UI", 11, "bold"),
                     text_color=COLORS["accent"], anchor="w").pack(fill="x", padx=18)

        for tip in tips:
            ctk.CTkLabel(win, text=f"   - {tip}",
                         font=("Segoe UI", 10),
                         text_color=COLORS["text_muted"],
                         anchor="w", wraplength=640, justify="left").pack(fill="x", padx=18)

        ctk.CTkLabel(win, text="Ключевые строки из лога:",
                     font=("Segoe UI", 11, "bold"),
                     text_color=COLORS["accent"], anchor="w").pack(fill="x", padx=18, pady=(14, 4))

        txt = ctk.CTkTextbox(
            win, font=("Consolas", 9),
            fg_color=COLORS["card"],
            text_color=COLORS["text_muted"],
            wrap="word",
            corner_radius=4,
        )
        txt.pack(fill="both", expand=True, padx=18, pady=(0, 10))
        txt.insert("1.0", "\n".join(key_lines))
        txt.configure(state="disabled")

        bottom = ctk.CTkFrame(win, fg_color="transparent")
        bottom.pack(fill="x", padx=18, pady=(0, 16))

        ctk.CTkButton(
            bottom, text="Открыть полный лог", height=36,
            fg_color=COLORS["card_hover"], hover_color=COLORS["accent"],
            text_color=COLORS["text"], corner_radius=4,
            command=lambda p=path: os.startfile(p) if os.path.isfile(p) else None,
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))

        ctk.CTkButton(
            bottom, text="Закрыть", height=36,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            text_color="#ffffff", corner_radius=4,
            command=win.destroy,
        ).pack(side="left", expand=True, fill="x", padx=(4, 0))

    # ---------------- UI ----------------
    def build_ui(self):
        self.sidebar = ctk.CTkFrame(self, width=220, fg_color=COLORS["bg2"], corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        self.build_sidebar()

        container = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        container.pack(side="left", fill="both", expand=True)

        self.pages = {}
        for key in ["main", "installed", "mods", "profiles",
                    "backups", "achievements", "logs", "settings"]:
            self.pages[key] = ctk.CTkFrame(container, fg_color=COLORS["bg"])

        self.build_main_page()
        self.build_installed_page()
        self.build_mods_page()
        self.build_profiles_page()
        self.build_backups_page()
        self.build_achievements_page()
        self.build_logs_page()
        self.build_settings_page()

        self.pages["main"].pack(fill="both", expand=True, padx=22, pady=18)

    def build_sidebar(self):
        self.sidebar_canvas = tk.Canvas(
            self.sidebar, highlightthickness=0, bd=0, bg=COLORS["bg2"]
        )
        self.sidebar_canvas.place(x=0, y=0, relwidth=1, relheight=1)

        self._particles = []
        for _ in range(18):
            self._spawn_particle(initial=True)

        logo = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo.pack(fill="x", pady=(20, 6))

        self.lightning_label = ctk.CTkLabel(
            logo, text="⚡  SLAY",
            font=("Segoe UI Black", 22, "bold"),
            text_color=COLORS["accent"],
        )
        self.lightning_label.pack()

        ctk.CTkLabel(logo, text="LAUNCHER", font=("Segoe UI", 12, "bold"),
                     text_color=COLORS["text"]).pack()
        ctk.CTkLabel(logo, text="slay your game",
                     font=("Segoe UI", 9, "italic"),
                     text_color=COLORS["text_muted"]).pack(pady=(2, 0))

        ctk.CTkFrame(self.sidebar, height=1, fg_color=COLORS["border"]).pack(fill="x", padx=16, pady=12)

        self.nav_buttons = {}
        tabs = [
            ("main", "Главная"),
            ("installed", "Установленные"),
            ("mods", "Моды"),
            ("profiles", "Профили"),
            ("backups", "Бэкапы"),
            ("achievements", "Достижения"),
            ("logs", "Логи"),
            ("settings", "Настройки"),
        ]
        for key, label in tabs:
            btn = ctk.CTkButton(
                self.sidebar, text=label, height=38,
                font=("Segoe UI", 11, "bold"),
                fg_color=COLORS["accent"] if key == self.current_page else "transparent",
                hover_color=COLORS["card_hover"],
                text_color=COLORS["text"] if key == self.current_page else COLORS["text_muted"],
                corner_radius=4, anchor="w",
                command=lambda k=key: self.switch_page(k),
            )
            btn.pack(fill="x", padx=10, pady=2)
            self.nav_buttons[key] = btn

        bottom = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", pady=(0, 12))
        ctk.CTkLabel(bottom, text=f"Запусков: {self.settings.get('launches', 0)}",
                     font=("Segoe UI", 10),
                     text_color=COLORS["text_muted"]).pack(pady=(0, 4))
        ctk.CTkLabel(bottom, text=f"Часов: {stats_mod.total_hours(self.settings)}",
                     font=("Segoe UI", 10),
                     text_color=COLORS["text_muted"]).pack(pady=(0, 4))
        ctk.CTkLabel(bottom, text=f"v{VERSION}  -  tg @slaylauncher",
                     font=("Segoe UI", 9),
                     text_color=COLORS["text_muted"]).pack()

        self._pulse_state = 0
        self._pulse_logo()
        self._animate_particles()

    # ---------------- АНИМАЦИИ ----------------
    def _spawn_particle(self, initial=False):
        try:
            size = random.choice([2, 3, 4])
            x = random.randint(10, 210)
            y = random.randint(0, 720) if initial else -10
            speed = random.uniform(0.3, 1.3)
            color = random.choice([
                COLORS["accent"],
                COLORS["text_muted"],
                "#ffffff",
            ])
            oval = self.sidebar_canvas.create_oval(
                x, y, x + size, y + size, fill=color, outline=""
            )
            self._particles.append({
                "id": oval, "x": x, "y": y, "speed": speed, "size": size,
            })
        except Exception:
            pass

    def _animate_particles(self):
        try:
            if not hasattr(self, "sidebar_canvas"):
                return
            for p in self._particles:
                p["y"] += p["speed"]
                if p["y"] > 720:
                    p["y"] = -10
                    p["x"] = random.randint(10, 210)
                self.sidebar_canvas.coords(
                    p["id"],
                    p["x"], p["y"],
                    p["x"] + p["size"], p["y"] + p["size"],
                )
            self.after(40, self._animate_particles)
        except Exception:
            pass

    def _pulse_logo(self):
        try:
            if not hasattr(self, "lightning_label"):
                return
            self._pulse_state = (self._pulse_state + 1) % 40
            factor = 0.85 + 0.15 * abs(1 - self._pulse_state / 20.0)

            base = COLORS["accent"].lstrip("#")
            r = int(base[0:2], 16)
            g = int(base[2:4], 16)
            b = int(base[4:6], 16)
            r = min(255, int(r * factor + 40))
            g = min(255, int(g * factor + 40))
            b = min(255, int(b * factor + 40))
            color = f"#{r:02x}{g:02x}{b:02x}"

            self.lightning_label.configure(text_color=color)
            self.after(80, self._pulse_logo)
        except Exception:
            pass

    def switch_page(self, page):
        self.current_page = page
        for k, b in self.nav_buttons.items():
            if k == page:
                b.configure(fg_color=COLORS["accent"], text_color=COLORS["text"])
            else:
                b.configure(fg_color="transparent", text_color=COLORS["text_muted"])
        for p in self.pages.values():
            p.pack_forget()
        self.pages[page].pack(fill="both", expand=True, padx=22, pady=18)

        {
            "installed": self.refresh_installed,
            "mods": self.refresh_mods,
            "profiles": self.refresh_profiles,
            "backups": self.refresh_backups,
            "achievements": self.refresh_achievements,
            "logs": self.refresh_logs,
        }.get(page, lambda: None)()

    def card(self, parent, **kw):
        return ctk.CTkFrame(parent, fg_color=COLORS["card"], corner_radius=4,
                            border_width=1, border_color=COLORS["border"], **kw)

    def build_main_page(self):
        p = self.pages["main"]
        cols = ctk.CTkFrame(p, fg_color="transparent")
        cols.pack(fill="both", expand=True)

        left = ctk.CTkFrame(cols, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        right = ctk.CTkFrame(cols, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))

        c1 = self.card(left)
        c1.pack(fill="x", pady=(0, 12))
        i1 = ctk.CTkFrame(c1, fg_color="transparent")
        i1.pack(fill="x", padx=18, pady=16)

        self.avatar_label = ctk.CTkLabel(i1, text="?", font=("Segoe UI", 40),
                                         width=64, height=64)
        self.avatar_label.pack(side="left", padx=(0, 14))

        ri = ctk.CTkFrame(i1, fg_color="transparent")
        ri.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(ri, text="НИКНЕЙМ", font=("Segoe UI", 10, "bold"),
                     text_color=COLORS["text_muted"], anchor="w").pack(fill="x")
        self.nickname_entry = ctk.CTkEntry(ri, height=36, font=("Segoe UI", 13),
                                           fg_color=COLORS["bg2"], border_color=COLORS["border"],
                                           corner_radius=4, text_color=COLORS["text"])
        self.nickname_entry.insert(0, self.settings["nickname"])
        self.nickname_entry.pack(fill="x", pady=(4, 0))
        self.nickname_entry.bind("<FocusOut>", lambda e: self.load_avatar_async())

        c2 = self.card(left)
        c2.pack(fill="x", pady=(0, 12))
        i2 = ctk.CTkFrame(c2, fg_color="transparent")
        i2.pack(fill="x", padx=18, pady=16)

        ctk.CTkLabel(i2, text="ТИП ВЕРСИИ", font=("Segoe UI", 10, "bold"),
                     text_color=COLORS["text_muted"], anchor="w").pack(fill="x", pady=(0, 6))
        self.type_seg = ctk.CTkSegmentedButton(
            i2, values=["Ванилла", "Forge", "Fabric"],
            variable=self.type_var, height=34,
            font=("Segoe UI", 11, "bold"),
            fg_color=COLORS["bg2"],
            selected_color=COLORS["accent"],
            unselected_color=COLORS["bg2"],
            unselected_hover_color=COLORS["card_hover"],
            text_color=COLORS["text"], corner_radius=4,
            command=lambda _: self.on_type_change(),
        )
        self.type_seg.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(i2, text="ВЕРСИЯ", font=("Segoe UI", 10, "bold"),
                     text_color=COLORS["text_muted"], anchor="w").pack(fill="x", pady=(0, 4))

        ver_row = ctk.CTkFrame(i2, fg_color="transparent")
        ver_row.pack(fill="x")

        self.version_dropdown = VersionDropdown(
            ver_row, variable=self.version_var,
            on_select=lambda _: (self.update_main_button(), self._update_fav_star()),
        )
        self.version_dropdown.pack(side="left", fill="x", expand=True)

        self.fav_btn = ctk.CTkButton(
            ver_row, text="+", width=42, height=42,
            font=("Segoe UI", 16, "bold"),
            fg_color=COLORS["bg2"], hover_color=COLORS["card_hover"],
            text_color=COLORS["text_muted"], corner_radius=4,
            border_width=1, border_color=COLORS["border"],
            command=self.toggle_favorite,
        )
        self.fav_btn.pack(side="left", padx=(6, 0))

        c3 = self.card(right)
        c3.pack(fill="both", expand=True)
        i3 = ctk.CTkFrame(c3, fg_color="transparent")
        i3.pack(fill="both", expand=True, padx=18, pady=16)

        ctk.CTkLabel(i3, text="СТАТУС", font=("Segoe UI", 10, "bold"),
                     text_color=COLORS["text_muted"], anchor="w").pack(fill="x", pady=(0, 10))

        status_box = ctk.CTkFrame(i3, fg_color="transparent", height=34)
        status_box.pack(fill="x", pady=(0, 14))
        status_box.pack_propagate(False)

        self.loader = AnimatedSpinner(status_box, frame_set="braille")
        self.loader.pack(fill="both", expand=True)
        self.status_label = self.loader.text

        prog_box = ctk.CTkFrame(i3, fg_color="transparent", height=14)
        prog_box.pack(fill="x", pady=(0, 18))
        prog_box.pack_propagate(False)
        self.progress = ctk.CTkProgressBar(prog_box, height=8, corner_radius=4,
                                           progress_color=COLORS["accent"],
                                           fg_color=COLORS["bg2"])
        self.progress.set(0)
        self.progress.pack(fill="x", pady=(3, 0))

        self.main_btn = ctk.CTkButton(i3, text="УСТАНОВИТЬ", height=64,
                                      font=("Segoe UI Black", 16, "bold"),
                                      fg_color=COLORS["accent"],
                                      hover_color=COLORS["accent_hover"],
                                      text_color="#ffffff", corner_radius=4,
                                      command=self.on_main_btn_click)
        self.main_btn.pack(fill="x")

        quote_box = ctk.CTkFrame(i3, fg_color="transparent", height=44)
        quote_box.pack(fill="x", pady=(16, 0))
        quote_box.pack_propagate(False)
        self.quote_label = ctk.CTkLabel(quote_box, text="", font=("Segoe UI", 10, "italic"),
                                        text_color=COLORS["text_muted"],
                                        wraplength=320, anchor="center")
        self.quote_label.pack(expand=True)

    def build_installed_page(self):
        p = self.pages["installed"]
        c = self.card(p)
        c.pack(fill="both", expand=True)
        inner = ctk.CTkFrame(c, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=18, pady=16)

        h = ctk.CTkFrame(inner, fg_color="transparent")
        h.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(h, text="УСТАНОВЛЕННЫЕ ВЕРСИИ",
                     font=("Segoe UI", 13, "bold"),
                     text_color=COLORS["text"]).pack(side="left")
        ctk.CTkButton(h, text="Обновить", width=110, height=30,
                      font=("Segoe UI", 10),
                      fg_color=COLORS["card_hover"], hover_color=COLORS["accent"],
                      text_color=COLORS["text"], corner_radius=4,
                      command=self.refresh_installed).pack(side="right")

        self.installed_scroll = ctk.CTkScrollableFrame(
            inner, fg_color=COLORS["bg2"], corner_radius=4,
            scrollbar_button_color=COLORS["accent"])
        self.installed_scroll.pack(fill="both", expand=True)

    def refresh_installed(self):
        for w in self.installed_scroll.winfo_children():
            w.destroy()
        vdir = os.path.join(self.get_mc_dir(), "versions")
        if not os.path.isdir(vdir):
            ctk.CTkLabel(self.installed_scroll, text="Пока ничего не установлено",
                         text_color=COLORS["text_muted"]).pack(pady=20)
            return
        items = []
        for name in os.listdir(vdir):
            path = os.path.join(vdir, name)
            if not os.path.isdir(path):
                continue
            if not any(f.endswith(".json") for f in os.listdir(path)):
                continue
            try:
                size_mb = sum(os.path.getsize(os.path.join(dp, f))
                              for dp, dn, fn in os.walk(path) for f in fn) // (1024 * 1024)
            except Exception:
                size_mb = 0
            items.append((name, size_mb))
        items.sort(key=lambda x: x[0], reverse=True)
        for name, size in items:
            row = ctk.CTkFrame(self.installed_scroll, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=name, anchor="w", font=("Segoe UI", 11),
                         text_color=COLORS["text"]).pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(row, text=f"{size} МБ", font=("Segoe UI", 9),
                         text_color=COLORS["text_muted"], width=70).pack(side="left", padx=(10, 8))
            ctk.CTkButton(row, text="X", width=34, height=28,
                          fg_color=COLORS["card_hover"], hover_color=COLORS["danger"],
                          text_color=COLORS["text"], corner_radius=4,
                          command=lambda n=name: self.delete_version(n)).pack(side="left")

    def delete_version(self, name):
        if not messagebox.askyesno("Удаление", f"Удалить версию {name}?"):
            return
        try:
            shutil.rmtree(os.path.join(self.get_mc_dir(), "versions", name))
            self.refresh_installed()
            self.update_main_button()
        except Exception as err:
            self.toast(str(err), "error")

    # ---------------- МОДЫ ----------------
    def build_mods_page(self):
        p = self.pages["mods"]
        c = self.card(p)
        c.pack(fill="both", expand=True)
        inner = ctk.CTkFrame(c, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=18, pady=16)

        ctk.CTkLabel(inner, text="МОДЫ",
                     font=("Segoe UI", 13, "bold"),
                     text_color=COLORS["text"], anchor="w").pack(fill="x", pady=(0, 8))

        src_row = ctk.CTkFrame(inner, fg_color="transparent")
        src_row.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(src_row, text="Источник:",
                     font=("Segoe UI", 11),
                     text_color=COLORS["text_muted"]).pack(side="left", padx=(0, 8))

        self.source_var = ctk.StringVar(value=self.settings.get("mod_source", "modrinth"))
        self.source_seg = ctk.CTkSegmentedButton(
            src_row,
            values=["Modrinth", "CurseForge"],
            variable=self.source_var,
            height=30,
            font=("Segoe UI", 10, "bold"),
            fg_color=COLORS["bg2"],
            selected_color=COLORS["accent"],
            unselected_color=COLORS["bg2"],
            text_color=COLORS["text"],
            corner_radius=4,
            command=self._on_mod_source_change,
        )
        self.source_seg.pack(side="left")

        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x", pady=(0, 10))
        self.mod_search_entry = ctk.CTkEntry(
            row, height=38, font=("Segoe UI", 12),
            fg_color=COLORS["bg2"], border_color=COLORS["border"],
            corner_radius=4, text_color=COLORS["text"],
            placeholder_text="Поиск мода...",
        )
        self.mod_search_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text="Найти", width=110, height=38,
                      font=("Segoe UI", 11, "bold"),
                      fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                      text_color="#ffffff", corner_radius=4,
                      command=self.search_mods).pack(side="left", padx=(8, 0))

        self.mods_results = ctk.CTkScrollableFrame(
            inner, fg_color=COLORS["bg2"], corner_radius=4,
            scrollbar_button_color=COLORS["accent"], height=280)
        self.mods_results.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(inner, text="Установленные моды",
                     font=("Segoe UI", 11, "bold"),
                     text_color=COLORS["text_muted"], anchor="w").pack(fill="x", pady=(0, 6))
        self.mods_installed = ctk.CTkScrollableFrame(
            inner, fg_color=COLORS["bg2"], corner_radius=4,
            scrollbar_button_color=COLORS["accent"])
        self.mods_installed.pack(fill="both", expand=True)

    def _on_mod_source_change(self, value):
        src = "curseforge" if value == "CurseForge" else "modrinth"
        self.settings["mod_source"] = src
        st_mod.save_settings(self.settings)
        self.toast(f"Источник: {value}", "info")

    def search_mods(self):
        q = self.mod_search_entry.get().strip()
        if not q:
            return
        for w in self.mods_results.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.mods_results, text="Поиск...",
                     text_color=COLORS["text_muted"]).pack(pady=10)
        self.update_idletasks()

        vt = self.type_var.get().lower()
        version_raw = self.version_var.get()
        if vt == "forge" and "-" in version_raw:
            mc_version = version_raw.split("-")[0]
        else:
            mc_version = version_raw

        if vt == "forge":
            loader = "forge"
        elif vt == "fabric":
            loader = "fabric"
        else:
            loader = None

        source = self.settings.get("mod_source", "modrinth")

        log.info(f"Mod search: q='{q}', mc='{mc_version}', loader='{loader}', source='{source}'")

        def worker():
            try:
                if source == "curseforge":
                    hits = curseforge_manager.search_mods(q, mc_version, loader, limit=15)
                else:
                    hits = mods_manager.search_mods(q, mc_version, loader, limit=15)
                log.info(f"Mod search result: {len(hits)} hits")
                self.after(0, lambda h=hits, s=source: self._show_mods(h, s))
            except Exception as err:
                err_text = str(err)
                log.error(f"Mod search error: {err_text}")
                self.after(0, lambda t=err_text: self.toast(f"Ошибка: {t}", "error"))

        threading.Thread(target=worker, daemon=True).start()

    def _show_mods(self, hits, source="modrinth"):
        for w in self.mods_results.winfo_children():
            w.destroy()
        if not hits:
            ctk.CTkLabel(self.mods_results, text="Ничего не найдено",
                         text_color=COLORS["text_muted"]).pack(pady=10)
            return

        if not hasattr(self, "_mod_icon_cache"):
            self._mod_icon_cache = {}

        for h in hits:
            if source == "curseforge":
                title = h.get("title") or h.get("name") or "?"
                desc = (h.get("description") or h.get("summary") or "")[:90]
                mod_id = h.get("project_id") or h.get("id")
                icon_url = h.get("icon_url") or h.get("iconUrl")
            else:
                title = h.get("title", "?")
                desc = (h.get("description") or "")[:90]
                mod_id = h.get("project_id")
                icon_url = h.get("icon_url")

            card = ctk.CTkFrame(self.mods_results, fg_color=COLORS["card"],
                                corner_radius=4, border_width=1,
                                border_color=COLORS["border"])
            card.pack(fill="x", pady=3)

            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=10, pady=8)

            icon_label = ctk.CTkLabel(
                inner, text="?",
                font=("Segoe UI", 24),
                text_color=COLORS["text_muted"],
                width=48, height=48,
            )
            icon_label.pack(side="left", padx=(0, 12))

            info = ctk.CTkFrame(inner, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True)

            ctk.CTkLabel(info, text=title, anchor="w",
                         font=("Segoe UI", 12, "bold"),
                         text_color=COLORS["text"]).pack(fill="x")
            ctk.CTkLabel(info, text=desc, anchor="w",
                         font=("Segoe UI", 9),
                         text_color=COLORS["text_muted"],
                         wraplength=350, justify="left").pack(fill="x")

            ctk.CTkButton(inner, text="⬇  Установить", width=110, height=32,
                          font=("Segoe UI", 10, "bold"),
                          fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                          text_color="#ffffff", corner_radius=4,
                          command=lambda mid=mod_id, s=source: self.install_mod(mid, s)
                          ).pack(side="right")

            if icon_url:
                self._load_mod_icon(icon_url, icon_label)

    def _load_mod_icon(self, url, label_widget):
        if not HAS_PIL:
            return

        if url in self._mod_icon_cache:
            img = self._mod_icon_cache[url]
            try:
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(48, 48))
                label_widget.configure(image=ctk_img, text="")
                label_widget._icon_image = ctk_img
            except Exception:
                pass
            return

        def worker():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=6) as resp:
                    data = resp.read()
                img = Image.open(BytesIO(data)).convert("RGBA")
                w, h = img.size
                side = min(w, h)
                left = (w - side) // 2
                top = (h - side) // 2
                img = img.crop((left, top, left + side, top + side))
                img = img.resize((48, 48), Image.LANCZOS)

                self._mod_icon_cache[url] = img

                def apply():
                    try:
                        ctk_img = ctk.CTkImage(
                            light_image=img, dark_image=img, size=(48, 48)
                        )
                        label_widget.configure(image=ctk_img, text="")
                        label_widget._icon_image = ctk_img
                    except Exception:
                        pass
                self.after(0, apply)
            except Exception as e:
                log.warning(f"icon load error: {e}")

        threading.Thread(target=worker, daemon=True).start()

    def install_mod(self, project_id, source="modrinth"):
        vt = self.type_var.get().lower()
        if vt == "ванилла":
            self.toast("Моды требуют Forge или Fabric", "error")
            return

        version_raw = self.version_var.get()
        if vt == "forge" and "-" in version_raw:
            mc_version = version_raw.split("-")[0]
        else:
            mc_version = version_raw

        if vt == "forge":
            loader = "forge"
        elif vt == "fabric":
            loader = "fabric"
        else:
            loader = None

        self.toast("Скачивание мода...", "info")

        def worker():
            try:
                if source == "curseforge":
                    path = curseforge_manager.install_mod(
                        project_id, self.get_mc_dir(),
                        mc_version, loader)
                else:
                    path = mods_manager.install_mod(
                        project_id, self.get_mc_dir(),
                        self.version_var.get(), loader)
                self.after(0, lambda p=path: self.toast(
                    f"Установлен: {os.path.basename(p)}", "success"))
                self.after(0, self.refresh_mods)
            except Exception as err:
                err_text = str(err)
                log.error(f"Mod install error: {err_text}")
                self.after(0, lambda t=err_text: self.toast(f"Ошибка: {t}", "error"))

        threading.Thread(target=worker, daemon=True).start()

    def refresh_mods(self):
        for w in self.mods_installed.winfo_children():
            w.destroy()
        mods = mods_manager.list_installed_mods(self.get_mc_dir())
        if not mods:
            ctk.CTkLabel(self.mods_installed, text="Модов нет",
                         text_color=COLORS["text_muted"]).pack(pady=10)
            return
        for m in mods:
            row = ctk.CTkFrame(self.mods_installed, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text="📦", font=("Segoe UI", 14),
                         text_color=COLORS["text_muted"]).pack(side="left", padx=(0, 6))
            ctk.CTkLabel(row, text=m, anchor="w", font=("Segoe UI", 11),
                         text_color=COLORS["text"]).pack(side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="📂", width=34, height=26,
                          font=("Segoe UI", 12),
                          fg_color=COLORS["card_hover"], hover_color=COLORS["accent"],
                          text_color=COLORS["text"], corner_radius=4,
                          command=self.open_mods_folder).pack(side="left", padx=(0, 4))
            ctk.CTkButton(row, text="X", width=34, height=26,
                          fg_color=COLORS["card_hover"], hover_color=COLORS["danger"],
                          text_color=COLORS["text"], corner_radius=4,
                          command=lambda f=m: self.delete_mod(f)).pack(side="left")

    def open_mods_folder(self):
        try:
            mods_dir = os.path.join(self.get_mc_dir(), "mods")
            os.makedirs(mods_dir, exist_ok=True)
            os.startfile(mods_dir)
        except Exception as e:
            self.toast(f"Не удалось открыть: {e}", "error")

    def delete_mod(self, filename):
        if mods_manager.delete_mod(self.get_mc_dir(), filename):
            self.refresh_mods()

    # ---------------- ПРОФИЛИ ----------------
    def build_profiles_page(self):
        p = self.pages["profiles"]
        c = self.card(p)
        c.pack(fill="both", expand=True)
        inner = ctk.CTkFrame(c, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=18, pady=16)

        ctk.CTkLabel(inner, text="ПРОФИЛИ",
                     font=("Segoe UI", 13, "bold"),
                     text_color=COLORS["text"], anchor="w").pack(fill="x", pady=(0, 8))

        add = ctk.CTkFrame(inner, fg_color="transparent")
        add.pack(fill="x", pady=(0, 10))
        self.new_profile_entry = ctk.CTkEntry(
            add, height=38, font=("Segoe UI", 12),
            fg_color=COLORS["bg2"], border_color=COLORS["border"],
            corner_radius=4, text_color=COLORS["text"],
            placeholder_text="Ник...")
        self.new_profile_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(add, text="Добавить", width=120, height=38,
                      fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                      text_color="#ffffff", corner_radius=4,
                      command=self.add_profile).pack(side="left", padx=(8, 0))

        self.profiles_scroll = ctk.CTkScrollableFrame(
            inner, fg_color=COLORS["bg2"], corner_radius=4,
            scrollbar_button_color=COLORS["accent"])
        self.profiles_scroll.pack(fill="both", expand=True)

    def refresh_profiles(self):
        for w in self.profiles_scroll.winfo_children():
            w.destroy()
        profiles = self.settings.get("profiles", [])
        current = self.nickname_entry.get().strip()
        if not profiles:
            ctk.CTkLabel(self.profiles_scroll, text="Профилей нет",
                         text_color=COLORS["text_muted"]).pack(pady=10)
            return
        for nick in profiles:
            row = ctk.CTkFrame(self.profiles_scroll, fg_color="transparent")
            row.pack(fill="x", pady=3)
            is_active = (nick == current)
            ctk.CTkLabel(row, text=("*  " if is_active else "   ") + nick,
                         anchor="w", font=("Segoe UI", 12),
                         text_color=COLORS["accent"] if is_active else COLORS["text"]
                         ).pack(side="left", fill="x", expand=True)
            ctk.CTkButton(row, text="Выбрать", width=90, height=30,
                          fg_color=COLORS["card_hover"], hover_color=COLORS["accent"],
                          text_color=COLORS["text"], corner_radius=4,
                          command=lambda n=nick: self.select_profile(n)).pack(side="left", padx=4)
            ctk.CTkButton(row, text="X", width=34, height=30,
                          fg_color=COLORS["card_hover"], hover_color=COLORS["danger"],
                          text_color=COLORS["text"], corner_radius=4,
                          command=lambda n=nick: self.delete_profile(n)).pack(side="left")

    def add_profile(self):
        nick = self.new_profile_entry.get().strip()
        if not nick:
            return
        profiles = self.settings.get("profiles", [])
        if nick in profiles:
            self.toast("Такой профиль уже есть", "error")
            return
        profiles.append(nick)
        self.settings["profiles"] = profiles
        if ach_mod.check_and_unlock(self.settings, "profile_made"):
            self.toast("Открыто: Создал первый профиль", "success")
        st_mod.save_settings(self.settings)
        self.new_profile_entry.delete(0, "end")
        self.refresh_profiles()
        self.refresh_achievements()

    def select_profile(self, nick):
        self.nickname_entry.delete(0, "end")
        self.nickname_entry.insert(0, nick)
        self.settings["nickname"] = nick
        st_mod.save_settings(self.settings)
        self.refresh_profiles()
        self.load_avatar_async()

    def delete_profile(self, nick):
        if not messagebox.askyesno("Удаление", f"Удалить профиль {nick}?"):
            return
        profiles = self.settings.get("profiles", [])
        if nick in profiles:
            profiles.remove(nick)
            self.settings["profiles"] = profiles
            st_mod.save_settings(self.settings)
            self.refresh_profiles()

    # ---------------- БЭКАПЫ ----------------
    def build_backups_page(self):
        p = self.pages["backups"]
        c = self.card(p)
        c.pack(fill="both", expand=True)
        inner = ctk.CTkFrame(c, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=18, pady=16)

        h = ctk.CTkFrame(inner, fg_color="transparent")
        h.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(h, text="БЭКАПЫ МИРОВ",
                     font=("Segoe UI", 13, "bold"),
                     text_color=COLORS["text"]).pack(side="left")
        ctk.CTkButton(h, text="Сделать бэкап", width=160, height=32,
                      fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                      text_color="#ffffff", corner_radius=4,
                      command=self.make_backup).pack(side="right")

        self.backups_scroll = ctk.CTkScrollableFrame(
            inner, fg_color=COLORS["bg2"], corner_radius=4,
            scrollbar_button_color=COLORS["accent"])
        self.backups_scroll.pack(fill="both", expand=True)

    def make_backup(self):
        try:
            path = backups.backup_saves(self.get_mc_dir())
            self.settings["backups_made"] = self.settings.get("backups_made", 0) + 1
            if ach_mod.check_and_unlock(self.settings, "backup_made"):
                self.toast("Открыто: Первый бэкап", "success")
            st_mod.save_settings(self.settings)
            self.toast(f"Бэкап создан: {os.path.basename(path)}", "success")
            self.refresh_backups()
            self.refresh_achievements()
        except Exception as err:
            self.toast(f"Ошибка: {str(err)}", "error")

    def refresh_backups(self):
        for w in self.backups_scroll.winfo_children():
            w.destroy()
        items = backups.list_backups(self.get_mc_dir())
        if not items:
            ctk.CTkLabel(self.backups_scroll, text="Бэкапов пока нет",
                         text_color=COLORS["text_muted"]).pack(pady=10)
            return
        for f in items:
            row = ctk.CTkFrame(self.backups_scroll, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=f, anchor="w", font=("Segoe UI", 11),
                         text_color=COLORS["text"]).pack(side="left", fill="x", expand=True)

    # ---------------- ДОСТИЖЕНИЯ ----------------
    def build_achievements_page(self):
        p = self.pages["achievements"]
        c = self.card(p)
        c.pack(fill="both", expand=True)
        inner = ctk.CTkFrame(c, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=18, pady=16)
        ctk.CTkLabel(inner, text="ДОСТИЖЕНИЯ",
                     font=("Segoe UI", 13, "bold"),
                     text_color=COLORS["text"], anchor="w").pack(fill="x", pady=(0, 10))
        self.achievements_scroll = ctk.CTkScrollableFrame(
            inner, fg_color=COLORS["bg2"], corner_radius=4,
            scrollbar_button_color=COLORS["accent"])
        self.achievements_scroll.pack(fill="both", expand=True)

    def refresh_achievements(self):
        for w in self.achievements_scroll.winfo_children():
            w.destroy()
        items = ach_mod.list_achievements(self.settings)
        for key, icon, title, unlocked in items:
            row = ctk.CTkFrame(self.achievements_scroll, fg_color="transparent")
            row.pack(fill="x", pady=3)
            color = COLORS["accent"] if unlocked else COLORS["text_muted"]
            ctk.CTkLabel(row, text=f"{icon}  {title}", anchor="w",
                         font=("Segoe UI", 12, "bold" if unlocked else "normal"),
                         text_color=color).pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(row, text="+" if unlocked else "-",
                         font=("Segoe UI", 12),
                         text_color=color).pack(side="right")

    # ---------------- ЛОГИ ----------------
    def build_logs_page(self):
        p = self.pages["logs"]
        c = self.card(p)
        c.pack(fill="both", expand=True)
        inner = ctk.CTkFrame(c, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=18, pady=16)

        h = ctk.CTkFrame(inner, fg_color="transparent")
        h.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(h, text="ЛОГ ЛАУНЧЕРА",
                     font=("Segoe UI", 13, "bold"),
                     text_color=COLORS["text"]).pack(side="left")

        ctk.CTkButton(h, text="🔄 Обновить", width=110, height=30,
                      font=("Segoe UI", 10),
                      fg_color=COLORS["card_hover"], hover_color=COLORS["accent"],
                      text_color=COLORS["text"], corner_radius=4,
                      command=self.refresh_logs).pack(side="right", padx=(4, 0))

        ctk.CTkButton(h, text="🗑 Очистить", width=110, height=30,
                      font=("Segoe UI", 10),
                      fg_color=COLORS["card_hover"], hover_color=COLORS["danger"],
                      text_color=COLORS["text"], corner_radius=4,
                      command=self.clear_logs).pack(side="right", padx=(4, 0))

        ctk.CTkButton(h, text="📂 Открыть файл", width=130, height=30,
                      font=("Segoe UI", 10),
                      fg_color=COLORS["card_hover"], hover_color=COLORS["accent"],
                      text_color=COLORS["text"], corner_radius=4,
                      command=self.open_logs).pack(side="right")

        filters = ctk.CTkFrame(inner, fg_color="transparent")
        filters.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(filters, text="Фильтр:",
                     font=("Segoe UI", 10),
                     text_color=COLORS["text_muted"]).pack(side="left", padx=(0, 6))

        self.log_filter_var = ctk.StringVar(value="ALL")
        self.log_filter_seg = ctk.CTkSegmentedButton(
            filters,
            values=["ALL", "INFO", "WARNING", "ERROR"],
            variable=self.log_filter_var,
            height=28,
            font=("Segoe UI", 10, "bold"),
            fg_color=COLORS["bg2"],
            selected_color=COLORS["accent"],
            unselected_color=COLORS["bg2"],
            text_color=COLORS["text"],
            corner_radius=4,
            command=lambda _: self.refresh_logs(),
        )
        self.log_filter_seg.pack(side="left")

        ctk.CTkButton(filters, text="🔄 Авто", width=80, height=28,
                      font=("Segoe UI", 10),
                      fg_color=COLORS["card_hover"], hover_color=COLORS["accent"],
                      text_color=COLORS["text"], corner_radius=4,
                      command=self.toggle_log_autorefresh).pack(side="right")

        self.log_text = ctk.CTkTextbox(
            inner,
            font=("Consolas", 10),
            fg_color=COLORS["bg2"],
            text_color=COLORS["text"],
            wrap="word",
            corner_radius=4,
        )
        self.log_text.pack(fill="both", expand=True)

        self._log_autorefresh = False
        self.refresh_logs()

    def refresh_logs(self):
        try:
            log_path = os.path.abspath("slaylauncher.log")
            if not os.path.isfile(log_path):
                content = "(лог пуст или ещё не создан)"
            else:
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                lines = lines[-500:]

                flt = self.log_filter_var.get()
                if flt != "ALL":
                    lines = [ln for ln in lines if flt in ln]

                content = "".join(lines) if lines else "(нет записей с таким фильтром)"

            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", "end")
            self.log_text.insert("1.0", content)
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        except Exception as e:
            try:
                self.log_text.configure(state="normal")
                self.log_text.delete("1.0", "end")
                self.log_text.insert("1.0", f"Ошибка чтения лога: {e}")
                self.log_text.configure(state="disabled")
            except Exception:
                pass

        if getattr(self, "_log_autorefresh", False):
            self.after(2000, self.refresh_logs)

    def toggle_log_autorefresh(self):
        self._log_autorefresh = not getattr(self, "_log_autorefresh", False)
        if self._log_autorefresh:
            self.toast("Авто-обновление лога включено", "info")
            self.refresh_logs()
        else:
            self.toast("Авто-обновление выключено", "info")

    def clear_logs(self):
        if not messagebox.askyesno("Очистка", "Очистить файл лога?"):
            return
        try:
            log_path = os.path.abspath("slaylauncher.log")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("")
            self.refresh_logs()
            self.toast("Лог очищен", "success")
        except Exception as e:
            self.toast(f"Ошибка: {e}", "error")

    # ---------------- НАСТРОЙКИ ----------------
    def build_settings_page(self):
        p = self.pages["settings"]
        scroll = ctk.CTkScrollableFrame(
            p, fg_color=COLORS["bg"], corner_radius=0,
            scrollbar_button_color=COLORS["accent"])
        scroll.pack(fill="both", expand=True)

        cols = ctk.CTkFrame(scroll, fg_color="transparent")
        cols.pack(fill="x")
        left = ctk.CTkFrame(cols, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        right = ctk.CTkFrame(cols, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True, padx=(10, 0))

        c1 = self.card(left)
        c1.pack(fill="x", pady=(0, 12))
        i1 = ctk.CTkFrame(c1, fg_color="transparent")
        i1.pack(fill="x", padx=18, pady=16)
        ctk.CTkLabel(i1, text="ПАПКА УСТАНОВКИ", font=("Segoe UI", 10, "bold"),
                     text_color=COLORS["text_muted"], anchor="w").pack(fill="x", pady=(0, 4))
        r = ctk.CTkFrame(i1, fg_color="transparent")
        r.pack(fill="x")
        self.path_entry = ctk.CTkEntry(r, height=36, font=("Segoe UI", 11),
                                       fg_color=COLORS["bg2"], border_color=COLORS["border"],
                                       corner_radius=4, text_color=COLORS["text"])
        self.path_entry.insert(0, self.settings["mc_dir"])
        self.path_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(r, text="ОБЗОР", width=80, height=36,
                      fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                      text_color="#ffffff", corner_radius=4,
                      command=self.browse_folder).pack(side="left", padx=(6, 0))

        c2 = self.card(left)
        c2.pack(fill="x", pady=(0, 12))
        i2 = ctk.CTkFrame(c2, fg_color="transparent")
        i2.pack(fill="x", padx=18, pady=16)
        ctk.CTkLabel(i2, text="ОЗУ (МБ)", font=("Segoe UI", 10, "bold"),
                     text_color=COLORS["text_muted"], anchor="w").pack(fill="x", pady=(0, 4))
        self.ram_entry = ctk.CTkEntry(i2, height=36, font=("Segoe UI", 13),
                                      fg_color=COLORS["bg2"], border_color=COLORS["border"],
                                      corner_radius=4, text_color=COLORS["text"])
        self.ram_entry.insert(0, str(self.settings["ram"]))
        self.ram_entry.pack(fill="x")

        c3 = self.card(left)
        c3.pack(fill="x", pady=(0, 12))
        i3 = ctk.CTkFrame(c3, fg_color="transparent")
        i3.pack(fill="x", padx=18, pady=16)
        ctk.CTkLabel(i3, text="JAVA (javaw.exe)", font=("Segoe UI", 10, "bold"),
                     text_color=COLORS["text_muted"], anchor="w").pack(fill="x", pady=(0, 4))
        jr = ctk.CTkFrame(i3, fg_color="transparent")
        jr.pack(fill="x")
        self.java_entry = ctk.CTkEntry(jr, height=36, font=("Segoe UI", 10),
                                       fg_color=COLORS["bg2"], border_color=COLORS["border"],
                                       corner_radius=4, text_color=COLORS["text"],
                                       placeholder_text="Автоопределение...")
        self.java_entry.insert(0, self.settings.get("java_path", ""))
        self.java_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(jr, text="АВТО", width=65, height=36,
                      fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                      text_color="#ffffff", corner_radius=4,
                      command=self.auto_detect_java).pack(side="left", padx=(6, 0))
        ctk.CTkButton(jr, text="...", width=38, height=36,
                      fg_color=COLORS["card_hover"], hover_color=COLORS["accent"],
                      text_color=COLORS["text"], corner_radius=4,
                      command=self.browse_java).pack(side="left", padx=(4, 0))
        ctk.CTkButton(i3, text="Скачать Java для выбранной версии", height=32,
                      font=("Segoe UI", 10),
                      fg_color="transparent", hover_color=COLORS["card_hover"],
                      text_color=COLORS["text_muted"], corner_radius=4,
                      border_width=1, border_color=COLORS["border"],
                      command=self.download_java).pack(fill="x", pady=(8, 0))

        c4 = self.card(left)
        c4.pack(fill="x", pady=(0, 12))
        i4 = ctk.CTkFrame(c4, fg_color="transparent")
        i4.pack(fill="x", padx=18, pady=16)
        ctk.CTkLabel(i4, text="АРГУМЕНТЫ JVM", font=("Segoe UI", 10, "bold"),
                     text_color=COLORS["text_muted"], anchor="w").pack(fill="x", pady=(0, 4))
        self.jvm_entry = ctk.CTkEntry(i4, height=36, font=("Segoe UI", 10),
                                      fg_color=COLORS["bg2"], border_color=COLORS["border"],
                                      corner_radius=4, text_color=COLORS["text"],
                                      placeholder_text="-XX:+UseG1GC")
        self.jvm_entry.insert(0, self.settings.get("jvm_args", ""))
        self.jvm_entry.pack(fill="x")

        c5 = self.card(right)
        c5.pack(fill="x", pady=(0, 12))
        i5 = ctk.CTkFrame(c5, fg_color="transparent")
        i5.pack(fill="x", padx=18, pady=16)

        ctk.CTkLabel(i5, text="ЦВЕТОВАЯ ТЕМА", font=("Segoe UI", 10, "bold"),
                     text_color=COLORS["text_muted"], anchor="w").pack(fill="x", pady=(0, 8))

        theme_keys = list(THEMES.keys())
        theme_names = [THEMES[k]["name"] for k in theme_keys]
        current_theme = self.settings.get("theme_name", "vaporwave")
        try:
            default_idx = theme_keys.index(current_theme)
        except ValueError:
            default_idx = 0

        self.theme_var = ctk.StringVar(value=theme_names[default_idx])
        self.theme_seg2 = ctk.CTkSegmentedButton(
            i5,
            values=theme_names,
            variable=self.theme_var,
            height=32,
            font=("Segoe UI", 10, "bold"),
            fg_color=COLORS["bg2"],
            selected_color=COLORS["accent"],
            unselected_color=COLORS["bg2"],
            text_color=COLORS["text"],
            corner_radius=4,
            command=self._on_theme_change,
        )
        self.theme_seg2.pack(fill="x")

        ctk.CTkLabel(i5, text="АКЦЕНТНЫЙ ЦВЕТ", font=("Segoe UI", 10, "bold"),
                     text_color=COLORS["text_muted"], anchor="w").pack(fill="x", pady=(14, 8))
        ar = ctk.CTkFrame(i5, fg_color="transparent")
        ar.pack(fill="x")
        for key, hexc in ACCENTS.items():
            ctk.CTkButton(ar, text="", width=44, height=32,
                          fg_color=hexc, hover_color=hexc, corner_radius=4,
                          command=lambda k=key: self.set_accent(k)).pack(side="left", padx=3)

        self.splash_var = ctk.BooleanVar(value=self.settings.get("splash_enabled", True))
        ctk.CTkCheckBox(i5, text="Показывать сплэш при запуске",
                        variable=self.splash_var,
                        font=("Segoe UI", 11), text_color=COLORS["text"],
                        fg_color=COLORS["accent"], border_color=COLORS["border"],
                        checkmark_color="#fff", corner_radius=4,
                        command=self._toggle_splash).pack(anchor="w", pady=(12, 0))

        c6 = self.card(right)
        c6.pack(fill="x", pady=(0, 12))
        i6 = ctk.CTkFrame(c6, fg_color="transparent")
        i6.pack(fill="x", padx=18, pady=16)
        ctk.CTkLabel(i6, text="СИСТЕМА", font=("Segoe UI", 10, "bold"),
                     text_color=COLORS["text_muted"], anchor="w").pack(fill="x", pady=(0, 8))
        ctk.CTkCheckBox(i6, text="Звуки лаунчера", variable=self.sounds_on,
                        font=("Segoe UI", 12), text_color=COLORS["text"],
                        fg_color=COLORS["accent"], border_color=COLORS["border"],
                        checkmark_color="#fff", corner_radius=4,
                        command=self.toggle_sounds).pack(anchor="w", pady=2)

        self.rpc_var = ctk.BooleanVar(value=self.settings.get("discord_rpc", False))
        ctk.CTkCheckBox(i6, text="Discord Rich Presence", variable=self.rpc_var,
                        font=("Segoe UI", 12), text_color=COLORS["text"],
                        fg_color=COLORS["accent"], border_color=COLORS["border"],
                        checkmark_color="#fff", corner_radius=4,
                        command=self.toggle_rpc).pack(anchor="w", pady=2)

        self.tray_var = ctk.BooleanVar(value=self.settings.get("tray_mode", False))
        ctk.CTkCheckBox(i6, text="Сворачивать в трей", variable=self.tray_var,
                        font=("Segoe UI", 12), text_color=COLORS["text"],
                        fg_color=COLORS["accent"], border_color=COLORS["border"],
                        checkmark_color="#fff", corner_radius=4,
                        command=self.toggle_tray).pack(anchor="w", pady=2)

        self.autostart_var = ctk.BooleanVar(value=self.settings.get("autostart", False))
        ctk.CTkCheckBox(i6, text="Запускать с Windows", variable=self.autostart_var,
                        font=("Segoe UI", 12), text_color=COLORS["text"],
                        fg_color=COLORS["accent"], border_color=COLORS["border"],
                        checkmark_color="#fff", corner_radius=4,
                        command=self.toggle_autostart).pack(anchor="w", pady=2)

        self.flash_var = ctk.BooleanVar(value=self.settings.get("flash_on_launch", True))
        ctk.CTkCheckBox(i6, text="Вспышка при запуске игры",
                        variable=self.flash_var,
                        font=("Segoe UI", 12), text_color=COLORS["text"],
                        fg_color=COLORS["accent"], border_color=COLORS["border"],
                        checkmark_color="#fff", corner_radius=4,
                        command=self._toggle_flash).pack(anchor="w", pady=2)

        self.crash_check_var = ctk.BooleanVar(value=self.settings.get("auto_crash_check", True))
        ctk.CTkCheckBox(i6, text="Автоанализ крашей",
                        variable=self.crash_check_var,
                        font=("Segoe UI", 12), text_color=COLORS["text"],
                        fg_color=COLORS["accent"], border_color=COLORS["border"],
                        checkmark_color="#fff", corner_radius=4,
                        command=self._toggle_crash_check).pack(anchor="w", pady=2)

        self.updates_check_var = ctk.BooleanVar(
            value=self.settings.get("check_updates_on_start", True)
        )
        ctk.CTkCheckBox(i6, text="Проверять обновления при запуске",
                        variable=self.updates_check_var,
                        font=("Segoe UI", 12), text_color=COLORS["text"],
                        fg_color=COLORS["accent"], border_color=COLORS["border"],
                        checkmark_color="#fff", corner_radius=4,
                        command=self._toggle_update_check).pack(anchor="w", pady=2)

        c7 = self.card(right)
        c7.pack(fill="x", pady=(0, 12))
        i7 = ctk.CTkFrame(c7, fg_color="transparent")
        i7.pack(fill="x", padx=18, pady=16)
        ctk.CTkLabel(i7, text="ФИЛЬТРЫ ВАНИЛЛЫ", font=("Segoe UI", 10, "bold"),
                     text_color=COLORS["text_muted"], anchor="w").pack(fill="x", pady=(0, 6))
        for text, var in [("Релизы", self.show_releases), ("Снапшоты", self.show_snapshots),
                          ("Старые беты", self.show_old_beta), ("Старые альфы", self.show_old_alpha)]:
            ctk.CTkCheckBox(i7, text=text, variable=var, font=("Segoe UI", 11),
                            text_color=COLORS["text"],
                            fg_color=COLORS["accent"], border_color=COLORS["border"],
                            checkmark_color="#fff", corner_radius=4,
                            command=self.refresh_versions).pack(anchor="w", pady=1)
        ctk.CTkCheckBox(i7, text="Forge: только последняя сборка",
                        variable=self.forge_only_latest, font=("Segoe UI", 11),
                        text_color=COLORS["text"],
                        fg_color=COLORS["accent"], border_color=COLORS["border"],
                        checkmark_color="#fff", corner_radius=4,
                        command=self.refresh_versions).pack(anchor="w", pady=(6, 0))

        c8 = self.card(right)
        c8.pack(fill="x", pady=(0, 12))
        i8 = ctk.CTkFrame(c8, fg_color="transparent")
        i8.pack(fill="x", padx=18, pady=16)
        ctk.CTkLabel(i8, text="ОБСЛУЖИВАНИЕ", font=("Segoe UI", 10, "bold"),
                     text_color=COLORS["text_muted"], anchor="w").pack(fill="x", pady=(0, 8))
        ctk.CTkButton(i8, text="🔄  Проверить обновления лаунчера",
                      height=34,
                      fg_color=COLORS["accent"],
                      hover_color=COLORS["accent_hover"],
                      text_color="#ffffff", corner_radius=4,
                      command=lambda: self.check_updates(silent=False)
                      ).pack(fill="x", pady=2)
        ctk.CTkButton(i8, text="Проверить систему (RAM, Java, GPU)",
                      height=34,
                      fg_color=COLORS["accent"],
                      hover_color=COLORS["accent_hover"],
                      text_color="#ffffff", corner_radius=4,
                      command=self.run_system_check).pack(fill="x", pady=2)
        ctk.CTkButton(i8, text="Проверить файлы", height=34,
                      fg_color=COLORS["card_hover"], hover_color=COLORS["accent"],
                      text_color=COLORS["text"], corner_radius=4,
                      command=self.verify_integrity).pack(fill="x", pady=2)
        ctk.CTkButton(i8, text="Открыть логи", height=34,
                      fg_color=COLORS["card_hover"], hover_color=COLORS["accent"],
                      text_color=COLORS["text"], corner_radius=4,
                      command=self.open_logs).pack(fill="x", pady=2)

        ctk.CTkButton(scroll, text="СОХРАНИТЬ НАСТРОЙКИ", height=46,
                      font=("Segoe UI", 13, "bold"),
                      fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
                      text_color="#ffffff", corner_radius=4,
                      command=self.save_all_settings).pack(fill="x", pady=(4, 10))

    # ---------------- ЛОГИКА ----------------
    def get_mc_dir(self):
        return self.path_entry.get().strip() or os.path.expanduser("~/.slayminecraft")

    def on_type_change(self):
        self.refresh_versions()
        self.update_main_button()

    def refresh_versions(self):
        vt = self.type_var.get()
        mc_dir = self.get_mc_dir()
        versions = []

        if vt == "Ванилла":
            try:
                all_v = minecraft_launcher_lib.utils.get_available_versions(mc_dir)
                filt = []
                for v in all_v:
                    t = v["type"]
                    if t == "release" and self.show_releases.get():
                        filt.append(v)
                    elif t == "snapshot" and self.show_snapshots.get():
                        filt.append(v)
                    elif t == "old_beta" and self.show_old_beta.get():
                        filt.append(v)
                    elif t == "old_alpha" and self.show_old_alpha.get():
                        filt.append(v)
                filt.sort(key=lambda x: parse_vanilla(x["id"]), reverse=True)
                versions = [v["id"] for v in filt]
            except Exception as e:
                log.error(f"Vanilla: {e}")
                versions = ["1.20.1", "1.7.10"]

        elif vt == "Forge":
            try:
                try:
                    all_forge = minecraft_launcher_lib.forge.list_forge_versions()
                except AttributeError:
                    all_forge = minecraft_launcher_lib.forge.get_forge_versions()
                all_forge = sorted(all_forge, key=parse_forge, reverse=True)
                if self.forge_only_latest.get():
                    seen, filt = set(), []
                    for v in all_forge:
                        mc = v.split("-")[0]
                        if mc not in seen:
                            seen.add(mc)
                            filt.append(v)
                    versions = filt
                else:
                    versions = all_forge
            except Exception as e:
                log.error(f"Forge: {e}")
                versions = []

        elif vt == "Fabric":
            try:
                all_v = minecraft_launcher_lib.utils.get_available_versions(mc_dir)
                rel = [v for v in all_v if v["type"] == "release"]
                rel.sort(key=lambda x: parse_vanilla(x["id"]), reverse=True)
                versions = [v["id"] for v in rel]
            except Exception as e:
                log.error(f"Fabric: {e}")
                versions = []

        if not versions:
            versions = ["—"]

        favs = self.settings.get("favorites", [])
        if favs:
            fav_set = set(favs)
            versions = ([v for v in versions if v in fav_set]
                        + [v for v in versions if v not in fav_set])

        self.version_dropdown.set_values(versions)
        self._update_fav_star()
        self.update_main_button()

    def resolve_launch_id(self, vt, version, mc_dir):
        vdir = os.path.join(mc_dir, "versions")
        if not os.path.isdir(vdir):
            return version

        if vt == "Fabric":
            for d in os.listdir(vdir):
                if d.startswith("fabric-loader") and d.endswith(f"-{version}"):
                    return d

        elif vt == "Forge":
            if "-" in version:
                mc, forge = version.split("-", 1)
                for candidate in [f"{mc}-forge-{forge}", version]:
                    if os.path.isdir(os.path.join(vdir, candidate)):
                        return candidate
            else:
                for d in os.listdir(vdir):
                    if "forge" in d.lower() and version in d:
                        return d

        return version

    def is_version_installed(self):
        vt = self.type_var.get()
        v = self.version_var.get()
        mc_dir = self.get_mc_dir()
        vdir = os.path.join(mc_dir, "versions")
        if not v or v == "—" or not os.path.isdir(vdir):
            return False

        if vt == "Fabric":
            for d in os.listdir(vdir):
                if d.startswith("fabric-loader") and d.endswith(f"-{v}"):
                    sub = os.path.join(vdir, d)
                    if os.path.isdir(sub) and any(f.endswith(".json") for f in os.listdir(sub)):
                        return True
            return False

        if vt == "Forge":
            if "-" in v:
                mc, forge = v.split("-", 1)
                for candidate in [f"{mc}-forge-{forge}", v]:
                    vd = os.path.join(vdir, candidate)
                    if os.path.isdir(vd) and any(f.endswith(".json") for f in os.listdir(vd)):
                        return True
                return False
            for d in os.listdir(vdir):
                if "forge" in d.lower() and v in d:
                    vd = os.path.join(vdir, d)
                    if any(f.endswith(".json") for f in os.listdir(vd)):
                        return True
            return False

        vd = os.path.join(vdir, v)
        return os.path.isdir(vd) and any(f.endswith(".json") for f in os.listdir(vd))

    def update_main_button(self):
        v = self.version_var.get()
        if not v or v == "—":
            self.main_btn.configure(text="НЕТ ВЕРСИЙ", fg_color=COLORS["card"], state="disabled")
            return
        if self.is_version_installed():
            self.main_btn.configure(text="ИГРАТЬ", fg_color=COLORS["green"],
                                    hover_color="#3ee6b4", state="normal")
            try:
                self.loader.set_text("Версия установлена")
                self.loader.spinner.configure(text="●", text_color=COLORS["green"])
            except Exception:
                pass
        else:
            self.main_btn.configure(text="УСТАНОВИТЬ", fg_color=COLORS["accent"],
                                    hover_color=COLORS["accent_hover"], state="normal")
            try:
                self.loader.set_text("Требуется установка")
                self.loader.spinner.configure(text="●", text_color=COLORS["text_muted"])
            except Exception:
                pass

    def on_main_btn_click(self):
        if self.is_version_installed():
            self.launch_thread()
        else:
            self.install_thread()

    def update_quote(self):
        try:
            self.quote_label.configure(text='" ' + random.choice(QUOTES) + ' "')
        except Exception:
            pass

    def toast(self, text, kind="info"):
        try:
            Toast(self, text, kind)
        except Exception:
            pass
        try:
            snd_mod.play("success" if kind == "success" else "error" if kind == "error" else "click",
                         self.sounds_on.get())
        except Exception:
            pass

    def install_version(self):
        vt = self.type_var.get()
        v = self.version_var.get()
        mc_dir = self.get_mc_dir()
        state = {"max": 100, "last_pct": -1, "last_status": ""}

        def set_status(t):
            if t != state["last_status"]:
                state["last_status"] = t
                try:
                    self.loader.set_text(t)
                except Exception:
                    pass
                self.update_idletasks()

        def set_max(m):
            state["max"] = max(m, 1)

        def set_progress(x):
            pct = int(x / state["max"] * 100)
            if pct != state["last_pct"]:
                state["last_pct"] = pct
                self.progress.set(pct / 100)
                self.update_idletasks()

        cb = {"setStatus": set_status, "setProgress": set_progress, "setMax": set_max}

        try:
            self.main_btn.configure(state="disabled", text="ЗАГРУЗКА...")
            self.loader.start(f"Установка {vt}: {v}...")
            self.loader.set_color(COLORS["accent"])
            log.info(f"Install {vt} {v}")

            if vt == "Ванилла":
                minecraft_launcher_lib.install.install_minecraft_version(v, mc_dir, callback=cb)
            elif vt == "Forge":
                minecraft_launcher_lib.forge.install_forge_version(v, mc_dir, callback=cb)
            elif vt == "Fabric":
                minecraft_launcher_lib.fabric.install_fabric(v, mc_dir, callback=cb)

            self.progress.set(1.0)
            self.toast(f"Установлено: {v}", "success")

            try:
                installed_count = len(os.listdir(os.path.join(mc_dir, "versions")))
                if installed_count >= 10 and ach_mod.check_and_unlock(self.settings, "install_10"):
                    self.toast("Открыто: Установил 10 версий", "success")
            except Exception:
                pass

            st_mod.save_settings(self.settings)
            self.refresh_installed()
            self.refresh_achievements()
        except Exception as err:
            err_text = str(err)
            self.toast(f"Ошибка: {err_text}", "error")
            log.error(f"Install error: {err_text}")
        finally:
            self.loader.stop("Готово")
            self.loader.spinner.configure(text="●", text_color=COLORS["green"])
            self.update_main_button()

    def launch_game(self):
        vt = self.type_var.get()
        v = self.version_var.get()
        mc_dir = self.get_mc_dir()
        nick = self.nickname_entry.get().strip() or "Slayer"

        try:
            ram = int(self.ram_entry.get())
        except ValueError:
            ram = 4096

        self.settings.update({
            "nickname": nick, "ram": ram, "version": v, "version_type": vt,
            "mc_dir": mc_dir,
            "show_releases": self.show_releases.get(),
            "show_snapshots": self.show_snapshots.get(),
            "show_old_beta": self.show_old_beta.get(),
            "show_old_alpha": self.show_old_alpha.get(),
            "forge_only_latest": self.forge_only_latest.get(),
            "java_path": self.java_entry.get().strip(),
            "jvm_args": self.jvm_entry.get().strip(),
        })
        self.settings["launches"] = self.settings.get("launches", 0) + 1
        stats_mod.inc_launch(self.settings, v)

        if self.settings["launches"] >= 100 and ach_mod.check_and_unlock(self.settings, "launch_100"):
            self.toast("Открыто: 100 запусков!", "success")

        st_mod.save_settings(self.settings)

        java_path = self.java_entry.get().strip()
        if not java_path or not os.path.isfile(java_path):
            per_ver = self.settings.get("java_per_version", {})
            java_path = per_ver.get(v, "")
            if not java_path:
                needed = java_manager.java_major_for_mc(v)
                installed = java_manager.list_installed_java()
                for key, path in installed.items():
                    if f"jdk-{needed}-" in key or key.startswith(f"{needed}."):
                        java_path = path
                        break
                if not java_path:
                    sys_paths = java_manager.detect_system_java()
                    if sys_paths:
                        java_path = sys_paths[-1]

        launch_id = self.resolve_launch_id(vt, v, mc_dir)
        offline_uuid = str(uuid.uuid4()).replace("-", "")
        jvm_args = [f"-Xmx{ram}M", f"-Xms{ram // 2}M"]
        extra = self.jvm_entry.get().strip()
        if extra:
            jvm_args += extra.split()

        options = {
            "username": nick, "uuid": offline_uuid, "token": "",
            "jvmArguments": jvm_args,
            "launcherName": APP_NAME, "launcherVersion": VERSION,
        }
        if java_path and os.path.isfile(java_path):
            options["executablePath"] = java_path

        try:
            saves = os.path.join(mc_dir, "saves")
            if os.path.isdir(saves):
                backups.backup_saves(mc_dir)
        except Exception:
            pass

        try:
            cmd = minecraft_launcher_lib.command.get_minecraft_command(launch_id, mc_dir, options)
            proc = subprocess.Popen(cmd, cwd=mc_dir)
            stats_mod.start_session(v)

            self.flash_animation()

            start_time = time.time()
            threading.Thread(
                target=self.watch_for_crash,
                args=(start_time, v),
                daemon=True,
            ).start()

            try:
                self.loader.spinner.configure(text=">", text_color=COLORS["accent"])
                self.loader.set_text(f"Запуск {v}...")
            except Exception:
                pass

            def mark_in_game():
                try:
                    self.loader.spinner.configure(text="●", text_color=COLORS["green"])
                    self.loader.set_text(f"В игре: {v}")
                except Exception:
                    pass
            self.after(15000, mark_in_game)

            if self.rpc.connected:
                try:
                    self.rpc.update(
                        details=f"Играет в Minecraft {v}",
                        state=vt,
                        large_image="minecraft",
                        large_text=f"Minecraft {v}",
                        small_image="logo",
                        small_text=APP_NAME,
                    )
                except Exception:
                    pass
            self.update_quote()
            self.toast(f"Запуск {v}", "success")

            def wait():
                proc.wait()
                stats_mod.end_session(self.settings, v)
                st_mod.save_settings(self.settings)
                if self.rpc.connected:
                    try:
                        self.rpc.update(details="В лаунчере", state=f"{APP_NAME} v{VERSION}")
                    except Exception:
                        pass

                def restore_ui():
                    try:
                        self.loader.spinner.configure(text="●", text_color=COLORS["green"])
                        self.loader.set_text("Версия установлена")
                        self.update_main_button()
                    except Exception:
                        pass
                try:
                    self.after(0, restore_ui)
                except Exception:
                    pass
            threading.Thread(target=wait, daemon=True).start()

        except Exception as err:
            err_text = str(err)
            self.toast(f"Ошибка запуска: {err_text}", "error")
            log.error(f"Launch error: {err_text}")
            try:
                self.loader.spinner.configure(text="●", text_color=COLORS["danger"])
                self.loader.set_text("Ошибка запуска")
            except Exception:
                pass

    def launch_thread(self):
        threading.Thread(target=self.launch_game, daemon=True).start()

    def install_thread(self):
        threading.Thread(target=self.install_version, daemon=True).start()

    def load_avatar_async(self):
        nick = self.nickname_entry.get().strip()
        if not nick:
            return

        def worker():
            img = fetch_skin(nick, 64)
            if img is not None:
                self.after(0, lambda i=img: self._set_avatar(i))
        threading.Thread(target=worker, daemon=True).start()

    def _set_avatar(self, pil_image):
        try:
            ctk_img = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(64, 64))
            self.avatar_label.configure(image=ctk_img, text="")
            self.avatar_image = ctk_img
        except Exception:
            pass

    def browse_folder(self):
        cur = self.path_entry.get()
        if not os.path.isdir(cur):
            cur = os.path.expanduser("~")
        folder = filedialog.askdirectory(title="Папка установки", initialdir=cur)
        if folder:
            folder = os.path.normpath(folder)
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, folder)
            self.settings["mc_dir"] = folder
            st_mod.save_settings(self.settings)
            os.makedirs(folder, exist_ok=True)
            self.refresh_versions()
            self.refresh_installed()
            self.update_main_button()

    def open_folder(self):
        try:
            os.makedirs(self.get_mc_dir(), exist_ok=True)
            os.startfile(self.get_mc_dir())
        except Exception:
            pass

    def browse_java(self):
        path = filedialog.askopenfilename(title="javaw.exe",
                                          filetypes=[("Java", "javaw.exe"), ("All", "*.*")])
        if path:
            self.java_entry.delete(0, "end")
            self.java_entry.insert(0, os.path.normpath(path))

    def auto_detect_java(self):
        paths = java_manager.detect_system_java()
        if not paths:
            self.toast("Java не найдена. Установите вручную.", "error")
            return
        best = paths[-1]
        self.java_entry.delete(0, "end")
        self.java_entry.insert(0, best)
        if ach_mod.check_and_unlock(self.settings, "java_set"):
            self.toast("Открыто: Настроил Java", "success")
        st_mod.save_settings(self.settings)
        self.refresh_achievements()
        self.toast(f"Java: {best}", "success")

    def download_java(self):
        needed = java_manager.java_major_for_mc(self.version_var.get())
        self.toast(f"Скачивание Java {needed}...", "info")
        self.loader.set_text(f"Скачивание Java {needed}...")

        def worker():
            try:
                path = java_manager.download_java(
                    needed,
                    on_progress=lambda p: self.after(0, lambda p=p: self.progress.set(p / 100)),
                    on_status=lambda s: self.after(0, lambda s=s: self.loader.set_text(s)),
                )
                if not path:
                    raise RuntimeError("javaw.exe не найден в скачанной Java")
                self.after(0, lambda path=path: self._java_downloaded(path, needed))
            except Exception as err:
                import traceback
                traceback.print_exc()
                log.error(f"Java download error: {err}")
                err_text = str(err)
                needed_text = needed
                self.after(0, lambda t=err_text, n=needed_text: messagebox.showerror(
                    "Ошибка скачивания Java",
                    f"Не удалось скачать Java {n}.\n\n"
                    f"Ошибка: {t}\n\n"
                    f"Скачай вручную: https://adoptium.net/temurin/releases/?version={n}\n"
                    f"Затем нажми '...' в настройках и укажи путь к javaw.exe"
                ))
        threading.Thread(target=worker, daemon=True).start()

    def _java_downloaded(self, path, major):
        self.settings.setdefault("java_per_version", {})[self.version_var.get()] = path
        self.java_entry.delete(0, "end")
        self.java_entry.insert(0, path)
        st_mod.save_settings(self.settings)
        self.toast(f"Java {major} установлена", "success")
        messagebox.showinfo("Java", f"Java {major} скачана:\n{path}\n\nТеперь можно запустить игру.")
        self.update_main_button()

    def toggle_sounds(self):
        self.settings["sounds_on"] = self.sounds_on.get()
        st_mod.save_settings(self.settings)

    def toggle_rpc(self):
        on = self.rpc_var.get()
        self.settings["discord_rpc"] = on
        if on:
            if self.rpc.connect():
                try:
                    self.rpc.update(details="В лаунчере", state=f"{APP_NAME} v{VERSION}")
                except Exception:
                    pass
                if ach_mod.check_and_unlock(self.settings, "discord_on"):
                    self.toast("Открыто: Discord RPC", "success")
            else:
                self.toast("pypresence не установлен", "error")
                self.rpc_var.set(False)
                self.settings["discord_rpc"] = False
        else:
            self.rpc.close()
        st_mod.save_settings(self.settings)
        self.refresh_achievements()

    def toggle_tray(self):
        self.settings["tray_mode"] = self.tray_var.get()
        st_mod.save_settings(self.settings)

    def toggle_autostart(self):
        on = self.autostart_var.get()
        if auto_mod.set_autostart(on):
            self.settings["autostart"] = on
            st_mod.save_settings(self.settings)
        else:
            self.toast("Не удалось изменить автозапуск", "error")
            self.autostart_var.set(not on)

    def verify_integrity(self):
        if messagebox.askyesno("Проверка", "Перекачать битые файлы?"):
            self.install_thread()

    def open_logs(self):
        try:
            path = os.path.abspath("slaylauncher.log")
            if os.path.isfile(path):
                os.startfile(path)
        except Exception:
            pass

    def save_all_settings(self):
        try:
            ram = int(self.ram_entry.get())
        except ValueError:
            ram = 4096
        self.settings.update({
            "mc_dir": self.get_mc_dir(),
            "ram": ram,
            "nickname": self.nickname_entry.get().strip(),
            "java_path": self.java_entry.get().strip(),
            "jvm_args": self.jvm_entry.get().strip(),
            "version_type": self.type_var.get(),
            "version": self.version_var.get(),
            "sounds_on": self.sounds_on.get(),
            "splash_enabled": self.splash_var.get(),
        })
        st_mod.save_settings(self.settings)
        self.toast("Настройки сохранены", "success")

    def on_close(self):
        if self.settings.get("tray_mode") and tray_mod.HAS_TRAY:
            self.withdraw()
            if self.tray_icon is None:
                def restore():
                    self.after(0, self.deiconify)

                def quit_app():
                    self.after(0, self._force_quit)

                self.tray_icon = tray_mod.run_tray(restore, quit_app)
                if self.tray_icon:
                    threading.Thread(target=self.tray_icon.run, daemon=True).start()
        else:
            self._force_quit()

    def _force_quit(self):
        try:
            self.rpc.close()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    app = SlayLauncher()
    app.mainloop()