"""実験 0035 の protocol.yaml と道具（measure.py・analyze.py・AS1 の道具 as1.py）が食い違っていないことの機械的な確認。

run.py・analyze.py が、実行・解析の前に check(protocol) を呼ぶ。食い違いがあれば AssertionError で止まる。
確定した事前登録（README・protocol.yaml v0.3、#156 merge `b71d6fc`）の値を写した固定値と、道具の定数・式の文字列を比べる。
"""

import importlib.util
import math
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXPERIMENT_FROM_DIR = HERE.name.split("_")[0]

# これまでに走らせた seed（0034 の alignment.py の SEEN に、0034 の本番・smoke・合成〔27001〜27299〕を足したもの）。重なってはいけない
SEEN = (set(range(1, 21)) | set(range(1001, 1021)) | set(range(2001, 2021)) | set(range(3001, 3007))
        | set(range(4001, 4021)) | set(range(5001, 5007)) | set(range(6001, 6021)) | set(range(7001, 7007))
        | set(range(8001, 8021)) | set(range(8101, 8107)) | set(range(9001, 9700))
        | set(range(10001, 10021)) | set(range(10101, 10107)) | set(range(11001, 11021))
        | set(range(11101, 11107)) | set(range(12001, 12021)) | set(range(12101, 12107))
        | set(range(13001, 13201)) | set(range(14001, 14201)) | set(range(15001, 15201)) | set(range(16001, 16300))
        | set(range(17001, 17300)) | set(range(18001, 18300)) | set(range(19001, 19300)) | set(range(20001, 20300))
        | set(range(21001, 21300)) | set(range(22001, 22300)) | set(range(23001, 23300)) | set(range(24001, 24300))
        | set(range(25001, 25300)) | set(range(26001, 26300)) | set(range(27001, 27300)))

SEEDS = {"seeds": (28001, 28060), "smoke_seeds": (28101, 28106), "synthetic_seeds": (28201, 28299)}
WORLD = {"delay_L": 2, "multiplicity": "per_reservation", "respond": True, "exogenous": [], "payload": "none"}
K_OF_M = {10: 9, 11: 9, 12: 10, 13: 10, 14: 11, 15: 12, 16: 12, 17: 13, 18: 13, 19: 14, 20: 15,
          21: 15, 22: 16, 23: 16, 24: 17, 25: 18, 26: 18, 27: 19, 28: 19, 29: 20, 30: 20, 31: 21,
          32: 22, 33: 22, 34: 23, 35: 23, 36: 24, 37: 24, 38: 25, 39: 26, 40: 26, 41: 27, 42: 27,
          43: 28, 44: 28, 45: 29, 46: 30, 47: 30, 48: 31, 49: 31, 50: 32, 51: 32, 52: 33, 53: 33,
          54: 34, 55: 35, 56: 35, 57: 36, 58: 36, 59: 37, 60: 37}
SIGN = {"both_found": "sign(tau_N - tau_F)", "only_F_found": "+", "only_N_found": "-", "none_found": "?"}
PREDICTION_SIGN = {"both_found": "sign(tau_hat_N - tau_hat_F)", "only_F_found": "+", "only_N_found": "-", "none_found": "0"}
PREDICTION = {
    "name": "two_path_approximation",
    "units_kept": ["source", "receiver"],
    "connection_kept": "receiver.main->source",
    "dynamics": "Core SimpleActivityDynamics.advance with delta_time = 1 (no runtime, no Application)",
    "per_world": {"F": "receiver gets receptor_weight at pulse t + 2", "N": "no consequence stimulus"},
    "inputs_per_pulse": {
        "receiver": "drives to receiver in Sigma_t at t + 1; plus receptor_weight at t + 2 in F",
        "source": "drives to source in Sigma_t at t + 1; plus w(receiver->source) at p if the receiver fired at p - 1 in that world"},
    "receiver_firings": "all receiver firings in (t, tau_hat] are followed, not only the first (audit 032)",
    "stop": "first source firing tau_hat in (t, t + H], else none",
    "ignored": ["other_unit_after_t", "plasticity_after_t"],
}
R1_EVENT = ["t", "e_pulse", "tau_F", "tau_N", "d_e", "s_e", "tau_hat_F", "tau_hat_N", "s_hat"]
R2_INDIVIDUAL = ["roles", "birth_units", "events_in_window", "counts", "V_i", "acc_rule", "acc_plus", "acc_zero", "acc_minus",
                 "acc_const", "Q_i", "confusion_3x3"]
R3_RULES = ["direct_only", "past_rhythm", "negative_control"]
R7_PULSES = [300, 600, 900, 1200, 1500, 1800, 2099]
BODY_LOG_KEEP = ["RUN", "SENSORY", "ACTIVITY", "DELTA", "EFFECT"]
PER_EVENT_RECORDS = ["sigma_t", "n_pending", "n_sensory", "n_firings", "tau_N"]
SIGMA_CONTENTS = ["units", "connections", "drives", "world", "runtime"]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def binom_upper_tail(m: int, k: int) -> float:
    return sum(math.comb(m, j) for j in range(k, m + 1)) / 2 ** m


def receptor_weights(manifest: dict) -> set[float]:
    """設計図の Receptor → Unit の投射の重み（二経路近似の結果の刺激の重み）。"""
    return {float(p["weight"]) for p in manifest["projections"] if str(p["from"]).startswith("receptor.")}


def check(protocol: dict) -> None:
    M = _load(f"measure_{EXPERIMENT_FROM_DIR}_alignment", HERE / "measure.py")
    A = M.A
    assert protocol["experiment"] == EXPERIMENT_FROM_DIR == "0035"
    assert protocol["kind"] == "preregistered_test"
    # seed（D5）
    ranges = {}
    for key, (first, last) in SEEDS.items():
        assert protocol[key] == {"first": first, "last": last}, key
        ranges[key] = set(range(first, last + 1))
        assert not (ranges[key] & SEEN), f"{key} がこれまでに走らせた seed と重なる"
    assert not (ranges["seeds"] & ranges["smoke_seeds"]) and not (ranges["seeds"] & ranges["synthetic_seeds"]) \
        and not (ranges["smoke_seeds"] & ranges["synthetic_seeds"])
    # 道具
    tools = protocol["tools"]
    assert tools["base"] == "experiments/as1_closed_loop/as1.py" and (ROOT / tools["base"]).exists()
    assert tools["contract_tests"] == "tests/integration/test_as1_contract.py" and (ROOT / tools["contract_tests"]).exists()
    assert tools["previous_experiment"] == "experiments/0034_as1_feedback_next_intent" and (ROOT / tools["previous_experiment"]).is_dir()
    # 脳（C0 のまま）と、道具が足すもの
    brain = protocol["brain"]
    assert (ROOT / brain["manifest"]).resolve() == A.C0_MANIFEST.resolve()
    manifest = A.c0_manifest_raw()
    assert brain["adaptation_tau_pulses"] == manifest["defaults"]["dynamics"]["adaptation_tau"] / A.PULSE_INTERVAL_SECONDS == 300
    assert manifest["defaults"]["dynamics"]["refractory_pulses"] == brain["refractory_pulses"] == 0
    assert manifest["defaults"]["dynamics"]["kind"] == "simple_activity"                 # 二経路近似が使う Unit の式
    assert brain["receptors"] == {v: k for k, v in A.RECEPTOR_OF.items()}
    assert brain["added_by_tool"]["effector"] == A.EFFECTOR_ID and brain["added_by_tool"]["intent_port"] == A.INTENT_PORT
    assert receptor_weights(manifest) == receptor_weights(A.as1_manifest_raw()) == {float(brain["receptor_weight"])} == {1.0}
    assert protocol["timeline"]["pulse_interval_seconds"] == A.PULSE_INTERVAL_SECONDS == 1.0
    # 役の割り当て（K2）
    assert protocol["roles"]["stream"] == "as1-roles-{seed}"
    assert 'f"as1-roles-{seed}"' in (ROOT / tools["base"]).read_text(encoding="utf-8")
    # 世界（README §1.1）
    assert protocol["world"] == WORLD
    assert WORLD["multiplicity"] == A.PER_RESERVATION
    # 区間と式
    tl = protocol["timeline"]
    assert tl["event_window"]["first"] == M.WINDOW_FIRST and tl["event_window"]["last"] == M.WINDOW_LAST
    assert tl["branch_pulse"] == M.BRANCH_PULSE and tl["horizon_H"] == M.HORIZON and tl["body_runs_to"] == M.BODY_RUNS_TO
    plan = M.formal_plan(protocol)
    assert (plan.window_first, plan.window_last, plan.horizon, plan.body_runs_to) == (301, 1800, 300, 2099)
    assert (plan.clone_check_at, plan.clone_check_until) == (300, 600)              # O3
    assert list(plan.checkpoints) == protocol["auxiliary"]["R7_weights"]["pulses"] == R7_PULSES
    # 出来事・符号・分岐の前の状態
    ev = protocol["events"]
    assert ev["sampling"] == "none" and ev["sign"] == SIGN
    assert ev["pre_branch_state"]["record"] == "as1.sigma(body) at the end of pulse t"
    assert ev["pre_branch_state"]["contents"] == SIGMA_CONTENTS
    # 予測（README §3。合わせ込む値を持たない）
    pr = protocol["prediction"]
    assert {k: pr[k] for k in PREDICTION} == PREDICTION
    assert pr["sign"] == PREDICTION_SIGN
    # 判定（README §4・§5）
    j = protocol["judgment"]["J_S"]
    assert j["min_applicable"] == 10 and j["alpha"] == 0.05 and j["direction"] == "one_sided"
    assert j["k_of_m"] == K_OF_M
    for m, k in K_OF_M.items():
        assert binom_upper_tail(m, k) <= 0.05 < binom_upper_tail(m, k - 1), m
    per = protocol["judgment"]["per_individual"]
    assert per["applicable"].startswith("body F has at least one consequence reservation e")
    assert per["evaluable_events"] == "s_e != ?"
    assert per["event_Q_i"] == "acc_rule > acc_const (for individuals with V_i)"
    assert per["decision_population_V_i"].startswith("applicable and the evaluable s_e take at least two distinct values")
    assert per["zero_evaluable"].startswith("acc_rule, acc_const and per-constant accuracies are null (not 0)")
    # 補助（判定しない）
    aux = protocol["auxiliary"]
    assert aux["R1_event"] == R1_EVENT and aux["R2_individual"] == R2_INDIVIDUAL
    assert list(aux["R3_alternative_rules"]) == R3_RULES
    assert aux["R6_interval"] == {"method": "clopper_pearson", "level": 0.95, "of": "#{V_i and Q_i} / m (same denominator as J_S)"}
    assert aux["window_end_u_e"] == "min(tau_F, tau_N, t + H) with a censored side taken as t + H"
    # 記録
    assert protocol["records"]["body_log_keep"] == BODY_LOG_KEEP
    assert M.body_log_keep(protocol) == A.AS1Log.DEFAULT_KEEP                       # 道具の既定と同じ
    assert protocol["records"]["per_event"] == PER_EVENT_RECORDS
    # N′（O7 の (b)）：来歴のログは感覚の出来事だけで、発火の記録を持たない（0034 で系 N について保存したのも、感覚の出来事・τ・
    # 止まった Pulse だけ）。τ は源の発火の数で検知するので、ログの中身に依らない
    assert M.N_PRIME_LOG_KEEP == frozenset({A.RuntimeEventType.SENSORY})
    # 操作の確認
    oc = protocol["operation_checks"]
    assert set(oc) == {"O1", "O2", "O3", "O4", "O5", "O6", "O7"}
    assert set(oc["O7"]) == {"body", "N"}


if __name__ == "__main__":
    check(yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8")))
    print("ok")
