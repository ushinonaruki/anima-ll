"""実験 0012 v0.3 の動作確認 S2 の根拠 T_min の契約テスト（README §5.5）。

T_min ＝ 発火して activity が 0 に戻った Unit が、入力なしで次に発火できる最短の Pulse 数。
出生時のばらつきの範囲で最も速く戻る個体（内在的駆動が最大・閾値が最小）で、順応 0 として決まる。
README は minimal-v3 で T_min ＝ 9 とした。ここでは式ではなく、本体と同じ組み立て
（build_application → PulseRuntime → GenericCognitiveUnit → SimpleActivityDynamics、FixedStepClock）で、
1 Pulse の更新の順番そのものに対して確かめる：

- 最速の個体・順応なし：発火のあと、間隔 1〜8 では一度も再発火せず、間隔 9 で初めて再発火する
- ばらつきの範囲の 4 つの角と内側の点、順応あり（minimal-v3 の α・τ_a）：間隔が 9 未満になることがない

判定の seed は使わない（ばらつきは設計図の jitter を 0 にして、角の値を直接書く）。
"""

import asyncio
import copy
import itertools
import math
from pathlib import Path

import pytest
import yaml

from anima_ll.adapter.clock.fixed_step_clock import FixedStepClock
from anima_ll.adapter.config.yaml_config_source import (
    parse_birth_state,
    parse_environment,
    parse_neuroarchitecture,
)
from anima_ll.adapter.persistence.in_memory_event_log import InMemoryEventLog
from anima_ll.bootstrap import build_application

ROOT = Path(__file__).resolve().parents[2]
V3 = yaml.safe_load((ROOT / "config/neuroarchitecture/minimal-v3.yaml").read_text(encoding="utf-8"))
DYN = V3["defaults"]["dynamics"]
PULSES = 3000
README_T_MIN = 9   # experiments/0012_passive_world/README.md §5.5 の値


def closed_form_t_min() -> int:
    """最速の出生（駆動 × (1 ＋ jitter)、閾値 × (1 − jitter)）・順応 0 で、0 から閾値に届くまでの Pulse 数（Δt ＝ 1）。"""
    lam, j = DYN["decay"], DYN["jitter"]
    drive, threshold = DYN["intrinsic_drive"] * (1 + j), DYN["threshold"] * (1 - j)
    return math.ceil(math.log(1 - threshold * (1 - lam) / drive) / math.log(lam))


def fire_pulses(drive_factor: float, threshold_factor: float, *, adaptation: bool) -> list[int]:
    """jitter 0 で、閾値・駆動をばらつきの点の値にした 1 Unit を、入力なしで本体と同じ経路で動かし、発火の Pulse を返す。"""
    dyn = copy.deepcopy(DYN)
    dyn["jitter"] = 0.0
    dyn["intrinsic_drive"] = DYN["intrinsic_drive"] * drive_factor
    dyn["threshold"] = DYN["threshold"] * threshold_factor
    if not adaptation:
        dyn["adaptation_increment"] = 0.0
        dyn["adaptation_tau"] = 0.0
    manifest = {"version": 3, "delta_ttl_pulses": V3["delta_ttl_pulses"],
                "interfaces": {"resources": [], "receptors": [], "effectors": []},
                "defaults": {"dynamics": dyn},
                "units": [{"id": "u0", "output": "relay"}], "projections": []}
    log = InMemoryEventLog()
    app = build_application(
        parse_neuroarchitecture(manifest),
        parse_environment({"runtime": {"pulse_interval_seconds": 1.0}}),
        parse_birth_state({"individual_id": "t-min", "seed": 1}),
        clock=FixedStepClock(1.0), event_log=log,
    )
    asyncio.run(app.lifecycle.run(max_pulses=PULSES))
    return [e.pulse for e in log.events if e.type == "activity"]


def intervals(pulses: list[int]) -> list[int]:
    return [b - a for a, b in zip(pulses, pulses[1:])]


def test_closed_form_matches_the_value_in_the_readme() -> None:
    assert closed_form_t_min() == README_T_MIN


def test_fastest_birth_without_adaptation_refires_first_at_exactly_t_min() -> None:
    j = DYN["jitter"]
    fires = fire_pulses(1 + j, 1 - j, adaptation=False)
    gaps = intervals(fires)
    assert len(gaps) > 100                       # 自発発火が続いている
    assert min(gaps) == README_T_MIN             # 1〜8 は一度もなく、9 が実際に起きる
    assert set(gaps) == {README_T_MIN}           # 順応なし・入力なしなので周期は一定


@pytest.mark.parametrize("adaptation", [False, True])
@pytest.mark.parametrize("drive_j, threshold_j", list(itertools.product((-1.0, -0.5, 0.0, 0.5, 1.0), repeat=2)))
def test_no_birth_in_the_jitter_range_refires_faster_than_t_min(drive_j, threshold_j, adaptation) -> None:
    j = DYN["jitter"]
    fires = fire_pulses(1 + drive_j * j, 1 + threshold_j * j, adaptation=adaptation)
    gaps = intervals(fires)
    assert all(g >= README_T_MIN for g in gaps), (drive_j, threshold_j, adaptation, min(gaps))
