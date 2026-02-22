import redis
import speech_recognition
import uuid
from config import Config


class MicrophoneReceptor:
    def __init__(self, signal_queue):
        self.signal_queue = signal_queue
        self.recognizer = speech_recognition.Recognizer()

        # Redis接続
        self.r = redis.Redis(
            host=Config.HOST,
            port=Config.REDIS_PORT_HOST,
            decode_responses=True,
        )

    def run(self):
        with speech_recognition.Microphone() as source:
            # 雑音と声の境界線を引き直す設定
            self.recognizer.adjust_for_ambient_noise(
                source,
                duration=Config.MIC_DURATION,
            )

            while True:
                try:
                    audio = self.recognizer.listen(
                        source,
                        timeout=None,
                        phrase_time_limit=Config.MIC_PHRASE_TIME_LIMIT,
                    )

                    # GoogleのAPIでテキスト化（テスト用）
                    text = self.recognizer.recognize_google(audio, language=Config.LANG)

                    if text:
                        # Redisに一時保存
                        memory_id = f"sensory:mic:{uuid.uuid4()}"
                        self.r.setex(memory_id, Config.MIC_EXPIRY_TIME, text)

                        # IDのみを脊髄に通知
                        signal = {
                            "receptor": Config.RECEPTOR.MICROPHONE,
                            "memory_id": memory_id,
                        }
                        self.signal_queue.put(signal)

                except speech_recognition.UnknownValueError:
                    pass
