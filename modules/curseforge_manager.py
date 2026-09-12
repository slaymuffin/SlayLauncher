import os
import json
import requests

# Базовый URL зеркала MCIM для CurseForge API
CURSEFORGE_API = "https://mod.mcimirror.top/curseforge/v1"

def _headers():
    return {
        "User-Agent": "SlayLauncher/4.0 (contact: local)",
        "Accept": "application/json",
    }

def search_mods(query, game_version=None, loader=None, api_key=None, limit=20):
    """
    Поиск модов на CurseForge через зеркало MCIM.
    loader: 'forge' | 'fabric' | 'quilt' | 'neoforge' | None
    game_version: '1.16.5', '1.20.1' и т.д. (без суффиксов Forge)
    """
    if game_version and "-" in game_version:
        game_version = game_version.split("-")[0]

    params = {
        "gameId": 432,           # ID Minecraft
        "classId": 6,            # ID категории "Mods"
        "searchFilter": query,
        "pageSize": limit,
        "sortField": 2,          # Сортировка по популярности
        "sortOrder": "desc",
    }

    if game_version:
        params["gameVersion"] = game_version

    if loader and loader.lower() in ("forge", "fabric", "quilt", "neoforge"):
        # CurseForge использует modLoaderType: 1=Forge, 4=Fabric, 5=Quilt, 6=NeoForge
        loader_map = {"forge": 1, "fabric": 4, "quilt": 5, "neoforge": 6}
        params["modLoaderType"] = loader_map.get(loader.lower(), 1)

    print(f"[MCIM] Search: query='{query}', version='{game_version}', loader='{loader}'")

    r = requests.get(f"{CURSEFORGE_API}/mods/search",
                     params=params,
                     headers=_headers(),
                     timeout=20)
    r.raise_for_status()
    data = r.json()
    return data.get("data", [])

def get_mod_files(mod_id, game_version=None, loader=None, api_key=None):
    """Возвращает список файлов мода."""
    if game_version and "-" in game_version:
        game_version = game_version.split("-")[0]

    params = {}
    if game_version:
        params["gameVersion"] = game_version
    if loader and loader.lower() in ("forge", "fabric", "quilt", "neoforge"):
        loader_map = {"forge": 1, "fabric": 4, "quilt": 5, "neoforge": 6}
        params["modLoaderType"] = loader_map.get(loader.lower(), 1)

    r = requests.get(f"{CURSEFORGE_API}/mods/{mod_id}/files",
                     params=params,
                     headers=_headers(),
                     timeout=20)
    r.raise_for_status()
    data = r.json()
    return data.get("data", [])

def get_download_url(mod_id, file_id, api_key=None):
    """Возвращает прямую ссылку на скачивание файла мода."""
    url = f"{CURSEFORGE_API}/mods/{mod_id}/files/{file_id}/download-url"
    try:
        r = requests.get(url, headers=_headers(), timeout=15)
        r.raise_for_status()
        data = r.json()
        # MCIM возвращает {"data": "https://..."}
        download_url = data.get("data")
        if download_url and isinstance(download_url, str) and download_url.startswith("http"):
            print(f"[MCIM] Download URL: {download_url[:80]}...")
            return download_url
    except Exception as e:
        print(f"[MCIM] get_download_url error: {e}")

    return None

def install_mod(mod_id, mc_dir, game_version=None, loader=None, api_key=None, on_status=None):
    """Скачивает последний подходящий файл мода в <mc_dir>/mods/."""
    import zipfile
    import time
    import urllib.parse

    if on_status:
        on_status("Поиск файлов мода...")

    files = get_mod_files(mod_id, game_version, loader)
    if not files:
        raise RuntimeError("Нет подходящих файлов для этой версии/загрузчика")

    files.sort(key=lambda f: f.get("fileDate", ""), reverse=True)
    chosen = files[0]

    file_id = chosen["id"]
    filename = chosen["fileName"]
    expected_size = chosen.get("fileLength", 0)

    # Собираем список возможных URL — пробуем по очереди
    urls_to_try = []

    # 1. Из поля downloadUrl (иногда есть)
    if chosen.get("downloadUrl"):
        urls_to_try.append(chosen["downloadUrl"])

    # 2. Прямая ссылка на ForgeCDN
    file_id_str = str(file_id)
    if len(file_id_str) > 3:
        part1 = file_id_str[:-3]
        part2 = file_id_str[-3:]
        cdn_url = f"https://mediafilez.forgecdn.net/files/{part1}/{part2}/{urllib.parse.quote(filename)}"
        urls_to_try.append(cdn_url)

    # 3. Через MCIM
    mcim_url = get_download_url(mod_id, file_id)
    if mcim_url:
        urls_to_try.append(mcim_url)

    if not urls_to_try:
        raise RuntimeError("Не удалось получить ссылку на скачивание")

    print(f"[MCIM] URLs to try: {urls_to_try}")

    mods_dir = os.path.join(mc_dir, "mods")
    os.makedirs(mods_dir, exist_ok=True)
    target = os.path.join(mods_dir, filename)

    last_err = None
    for url in urls_to_try:
        if on_status:
            on_status(f"Скачивание с {url[:50]}...")

        for attempt in range(2):
            try:
                if os.path.isfile(target):
                    os.remove(target)

                with requests.get(url, stream=True, headers=_headers(),
                                  timeout=180, allow_redirects=True) as resp:
                    resp.raise_for_status()
                    content_type = resp.headers.get("content-type", "")
                    print(f"[MCIM] Response: status={resp.status_code}, type={content_type}")

                    if "html" in content_type.lower() or "json" in content_type.lower():
                        raise RuntimeError(f"Сервер вернул {content_type}, а не файл")

                    with open(target, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=65536):
                            if chunk:
                                f.write(chunk)

                actual_size = os.path.getsize(target)

                if expected_size and abs(actual_size - expected_size) > 1000:
                    raise RuntimeError(
                        f"Размер {actual_size} != ожидалось {expected_size}"
                    )

                try:
                    with zipfile.ZipFile(target, "r") as z:
                        z.testzip()
                except zipfile.BadZipFile:
                    raise RuntimeError("Файл не zip")

                if on_status:
                    on_status("Установлено")
                return target

            except Exception as e:
                last_err = e
                print(f"[MCIM] Attempt failed: {e}")
                if on_status:
                    on_status(f"Повтор...")
                time.sleep(1)

    raise RuntimeError(f"Не удалось скачать мод: {last_err}")

def list_installed_mods(mc_dir):
    """Список .jar файлов в mods/"""
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