"""protocol.yaml（確定した事前登録 v0.1 の正本）と、0030 の設計図（C0）・F の変種・道具が同じ条件かを機械的に確かめる。

ズレていたら実行・解析を止める。run.py と analyze.py の両方が最初に呼ぶ。protocol は変えない（道具の側をこれに合わせる）。
実験の ID は、このフォルダの名前の先頭（"0030_post_experience_freeze_and_count_bound" → "0030"）から決め、protocol の experiment・
execution（ID・出力先・protocol のパス）・乱数の流れの名前がそれと一致することを確かめる。

下の QUANTITIES・JUDGMENT・RECORDS・CHECKS・F_VARIANT・FREEZE・CONDITIONS・TIMELINE は、確定した protocol.yaml（#130 の merge
`084ed38`）の各節の値をそのまま写した固定値（道具が実装している決まり）。check は protocol がこれと完全に同じことを確かめる。

主の判定（README §4・§5、protocol の judgment.per_family）は、F の家族と N^cnt の家族（どちらも一方向）に、それぞれ
J_Ca・J_O・J_M・J_OM の 4 つ。閾値は、割り当てた水準と K ＝ 19 から決まる最小の整数であることを、二項分布の上側の確率を厳密に
計算して確かめる。
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
# 0023〜0029 の本番・smoke・合成（予約した範囲ごと））。重なってはいけない
SEEN = (set(range(1, 21)) | set(range(1001, 1021)) | set(range(2001, 2021)) | set(range(3001, 3007))
        | set(range(4001, 4021)) | set(range(5001, 5007)) | set(range(6001, 6021)) | set(range(7001, 7007))
        | set(range(8001, 8021)) | set(range(8101, 8107)) | set(range(9001, 9700))
        | set(range(10001, 10021)) | set(range(10101, 10107)) | set(range(11001, 11021))
        | set(range(11101, 11107)) | set(range(12001, 12021)) | set(range(12101, 12107))
        | set(range(13001, 13201)) | set(range(14001, 14201)) | set(range(15001, 15201)) | set(range(16001, 16300))
        | set(range(17001, 17300)) | set(range(18001, 18300)) | set(range(19001, 19300)) | set(range(20001, 20300))
        | set(range(21001, 21300)) | set(range(22001, 22300)))

# 主の判定（README §4.2）
FAMILIES = ("F", "Ncnt")
JUDGMENTS = ("J_Ca", "J_O", "J_M", "J_OM")
STATISTIC = {"J_Ca": "h_Ca", "J_O": "h_O", "J_M": "h_M", "J_OM": "h_OM"}
EVENT = {"F": {"J_Ca": "O_Delta_AB_above", "J_O": "O_above", "J_M": "M_below", "J_OM": "O_and_M_split"},
         "Ncnt": {"J_Ca": "E_Ca_cnt", "J_O": "E_O_cnt", "J_M": "E_M_cnt", "J_OM": "E_OM_cnt"}}
# 閾値：割り当てた水準 alpha_J のもとで P(Bin(20, p0) ≥ h) ≤ alpha_J となる最小の h（check で厳密に確かめる）
HOLDS_MIN = {f: {"J_Ca": 4, "J_O": 4, "J_M": 4, "J_OM": 2} for f in FAMILIES}
STRUCTURAL_BOUND = -0.03                                         # g ＜ −0.03 が構造的、−0.03 ≤ g ＜ 0 が条件付き、g ≥ 0 が活動的
STRATA = ("structural", "conditional", "active")
NO_T0_REASON = "no_t0"

MANIFEST = "experiments/0012_passive_world/neuroarchitecture.yaml"   # 0014〜0029 と同じ設計図（C0）
BRAIN = {"manifest": MANIFEST, "dynamics_from": "config/neuroarchitecture/minimal-v3.yaml", "sensory_units": ["s1", "s2", "s3"],
         "receptors": {"receptor.x1": "s1", "receptor.x2": "s2", "receptor.x3": "s3"}, "refractory_pulses": 0,
         "plastic_connections": "six_s_to_s"}
REF = [f"W{i}" for i in range(1, 20)]

QUANTITIES = {'per_body': {'N': 'N_{X->Y} = #{ t : S <= t <= E - 1, s_X(t) = 1, s_Y(t + 1) = 1 } for ordered pairs X != Y',
              'Delta_AB': 'N_{A->B} - N_{B->A}',
              'Delta_AC': 'N_{A->C} - N_{C->A}',
              'D': 'Delta_AB - Delta_AC',
              'spike_count': 'N_X = #{ t : S <= t <= E, s_X(t) = 1 } for roles X in A, B, C'},
 'primary': {'window': 'count_window_main',
             'per_individual': {'F': {'O_Delta_AB_above': 'Delta_AB(F(O)) > max_i Delta_AB(F(W_i))',
                                      'O_above': 'D(F(O)) > max_i D(F(W_i))',
                                      'M_below': 'D(F(M)) < min_i D(F(W_i))',
                                      'O_and_M_split': 'O_above and M_below'},
                                'Ncnt': {'E_Ca_cnt': 'for all i: Delta_AB(O) - Delta_AB(W_i) > |N_A(O) - N_A(W_i)| + '
                                                     '|N_B(O) - N_B(W_i)|',
                                         'E_O_cnt': 'for all i: D(O) - D(W_i) > 2|N_A(O) - N_A(W_i)| + |N_B(O) - N_B(W_i)| '
                                                    '+ |N_C(O) - N_C(W_i)|',
                                         'E_M_cnt': 'for all i: D(W_i) - D(M) > 2|N_A(M) - N_A(W_i)| + |N_B(M) - N_B(W_i)| '
                                                    '+ |N_C(M) - N_C(W_i)|',
                                         'E_OM_cnt': 'E_O_cnt and E_M_cnt'}},
             'across_individuals': {'F': {'h_Ca': 'count(O_Delta_AB_above)',
                                          'h_O': 'count(O_above)',
                                          'h_M': 'count(M_below)',
                                          'h_OM': 'count(O_and_M_split)'},
                                    'Ncnt': {'h_Ca': 'count(E_Ca_cnt)',
                                             'h_O': 'count(E_O_cnt)',
                                             'h_M': 'count(E_M_cnt)',
                                             'h_OM': 'count(E_OM_cnt)'}}},
 'subset_proposition': 'each N^cnt event implies the corresponding 0028 event on the natural bodies (right-hand sides are '
                       '>= 0), so the per-individual null bounds 1/20 and 1/420 apply',
 'auxiliary': {'per_individual': {'freeze_time': True,
                                  'per_body_components': ['six_N_counts',
                                                          'Delta_AB',
                                                          'Delta_AC',
                                                          'Delta_BC',
                                                          'D',
                                                          'spike_counts_per_role',
                                                          'silent_roles'],
                                  'natural_0028_form_events': ['O_Delta_AB_above', 'O_above', 'M_below', 'O_and_M_split'],
                                  'ncnt_margins': 'for each N^cnt event: number of W_i satisfying the inequality, and the '
                                                  'largest (lhs - rhs) among the W_i not satisfying it',
                                  'F_ranks': ['rank_of_Delta_AB_FO_among_reference',
                                              'rank_of_D_FO_among_reference',
                                              'rank_of_D_FM_among_reference'],
                                  'F_opposite_direction': ['Delta_AB(F(O)) < min', 'D(F(O)) < min', 'D(F(M)) > max'],
                                  'frozen_per_judgment': {'F': 'all values used by the judgment are equal among F bodies',
                                                          'Ncnt': 'all values used by the judgment are equal among natural '
                                                                  'bodies (0028 form)'},
                                  'birth_margin_strata': {'g': 'g_i = intrinsic_drive_i / (1 - decay) - threshold_i for '
                                                               'roles A, B, C (birth Unit dynamics)',
                                                          'strata': {'structural': 'g_i < -0.03',
                                                                     'conditional': '-0.03 <= g_i < 0',
                                                                     'active': 'g_i >= 0'},
                                                          'record': 'per role and stratum: individuals, no-T0 individuals, '
                                                                    'and counts of each of the eight primary events'}},
               'across_individuals': {'counts_of_each_auxiliary_event': True,
                                      'no_t0_individuals': True,
                                      'clopper_pearson_95_of_h_over_20': ['F.h_Ca',
                                                                          'F.h_O',
                                                                          'F.h_M',
                                                                          'F.h_OM',
                                                                          'Ncnt.h_Ca',
                                                                          'Ncnt.h_O',
                                                                          'Ncnt.h_M',
                                                                          'Ncnt.h_OM']},
               'when_no_t0': {'recorded': ['natural_body_components_and_silence',
                                           'natural_0028_form_events',
                                           'ncnt_margins',
                                           'birth_margin_strata',
                                           'Ncnt_frozen'],
                              'null_with_reason_no_t0': ['F_body_components',
                                                         'F_ranks',
                                                         'F_opposite_direction',
                                                         'F_frozen',
                                                         'F_body_silence']}},
 'not_used': ['effect_size_threshold',
              'population_fraction_claims',
              'ratios',
              'normalizations',
              'rates',
              'weighted_lag_sums',
              'combined_scores',
              'post_hoc_windows',
              'post_hoc_lags',
              'contribution_shares',
              'comparison_between_families_h',
              'comparison_with_earlier_experiments_h',
              'individual_eligibility_filters',
              'selection_by_auxiliary_events',
              'selection_by_birth_margin_strata',
              'comparison_of_F_with_natural_bodies',
              'Ncnt_form_on_F_bodies',
              'decomposition_of_0029_Wt_effect',
              'probe_readouts',
              'between_trial_shuffle_reference']}

JUDGMENT = {'families': {'F': {'bodies': 'F_bodies', 'direction': 'one_sided', 'alpha': 0.05},
              'Ncnt': {'bodies': 'natural_bodies', 'direction': 'one_sided', 'alpha': 0.05}},
 'experiment_wide_error_rate_claimed': 'none',
 'per_family': {'alpha_split': {'J_Ca': 0.016, 'J_O': 0.016, 'J_M': 0.016, 'J_OM': 0.002},
                'F': {'J_Ca': {'statistic': 'h_Ca',
                               'holds_if': 'h_Ca >= 4',
                               'per_individual_null_probability_at_most': '1/20'},
                      'J_O': {'statistic': 'h_O', 'holds_if': 'h_O >= 4', 'per_individual_null_probability_at_most': '1/20'},
                      'J_M': {'statistic': 'h_M', 'holds_if': 'h_M >= 4', 'per_individual_null_probability_at_most': '1/20'},
                      'J_OM': {'statistic': 'h_OM',
                               'holds_if': 'h_OM >= 2',
                               'per_individual_null_probability_at_most': '1/420'}},
                'Ncnt': {'J_Ca': {'statistic': 'h_Ca',
                                  'holds_if': 'h_Ca >= 4',
                                  'per_individual_null_probability_at_most': '1/20'},
                         'J_O': {'statistic': 'h_O',
                                 'holds_if': 'h_O >= 4',
                                 'per_individual_null_probability_at_most': '1/20'},
                         'J_M': {'statistic': 'h_M',
                                 'holds_if': 'h_M >= 4',
                                 'per_individual_null_probability_at_most': '1/20'},
                         'J_OM': {'statistic': 'h_OM',
                                  'holds_if': 'h_OM >= 2',
                                  'per_individual_null_probability_at_most': '1/420'}}},
 'null_hypothesis': {'F_single': 'for every individual, F(O) (resp. F(M)) is exchangeable with F(W_1..W_19) (for the '
                                 'quantity of the judgment)',
                     'F_OM': 'for every individual, D(F(O)), D(F(M)), D(F(W_1..W_19)) (21 values) are exchangeable',
                     'Ncnt_single': 'for every individual, the natural O (resp. M) is exchangeable with W_1..W_19 (as in '
                                    '0028); each N^cnt event is a subset of the 0028 event',
                     'Ncnt_OM': 'for every individual, D(O), D(M), D(W_1..W_19) (21 values) are exchangeable (as in 0028)'},
 'independence_assumption': 'birth states and within-trial shuffle RNG streams are treated as independent across '
                            'individuals (statistical model assumption; not implied by distinct seeds)',
 'holds_means': 'reject_null_at_alpha_under_assumptions',
 'ties': 'strict_inequality_counts_ties_as_not_outside',
 'frozen_individuals': 'count_as_not_outside',
 'no_t0_individuals': {'in_denominator_of_20': True,
                       'F_events': False,
                       'Ncnt_events': 'computed_as_usual',
                       'recorded_separately_from_frozen': True,
                       'counted_as_completed': True},
 'on_any_invalid': 'experiment_invalid_no_judgment',
 'scope': {'F': 'C0_variant_with_weights_frozen_at_T0_and_no_plasticity_lag1_asymmetry_relative_to_F_within_trial_shuffle_reference',
           'Ncnt': 'C0_natural_bodies_lag1_asymmetry_exceeding_count_only_differences_a_and_b_relative_to_within_trial_shuffle_reference'},
 'not_judged': ['necessity_of_post_experience_rewriting_in_natural_C0',
                'weight_carried_content',
                'learning_necessity',
                'count_only_differences_other_than_a_and_b',
                'origin_of_relative_timing',
                'decomposition_of_0029_Wt_effect',
                'C_II_reproduction_and_elimination',
                'C_III_cause_of_natural_difference',
                'memory_formation',
                'meaning',
                'three_element_order',
                'intervals']}

RECORDS = {'full_state_fields': ['pulse', 'units', 'connections', 'drives', 'deltas'],
 'full_state_values_not_digests': True,
 'no_judgment_quantities_in_raw': True,
 'natural_bodies': {'per_body': ['birth_state',
                                 'unit_dynamics',
                                 'label_sequence',
                                 'spikes_1_to_end',
                                 'full_state_12000',
                                 'full_state_end_of_T0',
                                 'full_state_13500',
                                 'full_state_25500',
                                 'full_state_first_stimulus_and_next',
                                 'full_state_before_label_divergence']},
 'f_bodies': {'per_body': ['original_body',
                           'frozen_weights',
                           'unit_dynamics',
                           'full_state_start_at_T0',
                           'spikes_T0_plus_1_to_end',
                           'full_state_13500',
                           'full_state_25500']},
 'control_bodies': {'per_body': ['name',
                                 'full_state_start_at_T0',
                                 'spikes_T0_plus_1_to_end',
                                 'full_state_13500',
                                 'full_state_25500']},
 'freeze_fields': {'t0_exists': {'when_t0': True, 'when_no_t0': False},
                   't0': {'when_t0': 'integer_in_freeze_window', 'when_no_t0': None},
                   'window_witness': {'when_t0': None,
                                      'when_no_t0': 'array of {pulse, body, unit} for every Pulse of freeze_window in '
                                                    'ascending order; the first firing (body in order O, M, W1..W19; unit '
                                                    'in order s1, s2, s3) at that Pulse among the natural bodies'}},
 'no_t0': {'natural_bodies': 'same_as_above_except_full_state_end_of_T0_is_null', 'f_bodies': [], 'control_bodies': []},
 'inconsistent_raw_is_invalid': True}

CHECKS = {'result_values': ['pass', 'fail', 'not_applicable'],
 'exact': ['stimulus_labels',
           'identical_birth_state_natural_bodies',
           'input_free_after_experience',
           'identical_before_label_divergence',
           'freeze_time_rule',
           'f_construction',
           'f_weights_constant',
           'f_matches_natural_until_first_spike',
           'rebuild_identity',
           'no_clipping',
           'lag1_counts_two_ways'],
 'numeric': {'replay_weights_and_traces': {'natural_at': [12000, 'T0', 13500, 25500],
                                           'rebuild_control_at': [13500, 25500],
                                           'tolerance': 1e-12},
             'pair_sum': {'tolerance': 1e-12}},
 'revalidate_from_raw': True,
 'invalid_individuals': 'report_all',
 'no_t0': {'apply_on_natural_bodies_only': ['stimulus_labels',
                                            'identical_birth_state_natural_bodies',
                                            'input_free_after_experience',
                                            'identical_before_label_divergence',
                                            'no_clipping',
                                            'lag1_counts_two_ways',
                                            'replay_weights_and_traces',
                                            'pair_sum'],
           'freeze_time_rule': 'no-T0 proof: every Pulse of freeze_window has a firing in some natural body; each '
                               'window_witness entry matches the recorded spikes and is the first in the fixed order',
           'not_applicable': ['f_construction',
                              'f_weights_constant',
                              'f_matches_natural_until_first_spike',
                              'rebuild_identity'],
           'body_layout': 'natural 21; f_bodies and control_bodies are empty arrays'},
 'smoke_report_check_values': ['fail', 'ok']}

F_VARIANT = {'derived_from': 'brain.manifest',
 'edit': "remove plastic: true from the six s-s projections and set each s-s weight to the original body's connection "
         'weight at the end of T_0 (value as recorded); all other YAML settings and wiring identical',
 'plastic_connections': 'none',
 'unit_state_from': 'original_body_at_end_of_T0',
 'connection_state': 'none',
 'pulse_numbering': 'absolute t = T_0 + elapsed pulses of the rebuilt individual (spikes, full-state pulse, drive '
                    'created_pulse)',
 'premise': 'P_tau_updates_after_12000_depend_only_on_state',
 'implementation': 'manifest_values_and_core_public_import_state_only',
 'rebuild_control': {'body': 'R_O',
                     'construction': "same rebuild as F(O) but keep the C0 manifest (plastic) and copy O's unit state and "
                                     'full connection state (weights and traces) at end of T_0 via public import_state',
                     'expected': 'reproduces_natural_O_after_T0'}}

FREEZE = {'time': {'rule': 'T_0 = max{ t in [freeze_window.first, freeze_window.last] : no Unit fired at Pulse t in any of the 21 '
                  'natural bodies }',
          'state': 'end_of_pulse_T0',
          'if_none': 'F_events_not_outside_and_reported',
          'no_t0': {'valid': True,
                    'seed_status': 'completed',
                    'f_and_control_bodies': 'not_created',
                    'ncnt': 'computed_as_usual'}},
 'f_bodies': "for each natural body b in [O, M, W1..W19]: build F(b) from f_variant with b's weights at end of T_0, copy "
             "b's unit state at end of T_0, run T_0 + 1 .. body_runs_to without plasticity",
 'reference_bodies': ['W1',
                      'W2',
                      'W3',
                      'W4',
                      'W5',
                      'W6',
                      'W7',
                      'W8',
                      'W9',
                      'W10',
                      'W11',
                      'W12',
                      'W13',
                      'W14',
                      'W15',
                      'W16',
                      'W17',
                      'W18',
                      'W19']}

CONDITIONS = {'O': {'schedule': 'ordered'},
 'M': {'schedule': 'mirrored'},
 'within_trial_shuffles': {'count': 19,
                           'schedule': 'shuffled_labels_within_each_trial',
                           'rng': '0030-within-trial-{i}:{seed}',
                           'procedure': 'for each i, one random.Random(rng) stream; for k = 0 .. trials.count - 1 in order, '
                                        'shuffle the list [A, B, C] once with that stream and assign it to (t_k, t_k + '
                                        'b_offset, t_k + c_offset)'},
 'input_after_experience': 'none',
 'probes': 'none',
 'swaps': 'none'}

TIMELINE = {'pulse_interval_seconds': 1.0,
 'trials': {'first': 1, 'every': 60, 'count': 200},
 'experience_end': 'trials.first - 1 + trials.count * trials.every',
 'last_stimulus': 'trials.first + (trials.count - 1) * trials.every + c_offset',
 'delay': '5 * adaptation_tau / pulse_interval_seconds',
 'count_window_main': {'first': 'experience_end + delay + 1',
                       'length': 'trials.count * trials.every',
                       'last': 'count_window_main.first + count_window_main.length - 1'},
 'freeze_window': {'first': 'last_stimulus + 1', 'last': 'experience_end'},
 'body_runs_to': 'count_window_main.last'}

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
    """README §4.3：J_Ca・J_O・J_M は 1／(K ＋ 1)、J_OM は O が 21 個の最大かつ M が最小になる確率 1／((K ＋ 2)(K ＋ 1))。
    F・N^cnt のどちらも一方向（N^cnt は 0028 の事象の部分集合：README §4.4）。"""
    return Fraction(1, (k + 2) * (k + 1)) if judgment == "J_OM" else Fraction(1, k + 1)


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

    # 脳の設計図（README §1。0026・0028・0029 と同じ C0）と F の変種（README §2.3・§2.4）
    expect(protocol["brain"] == BRAIN, "設計図・Receptor・不応期・可塑性の対象が 0026・0028・0029 の C0 と違う")
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
    expect(protocol["f_variant"] == F_VARIANT and F_VARIANT["edit"] == W.F_EDIT and F_VARIANT["pulse_numbering"] == W.PULSE_NUMBERING
           and F_VARIANT["rebuild_control"]["construction"] == W.REBUILD_CONSTRUCTION and F_VARIANT["rebuild_control"]["body"] == W.CONTROL,
           "F の変種の決まり（設計図の変え方・Pulse の番号・組み立ての確認）が道具と違う")
    probe = {W.connection_id(a, b): 0.001 * (k + 1) for k, (a, b) in enumerate(itertools.permutations(units, 2))}
    variant = W.f_variant_manifest(protocol, probe)
    fv = parse_neuroarchitecture(variant)
    plain = yaml.safe_load(yaml.safe_dump(raw))
    for p in plain["projections"]:
        if p["from"].split(".")[0] in units and p["to"] in units:
            del p["plastic"]
            p["weight"] = probe[W.connection_id(p["from"].split(".")[0], p["to"])]
    expect(variant == plain, "F の変種が、C0 の設計図から 6 本の plastic: true を除き重みを替えたものと違う")
    expect(not any(p.plastic for p in fv.projections)
           and {W.connection_id(p.source_id, p.target_id): p.weight for p in fv.projections if p.source_id in units} == probe
           and [u.unit_id for u in fv.units] == [u.unit_id for u in m.units],
           "F の変種の接続が可塑性なし・指定の重み、Unit の並びが C0 と同じ、になっていない")

    # 時間の流れ（README §1・§2.2）
    expect(protocol["timeline"] == TIMELINE and TIMELINE["experience_end"] == W.EXPERIENCE_END
           and TIMELINE["last_stimulus"] == W.LAST_STIMULUS and TIMELINE["delay"] == W.DELAY
           and TIMELINE["count_window_main"] == W.COUNT_WINDOW_MAIN and TIMELINE["freeze_window"] == W.FREEZE_WINDOW
           and TIMELINE["body_runs_to"] == W.BODY_RUNS_TO,
           "時間の流れ（試行・最後の刺激・遅れ・主の区間・T_0 の窓・本体の終わり）の式が道具と違う")
    plan = W.plan_from(protocol)
    expect((plan.trials, plan.experience_end, plan.last_stimulus, plan.delay, plan.freeze_window, plan.main, plan.body_end,
            plan.first_stimulus) == (200, 12000, 11971, 1500, (11972, 12000), (13501, 25500), 25500, (1, 2)),
           "Plan が 試行 200・経験の終わり 12000・最後の刺激 11971・遅れ 1500・T_0 の窓 11972〜12000・主の区間 13501〜25500・"
           "本体の終わり 25500 ではない")
    expect(list(plan.snapshots) == [12000, 13500, 25500] and list(plan.rebuilt_snapshots) == [13500, 25500],
           "全状態を残す時点が 12000・13500・25500（F 本体・R(O) は 13500・25500）ではない")

    # 刺激と条件（README §2.1）
    st = protocol["stimulus"]
    expect((st["b_offset"], st["c_offset"]) == (2, 30) and st["counts"] == {r: plan.trials for r in W.ROLES},
           "刺激の形・数が 0028 と違う（各 200 ＝ 試行の数）")
    expect(0 < st["b_offset"] < st["c_offset"] < protocol["timeline"]["trials"]["every"], "試行の中の 3 つの枠が試行の中に順に収まらない")
    expect(st["role_assignment"] == W.ROLE_ASSIGNMENT, "役の割り当ての式が道具と違う")
    expect(sorted(map(tuple, st["role_orders"])) == sorted(itertools.permutations(BRAIN["receptors"])),
           "role_orders が Receptor の 6 通りの並べ方ではない")
    cond = protocol["conditions"]
    expect(cond == CONDITIONS and CONDITIONS["O"]["schedule"] == W.SCHEDULES["O"] and CONDITIONS["M"]["schedule"] == W.SCHEDULES["M"]
           and CONDITIONS["within_trial_shuffles"]["schedule"] == W.SCHEDULES["within_trial_shuffles"]
           and CONDITIONS["within_trial_shuffles"]["procedure"] == W.WITHIN_TRIAL_PROCEDURE
           and CONDITIONS["within_trial_shuffles"]["rng"] == f"{exp}-within-trial-{{i}}:{{seed}}",
           "条件（O・M・試行の中の並べ替え 19・その手順・経験の後の入力なし・試しなし・入れ替えなし）が道具と違う")
    expect(W.RNG_SHUFFLE == cond["within_trial_shuffles"]["rng"] and W.K == 19 and len(W.BODIES) == 21,
           "試行の中の並べ替えの乱数の流れ・数が道具と違う")

    # T_0（README §2.2・§2.6）
    expect(protocol["freeze"] == FREEZE and FREEZE["time"]["rule"] == W.FREEZE_TIME_RULE and FREEZE["f_bodies"] == W.F_BODIES
           and FREEZE["reference_bodies"] == REF == list(W.REFERENCE), "T_0 の規則・F 本体・参照の本体が道具と違う")

    # 量・判定・記録・確認（README §3〜§8）
    expect(protocol["quantities"] == QUANTITIES, "主・補助の量の定義が道具の実装と違う")
    j = protocol["judgment"]
    expect(j == JUDGMENT, "判定の決まりが道具の実装と違う")
    pf = j["per_family"]
    n = len(rng["seeds"])
    k = len(REF)
    split = {J: Fraction(str(pf["alpha_split"][J])) for J in JUDGMENTS}
    for f in FAMILIES:
        expect(sum(split.values()) == Fraction(str(j["families"][f]["alpha"])) == Fraction(1, 20),
               f"{f}：家族の中の水準の割り当ての和が家族の水準 0.05 ではない")
        expect(j["families"][f]["direction"] == "one_sided", f"{f}：判定の向きが一方向ではない")
        for J in JUDGMENTS:
            p0 = per_individual_null(J, k)
            spec = pf[f][J]
            expect(Fraction(spec["per_individual_null_probability_at_most"]) == p0, f"{f}・{J}：各個体の帰無の確率が {p0} ではない")
            expect(spec["statistic"] == STATISTIC[J] and spec["holds_if"] == f"{STATISTIC[J]} >= {HOLDS_MIN[f][J]}",
                   f"{f}・{J}：統計・成立の条件が道具と違う")
            expect(binom_tail(n, p0, HOLDS_MIN[f][J]) <= split[J] < binom_tail(n, p0, HOLDS_MIN[f][J] - 1),
                   f"{f}・{J}：閾値 {HOLDS_MIN[f][J]} が、P(Bin({n}, {p0}) ≥ h) ≤ {split[J]} となる最小の h ではない")
            expect(QUANTITIES["primary"]["across_individuals"][f][STATISTIC[J]] == f"count({EVENT[f][J]})",
                   f"{f}・{J}：統計の数える事象が道具と違う")
        expect(tuple(QUANTITIES["primary"]["per_individual"][f]) == tuple(EVENT[f].values()), f"{f}：4 つの事象の名前が道具と違う")
    expect(protocol["records"] == RECORDS and tuple(RECORDS["full_state_fields"]) == W.FULL_STATE_FIELDS
           and RECORDS["no_judgment_quantities_in_raw"] is True, "記録の項目が道具の実装と違う")
    expect(protocol["checks"] == CHECKS, "操作の確認の項目・時点・許容・T_0 がない個体での適用が道具の実装と違う")

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
