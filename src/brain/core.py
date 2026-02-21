def run(signal):
    match signal.get("receptor"):
        case "pulse":
            return {
                "effector": "console",
                "message": "Test Message",
            }
        case _:
            return None
