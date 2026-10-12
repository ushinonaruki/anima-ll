"""protocol.yaml（事前登録 v0.2 の正本）と、0016 の設計図・道具が同じ条件かを機械的に確かめる。

ズレていたら実行・分析を止める。run.py と analyze.py の両方が最初に呼ぶ。
"""

import importlib.util
import itertools
from pathlib import Path

import yaml

from anima_ll.adapter.config.yaml_config_source import parse_neuroarchitecture

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
# これまでに走らせた seed（0012〜0015 の判定・事後の解析・動作確認）と、0015 の合成専用の seed
SEEN = (set(range(1, 21)) | set(range(1001, 1021)) | set(range(2001, 2021)) | set(range(3001, 3007))
        | set(range(4001, 4021)) | set(range(5001, 5007)) | set(range(6001, 6021)) | set(range(7001, 7007))
        | {9001})


def _world():
    spec = importlib.util.spec_from_file_location("world_0016_for_alignment", HERE / "world.py")
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
    expect(brain["manifest"] == "experiments/0012_passive_world/neuroarchitecture.yaml", "設計図が 0014・0015 と同じではない")
    raw = W.manifest_raw(protocol)
    base = yaml.safe_load((ROOT / brain["dynamics_from"]).read_text(encoding="utf-8"))
    expect(raw["defaults"]["dynamics"] == base["defaults"]["dynamics"], "設計図の力学が minimal-v3 と違う")
    m = parse_neuroarchitecture(raw)
    units = list(brain["sensory_units"])
    expect({(p.source_id, p.target_id) for p in m.projections if p.source_id in units}
           == set(itertools.permutations(units, 2)), "s のあいだの接続が相互の 6 本ではない")
    expect(all(p.plastic and p.weight == m.plasticity.w_max / 2 for p in m.projections if p.source_id in units),
           "s のあいだの 6 本が、すべて可塑性の対象・初期の重み w_max／2 ではない（組の和の不変量の前提）")

    tl, st = protocol["timeline"], protocol["stimulus"]
    expect(tl["trials"] == {"first": 1, "every": 60, "count": 200}, "試行が 0014・0015 と違う")
    expect((W.experience_end(protocol), W.endpoint(protocol)) == (12000, 24000), "経験の終わり・終端が 12000・24000 ではない")
    expect(W.probe_times(protocol) == list(range(24001, 24301)), "試しの時刻が 24001〜24300 ではない")
    expect(W.total_pulses(protocol) == 24300, "総 Pulse が 24300 ではない")
    expect(tl["probes"]["every"] == 1, "試しが毎 Pulse ではない")
    expect((st["b_offset"], st["c_offset"]) == (2, 30), "b_offset・c_offset が 0014・0015 と違う")
    expect(st["counts"] == {"A": 200, "B": 200, "C": 200}, "A・B・C の数が 200 ずつではない")
    expect(st["conditions"] == ["ordered"], "条件が順序ありだけではない")
    expect(st["role_assignment"] == W.W14.ROLE_ASSIGNMENT, "役の割り当ての式が道具と違う")
    expect(sorted(map(tuple, st["role_orders"])) == sorted(itertools.permutations(brain["receptors"])),
           "role_orders が Receptor の 6 通りの並べ方ではない")
    expect(protocol["probe"] == {"read_at": 2, "fork_after": 0}, "試しの読み出し・分ける時点が 0014 v0.3 と違う")
    iv = protocol["intervention"]
    expect(iv["arms"] == ["as_is", "equalized"] and iv["rule"] == W.W14.INTERVENTION_RULE, "介入が 0014 v0.3 と違う")

    j = protocol["judgment"]
    expect(j["primary"] == "s", "主の判定が s ではない")
    expect(j["s"] == {"statistic": "sum_t0(E(t0))", "passes_if": "> 0"}, "s の定義が想定と違う")
    expect(j["applies_to"] == "all_individuals", "適用対象がすべての個体ではない")
    expect(0 < j["min_fraction"] <= 1, "min_fraction が 0〜1 にない")
    expect(j["manipulation"] == {
        "stimulus_counts": True, "input_free_after_experience": True, "clone_identity": True,
        "equalized_clone": True, "probe_input_delivered": True, "arms_identical_until_divergence": True,
        "replay_matches_recorded_weights": 1.0e-12, "revalidate_from_raw": True,
        "no_statistics_when_invalid": True}, "操作の確認の項目が想定と違う")

    formal = set(range(protocol["seeds"]["first"], protocol["seeds"]["last"] + 1))
    smoke = set(range(protocol["smoke"]["seeds"]["first"], protocol["smoke"]["seeds"]["last"] + 1))
    expect(not formal & SEEN, "判定の seed が、これまでに走らせた seed と重なる")
    expect(not smoke & SEEN, "動作確認の seed が、これまでに走らせた seed と重なる")
    expect(not formal & smoke, "判定の seed と動作確認の seed が重なる")
    expect(protocol["smoke"]["checks"] == {"manipulation": "all"}, "動作確認の確認が操作の確認すべてではない")
    expect(protocol["smoke"]["hide"] == ["E", "s"], "動作確認で隠す量が E・s ではない")
    expect(protocol["smoke"]["on_failure"] == "stop_and_amend", "動作確認が落ちたときの扱いが stop_and_amend ではない")

    if problems:
        raise SystemExit("protocol と 0016 の設計図・道具がずれている：\n- " + "\n- ".join(problems))
