"""実験 0034 の protocol.yaml と道具（measure.py・analyze.py・②の as1.py）が食い違っていないことの機械的な確認。

run.py・analyze.py が、実行・解析の前に check(protocol) を呼ぶ。食い違いがあれば AssertionError で止まる。
確定した事前登録（README・protocol.yaml、#149 merge `8b7ff8e`）の値を写した固定値と、道具の定数・式の文字列を比べる。
"""

import importlib.util
import math
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXPERIMENT_FROM_DIR = HERE.name.split("_")[0]

# これまでに走らせた seed（0033 の alignment.py の SEEN に、0033 の本番・smoke・合成〔26001〜26299〕を足したもの）。重なってはいけない。
# 9001〜9699 には、②の道具の確かめ（#148）で走らせた 9001〜9012 も入っている
SEEN = (set(range(1, 21)) | set(range(1001, 1021)) | set(range(2001, 2021)) | set(range(3001, 3007))
        | set(range(4001, 4021)) | set(range(5001, 5007)) | set(range(6001, 6021)) | set(range(7001, 7007))
        | set(range(8001, 8021)) | set(range(8101, 8107)) | set(range(9001, 9700))
        | set(range(10001, 10021)) | set(range(10101, 10107)) | set(range(11001, 11021))
        | set(range(11101, 11107)) | set(range(12001, 12021)) | set(range(12101, 12107))
        | set(range(13001, 13201)) | set(range(14001, 14201)) | set(range(15001, 15201)) | set(range(16001, 16300))
        | set(range(17001, 17300)) | set(range(18001, 18300)) | set(range(19001, 19300)) | set(range(20001, 20300))
        | set(range(21001, 21300)) | set(range(22001, 22300)) | set(range(23001, 23300)) | set(range(24001, 24300))
        | set(range(25001, 25300)) | set(range(26001, 26300)))

SEEDS = {"seeds": (27001, 27020), "smoke_seeds": (27101, 27106), "synthetic_seeds": (27201, 27299)}
WORLD = {"delay_L": 2, "multiplicity": "per_reservation", "respond": True, "exogenous": [], "payload": "none"}
K_OF_M = {10: 9, 11: 9, 12: 10, 13: 10, 14: 11, 15: 12, 16: 12, 17: 13, 18: 13, 19: 14, 20: 15}
SIGN = {"both_found": "sign(tau_N - tau_F)", "only_F_found": "+", "only_N_found": "-", "none_found": "?"}
R5_PULSES = [300, 600, 900, 1200, 1500, 1800, 2099]
BODY_LOG_KEEP = ["RUN", "SENSORY", "ACTIVITY", "DELTA", "EFFECT"]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def binom_upper_tail(m: int, k: int) -> float:
    return sum(math.comb(m, j) for j in range(k, m + 1)) / 2 ** m


def check(protocol: dict) -> None:
    M = _load(f"measure_{EXPERIMENT_FROM_DIR}_alignment", HERE / "measure.py")
    A = M.A
    assert protocol["experiment"] == EXPERIMENT_FROM_DIR == "0034"
    assert protocol["kind"] == "preregistered_test"
    # seed（D5）
    ranges = {}
    for key, (first, last) in SEEDS.items():
        assert protocol[key] == {"first": first, "last": last}, key
        ranges[key] = set(range(first, last + 1))
        assert not (ranges[key] & SEEN), f"{key} がこれまでに走らせた seed と重なる"
    assert not (ranges["seeds"] & ranges["smoke_seeds"]) and not (ranges["seeds"] & ranges["synthetic_seeds"]) \
        and not (ranges["smoke_seeds"] & ranges["synthetic_seeds"])
    seen = protocol["seen_out_of_range_seeds"]
    assert set(range(seen["first"], seen["last"] + 1)) <= SEEN
    # 道具
    assert protocol["tools"]["base"] == "experiments/as1_closed_loop/as1.py" and (ROOT / protocol["tools"]["base"]).exists()
    assert (ROOT / protocol["tools"]["contract_tests"]).exists()
    # 脳（C0 のまま）と、道具が足すもの
    brain = protocol["brain"]
    assert (ROOT / brain["manifest"]).resolve() == A.C0_MANIFEST.resolve()
    manifest = A.c0_manifest_raw()
    assert brain["adaptation_tau_pulses"] == manifest["defaults"]["dynamics"]["adaptation_tau"] / A.PULSE_INTERVAL_SECONDS == 300
    assert manifest["defaults"]["dynamics"]["refractory_pulses"] == brain["refractory_pulses"] == 0
    assert brain["receptors"] == {v: k for k, v in A.RECEPTOR_OF.items()}
    assert brain["added_by_tool"]["effector"] == A.EFFECTOR_ID and brain["added_by_tool"]["intent_port"] == A.INTENT_PORT
    assert protocol["timeline"]["pulse_interval_seconds"] == A.PULSE_INTERVAL_SECONDS == 1.0
    # 役の割り当て（K2）
    assert protocol["roles"]["stream"] == "as1-roles-{seed}"
    assert 'f"as1-roles-{seed}"' in (ROOT / protocol["tools"]["base"]).read_text(encoding="utf-8")
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
    assert list(plan.checkpoints) == protocol["auxiliary"]["R5_weights"]["pulses"] == R5_PULSES
    # 出来事・符号
    assert protocol["events"]["sampling"] == "none" and protocol["events"]["sign"] == SIGN
    # 判定（README §4・§5）
    j = protocol["judgment"]["J_A"]
    assert j["min_applicable"] == 10 and j["alpha"] == 0.05 and j["direction"] == "one_sided_plus"
    assert j["k_of_m"] == K_OF_M
    for m, k in K_OF_M.items():
        assert binom_upper_tail(m, k) <= 0.05 < binom_upper_tail(m, k - 1), m
    per = protocol["judgment"]["per_individual"]
    assert per["event_P_i"] == "n_plus > n_minus" and per["counts"] == ["n_plus", "n_minus", "n_zero", "n_unknown"]
    assert per["applicable"].startswith("body F has at least one consequence reservation e")
    # 補助（判定しない）
    aux = protocol["auxiliary"]
    assert aux["R2_CF2"]["intervention"] == {"kind": "FREEZE", "targets": "all_six_plastic", "trace_policy": "advance",
                                             "declared_at_boundary": "t", "declared_once": True, "cleared": "never"}
    assert aux["R3_FB1"]["intervention"] == {"kind": "FB1", "targets": ["receiver.main->source"], "declared_at_boundary": "t",
                                             "declared_once": True, "cleared": "never"}
    assert aux["R6_interval"] == {"method": "clopper_pearson", "level": 0.95, "of": "fraction of applicable individuals with P_i"}
    # 記録
    assert protocol["records"]["body_log_keep"] == BODY_LOG_KEEP
    assert M.body_log_keep(protocol) == A.AS1Log.DEFAULT_KEEP                       # 道具の既定と同じ
    assert set(protocol["operation_checks"]) == {"O1", "O2", "O3", "O4", "O5", "O6"}


if __name__ == "__main__":
    check(yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8")))
    print("ok")
