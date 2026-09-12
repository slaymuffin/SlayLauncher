try:
    from pypresence import Presence
    HAS_PYP = True
except ImportError:
    HAS_PYP = False


CLIENT_ID = "1548280984133181562"  # твой ID из Developer Portal


class RPC:
    def __init__(self):
        self.rpc = None
        self.connected = False

    def connect(self):
        if not HAS_PYP:
            return False
        try:
            self.rpc = Presence(CLIENT_ID)
            self.rpc.connect()
            self.connected = True
            return True
        except Exception:
            self.connected = False
            return False

    def update(self, details="В лаунчере", state="SlayLauncher",
               large_image="logo", large_text="SlayLauncher",
               small_image=None, small_text=None):
        if not self.connected:
            return
        try:
            kwargs = {
                "details": details,
                "state": state,
                "large_image": large_image,
                "large_text": large_text,
            }
            if small_image:
                kwargs["small_image"] = small_image
                kwargs["small_text"] = small_text or ""
            self.rpc.update(**kwargs)
        except Exception as e:
            print(f"[RPC] update error: {e}")

    def close(self):
        if self.connected:
            try:
                self.rpc.close()
            except Exception:
                pass
            self.connected = False