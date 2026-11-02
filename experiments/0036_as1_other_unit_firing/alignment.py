"""実験 0036 の protocol.yaml と道具（measure.py・AS1 の道具 as1.py）が食い違っていないことの機械的な確認。

run.py・analyze.py が、実行・解析の前に check(protocol) を呼ぶ。食い違いがあれば AssertionError で止まる。
確定した事前登録（README・protocol.yaml v0.2、#162 merge `dd2973f`）の値を写した固定値と、道具の定数・式の文字列を比べる。
analyze.py の対比の組（PAIRS）と protocol の quantities の対応は、契約テストで確かめる（analyze.py はこのファイルを読み込むため）。
"""

import importlib.util
import inspect
import math
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXPERIMENT_FROM_DIR = HERE.name.split("_")[0]

# これまでに走らせた seed（0035 の alignment.py の SEEN に、0035 の本番・smoke・合成〔28001〜28299〕を足したもの）。重なってはいけない
SEEN = (set(range(1, 21)) | set(range(1001, 1021)) | set(range(2001, 2021)) | set(range(3001, 3007))
        | set(range(4001, 4021)) | set(range(5001, 5007)) | set(range(6001, 6021)) | set(range(7001, 7007))
        | set(range(8001, 8021)) | set(range(8101, 8107)) | set(range(9001, 9700))
        | set(range(10001, 10021)) | set(range(10101, 10107)) | set(range(11001, 11021))
        | set(range(11101, 11107)) | set(range(12001, 12021)) | set(range(12101, 12107))
        | set(range(13001, 13201)) | set(range(14001, 14201)) | set(range(15001, 15201)) | set(range(16001, 16300))
        | set(range(17001, 17300)) | set(range(18001, 18300)) | set(range(19001, 19300)) | set(range(20001, 20300))
        | set(range(21001, 21300)) | set(range(22001, 22300)) | set(range(23001, 23300)) | set(range(24001, 24300))
        | set(range(25001, 25300)) | set(range(26001, 26300)) | set(range(27001, 27300)) | set(range(28001, 28300)))

SEEDS = {"seeds": (29001, 29080), "smoke_seeds": (29101, 29106), "synthetic_seeds": (29201, 29299)}
WORLD = {"delay_L": 2, "multiplicity": "per_reservation", "respond": True, "exogenous": [], "payload": "none"}
K_OF_M = {10: 9, 11: 9, 12: 10, 13: 10, 14: 11, 15: 12, 16: 12, 17: 13, 18: 13, 19: 14, 20: 15,
          21: 15, 22: 16, 23: 16, 24: 17, 25: 18, 26: 18, 27: 19, 28: 19, 29: 20, 30: 20, 31: 21,
          32: 22, 33: 22, 34: 23, 35: 23, 36: 24, 37: 24, 38: 25, 39: 26, 40: 26, 41: 27, 42: 27,
          43: 28, 44: 28, 45: 29, 46: 30, 47: 30, 48: 31, 49: 31, 50: 32, 51: 32, 52: 33, 53: 33,
          54: 34, 55: 35, 56: 35, 57: 36, 58: 36, 59: 37, 60: 37, 61: 38, 62: 38, 63: 39, 64: 40,
          65: 40, 66: 41, 67: 41, 68: 42, 69: 42, 70: 43, 71: 43, 72: 44, 73: 45, 74: 45, 75: 46,
          76: 46, 77: 47, 78: 47, 79: 48, 80: 48}
SIGN = {"both_known": "sign(tau_Y - tau_X)", "X_known_Y_censored": "'+' if c_Y >= tau_X else '?'",
        "Y_known_X_censored": "'-' if c_X >= tau_Y else '?'", "both_censored": "?", "value": "only when both are known"}
CENSOR = {"F": "t + H", "N": "t + H", "blk": "t + H", "none": "t + H", "cf": "t + H",
          "F_fixN": "stop_N", "N_fixF": "stop_F", "F_fixF": "stop_F"}
QUANTITIES = {"d_e": ["F", "N"], "d_fix": ["F_fixN", "N"], "d_chg": ["F", "F_fixN"], "d_fix_rev": ["F", "N_fixF"],
              "d_chg_rev": ["N_fixF", "N"], "d_blk": ["F_blk", "N_blk"], "d_none": ["F_none", "N_none"],
              "d_cf": ["F_cf", "N_cf"]}
BOUNDARY = {"n=0,k=0": False, "n=10,k=0": False, "n=10,k=1": True, "n=11,k=1": False}
TARGETS = ["{other}.main->{source}", "{other}.main->{receiver}"]
R10_PULSES = [300, 600, 900, 1200, 1500, 1800, 2099]
BODY_LOG_KEEP = ["RUN", "SENSORY", "ACTIVITY", "DELTA", "EFFECT"]
SIGMA_CONTENTS = ["units", "connections", "drives", "world", "runtime"]
CHECKS = {f"O{i}" for i in range(1, 13)}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def binom_upper_tail(m: int, k: int) -> float:
    return sum(math.comb(m, j) for j in range(k, m + 1)) / 2 ** m


def receptor_weights(manifest: dict) -> set[float]:
    return {float(p["weight"]) for p in manifest["projections"] if str(p["from"]).startswith("receptor.")}


def check(protocol: dict) -> None:
    M = _load(f"measure_{EXPERIMENT_FROM_DIR}_alignment", HERE / "measure.py")
    A = M.A
    assert protocol["experiment"] == EXPERIMENT_FROM_DIR == "0036"
    assert protocol["kind"] == "preregistered_test"
    # seed（D5）
    ranges = {}
    for key, (first, last) in SEEDS.items():
        assert protocol[key] == {"first": first, "last": last}, key
        ranges[key] = set(range(first, last + 1))
        assert not (ranges[key] & SEEN), f"{key} がこれまでに走らせた seed と重なる"
    assert not (ranges["seeds"] & ranges["smoke_seeds"]) and not (ranges["seeds"] & ranges["synthetic_seeds"]) \
        and not (ranges["smoke_seeds"] & ranges["synthetic_seeds"])
    # 道具（AS1 の道具の口：README §2.3）
    tools = protocol["tools"]
    assert tools["base"] == "experiments/as1_closed_loop/as1.py" and (ROOT / tools["base"]).exists()
    assert tools["contract_tests"] == "tests/integration/test_as1_contract.py" and (ROOT / tools["contract_tests"]).exists()
    assert tools["previous_experiment"] == "experiments/0035_as1_state_dependent_feedback" \
        and (ROOT / tools["previous_experiment"]).is_dir()
    assert tools["base_change_policy"].startswith("only an opt-in hook that does nothing by default")
    params = inspect.signature(A.build).parameters
    assert "unit_wrappers" in params and params["unit_wrappers"].default is None
    assert A.WRAPPABLE_ROLES == ("receiver", "other") and set(M.UNIT_WRAPPERS) == {"other"}
    # 脳（C0 のまま）
    brain = protocol["brain"]
    assert (ROOT / brain["manifest"]).resolve() == A.C0_MANIFEST.resolve()
    manifest = A.c0_manifest_raw()
    assert brain["adaptation_tau_pulses"] == manifest["defaults"]["dynamics"]["adaptation_tau"] / A.PULSE_INTERVAL_SECONDS == 300
    assert manifest["defaults"]["dynamics"]["refractory_pulses"] == brain["refractory_pulses"] == 0
    assert manifest["defaults"]["dynamics"]["kind"] == "simple_activity"
    assert brain["receptors"] == {v: k for k, v in A.RECEPTOR_OF.items()}
    assert brain["added_by_tool"]["effector"] == A.EFFECTOR_ID and brain["added_by_tool"]["intent_port"] == A.INTENT_PORT
    assert receptor_weights(manifest) == receptor_weights(A.as1_manifest_raw()) == {float(brain["receptor_weight"])} == {1.0}
    assert protocol["timeline"]["pulse_interval_seconds"] == A.PULSE_INTERVAL_SECONDS == 1.0
    # 役（K2）・世界
    assert protocol["roles"]["stream"] == "as1-roles-{seed}"
    assert 'f"as1-roles-{seed}"' in (ROOT / tools["base"]).read_text(encoding="utf-8")
    assert protocol["world"] == WORLD and WORLD["multiplicity"] == A.PER_RESERVATION
    # 区間と式
    tl = protocol["timeline"]
    assert tl["event_window"]["first"] == M.WINDOW_FIRST and tl["event_window"]["last"] == M.WINDOW_LAST
    assert tl["branch_pulse"] == M.BRANCH_PULSE and tl["horizon_H"] == M.HORIZON and tl["body_runs_to"] == M.BODY_RUNS_TO
    plan = M.formal_plan(protocol)
    assert (plan.window_first, plan.window_last, plan.horizon, plan.body_runs_to) == (301, 1800, 300, 2099)
    assert (plan.clone_check_at, plan.clone_check_until) == (300, 600)
    assert plan.body_runs_to in plan.checkpoints and list(plan.checkpoints) == R10_PULSES
    ev = protocol["events"]
    assert ev["sampling"] == "none"
    assert ev["pre_branch_state"]["record"] == "as1.sigma(body) at the end of pulse t"
    assert ev["pre_branch_state"]["contents"] == SIGMA_CONTENTS
    # 系（README §2.2）
    systems = protocol["systems"]
    names = {k for k in systems if k not in ("first_intent", "reference_not_extended")}
    assert names == {"F"} | set(M.SYSTEMS)
    assert systems["reference_not_extended"] is True
    for name in M.SYSTEMS:
        spec = systems[name]
        assert (spec["e"] == "cancelled") == (name in M.E_CANCELLED), name
        assert ("masked" in spec["other"]) == (name in M.BLOCKED), name
        assert ("FREEZE six" in spec["plasticity"]) == (name in M.FROZEN), name
        assert ("forced" in spec["other"]) == (name in M.FORCED), name
    assert "N's other firings" in systems["F_fixN"]["other"] and "F's other firings" in systems["N_fixF"]["other"] \
        and "F's own other firings" in systems["F_fixF"]["other"]
    assert M.FORCED == {"F_fixN": "N", "N_fixF": "F_prime", "F_fixF": "F_prime", "F_none": None, "N_none": None,
                        "F_none_cf": None, "N_none_cf": None}
    assert all("no firing" in systems[n]["other"] for n, ref in M.FORCED.items() if ref is None)
    assert systems["F_prime"]["stop"] == "stop_F" and systems["N_prime"]["stop"] == "same as N"
    # 固定と遮断（README §2.3・§2.4）
    ff = protocol["forced_firing"]
    assert ff["target"] == "other" and ff["core_change"] == "none" and ff["delivered_drive_copy_option_b"] == "not_included"
    assert ff["state"].startswith("Core SimpleActivityDynamics.advance computes the natural state")
    tb = protocol["transmission_block"]
    assert tb["targets"] == TARGETS and tb["declared_at_boundary"] == "t" and tb["drives_in_sigma_t"] == "delivered"
    assert tb["same_as_suppression"] is False and tb["mechanism"].startswith("AS1 InterventionConnections FB1")
    roles = A.assign_roles(29201)
    assert list(M.block_targets(roles)) == [x.format(**roles.as_dict()) for x in TARGETS]
    assert [M._key_text(k) for k in M.block_keys(roles)] == list(M.block_targets(roles))
    # 符号・量（README §3）
    sg = protocol["sign"]
    assert {k: sg[k] for k in SIGN} == SIGN and sg["censor_pulse"] == CENSOR
    q = protocol["quantities"]
    assert {k: q[k] for k in QUANTITIES} == QUANTITIES
    # 判定（README §4・§5）
    per = protocol["judgment"]["per_individual"]
    assert per["c"] == 0.1 and per["direction"] == "not rare (r_i >= c)"
    assert per["decision_population"] == "applicable and at least 10 events in event_window (body only; 10 = 1 / c)"
    assert per["evaluable_events"] == "s_e != ? and s_fix != ?"
    assert per["event_P_i"] == "n_i >= 1 and 10 * k_i >= n_i"
    assert per["zero_evaluable"] == "kept in the population; P_i is false"
    assert per["boundary_tests"] == BOUNDARY
    j = protocol["judgment"]["J_P"]
    assert j["min_population"] == 10 and j["alpha"] == 0.05 and j["direction"] == "one_sided" and j["below_min"] == "inconclusive"
    assert j["k_of_m"] == K_OF_M
    for m, k in K_OF_M.items():
        assert binom_upper_tail(m, k) <= 0.05 < binom_upper_tail(m, k - 1), m
    rc = protocol["reported_control"]["two_by_two"]
    assert rc["per_individual"]["P_blk_i"] == "n_blk_i >= 1 and 10 * k_blk_i >= n_blk_i"
    assert rc["boundary_tests"] == BOUNDARY
    # 補助・記録
    aux = protocol["auxiliary"]
    assert aux["R10_weights"]["pulses"] == R10_PULSES
    assert aux["R6_interval"] == {"method": "clopper_pearson", "level": 0.95, "of": "#{P_i} / m (same denominator as J_P)",
                                  "below_min": "not_computed"}
    assert list(aux["R5_sign_patterns"]["categories"]) == ["no_change", "only_B_differs", "only_A_differs",
                                                           "both_differ", "sign_return"]
    assert protocol["records"]["body_log_keep"] == BODY_LOG_KEEP and M.body_log_keep(protocol) == A.AS1Log.DEFAULT_KEEP
    assert M.N_PRIME_LOG_KEEP == frozenset({A.RuntimeEventType.SENSORY})
    oc = protocol["operation_checks"]
    assert set(oc) == CHECKS
    assert set(oc["O4"]) == {"a_branch_pending", "b_sensory_until_stop", "c_new_reservations", "contract_tests"}
    assert set(oc["O7"]) == {"a", "b", "c"} and oc["O7"]["c"].startswith("one per new intervention kind (F_fixN, F_blk, F_cf)")
    assert M.PLAIN == ("F_fixN", "F_blk", "F_cf")


if __name__ == "__main__":
    check(yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8")))
    print("ok")
