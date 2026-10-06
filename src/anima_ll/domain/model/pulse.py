from dataclasses import dataclass

from anima_ll.domain.model.identifiers import PulseNumber


@dataclass(frozen=True)
class PulseContext:
    """1 Pulse の時間情報。全 Unit が同じものを受け取る。

    「時間が経過すること」はここで表す。時間を感覚として知覚することとは別。
    """

    pulse: PulseNumber
    now: float
    """Clock 上の現在時刻（秒）。"""
    delta_time: float
    """前の Pulse からの経過時間（秒）。"""
