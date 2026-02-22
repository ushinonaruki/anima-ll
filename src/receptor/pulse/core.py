import time
from config import Config


class PulseReceptor:
    def __init__(self, signal_queue):
        self.signal_queue = signal_queue

    def run(self):
        while True:
            time.sleep(Config.PULSE_INTERVAL)

            signal = {"receptor": Config.RECEPTOR.PULSE}
            self.signal_queue.put(signal)
