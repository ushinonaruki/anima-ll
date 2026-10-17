"""実験 0022 の道具の契約テスト（確定した事前登録 v0.2 の README §2〜§7）。

本番の seed（15001〜15100）は使わない（実行もしない）。合成・確認専用の範囲（15101〜15200）だけを使う。

**都合のよい自然現象を見つけるための seed の走査はしない**（ChatGPT の承認の条件）。分岐の有無を確かめたい場合は、
人工の境界条件を手で作る。作り方は次のとおりで、どれも結果を見て選んだものではない：
- 合成の個体は、範囲の最初の seed 15101 の Birth State（力学の値）を使う。重み・痕跡・Unit の activity・順応だけを手で置き、
  刺激はない。Unit の力学の値（閾値など）・可塑性の規則・Runtime は変えない
- SAME（t_OS なし）：S を O の完全な複製にする
- QUIET（t_OS あり・t_YO と t_YS なし）：全 Unit の順応を 1.0 にして窓（120 Pulse）の間黙らせ、S の 1 つの Unit だけを
  Pulse 1 に発火させる。痕跡はすべて 0 なので、どの腕でも重みは変わらない（どの更新も相手の痕跡 0 を掛ける）
- TUNED（t_YO ＝ t_OS ＋ 2 ちょうど）：S の送り手だけを Pulse 1 に発火させ（t_OS ＝ 1）、O の送り手を Pulse 2 に発火させ、
  O の受け手の Pulse 3 の activity を、O の駆動 w0 と Y_O_from_S の駆動 w0·(1 − a／w_max·y) のちょうど間に閾値が来るように
  置く。送り手・受け手・黙らせる Unit は、Birth State の値 a* − θ の大きい順という規則で決める（seed 15101 の値で成り立つ
  ことを、走らせる前に式で確かめる）。S の重み・痕跡は O と違う値にして、P の恒等式・痕跡の差の減り方を 0 でない差で確かめる
- 実物の手順の通しの確認：15200（範囲の最後。操作の確認だけ。観測の量は計算・表示・確認しない）

使った合成の seed（PR に開示）：15101（人工の境界条件）、15200（実物の手順の通しの確認）、15101〜15110（並列数のテストの
時刻だけ・計算なし）、15101・15102（guard のテストの dummy runner・計算なし）、15199（meta の改ざんの値・計算なし）。
"""

import copy
import gzip
import importlib.util
import json
import math
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments" / "0022_natural_history_yoke"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))
SYN, CHECK_SEED = 15101, 15200
SAME, QUIET, TUNED = "SAME", "QUIET", "TUNED"
WINDOW = {SAME: 600, QUIET: 120, TUNED: 600}
A_CONTROL = (0.006, -0.004, 0.0)        # (a_AB, a_AC, a_BC)：組の和 ＝ w_max のまま w ＝ (w_max ± a)／2
A_OTHER = (-0.006, 0.004, 0.002)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W = _load("world_0022_test", EXP / "world.py")
G = _load("guard_0022_test", EXP / "guard.py")
SPEC = W.plasticity(PROTOCOL)
W_MAX = SPEC.w_max
RATIO = SPEC.amplitude / SPEC.w_max
KAPPA = math.exp(-1.0 / SPEC.trace_tau_seconds)


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)


@pytest.fixture(scope="module")
def A():
    return _load("analyze_0022_test", EXP / "analyze.py")


# ---- 人工の境界条件の組み立て ----------------------------------------------------------------------------

def _app(seed: int = SYN):
    log = W.ExperimentLog()
    app = W.build(PROTOCOL, "ordered", seed, log)
    for receptor in app.receptors.values():
        receptor._pulses.clear()
    return app, log, W.role_units(PROTOCOL, seed)


def _set_weights(app, u, a) -> None:
    state = app.connections.export_state()
    for (x, y), v in zip(((u["A"], u["B"]), (u["A"], u["C"]), (u["B"], u["C"])), a):
        state[W.connection_id(x, y)]["weight"] = (W_MAX + v) / 2
        state[W.connection_id(y, x)]["weight"] = (W_MAX - v) / 2
    app.connections.import_state(state)


def _set_traces(app, trace: dict) -> None:
    """Unit ごとの痕跡（接続 i→j の pre_trace は i の痕跡、post_trace は j の痕跡）。"""
    state = app.connections.export_state()
    for cid, v in state.items():
        src, dst = W.unit_of(cid)
        v["pre_trace"], v["post_trace"] = trace[src], trace[dst]
    app.connections.import_state(state)


def _set_unit(app, uid: str, activity: float, adaptation: float) -> None:
    unit = next(x for x in app.units.all() if x.unit_id == uid)
    s = unit.export_state()
    s["activity"], s["adaptation"] = activity, adaptation
    unit.import_state(s)


def _dyn(app) -> dict:
    return {x.unit_id: x.export_state()["dynamics"] for x in app.units.all()}


def _tuning_roles(app) -> tuple[str, str, str]:
    """受け手・送り手・黙らせる Unit を、Birth State の値 a* − θ（a* ＝ c／(1 − λ)）の大きい順で決める（規則。結果を見ない）。"""
    d = _dyn(app)
    g = {uid: v["intrinsic_drive_per_second"] / (1 - v["decay_per_second"]) - v["threshold"] for uid, v in d.items()}
    j, i, k = sorted(g, key=lambda x: (-g[x], x))
    return j, i, k


def _eight(O, Ol, S, Sl, n: int, every: int = 60) -> dict:
    """0022 と同じ手順を合成の状態で：自然な 2 個体 O・S から 6 腕を複製し、8 腕を並べて進める（Pulse 0 から n まで）。"""
    arms = W.fork_arms((O, Ol), (S, Sl))
    fork = {k: W.snapshot(app) for k, (app, _) in arms.items()}
    fork_in_flight = {k: W.in_flight(app) for k, (app, _) in arms.items()}
    yokes, audits = W.wrap_arms(arms)
    res = W.run_arms(arms, yokes, 0, n, every, audits)
    ends = {k: W.snapshot(app) for k, (app, _) in arms.items()}
    u = W.role_units(PROTOCOL, SYN)
    return {"seed": SYN, "roles": {"units": u}, "arms": res, "fork": fork, "fork_in_flight": fork_in_flight,
            "endpoints": ends}


def _same(n: int = WINDOW[SAME]) -> dict:
    O, Ol, u = _app()
    _set_weights(O, u, A_CONTROL)
    for x in O.units.all():
        _set_unit(O, x.unit_id, 0.0, 0.0)
    S, Sl = W.clone(O, Ol)
    return _eight(O, Ol, S, Sl, n)


def _quiet(n: int = WINDOW[QUIET]) -> dict:
    O, Ol, _ = _app()
    for x in O.units.all():
        _set_unit(O, x.unit_id, 0.0, 1.0)
    S, Sl = W.clone(O, Ol)
    j, _, _ = _tuning_roles(S)
    d = _dyn(S)[j]
    _set_unit(S, j, (d["threshold"] + 0.01 - d["intrinsic_drive_per_second"]) / d["decay_per_second"], 0.0)
    return _eight(O, Ol, S, Sl, n)


def _tuned_values(app) -> dict:
    """TUNED の初めの activity を式で決める（走らせる前に、成り立つ条件も式で確かめる）。"""
    j, i, k = _tuning_roles(app)
    d = _dyn(app)
    lam_i, c_i, th_i = d[i]["decay_per_second"], d[i]["intrinsic_drive_per_second"], d[i]["threshold"]
    lam_j, c_j, th_j = d[j]["decay_per_second"], d[j]["intrinsic_drive_per_second"], d[j]["threshold"]
    w0 = W_MAX / 2
    # 送り手 i：Pulse 1 には発火せず、Pulse 2 に発火する（駆動なし）。c − (1 − λ)θ ＞ 0 が要る
    room = c_i - (1 - lam_i) * th_i
    assert room > 0, "送り手の a* が閾値より低い（この Birth State では TUNED を作れない）"
    delta = 0.5 * room / lam_i
    a1_i = th_i - delta
    a0_i = (a1_i - c_i) / lam_i
    # 受け手 j：Pulse 3 に、O では w0、Y_O_from_S では w0·(1 − a／w_max·1) の駆動が送り手から届く。閾値をその間に置く
    gap = w0 * (1 - RATIO / 2)
    a2_j = (th_j - gap - c_j) / lam_j
    a1_j = (a2_j - c_j) / lam_j
    a0_j = (a1_j - c_j) / lam_j
    assert lam_j * a0_j + c_j < th_j and lam_j * a1_j + c_j < th_j, "受け手が Pulse 1・2 に発火してしまう"
    a0_i_s = (th_i + 0.01 - c_i) / lam_i                 # S の送り手：Pulse 1 に発火する
    return {"i": i, "j": j, "k": k, "a0_i": a0_i, "a0_j": a0_j, "a0_i_s": a0_i_s}


def _tuned(n: int = WINDOW[TUNED]) -> dict:
    O, Ol, u = _app()
    v = _tuned_values(O)
    _set_traces(O, {x.unit_id: 1.0 for x in O.units.all()})
    _set_unit(O, v["k"], 0.0, 1.0)
    _set_unit(O, v["i"], v["a0_i"], 0.0)
    _set_unit(O, v["j"], v["a0_j"], 0.0)
    S, Sl = W.clone(O, Ol)
    _set_unit(S, v["i"], v["a0_i_s"], 0.0)
    _set_weights(S, u, A_OTHER)                                       # δω ≠ 0
    _set_traces(S, {v["i"]: 2.0, v["j"]: 0.5, v["k"]: 3.0})           # ΔX ≠ 0
    run = _eight(O, Ol, S, Sl, n)
    run["tuned"] = v
    return run


@pytest.fixture(scope="module")
def cases():
    return {SAME: _same(), QUIET: _quiet(), TUNED: _tuned()}


def _before(run) -> dict:
    """合成の個体：0 より前の伝達はないので、t0 − 1 の重みは t0 の重みと同じとして渡す。"""
    return {nat: {c: v["weight"] for c, v in run["fork"][nat]["connections"].items()} for nat in ("O", "S")}


def _arms_problems(A, run, n=None) -> dict:
    n = n if n is not None else int(max(run["arms"]["samples"]["O"], key=int))
    out = {k: [] for k in A.CHECK_NAMES}
    A.check_arms(run, out, 0, n, _before(run))
    return {k: v for k, v in out.items() if v}


def _fd(A, run, a, b):
    return A.first_difference(run["arms"]["spikes"][a], run["arms"]["spikes"][b])


# ---- protocol との整合 -------------------------------------------------------------------------------------

def test_protocol_and_tools_are_aligned() -> None:
    _load("alignment_0022_test", EXP / "alignment.py").check(PROTOCOL)
    syn = range(PROTOCOL["synthetic_seeds"]["first"], PROTOCOL["synthetic_seeds"]["last"] + 1)
    assert SYN in syn and CHECK_SEED in syn


def test_tuned_construction_is_feasible_by_formula_before_running() -> None:
    """TUNED の初めの値は式だけで決まり、送り手・受け手の条件（発火する Pulse）を走らせる前に満たす。"""
    O, _, _ = _app()
    v = _tuned_values(O)
    d = _dyn(O)
    i = v["i"]
    ai1 = d[i]["decay_per_second"] * v["a0_i"] + d[i]["intrinsic_drive_per_second"]
    ai2 = d[i]["decay_per_second"] * ai1 + d[i]["intrinsic_drive_per_second"]
    assert ai1 < d[i]["threshold"] <= ai2
    assert len({v["i"], v["j"], v["k"]}) == 3


# ---- 人工の境界条件が意図した構造になっていること -------------------------------------------------------------

def test_constructed_cases_have_the_intended_structure(A, cases) -> None:
    same, quiet, tuned = cases[SAME], cases[QUIET], cases[TUNED]
    assert _fd(A, same, "O", "S") is None
    assert A.category(A.record_run(same, 0, WINDOW[SAME])) == "a_no_t_OS"
    assert _fd(A, quiet, "O", "S")[0] == 1
    assert A.category(A.record_run(quiet, 0, WINDOW[QUIET])) == "b_t_OS_without_t_YO_t_YS"
    v = tuned["tuned"]
    assert _fd(A, tuned, "O", "S") == (1, [v["i"]])
    assert _fd(A, tuned, "O", "Y_O_from_S") == (3, [v["j"]])                 # t_YO ＝ t_OS ＋ 2 ちょうど
    assert v["j"] in A.spikes_at(tuned["arms"]["spikes"]["O"], 3)              # 駆動の大きい O の側で発火した
    # TUNED の t_YS は作り方の対象外（どちらでもよい。ここでは確かめない）


@pytest.mark.parametrize("name", [SAME, QUIET, TUNED])
def test_all_arm_checks_pass_on_constructed_runs(A, cases, name) -> None:
    assert _arms_problems(A, cases[name]) == {}


def test_category_covers_the_five_structural_cases(A) -> None:
    def rec(t_os, t_yo, t_ys):
        return {"t_OS": t_os, "t_YO": t_yo, "t_YS": t_ys}
    assert A.category(rec(None, None, None)) == "a_no_t_OS"
    assert A.category(rec(5, None, None)) == "b_t_OS_without_t_YO_t_YS"
    assert A.category(rec(5, 9, None)) == "c_t_YO_only"
    assert A.category(rec(5, None, 9)) == "d_t_YS_only"
    assert A.category(rec(5, 9, 12)) == "e_t_YO_and_t_YS"
    assert set(A.CATEGORIES) == {"a_no_t_OS", "b_t_OS_without_t_YO_t_YS", "c_t_YO_only", "d_t_YS_only", "e_t_YO_and_t_YS"}


# ---- 複製（t0 の全状態、次の Pulse に届く駆動まで）----------------------------------------------------------

def test_fork_copies_full_state_including_in_flight_drive() -> None:
    """複製は、Unit の状態・接続の状態に加えて、次の Pulse に届く駆動まで基準と同じ。駆動がある時点で分けて確かめる。"""
    O, Ol, _ = _app()
    for x in O.units.all():
        _set_unit(O, x.unit_id, 0.0, 1.0)
    S, Sl = W.clone(O, Ol)
    j, _, _ = _tuning_roles(S)
    d = _dyn(S)[j]
    _set_unit(S, j, (d["threshold"] + 0.01 - d["intrinsic_drive_per_second"]) / d["decay_per_second"], 0.0)
    W.advance_to(O, 1)
    W.advance_to(S, 1)                                                         # S の j が Pulse 1 に発火 → 駆動が届く途中
    arms = W.fork_arms((O, Ol), (S, Sl))
    assert W.in_flight(S)["drives"], "駆動が届く途中の時点で確かめる"
    for name, (app, _) in arms.items():
        base = arms[W.BASE[name]][0]
        assert W.snapshot(app) == W.snapshot(base) and W.in_flight(app) == W.in_flight(base)
        if name not in W.NATURAL:
            assert app is not base and app.connections is not base.connections


@pytest.mark.parametrize("name", [SAME, QUIET, TUNED])
def test_twin_and_self_yokes_equal_their_bases_exactly(cases, name) -> None:
    run = cases[name]
    for arm, base in (("twin_O", "O"), ("twin_S", "S"), ("Y_O_from_O", "O"), ("Y_S_from_S", "S")):
        assert run["arms"]["spikes"][arm] == run["arms"]["spikes"][base]
        assert run["arms"]["samples"][arm] == run["arms"]["samples"][base]
        assert run["endpoints"][arm] == run["endpoints"][base]


# ---- yoke（README §2）---------------------------------------------------------------------------------

def test_yoke_passes_partner_firing_only_to_plasticity(A, cases) -> None:
    """Y_O_from_S の可塑性は S の発火の列で（出来事と痕跡の更新）、痕跡の初めの値は O の t0 の値。Unit・伝達は自分の重み。"""
    run = cases[TUNED]
    sp, ends, fork = run["arms"]["spikes"], run["endpoints"], run["fork"]
    n = WINDOW[TUNED]
    assert fork["Y_O_from_S"]["connections"] == fork["O"]["connections"] != fork["S"]["connections"]
    by_partner = A.replay_arm(run, "Y_O_from_S", (), 0, n)
    assert all(by_partner[c]["end"] == ends["Y_O_from_S"]["connections"][c] for c in by_partner)   # ビット単位で一致
    own = W.fired_by_pulse(sp["Y_O_from_S"])
    by_own = {c: W.replay(st, c, own, 0, n, SPEC, 1.0) for c, st in fork["Y_O_from_S"]["connections"].items()}
    assert any(by_own[c]["end"] != ends["Y_O_from_S"]["connections"][c] for c in by_own)
    s_from_o = A.replay_arm(run, "Y_S_from_O", (), 0, n)                                         # 逆向きも
    assert all(s_from_o[c]["end"] == ends["Y_S_from_O"]["connections"][c] for c in s_from_o)
    assert sp["Y_O_from_S"] != sp["S"]                                         # 活動は自分（O から始まる）の状態・重みで進む


def test_natural_arms_receive_nothing_from_the_yoke(cases) -> None:
    """O・S は発火の集合を渡すだけ。twin（包まない複製）と完全に一致することで確かめる。"""
    for name in (QUIET, TUNED):
        run = cases[name]
        assert run["arms"]["spikes"]["O"] == run["arms"]["spikes"]["twin_O"]
        assert run["arms"]["spikes"]["S"] == run["arms"]["spikes"]["twin_S"]
        assert run["endpoints"]["O"] == run["endpoints"]["twin_O"] and run["endpoints"]["S"] == run["endpoints"]["twin_S"]


def test_yoke_contract_errors() -> None:
    """渡し忘れ・Pulse 番号の違い・二重の渡し・相手をまだ進めていない（None）は YokeError（黙って自分の発火で更新しない）。"""
    app, _, _ = _app()
    y = W.make_yoked(app)
    assert app.pulse_runtime._connections is y and app.connections is y.inner      # 本物は app.connections のまま
    with pytest.raises(W.YokeError, match="渡されていない"):
        W.advance_to(app, 1)
    app2, _, _ = _app()
    y2 = W.make_yoked(app2)
    y2.provide(2, set())
    with pytest.raises(W.YokeError, match="Pulse"):
        W.advance_to(app2, 1)
    app3, _, _ = _app()
    y3 = W.make_yoked(app3)
    y3.provide(1, set())
    with pytest.raises(W.YokeError, match="まだ使われていない"):
        y3.provide(1, set())
    app4, _, _ = _app()
    y4 = W.make_yoked(app4)
    with pytest.raises(W.YokeError, match="相手の個体をまだ進めていない"):
        y4.provide(1, None)


def test_yoke_uses_each_partner_set_exactly_once_per_pulse(cases) -> None:
    """各 Pulse に渡す集合は、同じ Pulse の相手の発火そのもの（契約の包みを記録用に包んで確かめる）。"""
    O, Ol, _ = _app()
    v = _tuned_values(O)
    _set_traces(O, {x.unit_id: 1.0 for x in O.units.all()})
    _set_unit(O, v["k"], 0.0, 1.0)
    _set_unit(O, v["i"], v["a0_i"], 0.0)
    _set_unit(O, v["j"], v["a0_j"], 0.0)
    S, Sl = W.clone(O, Ol)
    _set_unit(S, v["i"], v["a0_i_s"], 0.0)
    arms = W.fork_arms((O, Ol), (S, Sl))
    yokes, audits = W.wrap_arms(arms)
    seen: dict[str, list] = {name: [] for name in yokes}
    for name, y in yokes.items():
        inner = y.inner

        class Spy:
            def __init__(self, inner, name):
                self._inner, self._name = inner, name

            def apply_activity(self, fired, dt):
                seen[self._name].append(frozenset(fired))
                self._inner.apply_activity(fired, dt)

            def __getattr__(self, attr):
                return getattr(self._inner, attr)

        y.inner = Spy(inner, name)
    res = W.run_arms(arms, yokes, 0, 40, 20, audits)
    fired = {nat: W.fired_by_pulse(res["spikes"][nat]) for nat in ("O", "S")}
    for name in yokes:
        src = W.SOURCE[name]
        assert seen[name] == [frozenset(fired[src].get(t, set())) for t in range(1, 41)], name


def test_run_arms_refuses_a_wrong_setup(cases) -> None:
    O, Ol, _ = _app()
    S, Sl = W.clone(O, Ol)
    arms = W.fork_arms((O, Ol), (S, Sl))
    yokes, audits = W.wrap_arms(arms)
    reordered = dict(reversed(list(arms.items())))
    with pytest.raises(ValueError, match="腕の並び"):
        W.run_arms(reordered, yokes, 0, 5, 5, audits)
    with pytest.raises(ValueError, match="yoke する腕"):
        W.run_arms(arms, {k: v for k, v in yokes.items() if k != "Y_O_from_S"}, 0, 5, 5, audits)
    with pytest.raises(ValueError, match="監査する腕"):
        W.run_arms(arms, yokes, 0, 5, 5, {k: v for k, v in audits.items() if k != "O"})
    W.advance_to(arms["twin_S"][0], 1)
    with pytest.raises(ValueError, match="まで進んでいること"):
        W.run_arms(arms, yokes, 0, 5, 5, audits)


def test_runtime_core_is_not_yoked_for_natural_arms_and_twins(cases) -> None:
    O, Ol, _ = _app()
    S, Sl = W.clone(O, Ol)
    arms = W.fork_arms((O, Ol), (S, Sl))
    W.wrap_arms(arms)
    for name, (app, _) in arms.items():
        kind = type(app.pulse_runtime._connections).__name__
        assert kind == ("YokedConnections" if name in W.YOKED else "ConnectionStore"), name
    assert all(type(x._dynamics).__name__ == "AuditedDynamics" for x in arms["Y_O_from_S"][0].units.all())
    assert all(type(x._dynamics).__name__ != "AuditedDynamics" for x in arms["twin_O"][0].units.all())


# ---- t_OS・t_YO と設計から決まる性質（命題 4.9、README §3.2）----------------------------------------------------

def test_yoke_equals_base_until_t_OS_plus_1_and_the_bound(A, cases) -> None:
    run = cases[TUNED]
    sp = run["arms"]["spikes"]
    t_os, t_yo = _fd(A, run, "O", "S")[0], _fd(A, run, "O", "Y_O_from_S")[0]
    assert [x for x in sp["O"] if x[0] <= t_os + 1] == [x for x in sp["Y_O_from_S"] if x[0] <= t_os + 1]
    assert t_yo >= t_os + 2
    ro, ry = A.replay_arm(run, "O", range(t_yo), 0, WINDOW[TUNED]), A.replay_arm(run, "Y_O_from_S", range(t_yo), 0, WINDOW[TUNED])
    for m in range(t_yo):
        same = all(ro[c]["at"][m] == ry[c]["at"][m] for c in ro)
        assert same == (m <= t_os - 1), m                                    # 接続の状態が分かれるのは t_OS の終わりから
    after = run["arms"]["t_OS"]["after"]
    for k in ("t", "t+1"):
        assert after[k]["O"]["units"] == after[k]["Y_O_from_S"]["units"]      # Unit の状態は t_OS ＋ 1 まで同じ
    quiet = cases[QUIET]
    assert _fd(A, quiet, "O", "Y_O_from_S") is None and _fd(A, quiet, "S", "Y_S_from_O") is None
    same = cases[SAME]
    for base, yoke in W.PAIRS.values():
        assert same["arms"]["spikes"][base] == same["arms"]["spikes"][yoke]
        assert same["endpoints"][base] == same["endpoints"][yoke]


def test_reconstruction_at_t0_plus_1_uses_the_firing_at_t0(A) -> None:
    """t_OS ＝ t0 ＋ 1 のとき、判定の再構成は t0 の発火（W の発火の列には入らない。経験の記録から読む）の駆動を含める。
    人工の境界条件：t0 ＝ 1 に送り手が両方の個体で発火し、t0 ＋ 1 ＝ 2 に受け手が S でだけ発火するように activity を置く。"""
    O, Ol, u = _app()
    j, i, k = _tuning_roles(O)
    d = _dyn(O)
    w0 = W_MAX / 2
    _set_unit(O, k, 0.0, 1.0)
    _set_unit(O, i, (d[i]["threshold"] + 0.01 - d[i]["intrinsic_drive_per_second"]) / d[i]["decay_per_second"], 0.0)
    lam, c, th = d[j]["decay_per_second"], d[j]["intrinsic_drive_per_second"], d[j]["threshold"]
    a1 = {"O": (th - 0.002 - c - w0) / lam, "S": (th + 0.002 - c - w0) / lam}
    assert all(lam * x + c < th for x in a1.values())                       # Pulse 2 の前の値は閾値より下
    S, Sl = W.clone(O, Ol)
    _set_unit(O, j, (a1["O"] - c) / lam, 0.0)
    _set_unit(S, j, (a1["S"] - c) / lam, 0.0)
    W.advance_to(O, 1)
    W.advance_to(S, 1)
    assert [x for _, x in Ol.activity()] == [i] == [x for _, x in Sl.activity()]   # t0 ＝ 1 の発火は両方で送り手だけ
    before = {"O": {cc: v["weight"] for cc, v in O.connections.export_state().items()},
              "S": {cc: v["weight"] for cc, v in S.connections.export_state().items()}}   # 痕跡 0 なので Pulse 1 で重みは不変
    arms = W.fork_arms((O, Ol), (S, Sl))
    fork = {name: W.snapshot(app) for name, (app, _) in arms.items()}
    fork_in_flight = {name: W.in_flight(app) for name, (app, _) in arms.items()}
    yokes, audits = W.wrap_arms(arms)
    res = W.run_arms(arms, yokes, 1, 60, 20, audits)
    run = {"seed": SYN, "roles": {"units": u}, "arms": res, "fork": fork, "fork_in_flight": fork_in_flight,
           "endpoints": {name: W.snapshot(app) for name, (app, _) in arms.items()},
           "conditions": {"ordered": {"activity": Ol.activity()}, "shuffled": {"activity": Sl.activity()}}}
    assert res["t_OS"]["pulse"] == 2 and res["t_OS"]["units"] == [j]
    out = {name: [] for name in A.CHECK_NAMES}
    A.check_arms(run, out, 1, 60, before)
    assert {name: v for name, v in out.items() if v} == {}
    bad = copy.deepcopy(run)
    bad["conditions"]["shuffled"]["activity"] = [x for x in bad["conditions"]["shuffled"]["activity"] if x[0] != 1]
    out = {name: [] for name in A.CHECK_NAMES}
    A.check_arms(bad, out, 1, 60, before)
    assert out["divergence_activity_reconstruction"] and out["divergence_decisions_reconstructed"]


def test_t_OS_at_the_last_pulse_has_no_after_record(A) -> None:
    """t_OS ＝ T のとき、t ＋ 1 の記録はなく、確認はそれを欠落として扱わない（D3）。"""
    run = _quiet(n=1)
    assert run["arms"]["t_OS"]["pulse"] == 1 and run["arms"]["t_OS"]["after"]["t+1"] is None
    assert _arms_problems(A, run, 1) == {}


def test_trace_difference_decays_as_a_kappa_power(A, cases) -> None:
    """命題 4.1：同じ発火で更新した痕跡の差は κ^(t−t0)·ΔX(t0)。TUNED では ΔX ≠ 0 にしてある。"""
    run = cases[TUNED]
    n = WINDOW[TUNED]
    times = list(range(n + 1))
    for yoke in ("Y_O_from_S", "Y_S_from_O"):
        partner, base = W.SOURCE[yoke], W.BASE[yoke]
        ry, rp = A.replay_arm(run, yoke, times, 0, n), A.replay_arm(run, partner, times, 0, n)
        nonzero = False
        for cid in ry:
            for f in ("pre_trace", "post_trace"):
                dx = run["fork"][base]["connections"][cid][f] - run["fork"][partner]["connections"][cid][f]
                nonzero |= dx != 0
                for t in times:
                    assert abs((ry[cid]["at"][t][f] - rp[cid]["at"][t][f]) - KAPPA ** t * dx) < 1e-14
        assert nonzero


def test_P_identity_holds_with_nonzero_initial_differences(A, cases) -> None:
    """命題 4.3：P ＝ Φ^B·δω ＋ T^B。TUNED では δω ≠ 0・ΔX ≠ 0（痕跡の差の項 T が効く）。改ざんは検出する。"""
    run = cases[TUNED]
    n = WINDOW[TUNED]
    at = sorted(int(t) for t in run["arms"]["samples"]["O"])
    fo, fs = run["fork"]["O"]["connections"], run["fork"]["S"]["connections"]
    assert any(fo[c]["weight"] != fs[c]["weight"] for c in fo) and any(fo[c]["pre_trace"] != fs[c]["pre_trace"] for c in fo)
    for yoke in ("Y_O_from_S", "Y_S_from_O"):
        assert A.p_identity(run, yoke, 0, n, at) == []
    bad = copy.deepcopy(run)
    cid = next(iter(bad["endpoints"]["Y_S_from_O"]["connections"]))
    bad["endpoints"]["Y_S_from_O"]["connections"][cid]["weight"] += 1e-9
    assert A.p_identity(bad, "Y_S_from_O", 0, n, at)


def test_first_difference_contributions_satisfy_the_decomposition_identity(A, cases) -> None:
    """Σ_i K_ij(t_YO) ＝ ã^O − ã^{Y_O_from_S}（README §3.2）。下限は t_OS ＋ 2、TUNED では送り手 1 本の 1 項だけ。"""
    run = cases[TUNED]
    v = run["tuned"]
    fd_os, fd_yo = _fd(A, run, "O", "S"), _fd(A, run, "O", "Y_O_from_S")
    k = A.first_difference_contributions(run, "YO", fd_os, fd_yo, 0, WINDOW[TUNED])
    assert set(k) == {v["j"]}
    c = k[v["j"]]
    assert abs(c["sum"] - c["activity_difference"]) < 1e-12
    assert {s for s, x in c["K"].items() if x != 0} == {v["i"]}               # 寄与が 0 でないのは送り手だけ（ほかは普通の 0）
    assert c["activity_difference"] > 0                                       # 発火した O の側の方が大きい
    assert abs(c["sum"] - (W_MAX / 2) * RATIO) < 1e-15                        # Δw ＝ w0·(a／w_max)·y（y ＝ 1）
    assert A.first_difference_contributions(run, "YO", fd_os, None, 0, WINDOW[TUNED]) is None
    assert A.first_difference_contributions(run, "YO", None, fd_yo, 0, WINDOW[TUNED]) is None


def test_contributions_respect_reset_and_delay(A) -> None:
    """r_j のリセットより前の項は入らない。Δw(k − 2) は送り手が k − 1 に発火したときだけ k に入る。"""
    cid = "s1.main->s2"
    spikes = [[3, "s1"], [5, "s2"], [7, "s1"]]
    diff = lambda m: {cid: 0.001 * m}
    k = A.contributions("s2", 9, 0, spikes, diff, 0.5, 0)
    assert k == {"s1": 0.5 * 0.001 * 6}
    assert A.contributions("s2", 9, 9, spikes, diff, 0.5, 0) == {"s1": 0.0}    # 下限（t_OS ＋ 2）より前の項は入らない（残るのは k ＝ 9 の 0）


# ---- 欠測 null と観測値 0（protocol の observations.missing_values）------------------------------------------

def test_missing_values_are_null_and_real_zeros_are_kept(A, cases) -> None:
    a = A.record_run(cases[SAME], 0, WINDOW[SAME])
    for key in ("t_OS", "U_OS", "detectable_pulses_after_t_OS", "t_YO", "U_YO", "t_YO_minus_t_OS",
                "t_YS", "U_YS", "t_YS_minus_t_OS"):
        assert a[key] is None, key
    assert a["first_difference_contributions"] == {"YO": None, "YS": None}
    assert a["differing_pulses"] == {"O_vs_Y_O_from_S": 0, "S_vs_Y_S_from_O": 0, "O_vs_S": 0}   # 実際の 0（null ではない）
    assert a["last_differing_pulse"] == {"O_vs_Y_O_from_S": None, "S_vs_Y_S_from_O": None, "O_vs_S": None}
    assert all(isinstance(x, int) for arm in a["spike_counts_per_unit"].values() for x in arm.values())
    for key in ("weight_differences_per_connection", "trace_differences_per_connection"):
        assert a[key]["t0"] is not None and a[key]["T"] is not None and a[key]["samples"] == A.SERIES
    assert all(v == 0.0 for c in a["weight_differences_per_connection"]["T"].values() for v in c.values())
    b = A.record_run(cases[QUIET], 0, WINDOW[QUIET])
    assert b["t_OS"] == 1 and b["t_YO"] is None and b["t_YS"] is None
    assert b["detectable_pulses_after_t_OS"] == WINDOW[QUIET] - 1 - 1 > 0           # t_YO・t_YS がなくても 0 にしない
    assert b["t_YO_minus_t_OS"] is None and b["first_difference_contributions"] == {"YO": None, "YS": None}
    assert b["differing_pulses"]["O_vs_S"] > 0 and b["differing_pulses"]["O_vs_Y_O_from_S"] == 0
    assert b["last_differing_pulse"]["O_vs_S"] is not None and b["last_differing_pulse"]["O_vs_Y_O_from_S"] is None
    c = A.record_run(cases[TUNED], 0, WINDOW[TUNED])
    assert c["t_YO_minus_t_OS"] == c["t_YO"] - c["t_OS"] == 2
    assert c["first_difference_contributions"]["YO"] is not None


def test_difference_series_follow_the_definitions_at_every_sample(A, cases) -> None:
    """標本ごとの重みの差・痕跡の差（README §5.2）。t0 では F ＝ 0、P_O ＝ δω、P_S ＝ −δω。接続ごと・時刻ごとに別々。"""
    run = cases[TUNED]
    n = WINDOW[TUNED]
    wd, td = A.weight_and_trace_differences(run, 0, n)
    assert sorted(map(int, wd)) == sorted(int(t) for t in run["arms"]["samples"]["O"]) == sorted(map(int, td))
    for name, v in wd["0"].items():
        assert v["F_O"] == 0.0 and v["F_S"] == 0.0 and v["P_O"] == v["D_nat"] == -v["P_S"]
    u = run["roles"]["units"]
    for t, by_conn in td.items():
        for name, (a, b) in A.CONNECTIONS.items():
            cid = W.connection_id(u[a], u[b])
            st = {arm: A._state_at(run, arm, int(t), n)["connections"][cid] for arm in ("O", "S", "Y_O_from_S", "Y_S_from_O")}
            for f in ("pre_trace", "post_trace"):
                assert by_conn[name][f] == {"natural": st["O"][f] - st["S"][f],
                                            "base_minus_yoke_O": st["O"][f] - st["Y_O_from_S"][f],
                                            "base_minus_yoke_S": st["S"][f] - st["Y_S_from_O"][f]}


def test_formal_main_writes_the_series_next_to_the_report_only_in_its_own_folder(A, tmp_path, monkeypatch) -> None:
    """本番の解析の書き出しの経路だけを確かめる（観測の量は計算しない：解析の関数を差し替える）。"""
    _, own, _ = _fake_data_root(tmp_path, monkeypatch, A)
    monkeypatch.setattr(A.ALIGN, "check", lambda protocol: None)
    monkeypatch.setattr(A, "analyze_folder", lambda folder, mode: {"valid": False, "problems": [], "individuals": {},
                                                                   "mode": mode, "per_seed": {}, "summary": {}})
    monkeypatch.setattr(A, "read", lambda path: {"runs": []})
    monkeypatch.setattr(A, "difference_series", lambda data: {"dummy": True})
    monkeypatch.setattr("sys.argv", ["analyze.py"])
    A.main()
    assert sorted(p.name for p in own.iterdir()) == sorted([A.REPORT, A.SERIES, A.LOG])
    assert json.loads(gzip.decompress((own / A.SERIES).read_bytes())) == {"dummy": True}
    report = json.loads((own / A.REPORT).read_text(encoding="utf-8"))
    assert report["artifacts"] == {A.SERIES: {"sha256": G.sha256_file(own / A.SERIES), "bytes": (own / A.SERIES).stat().st_size}}
    assert [e["event"] for e in A.read_log(own)] == ["started", "written", "written", "completed"]
    assert A.verify_artifacts(own, "formal") == {"problems": [], "notes": []}
    monkeypatch.setattr("sys.argv", ["analyze.py"])
    with pytest.raises(SystemExit, match="上書きしない"):
        A.main()


def test_distribution_excludes_nulls_and_reports_their_count(A) -> None:
    d = A._describe([None, 3, None, 5, 7])
    assert d == {"n": 3, "null": 2, "median": 5, "min": 3, "max": 7}
    assert A._describe([None, None]) == {"n": 0, "null": 2, "median": None, "min": None, "max": None}


def test_record_keys_match_the_preregistered_observations(A, cases) -> None:
    rec = A.record_run(cases[TUNED], 0, WINDOW[TUNED])
    obs = PROTOCOL["observations"]
    names = [k if isinstance(k, str) else next(iter(k)) for k in obs["primary"] + obs["secondary"]]
    assert set(rec) == set(names) - {"full_trains"}                       # 全発火の列は生の記録
    # #90 の定義のまま（F_O は基準 − yoke、F_S は yoke − 基準）。T の値を端点から計算し直して照合する
    u = cases[TUNED]["roles"]["units"]
    ends = cases[TUNED]["endpoints"]
    for name, (a, b) in A.CONNECTIONS.items():
        cid = W.connection_id(u[a], u[b])
        w = {arm: ends[arm]["connections"][cid]["weight"] for arm in ("O", "S", "Y_O_from_S", "Y_S_from_O")}
        got = rec["weight_differences_per_connection"]["T"][name]
        assert got == {"D_nat": w["O"] - w["S"], "F_O": w["O"] - w["Y_O_from_S"], "P_O": w["Y_O_from_S"] - w["S"],
                       "F_S": w["Y_S_from_O"] - w["S"], "P_S": w["Y_S_from_O"] - w["O"]}
    assert set(rec["trace_differences_per_connection"]["T"]["AB"]["pre_trace"]) == {"natural", "base_minus_yoke_O", "base_minus_yoke_S"}


def test_summary_counts_and_describes_only(A, cases) -> None:
    per = {str(i): A.record_run(cases[k], 0, WINDOW[k]) for i, k in enumerate((SAME, QUIET, TUNED))}
    individuals = {s: {"valid": True, "failed_checks": {}} for s in per}
    s = A.summarize(per, individuals, start=0)
    assert s["categories"]["a_no_t_OS"]["count"] == 1 and s["categories"]["b_t_OS_without_t_YO_t_YS"]["count"] == 1
    assert s["t_OS_minus_t0"] == {"n": 2, "null": 1, "median": 1.0, "min": 1, "max": 1}
    forbidden = ("holds", "fails", "ratio", "rate", "threshold", "interval", "score", "amplif")
    assert not any(w in json.dumps(s) for w in forbidden)


# ---- 改ざん・不整合の検出（生の記録からの再検証）-------------------------------------------------------------

def _mutated(A, run, mutate) -> dict:
    bad = copy.deepcopy(run)
    mutate(bad)
    return _arms_problems(A, bad)


def test_arm_checks_detect_tampering(A, cases) -> None:
    run = cases[TUNED]
    v = run["tuned"]
    n = WINDOW[TUNED]
    cid = W.connection_id(v["i"], v["j"])
    t_yo = run["arms"]["t_YO"]["pulse"]
    ts = "120"
    cases_ = [
        (lambda b: b["arms"]["spikes"]["twin_O"].append([n, v["k"]]), "twin_O_equals_O"),
        (lambda b: b["endpoints"]["twin_S"]["connections"][cid].__setitem__("pre_trace", 9.0), "twin_S_equals_S"),
        (lambda b: b["arms"]["samples"]["Y_O_from_O"][ts]["units"][v["j"]].__setitem__("activity", 0.1), "self_yoke_O_equals_O"),
        (lambda b: b["endpoints"]["Y_S_from_S"]["connections"][cid].__setitem__("post_trace", 9.0), "self_yoke_S_equals_S"),
        (lambda b: b["fork"]["Y_O_from_S"]["connections"][cid].__setitem__("pre_trace", 0.5), "fork_is_clone"),
        (lambda b: b["fork_in_flight"]["twin_S"]["drives"].append([v["i"], v["j"], 0.005, 0]), "fork_is_clone"),
        (lambda b: b["arms"]["spikes"]["Y_O_from_S"].insert(0, [2, v["k"]]), "yoke_equals_base_until_t_OS_plus_1"),
        (lambda b: b["arms"]["t_OS"]["after"]["t+1"]["Y_O_from_S"]["units"][v["k"]].__setitem__("activity", 0.3),
         "yoke_equals_base_until_t_OS_plus_1"),
        (lambda b: b["arms"]["samples"]["Y_O_from_S"][ts]["connections"][cid].__setitem__(
            "pre_trace", b["arms"]["samples"]["Y_O_from_S"][ts]["connections"][cid]["pre_trace"] + 1e-9), "trace_difference_decay"),
        (lambda b: b["arms"]["samples"]["Y_O_from_S"][ts]["connections"][cid].__setitem__(
            "weight", b["arms"]["samples"]["Y_O_from_S"][ts]["connections"][cid]["weight"] + 1e-9), "P_identity"),
        (lambda b: b["endpoints"]["S"]["connections"][cid].__setitem__(
            "weight", b["endpoints"]["S"]["connections"][cid]["weight"] + 1e-9), "plasticity_replay_W"),
        (lambda b: b["endpoints"]["twin_O"]["connections"][cid].__setitem__("weight", W_MAX * 2), "no_clipping"),
        (lambda b: b["endpoints"]["O"]["connections"][cid].__setitem__(
            "weight", b["endpoints"]["O"]["connections"][cid]["weight"] + 1e-9), "pair_sum"),
        (lambda b: b["arms"]["t_YO"].__setitem__("pulse", t_yo + 1), "revalidate_from_raw"),
        (lambda b: b["arms"]["t_YO"].__setitem__("units", ["s9"]), "revalidate_from_raw"),
        (lambda b: b["arms"]["t_OS"]["spikes"]["t"]["S"].append([1, "s9"]), "revalidate_from_raw"),
        (lambda b: b["arms"]["t_OS"]["spikes_after"]["t+1"]["O"].append([2, "s9"]), "revalidate_from_raw"),
        (lambda b: b["arms"]["t_YO"]["before"]["t-2"]["Y_O_from_S"]["connections"][cid].__setitem__("weight", 0.004),
         "revalidate_from_raw"),
        (lambda b: b["arms"].__setitem__("t_OS", None), "revalidate_from_raw"),
        (lambda b: b["arms"]["t_YO"]["before"]["t-1"]["Y_O_from_S"]["units"][v["i"]].__setitem__(
            "activity", b["arms"]["t_YO"]["before"]["t-1"]["Y_O_from_S"]["units"][v["i"]]["activity"] + 1e-9),
         "divergence_activity_reconstruction"),
        (lambda b: b["arms"]["t_YO"]["audit"]["O"][v["j"]].__setitem__(
            "activity_pre", b["arms"]["t_YO"]["audit"]["O"][v["j"]]["activity_pre"] + 1e-9), "divergence_activity_reconstruction"),
        (lambda b: b["arms"]["sensory"]["Y_S_from_O"].append([5, "receptor.x1"]), "input_free_after_experience"),
    ]
    for mutate, name in cases_:
        assert name in _mutated(A, run, mutate), name


def test_decision_reconstruction_detects_a_wrong_firing(A, cases) -> None:
    """分岐の Pulse の判定の再構成：t_OS（O・S）で、判定に効く t − 1 の状態を変えると、判定が実際の発火と合わなくなる。"""
    run = cases[TUNED]
    v = run["tuned"]
    got = _mutated(A, run, lambda b: b["fork"]["S"]["units"][v["i"]].__setitem__("activity", 0.0))   # t_OS ＝ 1：t − 1 は t0
    assert "divergence_decisions_reconstructed" in got


def test_bound_and_fabrication_checks_detect_violations(A, cases) -> None:
    run = cases[TUNED]
    t_os = run["arms"]["t_OS"]["pulse"]
    got = _mutated(A, run, lambda b: b["arms"]["spikes"]["Y_O_from_S"].append([t_os + 1, "s9"])
                   or b["arms"]["spikes"]["Y_O_from_S"].sort())
    assert "t_Y_at_least_t_OS_plus_2" in got and "yoke_equals_base_until_t_OS_plus_1" in got
    same = cases[SAME]
    got = _mutated(A, same, lambda b: b["arms"].__setitem__("t_YS", {"pulse": 5, "units": ["s1"], "arms": [], "before": {},
                                                                     "spikes": {}}))
    assert "revalidate_from_raw" in got
    got = _mutated(A, same, lambda b: b["arms"]["spikes"]["Y_S_from_O"].append([WINDOW[SAME], "s9"]))
    assert "yoke_equals_base_until_t_OS_plus_1" in got


def test_spike_trains_must_be_well_formed(A, cases) -> None:
    run = cases[SAME]
    for mutate in (lambda b: b["arms"]["spikes"]["O"].append([WINDOW[SAME] + 1, "s1"]),
                   lambda b: b["arms"]["spikes"]["O"].extend([[WINDOW[SAME], "s2"], [WINDOW[SAME], "s2"]])):
        assert "revalidate_from_raw" in _mutated(A, run, mutate)


# ---- 監査の生記録（判定の直前の activity）-----------------------------------------------------------------------

def test_audit_matches_independent_reconstruction_at_every_pulse() -> None:
    """監査の生記録が、t − 1 の状態・t − 2 の重み・t − 1 の発火からの独立な再構成と、300 Pulse すべてで 1e-12 以内に一致する。"""
    app, log, u = _app()
    _set_weights(app, u, A_CONTROL)
    for x in app.units.all():
        _set_unit(app, x.unit_id, 0.0, 0.0)
    sink = W.make_audited(app)
    reader = W._EventReader(log)
    hist, last, checked = [W.snapshot(app)], [], 0
    for t in range(1, 301):
        W.advance_to(app, t)
        now, _ = reader.new()
        assert {r["pulse"] for r in sink.values()} == {t} and set(sink) == {x.unit_id for x in app.units.all()}
        if len(hist) == 2:
            rec = W.reconstruct_firing(hist[-1]["units"], {c: v["weight"] for c, v in hist[0]["connections"].items()}, last, 1.0)
            for uid, r in rec.items():
                assert abs(r["activity_pre"] - sink[uid]["activity_pre"]) < 1e-12
                assert r["fires"] == sink[uid]["fired"] == (uid in {x for _, x in now})
                assert not sink[uid]["probe_fired"]
            checked += 1
        hist, last = (hist + [W.snapshot(app)])[-2:], now
    assert checked == 299 and log.activity()


def test_audit_does_not_change_how_an_arm_runs() -> None:
    plain, plain_log, u = _app()
    audited, audited_log, _ = _app()
    for app in (plain, audited):
        _set_weights(app, u, A_CONTROL)
        for x in app.units.all():
            _set_unit(app, x.unit_id, 0.0, 0.0)
    W.make_audited(audited)
    W.advance_to(plain, 600)
    W.advance_to(audited, 600)
    assert plain_log.activity() == audited_log.activity() and plain_log.activity()
    assert W.snapshot(plain) == W.snapshot(audited)


# ---- 実物の手順の通しの確認（合成・確認専用の範囲の seed 15200。観測の量は計算・表示・確認しない）---------------------

@pytest.fixture(scope="module")
def check_run():
    import os
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        return W.measure_seed(PROTOCOL, CHECK_SEED)
    finally:
        os.chdir(cwd)


def test_full_procedure_passes_checks_from_raw(A, check_run) -> None:
    out = A.check_run(check_run)
    assert {k: v for k, v in out.items() if v} == {}


def test_full_procedure_records_the_preregistered_raw_items(check_run) -> None:
    """生の記録の形（観測の量は見ない）：8 腕・t0 の複製と届く途中の駆動・標本の時刻・分岐の記録の鍵。"""
    assert tuple(check_run["arms"]["spikes"]) == W.ARMS == tuple(check_run["fork"]) == tuple(check_run["endpoints"])
    assert tuple(check_run["fork_in_flight"]) == W.ARMS
    times = sorted(int(t) for t in check_run["arms"]["samples"]["O"])
    assert times == list(range(12000, 24001, 60))
    assert set(check_run["arms"]) == {"spikes", "sensory", "samples", "t_OS", "t_YO", "t_YS"}
    assert set(check_run["conditions"]) == {"ordered", "shuffled"}


def test_condition_checks_detect_raw_problems(A, check_run) -> None:
    def failed(mutate) -> set:
        bad = copy.deepcopy(check_run)
        mutate(bad)
        return {k for k, v in A.check_run(bad).items() if v}

    u = check_run["roles"]["units"]
    cid = W.connection_id(u["A"], u["B"])
    assert "input_free_after_experience" in failed(
        lambda b: b["conditions"]["shuffled"]["sensory"].append([12001, b["roles"]["receptors"]["A"]]))
    assert "fork_is_clone" in failed(lambda b: b["conditions"]["shuffled"]["connections_12000"][cid].__setitem__("pre_trace", 0.123))
    assert "replay_history_12000" in failed(lambda b: b["conditions"]["ordered"]["connections_12000"][cid].__setitem__(
        "weight", b["conditions"]["ordered"]["connections_12000"][cid]["weight"] + 1e-9))
    assert "stimulus_counts" in failed(lambda b: b["conditions"]["ordered"]["sensory"].pop())
    assert "identical_before_label_divergence" in failed(lambda b: b["conditions"]["shuffled"]["birth"][u["A"]].__setitem__("activity", 0.3))


FAKE_COMMIT = "0" * 40


def _check_data(check_run, mode="check", commit=FAKE_COMMIT, runs=None):
    runs = [check_run] if runs is None else runs
    seeds = [r["seed"] for r in runs]
    ek = {"experiment": PROTOCOL["experiment"], "kind": PROTOCOL["kind"]}
    data = {"meta": ek | {"mode": mode, "git_commit": commit, "protocol": PROTOCOL,
                          "manifest": W.manifest_raw(PROTOCOL), "seeds": seeds}, "runs": runs}
    proto_sha = G.sha256_file(EXP / "protocol.yaml")
    records = {"start": ek | {"mode": mode, "git_commit": commit, "seeds": seeds, "protocol_sha256": proto_sha},
               "finish": ek | {"status": "completed", "mode": mode, "git_commit_start": commit,
                               "git_commit_end": commit, "seeds": seeds, "runs_sha256": "f" * 64},
               "runs_sha256": "f" * 64}
    return data, records


def test_check_report_hides_observations(A, check_run) -> None:
    data, records = _check_data(check_run)
    report = A.analyze(data, "check", records)
    assert report["valid"], report["problems"]
    assert not ({"summary", "per_seed"} & set(report))
    assert report["individuals"] == {str(CHECK_SEED): {"valid": True, "failed_checks": {}}}
    text = json.dumps(report)
    assert not any(k in text for k in ('"t_YO"', '"t_YS"', '"t_OS"', "U_YO", "differing_pulses"))


def test_invalid_individuals_are_reported_not_dropped(A, check_run) -> None:
    bad = copy.deepcopy(check_run)
    bad["arms"]["spikes"]["twin_O"].append([24000, "s9"])
    data, records = _check_data(check_run, runs=[bad])
    report = A.analyze(data, "check", records)
    assert not report["valid"]
    ind = report["individuals"][str(CHECK_SEED)]
    assert not ind["valid"] and "twin_O_equals_O" in ind["failed_checks"]


def test_completeness_rejects_bad_data(A, check_run) -> None:
    def invalid(data, records, mode="check", needle=None):
        r = A.analyze(data, mode, records)
        assert not r["valid"]
        if needle:
            assert any(needle in p for p in r["problems"]), r["problems"]

    data, rec = _check_data(check_run, runs=[])
    invalid(data, rec, needle="個体が 1 つもない")
    data, rec = _check_data(check_run)
    data["meta"]["seeds"] = [15199]
    invalid(data, rec, needle="meta の seed の列")
    data, rec = _check_data(check_run, mode="formal")
    invalid(data, rec, mode="check", needle="データの mode")
    data, rec = _check_data(check_run)
    invalid(data, rec, mode="formal", needle="データの mode")
    invalid(data, rec, mode="formal", needle="全件ではない")
    data, rec = _check_data(check_run, commit="unknown")
    invalid(data, rec, needle="40 桁の commit")
    data, rec = _check_data(check_run)
    data["meta"]["experiment"] = "0019"                               # 別の実験のデータをこの実験として解析しない
    invalid(data, rec, needle="experiment・kind")
    for other_seed in (14101, 15001):                                 # これまでの合成の範囲・本番の範囲の seed
        bad = copy.deepcopy(check_run)
        bad["seed"] = other_seed
        data, rec = _check_data(check_run, runs=[bad])
        invalid(data, rec, needle="範囲の外の seed")


def test_completeness_rejects_duplicate_seeds(A, check_run) -> None:
    data, _ = _check_data(check_run, runs=[check_run, check_run])
    r = A.completeness(data, "check")
    assert any("seed が重複" in p for p in r)


def test_run_records_are_verified(A, check_run) -> None:
    data, rec = _check_data(check_run)
    for mutate, needle in [
        (lambda r: r.__setitem__("start", None), "開始の記録"),
        (lambda r: r.__setitem__("finish", None), "終了の記録"),
        (lambda r: r["finish"].__setitem__("status", "failed"), "completed ではない"),
        (lambda r: r["finish"].__setitem__("git_commit_end", "1" * 40), "commit"),
        (lambda r: r.__setitem__("runs_sha256", "e" * 64), "sha256"),
        (lambda r: r["start"].__setitem__("protocol_sha256", "e" * 64), "protocol.yaml"),
        (lambda r: r["start"].__setitem__("mode", "formal"), "mode"),
        (lambda r: r["start"].__setitem__("experiment", "0019"), "experiment・kind"),
        (lambda r: r["finish"].__setitem__("kind", "exploration"), "experiment・kind"),
    ]:
        r = copy.deepcopy(rec)
        mutate(r)
        report = A.verify_records(r, data, "check")
        assert any(needle in p for p in report), (needle, report)


# ---- これまでの実験から完全に分離（README §7.2）・玩具を使わない ---------------------------------------------------

FORBIDDEN = [r'"0020"', r"'0020'", r'"0021"', r"'0021'", r"experiments/0020", r"experiments/0021",
             r"0020_weight_intervention", r"0021_yoked_plasticity", r"0020-shuffle", r"0021-shuffle",
             r"data/experiments/002[01]"]
SEED_NUMBERS = r"\b1[34][0-2]\d\d\b"        # 0020・0021 の seed の範囲（13001〜13200・14001〜14200）の数
TOOLS = ("world.py", "run.py", "analyze.py", "alignment.py", "guard.py")


def _strip_seen(src: str) -> str:
    return re.sub(r"SEEN = \(.*?\)\)\)\n", "", src, flags=re.DOTALL)


def test_tools_hold_no_earlier_experiment_constants() -> None:
    """0022 の道具のコードに、0020・0021 の experiment ID・出力先・protocol のパス・乱数の流れの名前・seed の範囲の定数がない。
    （alignment.py の使用済みの seed の一覧 SEEN は、重ならないことを確かめるための記録なので除く）"""
    for name in TOOLS:
        src = (EXP / name).read_text(encoding="utf-8")
        if name == "alignment.py":
            src = _strip_seen(src)
        for pat in FORBIDDEN:
            assert not re.search(pat, src), (name, pat)
        assert not re.search(SEED_NUMBERS, src), (name, "0020・0021 の seed の範囲の数")


def test_the_constant_scan_detects_leftovers() -> None:
    """上の検査そのものが、混入した定数を見逃さないこと（検査の検査）。"""
    src = (EXP / "alignment.py").read_text(encoding="utf-8")
    stripped = _strip_seen(src)
    assert "range(14001" in src and "range(14001" not in stripped and "SEEN = (" not in stripped
    for leftover in ('EXPERIMENT = "0021"', 'OUT = "data/experiments/0021"', 'RNG = "0021-shuffle:{seed}"',
                     "SEEDS = range(14001, 14101)", "path = 'experiments/0020_weight_intervention_exploration'",
                     "SYN = range(13101, 13201)"):
        assert any(re.search(p, leftover) for p in FORBIDDEN) or re.search(SEED_NUMBERS, leftover), leftover


def test_tools_do_not_use_the_pre_registration_toy() -> None:
    """README 付録 A の玩具（pre_registration_toy/）は記録として置くだけで、道具は読み込まない・使わない。"""
    for name in TOOLS:
        src = (EXP / name).read_text(encoding="utf-8")
        code = "\n".join(line for line in src.splitlines() if not line.lstrip().startswith("#"))
        code = re.sub(r'""".*?"""', "", code, flags=re.DOTALL)                 # 説明の文字列（「使わない」と書いた箇所）は除く
        assert "pre_registration_toy" not in code and "toy.py" not in code, name


def test_tools_read_identity_from_this_protocol() -> None:
    R = _load("run_0022_identity", EXP / "run.py")
    A_ = _load("analyze_0022_identity", EXP / "analyze.py")
    ex = PROTOCOL["execution"]
    assert R.EXPERIMENT == A_.EXPERIMENT == W.EXPERIMENT == PROTOCOL["experiment"] == ex["experiment_id"] == "0022"
    assert str(R.OUT_DIR) == str(A_.DEFAULT_DIR) == ex["output_dir"]
    assert str(R.PROTOCOL_PATH) == str(A_.PROTOCOL_PATH) == str(W.PROTOCOL_PATH) == ex["protocol_path"]
    assert W.RNG_SHUFFLE == W.W15.RNG_SHUFFLE == PROTOCOL["stimulus"]["rng_shuffle"]
    assert list(R.allowed_seeds("formal")) == list(range(PROTOCOL["seeds"]["first"], PROTOCOL["seeds"]["last"] + 1))
    assert list(R.allowed_seeds("check")) == list(range(15101, 15201))


def test_runtime_core_files_are_unchanged_from_main() -> None:
    """本体（src/）・設計図・0012〜0021 の実験の道具を、この PR で変えていない（main との差分）。
    0022 の道具を変える branch でだけ確かめる（PR #92 の範囲の確認なので、0022 の道具を変えない後の branch の作業を止めない。
    0023・0024 の契約テストと同じ形）。"""
    try:
        base = subprocess.run(["git", "-C", str(ROOT), "merge-base", "HEAD", "origin/main"], capture_output=True,
                              text=True, check=True).stdout.strip()
        diff = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", base, "--", "src", "config", "experiments"],
                              capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git の履歴がない環境")
    if not set(diff) & {f"experiments/{EXP.name}/{n}" for n in TOOLS}:
        pytest.skip("この branch は 0022 の道具を変えていない")
    assert all(p.startswith("experiments/0022_natural_history_yoke/") for p in diff), diff
    assert not any(p.endswith(("README.md", "protocol.yaml")) or "pre_registration_toy" in p for p in diff), diff


# ---- 一度限りの実行の保護（README §7.2）。使い捨ての git リポジトリで。seed の計算は dummy で、本番の seed は使わない ---------

def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / EXP.relative_to(ROOT)).mkdir(parents=True)
    (r / EXP.relative_to(ROOT) / "protocol.yaml").write_bytes((EXP / "protocol.yaml").read_bytes())
    (r / ".gitignore").write_text("/out/\n", encoding="utf-8")
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@example.invalid")
    _git(r, "config", "user.name", "t")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "init")
    return r


@pytest.fixture
def R():
    return _load("run_0022_test", EXP / "run.py")


def _serial(fn, seeds):
    return (fn(s) for s in seeds)


def test_guard_requires_a_clean_real_commit(repo, monkeypatch) -> None:
    head = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setenv("ANIMA_GIT_COMMIT", "f" * 40)
    assert G.verify_clean_commit(repo) == head == G.verify_clean_commit(repo, head)
    with pytest.raises(G.GuardError, match="指定した commit"):
        G.verify_clean_commit(repo, "1" * 40)
    (repo / "untracked.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(G.GuardError, match="作業ツリー"):
        G.verify_clean_commit(repo, head)


def test_execute_runs_once_and_saves_atomically(repo, R) -> None:
    out = repo / "out"
    head = _git(repo, "rev-parse", "HEAD")
    calls = []
    runner = lambda s: calls.append(s) or {"seed": s}
    rec = R.execute("check", [15101, 15102], out, repo, head, runner=runner, mapper=_serial)
    assert rec["status"] == "completed" and rec["experiment"] == PROTOCOL["experiment"] and rec["kind"] == PROTOCOL["kind"]
    assert calls == [15101, 15102]
    assert sorted(p.name for p in out.iterdir()) == [G.FINISH, G.START, G.RUNS]
    assert G.sha256_file(out / G.RUNS) == rec["runs_sha256"]
    start = json.loads((out / G.START).read_text(encoding="utf-8"))
    assert start["experiment"] == PROTOCOL["experiment"] and start["protocol_sha256"] == G.sha256_file(EXP / "protocol.yaml")
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    with pytest.raises(R.G.GuardError):
        R.execute("check", [15101, 15102], out, repo, head, runner=runner, mapper=_serial)
    assert calls == [15101, 15102] and {p.name: p.read_bytes() for p in out.iterdir()} == before


def test_execute_refuses_before_touching_seeds(repo, R) -> None:
    head = _git(repo, "rev-parse", "HEAD")
    calls = []
    runner = lambda s: calls.append(s) or {"seed": s}
    with pytest.raises(R.G.GuardError, match="指定した commit"):
        R.execute("check", [15101], repo.parent / "out1", repo, "1" * 40, runner=runner, mapper=_serial)
    (repo.parent / "out3").mkdir()
    (repo.parent / "out3" / G.START).write_text("{}", encoding="utf-8")
    with pytest.raises(R.G.GuardError, match="既にある"):
        R.execute("check", [15101], repo.parent / "out3", repo, head, runner=runner, mapper=_serial)
    for mode, seed in (("check", 14199), ("check", 13101), ("check", 15001), ("formal", 15101), ("formal", 14001)):
        with pytest.raises(R.G.GuardError, match="範囲の外"):
            R.execute(mode, [seed], repo.parent / f"out_{mode}_{seed}", repo, head, runner=runner, mapper=_serial)
        assert not (repo.parent / f"out_{mode}_{seed}").exists()
    with pytest.raises(R.G.GuardError):
        R.execute("check", [], repo.parent / "out6", repo, head, runner=runner, mapper=_serial)
    with pytest.raises(R.G.GuardError):
        R.execute("check", [15101, 15101], repo.parent / "out7", repo, head, runner=runner, mapper=_serial)
    assert calls == []
    assert not (repo.parent / "out1").exists()


def test_execute_records_failure_and_does_not_save_results(repo, R) -> None:
    head = _git(repo, "rev-parse", "HEAD")

    def runner(s):
        if s == 15102:
            raise RuntimeError("boom")
        return {"seed": s}

    out = repo / "out"
    with pytest.raises(RuntimeError, match="boom"):
        R.execute("check", [15101, 15102], out, repo, head, runner=runner, mapper=_serial)
    fin = json.loads((out / G.FINISH).read_text(encoding="utf-8"))
    assert fin["status"] == "failed" and fin["seeds_touched"] == [15101, 15102] and fin["experiment"] == PROTOCOL["experiment"]
    assert not (out / G.RUNS).exists()


def test_execute_detects_head_moving_during_the_run(repo, R) -> None:
    head = _git(repo, "rev-parse", "HEAD")

    def runner(s):
        (repo / f"moved_{s}.txt").write_text("x", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", f"moved {s}")
        return {"seed": s}

    out = repo / "out"
    with pytest.raises(R.G.GuardError, match="指定した commit"):
        R.execute("check", [15101], out, repo, head, runner=runner, mapper=_serial)
    assert json.loads((out / G.FINISH).read_text(encoding="utf-8"))["status"] == "failed"
    assert not (out / G.RUNS).exists()


def test_main_refuses_unsafe_invocations(R, monkeypatch, tmp_path) -> None:
    """本番は --measurement-commit が必須で出力先は固定。--check は本番・これまでの seed、data/experiments の下を使えない。
    拒否は、出力先に何も作らない（前後で比べる）。"""
    marker = ROOT / PROTOCOL["execution"]["output_dir"] / G.START
    existed = marker.exists()
    for argv, needle in [
        ([], "--measurement-commit"),
        (["--measurement-commit", "0" * 40, "--out", str(tmp_path)], "固定"),
        (["--check", "15200"], "--out"),
        (["--check", "15001", "--out", str(tmp_path)], "合成・確認専用"),
        (["--check", "14199", "--out", str(tmp_path)], "合成・確認専用"),
        (["--check", "15200", "--out", str(ROOT / PROTOCOL["execution"]["output_dir"])], "data/experiments"),
        (["--check", "15200", "--out", str(ROOT / "data" / "experiments" / "0019")], "data/experiments"),
    ]:
        monkeypatch.setattr("sys.argv", ["run.py", *argv])
        with pytest.raises(SystemExit, match=needle):
            R.main()
    assert marker.exists() == existed


def test_pool_map_uses_the_fixed_worker_cap_regardless_of_cpu_count(R, monkeypatch) -> None:
    assert R.MAX_WORKERS == PROTOCOL["execution"]["max_workers"] == 2
    seen = []

    class FakePool:
        def __init__(self, max_workers):
            seen.append(max_workers)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def map(self, fn, seeds):
            return map(fn, seeds)

    monkeypatch.setattr(R, "ProcessPoolExecutor", FakePool)
    monkeypatch.setattr("os.cpu_count", lambda: 64)
    seeds = list(range(15101, 15201))
    assert [r["seed"] for r in R._pool_map(lambda s: {"seed": s}, seeds)] == seeds
    assert [r["seed"] for r in R._pool_map(lambda s: {"seed": s}, [15101])] == [15101]
    assert seen == [2, 1]


@pytest.mark.parametrize("name,bad_mapper", [
    ("欠落", lambda fn, seeds: (fn(s) for s in seeds[:-1])),
    ("重複", lambda fn, seeds: (fn(s) for s in [seeds[0], seeds[0]])),
    ("別の seed", lambda fn, seeds: (fn(s + 50) for s in seeds)),
    ("多すぎる", lambda fn, seeds: (fn(s) for s in seeds + seeds[:1])),
    ("順序", lambda fn, seeds: (fn(s) for s in reversed(seeds))),
    ("辞書でない", lambda fn, seeds: (None for _ in seeds)),
])
def test_execute_never_marks_incomplete_results_completed(repo, R, name, bad_mapper) -> None:
    head = _git(repo, "rev-parse", "HEAD")
    out = repo.parent / f"out_{name}"
    with pytest.raises(R.G.GuardError, match="結果"):
        R.execute("check", [15101, 15102], out, repo, head, runner=lambda s: {"seed": s}, mapper=bad_mapper)
    fin = json.loads((out / G.FINISH).read_text(encoding="utf-8"))
    assert fin["status"] == "failed" and fin["experiment"] == PROTOCOL["experiment"]
    assert not (out / G.RUNS).exists()


def _timed_worker(seed):
    """実際のプロセスで、開始・終了の時刻と pid を記録する（並列数の契約のためだけ。seed の計算はしない）。"""
    import os as _os
    import time as _time
    t0 = _time.monotonic()
    _time.sleep(0.15)
    t1 = _time.monotonic()
    path = Path(_os.environ["ANIMA_0022_TIMING_DIR"]) / f"{seed}.json"
    path.write_text(json.dumps({"seed": seed, "pid": _os.getpid(), "t0": t0, "t1": t1}), encoding="utf-8")
    return {"seed": seed}


@pytest.mark.skipif(__import__("multiprocessing").get_start_method(allow_none=False) != "fork",
                    reason="テスト関数を子プロセスへ渡すのに fork が要る（本番の run.py は fork・spawn のどちらでも動く）")
def test_pool_map_never_runs_more_than_two_processes_at_once(R, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ANIMA_0022_TIMING_DIR", str(tmp_path))
    seeds = list(range(15101, 15111))
    out = list(R._pool_map(_timed_worker, seeds))
    assert [r["seed"] for r in out] == seeds
    rec = [json.loads(p.read_text(encoding="utf-8")) for p in tmp_path.glob("*.json")]
    assert sorted(r["seed"] for r in rec) == seeds
    assert len({r["pid"] for r in rec}) <= 2
    events = sorted([(r["t0"], 1) for r in rec] + [(r["t1"], -1) for r in rec])
    running = peak = 0
    for _, d in events:
        running += d
        peak = max(peak, running)
    assert peak <= 2


# ---- 解析の出力先の隔離（既存の report はバイト単位で変えない）------------------------------------------------------

def _fake_data_root(tmp_path, monkeypatch, A):
    """data/experiments の見立て（一時フォルダ）。これまでの実験の実データには触らない。"""
    root = tmp_path / "repo" / "data" / "experiments"
    own = root / Path(PROTOCOL["execution"]["output_dir"]).name
    other = root / "0019"
    for d in (own, other):
        d.mkdir(parents=True)
    monkeypatch.setattr(A, "DATA_ROOT", root)
    monkeypatch.setattr(A, "OWN_DIR", own)
    return root, own, other


def _contents(folder: Path) -> dict:
    return {p.name: p.read_bytes() for p in sorted(folder.iterdir())}


def test_analysis_never_writes_into_other_experiment_folders(A, tmp_path, monkeypatch) -> None:
    root, own, other = _fake_data_root(tmp_path, monkeypatch, A)
    (other / "report.json").write_bytes(b'{"experiment": "0019", "original": true}\n')
    (other / "runs.json.gz").write_bytes(b"not gzip")
    before = _contents(other)
    for argv in (["analyze.py", str(other)], ["analyze.py", str(other), "--check"],
                 ["analyze.py", str(root)], ["analyze.py", str(root), "--check"]):
        monkeypatch.setattr("sys.argv", argv)
        with pytest.raises(SystemExit, match="report を書かない"):
            A.main()
        assert _contents(other) == before
    assert sorted(p.name for p in own.iterdir()) == []


def test_analysis_never_overwrites_an_existing_report_or_series(A, tmp_path, monkeypatch) -> None:
    _, own, _ = _fake_data_root(tmp_path, monkeypatch, A)
    for name in (A.REPORT, A.SERIES, A.LOG, A.REPORT + ".tmp-1", A.SERIES + ".tmp-3"):
        (own / name).write_bytes(b'{"already": "analyzed"}\n')
        before = _contents(own)
        monkeypatch.setattr("sys.argv", ["analyze.py"])
        with pytest.raises(SystemExit, match="上書きしない"):
            A.main()
        assert _contents(own) == before
        (own / name).unlink()
    (own / A.REPORT).write_bytes(b'{"already": "analyzed"}\n')               # 解析の記録のない成果物：再開もしない
    before = _contents(own)
    monkeypatch.setattr(A.ALIGN, "check", lambda protocol: None)
    monkeypatch.setattr("sys.argv", ["analyze.py", "--resume"])
    with pytest.raises(SystemExit, match="再開できる解析の記録がない"):
        A.main()
    assert _contents(own) == before
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "report.json").write_bytes(b"old\n")
    monkeypatch.setattr("sys.argv", ["analyze.py", str(scratch), "--check"])
    with pytest.raises(SystemExit, match="上書きしない"):
        A.main()
    assert (scratch / "report.json").read_bytes() == b"old\n"


def test_check_analysis_writes_only_to_a_scratch_folder(A, tmp_path, monkeypatch) -> None:
    _fake_data_root(tmp_path, monkeypatch, A)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr("sys.argv", ["analyze.py", str(scratch), "--check"])
    A.main()
    report = json.loads((scratch / "report.json").read_text(encoding="utf-8"))
    assert report["mode"] == "check" and not report["valid"]                 # 結果のファイルがないので invalid
    assert not ({"summary", "per_seed"} & set(report))
    assert not (scratch / A.SERIES).exists() and report["artifacts"] == {}
    assert [e["event"] for e in A.read_log(scratch)] == ["started", "written", "completed"]
    assert A.verify_artifacts(scratch, "check") == {"problems": [], "notes": []}


def test_real_other_experiment_paths_are_refused_by_path_alone(A) -> None:
    """実際の data/experiments の下のほかの実験のフォルダ（と data/experiments そのもの）は、パスだけで拒否する。"""
    for other in ("0019", "0020", "0021"):
        real_other = A.REPO / "data" / "experiments" / other
        for mode in ("formal", "check"):
            with pytest.raises(A.G.GuardError):
                A.report_destination(real_other, mode)
    for mode in ("formal", "check"):
        with pytest.raises(A.G.GuardError):
            A.report_destination(A.REPO / "data" / "experiments", mode)



# ---- 成果物の公開の故障注入（#92 のレビュー 5505249564）---------------------------------------------------------
# 本番の解析の書き出しの経路だけを確かめる。観測の量は計算しない（解析の関数を、固定のダミーの出力に差し替える）。
# raw も実データではなく、ダミーのバイト列（sha256 の照合の対象としてだけ使う）。

FAKE_SERIES = gzip.compress(b'{"fake": "series, not data"}', mtime=0)


def _fake_formal(A, tmp_path, monkeypatch, series: bytes = FAKE_SERIES):
    _, own, _ = _fake_data_root(tmp_path, monkeypatch, A)
    (own / G.RUNS).write_bytes(b"raw stand-in (not real data)")
    monkeypatch.setattr(A.ALIGN, "check", lambda protocol: None)
    monkeypatch.setattr(A, "build_outputs", lambda folder, mode: (
        {"experiment": A.EXPERIMENT, "mode": mode, "valid": False, "problems": [], "individuals": {}, "per_seed": {}},
        {A.SERIES: series}))
    return own


def _main(A, monkeypatch, *argv) -> None:
    monkeypatch.setattr("sys.argv", ["analyze.py", *argv])
    A.main()


def _events(A, folder) -> list[str]:
    return [e["event"] for e in A.read_log(folder)]


def _fail_on(A, monkeypatch, name: str, leave_tmp: bool = False):
    """name の成果物の公開で故障させる（leave_tmp なら、書きかけの一時ファイルを残してから）。元の関数を返す。"""
    real = A._publish_file

    def fake(path, data, attempt):
        if path.name == name:
            if leave_tmp:
                path.with_name(f"{path.name}.tmp-{attempt}").write_bytes(data[:7])
            raise OSError("injected failure")
        return real(path, data, attempt)

    monkeypatch.setattr(A, "_publish_file", fake)
    return real


def test_interruption_after_series_before_report_is_completed_only_by_a_verified_resume(A, tmp_path, monkeypatch) -> None:
    own = _fake_formal(A, tmp_path, monkeypatch)
    real = _fail_on(A, monkeypatch, A.REPORT)
    with pytest.raises(OSError, match="injected"):
        _main(A, monkeypatch)
    assert (own / A.SERIES).exists() and not (own / A.REPORT).exists()          # 部分的な公開が残る
    assert _events(A, own) == ["started", "written", "failed"]
    failed = A.read_log(own)[-1]
    assert failed["present"] == {A.SERIES: G.sha256_bytes(FAKE_SERIES), A.REPORT: None}
    series_stat = (own / A.SERIES).stat()
    monkeypatch.setattr(A, "_publish_file", real)
    with pytest.raises(SystemExit, match="上書きしない"):                            # 通常の再入場は拒否
        _main(A, monkeypatch)
    _main(A, monkeypatch, "--resume")                                            # 照合して完了
    after = (own / A.SERIES).stat()
    assert (own / A.SERIES).read_bytes() == FAKE_SERIES and (after.st_ino, after.st_mtime_ns) == (series_stat.st_ino, series_stat.st_mtime_ns)
    report = json.loads((own / A.REPORT).read_text(encoding="utf-8"))
    assert report["artifacts"][A.SERIES] == {"sha256": G.sha256_bytes(FAKE_SERIES), "bytes": len(FAKE_SERIES)}
    assert report["inputs"]["runs_sha256"] == G.sha256_file(own / G.RUNS)
    assert _events(A, own) == ["started", "written", "failed", "resumed", "written", "completed"]
    assert A.read_log(own)[-1]["resumed"] is True
    assert A.verify_artifacts(own, "formal") == {"problems": [], "notes": []}
    with pytest.raises(SystemExit, match="0"):
        _main(A, monkeypatch, "--verify")
    with pytest.raises(SystemExit, match="完了"):
        _main(A, monkeypatch, "--resume")
    with pytest.raises(SystemExit, match="上書きしない"):
        _main(A, monkeypatch)


@pytest.mark.parametrize("damage,needle", [
    ("corrupt_series", "破損"),
    ("change_raw", "入力"),
    ("delete_series", "書いた記録があるのに、ない"),
    ("replace_series_with_other_bytes", "破損"),
])
def test_resume_refuses_and_records_unrecoverable_states(A, tmp_path, monkeypatch, damage, needle) -> None:
    """破損・入力の変化・成果物の消失は、再開しても完了させない。復旧不能を記録し、成果物を書き直さない。以後の再開も拒否。"""
    own = _fake_formal(A, tmp_path, monkeypatch)
    real = _fail_on(A, monkeypatch, A.REPORT)
    with pytest.raises(OSError):
        _main(A, monkeypatch)
    monkeypatch.setattr(A, "_publish_file", real)
    if damage == "corrupt_series":
        (own / A.SERIES).write_bytes(FAKE_SERIES[:-3])
    elif damage == "change_raw":
        (own / G.RUNS).write_bytes(b"different raw")
    elif damage == "delete_series":
        (own / A.SERIES).unlink()
    else:
        (own / A.SERIES).write_bytes(gzip.compress(b'{"other": 1}', mtime=0))
    before = _contents(own)
    with pytest.raises(SystemExit, match=needle):
        _main(A, monkeypatch, "--resume")
    assert _events(A, own)[-1] == "unrecoverable"
    assert not (own / A.REPORT).exists()
    after = _contents(own)
    assert {k: v for k, v in after.items() if k != A.LOG} == {k: v for k, v in before.items() if k != A.LOG}   # 成果物は変えない
    with pytest.raises(SystemExit, match="復旧不能"):
        _main(A, monkeypatch, "--resume")


def test_a_stale_temporary_file_is_kept_and_recorded(A, tmp_path, monkeypatch) -> None:
    """書きかけの一時ファイルは消さずに残し、再開の記録に載せる。再開は別の名前の一時ファイルで公開する。"""
    own = _fake_formal(A, tmp_path, monkeypatch)
    real = _fail_on(A, monkeypatch, A.REPORT, leave_tmp=True)
    with pytest.raises(OSError):
        _main(A, monkeypatch)
    stale = own / f"{A.REPORT}.tmp-1"
    assert stale.exists()
    stale_bytes = stale.read_bytes()
    monkeypatch.setattr(A, "_publish_file", real)
    with pytest.raises(SystemExit, match="上書きしない"):
        _main(A, monkeypatch)
    _main(A, monkeypatch, "--resume")
    assert stale.read_bytes() == stale_bytes                                    # 黙って消さない
    resumed = next(e for e in A.read_log(own) if e["event"] == "resumed")
    assert resumed["stale_tmp"] == [stale.name] and _events(A, own)[-1] == "completed"
    assert A.verify_artifacts(own, "formal")["problems"] == []


def test_interruption_before_any_artifact_and_after_an_unlogged_publication(A, tmp_path, monkeypatch) -> None:
    """(1) 最初の成果物の前の故障 → 再開で両方を公開。(2) 公開の後、記録の前に止まった（本名のファイルはあるが「書いた」がない）
    → 再開で、同じバイト列であることを確かめて、そのまま残す。"""
    own = _fake_formal(A, tmp_path, monkeypatch)
    real = _fail_on(A, monkeypatch, A.SERIES)
    with pytest.raises(OSError):
        _main(A, monkeypatch)
    assert A.read_log(own)[-1]["present"] == {A.SERIES: None, A.REPORT: None}
    monkeypatch.setattr(A, "_publish_file", real)
    _main(A, monkeypatch, "--resume")
    assert _events(A, own) == ["started", "failed", "resumed", "written", "written", "completed"]

    own2 = tmp_path / "second"
    own2.mkdir()
    monkeypatch.setattr(A, "OWN_DIR", own2)
    (own2 / G.RUNS).write_bytes(b"raw stand-in (not real data)")
    real_append = A._append

    def append(folder, event, create=False):
        if event["event"] == "written" and event.get("file") == A.SERIES:
            raise KeyboardInterrupt("stopped before the record")
        return real_append(folder, event, create)

    monkeypatch.setattr(A, "_append", append)
    with pytest.raises(KeyboardInterrupt):
        _main(A, monkeypatch, str(own2))
    assert (own2 / A.SERIES).exists() and _events(A, own2) == ["started", "failed"]
    monkeypatch.setattr(A, "_append", real_append)
    _main(A, monkeypatch, str(own2), "--resume")
    assert _events(A, own2) == ["started", "failed", "resumed", "written", "completed"]
    assert A.verify_artifacts(own2, "formal")["problems"] == []


def test_interruption_during_the_analysis_itself_leaves_no_artifact(A, tmp_path, monkeypatch) -> None:
    own = _fake_formal(A, tmp_path, monkeypatch)
    good = A.build_outputs
    monkeypatch.setattr(A, "build_outputs", lambda folder, mode: (_ for _ in ()).throw(MemoryError("injected")))
    with pytest.raises(MemoryError):
        _main(A, monkeypatch)
    assert sorted(p.name for p in own.iterdir()) == sorted([G.RUNS, A.LOG]) and _events(A, own) == ["started", "failed"]
    monkeypatch.setattr(A, "build_outputs", good)
    _main(A, monkeypatch, "--resume")
    assert _events(A, own)[-1] == "completed"


def test_verify_detects_damage_after_completion(A, tmp_path, monkeypatch) -> None:
    own = _fake_formal(A, tmp_path, monkeypatch)
    _main(A, monkeypatch)
    assert A.verify_artifacts(own, "formal") == {"problems": [], "notes": []}
    original = {n: (own / n).read_bytes() for n in (A.SERIES, A.REPORT, G.RUNS, A.LOG)}
    for name, damaged in ((A.SERIES, FAKE_SERIES[:-1]), (A.REPORT, original[A.REPORT] + b" "),
                          (G.RUNS, b"other raw"), (A.LOG, original[A.LOG] + b"not json\n")):
        (own / name).write_bytes(damaged)
        problems = A.verify_artifacts(own, "formal")["problems"]
        assert problems, name
        with pytest.raises(SystemExit, match="1"):
            _main(A, monkeypatch, "--verify")
        (own / name).write_bytes(original[name])
    (own / A.SERIES).unlink()
    assert any("ない" in p for p in A.verify_artifacts(own, "formal")["problems"])


def test_a_damaged_log_stops_the_resume(A, tmp_path, monkeypatch) -> None:
    own = _fake_formal(A, tmp_path, monkeypatch)
    real = _fail_on(A, monkeypatch, A.REPORT)
    with pytest.raises(OSError):
        _main(A, monkeypatch)
    monkeypatch.setattr(A, "_publish_file", real)
    with open(own / A.LOG, "a", encoding="utf-8") as f:
        f.write("{broken\n")
    with pytest.raises(SystemExit, match="記録の破損"):
        _main(A, monkeypatch, "--resume")
    assert not (own / A.REPORT).exists()


def test_rendering_is_deterministic_and_references_the_series_hash(A) -> None:
    report = {"valid": True, "problems": [], "individuals": {}}
    ctx = {"runs_sha256": "a" * 64}
    one, two = A.render(report, {A.SERIES: FAKE_SERIES}, ctx), A.render(report, {A.SERIES: FAKE_SERIES}, ctx)
    assert one == two and one[A.SERIES] == FAKE_SERIES
    assert json.loads(one[A.REPORT])["artifacts"][A.SERIES]["sha256"] == G.sha256_bytes(FAKE_SERIES)
    assert json.loads(A.render(report, {}, ctx)[A.REPORT])["artifacts"] == {}


def test_publication_never_overwrites_through_the_link(A, tmp_path) -> None:
    """公開は os.link で本名に置く：本名が既にあれば失敗し、既存のファイルは変わらない。"""
    target = tmp_path / "x.json"
    target.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        A._publish_file(target, b"new", 1)
    assert target.read_bytes() == b"existing"
