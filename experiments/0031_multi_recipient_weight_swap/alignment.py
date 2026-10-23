"""protocol.yaml（確定した事前登録 v0.1 の正本）と、0031 の設計図（C0）・道具が同じ条件かを機械的に確かめる。

ズレていたら実行・解析を止める。run.py と analyze.py の両方が最初に呼ぶ。protocol は変えない（道具の側をこれに合わせる）。
実験の ID は、このフォルダの名前の先頭（"0031_multi_recipient_weight_swap" → "0031"）から決め、protocol の experiment・
execution（ID・出力先・protocol のパス）・乱数の流れの名前がそれと一致することを確かめる。

下の TIMELINE・CONDITIONS・INTERVENTION・QUANTITIES・JUDGMENT・RECORDS・CHECKS は、確定した protocol.yaml（#133 の merge
`0c6664d`）の各節の値をそのまま写した固定値（道具が実装している決まり）。check は protocol がこれと完全に同じことを確かめる。

主の判定（README §4・§5、protocol の judgment.per_family）は、Agg の家族と All の家族（どちらも一方向）に、それぞれ
J_Ca・J_O・J_M・J_OM の 4 つ。閾値は、割り当てた水準と K ＝ 19 から決まる最小の整数であることを、二項分布の上側の確率を厳密に
計算して確かめる。All の事象は Agg の事象の部分集合で（README §4.3 の命題 1 の帰結 2）、閾値も帰無仮説も同じなので、8 判定を
まとめた水準は Agg の割り当ての和 0.05（README §5.2）。この入れ子は analyze.py が個体ごとに機械的に確かめる。
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
# 0023〜0030 の本番・smoke・合成（予約した範囲ごと））。重なってはいけない
SEEN = (set(range(1, 21)) | set(range(1001, 1021)) | set(range(2001, 2021)) | set(range(3001, 3007))
        | set(range(4001, 4021)) | set(range(5001, 5007)) | set(range(6001, 6021)) | set(range(7001, 7007))
        | set(range(8001, 8021)) | set(range(8101, 8107)) | set(range(9001, 9700))
        | set(range(10001, 10021)) | set(range(10101, 10107)) | set(range(11001, 11021))
        | set(range(11101, 11107)) | set(range(12001, 12021)) | set(range(12101, 12107))
        | set(range(13001, 13201)) | set(range(14001, 14201)) | set(range(15001, 15201)) | set(range(16001, 16300))
        | set(range(17001, 17300)) | set(range(18001, 18300)) | set(range(19001, 19300)) | set(range(20001, 20300))
        | set(range(21001, 21300)) | set(range(22001, 22300)) | set(range(23001, 23300)))

# 主の判定（README §4.2）
FAMILIES = ("Agg", "All")
JUDGMENTS = ("J_Ca", "J_O", "J_M", "J_OM")
STATISTIC = {"J_Ca": "h_Ca", "J_O": "h_O", "J_M": "h_M", "J_OM": "h_OM"}
EVENT = {f: {"J_Ca": "O_Delta_AB_above", "J_O": "O_above", "J_M": "M_below", "J_OM": "O_and_M_split"} for f in FAMILIES}
EVENTS = ("O_Delta_AB_above", "O_above", "M_below", "O_and_M_split")
# 閾値：割り当てた水準 alpha_J のもとで P(Bin(20, p0) ≥ h) ≤ alpha_J となる最小の h（check で厳密に確かめる）
HOLDS_MIN = {f: {"J_Ca": 4, "J_O": 4, "J_M": 4, "J_OM": 2} for f in FAMILIES}
EXPERIMENT_WIDE_ALPHA = 0.05                                     # README §5.2（入れ子による）
STRUCTURAL_BOUND = -0.03                                         # g ＜ −0.03 が構造的、−0.03 ≤ g ＜ 0 が条件付き、g ≥ 0 が活動的
STRATA = ("structural", "conditional", "active")
NO_TAU_REASON = "no_tau"

MANIFEST = "experiments/0012_passive_world/neuroarchitecture.yaml"   # 0014〜0030 と同じ設計図（C0）
BRAIN = {"manifest": MANIFEST, "dynamics_from": "config/neuroarchitecture/minimal-v3.yaml", "sensory_units": ["s1", "s2", "s3"],
         "receptors": {"receptor.x1": "s1", "receptor.x2": "s2", "receptor.x3": "s3"}, "refractory_pulses": 0,
         "plastic_connections": "six_s_to_s"}
REF = [f"W{i}" for i in range(1, 20)]
RECIPIENTS = [f"W{i}" for i in range(20, 25)]

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
                                        'rng': '0031-within-trial-{i}:{seed}',
                                        'procedure': 'for each i, one random.Random(rng) stream; for k = 0 .. trials.count - 1 in order, '
                                                     'shuffle the list [A, B, C] once with that stream and assign it to (t_k, t_k + '
                                                     'b_offset, t_k + c_offset)'},
              'input_after_experience': 'none',
              'probes': 'none'}

INTERVENTION = {'kind': 'state_block_swap',
                'swap_time': {'rule': 'tau = max{ t in [swap_window.first, swap_window.last] : no Unit fired at Pulse t in any of the 26 '
                                      'natural bodies }',
                              'common_to_all_recipients': True,
                              'state': 'end_of_pulse_tau',
                              'if_none': 'individual_not_outside_for_all_eight_judgments_and_reported',
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
                'block': {'family': 'Wt',
                          'replace': ['connections.weight'],
                          'keep_from_recipient': ['units.activity',
                                                  'units.adaptation',
                                                  'units.refractory_remaining',
                                                  'units.fire_count',
                                                  'connections.pre_trace',
                                                  'connections.post_trace']},
                'swapped_bodies': 'for each recipient r in recipients, for each donor d in donors: clone r at end of tau, replace the six '
                                  "weights by d's values at end of tau, run tau + 1 .. body_runs_to with plasticity",
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
              'scores': {'rank_score': 's^x_r(d) = sum over donors e != d of sign(x_r(d) - x_r(e))',
                         'total_score': 'S^x(d) = sum over recipients r of s^x_r(d)'},
              'primary': {'window': 'count_window_main',
                          'per_individual': {'Agg': {'O_Delta_AB_above': 'S^{Delta_AB}(O) > max_{d in reference} S^{Delta_AB}(d)',
                                                     'O_above': 'S^D(O) > max_{d in reference} S^D(d)',
                                                     'M_below': 'S^D(M) < min_{d in reference} S^D(d)',
                                                     'O_and_M_split': 'O_above and M_below'},
                                             'All': {'O_Delta_AB_above': 'for every recipient r: Delta_AB(Y_r(O)) > max_{d in reference} '
                                                                         'Delta_AB(Y_r(d))',
                                                     'O_above': 'for every recipient r: D(Y_r(O)) > max_{d in reference} D(Y_r(d))',
                                                     'M_below': 'for every recipient r: D(Y_r(M)) < min_{d in reference} D(Y_r(d))',
                                                     'O_and_M_split': 'O_above and M_below'}},
                          'across_individuals': {'Agg': {'h_Ca': 'count(O_Delta_AB_above)',
                                                         'h_O': 'count(O_above)',
                                                         'h_M': 'count(M_below)',
                                                         'h_OM': 'count(O_and_M_split)'},
                                                 'All': {'h_Ca': 'count(O_Delta_AB_above)',
                                                         'h_O': 'count(O_above)',
                                                         'h_M': 'count(M_below)',
                                                         'h_OM': 'count(O_and_M_split)'}}},
              'propositions': {'order_preservation': 'for fixed r and x: x_r(d) > x_r(e) implies s^x_r(d) >= s^x_r(e) + 2; x_r(d) = x_r(e) '
                                                     'implies s^x_r(d) = s^x_r(e)',
                               'single_recipient_reduction': 'with one recipient, each Agg event equals the 0029 Wt event for that '
                                                             'recipient',
                               'all_subset_of_agg': 'each All event implies the corresponding Agg event; h^All <= h^Agg for every judgment',
                               'null_bound': 'under the null, (S(O), S(W_1..W_19)) is exchangeable, so P(Agg event) <= 1/20 (1/420 for '
                                             'J_OM); All events have the same bounds'},
              'auxiliary': {'per_individual': {'swap_time': True,
                                               'per_body_components': ['six_N_counts',
                                                                       'Delta_AB',
                                                                       'Delta_AC',
                                                                       'Delta_BC',
                                                                       'D',
                                                                       'spike_counts_per_role',
                                                                       'silent_roles'],
                                               'scores': ['rank_scores_per_recipient_and_donor', 'total_scores_per_donor'],
                                               'per_recipient_0029_form_events': 'for each recipient r, the four 0029 Wt events; per '
                                                                                 'individual the number k (0..5) of recipients where each '
                                                                                 'holds',
                                               'ranks': ['rank_of_total_Delta_AB_O_among_reference',
                                                         'rank_of_total_D_O_among_reference',
                                                         'rank_of_total_D_M_among_reference'],
                                               'Agg_opposite_direction': ['S^{Delta_AB}(O) < min', 'S^D(O) < min', 'S^D(M) > max'],
                                               'frozen_per_judgment': {'Agg': 'all total scores used by the judgment are equal',
                                                                       'All': 'number of recipients (0..5) in which all values used by the '
                                                                              'judgment are equal'},
                                               'target_only_silence': 'for each recipient r and target Y_r(O) (J_Ca, J_O) and Y_r(M) (J_M): '
                                                                      'whether its set of silent roles differs from that of every Y_r(W_i); '
                                                                      'per individual the number of such recipients, and how often it '
                                                                      'co-occurs with each primary event',
                                               'birth_margin_strata': {'g': 'g_i = intrinsic_drive_i / (1 - decay) - threshold_i for roles '
                                                                            'A, B, C (birth Unit dynamics)',
                                                                       'strata': {'structural': 'g_i < -0.03',
                                                                                  'conditional': '-0.03 <= g_i < 0',
                                                                                  'active': 'g_i >= 0'},
                                                                       'record': 'per role and stratum: individuals, no-tau individuals, '
                                                                                 'and counts of each of the eight primary events'},
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
                                                   'distribution_of_k_per_event': True,
                                                   'no_tau_individuals': True,
                                                   'clopper_pearson_95_of_h_over_20': ['Agg.h_Ca',
                                                                                       'Agg.h_O',
                                                                                       'Agg.h_M',
                                                                                       'Agg.h_OM',
                                                                                       'All.h_Ca',
                                                                                       'All.h_O',
                                                                                       'All.h_M',
                                                                                       'All.h_OM']},
                            'when_no_tau': {'recorded': ['natural_body_components_and_silence', 'birth_margin_strata', 'natural_comparison'],
                                            'null_with_reason_no_tau': ['swapped_body_components',
                                                                        'scores',
                                                                        'per_recipient_0029_form_events',
                                                                        'ranks',
                                                                        'Agg_opposite_direction',
                                                                        'frozen_per_judgment',
                                                                        'target_only_silence',
                                                                        'swapped_body_silence'],
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
                           'heterogeneity_tests_across_recipients',
                           'ratio_or_difference_of_h_All_and_h_Agg',
                           'recipient_selection_by_data',
                           'post_hoc_windows',
                           'post_hoc_lags',
                           'contribution_shares',
                           'comparison_with_earlier_experiments_h',
                           'individual_eligibility_filters',
                           'selection_by_natural_comparison',
                           'selection_by_birth_margin_strata',
                           'selection_by_target_only_silence',
                           'count_exceeding_events',
                           'units_block_swap',
                           'probe_readouts',
                           'between_trial_shuffle_reference']}

JUDGMENT = {'families': {'Agg': {'events': 'total_scores_across_recipients', 'direction': 'one_sided', 'alpha': 0.05},
                         'All': {'events': 'all_recipients_0029_form', 'direction': 'one_sided', 'alpha': 0.05}},
            'nesting': 'All event implies Agg event for each judgment; same null hypothesis; same thresholds',
            'experiment_wide_error_rate_claimed': 0.05,
            'per_family': {'alpha_split': {'J_Ca': 0.016, 'J_O': 0.016, 'J_M': 0.016, 'J_OM': 0.002},
                           'Agg': {'J_Ca': {'statistic': 'h_Ca',
                                            'holds_if': 'h_Ca >= 4',
                                            'per_individual_null_probability_at_most': '1/20'},
                                   'J_O': {'statistic': 'h_O', 'holds_if': 'h_O >= 4', 'per_individual_null_probability_at_most': '1/20'},
                                   'J_M': {'statistic': 'h_M', 'holds_if': 'h_M >= 4', 'per_individual_null_probability_at_most': '1/20'},
                                   'J_OM': {'statistic': 'h_OM',
                                            'holds_if': 'h_OM >= 2',
                                            'per_individual_null_probability_at_most': '1/420'}},
                           'All': {'J_Ca': {'statistic': 'h_Ca',
                                            'holds_if': 'h_Ca >= 4',
                                            'per_individual_null_probability_at_most': '1/20'},
                                   'J_O': {'statistic': 'h_O', 'holds_if': 'h_O >= 4', 'per_individual_null_probability_at_most': '1/20'},
                                   'J_M': {'statistic': 'h_M', 'holds_if': 'h_M >= 4', 'per_individual_null_probability_at_most': '1/20'},
                                   'J_OM': {'statistic': 'h_OM',
                                            'holds_if': 'h_OM >= 2',
                                            'per_individual_null_probability_at_most': '1/420'}}},
            'null_hypothesis': {'single_O': "for every individual, the joint distribution of the five recipients' states at tau and the "
                                            "21 donors' weight blocks at tau is invariant under permutations of the labels O, W1..W19 (M "
                                            'fixed)',
                                'single_M': 'the same with M, W1..W19 (O fixed)',
                                'OM': 'the same under all permutations of the 21 donors'},
            'recipient_donor_independence_assumption': "given the birth state, the recipients' states are treated as independent of the "
                                                       "donors' weight blocks (distinct RNG stream names; O and M are fixed sequences; "
                                                       'statistical model assumption)',
            'independence_assumption': 'birth states and within-trial shuffle RNG streams are treated as independent across individuals '
                                       '(statistical model assumption; not implied by distinct seeds)',
            'within_individual_dependence': 'one_event_per_individual_per_judgment',
            'holds_means': 'reject_null_at_alpha_under_assumptions',
            'ties': 'strict_inequality_counts_ties_as_not_outside',
            'frozen_individuals': 'count_as_not_outside',
            'no_swap_time': 'count_as_not_outside',
            'no_tau_individuals': {'in_denominator_of_20': True,
                                   'all_eight_events': False,
                                   'recorded_separately_from_frozen': True,
                                   'counted_as_completed': True},
            'on_any_invalid': 'experiment_invalid_no_judgment',
            'scope': 'C0_C_I_effect_of_donor_weight_block_into_five_W_type_recipients_at_tau_before_main_window_on_lag1_asymmetry_relative_to_donor_reference',
            'not_judged': ['background_independence_for_arbitrary_backgrounds',
                           'heterogeneity_across_recipients',
                           'O_or_M_as_recipients',
                           'other_swap_times',
                           'C_II_reproduction_and_elimination_of_natural_difference',
                           'C_III_cause_of_natural_difference',
                           'exclusivity_of_blocks',
                           'contribution_shares',
                           'components_within_blocks',
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
           'swapped_bodies': {'per_body': ['swap_record_tau_block_recipient_donor',
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
                                                             'order; the first firing (body in order O, M, W1..W24; unit in order s1, '
                                                             's2, s3) at that Pulse among the natural bodies'}},
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
          'smoke_report_check_values': ['fail', 'ok']}

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
    Agg・All のどちらも一方向で、All は Agg の部分集合なので同じ上界。"""
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

    # 脳の設計図（README §1。0026・0028〜0030 と同じ C0）
    expect(protocol["brain"] == BRAIN, "設計図・Receptor・不応期・可塑性の対象が 0026・0028〜0030 の C0 と違う")
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
           "介入（τ の規則・τ がない個体・受け手・ドナー・塊・入れ替えた本体・確認の本体・不変の関係）が道具と違う")
    expect(list(W.RECIPIENTS) == RECIPIENTS and list(W.DONORS) == ["O", "M"] + REF and list(W.REFERENCE) == REF
           and not set(W.RECIPIENTS) & set(W.DONORS) and set(W.RECIPIENTS) | set(W.DONORS) == set(W.BODIES),
           "受け手・ドナー・参照のドナーが W20〜W24・(O, M, W1〜W19)・W1〜W19 ではないか、重なる・本体を覆わない")
    expect(iv["block"]["replace"] == [f"connections.{f}" for f in W.WEIGHTS[1]] and not W.WEIGHTS[0]
           and iv["block"]["keep_from_recipient"] == ([f"units.{f}" for f in W.UNIT_FIELDS]
                                                       + [f"connections.{f}" for f in W.CONNECTION_FIELDS if f not in W.WEIGHTS[1]]),
           "入れ替える欄（重みだけ）と受け手のまま残す欄が道具と違う")
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
        expect(tuple(QUANTITIES["primary"]["per_individual"][f]) == EVENTS, f"{f}：4 つの事象の名前が道具と違う")
    # 入れ子（README §5.2）：同じ閾値・同じ帰無仮説・同じ割り当てなので、8 判定の水準は Agg の和
    expect(HOLDS_MIN["Agg"] == HOLDS_MIN["All"] and pf["Agg"] == pf["All"]
           and Fraction(str(j["experiment_wide_error_rate_claimed"])) == sum(split.values()) == Fraction(str(EXPERIMENT_WIDE_ALPHA)),
           "Agg と All の閾値・帰無の確率が同じでないか、8 判定の水準が Agg の割り当ての和 0.05 ではない")
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
