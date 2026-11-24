"""実験 0042 の protocol.yaml と道具（measure.py・AS2b の道具 as2b.py・関門の宣言 v0.2・analysis.py）が食い違っていないことの機械的な確認。

run.py・analyze.py が、実行・解析の前に check(protocol) を呼ぶ。食い違いがあれば AssertionError で止まる。
事前登録（README・protocol.yaml v0.2。#195 merge `49d99e4`）の値を写した固定値と、道具の定数・関門の宣言の値を比べる。
analyze.py の量の組・O1 の契約テストの組と protocol の対応は、契約テストで確かめる（analyze.py はこのファイルを読み込むため）。
"""

import hashlib
import importlib.util
import json
from fractions import Fraction
from math import comb
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXPERIMENT_FROM_DIR = HERE.name.split("_")[0]

# これまでに走らせた seed（0041 の alignment.py の SEEN に、0041 の本番・smoke・合成〔34001〜34399〕を足したもの。
# AS2b の道具の確認の seed 9101〜9106 は 9001〜9699 に、関門 0038 の合成の seed は 31001〜31040 に入っている）。重なってはいけない
SEEN = (set(range(1, 21)) | set(range(1001, 1021)) | set(range(2001, 2021)) | set(range(3001, 3007))
        | set(range(4001, 4021)) | set(range(5001, 5007)) | set(range(6001, 6021)) | set(range(7001, 7007))
        | set(range(8001, 8021)) | set(range(8101, 8107)) | set(range(9001, 9700))
        | set(range(10001, 10021)) | set(range(10101, 10107)) | set(range(11001, 11021))
        | set(range(11101, 11107)) | set(range(12001, 12021)) | set(range(12101, 12107))
        | set(range(13001, 13201)) | set(range(14001, 14201)) | set(range(15001, 15201)) | set(range(16001, 16300))
        | set(range(17001, 17300)) | set(range(18001, 18300)) | set(range(19001, 19300)) | set(range(20001, 20300))
        | set(range(21001, 21300)) | set(range(22001, 22300)) | set(range(23001, 23300)) | set(range(24001, 24300))
        | set(range(25001, 25300)) | set(range(26001, 26300)) | set(range(27001, 27300)) | set(range(28001, 28300))
        | set(range(29001, 29300)) | set(range(30001, 30300)) | set(range(31001, 31041)) | set(range(32001, 32400))
        | set(range(33001, 33400)) | set(range(34001, 34400)))

SEEDS = {"seeds": (35001, 35200), "smoke_seeds": (35201, 35206), "synthetic_seeds": (35301, 35399)}
NOT_USED = {"gate_synthetic": (31001, 31040), "experiment_0039": (32001, 32399), "experiment_0040": (33001, 33399),
            "experiment_0041": (34001, 34399)}
GATE_SHA256 = "e612efc5e6b084e1712520de64a877e0dd477d737b88695252f4cc234a64e1cb"
GATE_VALUES = {"cue_first": 41, "cue_spacing": 41, "cue_count": 50, "o": 2, "W": 19, "tie": "close_window_without_intent",
               "L": 2, "consequence_receptor": "cue_receptor", "multiplicity": "per_reservation", "lc3": None,
               "roles_stream": "as2b-roles-{seed}", "per_individual": ["A1", "A2"], "plasticity": "on", "outlet": True,
               "respond": True, "interventions": "none", "pulses": 2072}
TAKEN = ["schedule", "exit", "world", "roles", "bodies.per_individual", "bodies.plasticity", "bodies.outlet", "bodies.respond",
         "bodies.interventions", "bodies.pulses"]
NOT_TAKEN = ["synthetic_seeds", "evaluation", "one_time_execution"]
TIMELINE = {"experience_E": {"windows": [1, 25], "pulses": [1, 1065]}, "boundary_P_E": 1065, "last_E_outcome_pulse": 1047,
            "test_U": {"windows": [26, 50], "pulses": [1066, 2072], "length": 1007}, "first_U_window": [1068, 1086],
            "earliest_U_consequence_pulse": 1070, "body_pulses": 2072}
SYSTEMS = ["B_A1", "B_A2", "B_A1_rerun",
           "G_A1_WA1", "G_A1_WA2", "G_A1_WA1_tr", "G_A2_WA2", "G_A2_WA1", "G_A2_WA2_tr",
           "G_A1_X1", "G_A1_X2", "G_A2_X1", "G_A2_X2",
           "N_A1_WA1", "N_A1_WA2", "N_A2_WA2", "N_A2_WA1"]
PULSES_PER_INDIVIDUAL = 20314
QUANTITIES = ["T_c", "T", "T_any", "BE_W", "BE", "TE_F", "D", "S_c", "S", "TN_c", "TN", "K_c", "Z_c", "delta"]
OUTCOMES = ["invalid", "inconclusive", "not_established", "plus", "minus"]
CHECKS = [f"O{i}" for i in range(1, 16)]
SE = [f"SE-T{i}" for i in range(1, 13)]
RECORDS = [f"R{i}" for i in range(1, 10)]
MIN_M, INDIVIDUALS = 10, 200
ALPHA_PER_DIRECTION = Fraction(1, 40)
CONTRACT_TESTS = ["tests/integration/test_as1_contract.py", "tests/integration/test_as2b_contract.py",
                  "tests/integration/test_as2b_rule_dependence_0039.py", "tests/integration/test_as2b_weight_extremes_0040.py",
                  "tests/integration/test_as2b_rule_weight_direction_0041.py"]
E_T_KEYS = {"m_def", "p_nz", "p_any", "cancellations", "p_plus_minus", "p_dir", "abs_T", "undefined_count", "no_threshold",
            "reporting_prominence"}
MUST_REPORT_KEYS = {"per_background", "two_by_two", "natural_pair", "sensitivity", "no_feedback", "feedback_contrast",
                    "plasticity_contrast", "delta", "diverged_subpopulation", "zero_table"}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def binom_upper_tail(m: int, k: int) -> Fraction:
    return Fraction(sum(comb(m, j) for j in range(k, m + 1)), 2 ** m)


def receptor_weights(manifest: dict) -> set[float]:
    return {float(p["weight"]) for p in manifest["projections"] if str(p["from"]).startswith("receptor.")}


def check(protocol: dict) -> None:
    M = _load(f"measure_{EXPERIMENT_FROM_DIR}_alignment", HERE / "measure.py")
    AX = _load(f"analysis_{EXPERIMENT_FROM_DIR}_alignment", HERE / "analysis.py")
    A, AS1 = M.A, M.AS1
    assert protocol["experiment"] == EXPERIMENT_FROM_DIR == "0042"
    assert protocol["kind"] == "preregistered_test"
    assert protocol["execution_form"].startswith("0039-type preregistered experiment")
    # seed（D5）。関門・0039・0040・0041 の seed は走らせない（README §9.2）
    ranges = {}
    for key, (first, last) in SEEDS.items():
        assert protocol[key] == {"first": first, "last": last}, key
        ranges[key] = set(range(first, last + 1))
        assert not (ranges[key] & SEEN), f"{key} がこれまでに走らせた seed と重なる"
    assert not (ranges["seeds"] & ranges["smoke_seeds"]) and not (ranges["seeds"] & ranges["synthetic_seeds"]) \
        and not (ranges["smoke_seeds"] & ranges["synthetic_seeds"])
    assert len(ranges["seeds"]) == INDIVIDUALS
    for key, (first, last) in NOT_USED.items():
        assert protocol["not_used_seeds"][key] == {"first": first, "last": last}, key
        assert set(range(first, last + 1)) <= SEEN
    # 引き継ぐ関門の組（README §1.1・O2）：宣言の SHA-256 と、宣言から取る値
    gate = protocol["inherited_gate_set"]
    raw = (ROOT / gate["declaration"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == gate["sha256"] == GATE_SHA256 and gate["version"] == "0.2"
    decl = json.loads(raw)
    assert decl["version"] == "0.2"
    cp, b = decl["schedule"]["cue_pulses"], decl["bodies"]
    from_decl = {"cue_first": cp["first"], "cue_spacing": cp["spacing"], "cue_count": cp["count"],
                 "o": decl["schedule"]["window_offset_o"], "W": decl["schedule"]["window_length_W"],
                 "tie": decl["exit"]["tie_rule"], "L": decl["world"]["delay_L"],
                 "consequence_receptor": decl["world"]["consequence_receptor"], "multiplicity": decl["world"]["multiplicity"],
                 "lc3": decl["world"]["lc3"], "roles_stream": decl["roles"]["stream"],
                 "per_individual": [x["rule_c"] for x in b["per_individual"]], "plasticity": b["plasticity"],
                 "outlet": b["outlet"], "respond": b["respond"], "interventions": b["interventions"], "pulses": b["pulses"]}
    assert gate["expected_values"] == from_decl == GATE_VALUES
    assert gate["taken_from_declaration"] == TAKEN and gate["not_taken"] == NOT_TAKEN
    assert decl["world"]["rule_c_assignment"] == "both_values_as_separate_bodies"
    assert decl["synthetic_seeds"]["first"] == NOT_USED["gate_synthetic"][0] \
        and decl["synthetic_seeds"]["last"] == NOT_USED["gate_synthetic"][1]
    assert M.gate_declaration(protocol) == (decl, GATE_SHA256)
    # 道具（AS2b の道具は変えない）
    tools = protocol["tools"]
    assert tools["base"] == "experiments/as2b_choice/as2b.py" and (ROOT / tools["base"]).exists()
    assert tools["contract_tests"] == CONTRACT_TESTS and all((ROOT / f).exists() for f in tools["contract_tests"])
    assert sorted(tools["previous_experiments"]) == ["0039", "0040", "0041"]
    assert (ROOT / tools["contract"]).exists() and (ROOT / tools["criteria"]).exists()
    for name in ("build", "clone", "sigma", "audit", "advance_to", "assign_roles", "sigma_diff"):
        assert callable(getattr(A, name)), name
    for name in ("transplant", "declare", "switch_world"):
        assert callable(getattr(A.AS2bSystem, name)), name
    # 脳（C0 のまま）
    brain = protocol["brain"]
    assert (ROOT / brain["manifest"]).resolve() == AS1.C0_MANIFEST.resolve()
    manifest = AS1.c0_manifest_raw()
    assert brain["adaptation_tau_pulses"] == manifest["defaults"]["dynamics"]["adaptation_tau"] / A.PULSE_INTERVAL_SECONDS == 300
    assert manifest["defaults"]["dynamics"]["refractory_pulses"] == brain["refractory_pulses"] == 0
    assert brain["units"] == list(A.UNITS) and brain["action_ids"] == {"source1": "A1", "source2": "A2"}
    assert tuple(brain["action_ids"].values()) == A.ACTION_IDS
    assert receptor_weights(manifest) == receptor_weights(AS1.as1_manifest_raw()) == {float(brain["receptor_weight"])} == {1.0}
    parsed = A.parse_neuroarchitecture(AS1.as1_manifest_raw())
    assert parsed.plasticity.w_max == brain["w_max"] == 0.01 and parsed.plasticity.w_min == brain["w_min"] == 0.0
    plastic = [p for p in parsed.projections if p.plastic]
    assert brain["plastic_connections"] == "six_s_to_s" and len(plastic) == 6
    assert {p.weight for p in plastic} == {brain["initial_weight_w0"]} == {0.005} and brain["initial_weight_w0"] * 2 == brain["w_max"]
    assert "as2b-roles-{seed}" in brain["roles"] and 'f"as2b-roles-{seed}"' in (ROOT / tools["base"]).read_text(encoding="utf-8")
    c0 = AX.c0_values()
    assert (c0["w_min"], c0["w_max"], c0["w0"]) == (brain["w_min"], brain["w_max"], brain["initial_weight_w0"])
    # 世界（README §2.3）
    world = protocol["world"]
    assert {k: world["rule_c"][k] for k in ("B_A1", "B_A2", "B_A1_rerun")} == {n: M.RULE_OF[n] for n in M.BODIES + (M.RERUN,)}
    assert all(M.RULE_OF[n] == M.RULE_OF[M.BACKGROUND[n]] for n in M.CLONES)
    assert world["not_used"] == ["replay", "lc3", "rule_change_at_boundary"]
    assert world["no_response"].startswith("N systems: switch_world(respond=False) called exactly once at P_E")
    assert list(M.NO_RESPONSE) == [n for n in M.CLONES if n.startswith("N_")]
    # 区間（README §2.1）：関門の宣言から作った Plan と、protocol の値と analysis.py の算術
    tl = protocol["timeline"]
    assert tl["pulse_interval_seconds"] == A.PULSE_INTERVAL_SECONDS == 1.0
    assert {k: tl[k] for k in TIMELINE} == TIMELINE
    plan = M.formal_plan(protocol)
    assert plan == M.Plan(41, 41, 50, 2, 19, 2, 25) and (plan.p_e, plan.end) == (1065, 2072)
    windows = plan.schedule().windows
    assert windows[24] == (25, 1027, 1045) and windows[25] == (26, 1068, 1086)
    iv = AX.intervals(AX.gate_set())
    assert iv["P_E"] == plan.p_e and iv["last_E_outcome_pulse"] == tl["last_E_outcome_pulse"]
    assert iv["U_pulses"] == [plan.p_e + 1, plan.end] and iv["U_length"] == tl["test_U"]["length"]
    assert iv["earliest_U_consequence_pulse"] == tl["earliest_U_consequence_pulse"]
    # 系（README §2.2）
    systems = protocol["systems"]
    assert systems["per_individual"] == SYSTEMS == list(M.SYSTEMS)
    assert list(AX.FULL_BODIES) + list(AX.U_SYSTEMS) == SYSTEMS
    assert systems["pulses_per_individual"] == PULSES_PER_INDIVIDUAL == iv["pulses_per_individual"]
    assert systems["trace_policy"] == AS1.ADVANCE
    assert systems["observation"]["not_observed"] == [M.RERUN]
    assert {n: M.WEIGHTS_OF[n] for n in M.CLONES} == {n: n.split("_")[2].removeprefix("W") for n in M.CLONES}
    assert set(M.TRANSPLANTS) == {"G_A1_WA2", "G_A1_WA1_tr", "G_A2_WA1", "G_A2_WA2_tr", "G_A1_X1", "G_A1_X2", "G_A2_X1",
                                  "G_A2_X2", "N_A1_WA2", "N_A2_WA1"}
    ex = protocol["extremes"]
    assert M.extremes(protocol) == {k: dict(AX.extremes(c0)[k]) for k in ("X1", "X2")}
    assert ex["contrast_in_delta_units"] == AX.extremes(c0)["contrast_in_delta_units"] == 0.02
    st = protocol["storage"]
    assert st["raw"].startswith("seeds/<seed>/raw.json.gz (guard)")
    assert st["pulse_weights"].startswith("clones only, every U pulse")
    # 量（README §3）
    q = protocol["quantities"]
    assert [k for k in QUANTITIES if k in q] == QUANTITIES
    assert q["arithmetic"].startswith("exact rational arithmetic")
    swap = AX.label_swap_and_identity_check()
    assert swap["invariant"] == ["T", "T_any", "BE", "TE_F", "D", "S", "TN"] and swap["TE_F_equals_half_T_plus_BE"] is True
    assert swap["cancellation_gives_T_zero_with_T_any_true"] is True
    assert AX.delta_label_swap_check()["delta_invariant_under_label_swap"] is True
    # 判定（README §4・§5）
    j = protocol["judgment"]
    jt = j["J_T"]
    assert jt["min_population"] == MIN_M == AX.MIN_M and jt["below_min"] == "inconclusive" and jt["only_judgment"] is True
    assert jt["alpha"] == {"two_sided": 0.05, "per_direction": 0.025}
    assert Fraction(str(jt["alpha"]["per_direction"])) == ALPHA_PER_DIRECTION == AX.ALPHA_PER_SIDE
    assert set(j["k2_of_m"]) == set(range(MIN_M, INDIVIDUALS + 1))
    for m, k in j["k2_of_m"].items():
        assert binom_upper_tail(m, k) <= ALPHA_PER_DIRECTION < binom_upper_tail(m, k - 1) and AX.k2(m) == k, m
    assert AX.INDIVIDUALS == INDIVIDUALS
    assert j["outcomes"] == OUTCOMES
    assert set(j["null_hypothesis"]) == {"status", "H0_T", "conditional_exactness"}
    assert j["interval"].startswith("Clopper-Pearson 95% (two-sided)")
    assert set(j["per_individual"]["sign"]) == {"plus", "minus", "zero", "undefined"}
    assert set(protocol["estimate_E_T"]) == E_T_KEYS
    assert set(protocol["must_report"]) == MUST_REPORT_KEYS
    # 構造上の同値・命題 S-1・操作の確認・記録（README §6〜§9）
    assert protocol["structural_equivalences"] == SE and protocol["operation_checks"] == CHECKS
    assert sorted(protocol["records"], key=lambda r: int(r[1:])) == RECORDS
    assert protocol["f1_tolerance"] == 1e-12
    s1 = protocol["proposition_S1"]
    bound = AX.silence_bound(c0, AX.gate_set())
    assert abs(bound["E_S"] - s1["E_S_value"]) < 5e-6
    share = AX.silence_probability(c0, bound["E_S"])
    assert abs(share["per_source_structural"] - s1["per_source_share"]) < 5e-5
    assert abs(share["individual_at_least_one_structural_source"] - s1["individual_share_at_least_one"]) < 5e-5
    assert s1["use"].startswith("labels only; never used in the judgment or the estimate")
    assert set(protocol["not_displayed"]["quantities"]) >= {"s", "n_U", "T", "T_any", "T_A1", "T_A2", "delta", "signs",
                                                            "E_T", "p_nz", "p_any", "k_star", "first_divergence_pulse"}


if __name__ == "__main__":
    check(yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8")))
    print("ok")
