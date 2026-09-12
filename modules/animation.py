import customtkinter as ctk
from .config import COLORS


class AnimatedSpinner(ctk.CTkFrame):
    """
    Анимированный спиннер с текстом статуса.
    Использует кадры-эмодзи для эффекта движения.
    """

    # Кадры анимации (кирка копает / ходьба / можно свои)
    FRAMES_PICKAXE = ["⛏️  ", " ⛏️ ", "  ⛏️", " ⛏️ "]
    FRAMES_DOTS = ["●  ", "●● ", "●●●", "●● ", "●  "]
    FRAMES_BLOCKS = ["🟪", "🟦", "🟩", "🟨", "🟧", "🟥"]
    FRAMES_BRAILLE = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, parent, frame_set="braille", **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        if frame_set == "pickaxe":
            self.frames = self.FRAMES_PICKAXE
        elif frame_set == "dots":
            self.frames = self.FRAMES_DOTS
        elif frame_set == "blocks":
            self.frames = self.FRAMES_BLOCKS
        else:
            self.frames = self.FRAMES_BRAILLE

        self.idx = 0
        self._running = False
        self._after_id = None

        # Спиннер
        self.spinner = ctk.CTkLabel(
            self,
            text=self.frames[0],
            font=("Segoe UI", 14, "bold"),
            text_color=COLORS["accent"],
            width=24,
        )
        self.spinner.pack(side="left", padx=(0, 8))

        # Текст статуса
        self.text = ctk.CTkLabel(
            self,
            text="Готов к запуску",
            font=("Segoe UI", 12),
            text_color=COLORS["text_muted"],
            anchor="w",
        )
        self.text.pack(side="left", fill="x", expand=True)

    def start(self, initial_text="Работаю..."):
        self._running = True
        self.set_text(initial_text)
        self._tick()

    def stop(self, final_text=None):
        self._running = False
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        self.spinner.configure(text="●", text_color=COLORS["green"])
        if final_text is not None:
            self.set_text(final_text)

    def set_text(self, text):
        try:
            self.text.configure(text=text)
        except Exception:
            pass

    def set_color(self, color):
        try:
            self.spinner.configure(text_color=color)
        except Exception:
            pass

    def _tick(self):
        if not self._running:
            return
        try:
            self.spinner.configure(text=self.frames[self.idx])
            self.idx = (self.idx + 1) % len(self.frames)
            self._after_id = self.after(120, self._tick)
        except Exception:
            pass