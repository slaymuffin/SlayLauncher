import os
import json
import requests


MODRINTH = "https://api.modrinth.com/v2"
UA = {"User-Agent": "SlayLauncher/4.0 (contact: local)"}


def search_mods(query, game_version=None, loader=None, limit=20):
    """
    Поиск модов на Modrinth.
    loader: 'fabric' | 'forge' | 'quilt' | 'neoforge' | None
    game_version: только MC-версия, например '1.20.1' (без суффиксов Forge)
    """
    # Очищаем версию от мусора
    if game_version:
        game_version = game_version.strip()
        if "-" in game_version:
            game_version = game_version.split("-")[0]

    facets = [["project_type:mod"]]

    if game_version and game_version not in ("—", ""):
        facets.append([f"versions:{game_version}"])

    valid_loaders = ["fabric", "forge", "quilt", "neoforge"]
    if loader and loader.lower() in valid_loaders:
        facets.append([f"categories:{loader.lower()}"])

    params = {
        "query": query,
        "limit": limit,
        "facets": json.dumps(facets),
    }
    headers = {
        "User-Agent": "SlayLauncher/4.0 (github.com/slaylauncher)",
    }

    # Диагностика
    print(f"[Modrinth] URL params: query='{query}', facets={params['facets']}")

    r = requests.get(f"{MODRINTH}/search", params=params, headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json()
    return data.get("hits", [])


def get_versions_for_mod(project_id, game_version=None, loader=None):
    """Список файлов проекта."""
    url = f"{MODRINTH}/project/{project_id}/version"
    params = {}
    if game_version:
        params["game_versions"] = f'["{game_version}"]'
    if loader:
        params["loaders"] = f'["{loader}"]'
    r = requests.get(url, params=params, headers=UA, timeout=15)
    r.raise_for_status()
    return r.json()


def install_mod(project_id, mc_dir, game_version=None, loader=None, on_status=None):
    """
    Скачивает последнюю подходящую версию мода в <mc_dir>/mods/<версия>.
    Возвращает путь к .jar
    """
    if on_status:
        on_status("Поиск подходящей версии...")

    versions = get_versions_for_mod(project_id, game_version, loader)
    if not versions:
        raise RuntimeError("Нет подходящих версий мода")

    v = versions[0]
    files = v.get("files", [])
    if not files:
        raise RuntimeError("У мода нет файлов")

    # Основной файл
    primary = next((f for f in files if f.get("primary")), files[0])
    url = primary["url"]
    filename = primary["filename"]

    mods_dir = os.path.join(mc_dir, "mods")
    os.makedirs(mods_dir, exist_ok=True)
    target = os.path.join(mods_dir, filename)

    if on_status:
        on_status(f"Скачивание {filename}...")

    with requests.get(url, stream=True, headers=UA, timeout=60) as resp:
        resp.raise_for_status()
        with open(target, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)

    if on_status:
        on_status("Установлено")
    return target


def list_installed_mods(mc_dir):
    mods_dir = os.path.join(mc_dir, "mods")
    if not os.path.isdir(mods_dir):
        return []
    return sorted(f for f in os.listdir(mods_dir) if f.endswith(".jar"))


def delete_mod(mc_dir, filename):
    path = os.path.join(mc_dir, "mods", filename)
    if os.path.isfile(path):
        os.remove(path)
        return True
    return False