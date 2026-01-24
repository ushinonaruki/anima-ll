import os
import requests
from dtos.site_jma import SiteJmaDto

REQUEST_TIMEOUT: float = float(os.environ.get("REQUEST_TIMEOUT"))


def execute() -> SiteJmaDto:
    """
    気象庁(JMA) APIから外の世界の情報を「環境感覚」として受け取る
    """

    # エリアコード（デフォルトは東京: 130000）
    # 本来は .env で管理するのが望ましい
    area_code = "130000"
    url = f"https://www.jma.go.jp/bosai/forecast/data/forecast/{area_code}.json"

    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        # JSONから必要な情報を抽出（エリア内の最初の予報値を参照）
        # w: 天気（文字列）, t: 気温（文字列）, h: 湿度（文字列/％）
        report = data[0]["timeSeries"][0]["areas"][0]
        weather_text = report["weathers"][0].replace("　", " ")

        # 気温情報の抽出（時系列データから取得）
        # ※JMA APIは時間帯によってデータ構造が変動するため簡易的な抽出を行う
        temp_report = data[0]["timeSeries"][2]["areas"][0]
        current_temp = temp_report["temps"][0]

        return SiteJmaDto(
            w=weather_text,
            t=current_temp,
            h="--",  # JMA予報JSONには湿度が含まれない場合が多いため、現在は暫定値
        )

    except Exception:
        # 取得失敗時は空の情報を返し、思考を止めない
        return SiteJmaDto(w="不明", t="--", h="--")
