"""protocol.yaml（確定した事前登録 v0.2 の正本）と、0026 の設計図（C0）・道具が同じ条件かを機械的に確かめる。

ズレていたら実行・解析を止める。run.py と analyze.py の両方が最初に呼ぶ。protocol は変えない（道具の側をこれに合わせる）。
実験の ID は、このフォルダの名前の先頭（"0026_state_block_swap" → "0026"）から決め、protocol の experiment・
execution（ID・出力先・protocol のパス）・乱数の流れの名前がそれと一致することを確かめる。
"""

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
# 0023〜0025 の本番・smoke・合成（予約した範囲ごと））。重なってはいけない
SEEN = (set(range(1, 21)) | set(range(1001, 1021)) | set(range(2001, 2021)) | set(range(3001, 3007))
        | set(range(4001, 4021)) | set(range(5001, 5007)) | set(range(6001, 6021)) | set(range(7001, 7007))
        | set(range(8001, 8021)) | set(range(8101, 8107)) | set(range(9001, 9700))
        | set(range(10001, 10021)) | set(range(10101, 10107)) | set(range(11001, 11021))
        | set(range(11101, 11107)) | set(range(12001, 12021)) | set(range(12101, 12107))
        | set(range(13001, 13201)) | set(range(14001, 14201)) | set(range(15001, 15201)) | set(range(16001, 16300))
        | set(range(17001, 17300)) | set(range(18001, 18300)))
# 判定の閾値（README §5.2）：各個体の帰無の確率 2／(K ＋ 1) ＝ 0.1 のもとで P(Bin(20, 0.1) ≥ h) ≤ alpha_each となる最小の h
HOLDS_MIN_H = 6
MANIFEST = "experiments/0012_passive_world/neuroarchitecture.yaml"   # 0014〜0025 と同じ設計図（C0）
EXACT_CHECKS = ["stimulus_labels", "input_free_after_experience", "identical_before_label_divergence",
                "probe_clone_equals_body_t0_minus_1", "identical_through_t0_plus_1", "proposition_3",
                "empty_side_identity", "O_twin_identity", "swap_time_rule", "swap_composition", "swap_invariants",
                "full_swap_reproduces_donor", "null_swap_identity", "censor_arithmetic_recomputed", "no_clipping"]
NUMERIC_CHECKS = {"replay_history_12000": 1.0e-12, "pair_sum": 1.0e-12}
QUANTITIES = {
    "primary": {
        "per_probe": {"ell_B": "n_B_null - n_B_A", "ell_C": "n_C_null - n_C_A"},
        "per_body": {"L": "mean_over_probes(ell_B - ell_C)"},
        "per_individual": {
            "outside_weights": "L(Y(weights <- O)) > max_k L(Y(weights <- W_k)) or L(Y(weights <- O)) < min_k "
                               "L(Y(weights <- W_k)), k = 2..20",
            "outside_units": "L(Y(units <- O)) > max_k L(Y(units <- W_k)) or L(Y(units <- O)) < min_k L(Y(units <- W_k)), "
                             "k = 2..20"},
        "across_individuals": {"h_weights": "count(outside_weights)", "h_units": "count(outside_units)"}},
    "auxiliary": {
        "per_body": {"L_B": "mean_over_probes(ell_B)", "L_C": "mean_over_probes(ell_C)",
                     "censor_counts": ["B_A", "B_null", "C_A", "C_null"]},
        "per_individual": {
            "swap_time": True,
            "rank_of_donor_O_among_20": ["weights", "units"],
            "direction_counts": ["weights", "units"],
            "natural_outside": "L(O) > max_i L(W_i) or L(O) < min_i L(W_i), i = 1..20 (natural bodies; record only)",
            # 300 は試しの数（analyze.py は len(plan.probes) と比べる。本番の Plan では 300）
            "silence_counts": {"B": "count of bodies with (censor_counts.B_A == 300 and censor_counts.B_null == 300)",
                               "C": "count of bodies with (censor_counts.C_A == 300 and censor_counts.C_null == 300)"}},
        "across_individuals": {"clopper_pearson_95_of_h_over_20": ["weights", "units"],
                               "no_swap_time_individuals": True, "natural_outside_count": True}},
    "not_used": ["effect_size_threshold", "population_fraction_claims", "ratios", "normalizations", "combined_scores",
                 "post_hoc_windows", "post_hoc_probe_ranges", "contribution_shares", "comparison_between_h_weights_and_h_units",
                 "comparison_with_earlier_experiments_h", "individual_eligibility_filters", "selection_by_natural_outside"],
}
JUDGMENT_FIXED = {"statistics": ["h_weights", "h_units"], "holds_if": "h >= 6", "alpha_family": 0.05, "alpha_each": 0.025,
                  "holds_means": "reject_null_at_alpha_each_under_assumptions",
                  "per_individual_null_probability_at_most": 0.1, "frozen_individuals": "count_as_not_outside",
                  "no_swap_time": "count_as_not_outside", "on_any_invalid": "experiment_invalid_no_judgment",
                  "scope": "C0_C_I_effect_of_donor_block_given_fixed_W1_background_at_T_relative_to_donor_reference",
                  "not_judged": ["C_II_reproduction_and_elimination_of_natural_difference",
                                 "C_III_cause_of_natural_difference"]}
RECORDS = {"full_state_fields": ["pulse", "units", "connections", "drives", "deltas"],
           "full_state_values_not_digests": True,
           "natural_bodies": {
               "per_body": ["birth_state", "label_sequence", "spikes_1_to_end", "full_state_12000",
                            "full_state_each_pulse_11999_to_end", "full_state_end_of_T"],
               "per_probe_A_copy": ["full_state_end_t0_minus_1_after_clone", "full_state_end_t0", "full_state_end_t0_plus_1",
                                    "spikes_t0_to_window_end", "full_state_window_end"],
               "empty_side_copies": {"probes": ["first", "last"], "keep": ["spikes_to_window_end", "full_state_each_pulse"]},
               "O_twin_without_probes": {"keep": ["spikes_1_to_end", "full_state_12000", "full_state_end"]}},
           "swapped_bodies": {
               "per_body": ["swap_record", "full_state_end_of_T_after_swap", "spikes_T_plus_1_to_end",
                            "full_state_at_selected_pulses"],
               "selected_pulses": ["experience_end", "probes.first", "probes.first + 1", "probes.last - 1", "probes.last",
                                   "probes.last + 1", "body_runs_to"],
               "per_probe": ["spikes_t0_to_window_end"],
               "per_probe_A_copy_states_for": ["first", "last"]},
           "control_bodies": {"keep": ["full_state_end_of_T_after_swap", "spikes_T_plus_1_to_end", "full_state_12000",
                                       "full_state_end"]}}
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


def intervention_of(W) -> dict:
    """道具の実装が表す protocol の intervention（README §2・§3）。"""
    replace = {"weights": [f"connections.{f}" for f in W.BLOCKS["weights"][1]],
               "units": [f"units.{f}" for f in W.BLOCKS["units"][0]] + [f"connections.{f}" for f in W.BLOCKS["units"][1]]}
    return {"kind": "state_block_swap",
            "swap_time": {"rule": W.SWAP_TIME_RULE, "last_stimulus": W.LAST_STIMULUS, "state": "end_of_pulse_T",
                          "if_none": "individual_not_outside_for_both_tests_and_reported"},
            "recipient": W.RECIPIENT, "donors": list(W.DONORS),
            "blocks": {"weights": {"replace": replace["weights"]},
                       "units": {"replace": replace["units"], "keep": [f"units.{f}" for f in W.KEPT_UNIT_FIELDS]}},
            "swapped_bodies": W.SWAPPED_BODIES,
            "control_bodies": {"full_swap": W.FULL_SWAP, "null_swap": W.NULL_SWAP},
            "invariants_checked_on_swapped_state": {"I1_pair_sum_tolerance": 1.0e-12, "I2_trace_per_unit": "exact",
                                                    "I3_activity_positive": "exact", "I4_no_drives_at_T": "exact"}}


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

    # 脳の設計図（README §1。0023・0025 と同じ C0）
    brain = protocol["brain"]
    expect(brain["manifest"] == MANIFEST, "設計図が 0014〜0025 と同じではない")
    raw = W.manifest_raw(protocol)
    base = yaml.safe_load((ROOT / brain["dynamics_from"]).read_text(encoding="utf-8"))
    expect(raw["defaults"]["dynamics"] == base["defaults"]["dynamics"], "設計図の力学が minimal-v3 と違う")
    expect(brain["refractory_pulses"] == raw["defaults"]["dynamics"]["refractory_pulses"] == 0, "不応期が 0 ではない")
    m = parse_neuroarchitecture(raw)
    units = list(brain["sensory_units"])
    expect({(p.source_id, p.target_id) for p in m.projections if p.source_id in units}
           == set(itertools.permutations(units, 2)), "s のあいだの接続が相互の 6 本ではない")
    expect(all(p.plastic and p.weight == m.plasticity.w_max / 2 for p in m.projections if p.source_id in units),
           "s のあいだの 6 本が、すべて可塑性の対象・初期の重み w_max／2 ではない")
    expect({p.source_id: p.target_id for p in m.projections if p.source_id in brain["receptors"]} == brain["receptors"],
           "Receptor → s の対応が protocol と違う")
    expect(m.plasticity.w_max == raw["defaults"]["dynamics"]["adaptation_increment"] == 0.01, "w_max ＝ α ＝ 0.01 ではない")

    # 時間の流れ（README §1。0023・0025 と同じ）
    tl = protocol["timeline"]
    expect(tl["pulse_interval_seconds"] == 1.0 and tl["trials"] == {"first": 1, "every": 60, "count": 200},
           "試行・Pulse の長さが 0023・0025 と違う")
    plan = W.plan_from(protocol)
    expect((plan.trials, plan.experience_end, plan.probes[0], plan.probes[-1], len(plan.probes), plan.window,
            plan.body_end, plan.states_from) == (200, 12000, 12001, 12300, 300, 300, 12601, 11999),
           "Plan が 試行 200・経験の終わり 12000・試し 12001〜12300（300 回）・T_w 300・本体の終わり 12601 ではない")

    # 刺激と条件（README §1・§2.1）
    st = protocol["stimulus"]
    expect((st["b_offset"], st["c_offset"]) == (2, 30) and st["counts"] == {r: plan.trials for r in W.ROLES},
           "刺激の形・数が 0023・0025 と違う（各 200 ＝ 試行の数）")
    expect(0 < st["b_offset"] < st["c_offset"] < tl["trials"]["every"], "試行の中の 3 つの枠が試行の中に順に収まらない")
    expect(st["role_assignment"] == W.ROLE_ASSIGNMENT, "役の割り当ての式が道具と違う")
    expect(sorted(map(tuple, st["role_orders"])) == sorted(itertools.permutations(brain["receptors"])),
           "role_orders が Receptor の 6 通りの並べ方ではない")
    cond = protocol["conditions"]
    expect(cond == {"O": {"schedule": W.SCHEDULES["O"]},
                    "within_trial_shuffles": {"count": 20, "schedule": W.SCHEDULES["within_trial_shuffles"],
                                              "rng": f"{exp}-within-trial-{{i}}:{{seed}}",
                                              "procedure": W.WITHIN_TRIAL_PROCEDURE},
                    "input_after_experience": "none"},
           "条件（O・試行の中の並べ替え 20・その手順・経験の後の入力なし）が道具と違う")
    expect(W.RNG_SHUFFLE == cond["within_trial_shuffles"]["rng"] and W.K == 20 and len(W.BODIES) == 21,
           "試行の中の並べ替えの乱数の流れ・数が道具と違う")

    # 介入（README §2・§3）
    iv = protocol["intervention"]
    expect(iv == intervention_of(W), "介入（T の規則・受け手・ドナー・塊・入れ替えた本体・確認の本体・不変の関係）が道具と違う")
    lo, hi = W.swap_window(protocol, plan)
    expect((lo, hi) == (11972, 12000), "T の窓が 11972〜12000 ではない")
    expect(W.selected_pulses(plan) == (12000, 12001, 12002, 12299, 12300, 12301, 12601),
           "入れ替えた本体の全状態を残す Pulse が想定と違う")
    every = {f for b in W.BLOCKS.values() for part in b for f in part}
    expect(set(W.BLOCKS["weights"][0]) | set(W.BLOCKS["weights"][1]) | set(W.BLOCKS["units"][0]) | set(W.BLOCKS["units"][1])
           == every and not (set(W.BLOCKS["weights"][1]) & set(W.BLOCKS["units"][1]))
           and set(W.BLOCKS["units"][0]) | set(W.KEPT_UNIT_FIELDS) == set(W.UNIT_FIELDS)
           and set(W.BLOCKS["weights"][1]) | set(W.BLOCKS["units"][1]) == set(W.CONNECTION_FIELDS),
           "2 つの塊が、発火の回数を除く Unit・接続の欄を重ならずに覆っていない")
    expect(W.DONORS == ("O",) + tuple(f"W{i}" for i in range(2, 21)) and W.RECIPIENT == "W1"
           and W.RECIPIENT not in W.DONORS, "受け手・ドナーが W1・(O, W2〜W20) ではない")

    # 試し（README §4）
    expect(protocol["probe"] == {"base": W.PROBE_BASE, "A_copy": W.A_COPY, "null_side": W.NULL_SIDE, "window": W.WINDOW,
                                 "first_fire_censor_value": W.CENSOR}, "試しの手順が道具と違う")

    # 量・判定・記録・確認（README §4〜§8）
    expect(protocol["quantities"] == QUANTITIES, "主・補助の量の定義が道具の実装と違う")
    j = protocol["judgment"]
    expect({k: j[k] for k in JUDGMENT_FIXED} == JUDGMENT_FIXED, "判定の決まりが道具の実装と違う")
    p0 = Fraction(2, len(W.DONORS))
    expect(p0 == Fraction(1, 10) == Fraction(j["per_individual_null_probability_at_most"]).limit_denominator(1000),
           "各個体の帰無の確率 2／(K ＋ 1) が 0.1 ではない")
    n = len(rng["seeds"])
    a_each = Fraction(j["alpha_each"]).limit_denominator(1000)
    expect(a_each * len(j["statistics"]) == Fraction(j["alpha_family"]).limit_denominator(1000),
           "alpha_each が alpha_family を判定の数で割った値（Bonferroni）ではない")
    expect(binom_tail(n, p0, HOLDS_MIN_H) <= a_each < binom_tail(n, p0, HOLDS_MIN_H - 1),
           "h ≥ 6 が、P(Bin(20, 0.1) ≥ h) ≤ alpha_each となる最小の h ではない")
    expect(protocol["records"] == RECORDS, "記録の項目が道具の実装と違う")
    expect(tuple(protocol["records"]["full_state_fields"]) == W.FULL_STATE_FIELDS, "全状態の欄が道具と違う")
    expect(protocol["records"]["swapped_bodies"]["selected_pulses"] == list(W.SELECTED_PULSES),
           "入れ替えた本体の全状態を残す Pulse の式が道具と違う")
    ch = protocol["checks"]
    expect(ch == {"exact": EXACT_CHECKS, "numeric": NUMERIC_CHECKS, "revalidate_from_raw": True,
                  "invalid_individuals": "report_all"}, "操作の確認の項目・許容が道具の実装と違う")

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
