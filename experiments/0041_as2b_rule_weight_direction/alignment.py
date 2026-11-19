"""実験 0041 の protocol.yaml と道具（measure.py・AS2b の道具 as2b.py・関門の宣言 v0.2・analysis.py）が食い違っていないことの機械的な確認。

run.py・analyze.py が、実行・解析の前に check(protocol) を呼ぶ。食い違いがあれば AssertionError で止まる。
事前登録（README・protocol.yaml v0.1。#189 merge `5fba79f`）の値を写した固定値と、道具の定数・関門の宣言の値を比べる。
analyze.py の量の組（QUANTITIES）・O1 の契約テストの組と protocol の対応は、契約テストで確かめる（analyze.py はこのファイルを読み込むため）。
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

# これまでに走らせた seed（0040 の alignment.py の SEEN に、0040 の本番・smoke・合成〔33001〜33399〕を足したもの。
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
        | set(range(33001, 33400)))

SEEDS = {"seeds": (34001, 34200), "smoke_seeds": (34201, 34206), "synthetic_seeds": (34301, 34399)}
NOT_USED = {"gate_synthetic": (31001, 31040), "experiment_0039": (32001, 32399), "experiment_0040": (33001, 33399)}
GATE_SHA256 = "e612efc5e6b084e1712520de64a877e0dd477d737b88695252f4cc234a64e1cb"
GATE_VALUES = {"cue_first": 41, "cue_spacing": 41, "cue_count": 50, "o": 2, "W": 19, "tie": "close_window_without_intent",
               "L": 2, "consequence_receptor": "cue_receptor", "multiplicity": "per_reservation", "lc3": None,
               "roles_stream": "as2b-roles-{seed}", "per_individual": ["A1", "A2"], "plasticity": "on", "outlet": True,
               "respond": True, "interventions": "none"}
TAKEN = ["schedule", "exit", "world", "roles", "bodies.per_individual", "bodies.plasticity", "bodies.outlet", "bodies.respond",
         "bodies.interventions"]
NOT_TAKEN = ["bodies.pulses", "synthetic_seeds", "evaluation", "one_time_execution"]
TIMELINE = {"experience_E": {"windows": [1, 25], "pulses": [1, 1065]}, "boundary_P_E": 1065, "last_E_outcome_pulse": 1047,
            "runs_to": 1065}
BODIES = ["B_A1", "B_A2", "B_A1_rerun"]
RULE_C = {"B_A1": "A1", "B_A2": "A2", "B_A1_rerun": "A1"}
QUANTITIES = ["delta", "q_1", "q_2", "delta_back", "epsilon"]
OUTCOMES = ["invalid", "not_established", "plus", "minus"]
CHECKS = [f"O{i}" for i in range(1, 12)]
SE = [f"SE-B{i}" for i in range(1, 8)]
RECORDS = [f"R{i}" for i in range(1, 9)]
M_FIXED, K2_200 = 200, 115
ALPHA_PER_DIRECTION = Fraction(1, 40)
CONTRACT_TESTS = ["tests/integration/test_as1_contract.py", "tests/integration/test_as2b_contract.py",
                  "tests/integration/test_as2b_rule_dependence_0039.py", "tests/integration/test_as2b_weight_extremes_0040.py"]


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
    assert protocol["experiment"] == EXPERIMENT_FROM_DIR == "0041"
    assert protocol["kind"] == "preregistered_test"
    assert protocol["execution_form"].startswith("0039-type preregistered experiment")
    # seed（D5）。関門・0039・0040 の seed は走らせない（README §9.2）
    ranges = {}
    for key, (first, last) in SEEDS.items():
        assert protocol[key] == {"first": first, "last": last}, key
        ranges[key] = set(range(first, last + 1))
        assert not (ranges[key] & SEEN), f"{key} がこれまでに走らせた seed と重なる"
    assert not (ranges["seeds"] & ranges["smoke_seeds"]) and not (ranges["seeds"] & ranges["synthetic_seeds"]) \
        and not (ranges["smoke_seeds"] & ranges["synthetic_seeds"])
    assert len(ranges["seeds"]) == M_FIXED
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
                 "outlet": b["outlet"], "respond": b["respond"], "interventions": b["interventions"]}
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
    assert tools["previous_experiment"] == "experiments/0040_as2b_weight_extremes" \
        and (ROOT / tools["previous_experiment"]).is_dir()
    assert (ROOT / tools["contract"]).exists() and (ROOT / tools["criteria"]).exists()
    for name in ("build", "sigma", "audit", "advance_to", "assign_roles", "sigma_diff"):
        assert callable(getattr(A, name)), name
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
    assert world["respond"] is True and world["rule_c"] == RULE_C == M.RULE_OF
    assert world["not_used"] == ["switch_world", "replay", "lc3"]
    # 区間（README §2.1）：関門の宣言から作った Plan と、protocol の値と analysis.py の算術
    tl = protocol["timeline"]
    assert tl["pulse_interval_seconds"] == A.PULSE_INTERVAL_SECONDS == 1.0
    assert {k: tl[k] for k in TIMELINE} == TIMELINE
    plan = M.formal_plan(protocol)
    assert plan == M.Plan(41, 41, 50, 2, 19, 2, 25) and plan.p_e == 1065
    windows = plan.schedule().windows
    assert windows[24] == (25, 1027, 1045) and windows[25] == (26, 1068, 1086)
    iv = AX.intervals(AX.gate_set())
    assert iv["P_E"] == plan.p_e and iv["last_E_outcome_pulse"] == tl["last_E_outcome_pulse"]
    assert iv["window_boundaries"] == plan.boundaries and iv["next_cue_after_P_E"] == plan.p_e + 1
    # 本体（README §2.2）
    bodies = protocol["bodies"]
    assert bodies["per_individual"] == BODIES == list(M.SYSTEMS)
    assert {n: bodies[n]["rule_c"] for n in BODIES} == RULE_C
    assert [n for n in BODIES if bodies[n]["observed"]] == list(M.BODIES) and M.RERUN == "B_A1_rerun"
    assert bodies["observation"] == {"observed": list(M.BODIES), "not_observed": [M.RERUN]}
    assert bodies["B_A1_rerun"]["run"].startswith("advanced to P_E in one call with the default log; no per-pulse reading")
    assert bodies["interventions"] == "none"
    assert bodies["pulses_per_individual"] == len(BODIES) * plan.p_e == iv["pulses_per_individual"] == 3195
    st = protocol["storage"]
    assert st["sigma"]["pulse_0"] == "observed bodies" and st["sigma"]["P_E"].startswith("all three bodies: the full sigma at P_E")
    assert st["pulse_weights"].startswith("observed bodies only")
    assert st["raw"].startswith("seeds/<seed>/raw.json.gz (guard)")
    # 量（README §3）
    q = protocol["quantities"]
    assert [k for k in QUANTITIES if k in q] == QUANTITIES
    assert q["arithmetic"].startswith("exact rational arithmetic on the stored binary64 values")
    assert AX.label_swap_check(c0)["delta_delta_back_epsilon_invariant"] is True
    # 判定（README §4・§5）
    j = protocol["judgment"]
    jb = j["J_B"]
    assert jb["m"] == M_FIXED and jb["k2_200"] == K2_200 and jb["only_judgment"] is True
    assert jb["alpha"] == {"two_sided": 0.05, "per_direction": 0.025}
    assert Fraction(str(jb["alpha"]["per_direction"])) == ALPHA_PER_DIRECTION == AX.ALPHA_PER_SIDE
    assert binom_upper_tail(M_FIXED, K2_200) <= ALPHA_PER_DIRECTION < binom_upper_tail(M_FIXED, K2_200 - 1)
    assert AX.k2(M_FIXED) == K2_200 and AX.INDIVIDUALS == M_FIXED
    assert j["outcomes"] == OUTCOMES
    assert set(j["null_hypothesis"]) == {"status", "H0_B", "zeros"}
    assert j["interval"].startswith("Clopper-Pearson 95% (two-sided)")
    assert set(j["per_individual"]["sign"]) == {"plus", "minus", "zero"}
    assert set(protocol["estimate_E_B"]) == {"p_change", "p_plus_minus", "abs_delta", "no_threshold"}
    assert set(protocol["must_report"]) == {"diverged_subpopulation", "delta_back", "epsilon", "cross_table", "zero_table"}
    # 構造上の同値・命題 S-1・操作の確認・記録（README §6〜§9）
    assert protocol["structural_equivalences"] == SE and protocol["operation_checks"] == CHECKS
    assert sorted(protocol["records"], key=lambda r: int(r[1:])) == RECORDS
    s1 = protocol["proposition_S1"]
    bound = AX.silence_bound(c0, AX.gate_set())
    assert abs(bound["E_S"] - s1["E_S_value"]) < 5e-6
    share = AX.silence_probability(c0, bound["E_S"])
    assert abs(share["per_source_structural"] - s1["per_source_share"]) < 5e-5
    assert abs(share["individual_at_least_one_structural_source"] - s1["individual_share_at_least_one"]) < 5e-5
    assert s1["use"].startswith("labels only; never used in the judgment or the estimate")
    assert set(protocol["not_displayed"]["quantities"]) >= {"delta", "q_1", "q_2", "delta_back", "epsilon", "signs", "E_B",
                                                            "k_star", "weights_at_P_E", "first_divergence_pulse"}


if __name__ == "__main__":
    check(yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8")))
    print("ok")
