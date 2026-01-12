from dataclasses import dataclass


@dataclass(frozen=True)
class SiteJmaDto:
    """
    日本気象庁から取得したデータ
    """

    # 天気コード (Weather Code)
    w: str

    # 気温 (Temperature Celsius: °C)
    t: str

    # 湿度 (Humidity Percentage: %)
    h: str

    def to_kv(self) -> str:
        return f"w:{self.w} t:{self.t} h:{self.h}"
