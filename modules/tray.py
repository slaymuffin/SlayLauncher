try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False


def make_icon():
    """Простая иконка-заглушка."""
    img = Image.new("RGB", (64, 64), "#1f1038")
    d = ImageDraw.Draw(img)
    d.polygon([(32, 8), (44, 32), (32, 56), (20, 32)], fill="#ff3bae")
    return img


def run_tray(on_restore, on_exit):
    """Запускает иконку в трее. on_restore/on_exit — колбэки."""
    if not HAS_TRAY:
        return None
    menu = pystray.Menu(
        pystray.MenuItem("Открыть", lambda: on_restore()),
        pystray.MenuItem("Выход", lambda: on_exit()),
    )
    icon = pystray.Icon("SlayLauncher", make_icon(), "SlayLauncher", menu)
    return icon