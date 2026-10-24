"""protocol.yaml（確定した事前登録 v0.1 の正本）と、0033 の設計図（C0）・道具が同じ条件かを機械的に確かめる。

ズレていたら実行・解析を止める。run.py と analyze.py の両方が最初に呼ぶ。protocol は変えない（道具の側をこれに合わせる）。
実験の ID は、このフォルダの名前の先頭（"0033_two_pair_weight_swap" → "0033"）から決め、protocol の experiment・
execution（ID・出力先・protocol のパス）・乱数の流れの名前がそれと一致することを確かめる。

下の TIMELINE・CONDITIONS・INTERVENTION・QUANTITIES・JUDGMENT・RECORDS・CHECKS は、確定した protocol.yaml（#139 の merge
`1b91089`）の各節の値をそのまま写した固定値（道具が実装している決まり）。check は protocol がこれと完全に同じことを確かめる。

主の判定（README §4・§5、protocol の judgment.per_family）は、2 組の種類 AB＋AC・AB＋BC・AC＋BC の家族（どれも一方向）に、
それぞれ J_Ca・J_O・J_M・J_OM の 4 つ、計 12。1 組（AB・AC・BC）と 6 本の入れ替えは補助の参照で、判定しない。
閾値は、割り当てた水準と K ＝ 19 から決まる最小の整数であることを、二項分布の上側の確率を厳密に計算して確かめる。
12 判定の割り当ての和 3 × 0.0165 ＝ 0.0495 が、主張する実験全体の水準 0.05 以下であることも確かめる（README §5.2。
Bonferroni で、判定のあいだの従属に依らない）。
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
# 0023〜0032 の本番・smoke・合成（予約した範囲ごと））。重なってはいけない
SEEN = (set(range(1, 21)) | set(range(1001, 1021)) | set(range(2001, 2021)) | set(range(3001, 3007))
        | set(range(4001, 4021)) | set(range(5001, 5007)) | set(range(6001, 6021)) | set(range(7001, 7007))
        | set(range(8001, 8021)) | set(range(8101, 8107)) | set(range(9001, 9700))
        | set(range(10001, 10021)) | set(range(10101, 10107)) | set(range(11001, 11021))
        | set(range(11101, 11107)) | set(range(12001, 12021)) | set(range(12101, 12107))
        | set(range(13001, 13201)) | set(range(14001, 14201)) | set(range(15001, 15201)) | set(range(16001, 16300))
        | set(range(17001, 17300)) | set(range(18001, 18300)) | set(range(19001, 19300)) | set(range(20001, 20300))
        | set(range(21001, 21300)) | set(range(22001, 22300)) | set(range(23001, 23300)) | set(range(24001, 24300))
        | set(range(25001, 25300)))

# 主の判定（README §4.2）
FAMILIES = ("AB+AC", "AB+BC", "AC+BC")                           # 2 組の種類の家族（主）
REFERENCE_KINDS = ("AB", "AC", "BC", "6")                        # 1 組・6 本の参照（補助。判定しない）
JUDGMENTS = ("J_Ca", "J_O", "J_M", "J_OM")
STATISTIC = {"J_Ca": "h_Ca", "J_O": "h_O", "J_M": "h_M", "J_OM": "h_OM"}
EVENT = {"J_Ca": "O_Delta_AB_above", "J_O": "O_above", "J_M": "M_below", "J_OM": "O_and_M_split"}
EVENTS = ("O_Delta_AB_above", "O_above", "M_below", "O_and_M_split")
# 閾値：割り当てた水準 alpha_J のもとで P(Bin(20, p0) ≥ h) ≤ alpha_J となる最小の h（check で厳密に確かめる）
HOLDS_MIN = {"J_Ca": 5, "J_O": 5, "J_M": 5, "J_OM": 2}
FAMILY_ALPHA = Fraction(165, 10000)                              # 0.005 × 3 ＋ 0.0015（README §5.1）
EXPERIMENT_WIDE_ALPHA = 0.05                                     # README §5.2（12 判定の Bonferroni、和 0.0495）
STRUCTURAL_BOUND = -0.03                                         # g ＜ −0.03 が構造的、−0.03 ≤ g ＜ 0 が条件付き、g ≥ 0 が活動的
STRATA = ("structural", "conditional", "active")
NO_TAU_REASON = "no_tau"
# 2 組の事象の型（README §3.4）：Q でだけ／Q と、Q に入る 1 組の少なくとも一方で／Q に入る 1 組のどちらかで成り立ち、Q で成り立たない／
# どれでも成り立たない
TWO_PAIR_EVENT_TYPES = ("two_pair_only", "two_pair_and_some_single", "some_single_but_not_two_pair", "none")

MANIFEST = "experiments/0012_passive_world/neuroarchitecture.yaml"   # 0014〜0032 と同じ設計図（C0）
BRAIN = {"manifest": MANIFEST, "dynamics_from": "config/neuroarchitecture/minimal-v3.yaml", "sensory_units": ["s1", "s2", "s3"],
         "receptors": {"receptor.x1": "s1", "receptor.x2": "s2", "receptor.x3": "s3"}, "refractory_pulses": 0,
         "plastic_connections": "six_s_to_s"}
REF = [f"W{i}" for i in range(1, 20)]
RECIPIENTS = [f"W{i}" for i in range(20, 25)]
UNIT_KEEP = ["units.activity", "units.adaptation", "units.refractory_remaining", "units.fire_count",
             "connections.pre_trace", "connections.post_trace"]
KEEP_FROM_RECIPIENT = ["weights_of_pairs_not_in_the_kind"] + UNIT_KEEP

TIMELINE = {'pulse_interval_seconds': 1.0,
            'trials': {'first': 1, 'every': 60, 'count': 200},
            'experience_end': 'trials.first - 1 + trials.count * trials.every',
            'delay': '5 * adaptation_tau / pulse_interval_seconds',
            'count_window_main': {'first': 'experience_end + delay + 1',
                                  'length': 'trials.count * trials.every',
                                  'last': 'count_window_main.first + count_window_main.length - 1'},
            'swap_window': {'first': 'count_window_main.first - trials.every', 'last': 'count_window_main.first - 1'},
            'body_runs_to': 'count_window_main.last'}

CONDITIONS = {'O': {'schedule': 'ordered'},
              'M': {'schedule': 'mirrored'},
              'within_trial_shuffles': {'count': 24,
                                        'schedule': 'shuffled_labels_within_each_trial',
                                        'rng': '0033-within-trial-{i}:{seed}',
                                        'procedure': 'for each i, one random.Random(rng) stream; for k = 0 .. trials.count - 1 in order, '
                                                     'shuffle the list [A, B, C] once with that stream and assign it to (t_k, t_k + '
                                                     'b_offset, t_k + c_offset)'},
              'input_after_experience': 'none',
              'probes': 'none'}

INTERVENTION = {'kind': 'state_block_swap',
                'swap_time': {'rule': 'tau = max{ t in [swap_window.first, swap_window.last] : no Unit fired at Pulse t in any of the 26 '
                                      'natural bodies }',
                              'common_to_all_recipients_and_swap_kinds': True,
                              'state': 'end_of_pulse_tau',
                              'if_none': 'individual_not_outside_for_all_twelve_judgments_and_reported',
                              'no_tau': {'valid': True, 'seed_status': 'completed', 'swapped_and_control_bodies': 'not_created'}},
                'recipients': ['W20', 'W21', 'W22', 'W23', 'W24'],
                'donors': ['O',
                           'M',
                           'W1',
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
                           'W19'],
                'reference_donors': ['W1',
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
                                     'W19'],
                'pairs': {'AB': ['A->B', 'B->A'], 'AC': ['A->C', 'C->A'], 'BC': ['B->C', 'C->B']},
                'swap_kinds': {'AB': {'pairs': ['AB'], 'role': 'auxiliary_reference'},
                               'AC': {'pairs': ['AC'], 'role': 'auxiliary_reference'},
                               'BC': {'pairs': ['BC'], 'role': 'auxiliary_reference'},
                               'AB+AC': {'pairs': ['AB', 'AC'], 'role': 'primary'},
                               'AB+BC': {'pairs': ['AB', 'BC'], 'role': 'primary'},
                               'AC+BC': {'pairs': ['AC', 'BC'], 'role': 'primary'},
                               '6': {'pairs': ['AB', 'AC', 'BC'], 'role': 'auxiliary_reference'}},
                'replace': ['connections.weight'],
                'keep_from_recipient': ['weights_of_pairs_not_in_the_kind',
                                        'units.activity',
                                        'units.adaptation',
                                        'units.refractory_remaining',
                                        'units.fire_count',
                                        'connections.pre_trace',
                                        'connections.post_trace'],
                'swapped_bodies': 'for each swap kind T in [AB, AC, BC, AB+AC, AB+BC, AC+BC, 6], for each recipient r in recipients, for '
                                  "each donor d in donors: clone r at end of tau, replace the weights of the pairs in T by d's values at "
                                  'end of tau, run tau + 1 .. body_runs_to with plasticity',
                'control_bodies': {'full_swap': 'for each recipient r: clone r at end of tau, replace weights and unit state and traces by '
                                                "O's values; run to body_runs_to",
                                   'null_swap': 'for each recipient r: clone r at end of tau, replace weights and unit state and traces by '
                                                "r's own values; run to body_runs_to"},
                'plasticity_after_swap': True,
                'invariants_checked_on_swapped_state': {'I1_pair_sum_tolerance': 1e-12,
                                                        'I2_trace_per_unit': 'exact',
                                                        'I3_activity_positive': 'exact',
                                                        'I4_no_drives_at_tau': 'exact'},
                'implementation': 'core_public_import_state_only'}

QUANTITIES = {'per_body': {'N': 'N_{X->Y} = #{ t : S <= t <= E - 1, s_X(t) = 1, s_Y(t + 1) = 1 } for ordered pairs X != Y',
                           'Delta_AB': 'N_{A->B} - N_{B->A}',
                           'Delta_AC': 'N_{A->C} - N_{C->A}',
                           'D': 'Delta_AB - Delta_AC',
                           'spike_count': 'N_X = #{ t : S <= t <= E, s_X(t) = 1 } for roles X in A, B, C'},
              'scores': {'rank_score': 's^{x,T}_r(d) = sum over donors e != d of sign(x_r^T(d) - x_r^T(e))',
                         'total_score': 'S^{x,T}(d) = sum over recipients r of s^{x,T}_r(d)',
                         'across_kinds': 'none'},
              'primary': {'window': 'count_window_main',
                          'per_individual': {'per_two_pair_kind': {'O_Delta_AB_above': 'S^{Delta_AB,Q}(O) > max_{d in reference} '
                                                                                       'S^{Delta_AB,Q}(d)',
                                                                   'O_above': 'S^{D,Q}(O) > max_{d in reference} S^{D,Q}(d)',
                                                                   'M_below': 'S^{D,Q}(M) < min_{d in reference} S^{D,Q}(d)',
                                                                   'O_and_M_split': 'O_above and M_below'}},
                          'across_individuals': {'per_two_pair_kind': {'h_Ca': 'count(O_Delta_AB_above)',
                                                                       'h_O': 'count(O_above)',
                                                                       'h_M': 'count(M_below)',
                                                                       'h_OM': 'count(O_and_M_split)'}}},
              'propositions': {'order_preservation': 'for fixed T, r and x: x_r^T(d) > x_r^T(e) implies s^{x,T}_r(d) >= s^{x,T}_r(e) + 2; '
                                                     'x_r^T(d) = x_r^T(e) implies s^{x,T}_r(d) = s^{x,T}_r(e)',
                               'null_bound': 'under H_Q, (S^{x,Q}(O), S^{x,Q}(W_1..W_19)) is exchangeable, so P(event) <= 1/20 (1/420 for '
                                             'J_OM)',
                               'swap_depends_on_donor_only_through_the_weights_of_the_pairs_in_the_kind': 'for fixed r and T, Y_r^T(d) is '
                                                                                                          "determined by r's state at tau "
                                                                                                          "and d's weights of the pairs in "
                                                                                                          'T at tau',
                               'every_kind_preserves_pair_sum': 'every pair of a swapped state comes wholly from r or wholly from d, so I1 '
                                                                'holds',
                               'full_factorial': 'with the recipient as baseline, the eight values f(z) determine mu, alpha_P, beta_PQ and '
                                                 'gamma uniquely (Moebius inversion); the 0032 I equals sum of beta_PQ plus gamma'},
              'auxiliary': {'per_individual': {'swap_time': True,
                                               'per_body_components': ['six_N_counts',
                                                                       'Delta_AB',
                                                                       'Delta_AC',
                                                                       'Delta_BC',
                                                                       'D',
                                                                       'spike_counts_per_role',
                                                                       'silent_roles'],
                                               'scores': ['rank_scores_per_kind_recipient_and_donor', 'total_scores_per_kind_and_donor'],
                                               'single_pair_and_six_reference': {'kinds': ['AB', 'AC', 'BC', '6'],
                                                                                 'events': ['O_Delta_AB_above',
                                                                                            'O_above',
                                                                                            'M_below',
                                                                                            'O_and_M_split'],
                                                                                 'frozen': True},
                                               'factorial': {'baseline': 'mu = b_r^x = x(natural body of recipient r)',
                                                             'main_term': 'alpha_P = f(e_P) - mu',
                                                             'two_pair_term': 'beta_PQ = f(e_P + e_Q) - f(e_P) - f(e_Q) + mu',
                                                             'three_pair_term': 'gamma = f(1,1,1) - sum over PQ of f(e_P + e_Q) + sum over '
                                                                                'P of f(e_P) - mu',
                                                             'I': 'I = f(1,1,1) - sum over P of f(e_P) + 2 mu = sum over PQ of beta_PQ + '
                                                                  'gamma',
                                                             'record': ['beta_gamma_I_for_all_105_recipient_donor_pairs',
                                                                        'count_of_zero_per_term',
                                                                        'sums_over_r_for_O_and_M_with_position_among_reference_sums',
                                                                        'two_pair_event_types_per_kind_and_event',
                                                                        'seven_kind_event_patterns_observed'],
                                                             'two_pair_event_types': ['two_pair_only',
                                                                                      'two_pair_and_some_single',
                                                                                      'some_single_but_not_two_pair',
                                                                                      'none']},
                                               'per_recipient_0029_form_events': 'for each kind T and recipient r, the four 0029 Wt '
                                                                                 'events; per individual the number k (0..5) of recipients '
                                                                                 'where each holds',
                                               'ranks': 'for each kind T: rank of S^{Delta_AB,T}(O), S^{D,T}(O), S^{D,T}(M) among '
                                                        'reference',
                                               'opposite_direction': 'for each kind T: S^{Delta_AB,T}(O) < min, S^{D,T}(O) < min, '
                                                                     'S^{D,T}(M) > max',
                                               'frozen_per_kind_and_judgment': 'all total scores used by the judgment are equal',
                                               'target_only_silence': 'for each kind T, recipient r and target Y_r^T(O) (J_Ca, J_O) and '
                                                                      'Y_r^T(M) (J_M): whether its set of silent roles differs from that '
                                                                      'of every Y_r^T(W_i); per individual the number of such recipients, '
                                                                      'and how often it co-occurs with each event',
                                               'natural_pair_weight_ranks': {'weights': {'AB': 'A->B', 'AC': 'A->C', 'BC': 'B->C'},
                                                                             'at': 'tau'},
                                               'birth_margin_strata': {'g': 'g_i = intrinsic_drive_i / (1 - decay) - threshold_i for roles '
                                                                            'A, B, C (birth Unit dynamics)',
                                                                       'strata': {'structural': 'g_i < -0.03',
                                                                                  'conditional': '-0.03 <= g_i < 0',
                                                                                  'active': 'g_i >= 0'},
                                                                       'record': 'per role and stratum: individuals, no-tau individuals, '
                                                                                 'and counts of each of the twelve primary events'},
                                               'natural_comparison': {'events': ['O_Delta_AB_above', 'O_above', 'M_below', 'O_and_M_split'],
                                                                      'reference': ['W1',
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
                                                                                    'W19']}},
                            'across_individuals': {'counts_of_each_auxiliary_event': True,
                                                   'distribution_of_k_per_kind_and_event': True,
                                                   'no_tau_individuals': True,
                                                   'clopper_pearson_95_of_h_over_20': ['AB+AC.h_Ca',
                                                                                       'AB+AC.h_O',
                                                                                       'AB+AC.h_M',
                                                                                       'AB+AC.h_OM',
                                                                                       'AB+BC.h_Ca',
                                                                                       'AB+BC.h_O',
                                                                                       'AB+BC.h_M',
                                                                                       'AB+BC.h_OM',
                                                                                       'AC+BC.h_Ca',
                                                                                       'AC+BC.h_O',
                                                                                       'AC+BC.h_M',
                                                                                       'AC+BC.h_OM']},
                            'when_no_tau': {'recorded': ['natural_body_components_and_silence',
                                                         'birth_margin_strata',
                                                         'natural_comparison'],
                                            'null_with_reason_no_tau': ['swapped_body_components',
                                                                        'scores',
                                                                        'single_pair_and_six_reference',
                                                                        'factorial',
                                                                        'per_recipient_0029_form_events',
                                                                        'ranks',
                                                                        'opposite_direction',
                                                                        'frozen_per_kind_and_judgment',
                                                                        'target_only_silence',
                                                                        'swapped_body_silence',
                                                                        'natural_pair_weight_ranks'],
                                            'strata_counts': 'count_events_as_not_outside_and_record_no_tau_count_per_stratum'}},
              'not_used': ['effect_size_threshold',
                           'population_fraction_claims',
                           'ratios',
                           'normalizations',
                           'rates',
                           'weighted_lag_sums',
                           'value_sum_aggregate_across_recipients',
                           'majority_rules_across_recipients',
                           'per_recipient_judgments',
                           'all_recipients_family',
                           'heterogeneity_tests_across_recipients',
                           'recipient_selection_by_data',
                           'score_sums_or_comparisons_across_kinds',
                           'comparison_of_h_across_kinds',
                           'contribution_shares',
                           'judgment_on_interaction_terms',
                           'judgment_on_single_pair_or_six_reference',
                           'theory_weighted_alpha',
                           'leave_one_pair_out_necessity_claims',
                           'one_direction_weight_swaps',
                           'combining_individuals_across_experiments',
                           'post_hoc_windows',
                           'post_hoc_lags',
                           'comparison_with_earlier_experiments_h',
                           'individual_eligibility_filters',
                           'selection_by_natural_comparison',
                           'selection_by_natural_pair_weight_ranks',
                           'selection_by_birth_margin_strata',
                           'selection_by_target_only_silence',
                           'count_exceeding_events',
                           'units_block_swap',
                           'probe_readouts',
                           'between_trial_shuffle_reference']}

JUDGMENT = {'families': {'AB+AC': {'events': 'total_scores_across_recipients_for_kind_AB+AC', 'direction': 'one_sided', 'alpha': 0.0165},
                         'AB+BC': {'events': 'total_scores_across_recipients_for_kind_AB+BC', 'direction': 'one_sided', 'alpha': 0.0165},
                         'AC+BC': {'events': 'total_scores_across_recipients_for_kind_AC+BC', 'direction': 'one_sided', 'alpha': 0.0165}},
            'experiment_wide_error_rate_claimed': 0.05,
            'per_family': {'alpha_split': {'J_Ca': 0.005, 'J_O': 0.005, 'J_M': 0.005, 'J_OM': 0.0015},
                           'each_two_pair_kind': {'J_Ca': {'statistic': 'h_Ca',
                                                           'holds_if': 'h_Ca >= 5',
                                                           'per_individual_null_probability_at_most': '1/20'},
                                                  'J_O': {'statistic': 'h_O',
                                                          'holds_if': 'h_O >= 5',
                                                          'per_individual_null_probability_at_most': '1/20'},
                                                  'J_M': {'statistic': 'h_M',
                                                          'holds_if': 'h_M >= 5',
                                                          'per_individual_null_probability_at_most': '1/20'},
                                                  'J_OM': {'statistic': 'h_OM',
                                                           'holds_if': 'h_OM >= 2',
                                                           'per_individual_null_probability_at_most': '1/420'}}},
            'null_hypothesis': {'single_O': "for every individual, the joint distribution of the five recipients' states at tau and the 21 "
                                            "donors' four weights of the two pairs in Q at tau is invariant under permutations of the "
                                            'labels O, W1..W19 (M fixed)',
                                'single_M': 'the same with M, W1..W19 (O fixed)',
                                'OM': 'the same under all permutations of the 21 donors'},
            'recipient_donor_independence_assumption': "given the birth state, the recipients' states (including their weights of the "
                                                       "remaining pair) are treated as independent of the donors' pair weights (distinct "
                                                       'RNG stream names; O and M are fixed sequences; statistical model assumption)',
            'independence_assumption': 'birth states and within-trial shuffle RNG streams are treated as independent across individuals '
                                       '(statistical model assumption; not implied by distinct seeds)',
            'within_individual_dependence': 'one_event_per_individual_per_judgment',
            'theory_expectations_not_used_for_alpha': 'AB+AC: J_Ca, J_O, J_M, J_OM; AB+BC: J_Ca, J_O; AC+BC: J_M (README §3.3; written '
                                                      'from the idealized analysis only, not from the 0032 results)',
            'holds_means': 'reject_null_at_alpha_under_assumptions',
            'ties': 'strict_inequality_counts_ties_as_not_outside',
            'frozen_individuals': 'count_as_not_outside',
            'no_swap_time': 'count_as_not_outside',
            'no_tau_individuals': {'in_denominator_of_20': True,
                                   'all_twelve_events': False,
                                   'recorded_separately_from_frozen': True,
                                   'counted_as_completed': True},
            'on_any_invalid': 'experiment_invalid_no_judgment',
            'scope': 'C0_C_I_effect_of_donor_weights_of_two_pairs_into_five_W_type_recipients_with_the_remaining_pair_and_unit_state_fixed_at_tau_before_main_window_on_lag1_asymmetry_relative_to_donor_reference',
            'not_judged': ['background_independence_for_arbitrary_backgrounds',
                           'heterogeneity_across_recipients',
                           'O_or_M_as_recipients',
                           'other_swap_times',
                           'C_II_reproduction_and_elimination_of_natural_difference',
                           'C_III_cause_of_natural_difference',
                           'exclusivity_of_pairs',
                           'contribution_shares',
                           'comparison_across_kinds',
                           'interaction_or_additivity',
                           'necessity_of_the_removed_pair',
                           'sufficiency_of_two_pairs_for_the_six_weight_effect',
                           'direction_within_pair',
                           'single_pair_and_six_reference_replication',
                           'units_block',
                           'reachability_of_swapped_states',
                           'learning_necessity',
                           'quantity_only_difference_excluded',
                           'plasticity_freeze_variant',
                           'memory_formation',
                           'meaning',
                           'three_element_order',
                           'intervals']}

RECORDS = {'full_state_fields': ['pulse', 'units', 'connections', 'drives', 'deltas'],
           'full_state_values_not_digests': True,
           'no_judgment_quantities_in_raw': True,
           'raw_top_level_keys': ['meta', 'run'],
           'natural_bodies': {'per_body': ['birth_state',
                                           'unit_dynamics',
                                           'label_sequence',
                                           'spikes_1_to_end',
                                           'full_state_12000',
                                           'full_state_end_of_tau',
                                           'full_state_13500',
                                           'full_state_25500',
                                           'full_state_first_stimulus_and_next',
                                           'full_state_before_label_divergence']},
           'swapped_bodies': {'per_body': ['swap_record_tau_kind_connections_recipient_donor',
                                           'full_state_end_of_tau_after_swap',
                                           'spikes_tau_plus_1_to_end',
                                           'full_state_13500',
                                           'full_state_25500']},
           'control_bodies': {'per_body': ['swap_record_tau_recipient_kind',
                                           'full_state_end_of_tau_after_swap',
                                           'spikes_tau_plus_1_to_end',
                                           'full_state_13500',
                                           'full_state_25500']},
           'swap_fields': {'tau_exists': {'when_tau': True, 'when_no_tau': False},
                           'tau': {'when_tau': 'integer_in_swap_window', 'when_no_tau': None},
                           'window_witness': {'when_tau': None,
                                              'when_no_tau': 'array of {pulse, body, unit} for every Pulse of swap_window in ascending '
                                                             'order; the first firing (body in order O, M, W1..W24; unit in order s1, s2, '
                                                             's3) at that Pulse among the natural bodies'}},
           'no_tau': {'natural_bodies': 'same_as_above_except_full_state_end_of_tau_is_null', 'swapped_bodies': [], 'control_bodies': []},
           'inconsistent_raw_is_invalid': True}

CHECKS = {'result_values': ['pass', 'fail', 'not_applicable'],
          'exact': ['stimulus_labels',
                    'identical_birth_state_natural_bodies',
                    'input_free_after_experience',
                    'identical_before_label_divergence',
                    'swap_time_rule',
                    'swap_composition',
                    'swap_invariants',
                    'full_swap_reproduces_donor',
                    'null_swap_identity',
                    'no_clipping',
                    'lag1_counts_two_ways'],
          'numeric': {'replay_weights_and_traces': {'natural_at': [12000, 'tau', 13500, 25500],
                                                    'swapped_at': [13500, 25500],
                                                    'tolerance': 1e-12},
                      'pair_sum': {'tolerance': 1e-12}},
          'revalidate_from_raw': True,
          'invalid_individuals': 'report_all',
          'no_tau': {'apply_on_natural_bodies_only': ['stimulus_labels',
                                                      'identical_birth_state_natural_bodies',
                                                      'input_free_after_experience',
                                                      'identical_before_label_divergence',
                                                      'no_clipping',
                                                      'lag1_counts_two_ways',
                                                      'replay_weights_and_traces',
                                                      'pair_sum'],
                     'swap_time_rule': 'no-tau proof: every Pulse of swap_window has a firing in some natural body; each window_witness '
                                       'entry matches the recorded spikes and is the first in the fixed order',
                     'not_applicable': ['swap_composition', 'swap_invariants', 'full_swap_reproduces_donor', 'null_swap_identity'],
                     'body_layout': 'natural 26; swapped_bodies and control_bodies are empty arrays'},
          'smoke_report': {'check_values': ['fail', 'ok'], 'checks': 'failed_check_names_only'}}

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
    """README §4.3 の命題 2：J_Ca・J_O・J_M は 1／(K ＋ 1)、J_OM は O が 21 個の最大かつ M が最小になる確率 1／((K ＋ 2)(K ＋ 1))。
    どの 2 組の家族も一方向で、同じ上界。"""
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

    # 脳の設計図（README §1。0026・0028〜0032 と同じ C0）
    expect(protocol["brain"] == BRAIN, "設計図・Receptor・不応期・可塑性の対象が 0026・0028〜0032 の C0 と違う")
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
    expect(protocol["timeline"] == TIMELINE and TIMELINE["experience_end"] == W.EXPERIENCE_END and TIMELINE["delay"] == W.DELAY
           and TIMELINE["count_window_main"] == W.COUNT_WINDOW_MAIN and TIMELINE["swap_window"] == W.SWAP_WINDOW
           and TIMELINE["body_runs_to"] == W.BODY_RUNS_TO,
           "時間の流れ（試行・遅れ・主の区間・τ の窓・本体の終わり）の式が道具と違う")
    plan = W.plan_from(protocol)
    expect((plan.trials, plan.experience_end, plan.delay, plan.swap_window, plan.main, plan.body_end, plan.first_stimulus)
           == (200, 12000, 1500, (13441, 13500), (13501, 25500), 25500, (1, 2)),
           "Plan が 試行 200・経験の終わり 12000・遅れ 1500・τ の窓 13441〜13500・主の区間 13501〜25500・本体の終わり 25500 ではない")
    expect(plan.swap_window[1] - plan.swap_window[0] + 1 == TIMELINE["trials"]["every"] == 60, "τ の窓の幅が trials.every（60）ではない")
    expect(list(plan.snapshots) == [12000, 13500, 25500] and list(plan.swapped_snapshots) == [13500, 25500],
           "全状態を残す時点が 12000・13500・25500（入れ替えた本体・確認の本体は 13500・25500）ではない")

    # 刺激と条件（README §2.1）
    st = protocol["stimulus"]
    expect((st["b_offset"], st["c_offset"]) == (2, 30) and st["counts"] == {r: plan.trials for r in W.ROLES},
           "刺激の形・数が 0028 と違う（各 200 ＝ 試行の数）")
    expect(0 < st["b_offset"] < st["c_offset"] < TIMELINE["trials"]["every"], "試行の中の 3 つの枠が試行の中に順に収まらない")
    expect(st["role_assignment"] == W.ROLE_ASSIGNMENT, "役の割り当ての式が道具と違う")
    expect(sorted(map(tuple, st["role_orders"])) == sorted(itertools.permutations(BRAIN["receptors"])),
           "role_orders が Receptor の 6 通りの並べ方ではない")
    cond = protocol["conditions"]
    expect(cond == CONDITIONS and CONDITIONS["O"]["schedule"] == W.SCHEDULES["O"] and CONDITIONS["M"]["schedule"] == W.SCHEDULES["M"]
           and CONDITIONS["within_trial_shuffles"]["schedule"] == W.SCHEDULES["within_trial_shuffles"]
           and CONDITIONS["within_trial_shuffles"]["procedure"] == W.WITHIN_TRIAL_PROCEDURE
           and CONDITIONS["within_trial_shuffles"]["rng"] == f"{exp}-within-trial-{{i}}:{{seed}}",
           "条件（O・M・試行の中の並べ替え 24・その手順・経験の後の入力なし・試しなし）が道具と違う")
    expect(W.RNG_SHUFFLE == cond["within_trial_shuffles"]["rng"] and W.K == 24 and len(W.BODIES) == 26,
           "試行の中の並べ替えの乱数の流れ・数が道具と違う")

    # 介入（README §2）
    iv = protocol["intervention"]
    expect(iv == INTERVENTION and iv["swap_time"]["rule"] == W.SWAP_TIME_RULE and iv["swapped_bodies"] == W.SWAPPED_BODIES
           and iv["control_bodies"] == {"full_swap": W.FULL_SWAP, "null_swap": W.NULL_SWAP},
           "介入（τ の規則・τ がない個体・受け手・ドナー・組・入れ替えの種類・入れ替えた本体・確認の本体・不変の関係）が道具と違う")
    expect(list(W.RECIPIENTS) == RECIPIENTS and list(W.DONORS) == ["O", "M"] + REF and list(W.REFERENCE) == REF
           and not set(W.RECIPIENTS) & set(W.DONORS) and set(W.RECIPIENTS) | set(W.DONORS) == set(W.BODIES),
           "受け手・ドナー・参照のドナーが W20〜W24・(O, M, W1〜W19)・W1〜W19 ではないか、重なる・本体を覆わない")
    # 組（README §2.3）：3 つの組が役の 3 つの組をちょうど覆い、各組が両向きの 2 本
    expect({p: list(v) for p, v in W.PAIR_ROLES.items()} == iv["pairs"] and tuple(iv["pairs"]) == W.PAIR_NAMES == ("AB", "AC", "BC"),
           "組（AB・AC・BC とその 2 本の向き）が道具と違う")
    arrows = [a for v in W.PAIR_ROLES.values() for a in v]
    expect(sorted(arrows) == sorted(f"{x}->{y}" for x, y in itertools.permutations(W.ROLES, 2))
           and all(len(v) == 2 and v[1] == "->".join(reversed(v[0].split("->"))) for v in W.PAIR_ROLES.values()),
           "組の向きが、役の 6 本の向きをちょうど一度ずつ、組ごとに両向きで覆わない")
    # 入れ替えの種類（README §2.3）：3 つの組の空でない部分集合をちょうど一度ずつ、1 組・2 組・3 組の順（各大きさの中は組の順）。
    # 名前は組の名前を "+" でつないだもの（3 組は "6"）。2 組の 3 つが主、1 組の 3 つと 6 が補助の参照
    kinds = iv.get("swap_kinds") if isinstance(iv.get("swap_kinds"), dict) else {}
    subsets = [c for size in (1, 2, 3) for c in itertools.combinations(W.PAIR_NAMES, size)]
    expect(list(kinds) == list(W.SWAP_KINDS) == list(W.KIND_PAIRS)
           and [tuple(v.get("pairs", ())) if isinstance(v, dict) else None for v in kinds.values()]
           == [W.KIND_PAIRS[k] for k in W.SWAP_KINDS] == subsets,
           "入れ替えの種類が AB・AC・BC・AB+AC・AB+BC・AC+BC・6 の順で、3 つの組の空でない部分集合をちょうど一度ずつ覆う形ではない")
    expect(all(k == ("+".join(ps) if len(ps) < len(W.PAIR_NAMES) else W.SIX) for k, ps in W.KIND_PAIRS.items()) and W.SIX == "6",
           "入れ替えの種類の名前が、組の名前を + でつないだもの（3 組は 6）ではない")
    expect({k: (v.get("role") if isinstance(v, dict) else None) for k, v in kinds.items()}
           == {k: ("primary" if len(ps) == 2 else "auxiliary_reference") for k, ps in W.KIND_PAIRS.items()},
           "2 組の種類が主、1 組・6 本の種類が補助の参照になっていない")
    expect(W.TWO_PAIR_KINDS == FAMILIES == tuple(k for k, v in kinds.items() if isinstance(v, dict) and v.get("role") == "primary")
           and W.SINGLE_PAIR_KINDS + (W.SIX,) == REFERENCE_KINDS, "主の家族（2 組の種類）・補助の参照の種類が道具と違う")
    expect(iv.get("replace") == [f"connections.{f}" for f in W.WEIGHTS[1]] == ["connections.weight"]
           and iv.get("keep_from_recipient") == KEEP_FROM_RECIPIENT and W.WEIGHTS == ((), ("weight",))
           and UNIT_KEEP == ([f"units.{f}" for f in W.UNIT_FIELDS]
                             + [f"connections.{f}" for f in W.CONNECTION_FIELDS if f not in W.WEIGHTS[1]]),
           "入れ替える欄（種類に入る組の重みだけ）と受け手のまま残す欄（種類に入らない組の重み・Unit の状態・痕跡）が道具と違う")
    expect(set(W.EVERYTHING[0]) | set(W.KEPT_UNIT_FIELDS) == set(W.UNIT_FIELDS) and set(W.EVERYTHING[1]) == set(W.CONNECTION_FIELDS),
           "確認の本体で替える欄が、発火の回数を除く Unit・接続の欄のすべてではない")

    # 量・判定・記録・確認（README §3〜§8）
    expect(protocol["quantities"] == QUANTITIES, "主・補助の量の定義が道具の実装と違う")
    j = protocol["judgment"]
    expect(j == JUDGMENT, "判定の決まりが道具の実装と違う")
    pf = j["per_family"]
    n = len(rng["seeds"])
    k = len(REF)
    split = {J: Fraction(str(pf["alpha_split"][J])) for J in JUDGMENTS}
    expect(sum(split.values()) == FAMILY_ALPHA, "家族の中の水準の割り当ての和が 0.0165 ではない")
    for f in FAMILIES:
        fam = j["families"].get(f) if isinstance(j.get("families"), dict) else None
        fam = fam if isinstance(fam, dict) else {}
        expect(fam.get("alpha") is not None and Fraction(str(fam["alpha"])) == FAMILY_ALPHA, f"{f}：家族の水準が 0.0165 ではない")
        expect(fam.get("direction") == "one_sided", f"{f}：判定の向きが一方向ではない")
    for J in JUDGMENTS:
        p0 = per_individual_null(J, k)
        spec = pf["each_two_pair_kind"][J]
        expect(Fraction(spec["per_individual_null_probability_at_most"]) == p0, f"{J}：各個体の帰無の確率が {p0} ではない")
        expect(spec["statistic"] == STATISTIC[J] and spec["holds_if"] == f"{STATISTIC[J]} >= {HOLDS_MIN[J]}",
               f"{J}：統計・成立の条件が道具と違う")
        expect(binom_tail(n, p0, HOLDS_MIN[J]) <= split[J] < binom_tail(n, p0, HOLDS_MIN[J] - 1),
               f"{J}：閾値 {HOLDS_MIN[J]} が、P(Bin({n}, {p0}) ≥ h) ≤ {split[J]} となる最小の h ではない")
        expect(QUANTITIES["primary"]["across_individuals"]["per_two_pair_kind"][STATISTIC[J]] == f"count({EVENT[J]})",
               f"{J}：統計の数える事象が道具と違う")
    expect(tuple(QUANTITIES["primary"]["per_individual"]["per_two_pair_kind"]) == EVENTS, "4 つの事象の名前が道具と違う")
    expect(isinstance(j.get("families"), dict) and tuple(j["families"]) == FAMILIES, "判定の家族が 2 組の種類 AB+AC・AB+BC・AC+BC ではない")
    aux = QUANTITIES["auxiliary"]["per_individual"]
    expect(tuple(aux["single_pair_and_six_reference"]["kinds"]) == REFERENCE_KINDS
           and tuple(aux["single_pair_and_six_reference"]["events"]) == EVENTS
           and tuple(aux["factorial"]["two_pair_event_types"]) == TWO_PAIR_EVENT_TYPES
           and aux["natural_pair_weight_ranks"]["weights"] == {p: W.PAIR_ROLES[p][0] for p in W.PAIR_NAMES},
           "補助（1 組・6 本の参照の種類・事象、2 組の事象の型、自然な組の重みの向き）が道具と違う")
    expect(QUANTITIES["auxiliary"]["across_individuals"]["clopper_pearson_95_of_h_over_20"]
           == [f"{f}.{STATISTIC[J]}" for f in FAMILIES for J in JUDGMENTS], "Clopper–Pearson の区間を添える 12 の統計が道具と違う")
    # 実験全体（README §5.2）：12 判定の割り当ての和が主張する水準以下
    expect(len(FAMILIES) * FAMILY_ALPHA <= Fraction(str(j["experiment_wide_error_rate_claimed"])) == Fraction(str(EXPERIMENT_WIDE_ALPHA)),
           "12 判定の水準の割り当ての和が、主張する実験全体の水準 0.05 を超える")
    expect(protocol["records"] == RECORDS and tuple(RECORDS["full_state_fields"]) == W.FULL_STATE_FIELDS
           and RECORDS["no_judgment_quantities_in_raw"] is True, "記録の項目が道具の実装と違う")
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
