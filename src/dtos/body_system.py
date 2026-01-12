from dataclasses import dataclass


@dataclass(frozen=True)
class BodySystemDto:
    """
    PCの客観的なステータス
    """

    # 時刻 (Time: HH:mm:ss)
    t: str

    # 鼓動 (CPU Usage: %)
    c: float

    # 記憶余白 (Available Memory: MB)
    m: int

    def to_kv(self) -> str:
        return f"t:{self.t} c:{self.c} m:{self.m}"
