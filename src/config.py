import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # --- Receptor ---
    class RECEPTOR:
        PULSE = "pulse"

    # --- Effector ---
    class EFFECTOR:
        CONSOLE = "console"

    # --- Pulse ---
    PULSE_INTERVAL = int(os.getenv("PULSE_INTERVAL", 10))
