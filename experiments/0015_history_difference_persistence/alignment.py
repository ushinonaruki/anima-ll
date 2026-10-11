"""protocol.yaml（事前登録 v0.2 の正本）と、0015 の設計図・道具が同じ条件かを機械的に確かめる。

ズレていたら実行・分析を止める。run.py と analyze.py の両方が最初に呼ぶ。
"""

import importlib.util
import itertools
from pathlib import Path

import yaml

from anima_ll.adapter.config.yaml_config_source import parse_neuroarchitecture

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
# これまでに走らせた seed（0012〜0014 の判定・事後の解析・動作確認）
SEEN = (set(range(1, 21)) | set(range(1001, 1021)) | set(range(2001, 2021)) | set(range(3001, 3007))
        | set(range(4001, 4021)) | set(range(5001, 5007)))


def _world():
    spec = importlib.util.spec_from_file_location("world_0015_for_alignment", HERE / "world.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(protocol: dict) -> None:
    problems: list[str] = []

    def expect(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    W = _world()
    brain = protocol["brain"]
    expect(brain["manifest"] == "experiments/0012_passive_world/neuroarchitecture.yaml", "設計図が 0012 v0.3（0014 と同じ）ではない")
    raw = W.manifest_raw(protocol)
    base = yaml.safe_load((ROOT / brain["dynamics_from"]).read_text(encoding="utf-8"))
    expect(raw["defaults"]["dynamics"] == base["defaults"]["dynamics"], "設計図の力学が minimal-v3 と違う")
    m = parse_neuroarchitecture(raw)
    units = list(brain["sensory_units"])
    expect([u.unit_id for u in m.units] == units, "Unit が protocol の sensory_units と違う")
    expect({(p.source_id, p.target_id) for p in m.projections if p.source_id in units}
           == set(itertools.permutations(units, 2)), "s のあいだの接続が相互の 6 本ではない")
    expect(all(p.plastic and p.weight == m.plasticity.w_max / 2 for p in m.projections if p.source_id in units),
           "s のあいだの 6 本が、すべて可塑性の対象・初期の重み w_max／2 ではない（組の和の不変量の前提）")
    expect({(p.source_id, p.target_id) for p in m.projections if p.source_id not in units}
           == set(brain["receptors"].items()), "Receptor → s の接続が protocol の receptors と違う")

    tl, st = protocol["timeline"], protocol["stimulus"]
    trials = tl["trials"]
    expect(trials == {"first": 1, "every": 60, "count": 200}, "試行が 0014 と違う")
    end, total = W.experience_end(protocol), W.total_pulses(protocol)
    expect(end == 12000 and total == 24000, "経験の終わり・総 Pulse が 12000・24000 ではない")
    expect(W.sample_every(protocol) == trials["every"], "標本の間隔が試行の間隔ではない")
    last = max(t for t, _ in W.ordered_stimuli(protocol))
    expect(last < end, "最後の経験の刺激が経験の終わりより後")
    expect((st["b_offset"], st["c_offset"]) == (2, 30), "b_offset・c_offset が 0014 と違う")
    expect(st["counts"] == {r: trials["count"] for r in W.ROLES}, "A・B・C の数が試行の数と揃っていない")
    expect(st["rng_shuffle"] == W.RNG_SHUFFLE, "順序を崩す乱数の流れが道具と違う")
    expect(st["role_assignment"] == W.ROLE_ASSIGNMENT, "役の割り当ての式が道具と違う")
    expect(sorted(map(tuple, st["role_orders"])) == sorted(itertools.permutations(brain["receptors"])),
           "role_orders が Receptor の 6 通りの並べ方ではない")
    expect(st["conditions"] == ["ordered", "shuffled"], "条件が ordered・shuffled ではない")

    j = protocol["judgment"]
    expect(j["primary"] == "p", "主の判定が p ではない")
    expect(j["p"] == {"statistic": "sign(D0) * DT", "passes_if": "> 0"}, "p の定義が想定と違う")
    expect(j["applies_to"] == "D0 != 0", "適用対象が D0 ≠ 0 ではない")
    expect(j["denominator"] == "applicable_individuals", "分母が適用対象の個体ではない")
    expect(0 < j["min_fraction"] <= 1, "min_fraction が 0〜1 にない")
    expect(j["manipulation"] == {
        "stimulus_counts": True, "input_free_after_experience": True, "identical_before_divergence": True,
        "replay_matches_recorded_weights": 1.0e-12, "revalidate_from_raw": True,
        "no_statistics_when_invalid": True}, "操作の確認の項目が想定と違う")

    formal = set(range(protocol["seeds"]["first"], protocol["seeds"]["last"] + 1))
    smoke = set(range(protocol["smoke"]["seeds"]["first"], protocol["smoke"]["seeds"]["last"] + 1))
    expect(not formal & SEEN, "判定の seed が、これまでに走らせた seed と重なる")
    expect(not smoke & SEEN, "動作確認の seed が、これまでに走らせた seed と重なる")
    expect(not formal & smoke, "判定の seed と動作確認の seed が重なる")
    expect(protocol["smoke"]["checks"] == {"manipulation": "all"}, "動作確認の確認が操作の確認すべてではない")
    expect(protocol["smoke"]["hide"] == ["p"], "動作確認で隠す量が p ではない")
    expect(protocol["smoke"]["on_failure"] == "stop_and_amend", "動作確認が落ちたときの扱いが stop_and_amend ではない")

    if problems:
        raise SystemExit("protocol と 0015 の設計図・道具がずれている：\n- " + "\n- ".join(problems))
