"""protocol.yaml（探索の設計 v0.1 の正本）と、0020 の設計図・道具が同じ条件かを機械的に確かめる。

ズレていたら実行・解析を止める。run.py と analyze.py の両方が最初に呼ぶ。
"""

import importlib.util
import itertools
from pathlib import Path

import yaml

from anima_ll.adapter.config.yaml_config_source import parse_neuroarchitecture

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
# これまでに走らせた seed（0012〜0019 の判定・事後の解析・動作確認）と、合成・探索に使った seed
SEEN = (set(range(1, 21)) | set(range(1001, 1021)) | set(range(2001, 2021)) | set(range(3001, 3007))
        | set(range(4001, 4021)) | set(range(5001, 5007)) | set(range(6001, 6021)) | set(range(7001, 7007))
        | set(range(8001, 8021)) | set(range(8101, 8107)) | set(range(9001, 9700))
        | set(range(10001, 10021)) | set(range(10101, 10107)) | set(range(11001, 11021))
        | set(range(11101, 11107)) | set(range(12001, 12021)) | set(range(12101, 12107)))
CHECKS = {"stimulus_counts": True, "input_free_after_experience": True, "identical_before_divergence": True,
          "clone_identity": True, "transplant": True, "replay_history_12000": 1.0e-12,
          "affine_matches_runtime": 1.0e-12, "divergence_reconstruction": True, "revalidate_from_raw": True}


def _world():
    spec = importlib.util.spec_from_file_location("world_0020_for_alignment", HERE / "world.py")
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
    expect(protocol["kind"] == "exploration", "kind が exploration ではない")
    expect(brain["manifest"] == "experiments/0012_passive_world/neuroarchitecture.yaml", "設計図が 0014〜0019 と同じではない")
    raw = W.manifest_raw(protocol)
    base = yaml.safe_load((ROOT / brain["dynamics_from"]).read_text(encoding="utf-8"))
    expect(raw["defaults"]["dynamics"] == base["defaults"]["dynamics"], "設計図の力学が minimal-v3 と違う")
    m = parse_neuroarchitecture(raw)
    units = list(brain["sensory_units"])
    expect({(p.source_id, p.target_id) for p in m.projections if p.source_id in units}
           == set(itertools.permutations(units, 2)), "s のあいだの接続が相互の 6 本ではない")
    expect(all(p.plastic and p.weight == m.plasticity.w_max / 2 for p in m.projections if p.source_id in units),
           "s のあいだの 6 本が、すべて可塑性の対象・初期の重み w_max／2 ではない")
    tl, st = protocol["timeline"], protocol["stimulus"]
    expect(tl["trials"] == {"first": 1, "every": 60, "count": 200}, "試行が 0015 と違う")
    expect((W.experience_end(protocol), W.total_pulses(protocol), W.sample_every(protocol)) == (12000, 24000, 60),
           "経験の終わり・終端・標本の間隔が 12000・24000・60 ではない")
    expect((st["b_offset"], st["c_offset"]) == (2, 30) and st["counts"] == {"A": 200, "B": 200, "C": 200},
           "刺激が 0015 と違う")
    expect(st["rng_shuffle"] == W.RNG_SHUFFLE == W.W15.RNG_SHUFFLE, "順序を崩す乱数の流れの名前が道具と違う")
    expect(st["conditions"] == list(W.CONDITIONS), "条件が ordered・shuffled ではない")
    expect(st["role_assignment"] == W.W15.ROLE_ASSIGNMENT, "役の割り当ての式が道具と違う")
    expect(sorted(map(tuple, st["role_orders"])) == sorted(itertools.permutations(brain["receptors"])),
           "role_orders が Receptor の 6 通りの並べ方ではない")
    iv = protocol["intervention"]
    expect(iv == {"at": W.INTERVENTION_AT, "arms": list(W.ARMS), "rule": W.INTERVENTION_RULE, "new_values": "none"},
           "介入が想定と違う")
    expect(protocol["checks"] == CHECKS, "操作の確認の項目が想定と違う")
    seeds = set(range(protocol["seeds"]["first"], protocol["seeds"]["last"] + 1))
    syn = set(range(protocol["synthetic_seeds"]["first"], protocol["synthetic_seeds"]["last"] + 1))
    expect(len(seeds) == 100, "探索の個体数が 100 ではない")
    expect(not seeds & SEEN and not syn & SEEN and not seeds & syn, "探索・合成の seed が、これまでの seed や互いと重なる")
    if problems:
        raise SystemExit("protocol と 0020 の設計図・道具がずれている：\n- " + "\n- ".join(problems))
