import os
from . import post

MODEL_NAME: str = os.environ.get("MODEL_NAME")


def execute(prompt: str) -> str:
    """
    パケットを読み解き、言葉を紡ぐ
    """

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
    }

    result = post.execute(payload)
    return result.get("response", "").strip()
