from config import Config


def run(signal):
    match signal.get("receptor"):
        case Config.RECEPTOR.PULSE:
            return {
                "effector": Config.EFFECTOR.CONSOLE,
                "message": "Test Message",
            }
        case _:
            return None
