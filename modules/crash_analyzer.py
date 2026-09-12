import os
import re
import glob


def find_recent_crash(mc_dir, since_time):
    """
    Ищет СВЕЖИЙ краш-лог (появившийся после since_time).
    Возвращает (путь, текст) или (None, None).
    ВАЖНО: latest.log игнорируется — это обычный лог, не краш.
    """
    candidates = []

    # Только реальные краш-логи (не latest.log!)
    patterns = [
        os.path.join(mc_dir, "hs_err_pid*.log"),
        os.path.join(mc_dir, "crash-reports", "crash-*.txt"),
        os.path.join(mc_dir, "crash-reports", "crash-*.log"),
        os.path.join(os.path.expanduser("~"), "hs_err_pid*.log"),
    ]
    for p in patterns:
        for f in glob.glob(p):
            try:
                mtime = os.path.getmtime(f)
                if mtime > since_time:
                    candidates.append((mtime, f))
            except Exception:
                pass

    if not candidates:
        return None, None

    # Сортируем по времени — самый свежий первым
    candidates.sort(reverse=True)
    newest = candidates[0][1]
    try:
        with open(newest, "r", encoding="utf-8", errors="ignore") as fp:
            text = fp.read(200000)
        return newest, text
    except Exception:
        return newest, ""


def analyze(crash_text, mc_version=""):
    text_lower = crash_text.lower()

    if ("outofmemoryerror" in text_lower or
            "insufficient memory" in text_lower or
            "could not reserve enough space" in text_lower):
        return (
            "Не хватает оперативной памяти",
            "Java не смогла выделить запрошенный объём ОЗУ. Скорее всего, "
            "ты выставил слишком много МБ в настройках или запущено много программ.",
            [
                "Открой Настройки -> ОЗУ и уменьши значение на 1024 МБ",
                "Закрой браузер и другие тяжёлые приложения",
                "Если у тебя 8 ГБ ОЗУ — не ставь больше 4096 МБ",
            ],
        )

    if ("unsupportedclassversionerror" in text_lower or
            "has been compiled by a more recent version" in text_lower):
        m = re.search(r"class file version (\d+)", crash_text)
        ver = m.group(1) if m else "?"
        needed_map = {"52": "Java 8", "61": "Java 17", "65": "Java 21"}
        need = needed_map.get(ver, f"более новая Java (class {ver})")
        return (
            "Неподходящая версия Java",
            f"Minecraft требует {need}, а установлена другая.",
            [
                "Открой Настройки -> Скачать Java для выбранной версии",
                "Или нажми АВТО — лаунчер сам подберёт нужную",
                "Для 1.17+ нужна Java 17/21, для 1.16.5 и ниже — Java 8",
            ],
        )

    if ("nosuchmethoderror" in text_lower or
            ("noclassdeffounderror" in text_lower and "mod" in text_lower) or
            ("mixin" in text_lower and "exception" in text_lower)):
        return (
            "Конфликт или несовместимость модов",
            "Один из установленных модов не подходит под эту версию Minecraft "
            "или конфликтует с другим.",
            [
                "Открой вкладку Моды и отключи недавно добавленные",
                "Проверь, что моды для правильной версии MC и загрузчика",
                "Ставь моды по одному, чтобы найти виновника",
            ],
        )

    if ("pixel format not accelerated" in text_lower or
            ("opengl" in text_lower and "error" in text_lower) or
            "failed to create display" in text_lower):
        return (
            "Проблема с видеодрайвером / OpenGL",
            "Java не смогла инициализировать графику.",
            [
                "Обнови драйвер видеокарты (NVIDIA / AMD / Intel)",
                "Добавь в Аргументы JVM: -Dsun.java2d.opengl=false",
                "На ноутбуке запускай игру на дискретной видеокарте",
            ],
        )

    if ("zip file is empty" in text_lower or
            "invalid or corrupt jarfile" in text_lower or
            "error reading zip" in text_lower):
        return (
            "Повреждён файл версии",
            "Файл Minecraft (.jar) или библиотека скачались не полностью.",
            [
                "Открой вкладку Установленные",
                "Удали проблемную версию и установи заново",
                "Проверь стабильность интернета",
            ],
        )

    if "lwjgl" in text_lower and ("not found" in text_lower or "missing" in text_lower):
        return (
            "Не хватает библиотек LWJGL",
            "Стандартные библиотеки Minecraft для графики отсутствуют.",
            [
                "Удали версию во вкладке Установленные",
                "Установи её заново — библиотеки докачаются",
            ],
        )

    if ("error occurred during initialization of vm" in text_lower or
            "unrecognized vm option" in text_lower):
        return (
            "Ошибка в аргументах JVM",
            "Java не понимает один из переданных аргументов JVM.",
            [
                "Открой Настройки -> Аргументы JVM и очисти поле",
                "Не добавляй -XX:+UseZGC при Java 8",
            ],
        )

    return (
        "Java завершилась с ошибкой",
        "Не удалось однозначно определить причину. Посмотри полный лог.",
        [
            "Попробуй запустить игру с аргументами JVM по умолчанию",
            "Обнови Java через Настройки",
            "Попробуй другую версию Minecraft",
        ],
    )


def extract_key_lines(crash_text, max_lines=15):
    lines = crash_text.splitlines()
    important = []
    for line in lines:
        if any(k in line for k in [
            "Exception", "Error", "Caused by", "at net.minecraft",
            "at net.minecraftforge", "java.lang.", "Insufficient",
            "Could not", "Failed to", "Cannot",
        ]):
            important.append(line)
        if len(important) >= max_lines:
            break
    return important if important else lines[:max_lines]