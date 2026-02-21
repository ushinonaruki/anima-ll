import queue
import threading
from brain import core as brain
from effector import ConsoleEffector
from receptor import PulseReceptor


def run():
    signal_queue = queue.Queue()

    # --- Receptor ---
    pulse_receptor = PulseReceptor(signal_queue)
    pulse_thread = threading.Thread(target=pulse_receptor.run, daemon=True)
    pulse_thread.start()

    # --- Effector ---
    console_effector = ConsoleEffector()

    while True:
        signal = signal_queue.get()
        print(f"[Spinal] Receptorからシグナルを受信: {signal}")

        command = brain.run(signal)
        print(f"[Spinal] Brainからコマンドを受信: {command}")

        match command.get("effector"):
            case "console":
                console_effector.run(command)
            case _:
                pass
        print(f"[Spinal] Effectorが反応")

        signal_queue.task_done()
