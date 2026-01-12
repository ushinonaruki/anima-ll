import requests
from common import config


def execute(payload: dict, timeout: float = None) -> dict:
    """
    Ollamaサーバーへパケットを送信する
    """

    url = f"http://localhost:{config.OLLAMA_PORT}/api/generate"

    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()
