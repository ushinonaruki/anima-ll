"""protocol.yaml（確定した事前登録 v0.2 の正本）と、0024 の設計図（V1）・道具が同じ条件かを機械的に確かめる。

ズレていたら実行・解析を止める。run.py と analyze.py の両方が最初に呼ぶ。protocol は変えない（道具の側をこれに合わせる）。
実験の ID は、このフォルダの名前の先頭（"0024_learning_free_order_readout" → "0024"）から決め、protocol の experiment・
execution（ID・出力先・protocol のパス）・乱数の流れの名前がそれと一致することを確かめる。

V1 の設計図（README §1.1）：protocol の brain.manifest（このフォルダの neuroarchitecture-v1.yaml）を YAML として読んだ値が、
brain.derived_from（0014〜0023 の設計図）を YAML として読んだ値から、s のあいだの 6 本の plastic: true だけを除いたものと
完全に同じであること（YAML の設定値と配線。ファイルの注釈は比べない）。derived_from はこの照合のためだけに読む。
"""

import copy
import importlib.util
import itertools
import math
from fractions import Fraction
from pathlib import Path

import yaml

from anima_ll.adapter.config.yaml_config_source import parse_neuroarchitecture

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXPERIMENT_FROM_DIR = HERE.name.split("_")[0]
# これまでに走らせた seed（0012〜0019 の判定・事後の解析・動作確認、0020 の探索と合成・確認、0021・0022 の本番と合成・確認、
# 0023 の本番・smoke・合成（予約した範囲ごと））。重なってはいけない
SEEN = (set(range(1, 21)) | set(range(1001, 1021)) | set(range(2001, 2021)) | set(range(3001, 3007))
        | set(range(4001, 4021)) | set(range(5001, 5007)) | set(range(6001, 6021)) | set(range(7001, 7007))
        | set(range(8001, 8021)) | set(range(8101, 8107)) | set(range(9001, 9700))
        | set(range(10001, 10021)) | set(range(10101, 10107)) | set(range(11001, 11021))
        | set(range(11101, 11107)) | set(range(12001, 12021)) | set(range(12101, 12107))
        | set(range(13001, 13201)) | set(range(14001, 14201)) | set(range(15001, 15201)) | set(range(16001, 16300)))
# 判定の閾値（README §5.2）：各個体の帰無の確率 2／(K ＋ 1) ＝ 0.1 のもとで P(Bin(20, 0.1) ≥ h) ≤ alpha となる最小の h
HOLDS_MIN_H = 5
DERIVED_FROM = "experiments/0012_passive_world/neuroarchitecture.yaml"   # 照合の相手（0014〜0023 の設計図。読み込むのは YAML だけ）
VARIANT = "remove plastic: true from the six s-s projections; all other YAML settings and wiring identical (header comments differ)"
BRAIN_KEYS = {"manifest", "derived_from", "variant", "dynamics_from", "sensory_units", "receptors", "refractory_pulses",
              "fixed_weights", "plastic_connections"}
EXACT_CHECKS = ["stimulus_labels", "input_free_after_experience", "identical_before_label_divergence",
                "probe_clone_equals_body_t0_minus_1", "identical_through_t0_plus_1", "proposition_3",
                "empty_side_identity", "O_twin_identity", "censor_arithmetic_recomputed",
                "no_plastic_connection_state", "fixed_transmission_weights"]
NOT_APPLICABLE_IN_V1 = ["replay_history_12000", "pair_sum", "no_clipping"]
QUANTITIES = {
    "primary": {"per_probe": {"ell_B": "n_B_null - n_B_A", "ell_C": "n_C_null - n_C_A"},
                "per_body": {"L": "mean_over_probes(ell_B - ell_C)"},
                "per_individual": {"outside": "L(O) > max_i L(S_i) or L(O) < min_i L(S_i)"},
                "across_individuals": {"h": "count(outside)"}},
    "auxiliary": {"per_body": {"L_B": "mean_over_probes(ell_B)", "L_C": "mean_over_probes(ell_C)",
                               "R1_prime": "mean_over_probes((B_A(t0+2) - B_null(t0+2)) - (C_A(t0+2) - C_null(t0+2)))",
                               "R1": "mean_over_probes(B_A(t0+2) - C_A(t0+2))",
                               "R3": "mean_over_probes((N_B_A - N_B_null) - (N_C_A - N_C_null))",
                               "censor_counts": ["B_A", "B_null", "C_A", "C_null"]},
                  "per_individual": {"rank_of_L_O_among_20": True,
                                     "direction_counts": ["L(O) > max_i L(S_i)", "L(O) < min_i L(S_i)"],
                                     "mirror": ["L(M)", "L(M) outside shuffles (same form)", "L(O) - L(M)"],
                                     "aux_outside_counts": ["R1_prime", "R1", "R3"],
                                     # 300 は試しの数（analyze.py は len(plan.probes) と比べる。本番の Plan では 300）
                                     "silence_counts": {
                                         "B": "count over 21 bodies of (censor_counts.B_A == 300 and censor_counts.B_null == 300)",
                                         "C": "count over 21 bodies of (censor_counts.C_A == 300 and censor_counts.C_null == 300)"}},
                  "across_individuals": {"clopper_pearson_95_of_h_over_20": True}},
    "not_used": ["effect_size_threshold", "population_fraction_claims", "ratios", "normalizations", "combined_scores",
                 "post_hoc_windows", "post_hoc_probe_ranges", "comparison_with_0023_h", "individual_eligibility_filters"],
}
JUDGMENT_FIXED = {"statistic": "h", "holds_if": "h >= 5", "alpha": 0.05,
                  "holds_means": "reject_null_at_alpha_under_assumptions",
                  "per_individual_null_probability_at_most": 0.1, "frozen_individuals": "count_as_not_outside",
                  "on_any_invalid": "experiment_invalid_no_judgment", "scope": "V1_only"}
RECORDS = {"full_state_fields": ["pulse", "units", "connections", "drives", "deltas"],
           "connections_field_in_V1": "empty_mapping_kept",
           "full_state_values_not_digests": True,
           "per_body": ["birth_state", "label_sequence", "spikes_1_to_end", "full_state_12000",
                        "full_state_each_pulse_11999_to_end"],
           "per_probe_A_copy": ["full_state_end_t0_minus_1_after_clone", "full_state_end_t0", "full_state_end_t0_plus_1",
                                "spikes_t0_to_window_end", "full_state_window_end"],
           "empty_side_copies": {"probes": ["first", "last"], "keep": ["spikes_to_window_end", "full_state_each_pulse"]},
           "O_twin_without_probes": {"keep": ["spikes_1_to_end", "full_state_12000", "full_state_end"]}}
PER_SEED = {"allowed": True,
            "start_record": {"exclusive_create": True, "fields": ["seed", "measurement_commit", "protocol_sha256", "started_at"]},
            "finish_record": {"fields": ["seed", "status", "finished_at", "raw_file_sha256", "raw_file_bytes"]},
            "refuse_if_start_record_exists": True,
            "aggregate_only_after": "all_20_seeds_have_start_and_finish_with_matching_raw_hash",
            "no_partial_judgment_quantities": True, "no_replacement_seeds": True}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def binom_tail(n: int, p: Fraction, k: int) -> Fraction:
    return sum((Fraction(math.comb(n, i)) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1)), Fraction(0))


def v1_from(derived: dict, units: list[str]) -> tuple[dict, int]:
    """derived_from の YAML の値から、s のあいだの接続の plastic: true だけを除いたもの（と、除いた本数）。"""
    v1 = copy.deepcopy(derived)
    removed = 0
    for p in v1["projections"]:
        if p["from"].split(".")[0] in units and p["to"] in units and p.get("plastic") is True:
            del p["plastic"]
            removed += 1
    return v1, removed


def check(protocol: dict) -> None:
    problems: list[str] = []

    def expect(ok: bool, what: str) -> None:
        if not ok:
            problems.append(what)

    exp = EXPERIMENT_FROM_DIR
    W = _load(f"world_{exp}_for_alignment", HERE / "world.py")
    G = _load(f"guard_{exp}_for_alignment", HERE / "guard.py")
    expect(protocol["experiment"] == exp == W.EXPERIMENT, f"experiment が、このフォルダの番号 {exp} ・道具と違う")
    expect(protocol["kind"] == "preregistered_test", "kind が事前登録した検証ではない")

    # seed（D5）
    rng = {k: set(range(protocol[k]["first"], protocol[k]["last"] + 1)) for k in ("seeds", "smoke_seeds", "synthetic_seeds")}
    expect((len(rng["seeds"]), len(rng["smoke_seeds"]), len(rng["synthetic_seeds"])) == (20, 6, 99),
           "本番・smoke・合成の seed の数が 20・6・99 ではない")
    expect(all(not v & SEEN for v in rng.values()), "本番・smoke・合成の seed が、これまでに走らせた seed と重なる")
    expect(all(not a & b for a, b in itertools.combinations(rng.values(), 2)), "本番・smoke・合成の seed の範囲が互いに重なる")

    # 脳の設計図 V1（README §1・§1.1）
    brain = protocol["brain"]
    units = list(brain["sensory_units"])
    expect(set(brain) == BRAIN_KEYS, "brain の項目が想定と違う")
    expect(brain["manifest"] == f"experiments/{HERE.name}/neuroarchitecture-v1.yaml", "設計図が、このフォルダの V1 ではない")
    expect(brain["derived_from"] == DERIVED_FROM and brain["variant"] == VARIANT, "V1 の元の設計図・変種の説明が想定と違う")
    expect(brain["plastic_connections"] == "none", "plastic_connections が none ではない")
    raw = W.manifest_raw(protocol)
    derived = yaml.safe_load((ROOT / brain["derived_from"]).read_text(encoding="utf-8"))
    expected_v1, removed = v1_from(derived, units)
    expect(removed == 6, "元の設計図の s のあいだの可塑性の対象が 6 本ではない")
    expect(raw == expected_v1, "V1 の設計図が、元の設計図から s のあいだの 6 本の plastic: true だけを除いたものと違う")
    base = yaml.safe_load((ROOT / brain["dynamics_from"]).read_text(encoding="utf-8"))
    expect(raw["defaults"]["dynamics"] == base["defaults"]["dynamics"], "設計図の力学が minimal-v3 と違う")
    expect(brain["refractory_pulses"] == raw["defaults"]["dynamics"]["refractory_pulses"] == 0, "不応期が 0 ではない")
    m = parse_neuroarchitecture(raw)
    expect(not any(p.plastic for p in m.projections), "V1 の設計図に可塑性の対象の接続がある")
    expect({(p.source_id, p.target_id) for p in m.projections if p.source_id in units}
           == set(itertools.permutations(units, 2)), "s のあいだの接続が相互の 6 本ではない")
    s_to_s = brain["fixed_weights"]["s_to_s"]
    expect(set(brain["fixed_weights"]) == {"s_to_s"} and s_to_s == 0.005 == m.plasticity.w_max / 2,
           "固定した伝達の重みが 0.005 ＝ w_max／2 ではない")
    expect(all(p.weight == s_to_s for p in m.projections if p.source_id in units),
           "s のあいだの 6 本の重みが brain.fixed_weights.s_to_s ではない")
    expect({p.source_id: p.target_id for p in m.projections if p.source_id in brain["receptors"]} == brain["receptors"],
           "Receptor → s の対応が protocol と違う")
    expect(all(p.weight == 1.0 for p in m.projections if p.source_id in brain["receptors"]), "Receptor → s の重みが 1.0 ではない")
    expect(len(m.projections) == 9, "接続が Receptor → s の 3 本と s のあいだの 6 本ではない")
    expect(m.plasticity.w_max == raw["defaults"]["dynamics"]["adaptation_increment"] == 0.01, "w_max ＝ α ＝ 0.01 ではない")
    expect(W.projection_weights(protocol) == {(p.source_id, p.target_id): p.weight for p in m.projections},
           "道具が読む接続の重みが設計図と違う")

    # 時間の流れ（README §3）
    tl = protocol["timeline"]
    expect(tl["pulse_interval_seconds"] == 1.0 and tl["trials"] == {"first": 1, "every": 60, "count": 200},
           "試行・Pulse の長さが 0023 と違う")
    plan = W.plan_from(protocol)
    expect((plan.trials, plan.experience_end, plan.probes[0], plan.probes[-1], len(plan.probes), plan.window,
            plan.body_end, plan.states_from) == (200, 12000, 12001, 12300, 300, 300, 12601, 11999),
           "Plan が 試行 200・経験の終わり 12000・試し 12001〜12300（300 回）・T_w 300・本体の終わり 12601 ではない")

    # 刺激と条件（README §2）
    st = protocol["stimulus"]
    expect((st["b_offset"], st["c_offset"]) == (2, 30) and st["counts"] == {r: plan.trials for r in W.ROLES},
           "刺激の形・数が 0023 と違う（各 200 ＝ 試行の数）")
    expect(st["c_offset"] < tl["trials"]["every"], "試行の中の刺激が次の試行と重なる")
    expect(st["role_assignment"] == W.ROLE_ASSIGNMENT, "役の割り当ての式が道具と違う")
    expect(sorted(map(tuple, st["role_orders"])) == sorted(itertools.permutations(brain["receptors"])),
           "role_orders が Receptor の 6 通りの並べ方ではない")
    cond = protocol["conditions"]
    expect(cond == {"O": {"schedule": W.SCHEDULES["O"]}, "M": {"schedule": W.SCHEDULES["M"], "role": "auxiliary"},
                    "shuffles": {"count": 19, "schedule": W.SCHEDULES["shuffles"], "rng": f"{exp}-shuffle-{{i}}:{{seed}}"},
                    "input_after_experience": "none"}, "条件（O・M・並べ替え 19・経験の後の入力なし）が道具と違う")
    expect(W.RNG_SHUFFLE == cond["shuffles"]["rng"] and W.K == 19 and len(W.BODIES) == 21, "並べ替えの乱数の流れ・数が道具と違う")

    # 試し（README §3）
    expect(protocol["probe"] == {"base": W.PROBE_BASE, "A_copy": W.A_COPY, "null_side": W.NULL_SIDE, "window": W.WINDOW,
                                 "first_fire_censor_value": W.CENSOR}, "試しの手順が道具と違う")

    # 量・判定・記録・確認（README §4〜§8）
    expect(protocol["quantities"] == QUANTITIES, "主・補助の量の定義が道具の実装と違う")
    j = protocol["judgment"]
    expect({k: j[k] for k in JUDGMENT_FIXED} == JUDGMENT_FIXED, "判定の決まりが道具の実装と違う")
    p0 = Fraction(2, cond["shuffles"]["count"] + 1)
    expect(p0 == Fraction(1, 10) == Fraction(j["per_individual_null_probability_at_most"]).limit_denominator(1000),
           "各個体の帰無の確率 2／(K ＋ 1) が 0.1 ではない")
    n = len(rng["seeds"])
    alpha = Fraction(j["alpha"]).limit_denominator(1000)
    expect(binom_tail(n, p0, HOLDS_MIN_H) <= alpha < binom_tail(n, p0, HOLDS_MIN_H - 1),
           "h ≥ 5 が、P(Bin(20, 0.1) ≥ h) ≤ alpha となる最小の h ではない")
    expect(protocol["records"] == RECORDS, "記録の項目が道具の実装と違う")
    expect(tuple(protocol["records"]["full_state_fields"]) == W.FULL_STATE_FIELDS, "全状態の欄が道具と違う")
    ch = protocol["checks"]
    expect(ch == {"exact": EXACT_CHECKS, "numeric": {}, "revalidate_from_raw": True, "invalid_individuals": "report_all",
                  "not_applicable_in_V1": NOT_APPLICABLE_IN_V1}, "操作の確認の項目が道具の実装と違う")
    expect(not set(EXACT_CHECKS) & set(NOT_APPLICABLE_IN_V1), "V1 で置かない確認が、確認の項目に入っている")

    # 一度限りの実行（README §9）
    ex = protocol["execution"]
    expect(ex["experiment_id"] == exp and ex["output_dir"] == f"data/experiments/{exp}"
           and ex["protocol_path"] == str(W.PROTOCOL_PATH), "execution の ID・出力先・protocol のパスがこの実験のものではない")
    expect(ex["start_record"] == G.START and ex["finish_record"] == G.FINISH, "開始・終了の記録の名前が道具と違う")
    expect(ex["per_seed"] == PER_SEED and list(G.START_FIELDS) == PER_SEED["start_record"]["fields"]
           and list(G.FINISH_FIELDS) == PER_SEED["finish_record"]["fields"], "seed 単位の実行の決まりが道具と違う")
    expect({k: ex[k] for k in ("measurement_commit", "rerun", "end_commit_check", "max_workers", "results_must_match_seeds",
                               "no_earlier_experiment_references", "analysis_commit_must_equal_measurement_commit")}
           == {"measurement_commit": "required", "rerun": "refuse", "end_commit_check": True, "max_workers": 2,
               "results_must_match_seeds": True, "no_earlier_experiment_references": True,
               "analysis_commit_must_equal_measurement_commit": True},
           "一度限りの実行の決まりが想定と違う")
    expect(ex["on_failure"] == "disclose_whole_experiment_invalid_or_incomplete_and_new_preregistration_with_new_seed_range",
           "失敗したときの扱いが想定と違う")
    if problems:
        raise SystemExit(f"protocol と {exp} の設計図・道具がずれている：\n- " + "\n- ".join(problems))
