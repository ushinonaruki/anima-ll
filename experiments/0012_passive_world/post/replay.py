"""可塑性 v1.1 の規則を、保存した発火の記録から計算し直し、重みの変化を「組」に分けて帰属させる（事後の解析用）。

規則（src/anima_ll/neuroarchitecture/plasticity.py）と同じ順番で計算する：
  Pulse p で T が発火 → 強める A · x · (w_max − w)/w_max（x は p − 1 の終わりの S の痕跡）
  Pulse p で S が発火 → 弱める A · y · w/w_max（y は p − 1 の終わりの T の痕跡）
  そのあと痕跡に exp(−Δt/τ) を掛け、p に発火していれば 1 を足す
痕跡は過去の発火の和なので、S の発火 p_k の寄与は K(d) ＝ exp(−(d − 1)Δt/τ)、d ＝ p − p_k。
強める量・弱める量を、どの過去の発火（どの d）から来たかに比例して分ける。
"""

import math
from collections import defaultdict
from collections.abc import Callable, Iterable


def replay(pre_spikes: Iterable[int], post_spikes: Iterable[int], *, w0: float, w_max: float,
           amplitude: float, tau: float, dt: float, end: int,
           classify: Callable[[str, int, int], str] | None = None) -> tuple[float, dict[str, float]]:
    """S（pre）→ T（post）の 1 本の接続を、Pulse 1〜end で計算し直す。

    返す値：(最後の重み, {分類: その分類に帰属した Δw の合計})。
    classify(kind, p, p_k)：kind は "pot"（T が p に発火、S の過去の発火 p_k との組）か
    "dep"（S が p に発火、T の過去の発火 p_k との組）。省略すると d で分類する。
    """
    pre, post = set(pre_spikes), set(post_spikes)
    pre_hist: list[int] = []
    post_hist: list[int] = []
    w = w0
    parts: dict[str, float] = defaultdict(float)
    decay = math.exp(-dt / tau)
    cutoff = 40 * tau / dt   # これより古い発火の寄与は e^{-40} 未満なので数えない

    def contributions(hist: list[int], p: int) -> list[tuple[int, float]]:
        return [(pk, decay ** (p - pk - 1)) for pk in hist if p - pk <= cutoff]

    def label(kind: str, p: int, pk: int) -> str:
        return classify(kind, p, pk) if classify else f"{kind} d={p - pk}"

    for p in range(1, end + 1):
        pot = dep = 0.0
        pot_parts: list[tuple[str, float]] = []
        dep_parts: list[tuple[str, float]] = []
        if p in post:
            cs = contributions(pre_hist, p)
            x = sum(c for _, c in cs)
            if x > 0:
                pot = amplitude * x * (w_max - w) / w_max
                pot_parts = [(label("pot", p, pk), pot * c / x) for pk, c in cs]
        if p in pre:
            cs = contributions(post_hist, p)
            y = sum(c for _, c in cs)
            if y > 0:
                dep = amplitude * y * w / w_max
                dep_parts = [(label("dep", p, pk), -dep * c / y) for pk, c in cs]
        new = min(w_max, max(0.0, w + pot - dep))
        if new != w + pot - dep:
            raise RuntimeError("上限・下限に当たった（この解析は当たらない場合だけを扱う）")
        w = new
        for k, v in pot_parts + dep_parts:
            parts[k] += v
        if p in pre:
            pre_hist.append(p)
        if p in post:
            post_hist.append(p)
    return w, dict(parts)
