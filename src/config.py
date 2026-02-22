import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # --- Receptor ---
    class RECEPTOR:
        MICROPHONE = "microphone"
        PULSE = "pulse"

    # --- Effector ---
    class EFFECTOR:
        CONSOLE = "console"

    # --- 共通設定 ---
    HOST = os.getenv("HOST", "localhost")
    LANG = os.getenv("LANG", "ja-JP")

    # --- Microphone ---
    MIC_DURATION = int(os.getenv("MIC_DURATION", 1))
    MIC_EXPIRY_TIME = int(os.getenv("MIC_EXPIRY_TIME", 60))
    MIC_PHRASE_TIME_LIMIT = int(os.getenv("MIC_PHRASE_TIME_LIMIT", 10))

    # --- Pulse ---
    PULSE_INTERVAL = int(os.getenv("PULSE_INTERVAL", 10))

    # --- Redis ---
    REDIS_PORT_HOST = int(os.getenv("REDIS_PORT_HOST", 6379))
