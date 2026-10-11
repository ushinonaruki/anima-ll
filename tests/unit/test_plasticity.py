"""可塑性 v1 の規則と接続の状態の単体テスト（可塑性 v1 の設計案 v0.2 §2・3・6、尺度は v1.1）。"""

import copy
import math
import random

import pytest

from anima_ll.adapter.config.yaml_config_source import ConfigError, parse_neuroarchitecture
from anima_ll.domain.model.manifest import PlasticitySpec
from anima_ll.neuroarchitecture.connections import ConnectionStore
from anima_ll.neuroarchitecture.plasticity import PlasticState, balanced_pair_window

TAU = -1.0 / math.log(0.85)
SPEC = PlasticitySpec(rule="balanced_pair_window", trace="additive", bounds="soft",
                      trace_tau_seconds=TAU, w_min=0.0, w_max=0.5, amplitude=0.005)


def run(events: dict[int, set[str]], pulses: int, w: float = 0.25) -> PlasticState:
    """events[p] は Pulse p に発火した側（'pre'・'post'）。"""
    state = PlasticState(weight=w)
    for p in range(1, pulses + 1):
        fired = events.get(p, set())
        state = balanced_pair_window(state, pre_fired="pre" in fired, post_fired="post" in fired,
                                     delta_time=1.0, spec=SPEC)
    return state


def test_pre_before_post_potentiates_with_window_value() -> None:
    w0 = 0.25
    for d in (1, 2, 5):
        s = run({1: {"pre"}, 1 + d: {"post"}}, 1 + d, w0)
        k = SPEC.amplitude * math.exp(-(d - 1) / TAU)            # K(d) ＝ A·exp(−(d−1)Δt/τ)
        assert s.weight == pytest.approx(w0 + k * (SPEC.w_max - w0) / SPEC.w_max)


def test_post_before_pre_depresses_with_the_same_size() -> None:
    w0 = 0.25
    s = run({1: {"post"}, 3: {"pre"}}, 3, w0)
    k = SPEC.amplitude * math.exp(-1 / TAU)
    assert s.weight == pytest.approx(w0 - k * w0 / SPEC.w_max)


def test_same_pulse_firing_does_not_change_the_weight() -> None:
    assert run({5: {"pre", "post"}}, 5).weight == 0.25


def test_trace_is_additive() -> None:
    s = run({1: {"pre"}, 2: {"pre"}}, 2)
    assert s.pre_trace == pytest.approx(math.exp(-1 / TAU) + 1.0)   # 1 にリセットではなく足し上げる


def test_soft_bounds_keep_the_weight_inside() -> None:
    events = {p: ({"pre"} if p % 2 else {"post"}) for p in range(1, 4000)}
    s = run(events, 4000, 0.49)
    assert 0.0 <= s.weight <= SPEC.w_max
    events = {p: ({"post"} if p % 2 else {"pre"}) for p in range(1, 4000)}
    assert 0.0 <= run(events, 4000, 0.01).weight <= SPEC.w_max


def test_independent_firing_with_different_rates_does_not_drift_from_half_w_max() -> None:
    """釣り合いの確認：互いに独立に、違う頻度で発火する 2 つの Unit では、重みは w_max/2 の近くに留まる。

    比較として、送り手がいつも受け手の 1 Pulse 前に発火する（順序の偏りがある）ときは大きく動く。
    """
    rng = random.Random(7)
    pulses = 60000
    events = {}
    for p in range(1, pulses + 1):
        fired = set()
        if rng.random() < 0.15:
            fired.add("pre")
        if rng.random() < 0.04:
            fired.add("post")
        events[p] = fired
    independent = run(events, pulses).weight
    ordered = run({p: ({"pre"} if p % 20 == 0 else {"post"} if p % 20 == 1 else set())
                   for p in range(1, 4001)}, 4000).weight
    assert abs(independent - 0.25) < 0.03
    assert ordered - 0.25 > 0.15


# ---- 接続の状態 ----------------------------------------------------------------------

BRAIN = {
    "version": 0, "delta_ttl_pulses": 10,
    "interfaces": {"resources": [], "receptors": ["receptor.x1"], "effectors": []},
    "defaults": {"dynamics": {"kind": "simple_activity", "decay": 0.85, "threshold": 0.5,
                              "refractory_pulses": 0, "intrinsic_drive": 0.08, "jitter": 0.1,
                              "initial_activity_max_ratio": 0.5,
                              "adaptation_increment": 0.01, "adaptation_tau": 300}},
    "units": [{"id": "s1", "output": "relay"}, {"id": "s2", "output": "relay"}],
    "projections": [
        {"from": "receptor.x1.main", "to": "s1", "weight": 1.0},
        {"from": "s1.main", "to": "s2", "weight": 0.005, "plastic": True},
        {"from": "s2.main", "to": "s1", "weight": 0.005, "plastic": True},
    ],
    "plasticity": {"rule": "balanced_pair_window", "trace": "additive", "bounds": "soft",
                   "trace_tau": "activity_time_constant", "w_min": 0.0, "w_max": "adaptation_increment",
                   "amplitude_ratio": 0.01},
}


def test_symbols_are_resolved_from_the_shared_dynamics() -> None:
    spec = parse_neuroarchitecture(copy.deepcopy(BRAIN)).plasticity
    assert spec.trace_tau_seconds == pytest.approx(TAU)
    assert spec.w_max == 0.01 and spec.amplitude == pytest.approx(0.0001)   # v1.1：w_max ＝ α


@pytest.mark.parametrize("mutate, message", [
    (lambda b: b.pop("plasticity"), "plasticity"),
    (lambda b: b["projections"][0].update(plastic=True), "Unit どうし"),
    (lambda b: b["projections"][1].update(weight=0.02), "外"),
    # v1.1：w_max ＝ θ は廃止。α がない（0・未記入）設計図では adaptation_increment の尺度もない
    (lambda b: b["plasticity"].update(w_max="threshold"), "廃止"),
    (lambda b: b["defaults"]["dynamics"].update(adaptation_increment=0.0), "順応"),
    (lambda b: b["defaults"]["dynamics"].pop("adaptation_increment"), "adaptation_increment"),
    (lambda b: b["units"][1].update(dynamics={"adaptation_increment": 0.02}), "adaptation_increment"),
    (lambda b: b["units"][0].update(dynamics={"decay": 0.9}), "decay"),
    (lambda b: b["plasticity"].pop("amplitude_ratio"), "amplitude_ratio"),
    (lambda b: b["plasticity"].update(amplitude_ratio=-0.01), "amplitude_ratio"),
    (lambda b: b["plasticity"].update(amplitude_ratio=0.0), "amplitude_ratio"),
    (lambda b: b["plasticity"].update(amplitude_ratio=float("nan")), "amplitude_ratio"),
    (lambda b: b["plasticity"].update(amplitude_ratio=float("inf")), "amplitude_ratio"),
    (lambda b: b["plasticity"].update(trace_tau=float("inf")), "有限"),
    (lambda b: b["plasticity"].update(w_max=float("nan"), w_min=0.0), "有限"),
    (lambda b: b["defaults"]["dynamics"].update(decay=1.0), "decay"),
    (lambda b: b["projections"][1].update(weight=float("nan")), "有限"),
    # 同じ (送り手, 出力路, 受け手) の接続を 2 本書く。"s1" と "s1.main" は同じ出力路
    (lambda b: b["projections"].append({"from": "s1", "to": "s2", "weight": 0.005, "plastic": True}), "重複"),
    (lambda b: b["projections"].append({"from": "s1.main", "to": "s2", "weight": 0.005}), "重複"),
])
def test_invalid_plasticity_configs_are_rejected(mutate, message) -> None:
    brain = copy.deepcopy(BRAIN)
    mutate(brain)
    with pytest.raises(ConfigError, match=message):
        parse_neuroarchitecture(brain)


def test_order_of_fired_units_does_not_matter() -> None:
    manifest = parse_neuroarchitecture(copy.deepcopy(BRAIN))
    a, b = ConnectionStore(manifest), ConnectionStore(manifest)
    for fired in (["s1"], ["s2", "s1"], ["s2"], [], ["s1", "s2"]):
        a.apply_activity(fired, 1.0)
        b.apply_activity(list(reversed(fired)), 1.0)
    assert a.export_state() == b.export_state()


def test_export_and_import_continue_the_same_life_history() -> None:
    manifest = parse_neuroarchitecture(copy.deepcopy(BRAIN))
    a = ConnectionStore(manifest)
    for fired in (["s1"], ["s2"], ["s1"], ["s2"]):
        a.apply_activity(fired, 1.0)
    b = ConnectionStore(manifest)
    b.import_state(a.export_state())
    for fired in (["s1"], [], ["s2"]):
        a.apply_activity(fired, 1.0)
        b.apply_activity(fired, 1.0)
    assert a.export_state() == b.export_state()
    assert dict(a.weights()) == dict(b.weights())


def test_weights_snapshot_is_frozen() -> None:
    store = ConnectionStore(parse_neuroarchitecture(copy.deepcopy(BRAIN)))
    snapshot = store.weights()
    with pytest.raises(TypeError):
        snapshot[("s1", "main", "s2")] = 0.4   # type: ignore[index]
    store.apply_activity(["s1"], 1.0)
    store.apply_activity(["s2"], 1.0)
    assert snapshot[("s1", "main", "s2")] == 0.005       # 写しは後の更新で変わらない
    assert store.weights()[("s1", "main", "s2")] != 0.005


def test_reciprocal_pair_sum_is_conserved_from_half_w_max() -> None:
    """可塑性 v1.1 §8：w(i→j) ＋ w(j→i) は、w0 ＝ w_max／2 の 2 本から始めれば w_max のまま保たれる（同時発火も含む）。"""
    manifest = parse_neuroarchitecture(copy.deepcopy(BRAIN))
    store = ConnectionStore(manifest)
    w_max = manifest.plasticity.w_max
    rng = random.Random(7)
    for _ in range(5000):
        fired = [u for u in ("s1", "s2") if rng.random() < 0.3]
        store.apply_activity(fired, 1.0)
        w = store.weights()
        assert w[("s1", "main", "s2")] + w[("s2", "main", "s1")] == pytest.approx(w_max, abs=1e-15)
    assert store.weights()[("s1", "main", "s2")] != manifest.plasticity.w_max / 2   # 実際に動いている


def test_reciprocal_pair_sum_is_conserved_even_when_an_update_is_clipped_at_the_bounds() -> None:
    """切り詰めの前の 2 本は補数（z と w_max − z）なので、clip(z) ＋ clip(w_max − z) ＝ w_max（可塑性 v1.1 §8）。"""
    w_max = 0.01
    big = PlasticitySpec(rule="balanced_pair_window", trace="additive", bounds="soft",
                         trace_tau_seconds=TAU, w_min=0.0, w_max=w_max, amplitude=3 * w_max)   # 1 回で範囲を越える振幅
    ij = PlasticState(weight=0.009, pre_trace=2.0, post_trace=0.0)    # i → j（送り手 i の痕跡 2）
    ji = PlasticState(weight=0.001, pre_trace=0.0, post_trace=2.0)    # j → i（受け手 i の痕跡 2）
    raw_ij = ij.weight + big.amplitude * ij.pre_trace * (w_max - ij.weight) / w_max
    assert raw_ij > w_max                                              # 切り詰めの前は上限を越えている
    ij2 = balanced_pair_window(ij, pre_fired=False, post_fired=True, delta_time=1.0, spec=big)   # j が発火
    ji2 = balanced_pair_window(ji, pre_fired=True, post_fired=False, delta_time=1.0, spec=big)
    assert (ij2.weight, ji2.weight) == (w_max, 0.0)                    # 片方は上限、もう片方は下限に同時に当たる
    assert ij2.weight + ji2.weight == pytest.approx(w_max, abs=1e-18)
