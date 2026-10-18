"""protocol.yaml（確定した事前登録 v0.2 の正本）と、0028 の二つの設計図（C0・V1）・道具が同じ条件かを機械的に確かめる。

ズレていたら実行・解析を止める。run.py と analyze.py の両方が最初に呼ぶ。protocol は変えない（道具の側をこれに合わせる）。
実験の ID は、このフォルダの名前の先頭（"0028_lag1_successor_asymmetry" → "0028"）から決め、protocol の experiment・
execution（ID・出力先・protocol のパス）・乱数の流れの名前がそれと一致することを確かめる。

V1 の設計図（README §1.1）：brains.V1.manifest（このフォルダの neuroarchitecture-v1.yaml）を YAML として読んだ値が、
brains.V1.derived_from（＝ brains.C0.manifest）を YAML として読んだ値から、s のあいだの 6 本の plastic: true だけを除いたものと
完全に同じであること（YAML の設定値と配線。ファイルの注釈は比べない）。brains.V1.variant の後半の「Body identical to …」は
記述の注で、道具はそのファイルを読まない（形だけを確かめる）。

主の判定（README §4、protocol の judgment.per_family）は、各家族（C0・V1）に J_Ca・J_O・J_M・J_OM の 4 つ。J_Ca は補助ではなく
正式な主の判定である（judgment.scope の要約の文字列は D だけを書いているが、機械的な主の判定は per_family の 4 つ）。
閾値は、割り当てた水準と K から決まる最小の整数であることを、二項分布の上側の確率を厳密に計算して確かめる。
"""

import copy
import importlib.util
import itertools
import math
import re
from fractions import Fraction
from pathlib import Path

import yaml

from anima_ll.adapter.config.yaml_config_source import parse_neuroarchitecture

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXPERIMENT_FROM_DIR = HERE.name.split("_")[0]
# これまでに走らせた seed（0012〜0019 の判定・事後の解析・動作確認、0020 の探索と合成・確認、0021・0022 の本番と合成・確認、
# 0023〜0027 の本番・smoke・合成（予約した範囲ごと））。重なってはいけない
SEEN = (set(range(1, 21)) | set(range(1001, 1021)) | set(range(2001, 2021)) | set(range(3001, 3007))
        | set(range(4001, 4021)) | set(range(5001, 5007)) | set(range(6001, 6021)) | set(range(7001, 7007))
        | set(range(8001, 8021)) | set(range(8101, 8107)) | set(range(9001, 9700))
        | set(range(10001, 10021)) | set(range(10101, 10107)) | set(range(11001, 11021))
        | set(range(11101, 11107)) | set(range(12001, 12021)) | set(range(12101, 12107))
        | set(range(13001, 13201)) | set(range(14001, 14201)) | set(range(15001, 15201)) | set(range(16001, 16300))
        | set(range(17001, 17300)) | set(range(18001, 18300)) | set(range(19001, 19300)) | set(range(20001, 20300)))

# 主の判定（README §4.1・§4.3）。J_Ca は C-a の正式な主の判定（補助ではない）
JUDGMENTS = ("J_Ca", "J_O", "J_M", "J_OM")
STATISTIC = {"J_Ca": "h_Ca", "J_O": "h_O", "J_M": "h_M", "J_OM": "h_OM"}
EVENT = {"J_Ca": "O_Delta_AB_above", "J_O": "O_above", "J_M": "M_below", "J_OM": "O_and_M_split"}
# 閾値：割り当てた水準 alpha_J のもとで P(Bin(20, p0_J) ≥ h) ≤ alpha_J となる最小の h（check で厳密に確かめる）
HOLDS_MIN = {"J_Ca": 4, "J_O": 4, "J_M": 4, "J_OM": 2}

MANIFEST_C0 = "experiments/0012_passive_world/neuroarchitecture.yaml"   # 0014〜0027 と同じ設計図（C0）
VARIANT = "remove plastic: true from the six s-s projections; all other YAML settings and wiring identical (header comments differ)."
VARIANT_NOTE = re.compile(r" Body identical to experiments/\d{4}_[a-z0-9_]+/neuroarchitecture-v1\.yaml")
COMMON = {"dynamics_from": "config/neuroarchitecture/minimal-v3.yaml", "sensory_units": ["s1", "s2", "s3"],
          "receptors": {"receptor.x1": "s1", "receptor.x2": "s2", "receptor.x3": "s3"}, "refractory_pulses": 0}

QUANTITIES = {
    "per_body": {"N": "N_{X->Y} = #{ t : S <= t <= E - 1, s_X(t) = 1, s_Y(t + 1) = 1 } for ordered pairs X != Y",
                 "Delta_AB": "N_{A->B} - N_{B->A}", "Delta_AC": "N_{A->C} - N_{C->A}", "D": "Delta_AB - Delta_AC"},
    "primary": {"window": "count_window_main",
                "per_individual_and_design": {"O_Delta_AB_above": "Delta_AB(O) > max_i Delta_AB(W_i)",
                                              "O_above": "D(O) > max_i D(W_i)", "M_below": "D(M) < min_i D(W_i)",
                                              "O_and_M_split": "O_above and M_below"},
                "across_individuals_per_design": {"h_Ca": "count(O_Delta_AB_above)", "h_O": "count(O_above)",
                                                  "h_M": "count(M_below)", "h_OM": "count(O_and_M_split)"}},
    "auxiliary": {
        "per_body": ["six_N_counts_per_window", "Delta_AB", "Delta_AC", "Delta_BC", "spike_counts_per_unit_per_window",
                     "silent_units_main_window"],
        "per_body_C0_only": ["weights_at_12000", "weights_at_13500", "weights_at_25500"],
        "per_individual_and_design": {
            "C_a_form_for_M": "Delta_AC(M) > max_i Delta_AC(W_i)",
            "opposite_direction": ["Delta_AB(O) < min_i Delta_AB(W_i)", "D(O) < min_i D(W_i)", "D(M) > max_i D(W_i)"],
            "ranks": ["rank_of_Delta_AB_O_among_W", "rank_of_D_O_among_W", "rank_of_D_M_among_W"],
            "early_window_same_four_events": True,
            "C0_weight_ranks": "ranks of w(A->B), w(A->C), w(B->C) of O and M among W at 12000, 13500, 25500 (descriptive only)",
            "frozen_per_judgment": True},
        "across_individuals_per_design": {"counts_of_each_auxiliary_event": True,
                                          "clopper_pearson_95_of_h_over_20": ["h_Ca", "h_O", "h_M", "h_OM"]}},
    "not_used": ["effect_size_threshold", "population_fraction_claims", "ratios", "normalizations", "rates", "weighted_lag_sums",
                 "combined_scores", "post_hoc_windows", "post_hoc_lags", "two_sided_tests", "comparison_between_designs",
                 "comparison_with_earlier_experiments", "individual_eligibility_filters", "selection_by_auxiliary_events",
                 "probe_readouts", "between_trial_shuffle_reference"],
}
JUDGMENT = {
    "families": {"C0": {"design": "C0", "alpha": 0.05}, "V1": {"design": "V1", "alpha": 0.05}},
    "experiment_wide_error_rate_claimed": "none",
    "per_family": {
        "alpha_split": {"J_Ca": 0.016, "J_O": 0.016, "J_M": 0.016, "J_OM": 0.002},
        "J_Ca": {"statistic": "h_Ca", "holds_if": "h_Ca >= 4",
                 "null_hypothesis": "for every individual, Delta_AB(O) is exchangeable with Delta_AB(W_1..W_19)",
                 "per_individual_null_probability_at_most": 0.05, "direction": "O_Delta_AB_above_only", "corresponds_to": "C-a"},
        "J_O": {"statistic": "h_O", "holds_if": "h_O >= 4",
                "null_hypothesis": "for every individual, D(O) is exchangeable with D(W_1..W_19)",
                "per_individual_null_probability_at_most": 0.05, "direction": "O_above_only"},
        "J_M": {"statistic": "h_M", "holds_if": "h_M >= 4",
                "null_hypothesis": "for every individual, D(M) is exchangeable with D(W_1..W_19)",
                "per_individual_null_probability_at_most": 0.05, "direction": "M_below_only"},
        "J_OM": {"statistic": "h_OM", "holds_if": "h_OM >= 2",
                 "null_hypothesis": "for every individual, D(O), D(M), D(W_1..W_19) (21 values) are exchangeable",
                 "per_individual_null_probability_at_most": "1/420", "direction": "O_above_and_M_below"}},
    "independence_assumption": ("birth states and within-trial shuffle RNG streams are treated as independent across individuals "
                                "(statistical model assumption; not implied by distinct seeds)"),
    "holds_means": "reject_null_at_alpha_under_assumptions",
    "ties": "strict_inequality_counts_ties_as_not_outside",
    "frozen_individuals": "count_as_not_outside",
    "on_any_invalid": "experiment_invalid_no_judgment",
    "scope": ("C0_and_V1_spontaneous_lag1_asymmetry_D_in_input_free_window_13501_25500_relative_to_within_trial_shuffle_reference_"
              "direction_fixed_by_theory"),
    "content_claimed": ("only whether the element that followed A at lag 2 (B in O, C in M) is reflected; not three-element order, "
                        "not intervals"),
    "not_judged": ["memory_formation", "meaning", "weight_carried_content", "quantity_only_difference_excluded",
                   "firing_count_robustness_of_D", "C_a_for_M", "three_element_order", "intervals",
                   "learning_contribution_from_comparing_families", "mechanism"],
}
RECORDS = {"full_state_fields": ["pulse", "units", "connections", "drives", "deltas"], "full_state_values_not_digests": True,
           "per_body": ["design", "birth_state", "label_sequence", "spikes_1_to_end", "full_state_12000", "full_state_13500",
                        "full_state_25500"]}
SNAPSHOTS = [12000, 13500, 25500]
CHECKS = {"exact": ["stimulus_labels", "identical_birth_state_all_42_bodies", "input_free_after_experience",
                    "identical_before_label_divergence_within_each_design", "C0_no_clipping",
                    "V1_connections_empty_all_recorded_states", "V1_s_to_s_drive_weights_all_0_005",
                    "receptor_drive_weights_all_1_0", "lag1_counts_two_ways"],
          "numeric": {"C0_replay_weights_and_traces": {"at": SNAPSHOTS, "tolerance": 1.0e-12},
                      "C0_pair_sum": {"at": SNAPSHOTS, "tolerance": 1.0e-12}},
          "revalidate_from_raw": True, "invalid_individuals": "report_all"}
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


def per_individual_null(judgment: str, k: int) -> Fraction:
    """README §4.2：J_Ca・J_O・J_M は 1／(K ＋ 1)、J_OM は O が 21 個の最大かつ M が最小になる確率 1／((K ＋ 2)(K ＋ 1))。"""
    return Fraction(1, (k + 2) * (k + 1)) if judgment == "J_OM" else Fraction(1, k + 1)


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

    # 二つの設計図（README §1・§1.1）
    brains = protocol["brains"]
    expect(set(brains) == {"C0", "V1", "common"} and brains["common"] == COMMON, "brains の項目・共通の値が想定と違う")
    units = list(COMMON["sensory_units"])
    expect(brains["C0"] == {"manifest": MANIFEST_C0, "plastic_connections": "six_s_to_s"}, "C0 の設計図が 0014〜0027 と同じではない")
    v1 = brains["V1"]
    expect(set(v1) == {"manifest", "derived_from", "variant", "fixed_weights", "plastic_connections"}
           and v1["manifest"] == f"experiments/{HERE.name}/neuroarchitecture-v1.yaml" and v1["derived_from"] == MANIFEST_C0
           and v1["plastic_connections"] == "none" and v1["fixed_weights"] == {"s_to_s": 0.005},
           "V1 の設計図・元の設計図・固定した重みが想定と違う")
    variant = v1.get("variant", "")
    expect(variant.startswith(VARIANT) and VARIANT_NOTE.fullmatch(variant[len(VARIANT):]) is not None,
           "V1 の変種の説明が想定と違う")
    raw_c0, raw_v1 = W.manifest_raw(protocol, "C0"), W.manifest_raw(protocol, "V1")
    base = yaml.safe_load((ROOT / COMMON["dynamics_from"]).read_text(encoding="utf-8"))
    expected_v1, removed = v1_from(raw_c0, units)
    expect(removed == 6, "C0 の s のあいだの可塑性の対象が 6 本ではない")
    expect(raw_v1 == expected_v1, "V1 の設計図が、C0 の設計図から s のあいだの 6 本の plastic: true だけを除いたものと違う")
    for design, raw in (("C0", raw_c0), ("V1", raw_v1)):
        expect(raw["defaults"]["dynamics"] == base["defaults"]["dynamics"], f"{design} の設計図の力学が minimal-v3 と違う")
        expect(raw["defaults"]["dynamics"]["refractory_pulses"] == COMMON["refractory_pulses"] == 0, f"{design} の不応期が 0 ではない")
        m = parse_neuroarchitecture(raw)
        expect({(p.source_id, p.target_id) for p in m.projections if p.source_id in units}
               == set(itertools.permutations(units, 2)), f"{design}：s のあいだの接続が相互の 6 本ではない")
        expect({p.source_id: p.target_id for p in m.projections if p.source_id in COMMON["receptors"]} == COMMON["receptors"]
               and all(p.weight == 1.0 for p in m.projections if p.source_id in COMMON["receptors"]),
               f"{design}：Receptor → s の対応・重み 1.0 が protocol と違う")
        expect(len(m.projections) == 9, f"{design}：接続が Receptor → s の 3 本と s のあいだの 6 本ではない")
        expect(m.plasticity.w_max == raw["defaults"]["dynamics"]["adaptation_increment"] == 0.01, f"{design}：w_max ＝ α ＝ 0.01 ではない")
        expect(raw["defaults"]["dynamics"]["adaptation_tau"] == 300, f"{design}：順応の時定数 τ_a が 300 ではない（D ＝ 5τ_a の根拠）")
        expect(all(p.weight == m.plasticity.w_max / 2 == 0.005 for p in m.projections if p.source_id in units),
               f"{design}：s のあいだの 6 本の初期の重みが w_max／2 ＝ 0.005 ではない")
        expect(W.projection_weights(protocol, design) == {(p.source_id, p.target_id): p.weight for p in m.projections},
               f"{design}：道具が読む接続の重みが設計図と違う")
        plastic = {(p.source_id, p.target_id) for p in m.projections if p.plastic}
        expect(plastic == (set(itertools.permutations(units, 2)) if design == "C0" else set()),
               f"{design}：可塑性の対象の接続が想定（C0：s のあいだの 6 本、V1：なし）と違う")

    # 時間の流れ（README §2.2・§3.4）
    tl = protocol["timeline"]
    expect(tl["pulse_interval_seconds"] == 1.0 and tl["trials"] == {"first": 1, "every": 60, "count": 200},
           "試行・Pulse の長さが 0025 と違う")
    expect(tl == {"pulse_interval_seconds": 1.0, "trials": tl["trials"], "experience_end": W.EXPERIENCE_END, "delay": W.DELAY,
                  "count_window_main": W.COUNT_WINDOW_MAIN, "count_window_early": W.COUNT_WINDOW_EARLY,
                  "body_runs_to": W.BODY_RUNS_TO}, "時間の流れ（遅れ・二つの区間・本体の終わり）の式が道具と違う")
    plan = W.plan_from(protocol)
    expect((plan.trials, plan.experience_end, plan.delay, plan.early, plan.main, plan.body_end, plan.first_stimulus)
           == (200, 12000, 1500, (12001, 13500), (13501, 25500), 25500, (1, 2)),
           "Plan が 試行 200・経験の終わり 12000・遅れ 1500・早い区間 12001〜13500・主の区間 13501〜25500・本体の終わり 25500 ではない")
    expect(plan.main[1] - plan.main[0] + 1 == tl["trials"]["count"] * tl["trials"]["every"] == 12000,
           "主の区間の長さが経験の長さ（12000）ではない")
    expect(list(plan.snapshots) == SNAPSHOTS, "全状態を残す時点が 12000・13500・25500 ではない")

    # 刺激と条件（README §2.1）
    st = protocol["stimulus"]
    expect((st["b_offset"], st["c_offset"]) == (2, 30) and st["counts"] == {r: plan.trials for r in W.ROLES},
           "刺激の形・数が 0025 と違う（各 200 ＝ 試行の数）")
    expect(0 < st["b_offset"] < st["c_offset"] < tl["trials"]["every"], "試行の中の 3 つの枠が試行の中に順に収まらない")
    expect(st["role_assignment"] == W.ROLE_ASSIGNMENT, "役の割り当ての式が道具と違う")
    expect(sorted(map(tuple, st["role_orders"])) == sorted(itertools.permutations(COMMON["receptors"])),
           "role_orders が Receptor の 6 通りの並べ方ではない")
    cond = protocol["conditions"]
    expect(cond == {"O": {"schedule": W.SCHEDULES["O"]}, "M": {"schedule": W.SCHEDULES["M"]},
                    "within_trial_shuffles": {"count": 19, "schedule": W.SCHEDULES["within_trial_shuffles"],
                                              "rng": f"{exp}-within-trial-{{i}}:{{seed}}",
                                              "procedure": W.WITHIN_TRIAL_PROCEDURE},
                    "designs": ["C0", "V1"], "input_after_experience": "none", "probes": "none"},
           "条件（O・M・試行の中の並べ替え 19・その手順・二つの設計・経験の後の入力なし・試しなし）が道具と違う")
    expect(W.RNG_SHUFFLE == cond["within_trial_shuffles"]["rng"] and W.K == 19 and len(W.BODIES) == 21
           and W.DESIGNS == ("C0", "V1"), "試行の中の並べ替えの乱数の流れ・数・設計が道具と違う")

    # 量・判定・記録・確認（README §3〜§8）
    expect(protocol["quantities"] == QUANTITIES, "主・補助の量の定義が道具の実装と違う")
    j = protocol["judgment"]
    expect(j == JUDGMENT, "判定の決まりが道具の実装と違う")
    pf = j["per_family"]
    n = len(rng["seeds"])
    k = cond["within_trial_shuffles"]["count"]
    four = tuple(pf.get("alpha_split", {})) == JUDGMENTS and set(pf) == set(JUDGMENTS) | {"alpha_split"}
    expect(four, "家族の中の判定が J_Ca・J_O・J_M・J_OM の 4 つではない（J_Ca も正式な主の判定）")
    split = {J: Fraction(str(pf["alpha_split"][J])) for J in JUDGMENTS} if four else {}
    for fam in j["families"].values():
        expect(sum(split.values()) == Fraction(str(fam["alpha"])) == Fraction(1, 20),
               "家族の中の水準の割り当ての和が家族の水準 0.05 ではない")
    for J in JUDGMENTS if four else ():
        p0 = per_individual_null(J, k)
        stated = pf[J]["per_individual_null_probability_at_most"]
        expect(Fraction(str(stated)) == p0, f"{J}：各個体の帰無の確率が {p0} ではない")
        expect(pf[J]["statistic"] == STATISTIC[J] and pf[J]["holds_if"] == f"{STATISTIC[J]} >= {HOLDS_MIN[J]}",
               f"{J}：統計・成立の条件が道具と違う")
        expect(binom_tail(n, p0, HOLDS_MIN[J]) <= split[J] < binom_tail(n, p0, HOLDS_MIN[J] - 1),
               f"{J}：閾値 {HOLDS_MIN[J]} が、P(Bin({n}, {p0}) ≥ h) ≤ {split[J]} となる最小の h ではない")
        expect(QUANTITIES["primary"]["across_individuals_per_design"][STATISTIC[J]] == f"count({EVENT[J]})",
               f"{J}：統計の数える事象が道具と違う")
    expect(protocol["records"] == RECORDS and tuple(RECORDS["full_state_fields"]) == W.FULL_STATE_FIELDS,
           "記録の項目が道具の実装と違う")
    expect(protocol["checks"] == CHECKS, "操作の確認の項目・時点・許容が道具の実装と違う")

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
