"""protocol.yaml（確定した事前登録 v0.1 の正本）と、0027 の設計図（C0）・道具が同じ条件かを機械的に確かめる。

ズレていたら実行・解析を止める。run.py と analyze.py の両方が最初に呼ぶ。protocol は変えない（道具の側をこれに合わせる）。
実験の ID は、このフォルダの名前の先頭（"0027_delayed_order_readout" → "0027"）から決め、protocol の experiment・
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
# 0023〜0026 の本番・smoke・合成（予約した範囲ごと））。重なってはいけない
SEEN = (set(range(1, 21)) | set(range(1001, 1021)) | set(range(2001, 2021)) | set(range(3001, 3007))
        | set(range(4001, 4021)) | set(range(5001, 5007)) | set(range(6001, 6021)) | set(range(7001, 7007))
        | set(range(8001, 8021)) | set(range(8101, 8107)) | set(range(9001, 9700))
        | set(range(10001, 10021)) | set(range(10101, 10107)) | set(range(11001, 11021))
        | set(range(11101, 11107)) | set(range(12001, 12021)) | set(range(12101, 12107))
        | set(range(13001, 13201)) | set(range(14001, 14201)) | set(range(15001, 15201)) | set(range(16001, 16300))
        | set(range(17001, 17300)) | set(range(18001, 18300)) | set(range(19001, 19300)))
# 判定の閾値（README §5.2）：各個体の帰無の確率 2／(K ＋ 1) ＝ 0.1 のもとで P(Bin(20, 0.1) ≥ h) ≤ alpha となる最小の h
HOLDS_MIN_H = 5
MANIFEST = "experiments/0012_passive_world/neuroarchitecture.yaml"   # 0014〜0026 と同じ設計図（C0）
EXACT_CHECKS = ["stimulus_labels", "input_free_after_experience", "identical_before_label_divergence",
                "probe_clone_equals_body_t0_minus_1", "identical_through_t0_plus_1", "proposition_3",
                "empty_side_identity", "O_twin_identity", "censor_arithmetic_recomputed", "no_clipping"]
NUMERIC_CHECKS = {"replay_history_12000": 1.0e-12, "replay_history_late_start": 1.0e-12, "pair_sum": 1.0e-12}
_SILENCE = "count over 20 bodies of (censor_counts.{w}.{r}_A == 300 and censor_counts.{w}.{r}_null == 300)"
QUANTITIES = {
    "primary": {"per_probe": {"ell_B": "n_B_null - n_B_A", "ell_C": "n_C_null - n_C_A"},
                "per_body": {"L_late": "mean_over_probes_late(ell_B - ell_C)"},
                "per_individual": {"outside_late": "L_late(O) > max_i L_late(W_i) or L_late(O) < min_i L_late(W_i)"},
                "across_individuals": {"h_late": "count(outside_late)"}},
    "auxiliary": {
        "per_body": {"L_early": "mean_over_probes_early(ell_B - ell_C)",
                     "L_B": {"early": "mean_over_probes_early(ell_B)", "late": "mean_over_probes_late(ell_B)"},
                     "L_C": {"early": "mean_over_probes_early(ell_C)", "late": "mean_over_probes_late(ell_C)"},
                     "censor_counts": {"early": ["B_A", "B_null", "C_A", "C_null"], "late": ["B_A", "B_null", "C_A", "C_null"]}},
        "per_individual": {
            "outside_early": "L_early(O) > max_i L_early(W_i) or L_early(O) < min_i L_early(W_i)",
            "rank_of_L_O_among_20": ["early", "late"],
            "direction_counts": ["early", "late"],
            # 300 は試しの数（analyze.py は len(plan.probes(w)) と比べる。本番の Plan では 300）
            "silence_counts": {w: {r: _SILENCE.format(w=w, r=r) for r in ("B", "C")} for w in ("early", "late")}},
        "across_individuals": {"h_early": "count(outside_early)",
                               "early_late_table": "counts of individuals by (outside_early, outside_late)",
                               "clopper_pearson_95_of_h_over_20": ["late", "early"]}},
    "not_used": ["effect_size_threshold", "population_fraction_claims", "ratios", "normalizations", "combined_scores",
                 "post_hoc_windows", "post_hoc_probe_ranges", "post_hoc_delays", "comparison_between_h_early_and_h_late",
                 "decay_tests", "comparison_with_earlier_experiments_h", "individual_eligibility_filters",
                 "selection_by_outside_early", "mirror_condition", "between_trial_shuffle_reference"],
}
JUDGMENT_FIXED = {"statistic": "h_late", "holds_if": "h >= 5", "alpha": 0.05,
                  "holds_means": "reject_null_at_alpha_under_assumptions",
                  "per_individual_null_probability_at_most": 0.1, "frozen_individuals": "count_as_not_outside",
                  "on_any_invalid": "experiment_invalid_no_judgment",
                  "scope": "C0_relative_to_within_trial_shuffle_reference_at_late_probe_window_after_5_tau_a",
                  "not_judged": ["mechanism_of_persistence", "decay_between_probe_windows", "memory_formation"]}
_A_STATES = ["full_state_end_t0_minus_1_after_clone", "full_state_end_t0", "full_state_end_t0_plus_1"]
RECORDS = {"full_state_fields": ["pulse", "units", "connections", "drives", "deltas"],
           "full_state_values_not_digests": True,
           "per_body": ["birth_state", "label_sequence", "spikes_1_to_end", "full_state_12000",
                        "full_state_each_pulse_early_range", "full_state_each_pulse_late_range"],
           "early_range": "experience_end - 1 .. probes_early.first + probes_early.count - 1 + 1 + window_pulses",
           "late_range": "probes_late.first - 1 .. body_runs_to",
           "per_probe_A_copy_late": _A_STATES + ["spikes_t0_to_window_end", "full_state_window_end"],
           "per_probe_A_copy_early": {"all_probes": ["spikes_t0_to_window_end"],
                                      "first_and_last": _A_STATES + ["full_state_window_end"]},
           "empty_side_copies": {"windows": ["probes_early", "probes_late"], "probes": ["first", "last"],
                                 "keep": ["spikes_to_window_end", "full_state_each_pulse"]},
           "O_twin_without_probes": {"keep": ["spikes_1_to_end", "full_state_12000", "full_state_late_first_minus_1",
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

    # 脳の設計図（README §1。0025 と同じ C0）
    brain = protocol["brain"]
    expect(brain["manifest"] == MANIFEST, "設計図が 0014〜0026 と同じではない")
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
    expect(raw["defaults"]["dynamics"]["adaptation_tau"] == 300, "順応の時定数 τ_a が 300 ではない（D ＝ 5τ_a の根拠）")

    # 時間の流れ（README §2・§3）
    tl = protocol["timeline"]
    expect(tl["pulse_interval_seconds"] == 1.0 and tl["trials"] == {"first": 1, "every": 60, "count": 200},
           "試行・Pulse の長さが 0025 と違う")
    expect(tl["experience_end"] == W.EXPERIENCE_END and tl["delay"] == W.DELAY and tl["window_pulses"] == W.WINDOW_PULSES
           and tl["probes_early"] == W.PROBES["early"] and tl["probes_late"] == W.PROBES["late"]
           and tl["body_runs_to"] == W.BODY_RUNS_TO, "時間の流れ（遅れ・二つの試しの区間・本体の終わり）の式が道具と違う")
    plan = W.plan_from(protocol)
    expect((plan.trials, plan.experience_end, plan.delay, plan.probes_early[0], plan.probes_early[-1], len(plan.probes_early),
            plan.probes_late[0], plan.probes_late[-1], len(plan.probes_late), plan.window, plan.body_end)
           == (200, 12000, 1500, 12001, 12300, 300, 13501, 13800, 300, 300, 14101),
           "Plan が 試行 200・経験の終わり 12000・遅れ 1500・早い時点 12001〜12300・遅い時点 13501〜13800・T_w 300・"
           "本体の終わり 14101 ではない")
    expect((plan.state_range("early"), plan.state_range("late")) == ((11999, 12601), (13500, 14101)),
           "全状態を残す範囲が 11999〜12601・13500〜14101 ではない")

    # 刺激と条件（README §2.1）
    st = protocol["stimulus"]
    expect((st["b_offset"], st["c_offset"]) == (2, 30) and st["counts"] == {r: plan.trials for r in W.ROLES},
           "刺激の形・数が 0025 と違う（各 200 ＝ 試行の数）")
    expect(0 < st["b_offset"] < st["c_offset"] < tl["trials"]["every"], "試行の中の 3 つの枠が試行の中に順に収まらない")
    expect(st["role_assignment"] == W.ROLE_ASSIGNMENT, "役の割り当ての式が道具と違う")
    expect(sorted(map(tuple, st["role_orders"])) == sorted(itertools.permutations(brain["receptors"])),
           "role_orders が Receptor の 6 通りの並べ方ではない")
    cond = protocol["conditions"]
    expect(cond == {"O": {"schedule": W.SCHEDULES["O"]},
                    "within_trial_shuffles": {"count": 19, "schedule": W.SCHEDULES["within_trial_shuffles"],
                                              "rng": f"{exp}-within-trial-{{i}}:{{seed}}",
                                              "procedure": W.WITHIN_TRIAL_PROCEDURE},
                    "input_after_experience": "none"},
           "条件（O・試行の中の並べ替え 19・その手順・経験の後の入力なし。M なし）が道具と違う")
    expect(W.RNG_SHUFFLE == cond["within_trial_shuffles"]["rng"] and W.K == 19 and len(W.BODIES) == 20,
           "試行の中の並べ替えの乱数の流れ・数が道具と違う")

    # 試し（README §2.2・§2.3）
    expect(protocol["probe"] == {"windows": ["probes_early", "probes_late"], "base": W.PROBE_BASE, "A_copy": W.A_COPY,
                                 "null_side": W.NULL_SIDE, "window": W.WINDOW, "first_fire_censor_value": W.CENSOR,
                                 "early_probes_do_not_change_body": True}, "試しの手順が道具と違う")

    # 量・判定・記録・確認（README §4〜§8）
    expect(protocol["quantities"] == QUANTITIES, "主・補助の量の定義が道具の実装と違う")
    j = protocol["judgment"]
    expect({k: j[k] for k in JUDGMENT_FIXED} == JUDGMENT_FIXED, "判定の決まりが道具の実装と違う")
    p0 = Fraction(2, cond["within_trial_shuffles"]["count"] + 1)
    expect(p0 == Fraction(1, 10) == Fraction(j["per_individual_null_probability_at_most"]).limit_denominator(1000),
           "各個体の帰無の確率 2／(K ＋ 1) が 0.1 ではない")
    n = len(rng["seeds"])
    alpha = Fraction(j["alpha"]).limit_denominator(1000)
    expect(binom_tail(n, p0, HOLDS_MIN_H) <= alpha < binom_tail(n, p0, HOLDS_MIN_H - 1),
           "h ≥ 5 が、P(Bin(20, 0.1) ≥ h) ≤ alpha となる最小の h ではない")
    expect(protocol["records"] == RECORDS, "記録の項目が道具の実装と違う")
    expect(tuple(protocol["records"]["full_state_fields"]) == W.FULL_STATE_FIELDS
           and protocol["records"]["early_range"] == W.EARLY_RANGE and protocol["records"]["late_range"] == W.LATE_RANGE,
           "全状態の欄・範囲が道具と違う")
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
