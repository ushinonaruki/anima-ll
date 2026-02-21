import time


class PulseReceptor:
    def __init__(self, signal_queue):
        self.signal_queue = signal_queue
        self.interval = 10

    def run(self):
        while True:
            time.sleep(self.interval)

            signal = {"receptor": "pulse"}
            self.signal_queue.put(signal)
