import os
import zipfile
import datetime


def backup_saves(mc_dir, on_status=None):
    """
    Архивирует папку saves/ в backups/saves_YYYY-MM-DD_HH-MM.zip.
    Возвращает путь к архиву.
    """
    saves = os.path.join(mc_dir, "saves")
    if not os.path.isdir(saves):
        raise RuntimeError("Папка saves/ не найдена")

    backups_dir = os.path.join(mc_dir, "slay_backups")
    os.makedirs(backups_dir, exist_ok=True)

    ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    archive = os.path.join(backups_dir, f"saves_{ts}.zip")

    if on_status:
        on_status("Архивация миров...")

    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for dp, dn, fn in os.walk(saves):
            for f in fn:
                full = os.path.join(dp, f)
                arc = os.path.relpath(full, mc_dir)
                z.write(full, arc)

    if on_status:
        on_status(f"Бэкап создан: {os.path.basename(archive)}")
    return archive


def list_backups(mc_dir):
    backups_dir = os.path.join(mc_dir, "slay_backups")
    if not os.path.isdir(backups_dir):
        return []
    files = [f for f in os.listdir(backups_dir) if f.endswith(".zip")]
    files.sort(reverse=True)
    return files