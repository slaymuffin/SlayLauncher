import time


_active_sessions = {}  # version -> start_time


def start_session(version):
    _active_sessions[version] = time.time()


def end_session(settings, version):
    """Добавляет к статистике длительность сессии."""
    start = _active_sessions.pop(version, None)
    if not start:
        return
    duration = int(time.time() - start)
    stats = settings.setdefault("stats", {})
    entry = stats.setdefault(version, {"launches": 0, "seconds": 0})
    entry["seconds"] += duration


def inc_launch(settings, version):
    stats = settings.setdefault("stats", {})
    entry = stats.setdefault(version, {"launches": 0, "seconds": 0})
    entry["launches"] += 1


def total_hours(settings):
    total = sum(v.get("seconds", 0) for v in settings.get("stats", {}).values())
    return round(total / 3600, 1)


def favorite_version(settings):
    stats = settings.get("stats", {})
    if not stats:
        return None
    return max(stats.items(), key=lambda x: x[1].get("launches", 0))[0]