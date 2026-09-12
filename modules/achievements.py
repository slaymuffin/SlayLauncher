from .config import ACHIEVEMENTS


def check_and_unlock(settings, key):
    """Возвращает True если достижение только что открыто."""
    unlocked = settings.setdefault("achievements", [])
    if key in ACHIEVEMENTS and key not in unlocked:
        unlocked.append(key)
        return True
    return False


def list_achievements(settings):
    unlocked = set(settings.get("achievements", []))
    return [(k, *ACHIEVEMENTS[k], k in unlocked) for k in ACHIEVEMENTS]