import customtkinter as ctk
from .config import COLORS


class Toast(ctk.CTkToplevel):
    """Небольшое всплывающее окно в правом нижнем углу родителя."""
    def __init__(self, parent, text, kind="info", duration=3000):
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(fg_color=COLORS["card"])

        # Цвет по типу
        colors = {
            "info": COLORS["accent"],
            "success": COLORS["green"],
            "error": COLORS["danger"],
        }
        border = colors.get(kind, COLORS["accent"])

        frame = ctk.CTkFrame(self, fg_color=COLORS["card"],
                             border_width=2, border_color=border, corner_radius=4)
        frame.pack(fill="both", expand=True)

        ctk.CTkLabel(
            frame, text=text, font=("Segoe UI", 11),
            text_color=COLORS["text"], wraplength=260, justify="left",
        ).pack(padx=14, pady=10)

        # Позиционируем
        self.update_idletasks()
        px = parent.winfo_rootx() + parent.winfo_width() - 300
        py = parent.winfo_rooty() + parent.winfo_height() - 80
        self.geometry(f"300x60+{px}+{py}")

        self.after(duration, self.destroy)