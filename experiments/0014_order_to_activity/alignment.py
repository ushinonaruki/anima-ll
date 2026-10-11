"""protocol.yaml（事前登録 v0.3 の正本）と、0014 の設計図・道具が同じ条件かを機械的に確かめる。

ズレていたら実行・分析を止める。run.py と analyze.py の両方が最初に呼ぶ。
"""

import importlib.util
import itertools
from pathlib import Path

import yaml

from anima_ll.adapter.config.yaml_config_source import parse_neuroarchitecture

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
# これまでに走らせた seed（0012 の判定・事後の解析、0013 の判定・動作確認）
SEEN = set(range(1, 21)) | set(range(1001, 1021)) | set(range(2001, 2021)) | set(range(3001, 3007))


def _world():
    spec = importlib.util.spec_from_file_location("world_0014_for_alignment", HERE / "world.py")
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
    expect(brain["manifest"] == "experiments/0012_passive_world/neuroarchitecture.yaml", "設計図が 0012 v0.3 のものではない")
    raw = W.manifest_raw(protocol)
    base = yaml.safe_load((ROOT / brain["dynamics_from"]).read_text(encoding="utf-8"))
    expect(raw["defaults"]["dynamics"] == base["defaults"]["dynamics"], "設計図の力学が minimal-v3 と違う")
    m = parse_neuroarchitecture(raw)
    units = list(brain["sensory_units"])
    expect([u.unit_id for u in m.units] == units, "Unit が protocol の sensory_units と違う")
    inter = {(p.source_id, p.target_id) for p in m.projections if p.source_id in units}
    expect(inter == set(itertools.permutations(units, 2)), "s のあいだの接続が相互の 6 本ではない")
    expect(all(p.plastic and p.weight == m.plasticity.w_max / 2 for p in m.projections if p.source_id in units),
           "s のあいだの 6 本が、すべて可塑性の対象・初期の重み w_max／2 ではない（組の和の不変量の前提）")
    expect({(p.source_id, p.target_id) for p in m.projections if p.source_id not in units}
           == set(brain["receptors"].items()), "Receptor → s の接続が protocol の receptors と違う")
    expect(not any(p.plastic for p in m.projections if p.source_id not in units), "Receptor → s が可塑性の対象")

    tl, st, pr = protocol["timeline"], protocol["stimulus"], protocol["probe"]
    trials, probes = tl["trials"], tl["probes"]
    expect(trials["first"] == 1, "経験が Pulse 1 から始まっていない")
    expect(probes["first"] == trials["first"] + trials["count"] * trials["every"], "試しの開始が次の（来ない）A の時刻ではない")
    expect(probes["every"] == 1, "試しが毎 Pulse ではない")
    expect(probes["count"] == W.PROBE_COUNT, "試しの数の式が道具と違う")
    n = W.probe_count(protocol)
    expect(tl["total_pulses"] == probes["first"] + n - 1, "総 Pulse が最後の試しの時刻ではない")
    last_stimulus = trials["first"] + (trials["count"] - 1) * trials["every"] + st["c_offset"]
    expect(last_stimulus < probes["first"] - 1, "最後の経験の刺激が W_post の時刻より後")
    expect(0 < st["b_offset"] < st["c_offset"] < trials["every"], "b_offset・c_offset が試行の中にない")
    expect(2 * st["c_offset"] == trials["every"], "c_offset が試行の間隔の半分ではない")
    expect(st["counts"] == {r: trials["count"] for r in W.ROLES}, "A・B・C の数が試行の数と揃っていない")
    expect(st["rng_shuffle"] == W.RNG_SHUFFLE, "順序を崩す乱数の流れが道具と違う")
    expect(st["role_assignment"] == W.ROLE_ASSIGNMENT, "役の割り当ての式が道具と違う")
    expect(sorted(map(tuple, st["role_orders"])) == sorted(itertools.permutations(brain["receptors"])),
           "role_orders が Receptor の 6 通りの並べ方ではない")
    expect(st["conditions"] == ["ordered", "shuffled"], "条件が ordered・shuffled ではない")
    expect(pr == {"read_at": 2, "fork_after": 0}, "試しの読み出し・分ける時点が v0.3 と違う")

    iv = protocol["intervention"]
    expect(iv["arms"] == ["as_is", "equalized"], "介入の腕が as_is・equalized ではない")
    expect(iv["rule"] == W.INTERVENTION_RULE, "介入の規則の名前が道具と違う")

    j = protocol["judgment"]
    expect(j["primary"] == "p", "主の判定が p ではない")
    expect(j["p"] == {"statistic": "mean_t0(sign(W_probe(t0)) * delta_R(t0))", "passes_if": "> 0",
                      "condition": "ordered"}, "p の定義が想定と違う")
    expect(j["w"] == {"statistic": "W_post", "passes_if": "ordered > shuffled"}, "w の定義が想定と違う")
    expect(0 < j["min_fraction"] <= 1, "min_fraction が 0〜1 にない")
    expect(j["manipulation"] == {
        "stimulus_counts": True, "identical_before_divergence": True, "clone_identity": True,
        "equalized_clone": True, "probe_input_delivered": True, "arms_identical_until_divergence": True,
        "revalidate_from_raw": True, "no_statistics_when_invalid": True}, "操作の確認の項目が想定と違う")

    formal = set(range(protocol["seeds"]["first"], protocol["seeds"]["last"] + 1))
    smoke = set(range(protocol["smoke"]["seeds"]["first"], protocol["smoke"]["seeds"]["last"] + 1))
    expect(not formal & SEEN, "判定の seed が、これまでに走らせた seed と重なる")
    expect(not smoke & SEEN, "動作確認の seed が、これまでに走らせた seed と重なる")
    expect(not formal & smoke, "判定の seed と動作確認の seed が重なる")
    expect(protocol["smoke"]["checks"] == {"manipulation": "all"}, "動作確認の確認が操作の確認すべてではない")
    expect(protocol["smoke"]["hide"] == ["p", "w"], "動作確認で隠す量が p・w ではない")
    expect(protocol["smoke"]["on_failure"] == "stop_and_amend", "動作確認が落ちたときの扱いが stop_and_amend ではない")

    if problems:
        raise SystemExit("protocol と 0014 の設計図・道具がずれている：\n- " + "\n- ".join(problems))
