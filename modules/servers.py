import requests


def check_server_status(ip, port=25565, timeout=5):
    """Через mcsrvstat.us узнаём онлайн/офлайн и количество игроков."""
    try:
        r = requests.get(f"https://api.mcsrvstat.us/3/{ip}:{port}", timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return {
            "online": bool(data.get("online")),
            "players": data.get("players", {}).get("online", 0),
            "max": data.get("players", {}).get("max", 0),
            "motd": " ".join(data.get("motd", {}).get("clean", [])) if data.get("motd") else "",
        }
    except Exception:
        return {"online": False, "players": 0, "max": 0, "motd": ""}


def check_all_servers(servers):
    """servers — список dict с 'ip' и 'port'. Возвращает список с полем status."""
    result = []
    for s in servers:
        st = check_server_status(s.get("ip"), s.get("port", 25565))
        result.append({**s, "status": st})
    return result