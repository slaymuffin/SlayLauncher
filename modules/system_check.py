import os
import sys
import ctypes
import shutil
import subprocess
import platform
from . import java_manager


def get_ram_info():
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return (stat.ullTotalPhys // (1024 * 1024),
                stat.ullAvailPhys // (1024 * 1024))
    except Exception:
        return (0, 0)


def get_gpu_name():
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_VideoController).Name"],
            timeout=8, creationflags=subprocess.CREATE_NO_WINDOW,
        ).decode("utf-8", errors="ignore").strip()
        names = [line.strip() for line in out.splitlines() if line.strip()]
        return names if names else ["Неизвестно"]
    except Exception:
        return ["Не удалось определить"]


def get_cpu_name():
    try:
        return platform.processor() or "Неизвестно"
    except Exception:
        return "Неизвестно"


def get_disk_free(path):
    try:
        if not os.path.isdir(path):
            path = os.path.dirname(path) or "C:\\"
        usage = shutil.disk_usage(path)
        return (round(usage.free / (1024 ** 3), 1),
                round(usage.total / (1024 ** 3), 1))
    except Exception:
        return (0, 0)


def get_java_versions():
    result = []
    paths = java_manager.detect_system_java()
    for key, path in java_manager.list_installed_java().items():
        paths.append(path)

    seen = set()
    for p in paths:
        if p in seen:
            continue
        seen.add(p)
        ver = "?"
        try:
            out = subprocess.check_output(
                [p, "-version"], stderr=subprocess.STDOUT, timeout=6,
                creationflags=subprocess.CREATE_NO_WINDOW,
            ).decode("utf-8", errors="ignore")
            first = out.splitlines()[0] if out else ""
            if '"' in first:
                ver = first.split('"')[1]
        except Exception:
            pass
        result.append({"path": p, "version": ver})
    return result


def run_full_check(mc_dir):
    report = {}
    total, avail = get_ram_info()
    report["ram_total_mb"] = total
    report["ram_avail_mb"] = avail

    if total >= 16 * 1024:
        rec = 6144
    elif total >= 8 * 1024:
        rec = 4096
    elif total >= 6 * 1024:
        rec = 3072
    elif total >= 4 * 1024:
        rec = 2048
    else:
        rec = 1024
    report["ram_recommended_mb"] = rec

    report["gpu"] = get_gpu_name()
    report["cpu"] = get_cpu_name()

    free_gb, total_gb = get_disk_free(mc_dir)
    report["disk_free_gb"] = free_gb
    report["disk_total_gb"] = total_gb
    report["disk_path"] = mc_dir

    report["java"] = get_java_versions()
    report["mc_dir"] = mc_dir
    report["mc_dir_exists"] = os.path.isdir(mc_dir)

    warnings = []
    if total < 6 * 1024:
        warnings.append("Мало ОЗУ (меньше 6 ГБ) — Minecraft может тормозить")
    if free_gb < 5:
        warnings.append(f"Мало места на диске ({free_gb} ГБ) — нужно хотя бы 5 ГБ")
    if not report["java"]:
        warnings.append("Java не найдена — установите через лаунчер или с adoptium.net")
    report["warnings"] = warnings
    return report


def format_report(report):
    lines = []
    lines.append("=== ПРОВЕРКА СИСТЕМЫ ===\n")

    ram_t = report.get("ram_total_mb", 0)
    ram_a = report.get("ram_avail_mb", 0)
    ram_rec = report.get("ram_recommended_mb", 0)
    lines.append(f"[RAM] Всего:       {ram_t} МБ ({ram_t // 1024} ГБ)")
    lines.append(f"[RAM] Доступно:    {ram_a} МБ")
    lines.append(f"[i]  Рекомендуется выставить {ram_rec} МБ в настройках лаунчера\n")

    lines.append(f"[CPU] {report.get('cpu', '?')}")
    gpus = report.get("gpu", [])
    for i, g in enumerate(gpus):
        lines.append(f"[GPU #{i+1}] {g}")
    lines.append("")

    lines.append(f"[DISK] {report.get('disk_path', '?')[:3]}\\... "
                 f"{report.get('disk_free_gb', 0)} ГБ свободно "
                 f"из {report.get('disk_total_gb', 0)} ГБ\n")

    java_list = report.get("java", [])
    if java_list:
        lines.append(f"[JAVA] Найдено: {len(java_list)}")
        for j in java_list:
            lines.append(f"   - {j['version']:>12}  ->  {j['path']}")
    else:
        lines.append("[JAVA] Java не найдена!")
    lines.append("")

    warnings = report.get("warnings", [])
    if warnings:
        lines.append("!!! ВНИМАНИЕ:")
        for w in warnings:
            lines.append(f"   - {w}")
    else:
        lines.append("OK - проблем не обнаружено. Можно играть!")

    return "\n".join(lines)