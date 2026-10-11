"""可塑性 v1：釣り合った時刻の差の窓・加算型の痕跡・柔らかい上限・下限（可塑性 v1 の設計案 v0.2）。

ある接続（送り手 S → 受け手 T）について、Pulse の境界で、その Pulse の発火の出来事だけを使って更新する。
読むのは S・T が発火したか、この接続の重みと痕跡、経過時間だけ（接続の状態 仕様 §6.1）。
Delta の中身・Runtime の状態・ほかの接続は読まない。

    T が発火 → 強める：A · x · (w_max − w) / w_max     （x：前の Pulse までの S の痕跡。d ≥ 1）
    S が発火 → 弱める：A · y · w / w_max               （y：前の Pulse までの T の痕跡。d ≤ −1）
    そのあと痕跡を減らし（exp(−Δt/τ_x)）、この Pulse に発火していれば 1 を足す（加算）
同じ Pulse の発火（d = 0）は、前の Pulse までの痕跡だけを使うので数えられない。
"""

import math
from dataclasses import dataclass

from anima_ll.domain.model.manifest import PlasticitySpec


@dataclass(frozen=True)
class PlasticState:
    weight: float
    pre_trace: float = 0.0    # x：送り手の発火の痕跡
    post_trace: float = 0.0   # y：受け手の発火の痕跡


def balanced_pair_window(state: PlasticState, *, pre_fired: bool, post_fired: bool,
                         delta_time: float, spec: PlasticitySpec) -> PlasticState:
    w = state.weight
    potentiation = spec.amplitude * state.pre_trace * (spec.w_max - w) / spec.w_max if post_fired else 0.0
    depression = spec.amplitude * state.post_trace * w / spec.w_max if pre_fired else 0.0
    w = min(spec.w_max, max(spec.w_min, w + potentiation - depression))
    decay = math.exp(-delta_time / spec.trace_tau_seconds)
    return PlasticState(
        weight=w,
        pre_trace=state.pre_trace * decay + (1.0 if pre_fired else 0.0),
        post_trace=state.post_trace * decay + (1.0 if post_fired else 0.0),
    )
