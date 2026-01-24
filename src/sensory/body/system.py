import os
import psutil
from datetime import datetime
from dtos.body_system import BodySystemDto

BYTES_TO_MB: int = int(os.environ.get("BYTES_TO_MB"))
TIME_FORMAT: str = os.environ.get("TIME_FORMAT")


def execute() -> BodySystemDto:
    """
    PCの内部（身体）の鼓動を感じ取る
    """

    return BodySystemDto(
        t=datetime.now().strftime(TIME_FORMAT),
        c=psutil.cpu_percent(interval=None),
        m=int(psutil.virtual_memory().available / BYTES_TO_MB),
    )
