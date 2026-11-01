"""実験 0036 の道具の契約テスト（確定した事前登録 v0.2 の README・protocol.yaml、#162 merge `dd2973f`）。

本番の seed（29001〜29080）・smoke の seed（29101〜29106）は使わない（実行もしない）。0034・0035 の seed・raw（27001〜28299）も
使わない。合成の契約テスト専用の範囲（29201〜29299）だけを使う。合成の個体は、本番と同じ道具（measure.measure_seed）・同じ式で、
区間だけを小さくした Plan（SMALL：0035 の契約テストと同じ。区間 W は e の Pulse 31〜180、H ＝ 60、本体は 239 まで、O3 の複製は
30 の後に作り 90 で比べる）で、実物の runtime を通して作る。結果を見て Plan・seed を選んでいない（seed は範囲の最初から順に使う）。
テストは操作の確認・記録の形・介入の部品の決まり方・符号の規則と判定の算術だけを確かめ、合成の個体の判定の量（s_e・s_fix・r_i・
P_i・J_P・R6・対照の数）の値を表示も判定もしない。

使った合成の seed（PR に開示）：29201〜29210（SMALL で実物の runtime を通す）、29221〜29226（一度限りの実行の契約。dummy の計算）、
29290〜29299 のうち 29299 から順に最初の出来事のある個体（本番の Plan で実物の runtime を通す確かめ）。
"""

import copy
import functools
import gzip
import importlib.util
import inspect
import json
import math
import re
import subprocess
from concurrent.futures import Future
from pathlib import Path

import pytest
import yaml

from anima_ll.domain.model.runtime_event import RuntimeEventType
from anima_ll.unit.dynamics.activity_dynamics import ActivityState

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments" / "0036_as1_other_unit_firing"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = _load("measure_0036_test", EXP / "measure.py")
AN = _load("analyze_0036_test", EXP / "analyze.py")
AL = _load("alignment_0036_test", EXP / "alignment.py")
R = _load("run_0036_test", EXP / "run.py")
A = M.A
SMALL = M.Plan(window_first=31, window_last=180, horizon=60, body_runs_to=239, checkpoints=(30, 120, 239),
               clone_check_at=30, clone_check_until=90)
SYN = list(range(29201, 29211))
GUARD_SEEDS = list(range(29221, 29227))


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)


def _raw(run: dict, mode: str = "synthetic") -> dict:
    return {"meta": {"experiment": "0036", "kind": PROTOCOL["kind"], "mode": mode, "seed": run["seed"],
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
    """合成の範囲の最初から順に見て、SMALL の区間 W に出来事が at_least 個以上ある最初の個体（決定的に求める）。"""
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
    assert R.OUT_DIR == Path("data/experiments/0036") and R.MAX_WORKERS == 2 and AN.OUT_DIR == R.OUT_DIR


def test_seen_seeds_include_0035_and_exclude_0036() -> None:
    assert set(range(27001, 27300)) <= AL.SEEN and set(range(28001, 28300)) <= AL.SEEN
    assert not (set(range(29001, 29300)) & AL.SEEN)


def test_contract_tests_of_o1_are_the_as1_tests_and_this_file() -> None:
    assert AN.CONTRACT_TESTS == (PROTOCOL["tools"]["contract_tests"], str(Path(__file__).relative_to(ROOT)))


def test_the_analysis_pairs_and_censoring_follow_the_protocol() -> None:
    """README §3.1・§3.3：対比の組（X → Y で τ_Y − τ_X）と、系ごとの打ち切りの Pulse。"""
    q = PROTOCOL["quantities"]
    assert {f"d_{k}": list(v) for k, v in AN.PAIRS.items()} == {k: q[k] for k in q if k.startswith("d_")}
    cp = PROTOCOL["sign"]["censor_pulse"]
    ev = {"t": 100, "systems": {"N": {"stopped_at": 111}, "F_prime": {"stopped_at": 122}}}
    want = {"t + H": 160, "stop_N": 111, "stop_F": 122}
    def key_of(name: str) -> str:
        if name in cp:
            return name
        if name in ("F_prime", "N_prime"):
            return name[0]
        return next(k for k in ("blk", "none", "cf") if k in name)
    for name in M.SYSTEMS:
        assert AN.expected_censor(ev, name, 60) == want[cp[key_of(name)]], name
    assert AN.POPULATION_MIN_EVENTS == 10 and AN.C == AN.Fraction(1, 10)


# ---- 実物の runtime を通した合成の個体：操作の確認がすべて成り立つ -----------------------------------

@pytest.mark.parametrize("seed", SYN)
def test_synthetic_individuals_pass_every_operation_check(seed) -> None:
    assert failures(measured(seed), seed) == {}


@functools.lru_cache(maxsize=None)
def _formal_synthetic() -> tuple[int, str]:
    """本番の Plan での確かめ：合成の範囲の最後（29299）から順に見て、本番の Plan の区間 W に出来事がある最初の個体。"""
    plan = M.formal_plan(PROTOCOL)
    for seed in range(29299, 29289, -1):
        run = M.measure_seed(PROTOCOL, seed, plan)
        if run["events"]:
            return seed, json.dumps(_raw(run))
    raise AssertionError("29290〜29299 に出来事のある個体がない")


def test_the_formal_plan_through_the_runtime_passes_every_operation_check() -> None:
    seed, text = _formal_synthetic()
    data = json.loads(text)
    assert {k: v for k, v in AN.check_seed(data, "synthetic", seed, M.formal_plan(PROTOCOL)).items() if v} == {}
    run = data["run"]
    assert run["clone_check"]["at"] == 300 and run["clone_check"]["until"] == 600
    assert sorted(map(int, run["body"]["checkpoints"])) == [300, 600, 900, 1200, 1500, 1800, 2099]
    assert run["rerun_plain"]["pulse"] == 2099 and run["rerun_plain"]["sigma_end_sha256"] == run["body"]["checkpoint_sigma_sha256"]["2099"]


def test_the_synthetic_range_contains_individuals_with_and_without_events() -> None:
    have = [bool(measured(s)["run"]["events"]) for s in SYN]
    assert any(have) and not all(have)


def test_raw_has_no_judgment_quantities() -> None:
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
    for name in ("s_e", "d_e", "s_fix", "d_fix", "s_chg", "s_blk", "s_none", "s_hat", "tau_hat_F", "tau_F", "n_i", "k_i",
                 "r_i", "P_i", "J_P", "R6", "P_blk", "shortcut"):
        assert name not in keys, name


def test_sigma_t_is_the_tool_sigma_at_the_end_of_t() -> None:
    seed = first_with_events()
    run = measured(seed)["run"]
    ev = run["events"][0]
    body = M.build_body(PROTOCOL, seed)
    A.advance_to(body.app, ev["t"])
    assert json.loads(json.dumps(M._sigma(body))) == ev["sigma_t"] and ev["sigma_t"]["pulse"] == ev["t"]


def test_the_synthetic_systems_cover_earlier_and_later_first_intents_and_both_overrides() -> None:
    """O4（README §7 の O4 の詳細）と固定の部品の決まり方が、合成の個体の中で、介入で最初の意図が本体より早い系と遅い系の両方、
    列が自然な決まり方と違う「発火」と「発火しない」の両方を通っている（どれも O4・O8 が成り立つ。値は見ない）。"""
    earlier = later = fire = hold = 0
    for s in SYN:
        run = measured(s)["run"]
        for ev in run["events"]:
            _, stop_f = AN._stop_f(run, ev)
            for name in M.SYSTEMS:
                earlier += ev["systems"][name]["stopped_at"] < stop_f
                later += ev["systems"][name]["stopped_at"] > stop_f
            for name in M.FORCED:
                kinds = [k for _, k in ev["systems"][name]["control"]["overrides"]]
                fire += kinds.count("fire")
                hold += kinds.count("hold")
    assert earlier and later and fire and hold


# ---- AS1 の道具の口（unit_wrappers）と、包みの非干渉（README §2.3） ------------------------------------------

@pytest.mark.parametrize("seed", SYN[:3])
def test_the_pass_through_wrapper_leaves_the_body_unchanged(seed) -> None:
    """他の Unit を包んだ本体（列を置かない）と、#148 と同じ組み立て（unit_wrappers なし）は、出生の時から最後まで、Σ・発火・意図・
    感覚が同じ（O7 の (a) の rerun_plain は、これを seed ごとに確かめる）。"""
    a, b = M.build_body(PROTOCOL, seed), M.build_body(PROTOCOL, seed, wrapped=False)
    assert isinstance(a.app.units.get(a.roles.other), M.OtherFiringControl)
    assert not isinstance(b.app.units.get(b.roles.other), M.OtherFiringControl)
    assert M._sigma(a) == M._sigma(b)
    for p in (1, 50, 120, SMALL.body_runs_to):
        A.advance_to(a.app, p)
        A.advance_to(b.app, p)
        assert M._sigma(a) == M._sigma(b), p
    assert a.log.activity() == b.log.activity() and a.log.sensory() == b.log.sensory() and a.world.intents == b.world.intents


def test_o7_detects_a_wrapper_that_changes_the_body(monkeypatch) -> None:
    """列を置かない間にも中の Unit を変える包み（tick のたびに順応を少し上げる）を差し込むと、本体と、同じく包む走り直しは一致しうるが、
    包まない走り直し（rerun_plain）とは一致しない。O7 の (a) は、この場合に成り立たない。"""
    real = M.OtherFiringControl

    class Leaky(real):
        def tick(self, view, context):
            st = self._inner.export_state()
            st["adaptation"] += 1e-4
            self._inner.import_state(st)
            return super().tick(view, context)
    monkeypatch.setattr(M, "UNIT_WRAPPERS", {"other": Leaky})
    seed = first_with_events()
    data = json.loads(json.dumps(_raw(M.measure_seed(PROTOCOL, seed, SMALL))))
    got = failures(data, seed)
    assert "O7" in got and any("包まない" in x for x in got["O7"]), sorted(got)


# ---- 他の Unit の発火の時刻の固定の部品（README §2.3） ----------------------------------------------------

def _live(seed: int | None = None):
    """SMALL の区間で最初の出来事の Pulse t の処理の後の本体（包んだ組み立て）と、その出来事。"""
    seed = seed or first_with_events()
    body = M.build_body(PROTOCOL, seed)
    for pulse in range(1, SMALL.body_runs_to + 1):
        before = len(body.world.intents)
        A.advance_to(body.app, pulse)
        found = M._event_at(body, before, SMALL, 2)
        if found is not None:
            return body, found
    raise AssertionError("出来事がない")


def _natural_other(body, t: int, until: int) -> list[int]:
    twin = A.clone(body)
    A.advance_to(twin.app, until)
    return [p for p, u in twin.log.activity() if u == body.roles.other and t < p <= until]


def _drives_to(system, unit: str) -> float:
    return sum(d.weight for d in system.app.pulse_runtime.brain_state.drives if d.target_id == unit)


def _dyn(system):
    st = system.app.units.get(system.roles.other).export_state()
    return M._dynamics(st["dynamics"]), M._state_of(st)


def test_identity_the_own_schedule_reproduces_the_natural_system() -> None:
    """恒等の条件（README §2.3）：自分自身の自然な列を置くと、区間の全体で、自然な系と発火・Σ が同じで、列が自然な決まり方と違う
    Pulse はない。"""
    body, (t, _, _) = _live()
    until = t + SMALL.horizon
    own = _natural_other(body, t, until)
    x, y = A.clone(body), A.clone(body)
    M.control_of(x).force(own, after=t, until=until)
    for p in range(t + 1, until + 1):
        A.advance_to(x.app, p)
        A.advance_to(y.app, p)
        assert M._sigma(x) == M._sigma(y), p
    assert x.log.activity() == y.log.activity() and M.control_of(x).overrides == []


def _replay_connections(system_before, fired: list[str]) -> dict:
    store = copy.deepcopy(system_before.connections.inner)
    store.apply_activity(fired, A.PULSE_INTERVAL_SECONDS)
    return store.export_state()


def _fired_at(log, p: int) -> list[str]:
    return [u for q, u in log.activity() if q == p]


def test_a_forced_firing_takes_the_firing_branch_and_the_natural_output_path() -> None:
    """列が「発火」で自然には発火しない Pulse p：他の Unit の状態は advance の発火の枝の更新（活動 0・不応・順応の増分・発火の数）、
    p に ActivityEvent が出て、p の冒頭に固定した重みの駆動が p ＋ 1 に届く（他 → 源・他 → 受）。可塑性は、p の発火の組（他を含む）で
    規則どおりに更新される。"""
    body, (t, _, _) = _live()
    until = t + SMALL.horizon
    natural = _natural_other(body, t, until)
    p = next(q for q in range(t + 2, until) if q not in natural)
    x = A.clone(body)
    M.control_of(x).force([q for q in natural if q < p] + [p], after=t, until=p + 1)
    A.advance_to(x.app, p - 1)
    roles = x.roles
    dyn, pre = _dyn(x)
    stim = _drives_to(x, roles.other)
    _, would = dyn.advance(pre, stim, 1.0)
    assert would is None                                                      # 自然には発火しない Pulse
    weights_p = {k: v["weight"] for k, v in x.app.connections.export_state().items()}
    before = copy.deepcopy(x)
    A.advance_to(x.app, p)
    got = M._state_of(x.app.units.get(roles.other).export_state())
    a = pre.adaptation * math.exp(-1.0 / dyn.adaptation_tau_seconds)
    assert got == ActivityState(0.0, dyn.refractory_pulses, a + dyn.adaptation_increment, pre.fire_count + 1)
    assert roles.other in _fired_at(x.log, p) and M.control_of(x).overrides == [[p, "fire"]]
    drives = {(d.source_id, d.target_id): d.weight for d in x.app.pulse_runtime.brain_state.drives if d.source_id == roles.other}
    assert drives[(roles.other, roles.source)] == weights_p[f"{roles.other}.main->{roles.source}"]
    assert drives[(roles.other, roles.receiver)] == weights_p[f"{roles.other}.main->{roles.receiver}"]
    assert x.app.connections.export_state() == _replay_connections(before, _fired_at(x.log, p))


def test_a_forced_hold_takes_the_non_firing_branch() -> None:
    """列が「発火しない」で自然には発火する Pulse p：他の Unit の状態は advance の発火しない枝の更新（閾値を越えていても活動を
    残し、順応は戻るだけ、発火の数は同じ）。p に ActivityEvent がなく、他の Unit の駆動は作られない。可塑性は、他を含まない発火の組で
    規則どおり。"""
    for seed in SYN:
        found = None
        try:
            body, (t, _, _) = _live(seed)
        except AssertionError:
            continue
        natural = _natural_other(body, t, t + SMALL.horizon)
        if natural:
            found = (body, t, natural[0])
            break
    assert found is not None
    body, t, p = found
    x = A.clone(body)
    M.control_of(x).force([], after=t, until=p)
    A.advance_to(x.app, p - 1)
    dyn, pre = _dyn(x)
    stim = _drives_to(x, x.roles.other)
    natural_state, would = dyn.advance(pre, stim, 1.0)
    assert would is not None                                                  # 自然には発火する Pulse
    before = copy.deepcopy(x)
    A.advance_to(x.app, p)
    got = M._state_of(x.app.units.get(x.roles.other).export_state())
    act = pre.activity * dyn.decay_per_second + stim + dyn.intrinsic_drive_per_second
    assert got == ActivityState(act, 0, pre.adaptation * math.exp(-1.0 / dyn.adaptation_tau_seconds), pre.fire_count)
    assert got.activity >= dyn.threshold + got.adaptation                    # 閾値を越えていても発火の更新をしない
    assert x.roles.other not in _fired_at(x.log, p) and M.control_of(x).overrides == [[p, "hold"]]
    assert not any(d.source_id == x.roles.other for d in x.app.pulse_runtime.brain_state.drives)
    assert x.app.connections.export_state() == _replay_connections(before, _fired_at(x.log, p))


def test_the_control_rejects_repeated_out_of_interval_and_refractory_use() -> None:
    body, (t, _, _) = _live()
    x = A.clone(body)
    with pytest.raises(ValueError):
        M.control_of(x).force([t], after=t, until=t + 3)                     # 区間 (after, until] の外
    with pytest.raises(ValueError):
        M.control_of(x).force([t + 1, t + 1], after=t, until=t + 3)
    M.control_of(x).force([], after=t, until=t + 2)
    with pytest.raises(RuntimeError):
        M.control_of(x).force([], after=t, until=t + 2)                      # 一度だけ
    A.advance_to(x.app, t + 2)
    with pytest.raises(RuntimeError):
        A.advance_to(x.app, t + 3)                                            # 区間の外の Pulse
    y = A.clone(body)
    M.control_of(y).force([t + 1], after=t, until=t + 2)
    unit = y.app.units.get(y.roles.other)
    unit.import_state(dict(unit.export_state(), refractory_remaining=1))
    with pytest.raises(RuntimeError):
        A.advance_to(y.app, t + 1)                                            # 不応の途中（C0 では起きない）


def test_the_schedule_is_copied_with_the_clone_and_is_not_part_of_sigma() -> None:
    body, (t, _, _) = _live()
    x = A.clone(body)
    M.control_of(x).force([t + 2], after=t, until=t + 5)
    y = A.clone(x)
    assert M.control_of(y).control_state() == M.control_of(x).control_state()
    assert M.control_of(y) is not M.control_of(x)
    assert M._sigma(x) == M._sigma(body)                                     # Σ の Unit の状態は中の Unit の状態
    assert M.control_of(body).control_state() is None


# ---- 伝達の遮断（README §2.4） --------------------------------------------------------------------

def test_blocking_zeroes_only_the_two_targets_and_keeps_the_plasticity_rule() -> None:
    body, (t, _, _) = _live()
    x = A.clone(body)
    x.declare([A.Intervention(A.FB1, frozenset(M.block_targets(x.roles)))], label="F_blk")
    keys = M.block_keys(x.roles)
    for p in range(t + 1, t + 20):
        before = copy.deepcopy(x)
        A.advance_to(x.app, p)
        ret, inner = x.connections.last_returned, x.connections.last_inner
        assert all(ret[k] == 0.0 for k in keys)
        assert {k for k in ret if ret[k] != inner[k]} <= set(keys)
        assert x.app.connections.export_state() == _replay_connections(before, _fired_at(x.log, p))


def test_drives_already_in_sigma_t_are_delivered_and_later_ones_are_blocked() -> None:
    """Pulse q に他の Unit が発火した境界で遮断を宣言すると、q に作られた駆動（Σ に入っている）は q ＋ 1 にそのまま届き、
    q ＋ 1 以後の他の Unit の発火による駆動は重み 0 で届く（README §2.4。VIEW の記録で確かめる）。"""
    seed = first_with_events()
    body = M.build_body(PROTOCOL, seed)
    A.advance_to(body.app, SMALL.body_runs_to)
    other, src = body.roles.other, body.roles.source
    fires = [p for p, u in body.log.activity() if u == other]
    probe = M.build_body(PROTOCOL, seed)
    for q in fires:
        A.advance_to(probe.app, q)
        x = A.clone(probe)
        x.log.keep = frozenset({RuntimeEventType.VIEW, RuntimeEventType.ACTIVITY})
        x.declare([A.Intervention(A.FB1, frozenset(M.block_targets(x.roles)))], label="F_blk")
        w = x.app.connections.export_state()[f"{other}.main->{src}"]["weight"]
        A.advance_to(x.app, q + 40)
        views = {(e.pulse, e.data["unit_id"]): e.data["drives"] for e in x.log.of(RuntimeEventType.VIEW)}
        assert [other, w] in views[(q + 1, src)] and w > 0
        later = [p for p, u in x.log.activity() if u == other and p < q + 40]
        if later:
            assert [other, 0.0] in views[(later[0] + 1, src)]
            return
    raise AssertionError("他の Unit が発火した後に、もう一度発火する区間がない")


# ---- 二経路近似（0035 §3）と、可塑性を止めた遮断・抑制の系の一致（O11） --------------------------------------

def test_two_path_is_the_0035_implementation() -> None:
    old = _load("analyze_0035_for_0036_test", ROOT / "experiments" / "0035_as1_state_dependent_feedback" / "analyze.py")
    n = 0
    for s in SYN:
        run = measured(s)["run"]
        for ev in run["events"]:
            args = (ev["sigma_t"], run["roles"]["source"], run["roles"]["receiver"], SMALL.horizon)
            assert AN.two_path(*args) == old.two_path(*args)
            n += 1
    assert n


def test_o11_detects_a_mismatch_with_the_two_path_approximation() -> None:
    for name in ("F_blk_cf", "N_blk_cf", "F_none_cf", "N_none_cf"):
        _tampered(lambda r, n=name: r["events"][0]["systems"][n].update(
            tau=None if r["events"][0]["systems"][n]["tau"] is not None else r["events"][0]["t"] + 1), "O11")


# ---- 符号の規則（README §3.2）と近道（§3.3） ---------------------------------------------------------

@pytest.mark.parametrize("tx,cx,ty,cy,sign", [
    (105, 160, 110, 160, "+"), (110, 160, 105, 160, "-"), (107, 160, 107, 160, "0"),
    (105, 160, None, 160, "+"), (None, 160, 105, 160, "-"), (None, 160, None, 160, "?"),
    (115, 160, None, 110, "?"),            # README §3.3 の例：τ_F ＝ t ＋ 15、F^{o:=N} は τ_N ＝ t ＋ 10 で打ち切り → s_chg は ？
    (None, 110, 110, 160, "-"),            # 同じ例の s_fix：F^{o:=N} は c ＝ τ_N で打ち切り、N は τ_N → −
    (105, 160, None, 110, "+"),            # c_Y ≥ τ_X なら ＋
    (None, 104, 105, 160, "?"),            # c_X ＜ τ_Y なら ？
])
def test_censored_sign_follows_the_rule(tx, cx, ty, cy, sign) -> None:
    assert AN.censored_sign(tx, cx, ty, cy) == sign


def test_the_sign_rule_is_the_0034_table_when_both_censor_at_t_plus_h() -> None:
    c = 160
    for tf in (None, 101, 130, 160):
        for tn in (None, 101, 130, 160):
            want = ("+" if tn > tf else "-" if tn < tf else "0") if tf and tn else "+" if tf else "-" if tn else "?"
            assert AN.censored_sign(tf, c, tn, c) == want


def test_the_shortcut_needs_the_reference_to_reach_tau_f() -> None:
    """README §3.3 の (1)：N が τ_F より先に止まれば、共通の区間で他の Unit の発火が同じでも、近道は成り立たない。"""
    for s in SYN:
        run = measured(s)["run"]
        for ev in run["events"]:
            tau_f, _ = AN._stop_f(run, ev)
            if tau_f is None or tau_f <= ev["t"] + 1:
                continue
            ev = copy.deepcopy(ev)
            n = ev["systems"]["N"]
            n["stopped_at"] = tau_f - 1
            n["firings"] = [x for x in run["body"]["activity"] if ev["t"] < x[0] <= tau_f - 1]
            q = AN.event_quantities(run, ev)
            assert q["shortcut_1"] is False and q["shortcut"] is False and q["shortcut_2"] is None
            return
    raise AssertionError("τ_F が t ＋ 2 以後に見つかる出来事がない")


def test_event_quantities_follow_the_pairs_and_the_saved_records() -> None:
    for s in SYN:
        run = measured(s)["run"]
        for ev in run["events"]:
            q = AN.event_quantities(run, ev)
            tau_f, _ = AN._stop_f(run, ev)
            assert q["tau"]["F"] == tau_f and q["censor"]["F"] == ev["t"] + SMALL.horizon
            for key, (x, y) in AN.PAIRS.items():
                assert q[f"s_{key}"] == AN.censored_sign(q["tau"][x], q["censor"][x], q["tau"][y], q["censor"][y])
                assert q[f"d_{key}"] == AN.difference(q["tau"][x], q["tau"][y])
            if q["s_e"] != "?" and q["s_fix"] != "?" and q["s_chg"] != "?" and None not in (q["d_e"], q["d_fix"], q["d_chg"]):
                assert q["d_e"] == q["d_fix"] + q["d_chg"]                    # 恒等式（三つの τ が既知のとき）


# ---- 個体の量・判定の算術（合成の入力） ------------------------------------------------------------

@pytest.mark.parametrize("key,want", list(PROTOCOL["judgment"]["per_individual"]["boundary_tests"].items()))
def test_the_individual_event_boundaries(key, want) -> None:
    n, k = (int(x.split("=")[1]) for x in key.split(","))
    assert AN._p_like(n, k) is want


def _ev(s_e="0", s_fix="0", s_blk="0", s_none="0", **kw):
    base = {"s_e": s_e, "s_fix": s_fix, "s_blk": s_blk, "s_none": s_none, "s_chg": "0", "s_fix_rev": s_fix, "s_cf": s_e,
            "s_hat": "0", "d_e": 0, "d_fix": 0, "d_chg": 0, "d_blk": 0, "d_none": 0, "d_cf": 0, "d_fix_rev": 0,
            "shortcut": False, "shortcut_1": False, "other_same_F_N": True}
    return {**base, **kw}


def _individual(monkeypatch, events):
    monkeypatch.setattr(AN, "event_quantities", lambda run, ev: events[ev["k"]])
    run = {"roles": {"source": "s1", "receiver": "s2", "other": "s3"}, "body": {"birth_units": {}, "activity": []},
           "events": [{"k": k} for k in range(len(events))]}
    return AN.individual(run)


def test_the_population_depends_only_on_the_body_event_count(monkeypatch) -> None:
    """A3：判定の母集団は本体の W の出来事の数（10 以上）だけで決まり、反実仮想の結果（打ち切り・符号）に依らない。"""
    for n in (9, 10, 11):
        for s in ("?", "+", "0"):
            v = _individual(monkeypatch, [_ev(s_e=s, s_fix=s)] * n)
            assert v["in_population"] is (n >= 10) and v["applicable"] is True
    assert _individual(monkeypatch, [])["applicable"] is False


def test_zero_evaluable_individuals_stay_in_the_population_and_fail(monkeypatch) -> None:
    v = _individual(monkeypatch, [_ev(s_e="?", s_fix="?")] * 10 + [_ev(s_e="+", s_fix="?")] * 2)
    assert v["in_population"] is True and v["n_i"] == 0 and v["k_i"] == 0 and v["r_i"] is None and v["P_i"] is False
    assert v["unevaluable"] == 12


def test_p_i_counts_only_evaluable_events(monkeypatch) -> None:
    ten = [_ev()] * 9 + [_ev(s_e="+", s_fix="-")]
    v = _individual(monkeypatch, ten + [_ev(s_e="?", s_fix="+")] * 3)
    assert (v["n_i"], v["k_i"], v["P_i"]) == (10, 1, True)
    v = _individual(monkeypatch, [_ev()] * 10 + [_ev(s_e="+", s_fix="-")])
    assert (v["n_i"], v["k_i"], v["P_i"]) == (11, 1, False)


def test_the_reported_control_counts_no_evaluable_event_separately(monkeypatch) -> None:
    """README §6.1（v0.2 の必須 1）：比べられる出来事が一つもない個体を、成立に数えない。全体は m・n ＝ 0 の数・成立の数を並べる。"""
    a = _individual(monkeypatch, [_ev(s_blk="?", s_none="?")] * 10)                     # 対照で評価できる出来事なし
    b = _individual(monkeypatch, [_ev()] * 9 + [_ev(s_blk="+", s_none="+")])           # 10 のうち 1 で違う
    c = _individual(monkeypatch, [_ev()] * 11 + [_ev(s_blk="+")])                      # 12 のうち 1（不成立）
    d = _individual(monkeypatch, [_ev(s_blk="+")] * 3)                                  # 母集団の外
    for v, want in ((a, (0, 0, False, True)), (b, (10, 1, True, False)), (c, (12, 1, False, False))):
        x = v["control"]["blk"]
        assert (x["n"], x["k"], x["P"], x["zero_evaluable"]) == want
    rc = AN.reported_control({"a": a, "b": b, "c": c, "d": d})
    assert {k: rc["blk"][k] for k in ("m", "no_evaluable_event", "count_P")} == {"m": 3, "no_evaluable_event": 1, "count_P": 1}
    assert {k: rc["none"][k] for k in ("m", "no_evaluable_event", "count_P")} == {"m": 3, "no_evaluable_event": 1, "count_P": 1}
    assert set(rc["blk"]["per_individual"]) == {"a", "b", "c"}


def test_r2_separates_the_small_denominator_successes(monkeypatch) -> None:
    """Gemini の監査（#162 の後）：1 ≤ n_i ≤ 9 では 1 つの符号の違いで P_i が成り立つので、その成立の数を分けて残す。"""
    small = _individual(monkeypatch, [_ev(s_e="?", s_fix="?")] * 8 + [_ev(), _ev(s_e="+", s_fix="0")])     # n ＝ 2、k ＝ 1
    large = _individual(monkeypatch, [_ev()] * 10 + [_ev(s_e="-", s_fix="+")] * 2)                           # n ＝ 12、k ＝ 2
    none = _individual(monkeypatch, [_ev(s_e="?", s_fix="?")] * 10)                                           # n ＝ 0
    assert (small["n_i"], small["P_i"], large["n_i"], large["P_i"], none["P_i"]) == (2, True, 12, True, False)
    r2 = AN.auxiliary({"a": small, "b": large, "c": none}, {})["R2"]
    assert (r2["P_i_with_n_i_1_to_9"], r2["P_i_with_n_i_10_or_more"], r2["population_with_n_i_below_10"]) == (1, 1, 2)
    assert r2["in_population"] == 3 and r2["unevaluable_in_population"] == 8 + 0 + 10


def test_the_five_sign_patterns() -> None:
    assert AN.pattern("+", "+", "+") == "no_change"
    assert AN.pattern("+", "+", "-") == "only_B_differs"
    assert AN.pattern("+", "-", "-") == "only_A_differs"
    assert AN.pattern("+", "-", "0") == "both_differ"
    assert AN.pattern("+", "-", "+") == "sign_return"                       # 設計メモ §6.4 の例


def _inds(n_pop: int, n_p: int, n_small: int = 0, n_na: int = 0) -> dict:
    d = {}
    for i in range(n_pop):
        d[f"p{i}"] = {"applicable": True, "in_population": True, "P_i": i < n_p}
    for i in range(n_small):
        d[f"s{i}"] = {"applicable": True, "in_population": False, "P_i": True}          # 母集団の外（数に入れない）
    for i in range(n_na):
        d[f"n{i}"] = {"applicable": False, "in_population": False, "P_i": False}
    return d


def test_judge_counts_only_the_population_and_thresholds() -> None:
    assert AN.judge(_inds(10, 9, 30, 20))["J_P"] == {"m": 10, "count_P_i": 9, "k": 9, "tail_probability": AN.binom_upper_tail(10, 9),
                                                     "status": "established"}
    assert AN.judge(_inds(10, 8, 30))["J_P"]["status"] == "not_established"
    assert AN.judge(_inds(55, 35))["J_P"]["status"] == "established" and AN.judge(_inds(55, 34))["J_P"]["status"] == "not_established"
    assert AN.judge(_inds(80, 48))["J_P"]["status"] == "established" and AN.judge(_inds(80, 47))["J_P"]["status"] == "not_established"


def test_r6_is_null_below_ten_and_kept_apart_from_the_inconclusive_status() -> None:
    for m in (0, 1, 9):
        out = AN.judge(_inds(m, m, 5, 5))
        assert out["J_P"]["status"] == "inconclusive" and out["J_P"]["k"] is None
        assert out["R6"]["computed"] is False and out["R6"]["interval"] is None and "not computed" in out["R6"]["reason"]
    out = AN.judge(_inds(10, 3))
    assert out["R6"]["computed"] is True and tuple(out["R6"]["interval"]) == AN.clopper_pearson(3, 10)


def test_k_of_m_matches_the_protocol_table() -> None:
    table = PROTOCOL["judgment"]["J_P"]["k_of_m"]
    assert sorted(table) == list(range(10, 81))
    for m, k in table.items():
        assert AN.k_of_m(m, 0.05) == k


def test_clopper_pearson_known_values() -> None:
    lo, hi = AN.clopper_pearson(16, 20)
    assert round(lo, 4) == 0.5634 and round(hi, 4) == 0.9427


def test_five_numbers() -> None:
    assert AN.five_numbers([]) is None
    assert AN.five_numbers([3]) == {"count": 1, "min": 3, "q1": 3, "median": 3, "q3": 3, "max": 3}
    assert AN.five_numbers([4, 1, 3, 2, 5])["median"] == 3


def test_the_analysis_of_the_synthetic_individuals_runs_through() -> None:
    runs = {s: measured(s) for s in SYN}
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=[])
    assert report["valid"] is True and set(report["judgment"]) == {"J_P"} and report["O1"]["status"] == "ok"
    assert set(report["reported_control"]) == {"blk", "none"} and set(report["individuals"]) == {str(s) for s in SYN}
    assert set(report["auxiliary"]) == {"R2", "R4_reverse", "R5_patterns", "R7_two_path", "R8_estimand_B", "R9_shortcut",
                                        "R10_weights"}


def test_the_records_are_consistent_with_each_other() -> None:
    """個体の量どうし・全体の数どうしの整合（値は見ない）。"""
    runs = {s: measured(s) for s in SYN}
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=[])
    inds, aux, rc = report["individuals"], report["auxiliary"], report["reported_control"]
    pop = {s for s, v in inds.items() if v["in_population"]}
    assert report["judgment"]["J_P"]["m"] == len(pop) == rc["blk"]["m"] == aux["R2"]["in_population"]
    for s, v in inds.items():
        run = runs[int(s)]["run"]
        assert v["events_in_window"] == len(run["events"]) and v["in_population"] == (len(run["events"]) >= 10)
        assert v["n_i"] + v["unevaluable"] == v["events_in_window"]
        assert v["P_i"] == AN._p_like(v["n_i"], v["k_i"])
        for key in ("blk", "none"):
            p = v["patterns"][key]
            assert p["denominator"] + p["unobservable"] == v["events_in_window"] == sum(p[x] for x in AN.PATTERNS) + p["unobservable"]
    assert aux["R2"]["P_i_with_n_i_1_to_9"] + aux["R2"]["P_i_with_n_i_10_or_more"] == report["judgment"]["J_P"]["count_P_i"]
    for key in ("blk", "none"):
        assert rc[key]["count_P"] == sum(1 for s in pop if inds[s]["control"][key]["P"])
        assert rc[key]["no_evaluable_event"] == sum(1 for s in pop if inds[s]["control"][key]["n"] == 0)


def test_an_invalid_individual_or_a_failed_o1_blocks_the_judgment() -> None:
    runs = {s: measured(s) for s in SYN}
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=["x"])
    assert report["valid"] is False and report["judgment"] is None and "reported_control" not in report
    s = first_with_events()
    runs[s]["run"]["events"][0]["systems"]["N_prime"]["tau"] = -1
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=[])
    assert report["valid"] is False and report["judgment"] is None and "O7" in report["failed_checks"][str(s)]


# ---- O4（README §7 の O4 の詳細。v0.2 の必須 2）：手で作った記録で ----------------------------------------------

def _o4_run(stop_x: dict, *, x_sensory=None, x_pending=None) -> dict:
    """手で作った 1 出来事の記録：t ＝ 100、e は Pulse 101 の受の Receptor への予約（rid 7）。本体の次の意図は τ_F ＝ 115
    （その意図の予約は Pulse 116。区間 W は e の Pulse 31〜110 なので、出来事は t ＝ 100 の 1 つ）。系 X の止まった Pulse を名前ごとに与える。最初の意図で作られる新しい予約は pending_stop に入れる。"""
    roles = {"source": "s1", "receiver": "s2", "other": "s3", "consequence_receptor": "receptor.x2", "source_receptor": "receptor.x1"}
    e_row = [7, 100, "receptor.x2", 101, "consequence"]
    body = {"intents": [[100, "d100"], [115, "d115"]], "sensory": [[101, "receptor.x2"], [116, "receptor.x2"]]}
    systems = {}
    for name in M.SYSTEMS:
        stop = stop_x.get(name, 115)
        cancelled = name in M.E_CANCELLED
        pending = [] if cancelled else [e_row]
        systems[name] = {"stopped_at": stop, "pending_branch": copy.deepcopy(pending),
                         "sensory": [] if cancelled else [[101, "receptor.x2"]],
                         "pending_stop": [[99, stop, "receptor.x2", stop + 1, "consequence"]]}
    if x_sensory:
        for name, s in x_sensory.items():
            systems[name]["sensory"] = s
    if x_pending:
        for name, p in x_pending.items():
            systems[name]["pending_branch"] = p
    return {"roles": roles, "plan": {"window_first": 31, "window_last": 110, "horizon": 60}, "body": body,
            "events": [{"t": 100, "intent_delta_id": "d100", "e": {"rid": 7, "pulse": 101, "receptor": "receptor.x2", "origin": "d100"},
                        "body_pending": [e_row], "systems": systems}]}


def test_o4_accepts_earlier_and_later_first_intents_and_their_new_reservations() -> None:
    """介入で最初の意図が早まる（t ＋ 10）・遅れる（t ＋ 25）系があっても、O4 は狙いどおりの差（新しい予約）を違反にしない。"""
    out: list = []
    AN._o4(_o4_run({"F_blk": 110, "N_blk": 125, "F_fixN": 110, "N_fixF": 112, "F_cf": 130}), out)
    assert out == []
    out = []
    AN._o4(_o4_run({}), out)
    assert out == []


def test_o4_detects_a_wrong_branch_pending_or_sensory_list() -> None:
    e_row = [7, 100, "receptor.x2", 101, "consequence"]
    for kw in ({"x_pending": {"N_blk": [e_row]}},                                       # e を取り消していない
               {"x_pending": {"F_blk": []}},                                           # e を届ける系から e が消えた
               {"x_sensory": {"F_blk": []}},                                            # e の感覚の出来事がない
               {"x_sensory": {"N": [[101, "receptor.x2"]]}},                           # 取り消したのに e の感覚の出来事がある
               {"x_sensory": {"F_fixN": [[101, "receptor.x2"], [105, "receptor.x3"]]}}):  # 予約にない感覚の出来事
        out: list = []
        AN._o4(_o4_run({"F_blk": 110}, **kw), out)
        assert out, kw


# ---- 改ざん・欠けの検出（実物の記録で） ---------------------------------------------------------------

def _tampered(f, check: str, seed: int | None = None) -> None:
    seed = seed or first_with_events()
    data = measured(seed)
    f(data["run"])
    got = failures(data, seed)
    assert check in got, (check, sorted(got))


def _ev0(r, name=None):
    ev = r["events"][0]
    return ev if name is None else ev["systems"][name]


def test_o2_and_o3_detect_tampering() -> None:
    _tampered(lambda r: r["body"]["sensory"].append([r["plan"]["body_runs_to"], r["roles"]["source_receptor"]]), "O2")
    _tampered(lambda r: r["body"]["intents"].pop(), "O2")
    _tampered(lambda r: r["clone_check"]["sigma_clone"]["units"][r["roles"]["source"]].update(activity=0.123), "O3")


def test_o4_detects_tampering_in_the_records() -> None:
    _tampered(lambda r: _ev0(r, "N_cf").update(pending_branch=copy.deepcopy(_ev0(r)["body_pending"])), "O4")
    _tampered(lambda r: _ev0(r, "F_none")["sensory"].append([_ev0(r)["t"] + 1, r["roles"]["consequence_receptor"]]), "O4")
    _tampered(lambda r: r["events"].pop(0), "O4")
    _tampered(lambda r: _ev0(r)["e"].update(pulse=_ev0(r)["e"]["pulse"] + 1), "O4")


def test_o5_detects_wrong_censoring_stops_and_tau() -> None:
    _tampered(lambda r: _ev0(r, "F_fixN").update(censor=_ev0(r, "F_fixN")["censor"] + 1), "O5")
    _tampered(lambda r: _ev0(r, "N_fixF").update(censor=_ev0(r, "N_fixF")["censor"] - 1), "O5")
    _tampered(lambda r: _ev0(r).update(n_branch_sigma_sha256="0" * 64), "O5")
    _tampered(lambda r: _ev0(r, "F_blk").update(stopped_at=_ev0(r, "F_blk")["stopped_at"] + 1), "O5")
    src = measured(first_with_events())["run"]["roles"]["source"]

    def drop_source(r):
        s = _ev0(r, "N_blk")
        if s["tau"] is not None:
            s["firings"] = [x for x in s["firings"] if x != [s["tau"], src]]
        else:
            s["firings"] = sorted(s["firings"] + [[_ev0(r)["t"] + 1, src]], key=lambda x: x[0])
    _tampered(drop_source, "O5")
    _tampered(lambda r: r["events"][0]["plain"]["F_cf"].update(stopped_at=_ev0(r)["t"]), "O5")


def test_o7_detects_tampering() -> None:
    _tampered(lambda r: r["rerun"]["intents"].pop(), "O7")
    _tampered(lambda r: r["rerun_plain"].update(sigma_end_sha256="0" * 64), "O7")
    _tampered(lambda r: _ev0(r, "N_prime").update(sigma_stop_sha256="0" * 64), "O7")
    for name in M.PLAIN:
        _tampered(lambda r, n=name: r["events"][0]["plain"][n]["firings"].append([_ev0(r, n)["stopped_at"], "s1"]), "O7")


def test_o8_detects_a_wrong_schedule_or_unscheduled_firings() -> None:
    _tampered(lambda r: _ev0(r, "F_fixN")["control"]["schedule"].append(_ev0(r, "F_fixN")["censor"]), "O8")
    _tampered(lambda r: _ev0(r, "F_none")["control"].update(until=_ev0(r)["t"] + 1), "O8")
    _tampered(lambda r: _ev0(r, "N_fixF")["control"].update(after=_ev0(r)["t"] - 1), "O8")
    _tampered(lambda r: _ev0(r, "F_fixF")["firings"].append([_ev0(r, "F_fixF")["stopped_at"], r["roles"]["other"]])
              if not any(p == _ev0(r, "F_fixF")["stopped_at"] and u == r["roles"]["other"] for p, u in _ev0(r, "F_fixF")["firings"])
              else _ev0(r, "F_fixF")["firings"].remove([_ev0(r, "F_fixF")["stopped_at"], r["roles"]["other"]]), "O8")
    _tampered(lambda r: _ev0(r, "F_none")["control"]["overrides"].append([_ev0(r)["t"] + 1, "fire"]), "O8")
    _tampered(lambda r: _ev0(r, "F_blk").update(control={"schedule": [], "after": 0, "until": 0, "overrides": []}), "O8")


def test_o9_detects_unblocked_or_missing_records() -> None:
    _tampered(lambda r: _ev0(r, "F_blk")["masked"][0][1].__setitem__(0, 0.001), "O9")
    _tampered(lambda r: _ev0(r, "N_blk_cf")["masked"].pop(), "O9")
    _tampered(lambda r: _ev0(r, "F_blk")["masked"][0][2].append("s1.main->s2"), "O9")
    _tampered(lambda r: _ev0(r, "F_blk")["history"].append(_ev0(r, "F_blk")["history"][0]), "O9")
    _tampered(lambda r: _ev0(r, "F_cf").update(masked=[]), "O9")


def test_o10_detects_a_broken_identity() -> None:
    _tampered(lambda r: _ev0(r, "F_fixF").update(sigma_stop_sha256="0" * 64), "O10")
    _tampered(lambda r: _ev0(r, "F_prime")["firings"].append([_ev0(r, "F_prime")["stopped_at"], r["roles"]["other"]]), "O10")


def test_o12_detects_moving_or_missing_frozen_weights() -> None:
    def move(r):
        pw = _ev0(r, "F_cf")["pulse_weights"]
        k = next(iter(pw[0][1]))
        pw[0][1][k] += 1e-9
    _tampered(move, "O12")
    _tampered(lambda r: _ev0(r, "N_none_cf")["pulse_weights"].pop(), "O12")
    _tampered(lambda r: _ev0(r, "F_blk").update(pulse_weights=[]), "O12")


def test_structure_detects_extra_fields_and_wrong_roles() -> None:
    _tampered(lambda r: r.update(judgment={"J_P": True}), "structure")
    _tampered(lambda r: _ev0(r).update(s_fix="+"), "structure")
    _tampered(lambda r: _ev0(r, "N").update(s_e="+"), "structure")
    _tampered(lambda r: _ev0(r)["systems"].pop("F_cf"), "structure")
    _tampered(lambda r: r["events"][0]["plain"].pop("F_blk"), "structure")
    _tampered(lambda r: r["roles"].update(source="s9"), "structure")
    _tampered(lambda r: r["plan"].update(horizon=61), "structure")


def test_o6_rejects_seeds_outside_the_range_or_seen() -> None:
    for seed in (28001, 28201, 29001, 29101):
        out: list = []
        AN._o6(seed, "synthetic", out)
        assert out, seed
    out = []
    AN._o6(29201, "synthetic", out)
    assert out == []


def test_meta_blind_must_match_the_mode() -> None:
    s = SYN[0]
    data = measured(s)
    data["meta"]["blind"] = "no"
    assert "structure" in failures(data, s)
    assert AN.check_seed(dict(measured(s), meta=dict(measured(s)["meta"], blind=True)), "formal", s, SMALL)["structure"]


# ---- 一度限りの実行（guard と run.execute。dummy の計算。0035 と同じ） ------------------------------------------

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
    assert _exec(repo, out, GUARD_SEEDS[:2])["completed"] == GUARD_SEEDS[:2]
    with pytest.raises(R.G.GuardError):
        _exec(repo, out, GUARD_SEEDS[:1])

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
        _exec(repo, out2, GUARD_SEEDS[5:6])


def test_formal_requires_the_measurement_commit_and_the_range(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    with pytest.raises(R.G.GuardError):
        R.execute("formal", [29001], tmp_path / "o", repo, None, runner=_dummy, executor_factory=SerialExecutor)
    for seed in (29001, 29101, 28201):
        with pytest.raises(R.G.GuardError):
            R.execute("synthetic", [seed], tmp_path / f"o{seed}", repo, _git(repo, "rev-parse", "HEAD"), runner=_dummy,
                      executor_factory=SerialExecutor)
        assert not (tmp_path / f"o{seed}").exists()


def test_records_state_and_the_synthetic_pipeline_through_run_and_analyze(repo, tmp_path, monkeypatch) -> None:
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
    assert report["valid"] is True and report["judgment"]["J_P"]["status"] == "inconclusive"   # 3 個体なので m ＜ 10
    assert report["R6"]["computed"] is False


# ---- smoke の盲検：現象の数値を保存しない（0035 と同じ） -------------------------------------------------

FORBIDDEN_KEYS = ((AN.RUN_KEYS - {"seed", "plan", "roles"}) | AN.BODY_KEYS | AN.EVENT_KEYS | AN.SYSTEM_KEYS | AN.RERUN_KEYS
                  | AN.RERUN_PLAIN_KEYS
                  | {"run", "s_e", "d_e", "s_fix", "s_blk", "s_hat", "n_i", "k_i", "r_i", "P_i", "J_P", "R6",
                     "judgment", "individuals", "auxiliary", "reported_control"})
META_KEYS = {"experiment", "kind", "mode", "seed", "measurement_commit", "protocol_sha256", "protocol", "manifest", "blind"}


def _keys(x, path=()):
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
NUMERIC_OK = {"seed", "raw_file_bytes", "max_workers", "pid"}


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
    for d in [out, *out.rglob("*")]:
        assert d.stat().st_mtime == R.CONCEALED_MTIME, d
    for d in sorted((out / R.G.SEEDS_DIR).iterdir()):
        start = json.loads((d / R.G.START).read_text(encoding="utf-8"))
        finish = json.loads((d / R.G.FINISH).read_text(encoding="utf-8"))
        assert start["started_at"] == R.BLINDED_TIME and finish["finished_at"] == R.BLINDED_TIME
        assert finish["seconds"] is None and start["max_workers"] == 1
        for rec in (start, finish):
            assert not ISO_TIME.search(json.dumps(rec)), rec
            assert _numeric_keys(rec) <= NUMERIC_OK, _numeric_keys(rec)


def test_blind_execution_stores_no_phenomenon_values(repo, tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    seeds = [first_with_events(), next(s for s in SYN if not measured(s)["run"]["events"])]
    workers: list[int] = []
    done = _blind_exec(repo, out, seeds, workers=workers)
    assert done["completed"] == sorted(seeds) and workers == [1]
    assert capsys.readouterr().out == ""
    _assert_no_timing(out)
    files = sorted(p for p in out.rglob("*") if p.is_file() and p != out / R.G.LOCK)
    assert {p.name for p in files} == {R.G.START, R.G.FINISH, R.G.RAW} and len(files) == 3 * len(seeds)
    for p in files:
        data = json.loads(gzip.decompress(p.read_bytes()) if p.name.endswith(".gz") else p.read_bytes())
        bad = {k for _, k in _keys(data) if k in FORBIDDEN_KEYS}
        assert not bad, (p, bad)
        if p.name == R.G.RAW:
            s = data["meta"]["seed"]
            assert set(data) == {"meta", "blind"} and set(data["meta"]) == META_KEYS
            assert data["blind"]["checks"] == {k: "ok" for k in AN.CHECK_NAMES}
            assert set(AN.CHECK_NAMES) == {"structure", *(f"O{i}" for i in range(2, 13))}
            again = {"meta": data["meta"], "run": M.measure_seed(PROTOCOL, s, SMALL)}
            canonical = json.dumps(json.loads(json.dumps(again)), separators=(",", ":"), sort_keys=True).encode("utf-8")
            assert data["blind"]["raw_sha256"] == R.G.sha256_bytes(canonical)


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
    finish = json.loads((R.G.seed_dir(out, GUARD_SEEDS[1]) / R.G.FINISH).read_text(encoding="utf-8"))
    assert finish["reason"] == "RuntimeError"
    assert all("1234" not in p.read_bytes().decode("utf-8", "replace") for p in out.rglob("*") if p.is_file())
    assert capsys.readouterr().out == ""
    _assert_no_timing(out)


def test_blinded_record_marks_a_failed_check_without_reasons() -> None:
    s = first_with_events()
    for tamper, check in ((lambda r: _ev0(r, "N").update(pending_branch=copy.deepcopy(_ev0(r)["body_pending"])), "O4"),
                          (lambda r: _ev0(r).update(n_branch_sigma_sha256="0" * 64), "O5"),
                          (lambda r: _ev0(r, "F_fixF").update(sigma_stop_sha256="0" * 64), "O10")):
        data = measured(s)
        data["meta"]["blind"] = True
        tamper(data["run"])
        rec = R.blinded(data, "synthetic", s, SMALL)
        assert set(rec) == {"meta", "blind"} and rec["blind"]["checks"][check] == "fail"


def test_smoke_report_reads_blinded_records_and_rechecks_o6() -> None:
    s = SYN[0]
    data = measured(s)
    data["meta"]["blind"] = True
    rec = R.blinded(data, "synthetic", s, SMALL)
    rec["meta"]["mode"] = "smoke"
    report = AN.analyze_runs({s: rec}, "smoke", o1=[])
    assert set(report) == {"mode", "O1", "checks", "valid"} and report["checks"][str(s)]["O6"] == "fail"
    missing = copy.deepcopy(rec)
    missing["blind"]["checks"].pop("O12")
    assert AN.check_blinded(missing, s, "smoke") == {k: "fail" for k in AN.CHECK_NAMES}


def test_smoke_must_be_blind_and_formal_must_not(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    commit = _git(repo, "rev-parse", "HEAD")
    for mode, kw in (("smoke", {"blind": False}), ("formal", {"blind": True}), ("smoke", {"check_plan": SMALL})):
        out = tmp_path / f"o_{mode}_{sorted(kw)[0]}"
        with pytest.raises(R.G.GuardError):
            R.execute(mode, GUARD_SEEDS[:1], out, repo, commit, runner=_dummy, executor_factory=SerialExecutor, **kw)
        assert not out.exists()


# ---- O1 の証拠（0035 と同じ） ---------------------------------------------------------------------------

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
    assert rec["exit_code"] == 0 and calls[0][0][1:] == ["-m", "pytest", "-q", *AN.CONTRACT_TESTS]
    assert AN.o1_check(out, commit) == []
    R.record_contract_tests(repo, out, commit, run=lambda *a, **k: pytest.fail("走らせ直さない"))


def _never(*a, **k):
    raise AssertionError("O1 が成り立たないのに、契約テストの実行か seed の計算に進んだ")


@pytest.mark.parametrize("name,tamper", [
    ("終了コード", lambda r: r.update(exit_code=1)),
    ("結果の行", lambda r: r.update(summary="1 failed, 198 passed in 50.0s")),
    ("テストのファイルの SHA-256", lambda r: r["test_files_sha256"].update({AN.CONTRACT_TESTS[1]: "0" * 64})),
    ("走らせたコマンド", lambda r: r.update(command=["python", "-m", "pytest", "-q", AN.CONTRACT_TESTS[0]])),
    ("測定の commit", lambda r: r.update(measurement_commit="0" * 40)),
])
def test_a_broken_o1_record_stops_before_any_seed_is_started(repo, tmp_path, monkeypatch, name, tamper) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    commit = _o1_repo(repo)
    R.record_contract_tests(repo, out, commit, run=lambda *a, **k: _Proc(0, "199 passed in 50.0s\n"))
    path = out / AN.O1_FILE
    rec = json.loads(path.read_text(encoding="utf-8"))
    tamper(rec)
    path.write_text(json.dumps(rec), encoding="utf-8")
    with pytest.raises(R.G.GuardError):
        R.start("synthetic", GUARD_SEEDS[:2], out, repo, commit, run=_never, runner=_never, executor_factory=SerialExecutor)
    assert not (out / R.G.SEEDS_DIR).exists()


def test_a_valid_o1_record_lets_start_run_the_seeds(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    commit = _o1_repo(repo)
    R.record_contract_tests(repo, out, commit, run=lambda *a, **k: _Proc(0, "199 passed in 50.0s\n"))
    done = R.start("synthetic", GUARD_SEEDS[:2], out, repo, commit, run=_never, runner=_dummy, executor_factory=SerialExecutor)
    assert done["completed"] == GUARD_SEEDS[:2]


def test_main_goes_through_start() -> None:
    src = inspect.getsource(R.main)
    assert "start(mode, seeds, out, REPO, args.measurement_commit)" in src and "execute(" not in src


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
    gone = copy_to("gone")
    (R.G.seed_dir(gone, GUARD_SEEDS[1]) / R.G.RAW).unlink()
    assert AN.verify_results_copy(out, gone)
