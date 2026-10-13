"""protocol.yaml（事前登録 v0.1 の正本）と、0021 の設計図・道具が同じ条件かを機械的に確かめる。

ズレていたら実行・解析を止める。run.py と analyze.py の両方が最初に呼ぶ。
実験の ID は、このフォルダの名前の先頭（"0021_yoked_plasticity" → "0021"）から決め、protocol の experiment・
execution（ID・出力先・protocol のパス）・乱数の流れの名前がそれと一致することを確かめる（README §7.1）。
"""

import importlib.util
import itertools
from pathlib import Path

import yaml

from anima_ll.adapter.config.yaml_config_source import parse_neuroarchitecture

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXPERIMENT_FROM_DIR = HERE.name.split("_")[0]
# これまでに走らせた seed（0012〜0019 の判定・事後の解析・動作確認、0020 の探索と合成・確認）。重なってはいけない
SEEN = (set(range(1, 21)) | set(range(1001, 1021)) | set(range(2001, 2021)) | set(range(3001, 3007))
        | set(range(4001, 4021)) | set(range(5001, 5007)) | set(range(6001, 6021)) | set(range(7001, 7007))
        | set(range(8001, 8021)) | set(range(8101, 8107)) | set(range(9001, 9700))
        | set(range(10001, 10021)) | set(range(10101, 10107)) | set(range(11001, 11021))
        | set(range(11101, 11107)) | set(range(12001, 12021)) | set(range(12101, 12107))
        | set(range(13001, 13201)))
# 道具が実装している操作の確認の名前（analyze.check_run）。protocol の checks と一致すること
IMPLEMENTED_CHECKS = {
    "inherited_from_0020": ["stimulus_counts", "input_free_after_experience", "identical_before_label_divergence",
                            "transplant", "first_pulse_identical"],
    "exact": ["twin_equals_C", "Y0_equals_C", "I_equals_Y_until_t1", "Y_traces_equal_C_traces",
              "P_zero_on_untransplanted_pairs", "t1_C_Y_equals_t1_C_I", "t2_at_least_t1_plus_2", "no_clipping",
              "divergence_decisions_reconstructed"],
    "numeric": {"replay_history_12000": 1.0e-12, "affine_reconstruction_T": 1.0e-12, "P_identity": 1.0e-12,
                "pair_sum": 1.0e-12, "divergence_activity_reconstruction": 1.0e-12, "t2_decomposition_identity": 1.0e-12},
    "revalidate_from_raw": True,
    "invalid_individuals": "report_all",
}
ARMS = {"C": {"start": "ordered", "transmission": "own", "plasticity_input": "own"},
        "I": {"start": "transplant_of_C", "transmission": "own", "plasticity_input": "own"},
        "Y": {"start": "clone_of_I", "transmission": "own", "plasticity_input": "C"},
        "twin": {"start": "clone_of_C", "transmission": "own", "plasticity_input": "own", "role": "check"},
        "Y0": {"start": "clone_of_C", "transmission": "own", "plasticity_input": "C", "role": "check"}}
YOKE = {"connections": "all_plastic", "replaces": ["fire_events", "traces"], "unit_state": "own",
        "pulse_order": ["C", "I", "Y", "twin", "Y0"], "pulse_match": "required", "runtime_core_unchanged": True}
MISSING_VALUES = {
    "null_if_no_t1": ["t1", "U1", "remaining_after_t1", "t2_detectable_pulses", "t1_contributions"],
    "null_if_no_t2": ["t2", "U2", "t2_minus_t1", "spike_counts_per_unit_from_t2", "t2_contributions"],
    "always_counted_keep_zero": ["spike_counts_per_unit", "differing_pulses"],
    "keep_formula_value_if_t1_without_t2": ["remaining_after_t1", "t2_detectable_pulses"],
    "null_is_not_zero": True,
}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(protocol: dict) -> None:
    problems: list[str] = []

    def expect(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    exp = EXPERIMENT_FROM_DIR
    W = _load(f"world_{exp}_for_alignment", HERE / "world.py")
    G = _load(f"guard_{exp}_for_alignment", HERE / "guard.py")
    expect(protocol["experiment"] == exp == W.EXPERIMENT, f"experiment が、このフォルダの番号 {exp} ・道具と違う")
    expect(protocol["kind"] == "preregistered_descriptive_intervention", "kind が事前登録した記述的な介入実験ではない")
    ex = protocol["execution"]
    expect(ex["experiment_id"] == exp, "execution.experiment_id がこの実験の番号と違う")
    expect(ex["output_dir"] == f"data/experiments/{exp}", "本番の出力先がこの実験のものではない")
    expect(ex["protocol_path"] == str(W.PROTOCOL_PATH), "execution.protocol_path がこの protocol.yaml の場所と違う")
    expect({k: ex[k] for k in ex if k not in ("experiment_id", "output_dir", "protocol_path")} == {
        "measurement_commit": "required", "start_record": G.START, "finish_record": G.FINISH, "rerun": "refuse",
        "end_commit_check": True, "on_failure": "disclose_and_use_new_seed_range", "max_workers": 2,
        "results_must_match_seeds": True, "no_0020_references": True}, "一度限りの実行の決まりが想定と違う")
    brain = protocol["brain"]
    expect(brain["manifest"] == "experiments/0012_passive_world/neuroarchitecture.yaml", "設計図が 0014〜0020 と同じではない")
    raw = W.manifest_raw(protocol)
    base = yaml.safe_load((ROOT / brain["dynamics_from"]).read_text(encoding="utf-8"))
    expect(raw["defaults"]["dynamics"] == base["defaults"]["dynamics"], "設計図の力学が minimal-v3 と違う")
    expect(brain["refractory_pulses"] == raw["defaults"]["dynamics"]["refractory_pulses"] == 0,
           "不応期が 0 ではない（README §3 の前提）")
    m = parse_neuroarchitecture(raw)
    units = list(brain["sensory_units"])
    expect({(p.source_id, p.target_id) for p in m.projections if p.source_id in units}
           == set(itertools.permutations(units, 2)), "s のあいだの接続が相互の 6 本ではない")
    expect(all(p.plastic and p.weight == m.plasticity.w_max / 2 for p in m.projections if p.source_id in units),
           "s のあいだの 6 本が、すべて可塑性の対象・初期の重み w_max／2 ではない")
    tl, st = protocol["timeline"], protocol["stimulus"]
    expect(tl["trials"] == {"first": 1, "every": 60, "count": 200}, "試行が 0020 と違う")
    expect((W.experience_end(protocol), W.total_pulses(protocol), W.sample_every(protocol)) == (12000, 24000, 60),
           "経験の終わり・終端・標本の間隔が 12000・24000・60 ではない")
    expect(tl["window"] == "experience_end + 1 .. total_pulses", "観測の窓の式が想定と違う")
    expect((st["b_offset"], st["c_offset"]) == (2, 30) and st["counts"] == {"A": 200, "B": 200, "C": 200},
           "刺激が 0020 と違う")
    expect(st["rng_shuffle"] == f"{exp}-shuffle:{{seed}}" == W.RNG_SHUFFLE == W.W15.RNG_SHUFFLE,
           "順序を崩す乱数の流れの名前が、この実験のもの・道具と違う")
    expect(st["conditions"] == list(W.CONDITIONS) and st["shuffled_runs_to"] == W.INTERVENTION_AT,
           "条件・shuffled を進める終わりが想定と違う")
    expect(st["role_assignment"] == W.W15.ROLE_ASSIGNMENT, "役の割り当ての式が道具と違う")
    expect(sorted(map(tuple, st["role_orders"])) == sorted(itertools.permutations(brain["receptors"])),
           "role_orders が Receptor の 6 通りの並べ方ではない")
    expect(protocol["intervention"] == {"at": W.INTERVENTION_AT, "rule": W.INTERVENTION_RULE, "new_values": "none"},
           "介入が想定と違う")
    expect(protocol["arms"] == ARMS, "腕の定義が想定と違う")
    expect(protocol["yoke"] == YOKE, "yoke の定義が想定と違う")
    expect(tuple(YOKE["pulse_order"]) == W.ARMS and W.ARMS[0] == W.SOURCE == "C", "腕を進める順が道具と違う")
    expect(tuple(a for a, v in ARMS.items() if v["plasticity_input"] == "C") == W.YOKED, "yoke する腕が道具と違う")
    expect(protocol["observations"]["missing_values"] == MISSING_VALUES, "欠測値の規約が想定と違う")
    expect(protocol["checks"] == IMPLEMENTED_CHECKS, "操作の確認の項目・許容が、道具の実装と違う")
    seeds = set(range(protocol["seeds"]["first"], protocol["seeds"]["last"] + 1))
    syn = set(range(protocol["synthetic_seeds"]["first"], protocol["synthetic_seeds"]["last"] + 1))
    expect(len(seeds) == 100, "本番の個体数が 100 ではない")
    expect(not seeds & SEEN and not syn & SEEN and not seeds & syn, "本番・合成の seed が、これまでの seed や互いと重なる")
    if problems:
        raise SystemExit(f"protocol と {exp} の設計図・道具がずれている：\n- " + "\n- ".join(problems))
