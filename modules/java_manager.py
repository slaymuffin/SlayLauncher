import os
import json
import zipfile
import tarfile
import requests
import platform
from .config import LAUNCHER_DIR


JAVA_DIR = os.path.join(LAUNCHER_DIR, "java")
ADOPTIUM_API = (
    "https://api.adoptium.net/v3/assets/feature_releases/{version}/ga"
    "?architecture=x64&heap_size=normal&image_type=jdk&jvm_impl=hotspot"
    "&os=windows&page=0&page_size=1&project=jdk"
    "&sort_method=DEFAULT&sort_order=DESC&vendor=eclipse"
)


def list_installed_java():
    """Ищет javaw.exe в папке лаунчера."""
    found = {}
    if not os.path.isdir(JAVA_DIR):
        return found
    for name in os.listdir(JAVA_DIR):
        folder = os.path.join(JAVA_DIR, name)
        if not os.path.isdir(folder):
            continue
        javaw = _find_javaw(folder)
        if javaw:
            found[name] = javaw
    return found


def _find_javaw(root):
    """Рекурсивно ищет javaw.exe."""
    if not os.path.isdir(root):
        return None
    for dp, dn, fn in os.walk(root):
        for f in fn:
            if f.lower() == "javaw.exe":
                return os.path.join(dp, f)
    return None


def detect_system_java():
    """Стандартные места установки Java на Windows."""
    paths = []
    search_dirs = [
        r"C:\Program Files\Java",
        r"C:\Program Files\Eclipse Adoptium",
        r"C:\Program Files\Microsoft",
        r"C:\Program Files (x86)\Java",
        r"C:\Program Files\Zulu",
        r"C:\Program Files\BellSoft",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Eclipse Adoptium"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Zulu"),
    ]
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        try:
            for name in os.listdir(d):
                javaw = os.path.join(d, name, "bin", "javaw.exe")
                if os.path.isfile(javaw):
                    paths.append(javaw)
        except Exception:
            pass
    return paths


def download_java(major_version, on_progress=None, on_status=None):
    """
    Скачивает JDK нужной мажорной версии (8, 17, 21) с Adoptium.
    Возвращает путь к javaw.exe.
    """
    if platform.system() != "Windows":
        raise RuntimeError("Автоскачивание Java только для Windows")

    os.makedirs(JAVA_DIR, exist_ok=True)

    if on_status:
        on_status(f"Запрос к Adoptium для Java {major_version}...")

    # Запрос к Adoptium
    url = ADOPTIUM_API.format(version=major_version)
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()

    if not data:
        raise RuntimeError(f"Adoptium не вернул сборок для Java {major_version}")

    release = data[0]
    binaries = release.get("binaries", [])
    if not binaries:
        raise RuntimeError("Adoptium не вернул binaries")

    if on_status:
        on_status(f"Найдено {len(binaries)} файлов, выбираю Windows x64 JDK...")

    # API уже отфильтровал, но проверим ещё раз
    chosen = None
    for b in binaries:
        pkg = b.get("package", {})
        os_name = (pkg.get("os") or "").lower()
        arch = (pkg.get("arch") or "").lower()
        if os_name == "windows" and arch == "x64":
            chosen = b
            break

    # Fallback — берём первый бинарник
    if not chosen:
        chosen = binaries[0]
        pkg = chosen.get("package", {})
        if on_status:
            on_status(f"Fallback: {pkg.get('os')} {pkg.get('arch')} {pkg.get('image_type')}")

    link = chosen["package"]["link"]
    filename = chosen["package"]["name"]
    semver = release.get("version_data", {}).get("semver", f"java{major_version}")

    if on_status:
        on_status(f"Файл: {filename}")

    # Целевая папка
    target_dir = os.path.join(JAVA_DIR, f"jdk-{major_version}-{semver}")
    os.makedirs(target_dir, exist_ok=True)
    archive_path = os.path.join(target_dir, filename)

    # Скачиваем с прогрессом
    with requests.get(link, stream=True, timeout=180) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(archive_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total and on_progress:
                        on_progress(int(downloaded / total * 100))

    if on_status:
        on_status(f"Скачано {downloaded // (1024 * 1024)} МБ. Распаковка...")

    # Распаковка
    try:
        if filename.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as z:
                z.extractall(target_dir)
        elif filename.endswith(".tar.gz"):
            with tarfile.open(archive_path, "r:gz") as t:
                t.extractall(target_dir)
        else:
            raise RuntimeError(f"Неизвестный формат архива: {filename}")
    except Exception as e:
        raise RuntimeError(f"Ошибка распаковки: {e}")

    # Удаляем архив
    try:
        os.remove(archive_path)
    except Exception:
        pass

    # Ищем javaw.exe
    if on_status:
        on_status("Поиск javaw.exe...")

    javaw = _find_javaw(target_dir)

    if not javaw:
        # Диагностика
        tree = []
        for dp, dn, fn in os.walk(target_dir):
            for f in fn[:5]:
                rel = os.path.relpath(os.path.join(dp, f), target_dir)
                tree.append(rel)
            if len(tree) > 30:
                break
        raise RuntimeError(
            f"javaw.exe не найден в {target_dir}\n"
            f"Содержимое (первые 30):\n" + "\n".join(tree)
        )

    if on_status:
        on_status(f"Java {major_version} готова")

    # Записываем файл-маркер, чтобы видеть версию
    try:
        with open(os.path.join(target_dir, "java_version.txt"), "w") as f:
            f.write(str(major_version))
    except Exception:
        pass

    return javaw


def java_major_for_mc(mc_version: str) -> int:
    """
    Определяет нужную мажорную версию Java для версии Minecraft.
    1.7.10 - 1.16.5 → 8
    1.17 - 1.20.4 → 17
    1.20.5+ → 21
    """
    try:
        parts = mc_version.split(".")
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch_str = parts[2].split("-")[0] if len(parts) > 2 else "0"
        patch = int(patch_str) if patch_str.isdigit() else 0
    except (ValueError, IndexError):
        return 8

    if major > 1:
        return 21
    if minor >= 21:
        return 21
    if minor >= 20 and patch >= 5:
        return 21
    if minor >= 17:
        return 17
    return 8