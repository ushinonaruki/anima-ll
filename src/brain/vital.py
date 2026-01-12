from . import post
from common import config


def execute():
    """
    VRAMの活性化を実行する
    """

    payload = {"model": config.MODEL_NAME, "prompt": ".", "keep_alive": "24h"}
    try:
        post.execute(payload, timeout=60.0)
    except:
        pass
