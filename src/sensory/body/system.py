import psutil
from datetime import datetime
from common import config
from dtos.body_system import BodySystemDto


def execute() -> BodySystemDto:
    """
    PCの内部（身体）の鼓動を感じ取る
    """

    return BodySystemDto(
        t=datetime.now().strftime(config.TIME_FORMAT),
        c=psutil.cpu_percent(interval=None),
        m=int(psutil.virtual_memory().available / config.BYTES_TO_MB),
    )
