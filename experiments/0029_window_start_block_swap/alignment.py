"""protocol.yaml（確定した事前登録 v0.2 の正本）と、0029 の設計図（C0）・道具が同じ条件かを機械的に確かめる。

ズレていたら実行・解析を止める。run.py と analyze.py の両方が最初に呼ぶ。protocol は変えない（道具の側をこれに合わせる）。
実験の ID は、このフォルダの名前の先頭（"0029_window_start_block_swap" → "0029"）から決め、protocol の experiment・
execution（ID・出力先・protocol のパス）・乱数の流れの名前がそれと一致することを確かめる。

主の判定（README §4・§5、protocol の judgment.per_family）は、Wt の家族（一方向）と U の家族（向きを問わない）に、それぞれ
J_Ca・J_O・J_M・J_OM の 4 つ。閾値は、割り当てた水準と K ＝ 19・向きの扱いから決まる最小の整数であることを、二項分布の上側の確率を
厳密に計算して確かめる。

protocol の書き方についての注（README の意味は変えない）：quantities.auxiliary の clopper_pearson_95_of_h_over_20 は、v0.2 の
書き足しの位置のため when_no_tau の下に入っているが、README §6 の補助の表のとおり、τ の有無に依らない 8 つの判定の h／20 の区間
（判定に使わない）として analyze.py が計算する。この alignment は protocol をそのままの形で比べる。
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
# 0023〜0028 の本番・smoke・合成（予約した範囲ごと））。重なってはいけない
SEEN = (set(range(1, 21)) | set(range(1001, 1021)) | set(range(2001, 2021)) | set(range(3001, 3007))
        | set(range(4001, 4021)) | set(range(5001, 5007)) | set(range(6001, 6021)) | set(range(7001, 7007))
        | set(range(8001, 8021)) | set(range(8101, 8107)) | set(range(9001, 9700))
        | set(range(10001, 10021)) | set(range(10101, 10107)) | set(range(11001, 11021))
        | set(range(11101, 11107)) | set(range(12001, 12021)) | set(range(12101, 12107))
        | set(range(13001, 13201)) | set(range(14001, 14201)) | set(range(15001, 15201)) | set(range(16001, 16300))
        | set(range(17001, 17300)) | set(range(18001, 18300)) | set(range(19001, 19300)) | set(range(20001, 20300))
        | set(range(21001, 21300)))

# 主の判定（README §4.2）
FAMILIES = ("Wt", "U")
JUDGMENTS = ("J_Ca", "J_O", "J_M", "J_OM")
STATISTIC = {"J_Ca": "h_Ca", "J_O": "h_O", "J_M": "h_M", "J_OM": "h_OM"}
EVENT = {"Wt": {"J_Ca": "O_Delta_AB_above", "J_O": "O_above", "J_M": "M_below", "J_OM": "O_and_M_split"},
         "U": {"J_Ca": "O_Delta_AB_outside", "J_O": "O_outside", "J_M": "M_outside", "J_OM": "O_and_M_opposite_ends"}}
SIDES = {"Wt": 1, "U": 2}                                       # 一方向・向きを問わない（個体ごとの帰無の確率の分子）
# 閾値：割り当てた水準 alpha_J のもとで P(Bin(20, p0) ≥ h) ≤ alpha_J となる最小の h（check で厳密に確かめる）
HOLDS_MIN = {"Wt": {"J_Ca": 4, "J_O": 4, "J_M": 4, "J_OM": 2}, "U": {"J_Ca": 6, "J_O": 6, "J_M": 6, "J_OM": 3}}

MANIFEST = "experiments/0012_passive_world/neuroarchitecture.yaml"   # 0014〜0028 と同じ設計図（C0）
BRAIN = {"manifest": MANIFEST, "dynamics_from": "config/neuroarchitecture/minimal-v3.yaml", "sensory_units": ["s1", "s2", "s3"],
         "receptors": {"receptor.x1": "s1", "receptor.x2": "s2", "receptor.x3": "s3"}, "refractory_pulses": 0,
         "plastic_connections": "six_s_to_s"}
REF = [f"W{i}" for i in range(1, 20)]

QUANTITIES = {
    "per_body": {"N": "N_{X->Y} = #{ t : S <= t <= E - 1, s_X(t) = 1, s_Y(t + 1) = 1 } for ordered pairs X != Y",
                 "Delta_AB": "N_{A->B} - N_{B->A}", "Delta_AC": "N_{A->C} - N_{C->A}", "D": "Delta_AB - Delta_AC"},
    "primary": {
        "window": "count_window_main",
        "per_individual": {
            "Wt": {"O_Delta_AB_above": "Delta_AB(Y^Wt(O)) > max_d Delta_AB(Y^Wt(d))",
                   "O_above": "D(Y^Wt(O)) > max_d D(Y^Wt(d))",
                   "M_below": "D(Y^Wt(M)) < min_d D(Y^Wt(d))",
                   "O_and_M_split": "O_above and M_below"},
            "U": {"O_Delta_AB_outside": "Delta_AB(Y^U(O)) > max_d Delta_AB(Y^U(d)) or Delta_AB(Y^U(O)) < min_d Delta_AB(Y^U(d))",
                  "O_outside": "D(Y^U(O)) > max_d D(Y^U(d)) or D(Y^U(O)) < min_d D(Y^U(d))",
                  "M_outside": "D(Y^U(M)) > max_d D(Y^U(d)) or D(Y^U(M)) < min_d D(Y^U(d))",
                  "O_and_M_opposite_ends": ("(D(Y^U(O)) > max_d D(Y^U(d)) and D(Y^U(M)) < min_d D(Y^U(d))) or "
                                            "(D(Y^U(O)) < min_d D(Y^U(d)) and D(Y^U(M)) > max_d D(Y^U(d)))")}},
        "across_individuals": {
            "Wt": {"h_Ca": "count(O_Delta_AB_above)", "h_O": "count(O_above)", "h_M": "count(M_below)",
                   "h_OM": "count(O_and_M_split)"},
            "U": {"h_Ca": "count(O_Delta_AB_outside)", "h_O": "count(O_outside)", "h_M": "count(M_outside)",
                  "h_OM": "count(O_and_M_opposite_ends)"}}},
    "auxiliary": {
        "per_individual": {
            "swap_time": True,
            "per_body_components": ["six_N_counts", "Delta_AB", "Delta_AC", "Delta_BC", "D", "spike_counts_per_unit",
                                    "silent_units"],
            "ranks": ["rank_of_Delta_AB_O_among_reference", "rank_of_D_O_among_reference", "rank_of_D_M_among_reference"],
            "Wt_opposite_direction": ["Delta_AB(Y^Wt(O)) < min", "D(Y^Wt(O)) < min", "D(Y^Wt(M)) > max"],
            "U_directions": ["above_max_or_below_min_for_each_U_event", "direction_pair_of_O_and_M_opposite_ends"],
            "frozen_per_judgment": True,
            "birth_margin_strata": {
                "g": "g_i = intrinsic_drive_i / (1 - decay) - threshold_i for roles A, B, C (birth Unit dynamics)",
                "strata": {"structural": "g_i < -0.03", "conditional": "-0.03 <= g_i < 0", "active": "g_i >= 0"},
                "record": "counts_of_each_primary_event_per_stratum"},
            "natural_comparison": {"events": ["O_Delta_AB_above", "O_above", "M_below", "O_and_M_split"], "reference": REF}},
        "across_individuals": {"counts_of_each_auxiliary_event": True, "no_swap_time_individuals": True},
        "when_no_tau": {
            "recorded": ["natural_body_components_and_silence", "birth_margin_strata", "natural_comparison"],
            "null_with_reason_no_tau": ["swapped_body_components", "ranks", "Wt_opposite_direction", "U_directions",
                                        "frozen_per_judgment", "swapped_body_silence"],
            "strata_counts": "count_events_as_not_outside_and_record_no_tau_count_per_stratum",
            "clopper_pearson_95_of_h_over_20": ["Wt.h_Ca", "Wt.h_O", "Wt.h_M", "Wt.h_OM", "U.h_Ca", "U.h_O", "U.h_M",
                                                "U.h_OM"]}},
    "not_used": ["effect_size_threshold", "population_fraction_claims", "ratios", "normalizations", "rates", "weighted_lag_sums",
                 "combined_scores", "post_hoc_windows", "post_hoc_lags", "contribution_shares", "comparison_between_families_h",
                 "comparison_with_earlier_experiments_h", "individual_eligibility_filters", "selection_by_natural_comparison",
                 "selection_by_birth_margin_strata", "probe_readouts", "between_trial_shuffle_reference"],
}
STRUCTURAL_BOUND = -0.03                                         # g ＜ −0.03 が構造的、−0.03 ≤ g ＜ 0 が条件付き、g ≥ 0 が活動的
STRATA = ("structural", "conditional", "active")

JUDGMENT = {
    "families": {"Wt": {"block": "weights", "direction": "one_sided", "alpha": 0.05},
                 "U": {"block": "units", "direction": "two_sided", "alpha": 0.05}},
    "experiment_wide_error_rate_claimed": "none",
    "per_family": {
        "alpha_split": {"J_Ca": 0.016, "J_O": 0.016, "J_M": 0.016, "J_OM": 0.002},
        "Wt": {"J_Ca": {"statistic": "h_Ca", "holds_if": "h_Ca >= 4", "per_individual_null_probability_at_most": "1/20"},
               "J_O": {"statistic": "h_O", "holds_if": "h_O >= 4", "per_individual_null_probability_at_most": "1/20"},
               "J_M": {"statistic": "h_M", "holds_if": "h_M >= 4", "per_individual_null_probability_at_most": "1/20"},
               "J_OM": {"statistic": "h_OM", "holds_if": "h_OM >= 2", "per_individual_null_probability_at_most": "1/420"}},
        "U": {"J_Ca": {"statistic": "h_Ca", "holds_if": "h_Ca >= 6", "per_individual_null_probability_at_most": "2/20"},
              "J_O": {"statistic": "h_O", "holds_if": "h_O >= 6", "per_individual_null_probability_at_most": "2/20"},
              "J_M": {"statistic": "h_M", "holds_if": "h_M >= 6", "per_individual_null_probability_at_most": "2/20"},
              "J_OM": {"statistic": "h_OM", "holds_if": "h_OM >= 3", "per_individual_null_probability_at_most": "2/420"}}},
    "null_hypothesis": {
        "Wt_single": ("for every individual, as a donor of the weights block into W20 at tau, O (resp. M) is exchangeable with "
                      "W1..W19 (for the quantity of the judgment)"),
        "Wt_OM": ("for every individual, as donors of the weights block into W20 at tau, O, M, W1..W19 (21 donors) are "
                  "exchangeable (for D)"),
        "U_single": ("for every individual, as a donor of the units block into W20 at tau, O (resp. M) is exchangeable with "
                     "W1..W19 (for the quantity of the judgment)"),
        "U_OM": ("for every individual, as donors of the units block into W20 at tau, O, M, W1..W19 (21 donors) are "
                 "exchangeable (for D)")},
    "independence_assumption": ("birth states and within-trial shuffle RNG streams are treated as independent across individuals "
                                "(statistical model assumption; not implied by distinct seeds)"),
    "holds_means": "reject_null_at_alpha_under_assumptions",
    "ties": "strict_inequality_counts_ties_as_not_outside",
    "frozen_individuals": "count_as_not_outside",
    "no_swap_time": "count_as_not_outside",
    "no_tau_individuals": {"in_denominator_of_20": True, "all_eight_events": False, "recorded_separately_from_frozen": True,
                           "counted_as_completed": True},
    "on_any_invalid": "experiment_invalid_no_judgment",
    "scope": "C0_C_I_effect_of_donor_block_into_W20_at_tau_before_main_window_on_lag1_asymmetry_relative_to_donor_reference",
    "not_judged": ["C_II_reproduction_and_elimination_of_natural_difference", "C_III_cause_of_natural_difference",
                   "exclusivity_of_blocks", "contribution_shares", "other_recipients", "components_within_blocks",
                   "reachability_of_swapped_states", "learning_necessity", "quantity_only_difference_excluded",
                   "plasticity_freeze_variant", "count_exceeding_events", "memory_formation", "meaning", "three_element_order",
                   "intervals"],
}
SWAPPED_PER_BODY = ["swap_record", "full_state_end_of_tau_after_swap", "spikes_tau_plus_1_to_end", "full_state_13500",
                    "full_state_25500"]
RECORDS = {
    "full_state_fields": ["pulse", "units", "connections", "drives", "deltas"],
    "full_state_values_not_digests": True,
    "natural_bodies": {"per_body": ["birth_state", "unit_dynamics", "label_sequence", "spikes_1_to_end", "full_state_12000",
                                    "full_state_end_of_tau", "full_state_13500", "full_state_25500",
                                    "full_state_first_stimulus_and_next", "full_state_before_label_divergence"]},
    "swapped_bodies": {"per_body": SWAPPED_PER_BODY},
    "control_bodies": {"per_body": SWAPPED_PER_BODY},
    "swap_fields": {"tau_exists": {"when_tau": True, "when_no_tau": False},
                    "tau": {"when_tau": "integer_in_swap_window", "when_no_tau": None},
                    "window_witness": {"when_tau": None,
                                       "when_no_tau": ("array of {pulse, body, unit} for every Pulse of swap_window in ascending "
                                                       "order; the first firing (body in order O, M, W1..W20; unit in order s1, "
                                                       "s2, s3) at that Pulse among the natural bodies")}},
    "no_tau": {"natural_bodies": "same_as_above_except_full_state_end_of_tau_is_null", "swapped_bodies": [],
               "control_bodies": [], "events": {"all_eight": False, "not_outside_reason": "no_tau"}},
    "inconsistent_raw_is_invalid": True,
}
SNAPSHOTS = [12000, 13500, 25500]
CHECKS = {
    "result_values": ["pass", "fail", "not_applicable"],
    "exact": ["stimulus_labels", "identical_birth_state_natural_bodies", "input_free_after_experience",
              "identical_before_label_divergence", "swap_time_rule", "swap_composition", "swap_invariants",
              "full_swap_reproduces_donor", "null_swap_identity", "no_clipping", "lag1_counts_two_ways"],
    "numeric": {"replay_weights_and_traces": {"natural_at": [12000, "tau", 13500, 25500], "swapped_at": [13500, 25500],
                                              "tolerance": 1.0e-12},
                "pair_sum": {"tolerance": 1.0e-12}},
    "revalidate_from_raw": True,
    "invalid_individuals": "report_all",
    "no_tau": {"apply_on_natural_bodies_only": ["stimulus_labels", "identical_birth_state_natural_bodies",
                                                "input_free_after_experience", "identical_before_label_divergence", "no_clipping",
                                                "lag1_counts_two_ways", "replay_weights_and_traces", "pair_sum"],
               "swap_time_rule": ("no-tau proof: every Pulse of swap_window has a firing in some natural body; each "
                                  "window_witness entry matches the recorded spikes and is the first in the fixed order"),
               "not_applicable": ["swap_composition", "swap_invariants", "full_swap_reproduces_donor", "null_swap_identity"],
               "body_layout": "natural 22; swapped_bodies and control_bodies are empty arrays"},
}
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


def per_individual_null(family: str, judgment: str, k: int) -> Fraction:
    """README §4.3：一方向（Wt）の J_Ca・J_O・J_M は 1／(K ＋ 1)、J_OM は O が 21 個の最大かつ M が最小になる確率
    1／((K ＋ 2)(K ＋ 1))。向きを問わない（U）はそれぞれ 2 倍（どちらの端か・どちらの向きの組か）。"""
    base = Fraction(1, (k + 2) * (k + 1)) if judgment == "J_OM" else Fraction(1, k + 1)
    return SIDES[family] * base


def intervention_of(W) -> dict:
    """道具の実装が表す protocol の intervention（README §2）。"""
    replace = {"weights": [f"connections.{f}" for f in W.BLOCKS["weights"][1]],
               "units": [f"units.{f}" for f in W.BLOCKS["units"][0]] + [f"connections.{f}" for f in W.BLOCKS["units"][1]]}
    return {"kind": "state_block_swap",
            "swap_time": {"rule": W.SWAP_TIME_RULE, "state": "end_of_pulse_tau",
                          "if_none": "individual_not_outside_for_all_eight_judgments_and_reported",
                          "no_tau": {"valid": True, "seed_status": "completed", "swapped_and_control_bodies": "not_created"}},
            "recipient": W.RECIPIENT, "donors": list(W.DONORS), "reference_donors": list(W.REFERENCE),
            "blocks": {"weights": {"family": W.FAMILY_OF["weights"], "replace": replace["weights"]},
                       "units": {"family": W.FAMILY_OF["units"], "replace": replace["units"],
                                 "keep": [f"units.{f}" for f in W.KEPT_UNIT_FIELDS]}},
            "swapped_bodies": W.SWAPPED_BODIES,
            "control_bodies": {"full_swap": W.FULL_SWAP, "null_swap": W.NULL_SWAP},
            "plasticity_after_swap": True,
            "invariants_checked_on_swapped_state": {"I1_pair_sum_tolerance": 1.0e-12, "I2_trace_per_unit": "exact",
                                                    "I3_activity_positive": "exact", "I4_no_drives_at_tau": "exact"},
            "implementation": "core_public_import_state_only"}


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

    # 脳の設計図（README §1。0026・0028 と同じ C0）
    brain = protocol["brain"]
    expect(brain == BRAIN, "設計図・Receptor・不応期・可塑性の対象が 0026・0028 の C0 と違う")
    raw = W.manifest_raw(protocol)
    base = yaml.safe_load((ROOT / BRAIN["dynamics_from"]).read_text(encoding="utf-8"))
    expect(raw["defaults"]["dynamics"] == base["defaults"]["dynamics"], "設計図の力学が minimal-v3 と違う")
    expect(raw["defaults"]["dynamics"]["refractory_pulses"] == 0, "不応期が 0 ではない")
    expect(raw["defaults"]["dynamics"]["adaptation_tau"] == 300, "順応の時定数 τ_a が 300 ではない（遅れ 5τ_a の根拠）")
    m = parse_neuroarchitecture(raw)
    units = list(BRAIN["sensory_units"])
    expect({(p.source_id, p.target_id) for p in m.projections if p.source_id in units}
           == set(itertools.permutations(units, 2)), "s のあいだの接続が相互の 6 本ではない")
    expect(all(p.plastic and p.weight == m.plasticity.w_max / 2 == 0.005 for p in m.projections if p.source_id in units),
           "s のあいだの 6 本が、すべて可塑性の対象・初期の重み w_max／2 ＝ 0.005 ではない")
    expect({p.source_id: p.target_id for p in m.projections if p.source_id in BRAIN["receptors"]} == BRAIN["receptors"]
           and len(m.projections) == 9, "Receptor → s の対応が protocol と違うか、接続が 9 本ではない")
    expect(m.plasticity.w_max == raw["defaults"]["dynamics"]["adaptation_increment"] == 0.01, "w_max ＝ α ＝ 0.01 ではない")

    # 時間の流れ（README §1・§2.2）
    tl = protocol["timeline"]
    expect(tl == {"pulse_interval_seconds": 1.0, "trials": {"first": 1, "every": 60, "count": 200},
                  "experience_end": W.EXPERIENCE_END, "delay": W.DELAY, "count_window_main": W.COUNT_WINDOW_MAIN,
                  "swap_window": W.SWAP_WINDOW, "body_runs_to": W.BODY_RUNS_TO},
           "時間の流れ（試行・遅れ・主の区間・τ の窓・本体の終わり）の式が道具と違う")
    plan = W.plan_from(protocol)
    expect((plan.trials, plan.experience_end, plan.delay, plan.swap_window, plan.main, plan.body_end, plan.first_stimulus)
           == (200, 12000, 1500, (13441, 13500), (13501, 25500), 25500, (1, 2)),
           "Plan が 試行 200・経験の終わり 12000・遅れ 1500・τ の窓 13441〜13500・主の区間 13501〜25500・本体の終わり 25500 ではない")
    expect(plan.swap_window[1] - plan.swap_window[0] + 1 == tl["trials"]["every"] == 60, "τ の窓の幅が trials.every（60）ではない")
    expect(list(plan.snapshots) == SNAPSHOTS and list(plan.swapped_snapshots) == SNAPSHOTS[1:],
           "全状態を残す時点が 12000・13500・25500（入れ替えた本体は 13500・25500）ではない")

    # 刺激と条件（README §2.1）
    st = protocol["stimulus"]
    expect((st["b_offset"], st["c_offset"]) == (2, 30) and st["counts"] == {r: plan.trials for r in W.ROLES},
           "刺激の形・数が 0028 と違う（各 200 ＝ 試行の数）")
    expect(0 < st["b_offset"] < st["c_offset"] < tl["trials"]["every"], "試行の中の 3 つの枠が試行の中に順に収まらない")
    expect(st["role_assignment"] == W.ROLE_ASSIGNMENT, "役の割り当ての式が道具と違う")
    expect(sorted(map(tuple, st["role_orders"])) == sorted(itertools.permutations(BRAIN["receptors"])),
           "role_orders が Receptor の 6 通りの並べ方ではない")
    cond = protocol["conditions"]
    expect(cond == {"O": {"schedule": W.SCHEDULES["O"]}, "M": {"schedule": W.SCHEDULES["M"]},
                    "within_trial_shuffles": {"count": 20, "schedule": W.SCHEDULES["within_trial_shuffles"],
                                              "rng": f"{exp}-within-trial-{{i}}:{{seed}}",
                                              "procedure": W.WITHIN_TRIAL_PROCEDURE},
                    "input_after_experience": "none", "probes": "none"},
           "条件（O・M・試行の中の並べ替え 20・その手順・経験の後の入力なし・試しなし）が道具と違う")
    expect(W.RNG_SHUFFLE == cond["within_trial_shuffles"]["rng"] and W.K == 20 and len(W.BODIES) == 22,
           "試行の中の並べ替えの乱数の流れ・数が道具と違う")

    # 介入（README §2）
    expect(protocol["intervention"] == intervention_of(W),
           "介入（τ の規則・τ がない個体・受け手・ドナー・塊・入れ替えた本体・確認の本体・不変の関係）が道具と違う")
    expect(W.RECIPIENT == "W20" and W.DONORS == ("O", "M") + tuple(REF) and W.REFERENCE == tuple(REF)
           and W.RECIPIENT not in W.DONORS, "受け手・ドナー・参照のドナーが W20・(O, M, W1〜W19)・W1〜W19 ではない")
    every = set(W.BLOCKS["weights"][1]) | set(W.BLOCKS["units"][1])
    expect(not (set(W.BLOCKS["weights"][1]) & set(W.BLOCKS["units"][1])) and every == set(W.CONNECTION_FIELDS)
           and not W.BLOCKS["weights"][0] and set(W.BLOCKS["units"][0]) | set(W.KEPT_UNIT_FIELDS) == set(W.UNIT_FIELDS),
           "2 つの塊が、発火の回数を除く Unit・接続の欄を重ならずに覆っていない")

    # 量・判定・記録・確認（README §3〜§8）
    expect(protocol["quantities"] == QUANTITIES, "主・補助の量の定義が道具の実装と違う")
    expect(all(tuple(QUANTITIES["primary"]["per_individual"][f]) == W.EVENTS[f] for f in FAMILIES),
           "8 つの事象の名前が道具（τ がない個体の事象）と違う")
    j = protocol["judgment"]
    expect(j == JUDGMENT, "判定の決まりが道具の実装と違う")
    pf = j["per_family"]
    n = len(rng["seeds"])
    k = len(REF)
    split = {J: Fraction(str(pf["alpha_split"][J])) for J in JUDGMENTS}
    for f in FAMILIES:
        expect(sum(split.values()) == Fraction(str(j["families"][f]["alpha"])) == Fraction(1, 20),
               f"{f}：家族の中の水準の割り当ての和が家族の水準 0.05 ではない")
        expect(j["families"][f]["direction"] == ("one_sided" if SIDES[f] == 1 else "two_sided"), f"{f}：判定の向きが道具と違う")
        for J in JUDGMENTS:
            p0 = per_individual_null(f, J, k)
            spec = pf[f][J]
            expect(Fraction(spec["per_individual_null_probability_at_most"]) == p0, f"{f}・{J}：各個体の帰無の確率が {p0} ではない")
            expect(spec["statistic"] == STATISTIC[J] and spec["holds_if"] == f"{STATISTIC[J]} >= {HOLDS_MIN[f][J]}",
                   f"{f}・{J}：統計・成立の条件が道具と違う")
            expect(binom_tail(n, p0, HOLDS_MIN[f][J]) <= split[J] < binom_tail(n, p0, HOLDS_MIN[f][J] - 1),
                   f"{f}・{J}：閾値 {HOLDS_MIN[f][J]} が、P(Bin({n}, {p0}) ≥ h) ≤ {split[J]} となる最小の h ではない")
            expect(QUANTITIES["primary"]["across_individuals"][f][STATISTIC[J]] == f"count({EVENT[f][J]})",
                   f"{f}・{J}：統計の数える事象が道具と違う")
    expect(protocol["records"] == RECORDS and tuple(RECORDS["full_state_fields"]) == W.FULL_STATE_FIELDS,
           "記録の項目が道具の実装と違う")
    expect(protocol["checks"] == CHECKS, "操作の確認の項目・時点・許容・τ がない個体での適用が道具の実装と違う")

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
