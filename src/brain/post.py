import os
import requests

OLLAMA_PORT_HOST: int = int(os.environ.get("OLLAMA_PORT_HOST"))


def execute(payload: dict, timeout: float = None) -> dict:
    """
    Ollamaサーバーへパケットを送信する
    """

    url = f"http://localhost:{OLLAMA_PORT_HOST}/api/generate"

    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()
