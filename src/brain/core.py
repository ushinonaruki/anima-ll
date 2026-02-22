import redis
from config import Config

r = redis.Redis(
    host=Config.HOST,
    port=Config.REDIS_PORT_HOST,
    decode_responses=True,
)


def run(signal):
    match signal.get("receptor"):
        case Config.RECEPTOR.MICROPHONE:
            user_text = r.get(signal.get("memory_id"))
            return {
                "effector": Config.EFFECTOR.CONSOLE,
                "message": user_text,
            }
        case Config.RECEPTOR.PULSE:
            return {
                "effector": Config.EFFECTOR.CONSOLE,
                "message": "Test Message",
            }
        case _:
            return None
