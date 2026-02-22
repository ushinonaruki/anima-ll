import queue
import threading
from brain import core as brain
from config import Config
from effector import ConsoleEffector
from receptor import PulseReceptor


def run():
    signal_queue = queue.Queue()

    # --- Receptor ---
    threading.Thread(target=PulseReceptor(signal_queue).run, daemon=True).start()

    # --- Effector ---
    console_effector = ConsoleEffector()

    while True:
        signal = signal_queue.get()
        print(f"[Spinal] Receptorからシグナルを受信: {signal}")

        command = brain.run(signal)
        print(f"[Spinal] Brainからコマンドを受信: {command}")

        match command.get("effector"):
            case Config.EFFECTOR.CONSOLE:
                console_effector.run(command)
            case _:
                pass
        print(f"[Spinal] Effectorが反応")

        signal_queue.task_done()
