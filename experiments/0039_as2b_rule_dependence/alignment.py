"""実験 0039 の protocol.yaml と道具（measure.py・AS2b の道具 as2b.py・関門の宣言 v0.2）が食い違っていないことの機械的な確認。

run.py・analyze.py が、実行・解析の前に check(protocol) を呼ぶ。食い違いがあれば AssertionError で止まる。
確定した事前登録（README・protocol.yaml v0.2、#179 merge `ba7ffba`）の値を写した固定値と、道具の定数・関門の宣言の値を比べる。
analyze.py の対比の組（CONTRASTS）・O1 の契約テストの組と protocol の対応は、契約テストで確かめる（analyze.py はこのファイルを読み込むため）。
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

# これまでに走らせた seed（0037 の alignment.py の SEEN に、0037 の本番・smoke・合成〔30001〜30299〕と、関門 0038 の合成の seed
# 〔31001〜31040〕を足したもの。AS2b の道具の確認の seed 9101〜9106 は 9001〜9699 に入っている）。重なってはいけない
SEEN = (set(range(1, 21)) | set(range(1001, 1021)) | set(range(2001, 2021)) | set(range(3001, 3007))
        | set(range(4001, 4021)) | set(range(5001, 5007)) | set(range(6001, 6021)) | set(range(7001, 7007))
        | set(range(8001, 8021)) | set(range(8101, 8107)) | set(range(9001, 9700))
        | set(range(10001, 10021)) | set(range(10101, 10107)) | set(range(11001, 11021))
        | set(range(11101, 11107)) | set(range(12001, 12021)) | set(range(12101, 12107))
        | set(range(13001, 13201)) | set(range(14001, 14201)) | set(range(15001, 15201)) | set(range(16001, 16300))
        | set(range(17001, 17300)) | set(range(18001, 18300)) | set(range(19001, 19300)) | set(range(20001, 20300))
        | set(range(21001, 21300)) | set(range(22001, 22300)) | set(range(23001, 23300)) | set(range(24001, 24300))
        | set(range(25001, 25300)) | set(range(26001, 26300)) | set(range(27001, 27300)) | set(range(28001, 28300))
        | set(range(29001, 29300)) | set(range(30001, 30300)) | set(range(31001, 31041)))

SEEDS = {"seeds": (32001, 32200), "smoke_seeds": (32201, 32206), "synthetic_seeds": (32301, 32399)}
GATE_SEEDS = (31001, 31040)
GATE_SHA256 = "e612efc5e6b084e1712520de64a877e0dd477d737b88695252f4cc234a64e1cb"
GATE_VALUES = {"cue_first": 41, "cue_spacing": 41, "cue_count": 50, "o": 2, "W": 19, "tie": "close_window_without_intent",
               "L": 2, "consequence_receptor": "cue_receptor", "multiplicity": "per_reservation", "lc3": None,
               "roles_stream": "as2b-roles-{seed}", "body_pulses": 2072}
TIMELINE = {"experience_E": {"windows": [1, 25], "pulses": [1, 1065]}, "P_E": 1065,
            "trial_U": {"windows": [26, 50], "pulses": [1066, 2072]}, "runs_to": 2072}
SYSTEMS = ["B_A1", "B_A2", "B_A1_rerun", "F_A1", "F_A2", "G_A1_WA1", "G_A1_WA2", "G_A1_WA1_tr",
           "G_A2_WA2", "G_A2_WA1", "G_A2_WA2_tr"]
CONTRASTS = {"D": ["B_A1", "B_A2"], "D_W": ["G_A1_WA1", "G_A1_WA2"], "D_W_rev": ["G_A2_WA1", "G_A2_WA2"],
             "D_F": ["F_A1", "F_A2"], "Z_A1": ["B_A1", "G_A1_WA1"], "Z_A2": ["B_A2", "G_A2_WA2"],
             "P_A1": ["B_A1", "F_A1"], "P_A2": ["B_A2", "F_A2"]}
OUTCOMES = {"invalid", "inconclusive", "J_7_not_established", "J_7_only", "both_same_direction", "both_opposite_direction"}
CHECKS = [f"O{i}" for i in range(1, 15)]
SE = [f"SE-{i}" for i in range(1, 10)]
K2_RANGE = (10, 200)
ALPHA_PER_DIRECTION = Fraction(1, 40)


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
    assert protocol["experiment"] == EXPERIMENT_FROM_DIR == "0039"
    assert protocol["kind"] == "preregistered_test"
    # seed（D5）。関門の seed は走らせない（README §9.2）
    ranges = {}
    for key, (first, last) in SEEDS.items():
        assert protocol[key] == {"first": first, "last": last}, key
        ranges[key] = set(range(first, last + 1))
        assert not (ranges[key] & SEEN), f"{key} がこれまでに走らせた seed と重なる"
    assert not (ranges["seeds"] & ranges["smoke_seeds"]) and not (ranges["seeds"] & ranges["synthetic_seeds"]) \
        and not (ranges["smoke_seeds"] & ranges["synthetic_seeds"])
    assert protocol["not_used_seeds"]["gate_synthetic"] == {"first": GATE_SEEDS[0], "last": GATE_SEEDS[1]}
    assert set(range(GATE_SEEDS[0], GATE_SEEDS[1] + 1)) <= SEEN
    # 引き継ぐ関門の組（README §1.1・O2）：宣言の SHA-256 と、宣言から取る値
    gate = protocol["inherited_gate_set"]
    raw = (ROOT / gate["declaration"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == gate["sha256"] == GATE_SHA256 and gate["version"] == "0.2"
    decl = json.loads(raw)
    assert decl["version"] == "0.2"
    cp = decl["schedule"]["cue_pulses"]
    from_decl = {"cue_first": cp["first"], "cue_spacing": cp["spacing"], "cue_count": cp["count"],
                 "o": decl["schedule"]["window_offset_o"], "W": decl["schedule"]["window_length_W"],
                 "tie": decl["exit"]["tie_rule"], "L": decl["world"]["delay_L"],
                 "consequence_receptor": decl["world"]["consequence_receptor"], "multiplicity": decl["world"]["multiplicity"],
                 "lc3": decl["world"]["lc3"], "roles_stream": decl["roles"]["stream"], "body_pulses": decl["bodies"]["pulses"]}
    assert gate["expected_values"] == from_decl == GATE_VALUES
    assert gate["taken_from_declaration"] == ["schedule", "exit", "world", "roles", "bodies"]
    assert gate["not_taken"] == ["synthetic_seeds", "evaluation", "one_time_execution"]
    assert decl["synthetic_seeds"]["first"] == GATE_SEEDS[0] and decl["synthetic_seeds"]["last"] == GATE_SEEDS[1]
    assert M.gate_declaration(protocol) == (decl, GATE_SHA256)
    # 道具（AS2b の道具は変えない）
    tools = protocol["tools"]
    assert tools["base"] == "experiments/as2b_choice/as2b.py" and (ROOT / tools["base"]).exists()
    assert tools["contract_tests"] == ["tests/integration/test_as1_contract.py", "tests/integration/test_as2b_contract.py"]
    assert all((ROOT / f).exists() for f in tools["contract_tests"])
    assert tools["previous_experiment"] == "experiments/0037_as1_plasticity_contribution" \
        and (ROOT / tools["previous_experiment"]).is_dir()
    assert (ROOT / tools["contract"]).exists() and (ROOT / tools["criteria"]).exists()
    assert tools["gate_body"].endswith("build(seed, schedule=..., delay=2, rule_c=c, respond=True)")
    for name in ("build", "clone", "sigma", "audit", "advance_to"):
        assert callable(getattr(A, name)), name
    assert callable(A.AS2bSystem.transplant) and callable(A.AS2bSystem.declare)
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
    assert parsed.plasticity.w_max == brain["w_max"] == 0.01
    plastic = [p for p in parsed.projections if p.plastic]
    assert brain["plastic_connections"] == "six_s_to_s" and len(plastic) == 6
    assert {p.weight for p in plastic} == {brain["initial_weight_w0"]} == {0.005} and brain["initial_weight_w0"] * 2 == brain["w_max"]
    assert "as2b-roles-{seed}" in brain["roles"] and 'f"as2b-roles-{seed}"' in (ROOT / tools["base"]).read_text(encoding="utf-8")
    assert protocol["world"]["closed_loop"] is True
    # 区間（README §2.1）：関門の宣言から作った Plan と、protocol の値
    tl = protocol["timeline"]
    assert tl["pulse_interval_seconds"] == A.PULSE_INTERVAL_SECONDS == 1.0
    assert {k: tl[k] for k in TIMELINE} == TIMELINE
    plan = M.formal_plan(protocol)
    assert plan == M.Plan(41, 41, 50, 2, 19, 2, 25) and (plan.p_e, plan.end) == (1065, 2072)
    windows = plan.schedule().windows
    assert windows[24] == (25, 1027, 1045) and windows[25] == (26, 1068, 1086) and windows[-1] == (50, 2052, 2070)
    assert windows[24][2] + plan.delay < plan.p_e < plan.schedule().cues[25]      # E の最後の結果 ＜ P_E ＜ U の最初の手がかり
    # 系と境界の順序（README §2.2・§2.4）
    systems = protocol["systems"]
    assert systems["per_individual"] == SYSTEMS == list(M.SYSTEMS)
    assert systems["pulses_per_individual"] == 5 * plan.end + 6 * (plan.end - plan.p_e) == 16402
    assert systems["trace_policy"] == AS1.ADVANCE == "advance"
    assert M.BODIES == ("B_A1", "B_A2") and M.FROZEN_BODIES == ("F_A1", "F_A2") and M.RERUN == "B_A1_rerun"
    assert M.TRANSPLANTS == {"G_A1_WA2": "A2", "G_A1_WA1_tr": "A1", "G_A2_WA1": "A1", "G_A2_WA2_tr": "A2"}
    assert M.FROZEN_VALUE == {"G_A1_WA1": "A1", "G_A1_WA2": "A2", "G_A1_WA1_tr": "A1",
                              "G_A2_WA2": "A2", "G_A2_WA1": "A1", "G_A2_WA2_tr": "A2"}
    assert M.BACKGROUND == {"G_A1_WA1": "B_A1", "G_A1_WA2": "B_A1", "G_A1_WA1_tr": "B_A1",
                            "G_A2_WA2": "B_A2", "G_A2_WA1": "B_A2", "G_A2_WA2_tr": "B_A2"}
    assert M.PAIRS == (("G_A1_WA1", "G_A1_WA2"), ("G_A2_WA2", "G_A2_WA1"))
    assert M.IDENTITIES == (("G_A1_WA1", "G_A1_WA1_tr"), ("G_A2_WA2", "G_A2_WA2_tr"))
    assert all(M.RULE_OF[n] == n.split("_")[1] for n in SYSTEMS)
    bs = protocol["boundary_sequence"]
    assert [k for k in bs if k.startswith("S")] == [f"S{i}" for i in range(6)]
    assert bs["no_pulse_between"] == ["S1", "S4"] and bs["compare_sigma_at"] == ["after_S3", "after_S4"]
    # 量（README §3）
    assert protocol["quantities"]["contrasts"] == CONTRASTS
    # 判定（README §4・§5）
    j = protocol["judgment"]
    for key in ("J_7", "J_W"):
        assert j[key]["min_population"] == 10 and j[key]["below_min"] == "inconclusive", key
    assert j["J_7"]["alpha"] == {"two_sided": 0.05, "per_direction": 0.025}
    assert Fraction(str(j["J_7"]["alpha"]["per_direction"])) == ALPHA_PER_DIRECTION
    assert j["J_W"]["tested_only_if"].startswith("J_7 is established") and j["J_W"]["otherwise"] == "not_tested"
    table = j["k2_of_m"]
    assert sorted(table) == list(range(K2_RANGE[0], K2_RANGE[1] + 1))
    for m, k in table.items():
        assert binom_upper_tail(m, k) <= ALPHA_PER_DIRECTION < binom_upper_tail(m, k - 1), m
    assert table == {int(m): k for m, k in ((m, AX.k2(m)) for m in table)}
    assert set(j["outcomes"]) == OUTCOMES
    assert set(j["null_hypotheses"]) == {"status", "H0_7", "H0_W", "zeros"}
    assert "no same-individual mediation" in j["combined_claim"]
    assert j["interval"].startswith("Clopper-Pearson 95% (two-sided)")
    mr = protocol["must_report"]
    assert mr["contrasts"] == ["D_W_rev", "D_F"] and mr["descriptive"] == ["Z_A1", "Z_A2", "P_A1", "P_A2"]
    # 構造上の同値・命題 S-1・操作の確認・記録（README §7〜§9）
    assert protocol["structural_equivalences"] == SE and protocol["operation_checks"] == CHECKS
    s1 = protocol["proposition_S1"]
    bound = AX.silence_bound(AX.c0_values(), AX.gate_set())
    assert abs(bound["E_S"] - s1["E_S_value"]) < 5e-6
    share = AX.silence_probability(AX.c0_values(), bound["E_S"])
    assert abs(share["per_source_structural"] - s1["per_source_share"]) < 5e-5
    assert abs(share["individual_at_least_one_structural_source"] - s1["individual_share_at_least_one"]) < 5e-5
    assert s1["use"].startswith("labels only; never used in a judgment")
    assert protocol["storage"]["raw"].startswith("seeds/<seed>/raw.json.gz (guard)")


if __name__ == "__main__":
    check(yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8")))
    print("ok")
