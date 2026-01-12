from . import post
from common import config


def execute(prompt: str) -> str:
    """
    パケットを読み解き、言葉を紡ぐ
    """

    payload = {
        "model": config.MODEL_NAME,
        "prompt": prompt,
        "stream": False,
    }

    result = post.execute(payload)
    return result.get("response", "").strip()
