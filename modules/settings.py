import json
import os
from .config import SETTINGS_FILE, DEFAULT_MC_DIR


def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                s = json.load(f)
        except Exception:
            s = {}
    else:
        s = {}

    defaults = {
        "nickname": "Slayer",
        "ram": 4096,
        "version": "1.20.1",
        "mc_dir": DEFAULT_MC_DIR,
        "version_type": "Ванилла",
        "show_releases": True,
        "show_snapshots": False,
        "show_old_beta": False,
        "show_old_alpha": False,
        "forge_only_latest": True,
        "java_path": "",
        "java_per_version": {},
        "jvm_args": "",
        "accent": "pink",
        "theme_name": "vaporwave",
        "profiles": ["Slayer"],
        "launches": 0,
        "discord_rpc": False,
        "tray_mode": False,
        "autostart": False,
        "sounds_on": True,
        "servers": [],
        "stats": {},
        "achievements": [],
        "mods_downloaded_mb": 0,
        "backups_made": 0,
        "splash_enabled": True,
        "favorites": [],
        "flash_on_launch": True,
        "auto_crash_check": True,
        "mod_source": "modrinth",
        "check_updates_on_start": True,
        "seasonal_themes": True,
    }
    for k, v in defaults.items():
        s.setdefault(k, v)

    # Миграция: старые ключи
    s.pop("curseforge_api_key", None)
    old_theme = s.pop("theme", None)
    if old_theme == "light" and "theme_name" not in s:
        s["theme_name"] = "light"
    for key in ("wallpaper", "wallpaper_darkness"):
        s.pop(key, None)

    return s


def save_settings(data):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[settings] save error: {e}")