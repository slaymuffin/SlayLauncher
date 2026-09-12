try:
    import winsound
    HAS_SOUND = True
except ImportError:
    HAS_SOUND = False

import os
from .config import LAUNCHER_DIR

SOUND_DIR = os.path.join(LAUNCHER_DIR, "assets", "sounds")


def play(name, enabled=True):
    """name: 'click' | 'success' | 'error'."""
    if not enabled or not HAS_SOUND:
        return
    path = os.path.join(SOUND_DIR, f"{name}.wav")
    if os.path.isfile(path):
        try:
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            pass