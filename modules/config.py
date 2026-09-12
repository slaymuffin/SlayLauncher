import os

APP_NAME = "SlayLauncher"
VERSION = "1.0"
LAUNCHER_VERSION_URL = "https://example.com/version.json"  # ← замени на свою ссылку

SETTINGS_FILE = "slaylauncher_settings.json"
DEFAULT_MC_DIR = os.path.join(os.path.expanduser("~"), ".slayminecraft")
LAUNCHER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ACCENTS = {
    "pink":   "#ff3bae",
    "cyan":   "#00edff",
    "purple": "#a855f7",
    "green":  "#22d3a0",
}

BASE_DARK = {
    "bg":         "#0d0217",
    "bg2":        "#1a0b2e",
    "card":       "#1f1038",
    "card_hover": "#2d1b4e",
    "text":       "#faf5ed",
    "text_muted": "#9f7aea",
    "border":     "#3a2260",
    "green":      "#22d3a0",
    "danger":     "#e34c4c",
}

THEMES = {
    "vaporwave": {
        "name": "Vaporwave",
        "bg":         "#0d0217",
        "bg2":        "#1a0b2e",
        "card":       "#1f1038",
        "card_hover": "#2d1b4e",
        "text":       "#faf5ed",
        "text_muted": "#9f7aea",
        "border":     "#3a2260",
    },
    "midnight": {
        "name": "Midnight",
        "bg":         "#0a0e1a",
        "bg2":        "#111827",
        "card":       "#1a2332",
        "card_hover": "#243044",
        "text":       "#e8eef7",
        "text_muted": "#7a8ba5",
        "border":     "#2a3a52",
    },
    "forest": {
        "name": "Forest",
        "bg":         "#0a140e",
        "bg2":        "#132018",
        "card":       "#1a2e22",
        "card_hover": "#25402f",
        "text":       "#e8f5ec",
        "text_muted": "#7aa58b",
        "border":     "#2a4a35",
    },
    "halloween": {
        "name": "🎃 Halloween",
        "bg":         "#0d0200",
        "bg2":        "#1a0800",
        "card":       "#24100a",
        "card_hover": "#3a1810",
        "text":       "#ffefe0",
        "text_muted": "#c08560",
        "border":     "#4a1a08",
    },
    "newyear": {
        "name": "❄ Новый год",
        "bg":         "#010a18",
        "bg2":        "#0a1830",
        "card":       "#102040",
        "card_hover": "#183058",
        "text":       "#eaf3ff",
        "text_muted": "#7a9cc7",
        "border":     "#1a3a60",
    },
    "light": {
        "name": "Light",
        "bg":         "#f0ecf7",
        "bg2":        "#e2d9f0",
        "card":       "#ffffff",
        "card_hover": "#ece2f7",
        "text":       "#1a0b2e",
        "text_muted": "#7a5faa",
        "border":     "#c9b8e0",
    },
}

COLORS = {}
THEME_NAME = "vaporwave"


def apply_theme(accent_key: str, theme_name: str = "vaporwave"):
    global COLORS, THEME_NAME
    THEME_NAME = theme_name
    theme = THEMES.get(theme_name, THEMES["vaporwave"])
    base = {
        "bg":         theme["bg"],
        "bg2":        theme["bg2"],
        "card":       theme["card"],
        "card_hover": theme["card_hover"],
        "text":       theme["text"],
        "text_muted": theme["text_muted"],
        "border":     theme["border"],
        "green":      "#22d3a0",
        "danger":     "#e34c4c",
    }
    a = ACCENTS.get(accent_key, ACCENTS["pink"])
    base["accent"] = a
    base["accent_hover"] = a
    COLORS.clear()
    COLORS.update(base)


QUOTES = [
    "Ты попал в мир, полный чудес!",
    "Не копай вниз!",
    "Creeper? Aw man!",
    "Кирка, меч, еда — три вещи для выживания.",
    "Ночь близко. Построй укрытие.",
    "Алмазы где-то глубоко.",
    "Слушай звуки пещеры.",
    "Лава — это плохо.",
    "Кровать — точка возрождения.",
    "Убей дракона!",
    "Найди Незерский портал.",
    "Пещеры — это опасность и сокровища.",
]

ACHIEVEMENTS = {
    "install_10":   ("T", "Установил 10 версий"),
    "launch_100":   (">", "Запустил игру 100 раз"),
    "java_set":     ("J", "Настроил Java вручную"),
    "mods_1gb":     ("M", "Скачал 1 ГБ модов"),
    "backup_made":  ("B", "Сделал первый бэкап"),
    "discord_on":   ("D", "Включил Discord RPC"),
    "profile_made": ("P", "Создал свой первый профиль"),
}