import os
import playsound
import requests
import tempfile
import time

FISH_SPEECH_PORT_HOST = os.environ.get("FISH_SPEECH_PORT_HOST")


def execute(text: str):
    """
    思考した言葉を「音」として具現化する
    """

    url = f"http://localhost:{FISH_SPEECH_PORT_HOST}/v1/tts"
    payload = {"text": text}
    response = requests.post(url, json=payload)

    # 音声ファイルを一時保存して再生
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        f.write(response.content)
        wav_path = f.name

    playsound.playsound(wav_path)

    # playsoundがファイルを解放するまで待機してから削除
    max_retries = 10
    for i in range(max_retries):
        try:
            os.remove(wav_path)
            break
        except PermissionError:
            if i < max_retries - 1:
                time.sleep(0.1)
            else:
                # 削除できなくても続行
                pass
