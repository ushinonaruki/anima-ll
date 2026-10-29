"""実験 0035 の道具の契約テスト（確定した事前登録 v0.3 の README・protocol.yaml、#156 merge `b71d6fc`）。

本番の seed（28001〜28060）・smoke の seed（28101〜28106）は使わない（実行もしない）。0034 の seed・raw（27001〜27299）も使わない。
合成の契約テスト専用の範囲（28201〜28299）だけを使う。合成の個体は、本番と同じ道具（measure.measure_seed）・同じ式で、区間だけを
小さくした Plan（SMALL：区間 W は e の Pulse 31〜180、H ＝ 60、本体は 239 まで、O3 の複製は 30 の後に作り 90 で比べる。0034 の
契約テストと同じ）で、実物の runtime を通して作る。結果を見て Plan・seed を選んでいない（seed は範囲の最初から順に使う）。
テストは操作の確認・記録の形・予測の規則の実装・判定の算術だけを確かめ、合成の個体の判定の量（s_e・ŝ・当たりの割合・V_i・Q_i・J_S・
R6）の値を表示も判定もしない。

二経路近似の実装の確かめ（test_two_path_is_exact_when_its_omissions_are_absent）は、二経路近似が無視するもの（t の後の可塑性と、
他の Unit の発火）がない場合に、実物の runtime の τ と一致することを見る。可塑性は FREEZE（6 本、Pulse t の境界）で止めた複製を使い、
他の Unit が発火した出来事は比べない。これは実装が Core の式と Pulse の順序に従うことの確かめで、判定の量ではない。

使った合成の seed（PR に開示）：28201〜28210（SMALL で実物の runtime を通す）、28221〜28226（一度限りの実行の契約。dummy の計算）、
28290〜28299 のうち 28299 から順に最初の出来事のある個体（本番の Plan で実物の runtime を通す確かめ）。
"""

import copy
import functools
import gzip
import importlib.util
import inspect
import json
import re
import subprocess
from concurrent.futures import Future
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments" / "0035_as1_state_dependent_feedback"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = _load("measure_0035_test", EXP / "measure.py")
AN = _load("analyze_0035_test", EXP / "analyze.py")
AL = _load("alignment_0035_test", EXP / "alignment.py")
R = _load("run_0035_test", EXP / "run.py")
A = M.A
SMALL = M.Plan(window_first=31, window_last=180, horizon=60, body_runs_to=239, checkpoints=(30, 120, 239),
               clone_check_at=30, clone_check_until=90)
SYN = list(range(28201, 28211))
GUARD_SEEDS = list(range(28221, 28227))


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)


def _raw(run: dict, mode: str = "synthetic") -> dict:
    return {"meta": {"experiment": "0035", "kind": PROTOCOL["kind"], "mode": mode, "seed": run["seed"],
                     "manifest": M.manifest_raw(), "blind": mode == "smoke"}, "run": run}


@functools.lru_cache(maxsize=None)
def _measured(seed: int) -> str:
    return json.dumps(_raw(M.measure_seed(PROTOCOL, seed, SMALL)))


def measured(seed: int) -> dict:
    """SMALL の Plan で実物の runtime を通した合成の個体の生の記録（JSON を通した形。返すのは複製）。"""
    return json.loads(_measured(seed))


def failures(data: dict, seed: int) -> dict:
    return {k: v for k, v in AN.check_seed(data, "synthetic", seed, SMALL).items() if v}


def first_with_events(at_least: int = 1) -> int:
    """合成の範囲の最初から順に見て、SMALL の区間 W に出来事が at_least 個以上ある最初の個体（決定的に求める。中身は見ない）。"""
    return next(s for s in SYN if len(measured(s)["run"]["events"]) >= at_least)


# ---- protocol と道具の一致 ----------------------------------------------------------------------

def test_protocol_and_tools_are_aligned() -> None:
    AL.check(PROTOCOL)


def test_formal_plan_follows_the_protocol_formulas() -> None:
    plan = M.formal_plan(PROTOCOL)
    assert (plan.window_first, plan.window_last, plan.horizon, plan.body_runs_to) == (301, 1800, 300, 2099)
    assert plan.checkpoints == (300, 600, 900, 1200, 1500, 1800, 2099)


def test_the_run_entry_point_uses_only_the_protocol_plan() -> None:
    assert inspect.signature(R.measure).parameters.keys() == {"seed"}
    assert "measure_seed(PROTOCOL, seed)" in inspect.getsource(R.measure)
    assert R.OUT_DIR == Path("data/experiments/0035") and R.MAX_WORKERS == 2 and AN.OUT_DIR == R.OUT_DIR


def test_seen_seeds_include_0034_and_exclude_0035() -> None:
    assert set(range(27001, 27300)) <= AL.SEEN
    assert not (set(range(28001, 28300)) & AL.SEEN)


def test_contract_tests_of_o1_are_the_as1_tests_and_this_file() -> None:
    assert AN.CONTRACT_TESTS == (PROTOCOL["tools"]["contract_tests"], str(Path(__file__).relative_to(ROOT)))


# ---- 実物の runtime を通した合成の個体：操作の確認がすべて成り立つ -----------------------------------

@pytest.mark.parametrize("seed", SYN)
def test_synthetic_individuals_pass_every_operation_check(seed) -> None:
    assert failures(measured(seed), seed) == {}


@functools.lru_cache(maxsize=None)
def _formal_synthetic() -> tuple[int, str]:
    """本番の Plan での確かめ：合成の範囲の最後（28299）から順に見て、本番の Plan の区間 W に出来事がある最初の個体（決定的に求める）。"""
    plan = M.formal_plan(PROTOCOL)
    for seed in range(28299, 28289, -1):
        run = M.measure_seed(PROTOCOL, seed, plan)
        if run["events"]:
            return seed, json.dumps(_raw(run))
    raise AssertionError("28290〜28299 に出来事のある個体がない")


def test_the_formal_plan_through_the_runtime_passes_every_operation_check() -> None:
    seed, text = _formal_synthetic()
    data = json.loads(text)
    assert {k: v for k, v in AN.check_seed(data, "synthetic", seed, M.formal_plan(PROTOCOL)).items() if v} == {}
    run = data["run"]
    assert run["clone_check"]["at"] == 300 and run["clone_check"]["until"] == 600
    assert sorted(map(int, run["body"]["checkpoints"])) == [300, 600, 900, 1200, 1500, 1800, 2099]
    assert set(run["rerun"]["sigma_sha256"]) == {str(p) for p in M.formal_plan(PROTOCOL).checkpoints} | {str(ev["t"]) for ev in run["events"]}


def test_the_synthetic_range_contains_individuals_with_and_without_events() -> None:
    have = [bool(measured(s)["run"]["events"]) for s in SYN]
    assert any(have) and not all(have)                    # 適用できる個体と N/A の個体の両方を確かめられる


def test_raw_has_no_prediction_or_judgment_quantities() -> None:
    run = measured(first_with_events())["run"]
    keys = set()

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                keys.add(k)
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(run)
    for name in ("s_e", "d_e", "s_hat", "tau_hat_F", "tau_hat_N", "tau_F", "acc_rule", "acc_const", "V_i", "Q_i", "J_S", "R6"):
        assert name not in keys, name


def test_sigma_t_is_the_tool_sigma_at_the_end_of_t() -> None:
    """Σ_t は、本体を Pulse t の処理の後まで進めたところの as1.sigma の書き出しそのもの（README §2.4）。"""
    seed = first_with_events()
    run = measured(seed)["run"]
    ev = run["events"][0]
    body = A.build(seed, delay=2, multiplicity=PROTOCOL["world"]["multiplicity"], respond=True, exogenous=(),
                   log=A.AS1Log(keep=M.body_log_keep(PROTOCOL)))
    A.advance_to(body.app, ev["t"])
    assert json.loads(json.dumps(M._sigma(body))) == ev["sigma_t"]
    assert set(ev["sigma_t"]) >= set(PROTOCOL["events"]["pre_branch_state"]["contents"])
    assert ev["sigma_t"]["pulse"] == ev["t"]


# ---- O5 の (a)：分岐の時点の N の Σ は、Σ_t から e の予約だけを取り消したもの（pending・cancelled の差分） -----------

def _first_event_live(seed: int):
    body = A.build(seed, delay=2, multiplicity=PROTOCOL["world"]["multiplicity"], respond=True, exogenous=(),
                   log=A.AS1Log(keep=M.body_log_keep(PROTOCOL)))
    for pulse in range(1, SMALL.body_runs_to + 1):
        before = len(body.world.intents)
        A.advance_to(body.app, pulse)
        found = M._event_at(body, before, SMALL, 2)
        if found is not None:
            return body, found
    raise AssertionError("出来事がない")


def test_the_n_branch_sigma_differs_from_sigma_t_only_by_moving_e_from_pending_to_cancelled() -> None:
    body, (t, _, e) = _first_event_live(first_with_events())
    sigma_t = M._sigma(body)
    n = A.clone(body)
    n.world.cancel(e.rid)
    sigma_n = M._sigma(n)
    assert sigma_n == M.expected_n_branch_sigma(sigma_t, {"rid": e.rid})          # 写しの全体が一致する
    assert {k for k in sigma_t if sigma_t[k] != sigma_n[k]} == {"world"}
    assert {k for k in sigma_t["world"] if sigma_t["world"][k] != sigma_n["world"][k]} == {"pending", "cancelled"}
    row = next(r for r in sigma_t["world"]["pending"] if r[0] == e.rid)
    assert sigma_n["world"]["pending"] == [r for r in sigma_t["world"]["pending"] if r[0] != e.rid]
    assert sigma_n["world"]["cancelled"] == list(sigma_t["world"]["cancelled"]) + [row]
    assert M._sigma(body) == sigma_t                                                 # 本体は変わらない


def _with_n_branch(f):
    """出来事 0 の分岐の時点の N の Σ の SHA-256 を、Σ_t を f で変えたものの SHA-256 に置き換える。"""
    def tamper(run):
        ev = run["events"][0]
        s = copy.deepcopy(ev["sigma_t"])
        f(s, ev["e"])
        ev["n_branch_sigma_sha256"] = M.sigma_sha256(s)
    return tamper


def test_o5_detects_a_branch_sigma_that_is_not_exactly_e_moved_to_cancelled() -> None:
    def removed_only(s, e):                                     # pending から除いたが cancelled に足していない
        s["world"]["pending"] = [r for r in s["world"]["pending"] if r[0] != e["rid"]]

    def cancelled_only(s, e):                                   # cancelled に足したが pending に残っている
        s["world"]["cancelled"] = list(s["world"]["cancelled"]) + [next(r for r in s["world"]["pending"] if r[0] == e["rid"])]

    def also_changed_a_unit(s, e):                              # e のほかに Unit の状態も違う
        moved = M.expected_n_branch_sigma(s, e)
        s.clear()
        s.update(moved)
        s["units"][next(iter(s["units"]))]["activity"] += 1e-9

    def also_changed_a_weight(s, e):
        moved = M.expected_n_branch_sigma(s, e)
        s.clear()
        s.update(moved)
        s["connections"][next(iter(s["connections"]))]["weight"] += 1e-9

    for f in (lambda s, e: None, removed_only, cancelled_only, also_changed_a_unit, also_changed_a_weight):
        _tampered(_with_n_branch(f), "O5")


def test_o5_detects_a_sigma_t_that_does_not_belong_to_t() -> None:
    _tampered(lambda r: r["events"][0]["sigma_t"].update(pulse=r["events"][0]["t"] + 1), "O5")
    _tampered(lambda r: r["events"][0]["sigma_t"]["world"].update(
        pending=[x for x in r["events"][0]["sigma_t"]["world"]["pending"] if x[0] != r["events"][0]["e"]["rid"]]), "O5")


# ---- O5 の (b)：保存した N の発火から計算し直した τ_N ------------------------------------------------

def test_o5_recomputes_tau_n_from_the_saved_firings() -> None:
    seed = first_with_events()
    data = measured(seed)
    run = data["run"]
    src = run["roles"]["source"]
    k = next((i for i, ev in enumerate(run["events"]) if ev["N"]["tau"] is not None), 0)
    ev = run["events"][k]
    if ev["N"]["tau"] is not None:                              # 源の発火を消すと、計算し直した τ_N が記録と合わない
        ev["N"]["firings"] = [x for x in ev["N"]["firings"] if x != [ev["N"]["tau"], src]]
    else:                                                       # 源の発火を足すと、計算し直した τ_N が記録と合わない
        ev["N"]["firings"] = sorted(ev["N"]["firings"] + [[ev["t"] + 1, src]], key=lambda x: x[0])
    assert "O5" in failures(data, seed)
    data = measured(seed)
    data["run"]["events"][0]["N"]["firings"].insert(0, [data["run"]["events"][0]["t"], src])   # 分岐の前の発火
    assert "O5" in failures(data, seed)


def test_n_firings_cover_all_units_from_the_branch() -> None:
    """系 N の発火の記録は、すべての Unit の発火で、分岐の後から始まる（R4・R8 が本体と N の他の Unit の発火を読めるように）。"""
    seed = first_with_events()
    run = measured(seed)["run"]
    units = set()
    for ev in run["events"]:
        assert all(ev["t"] < p <= ev["N"]["stopped_at"] for p, _ in ev["N"]["firings"])
        units |= {u for _, u in ev["N"]["firings"]}
    assert units <= {"s1", "s2", "s3"} and len(units) >= 2


# ---- O7：観測の非干渉（本体と系 N） --------------------------------------------------------------

def test_o7_detects_a_body_that_differs_from_the_plain_rerun() -> None:
    _tampered(lambda r: r["rerun"]["intents"].pop(), "O7")
    _tampered(lambda r: r["rerun"]["activity"].append([r["plan"]["body_runs_to"], "s1"]), "O7")
    _tampered(lambda r: r["rerun"]["sensory"].pop(0), "O7")
    _tampered(lambda r: r["rerun"]["sigma_sha256"].update({str(r["plan"]["checkpoints"][0]): "0" * 64}), "O7")
    _tampered(lambda r: r["rerun"]["sigma_sha256"].update({str(r["events"][0]["t"]): "0" * 64}), "O7")
    _tampered(lambda r: r["rerun"]["sigma_sha256"].pop(str(r["events"][-1]["t"])), "O7")
    _tampered(lambda r: r["body"]["checkpoint_sigma_sha256"].update({str(r["plan"]["checkpoints"][-1]): "0" * 64}), "O7")
    _tampered(lambda r: r["events"][0]["sigma_t"]["units"][r["roles"]["source"]].update(activity=0.123), "O7")


def test_o7_detects_an_n_that_differs_from_n_prime() -> None:
    _tampered(lambda r: r["events"][0]["N_prime"].update(tau=r["events"][0]["t"] + 1), "O7")
    _tampered(lambda r: r["events"][0]["N_prime"].update(stopped_at=r["events"][0]["N"]["stopped_at"] - 1), "O7")
    _tampered(lambda r: r["events"][0]["N_prime"]["sensory"].append([r["events"][0]["t"] + 1, r["roles"]["consequence_receptor"]]), "O7")
    _tampered(lambda r: r["events"][0]["N_prime"].update(sigma_stop_sha256="0" * 64), "O7")
    _tampered(lambda r: r["events"][0]["N"].update(sigma_stop_sha256="0" * 64), "O7")


def test_n_prime_keeps_only_sensory_events_in_its_log() -> None:
    body, (t, _, e) = _first_event_live(first_with_events())
    n = A.clone(body)
    n.world.cancel(e.rid)
    n_prime = A.clone(n)
    n_prime.log.keep = M.N_PRIME_LOG_KEEP
    a = M._run_n(n, t, SMALL.horizon, record_firings=True)
    b = M._run_n(n_prime, t, SMALL.horizon, record_firings=False)
    assert n_prime.log.activity() == [] and {ev.type for ev in n_prime.log.events} <= {A.RuntimeEventType.SENSORY}
    assert (a["tau"], a["stopped_at"], a["sensory"], a["sigma_stop_sha256"]) == \
        (b["tau"], b["stopped_at"], b["sensory"], b["sigma_stop_sha256"])


# ---- 改ざん・欠けの検出（O2〜O4・structure・O6） ------------------------------------------------------

def _tampered(f, check: str) -> None:
    seed = first_with_events()
    data = measured(seed)
    f(data["run"])
    got = failures(data, seed)
    assert check in got, (check, sorted(got))


def test_o2_detects_an_extra_or_missing_sensory_event() -> None:
    _tampered(lambda r: r["body"]["sensory"].append([r["plan"]["body_runs_to"], r["roles"]["source_receptor"]]), "O2")
    _tampered(lambda r: r["body"]["sensory"].pop(0), "O2")
    _tampered(lambda r: r["body"]["intents"].pop(), "O2")


def test_o3_detects_a_clone_that_differs() -> None:
    _tampered(lambda r: r["clone_check"]["sigma_clone"]["units"][r["roles"]["source"]].update(activity=0.123), "O3")
    _tampered(lambda r: r["clone_check"]["activity_clone"].append([r["plan"]["clone_check_until"], "s1"]), "O3")


def test_o4_detects_wrong_cancellation_or_sensory() -> None:
    _tampered(lambda r: r["events"][0].update(n_pending=copy.deepcopy(r["events"][0]["body_pending"])), "O4")   # e を取り消していない
    _tampered(lambda r: r["events"][0]["N"]["sensory"].append(list(r["events"][0]["N"]["sensory"][0])
                                                            if r["events"][0]["N"]["sensory"]
                                                            else [r["events"][0]["t"] + 1, r["events"][0]["e"]["receptor"]]), "O4")
    _tampered(lambda r: r["events"].pop(0), "O4")                   # 出来事が欠けた（A3 の適用の対象が崩れる）
    _tampered(lambda r: r["events"][0]["e"].update(pulse=r["events"][0]["e"]["pulse"] + 1), "O4")
    _tampered(lambda r: r["events"][0]["N"].update(stopped_at=r["events"][0]["t"] + r["plan"]["horizon"] + 1), "O4")


def test_o4_compares_only_the_post_branch_slice() -> None:
    seed = first_with_events(2)
    data = measured(seed)
    ev = data["run"]["events"][-1]
    assert any(x[0] <= ev["t"] for x in data["run"]["body"]["sensory"])          # 本体には分岐の前の出来事がある
    assert not any(x[0] <= ev["t"] for x in ev["N"]["sensory"])                   # N のログは分岐から始まる
    assert failures(data, seed) == {}
    ev["N"]["sensory"].append([ev["t"] + 1, data["run"]["roles"]["other"].replace("s", "receptor.x")])
    assert "O4" in failures(data, seed)


def test_structure_detects_extra_fields_and_wrong_roles() -> None:
    _tampered(lambda r: r.update(judgment={"J_S": True}), "structure")
    _tampered(lambda r: r["events"][0].update(s_hat="+"), "structure")              # 予測の量を raw に入れない
    _tampered(lambda r: r["events"][0]["N"].update(tau_hat=1), "structure")
    _tampered(lambda r: r["rerun"].update(extra=1), "structure")
    _tampered(lambda r: r["roles"].update(source="s9"), "structure")
    _tampered(lambda r: r["plan"].update(horizon=61), "structure")


def test_o6_rejects_seeds_outside_the_range_or_seen() -> None:
    for seed in (27001, 27201, 28001, 28101):                                    # 0034 の seed・本番・smoke は合成の範囲の外
        out: list = []
        AN._o6(seed, "synthetic", out)
        assert out, seed
    out = []
    AN._o6(28201, "synthetic", out)
    assert out == []


def test_meta_blind_must_match_the_mode() -> None:
    s = SYN[0]
    data = measured(s)
    data["meta"]["blind"] = "no"
    assert "structure" in failures(data, s)
    assert AN.check_seed(dict(measured(s), meta=dict(measured(s)["meta"], blind=True)), "synthetic", s, SMALL)["structure"] == []
    assert AN.check_seed(dict(measured(s), meta=dict(measured(s)["meta"], blind=True)), "formal", s, SMALL)["structure"]


# ---- 二経路近似（README §3）の実装 ----------------------------------------------------------------

def _unit(decay, threshold, drive, activity, alpha=0.0, tau=0.0):
    return {"dynamics": {"kind": "simple_activity", "decay_per_second": decay, "threshold": threshold, "refractory_pulses": 0,
                         "intrinsic_drive_per_second": drive, "adaptation_increment": alpha, "adaptation_tau_seconds": tau},
            "activity": activity, "refractory_remaining": 0, "adaptation": 0.0, "fire_count": 0}


def _sigma(receiver, source, w, drives=(), t=100):
    """手で作った Σ_t（受 r、源 s。式は Core の SimpleActivityDynamics。値は 2 進で割り切れるものを選んだ）。"""
    return {"pulse": t, "connections": {"r.main->s": {"weight": w}}, "drives": [list(d) for d in drives],
            "units": {"r": receiver, "s": source}}


def test_two_path_follows_the_pulse_order_in_hand_made_states() -> None:
    # F：受が t + 2 に結果の刺激で発火し、t + 3 に w が源へ届いて源が先に越える（＋）
    s = _sigma(_unit(0.0, 0.5, 0.0, 0.0), _unit(1.0, 1.0, 0.125, 0.5), 0.25)
    assert AN.two_path(s, "s", "r", 30) == (103, 104, "+")
    assert AN.two_path(s, "s", "r", 3) == (103, None, "+")                          # N は t + H の後：F だけ
    # N では受が t + 3 に自発で発火し、F では t + 2 に発火して戻る。源は上昇の途中なので、遅く届く N の駆動が先に効く（−）
    s = _sigma(_unit(1.0, 1.0, 0.25, 0.25), _unit(0.5, 0.99, 0.5, 0.0), 0.05)
    assert AN.two_path(s, "s", "r", 30) == (106, 105, "-")
    assert AN.two_path(s, "s", "r", 30, direct_only=True) == (106, 107, "+")       # 直接の経路だけなら ＋
    # 受は毎 Pulse 発火し、源は 3 回の駆動で越える：受の発火を何回でも追う（監査 032）。直接の経路だけでは越えない
    s = _sigma(_unit(0.0, 0.5, 0.6, 0.0), _unit(1.0, 1.0, 0.0, 0.0), 0.4)
    assert AN.two_path(s, "s", "r", 30) == (104, 104, "0")
    assert AN.two_path(s, "s", "r", 30, direct_only=True) == (None, None, "0")
    # Σ_t の駆動（Pulse t に作られ t + 1 に届く）を受と源の両方に入れる
    s = _sigma(_unit(0.0, 0.5, 0.0, 0.0), _unit(1.0, 1.0, 0.0, 0.0), 0.25,
               drives=[["x", "s", 0.75, None], ["x", "r", 0.5, None], ["x", "other", 9.0, None]])
    assert AN.two_path(s, "s", "r", 30) == (102, 102, "0")
    assert AN.two_path(s, "s", "r", 30, direct_only=True) == (103, None, "+")
    # どちらも発火しない：予測は ？ を出さず 0
    s = _sigma(_unit(0.0, 0.5, 0.0, 0.0), _unit(1.0, 1.0, 0.0, 0.0), 0.25)
    assert AN.two_path(s, "s", "r", 30) == (None, None, "0")


@pytest.mark.parametrize("hf,hn,sign", [(103, 105, "+"), (105, 103, "-"), (104, 104, "0"), (103, None, "+"),
                                        (None, 103, "-"), (None, None, "0")])
def test_predicted_sign_follows_the_table(hf, hn, sign) -> None:
    assert AN.predicted_sign(hf, hn) == sign


def test_two_path_reads_only_the_pre_branch_state_and_constants() -> None:
    """未来の情報を参照しない（README §3.2）：入力は Σ_t と定数（Receptor の重み・H）だけ。Σ_t のうちでも、源と受の Unit、
    受 → 源 の接続、Pulse t の駆動、Pulse の番号だけで計算が決まる（世界・runtime・他の Unit・ほかの接続を消しても同じ）。"""
    assert list(inspect.signature(AN.two_path).parameters) == ["sigma_t", "source", "receiver", "horizon", "receptor_weight",
                                                                "direct_only"]
    assert AN.RECEPTOR_WEIGHT == PROTOCOL["brain"]["receptor_weight"] == 1.0
    seed = first_with_events()
    run = measured(seed)["run"]
    src, rcv, h = run["roles"]["source"], run["roles"]["receiver"], run["plan"]["horizon"]
    for ev in run["events"]:
        full = ev["sigma_t"]
        key = f"{rcv}.main->{src}"
        minimal = {"pulse": full["pulse"], "connections": {key: {"weight": full["connections"][key]["weight"]}},
                   "drives": full["drives"], "units": {u: full["units"][u] for u in (src, rcv)}}
        for direct in (False, True):
            assert AN.two_path(full, src, rcv, h, direct_only=direct) == AN.two_path(minimal, src, rcv, h, direct_only=direct)


def test_predictions_do_not_change_when_future_fields_change() -> None:
    """出来事ごとに、t の後の本体の記録・系 N・N′・走り直し・ほかの出来事を壊しても、τ̂・ŝ と別の規則 (a)(b) の予測は変わらない。"""
    for seed in SYN:
        run = measured(seed)["run"]
        for k, ev in enumerate(run["events"]):
            t = ev["t"]
            before = AN.event_quantities(run, ev)
            cut = copy.deepcopy(run)
            body = cut["body"]
            body["intents"] = [x for x in body["intents"] if x[0] <= t] + [[t + 1, "x"]]
            body["activity"] = [x for x in body["activity"] if x[0] <= t] + [[t + 1, u] for u in ("s1", "s2", "s3")]
            body["sensory"] = [x for x in body["sensory"] if x[0] <= t]
            cut["rerun"] = {}
            cut["events"] = [e if i == k else {} for i, e in enumerate(cut["events"])]
            mine = cut["events"][k]
            mine["N"] = {"tau": t + 1, "stopped_at": t + 1, "sensory": [], "sigma_stop_sha256": "", "firings": [[t + 1, "s1"]]}
            mine["N_prime"] = {}
            after = AN.event_quantities(cut, mine)
            for name in ("tau_hat_F", "tau_hat_N", "s_hat", "s_direct", "s_rhythm"):
                assert after[name] == before[name], (seed, k, name)


@pytest.mark.parametrize("seed", SYN)
def test_two_path_is_exact_when_its_omissions_are_absent(seed) -> None:
    """二経路近似が無視するもの（t の後の可塑性・他の Unit の発火）がないとき、実物の runtime の τ_F・τ_N と一致する。
    可塑性は FREEZE（6 本、Pulse t の境界、advance）で止める。他の Unit が (t, 止まった Pulse] に発火した出来事は比べない。"""
    body = A.build(seed, delay=2, multiplicity=PROTOCOL["world"]["multiplicity"], respond=True, exogenous=(),
                   log=A.AS1Log(keep=M.body_log_keep(PROTOCOL)))
    roles = body.roles
    plastic = frozenset(body.app.connections.export_state())
    for pulse in range(1, SMALL.body_runs_to + 1):
        before = len(body.world.intents)
        A.advance_to(body.app, pulse)
        found = M._event_at(body, before, SMALL, 2)
        if found is None:
            continue
        t, _, e = found
        sigma_t = M._sigma(body)
        f, n = A.clone(body), A.clone(body)
        n.world.cancel(e.rid)
        for system in (f, n):
            system.declare([A.Intervention(A.FREEZE, plastic, A.ADVANCE)], label="contract")
        tau_f = A.advance_until_first_intent(f, t, t + SMALL.horizon)
        tau_n = A.advance_until_first_intent(n, t, t + SMALL.horizon)
        if any(u == roles.other for system in (f, n) for _, u in system.log.activity()):
            continue
        hat_f, hat_n, _ = AN.two_path(json.loads(json.dumps(sigma_t)), roles.source, roles.receiver, SMALL.horizon)
        assert (hat_f, hat_n) == (tau_f, tau_n), (seed, t)


def test_the_exactness_check_covers_events() -> None:
    """上の確かめが空でないこと（合成の 10 個体で、比べた出来事が少なくとも 1 つある）。数だけを見る。"""
    compared = 0
    for seed in SYN:
        body = A.build(seed, delay=2, multiplicity=PROTOCOL["world"]["multiplicity"], respond=True, exogenous=(),
                       log=A.AS1Log(keep=M.body_log_keep(PROTOCOL)))
        plastic = frozenset(body.app.connections.export_state())
        for pulse in range(1, SMALL.body_runs_to + 1):
            before = len(body.world.intents)
            A.advance_to(body.app, pulse)
            found = M._event_at(body, before, SMALL, 2)
            if found is None:
                continue
            t, _, e = found
            f, n = A.clone(body), A.clone(body)
            n.world.cancel(e.rid)
            for system in (f, n):
                system.declare([A.Intervention(A.FREEZE, plastic, A.ADVANCE)], label="contract")
                A.advance_until_first_intent(system, t, t + SMALL.horizon)
            compared += not any(u == body.roles.other for system in (f, n) for _, u in system.log.activity())
    assert compared >= 1


def test_direct_only_predicts_only_plus_or_zero() -> None:
    for seed in SYN:
        run = measured(seed)["run"]
        for ev in run["events"]:
            assert AN.event_quantities(run, ev)["s_direct"] in ("+", "0")


def test_past_rhythm_definition() -> None:
    # 受の最後の発火 90、その前 80 → r̂ ＝ 100。源の直前の意図 60、t ＝ 95 → ŝrc ＝ 130。t + 2 ＝ 97 ＜ 100 ＜ 130 → −
    act = [[80, "r"], [90, "r"], [96, "r"], [60, "s"]]                            # 96 は t ＝ 95 の後（使わない）
    assert AN.past_rhythm(act, [60, 95], "s", "r", 95) == "-"
    assert AN.past_rhythm(act + [[200, "r"], [210, "r"]], [60, 95, 150], "s", "r", 95) == "-"   # t の後の発火・意図は使わない
    assert AN.past_rhythm([[90, "r"], [91, "r"]], [60, 95], "s", "r", 95) == "0"   # r̂ ＝ 92 ≤ t + 2 ＝ 97
    assert AN.past_rhythm([[50, "r"], [90, "r"]], [60, 95], "s", "r", 95) == "0"   # r̂ ＝ 130 ＝ ŝrc（厳密に小さくない）
    assert AN.past_rhythm([[90, "r"]], [60, 95], "s", "r", 95) == "0"            # 受の過去の発火が 1 つ：足りない
    assert AN.past_rhythm(act, [95], "s", "r", 95) == "0"                        # 源の直前の意図がない：足りない


# ---- 個体の量・判定の算術（合成の入力） ------------------------------------------------------------

def _individual(monkeypatch, pairs):
    """出来事ごとの (s_e, ŝ) だけを与えて、個体の量を計算する（ほかの欄は固定の値）。"""
    def fake(run, ev):
        s_e, s_hat = pairs[ev["k"]]
        return {"t": ev["k"], "s_e": s_e, "s_hat": s_hat, "s_direct": "0", "s_rhythm": "0", "other_fired": False}
    monkeypatch.setattr(AN, "event_quantities", fake)
    run = {"roles": {"source": "s1", "receiver": "s2", "other": "s3"}, "body": {"birth_units": {}, "activity": []},
           "events": [{"k": k} for k in range(len(pairs))]}
    return AN.individual(run)


def test_individual_without_events_is_not_applicable(monkeypatch) -> None:
    v = _individual(monkeypatch, [])
    assert (v["applicable"], v["V_i"], v["Q_i"], v["acc_rule"], v["acc_const"]) == (False, False, False, None, None)


def test_zero_evaluable_events_give_null_accuracies(monkeypatch) -> None:
    v = _individual(monkeypatch, [("?", "0"), ("?", "+")])
    assert v["applicable"] is True and v["evaluable"] == 0 and v["counts"]["n_unknown"] == 2
    assert (v["acc_rule"], v["acc_const"], v["acc_plus"], v["acc_zero"], v["acc_minus"]) == (None,) * 5
    assert v["V_i"] is False and v["Q_i"] is False


def test_single_class_individuals_cannot_satisfy_q(monkeypatch) -> None:
    v = _individual(monkeypatch, [("0", "0")] * 4 + [("?", "+")])
    assert v["V_i"] is False and v["acc_rule"] == v["acc_const"] == 1.0 and v["Q_i"] is False   # 監査 031 の天井


def test_q_is_strict_and_uses_only_evaluable_events(monkeypatch) -> None:
    v = _individual(monkeypatch, [("+", "+"), ("0", "0"), ("0", "0"), ("?", "-")])
    assert v["V_i"] is True and v["evaluable"] == 3 and v["correct_rule"] == 3 and v["Q_i"] is True
    tie = _individual(monkeypatch, [("+", "+"), ("+", "+"), ("0", "+"), ("0", "+")])
    assert tie["V_i"] is True and tie["acc_rule"] == tie["acc_const"] == 0.5 and tie["Q_i"] is False   # 等しいときは不成立
    worse = _individual(monkeypatch, [("+", "+"), ("0", "+"), ("0", "0"), ("0", "-")])
    assert worse["V_i"] is True and worse["Q_i"] is False
    assert worse["confusion"]["+|0"] == 1 and worse["confusion"]["-|0"] == 1 and sum(worse["confusion"].values()) == 4


def test_v_uses_only_the_s_e_labels(monkeypatch) -> None:
    labels = [("+", None), ("0", None), ("0", None)]
    vs = {_individual(monkeypatch, [(a, s) for (a, _), s in zip(labels, hats)])["V_i"]
          for hats in (("+", "0", "0"), ("-", "-", "-"), ("0", "+", "-"))}
    assert vs == {True}
    assert _individual(monkeypatch, [("-", "+"), ("-", "0")])["V_i"] is False


def test_negative_control_is_a_cyclic_shift_within_the_individual(monkeypatch) -> None:
    v = _individual(monkeypatch, [("+", "+"), ("0", "0"), ("-", "-")])
    assert [e["s_shift"] for e in v["events"]] == ["0", "-", "+"]                 # 出来事 k に (k + ⌊3/2⌋) mod 3 の ŝ
    assert v["alternatives"]["shift"] == {"applicable": True, "correct": 0, "acc": 0.0, "Q_like": False}
    v = _individual(monkeypatch, [("+", "+"), ("0", "0"), ("0", "0"), ("-", "-")])
    assert [e["s_shift"] for e in v["events"]] == ["0", "-", "+", "0"]
    one = _individual(monkeypatch, [("+", "+")])
    assert one["alternatives"]["shift"] == {"applicable": False, "correct": None, "acc": None, "Q_like": False}   # n ＜ 2 は対象外


def _inds(n_v: int, n_q: int, n_single: int = 0, n_na: int = 0) -> dict:
    d = {}
    for i in range(n_v):
        d[f"v{i}"] = {"applicable": True, "V_i": True, "Q_i": i < n_q}
    for i in range(n_single):
        d[f"s{i}"] = {"applicable": True, "V_i": False, "Q_i": True}            # 判定の対象の外（数に入れない）
    for i in range(n_na):
        d[f"n{i}"] = {"applicable": False, "V_i": False, "Q_i": False}
    return d


def test_judge_counts_only_decision_individuals_and_thresholds() -> None:
    assert AN.judge(_inds(10, 9, 30, 20))["J_S"] == {"m": 10, "count_Q_i": 9, "k": 9, "tail_probability": AN.binom_upper_tail(10, 9),
                                                     "status": "established"}
    assert AN.judge(_inds(10, 8, 30))["J_S"]["status"] == "not_established"
    assert AN.judge(_inds(20, 15))["J_S"]["status"] == "established" and AN.judge(_inds(20, 14))["J_S"]["status"] == "not_established"
    assert AN.judge(_inds(60, 37))["J_S"]["status"] == "established" and AN.judge(_inds(60, 36))["J_S"]["status"] == "not_established"
    assert AN.judge(_inds(39, 26))["J_S"]["k"] == 26


def test_r6_is_null_below_ten_and_kept_apart_from_the_inconclusive_status() -> None:
    """m ＜ 10：J_S は判定不能（status）で、R6 は別の欄として計算しない（interval は null、理由を書く）。
    m ≥ 10：J_S の成立・不成立にかかわらず、R6 を同じ分母 m で計算する（R6 の null は m だけで決まり、J_S の status では決まらない）。"""
    for m in (0, 1, 9):
        out = AN.judge(_inds(m, m, 5, 5))
        assert out["J_S"]["status"] == "inconclusive" and out["J_S"]["k"] is None and "interval" not in out["J_S"]
        assert out["R6"]["computed"] is False and out["R6"]["interval"] is None
        assert out["R6"]["denominator"] == m and "not computed" in out["R6"]["reason"]
    for n_q in (9, 3):
        out = AN.judge(_inds(10, n_q))
        assert out["J_S"]["status"] in ("established", "not_established") and out["R6"]["computed"] is True
        lo, hi = out["R6"]["interval"]
        assert (lo, hi) == AN.clopper_pearson(n_q, 10) and out["R6"]["numerator"] == n_q and out["R6"]["denominator"] == 10


def test_k_of_m_matches_the_protocol_table() -> None:
    for m, k in PROTOCOL["judgment"]["J_S"]["k_of_m"].items():
        assert AN.k_of_m(m, 0.05) == k


def test_clopper_pearson_known_values() -> None:
    lo, hi = AN.clopper_pearson(16, 20)
    assert round(lo, 4) == 0.5634 and round(hi, 4) == 0.9427
    assert AN.clopper_pearson(0, 10)[0] == 0.0 and AN.clopper_pearson(10, 10)[1] == 1.0


def test_analysis_of_the_synthetic_individuals_runs_through() -> None:
    runs = {s: measured(s) for s in SYN}
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=[])
    assert report["valid"] is True and set(report["judgment"]) == {"J_S"} and report["O1"]["status"] == "ok"
    assert set(report["judgment"]["J_S"]) >= {"m", "count_Q_i", "status"} and set(report["R6"]) >= {"computed", "interval"}
    assert set(report["individuals"]) == {str(s) for s in SYN}
    assert set(report["auxiliary"]) == {"R3_alternative_Q_like_counts", "R4_misses", "R5_pooled_confusion", "R7_weights",
                                        "R8_by_other_unit", "R9"}


def test_auxiliary_records_are_consistent_with_the_individuals() -> None:
    """R2・R4・R5・R8・R9 の数どうしの整合（値は見ない）。"""
    runs = {s: measured(s) for s in SYN}
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=[])
    inds, aux = report["individuals"], report["auxiliary"]
    evaluable = sum(v["evaluable"] for v in inds.values())
    assert sum(aux["R5_pooled_confusion"].values()) == evaluable
    pooled = aux["R8_by_other_unit"]["pooled"]
    assert pooled["other_quiet"]["events"] + pooled["other_fired"]["events"] == evaluable
    assert sum(len(x) for x in aux["R4_misses"]["per_individual"].values()) == aux["R4_misses"]["pooled"]["misses"]
    assert aux["R4_misses"]["pooled"]["misses"] == evaluable - sum(v["correct_rule"] for v in inds.values())
    applicable = {s for s, v in inds.items() if v["applicable"]}
    assert set(aux["R9"]["outside_decision"]) == {s for s in applicable if not inds[s]["V_i"]}
    assert aux["R9"]["applicable"] == len(applicable) == aux["R9"]["all_applicable_beats_const"]["denominator"]
    assert aux["R9"]["all_applicable_beats_const"]["count"] == sum(1 for s in applicable if inds[s]["Q_i"])
    for s, v in inds.items():
        run = runs[int(s)]["run"]
        assert v["roles"] == run["roles"] and v["birth_units"] == run["body"]["birth_units"]
        assert v["events_in_window"] == len(run["events"]) and v["applicable"] == bool(run["events"])
        assert sum(v["counts"].values()) == v["events_in_window"]
        assert sum(v["confusion"].values()) == v["evaluable"]
        if v["Q_i"]:
            assert v["V_i"]                                                       # Q_i は V_i のない個体では成り立たない
        for p, st in run["body"]["checkpoints"].items():
            r7 = aux["R7_weights"][s][p]
            assert r7["weights"] == {c: x["weight"] for c, x in st.items()} and set(r7) == {"weights", "traces", "pair_sums"}


def test_u_e_and_other_unit_come_from_the_saved_firings() -> None:
    seed = first_with_events()
    run = measured(seed)["run"]
    other = run["roles"]["other"]
    for ev in run["events"]:
        q = AN.event_quantities(run, ev)
        t, h = ev["t"], run["plan"]["horizon"]
        assert q["u_e"] == min(x for x in (q["tau_F"], q["tau_N"], t + h) if x is not None)
        fired = any(u == other and t < p <= q["u_e"] for p, u in run["body"]["activity"] + ev["N"]["firings"])
        assert q["other_fired"] is fired


def test_an_invalid_individual_or_a_failed_o1_blocks_the_judgment() -> None:
    runs = {s: measured(s) for s in SYN}
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=["x"])
    assert report["valid"] is False and report["judgment"] is None and report["O1"]["status"] == "fail"
    assert "R6" not in report and "individuals" not in report
    s = first_with_events()
    runs[s]["run"]["events"][0]["N_prime"]["tau"] = -1
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=[])
    assert report["valid"] is False and report["judgment"] is None and "O7" in report["failed_checks"][str(s)]


# ---- 一度限りの実行（guard と run.execute。dummy の計算） -------------------------------------------------

class SerialExecutor:
    def __init__(self, n: int) -> None:
        self.n = n

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def submit(self, fn, *args, **kwargs):
        f = Future()
        try:
            f.set_result(fn(*args, **kwargs))
        except BaseException as e:                     # noqa: BLE001
            f.set_exception(e)
        return f


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path) -> Path:
    r = tmp_path / "repo"
    (r / EXP.relative_to(ROOT)).mkdir(parents=True)
    (r / EXP.relative_to(ROOT) / "protocol.yaml").write_bytes((EXP / "protocol.yaml").read_bytes())
    _git(r, "init", "-q")
    for k, v in (("user.email", "t@example.invalid"), ("user.name", "t"), ("commit.gpgsign", "false")):
        _git(r, "config", k, v)
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "init")
    return r


def _dummy(seed: int) -> dict:
    return {"seed": seed, "dummy": True}


def _exec(repo, out, seeds, runner=_dummy):
    return R.execute("synthetic", seeds, out, repo, _git(repo, "rev-parse", "HEAD"), runner=runner,
                     executor_factory=SerialExecutor)


def test_each_seed_runs_once_and_a_failure_stops_the_rest(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    done = _exec(repo, out, GUARD_SEEDS[:2])
    assert done["completed"] == GUARD_SEEDS[:2]
    with pytest.raises(R.G.GuardError):
        _exec(repo, out, GUARD_SEEDS[:1])                                # 二度と始めない

    def boom(seed: int) -> dict:
        if seed == GUARD_SEEDS[3]:
            raise RuntimeError("x")
        return _dummy(seed)
    out2 = tmp_path / "out2"
    with pytest.raises(R.G.GuardError):
        _exec(repo, out2, GUARD_SEEDS[2:6], runner=boom)
    statuses = {s: st for s, (st, _) in R.G.scan(out2)["seeds"].items()}
    assert statuses[GUARD_SEEDS[3]] == "failed" and GUARD_SEEDS[5] not in statuses
    with pytest.raises(R.G.GuardError):
        _exec(repo, out2, GUARD_SEEDS[5:6])                              # 失敗があれば、どの seed も始めない


def test_formal_requires_the_measurement_commit_and_the_range(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    with pytest.raises(R.G.GuardError):
        R.execute("formal", [28001], tmp_path / "o", repo, None, runner=_dummy, executor_factory=SerialExecutor)
    for seed in (28001, 28101, 27201):                                   # 本番・smoke・0034 の seed は合成の mode で走らない
        with pytest.raises(R.G.GuardError):
            R.execute("synthetic", [seed], tmp_path / f"o{seed}", repo, _git(repo, "rev-parse", "HEAD"), runner=_dummy,
                      executor_factory=SerialExecutor)
        assert not (tmp_path / f"o{seed}").exists()


def test_records_state_and_the_synthetic_pipeline_through_run_and_analyze(repo, tmp_path, monkeypatch) -> None:
    """run.execute（合成の mode、SMALL の Plan の実物の計算）→ 記録の確認 → 生の記録からの解析、を通す（判定の値は見ない）。"""
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    seeds = SYN[:3]
    runner = functools.partial(M.measure_seed, PROTOCOL, plan=SMALL)
    _exec(repo, out, seeds[:2], runner=runner)
    assert AN.verify_records(out, "synthetic", seeds)["state"] == "incomplete"
    _exec(repo, out, seeds[2:], runner=runner)
    records = AN.verify_records(out, "synthetic", seeds)
    assert records["state"] == "complete" and records["measurement_commit"] == _git(repo, "rev-parse", "HEAD")
    runs = {s: AN.read_raw(R.G.seed_dir(out, s) / R.G.RAW) for s in seeds}
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=[])
    assert report["valid"] is True and report["judgment"]["J_S"]["status"] == "inconclusive"   # 3 個体なので m ＜ 10
    assert report["R6"]["computed"] is False and report["R6"]["interval"] is None


# ---- smoke の盲検（0034 の #150 のレビューの必須 1）：現象の数値を保存しない -------------------------------------

FORBIDDEN_KEYS = ((AN.RUN_KEYS - {"seed", "plan", "roles"}) | AN.BODY_KEYS | AN.EVENT_KEYS | AN.N_KEYS | AN.RERUN_KEYS
                  | {"run", "s_e", "d_e", "s_hat", "tau_hat_F", "tau_hat_N", "acc_rule", "acc_const", "V_i", "Q_i", "J_S", "R6",
                     "judgment", "individuals", "auxiliary"})
META_KEYS = {"experiment", "kind", "mode", "seed", "measurement_commit", "protocol_sha256", "protocol", "manifest", "blind"}


def _keys(x, path=()):
    """JSON の値の中の、すべての (経路, 欄の名前)。meta の protocol・manifest（実行の前に決まっている定数）は見ない。"""
    if isinstance(x, dict):
        for k, v in x.items():
            yield path, k
            if path == ("meta",) and k in ("protocol", "manifest"):
                continue
            yield from _keys(v, path + (k,))
    elif isinstance(x, list):
        for v in x:
            yield from _keys(v, path)


ISO_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
NUMERIC_OK = {"seed", "raw_file_bytes", "max_workers", "pid"}       # 実行の記録に数値で残ってよい欄（時間の手がかりにならない）


def _numeric_keys(x, key=None):
    if isinstance(x, bool):
        return set()
    if isinstance(x, (int, float)):
        return {key}
    if isinstance(x, dict):
        return set().union(*(_numeric_keys(v, k) for k, v in x.items())) if x else set()
    if isinstance(x, list):
        return set().union(*(_numeric_keys(v, key) for v in x)) if x else set()
    return set()


def _blind_exec(repo, out, seeds, runner=None, workers=None):
    def factory(n):
        if workers is not None:
            workers.append(n)
        return SerialExecutor(n)
    return R.execute("synthetic", seeds, out, repo, _git(repo, "rev-parse", "HEAD"),
                     runner=runner or functools.partial(M.measure_seed, PROTOCOL, plan=SMALL),
                     executor_factory=factory, blind=True, check_plan=SMALL)


def _assert_no_timing(out: Path) -> None:
    """盲検の出力先から、seed ごとの実行の時間を戻せないこと（0034 の #150 の再レビュー 5692062243）。"""
    for d in [out, *out.rglob("*")]:                                  # 読むと変わるアクセスの時刻は見ない（中身の更新の時刻を見る）
        assert d.stat().st_mtime == R.CONCEALED_MTIME, d
    for d in sorted((out / R.G.SEEDS_DIR).iterdir()):
        start = json.loads((d / R.G.START).read_text(encoding="utf-8"))
        finish = json.loads((d / R.G.FINISH).read_text(encoding="utf-8"))
        assert start["started_at"] == R.BLINDED_TIME and finish["finished_at"] == R.BLINDED_TIME
        assert finish["seconds"] is None and start["max_workers"] == 1
        for rec in (start, finish):
            assert not ISO_TIME.search(json.dumps(rec)), rec
            assert _numeric_keys(rec) <= NUMERIC_OK, _numeric_keys(rec)
        if (d / R.G.RAW).exists():
            raw = json.loads(gzip.decompress((d / R.G.RAW).read_bytes()))
            assert not ISO_TIME.search(json.dumps(raw["blind"])) and set(raw["meta"]) == META_KEYS


def test_blind_execution_stores_no_phenomenon_values(repo, tmp_path, monkeypatch, capsys) -> None:
    """smoke と同じ盲検の実行を合成の seed で行い、出力先のすべてのファイルに、Σ_t・現象の数値・予測と判定の量が無いことを確かめる。"""
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    seeds = [first_with_events(), next(s for s in SYN if not measured(s)["run"]["events"]), SYN[-1]]
    workers: list[int] = []
    done = _blind_exec(repo, out, seeds, workers=workers)
    assert done["completed"] == sorted(seeds) and workers == [1]     # 盲検は 1 つずつ（終わる順を残さない）
    assert capsys.readouterr().out == ""                             # seed ごとの進み具合・時間を表示しない
    _assert_no_timing(out)
    assert AN.verify_records(out, "synthetic", sorted(seeds))["state"] == "complete"
    with pytest.raises(R.G.GuardError):
        _blind_exec(repo, out, seeds[:1])                            # 二度と始めない
    files = sorted(p for p in out.rglob("*") if p.is_file() and p != out / R.G.LOCK)
    assert (out / R.G.LOCK).read_bytes() == b""
    assert {p.name for p in files} == {R.G.START, R.G.FINISH, R.G.RAW} and len(files) == 3 * len(seeds)
    for p in files:
        data = json.loads(gzip.decompress(p.read_bytes()) if p.name.endswith(".gz") else p.read_bytes())
        bad = {k for _, k in _keys(data) if k in FORBIDDEN_KEYS}
        assert not bad, (p, bad)
        if p.name == R.G.RAW:
            s = data["meta"]["seed"]
            assert set(data) == {"meta", "blind"} and set(data["meta"]) == META_KEYS and set(data["blind"]) == AN.BLIND_KEYS
            assert data["meta"]["protocol"] == json.loads(json.dumps(PROTOCOL)) and data["meta"]["manifest"] == M.manifest_raw()
            assert data["blind"]["checks"] == {k: "ok" for k in AN.CHECK_NAMES}
            assert set(AN.CHECK_NAMES) == {"structure", "O2", "O3", "O4", "O5", "O6", "O7"}
            again = {"meta": data["meta"], "run": M.measure_seed(PROTOCOL, s, SMALL)}
            canonical = json.dumps(json.loads(json.dumps(again)), separators=(",", ":"), sort_keys=True).encode("utf-8")
            assert data["blind"]["raw_sha256"] == R.G.sha256_bytes(canonical)
            assert AN.check_blinded(data, s, "synthetic") == {k: "ok" for k in AN.CHECK_NAMES}


def test_blind_failure_keeps_no_timing_or_reason_text(repo, tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"

    def boom(seed: int) -> dict:
        if seed == GUARD_SEEDS[1]:
            raise RuntimeError("Pulse 1234：x")
        return M.measure_seed(PROTOCOL, seed, SMALL)
    with pytest.raises(R.G.GuardError) as err:
        _blind_exec(repo, out, GUARD_SEEDS[:3], runner=boom)
    assert "1234" not in str(err.value)
    statuses = {s: st for s, (st, _) in R.G.scan(out)["seeds"].items()}
    assert statuses == {GUARD_SEEDS[0]: "completed", GUARD_SEEDS[1]: "failed"}
    finish = json.loads((R.G.seed_dir(out, GUARD_SEEDS[1]) / R.G.FINISH).read_text(encoding="utf-8"))
    assert finish["reason"] == "RuntimeError"
    assert all("1234" not in p.read_bytes().decode("utf-8", "replace") for p in out.rglob("*") if p.is_file())
    assert capsys.readouterr().out == ""
    _assert_no_timing(out)


def test_non_blind_runs_keep_real_times(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    _exec(repo, out, GUARD_SEEDS[:1])
    d = R.G.seed_dir(out, GUARD_SEEDS[0])
    start = json.loads((d / R.G.START).read_text(encoding="utf-8"))
    finish = json.loads((d / R.G.FINISH).read_text(encoding="utf-8"))
    assert ISO_TIME.match(start["started_at"]) and ISO_TIME.match(finish["finished_at"])
    assert isinstance(finish["seconds"], float) and start["max_workers"] == R.MAX_WORKERS
    assert (d / R.G.START).stat().st_mtime != R.CONCEALED_MTIME


def test_blinded_record_marks_a_failed_check_without_reasons() -> None:
    s = first_with_events()
    for tamper, check in ((lambda r: r["events"][0].update(n_pending=copy.deepcopy(r["events"][0]["body_pending"])), "O4"),
                          (lambda r: r["events"][0].update(n_branch_sigma_sha256="0" * 64), "O5"),
                          (lambda r: r["events"][0]["N_prime"].update(sigma_stop_sha256="0" * 64), "O7")):
        data = measured(s)
        data["meta"]["blind"] = True
        tamper(data["run"])
        rec = R.blinded(data, "synthetic", s, SMALL)
        assert set(rec) == {"meta", "blind"} and set(rec["blind"]) == AN.BLIND_KEYS
        assert rec["blind"]["checks"][check] == "fail" and set(rec["blind"]["checks"].values()) <= {"ok", "fail"}


def test_smoke_report_reads_blinded_records_and_rechecks_o6() -> None:
    s = SYN[0]
    data = measured(s)
    data["meta"]["blind"] = True
    rec = R.blinded(data, "synthetic", s, SMALL)
    rec["meta"]["mode"] = "smoke"
    report = AN.analyze_runs({s: rec}, "smoke", o1=[])
    assert set(report) == {"mode", "O1", "checks", "valid"} and report["O1"] == "ok"
    assert report["checks"][str(s)]["O6"] == "fail" and report["valid"] is False        # 合成の seed は smoke の範囲の外
    assert {v for k, v in report["checks"][str(s)].items() if k != "O6"} == {"ok"}
    broken = copy.deepcopy(rec)
    broken["blind"]["extra"] = 1
    assert AN.check_blinded(broken, s, "smoke") == {k: "fail" for k in AN.CHECK_NAMES}
    leaked = dict(copy.deepcopy(rec), run=data["run"])                                    # 生の記録を混ぜた記録は通さない
    assert AN.check_blinded(leaked, s, "smoke") == {k: "fail" for k in AN.CHECK_NAMES}
    missing = copy.deepcopy(rec)
    missing["blind"]["checks"].pop("O7")                                                  # O7 の欠けた記録は通さない
    assert AN.check_blinded(missing, s, "smoke") == {k: "fail" for k in AN.CHECK_NAMES}
    assert AN.analyze_runs({s: rec}, "smoke", o1=["x"])["O1"] == "fail"


def test_smoke_must_be_blind_and_formal_must_not(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    commit = _git(repo, "rev-parse", "HEAD")
    for mode, kw in (("smoke", {"blind": False}), ("formal", {"blind": True}), ("smoke", {"check_plan": SMALL}),
                     ("formal", {"check_plan": SMALL})):
        out = tmp_path / f"o_{mode}_{len(kw)}_{sorted(kw)[0]}"
        with pytest.raises(R.G.GuardError):                     # seed に触れる前に止まる（seed は合成の範囲のもの）
            R.execute(mode, GUARD_SEEDS[:1], out, repo, commit, runner=_dummy, executor_factory=SerialExecutor, **kw)
        assert not out.exists()


# ---- O1 の証拠（測定の commit で契約テストを実際に走らせた記録） ---------------------------------------------

class _Proc:
    def __init__(self, code: int, stdout: str) -> None:
        self.returncode, self.stdout = code, stdout


def _o1_repo(repo: Path) -> str:
    for f in AN.CONTRACT_TESTS:
        (repo / f).parent.mkdir(parents=True, exist_ok=True)
        (repo / f).write_text(f"# {f}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "tests")
    return _git(repo, "rev-parse", "HEAD")


def test_o1_records_the_real_contract_test_run_once(repo, tmp_path, monkeypatch) -> None:
    commit = _o1_repo(repo)
    monkeypatch.setattr(AN, "REPO", repo)
    calls = []

    def ok(cmd, **kw):
        calls.append((cmd, kw["cwd"]))
        return _Proc(0, "....\n150 passed in 9.0s\n")
    out = tmp_path / "out"
    rec = R.record_contract_tests(repo, out, commit, run=ok)
    assert rec["exit_code"] == 0 and rec["summary"] == "150 passed in 9.0s" and calls[0][1] == repo
    assert calls[0][0][1:] == ["-m", "pytest", "-q", *AN.CONTRACT_TESTS]
    assert AN.o1_check(out, commit) == []
    R.record_contract_tests(repo, out, commit, run=lambda *a, **k: pytest.fail("走らせ直さない"))
    assert AN.o1_check(out, "0" * 40)
    with pytest.raises(R.G.GuardError):
        R.record_contract_tests(repo, out, "0" * 40, run=ok)


def test_o1_failure_or_tampering_is_detected(repo, tmp_path, monkeypatch) -> None:
    commit = _o1_repo(repo)
    monkeypatch.setattr(AN, "REPO", repo)
    out = tmp_path / "out"
    assert AN.o1_check(out, commit)
    with pytest.raises(R.G.GuardError):
        R.record_contract_tests(repo, out, commit, run=lambda *a, **k: _Proc(1, "1 failed, 149 passed in 9.0s\n"))
    assert AN.o1_check(out, commit)
    with pytest.raises(R.G.GuardError):
        R.record_contract_tests(repo, out, commit, run=lambda *a, **k: _Proc(0, "150 passed\n"))   # 書き直さない
    out2 = tmp_path / "out2"
    R.record_contract_tests(repo, out2, commit, run=lambda *a, **k: _Proc(0, "150 passed in 9.0s\n"))
    path = out2 / AN.O1_FILE
    good = json.loads(path.read_text(encoding="utf-8"))
    for tamper in (lambda r: r.update(exit_code=2), lambda r: r.update(summary="2 failed, 148 passed"),
                   lambda r: r["test_files_sha256"].update({AN.CONTRACT_TESTS[0]: "0" * 64}),
                   lambda r: r.update(command=["python", "-m", "pytest", "-q"]), lambda r: r.pop("at")):
        bad = copy.deepcopy(good)
        tamper(bad)
        path.write_text(json.dumps(bad), encoding="utf-8")
        assert AN.o1_check(out2, commit), bad
    (repo / AN.CONTRACT_TESTS[1]).write_text("# changed\n", encoding="utf-8")
    path.write_text(json.dumps(good), encoding="utf-8")
    assert AN.o1_check(out2, commit)
    with pytest.raises(R.G.GuardError):
        R.record_contract_tests(repo, tmp_path / "out3", commit, run=lambda *a, **k: _Proc(0, "1 passed\n"))


# ---- 結果の写し（guard の形 → results/）の照合 ------------------------------------------------------------

def test_results_copy_is_verified_byte_for_byte(repo, tmp_path, monkeypatch) -> None:
    import shutil
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    _exec(repo, out, GUARD_SEEDS[:2])
    (out / AN.REPORT).write_text(json.dumps({"measurement_commit": _git(repo, "rev-parse", "HEAD")}), encoding="utf-8")

    def copy_to(name: str) -> Path:
        dst = tmp_path / name
        shutil.copytree(out, dst, ignore=shutil.ignore_patterns(R.G.LOCK))
        return dst
    assert AN.verify_results_copy(out, copy_to("ok")) == []
    swap = copy_to("swap")
    a, b = (R.G.seed_dir(swap, s) / R.G.RAW for s in GUARD_SEEDS[:2])
    da, db = a.read_bytes(), b.read_bytes()
    a.write_bytes(db)
    b.write_bytes(da)
    assert AN.verify_results_copy(out, swap)
    gone = copy_to("gone")
    (R.G.seed_dir(gone, GUARD_SEEDS[1]) / R.G.RAW).unlink()
    assert AN.verify_results_copy(out, gone)
    extra = copy_to("extra")
    (extra / "note.txt").write_text("x", encoding="utf-8")
    assert AN.verify_results_copy(out, extra)
    rep = copy_to("rep")
    (rep / AN.REPORT).write_text(json.dumps({"measurement_commit": "0" * 40}), encoding="utf-8")
    assert AN.verify_results_copy(out, rep)
