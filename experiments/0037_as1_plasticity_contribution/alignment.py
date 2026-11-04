"""実験 0037 の protocol.yaml と道具（measure.py・AS1 の道具 as1.py）が食い違っていないことの機械的な確認。

run.py・analyze.py が、実行・解析の前に check(protocol) を呼ぶ。食い違いがあれば AssertionError で止まる。
確定した事前登録（README・protocol.yaml v0.2、#168 merge `1c71f3c`）の値を写した固定値と、道具の定数・式の文字列を比べる。
analyze.py の対比の組（CONTRASTS）と protocol の quantities.contrasts の対応は、契約テストで確かめる（analyze.py はこのファイルを読み込むため）。
"""

import importlib.util
import inspect
from fractions import Fraction
from math import comb
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXPERIMENT_FROM_DIR = HERE.name.split("_")[0]

# これまでに走らせた seed（0036 の alignment.py の SEEN に、0036 の本番・smoke・合成〔29001〜29299〕を足したもの）。重なってはいけない
SEEN = (set(range(1, 21)) | set(range(1001, 1021)) | set(range(2001, 2021)) | set(range(3001, 3007))
        | set(range(4001, 4021)) | set(range(5001, 5007)) | set(range(6001, 6021)) | set(range(7001, 7007))
        | set(range(8001, 8021)) | set(range(8101, 8107)) | set(range(9001, 9700))
        | set(range(10001, 10021)) | set(range(10101, 10107)) | set(range(11001, 11021))
        | set(range(11101, 11107)) | set(range(12001, 12021)) | set(range(12101, 12107))
        | set(range(13001, 13201)) | set(range(14001, 14201)) | set(range(15001, 15201)) | set(range(16001, 16300))
        | set(range(17001, 17300)) | set(range(18001, 18300)) | set(range(19001, 19300)) | set(range(20001, 20300))
        | set(range(21001, 21300)) | set(range(22001, 22300)) | set(range(23001, 23300)) | set(range(24001, 24300))
        | set(range(25001, 25300)) | set(range(26001, 26300)) | set(range(27001, 27300)) | set(range(28001, 28300))
        | set(range(29001, 29300)))

SEEDS = {"seeds": (30001, 30100), "smoke_seeds": (30101, 30106), "synthetic_seeds": (30201, 30299)}
CLOSED_LOOP = {"delay_L": 2, "multiplicity": "per_reservation", "respond": True, "exogenous": [], "payload": "none"}
K_OF_M = {10: 9, 11: 9, 12: 10, 13: 10, 14: 11, 15: 12, 16: 12, 17: 13, 18: 13, 19: 14, 20: 15,
          21: 15, 22: 16, 23: 16, 24: 17, 25: 18, 26: 18, 27: 19, 28: 19, 29: 20, 30: 20, 31: 21,
          32: 22, 33: 22, 34: 23, 35: 23, 36: 24, 37: 24, 38: 25, 39: 26, 40: 26, 41: 27, 42: 27,
          43: 28, 44: 28, 45: 29, 46: 30, 47: 30, 48: 31, 49: 31, 50: 32, 51: 32, 52: 33, 53: 33,
          54: 34, 55: 35, 56: 35, 57: 36, 58: 36, 59: 37, 60: 37, 61: 38, 62: 38, 63: 39, 64: 40,
          65: 40, 66: 41, 67: 41, 68: 42, 69: 42, 70: 43, 71: 43, 72: 44, 73: 45, 74: 45, 75: 46,
          76: 46, 77: 47, 78: 47, 79: 48, 80: 48, 81: 49, 82: 49, 83: 50, 84: 51, 85: 51, 86: 52,
          87: 52, 88: 53, 89: 53, 90: 54, 91: 54, 92: 55, 93: 55, 94: 56, 95: 57, 96: 57, 97: 58,
          98: 58, 99: 59, 100: 59}
CONTRASTS = {"C_tr": ["M", "M_W0"], "C_tr_rev": ["Y_WM", "Y"], "C_rep": ["M", "Y"], "H_ext": ["Y", "K"],
             "C_PC1": ["M", "K"], "S_WM": ["M", "Y_WM"], "S_W0": ["M_W0", "Y"]}
SYSTEM_NAMES = {"M", "Y", "K", "M_W0", "Y_WM", "M_WM", "Y_on", "M_rerun"}
R2_PULSES = [300, 600, 900, 1200, 1500, 1800]
CHECKS = {f"O{i}" for i in range(1, 16)}
SE = {f"SE_{i}" for i in range(1, 9)}


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
    A = M.A
    assert protocol["experiment"] == EXPERIMENT_FROM_DIR == "0037"
    assert protocol["kind"] == "preregistered_test"
    # seed（D5）
    ranges = {}
    for key, (first, last) in SEEDS.items():
        assert protocol[key] == {"first": first, "last": last}, key
        ranges[key] = set(range(first, last + 1))
        assert not (ranges[key] & SEEN), f"{key} がこれまでに走らせた seed と重なる"
    assert not (ranges["seeds"] & ranges["smoke_seeds"]) and not (ranges["seeds"] & ranges["synthetic_seeds"]) \
        and not (ranges["smoke_seeds"] & ranges["synthetic_seeds"])
    # 道具（AS1 の道具に足した口：README §14）
    tools = protocol["tools"]
    assert tools["base"] == "experiments/as1_closed_loop/as1.py" and (ROOT / tools["base"]).exists()
    assert tools["contract_tests"] == "tests/integration/test_as1_contract.py" and (ROOT / tools["contract_tests"]).exists()
    assert tools["previous_experiment"] == "experiments/0036_as1_other_unit_firing" \
        and (ROOT / tools["previous_experiment"]).is_dir()
    assert tools["design_memo"] == "docs/as1-plasticity-contribution-design.md" and (ROOT / tools["design_memo"]).exists()
    assert tools["base_additions"].startswith("world-rule switch at a boundary (recorded; default unchanged)")
    assert tools["no_change"].startswith("transplant keeps refusing frozen connections")
    assert callable(A.AS1System.switch_world) and callable(A.replay_schedule) and callable(A.sigma_diff)
    assert "FREEZE 中の接続" in inspect.getsource(A.transplant) and "frozen_targets" in inspect.getsource(A.transplant)
    # 脳（C0 のまま）
    brain = protocol["brain"]
    assert (ROOT / brain["manifest"]).resolve() == A.C0_MANIFEST.resolve()
    manifest = A.c0_manifest_raw()
    assert brain["adaptation_tau_pulses"] == manifest["defaults"]["dynamics"]["adaptation_tau"] / A.PULSE_INTERVAL_SECONDS == 300
    assert manifest["defaults"]["dynamics"]["refractory_pulses"] == brain["refractory_pulses"] == 0
    assert brain["receptors"] == {v: k for k, v in A.RECEPTOR_OF.items()}
    assert brain["added_by_tool"]["effector"] == A.EFFECTOR_ID and brain["added_by_tool"]["intent_port"] == A.INTENT_PORT
    assert receptor_weights(manifest) == receptor_weights(A.as1_manifest_raw()) == {float(brain["receptor_weight"])} == {1.0}
    parsed = A.parse_neuroarchitecture(A.as1_manifest_raw())
    assert parsed.plasticity.w_max == brain["w_max"] == 0.01
    plastic = [p for p in parsed.projections if p.plastic]
    assert len(plastic) == 6 and {p.weight for p in plastic} == {brain["initial_weight_w0"]} == {0.005}
    assert brain["initial_weight_w0"] * 2 == brain["w_max"]
    assert protocol["timeline"]["pulse_interval_seconds"] == A.PULSE_INTERVAL_SECONDS == 1.0
    # 役・世界（README §2.3）
    assert protocol["roles"]["stream"] == "as1-roles-{seed}"
    assert 'f"as1-roles-{seed}"' in (ROOT / tools["base"]).read_text(encoding="utf-8")
    world = protocol["world"]
    assert world["closed_loop"] == CLOSED_LOOP and CLOSED_LOOP["multiplicity"] == A.PER_RESERVATION
    assert world["replay"]["respond"] is False
    assert world["switch"]["systems"] == list(M.SWITCHED) == ["Y", "Y_WM"]
    assert world["switch"]["to"] == "closed_loop" and world["switch"]["at_boundary"] == "P_E"
    # 区間（README §2.1）
    tl = protocol["timeline"]
    assert tl["P_E"] == M.P_E and tl["U_length"] == M.U_LENGTH and tl["runs_to"] == M.RUNS_TO
    assert tl["values"] == {"P_E": 1800, "U_length": 300, "runs_to": 2100}
    plan = M.formal_plan(protocol)
    assert (plan.p_e, plan.u_length, plan.p_e + plan.u_length) == (1800, 300, 2100)
    assert list(plan.checkpoints) == R2_PULSES == protocol["auxiliary"]["R2_weights"]["M_checkpoints"]["pulses"]
    # 系と境界の順序（README §2.2・§2.4）
    systems = protocol["systems"]
    assert {k for k in systems if k not in ("run_in_U", "W_M", "W_0", "trace_policy")} == SYSTEM_NAMES
    assert systems["run_in_U"] == list(M.U_SYSTEMS) and systems["trace_policy"] == A.ADVANCE == "advance"
    assert set(M.U_SYSTEMS) | set(M.E_ONLY) == SYSTEM_NAMES
    assert M.TRANSPLANTS == {"M_W0": ("M", "W_0"), "M_WM": ("M", "W_M"), "Y_WM": ("Y", "W_M")}
    assert M.FROZEN_VALUE == {"M": "W_M", "M_W0": "W_0", "M_WM": "W_M", "Y": "W_0", "Y_WM": "W_M", "K": "W_0"}
    assert M.E_FROZEN == ("Y", "K") and M.HORIZONTAL == (("M", "M_W0"), ("Y", "Y_WM"))
    bs = protocol["boundary_sequence"]
    assert [k for k in bs if k.startswith("S")] == [f"S{i}" for i in range(7)]
    assert M.S0_ORDER == ("M", "Y", "Y_on", "K", "M_rerun") and set(M.S0_ORDER) == SYSTEM_NAMES - {"M_W0", "M_WM", "Y_WM"}
    assert bs["no_pulse_between"] == ["S1", "S5"] and bs["compare_sigma_at"] == ["after_S3_before_S4", "after_S5"]
    # 量（README §3）
    q = protocol["quantities"]
    assert q["contrasts"] == CONTRASTS
    # 判定（README §4・§5）
    per = protocol["judgment"]["per_individual"]
    assert per["m_E"] == 1 and per["unobservable"] == "none"
    assert set(per["ineligible_kinds"]) == {"a_no_source_firing_in_E", "b_source_fired_only_at_P_E"}
    assert per["P_i"] == "I_U(M) != I_U(M_W0)"
    j = protocol["judgment"]["J_C"]
    assert j["min_population"] == 10 and j["alpha"] == 0.05 and j["direction"] == "one_sided" and j["below_min"] == "inconclusive"
    assert j["k_of_m"] == K_OF_M and sorted(K_OF_M) == list(range(10, 101))
    for m, k in K_OF_M.items():
        assert binom_upper_tail(m, k) <= Fraction(1, 20) < binom_upper_tail(m, k - 1), m
    assert set(protocol["judgment"]["outcomes"]) == {"invalid", "inconclusive", "established", "not_established"}
    assert protocol["judgment"]["low_rate_claim"] == "not_tested"
    iv = protocol["judgment"]["interval"]
    assert (iv["method"], iv["level"], iv["sides"]) == ("clopper_pearson", 0.95, "two")
    assert iv["computed_when"] == "m >= 1, regardless of the J_C outcome"
    dc = protocol["descriptive_controls"]
    assert dc["required"] == ["C_tr_rev", "C_rep", "H_ext"] and dc["also"] == ["C_PC1", "S_WM", "S_W0"]
    # 構造上の同値・操作の確認・記録（README §7〜§9）
    assert set(protocol["structural_equivalences"]) == SE
    oc = protocol["operation_checks"]
    assert set(oc) == CHECKS
    assert set(oc["O7"]) == {"a_after_S3", "b_after_S5"} and set(oc["O15"]) == {"source", "a", "b", "c"}
    assert protocol["records"]["save"].startswith("guard layout (seeds/<seed>/raw.json.gz)")


if __name__ == "__main__":
    check(yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8")))
    print("ok")
