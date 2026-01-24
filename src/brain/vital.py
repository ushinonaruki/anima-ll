import os
from . import post

MODEL_NAME: str = os.environ.get("MODEL_NAME")


def execute():
    """
    VRAMの活性化を実行する
    """

    payload = {"model": MODEL_NAME, "prompt": ".", "keep_alive": "24h"}
    try:
        post.execute(payload, timeout=60.0)
    except:
        pass
