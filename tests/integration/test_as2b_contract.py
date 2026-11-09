"""AS2b の最小の研究用の道具の契約テスト（docs/as2b-minimal-implementation-contract.md の ②a）。

正式な実験ではない。ここで走らせる seed（9101〜9106）は、道具の確認だけに使う（AS1 の道具の確認の 9001〜9006、
これまでの実験の seed、関門の合成の seed 31001〜31040 とは重ならない）。確かめるのは契約（EC・WB・CT）の構造だけで、
選択の数・割合・時間の変化・規則 c の違う本体の差は、計算も表示もしない。関門の組（0038 の宣言）の値では走らせない。
"""

import copy
import hashlib
import importlib.util
import inspect
import json
import random
from pathlib import Path

import pytest

from anima_ll.domain.model.activity import ActivityEvent, Drive
from anima_ll.domain.model.delta import DeltaKind, ProposedDelta
from anima_ll.domain.model.pulse import PulseContext
from anima_ll.domain.model.receptive_view import ReceptiveView
from anima_ll.domain.model.runtime_event import RuntimeEventType
from anima_ll.domain.model.unit_step import UnitStepResult

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = _load("as2b_tools_test", ROOT / "experiments" / "as2b_choice" / "as2b.py")
GATE_DIR = ROOT / "experiments" / "0038_as2b_forward_gate"
G = _load("as2b_gate_test", GATE_DIR / "gate.py")
AN = _load("as2b_analysis_test", GATE_DIR / "analysis.py")

TOOL_SEEDS = (9101, 9102, 9103, 9104, 9105, 9106)
SEEDS = TOOL_SEEDS[:3]
L = 2
# 道具の確認用の予定（関門の宣言の値ではない）：窓が広く、決定が起きやすい形
TEST_SCHEDULE = M.TrialSchedule.periodic(first=30, spacing=80, count=14, offset=2, length=60)
N_TEST = TEST_SCHEDULE.last_outcome_pulse(L)
H = 150


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)


def run(seed: int, until: int, **kw):
    kw.setdefault("schedule", TEST_SCHEDULE)
    system = M.build(seed, **kw)
    M.advance_to(system.app, until)
    return system


def intent_events(log):
    return [e.data for e in log.of(RuntimeEventType.DELTA) if e.data["kind"] == DeltaKind.INTENT]


def brain_view(system):
    s = M.sigma(system)
    return {k: s[k] for k in ("units", "connections", "drives")}


# ---- 試験用の部品（スタブ）：出口の論理だけを確かめる ------------------------------

class StubUnit:
    """台本の Pulse にだけ発火する。relay に当たる提案を毎回 1 つ出す（EC-6 の確かめ）。"""

    def __init__(self, uid: str, fires) -> None:
        self._uid = uid
        self.fires = set(fires)
        self.ticks = 0

    @property
    def unit_id(self) -> str:
        return self._uid

    def tick(self, view, context) -> UnitStepResult:
        self.ticks += 1
        relay = (ProposedDelta(kind=DeltaKind.CONTENT, payload=f"{self._uid}@{context.pulse}"),)
        if context.pulse in self.fires:
            return UnitStepResult(proposed_deltas=relay, activity=ActivityEvent(self._uid, context.pulse))
        return UnitStepResult(proposed_deltas=relay)

    def handle_kernel_result(self, task, result, context):
        return UnitStepResult()

    def export_state(self):
        return {"ticks": self.ticks}

    def import_state(self, state) -> None:
        self.ticks = state["ticks"]


ACTION = {"u1": "A1", "u2": "A2"}


def _view(uid, t):
    return ReceptiveView(unit_id=uid, snapshot_id=f"snap-{t}", pulse=t, deltas=(), drives=())


def _ctx(t):
    return PulseContext(pulse=t, now=float(t), delta_time=1.0)


def drive(scripts, windows, pulses, order=("u1", "u2"), action_of=ACTION):
    decider = M.I2Decider(windows, action_of)
    taps = {u: M.CompetitionTap(StubUnit(u, scripts[u]), decider) for u in ("u1", "u2")}
    intents, relays = [], []
    for t in range(1, pulses + 1):
        for u in (order(t) if callable(order) else order):
            step = taps[u].tick(_view(u, t), _ctx(t))
            for d in step.proposed_deltas:
                if d.kind == DeltaKind.INTENT:
                    intents.append((t, u, d.payload, d.output_port))
                else:
                    relays.append((t, u, d.payload))
            assert decider.reports_pulse in (None, t)
        assert decider.reports == {} and decider.reports_pulse is None        # Pulse のあいだでは報告は空（EC-7）
    return decider, intents, relays


def oracle(scripts, windows, pulses, action_of=ACTION):
    """契約 §2.5 の手順を、決定の部品とは独立に書いたもの。"""
    records, intents = [], []
    for k, a, b in windows:
        if a > pulses:
            break
        out = None
        for t in range(a, min(b, pulses) + 1):
            f1, f2 = t in scripts["u1"], t in scripts["u2"]
            if f1 and f2:
                out = (k, M.TIE, t, None)
                break
            if f1 or f2:
                u = "u1" if f1 else "u2"
                out = (k, action_of[u], t, u)
                break
        if out is None and b <= pulses:
            out = (k, M.NONE, None, None)
        if out is not None:
            records.append(out)
            if out[3] is not None and out[2] + 1 <= pulses:
                intents.append((out[2] + 1, out[3], action_of[out[3]]))
    return records, intents


WINDOWS = ((1, 5, 10), (2, 20, 25), (3, 30, 34), (4, 40, 44), (5, 50, 52), (6, 60, 62))
SCRIPT = {
    # 窓の外（2・15・3・27）、窓の始まりの単独の先着（5）、勝ちの後のもう一方（6）と同じ源（8）、最初の発火の同時（20）と
    # 引き分けの後の発火（22）、発火なしの窓（30〜34）、窓の終わりの先着（44）と窓の外の直後（45）、続く窓の先着（50）と
    # その後（51）、最後の窓の終わり（62）
    "u1": {2, 5, 8, 15, 20, 22, 45, 51, 62},
    "u2": {3, 6, 20, 27, 44, 50},
}


def _records_view(decider):
    return [(r["window"], r["outcome"], r["decision_pulse"], r["winner_unit"]) for r in decider.records]


# ---- CT-E1〜E3・E9（スタブ） --------------------------------------------------------

def test_ct_e3_scripted_cases_match_the_independent_procedure_and_make_no_extra_intent() -> None:
    decider, intents, _ = drive(SCRIPT, WINDOWS, 70)
    exp_records, exp_intents = oracle(SCRIPT, WINDOWS, 70)
    assert _records_view(decider) == exp_records
    assert [(t, u, p) for t, u, p, _port in intents] == exp_intents
    assert [r[1] for r in exp_records] == ["A1", M.TIE, M.NONE, "A2", "A2", "A1"]   # 台本どおりの場合を含む
    wins = [r for r in decider.records if r["winner_unit"] is not None]
    assert len(intents) == len(wins)                                         # 勝ちの窓 1 つに意図ちょうど 1 つ
    assert all(port == M.INTENT_PORT for *_x, port in intents)
    assert len({t for t, *_x in intents}) == len(intents)                   # 1 Pulse に高々 1 つ
    for (t, u, payload, _port), r in zip(intents, wins):
        assert (t, u, payload) == (r["decision_pulse"] + 1, r["winner_unit"], ACTION[r["winner_unit"]])
        assert r["emitted"] and r["emit_pulse"] == t
    assert decider.pending is None


@pytest.mark.parametrize("order", [("u1", "u2"), ("u2", "u1"), lambda t: ("u1", "u2") if t % 2 else ("u2", "u1")],
                         ids=["u1-first", "u2-first", "alternating"])
def test_ct_e1_the_decision_does_not_depend_on_the_call_order(order) -> None:
    base = drive(SCRIPT, WINDOWS, 70)
    other = drive(SCRIPT, WINDOWS, 70, order=order)
    assert other[0].records == base[0].records
    assert [(t, u, p) for t, u, p, _ in other[1]] == [(t, u, p) for t, u, p, _ in base[1]]


def test_ct_e1_e3_random_scripts_in_both_orders_match_the_independent_procedure() -> None:
    rng = random.Random("as2b-ct-e3-scripts")       # 台本を作るだけの乱数（実験の個体ではない）
    for _ in range(300):
        scripts = {u: {t for t in range(1, 121) if rng.random() < rng.choice((0.05, 0.15, 0.4))} for u in ("u1", "u2")}
        exp = oracle(scripts, ((1, 10, 30), (2, 40, 44), (3, 50, 50), (4, 60, 90), (5, 100, 118)), 120)
        for order in (("u1", "u2"), ("u2", "u1")):
            d, intents, _ = drive(scripts, ((1, 10, 30), (2, 40, 44), (3, 50, 50), (4, 60, 90), (5, 100, 118)), 120, order)
            assert _records_view(d) == exp[0]
            assert [(t, u, p) for t, u, p, _ in intents] == exp[1]


def test_ct_e2_swapping_the_two_sources_mirrors_the_outcomes() -> None:
    d, intents, _ = drive(SCRIPT, WINDOWS, 70)
    mirrored = {"u1": SCRIPT["u2"], "u2": SCRIPT["u1"]}
    dm, intents_m, _ = drive(mirrored, WINDOWS, 70)
    swap = {"A1": "A2", "A2": "A1", M.TIE: M.TIE, M.NONE: M.NONE}
    other = {"u1": "u2", "u2": "u1", None: None}
    assert [(r["window"], swap[r["outcome"]], r["decision_pulse"], other[r["winner_unit"]]) for r in d.records] == \
           [(r["window"], r["outcome"], r["decision_pulse"], r["winner_unit"]) for r in dm.records]
    assert [(t, other[u], swap[p]) for t, u, p, _ in intents] == [(t, u, p) for t, u, p, _ in intents_m]


@pytest.mark.parametrize("stop", [10, 11], ids=["P_end=b_k", "P_end=b_k+1"])
def test_ct_e3_e10_a_win_on_the_last_pulse_is_carried_over_not_lost(stop) -> None:
    """勝ちが窓の終わり b_k ＝ 10 に決まる台本。b_k で止めると未発行の予定、b_k ＋ 1 で止めると発行済み（申し送り ②）。"""
    script = {"u1": {10}, "u2": {12}}
    decider, intents, _ = drive(script, ((1, 5, 10),), stop)
    wins = [r for r in decider.records if r["winner_unit"] is not None]
    carried = [r for r in wins if not r["emitted"]]
    assert len(wins) == 1 and wins[0]["decision_pulse"] == 10
    assert len(intents) + len(carried) == len(wins)
    if stop == 10:
        assert intents == [] and decider.pending == {"unit": "u1", "action": "A1", "pulse": 11, "record": 0}
    else:
        assert [(t, u, p) for t, u, p, _ in intents] == [(11, "u1", "A1")] and decider.pending is None and carried == []


def test_ct_e9_missing_or_duplicate_reports_and_a_missed_emission_stop_the_run() -> None:
    decider = M.I2Decider(WINDOWS, ACTION)
    taps = {u: M.CompetitionTap(StubUnit(u, SCRIPT[u]), decider) for u in ("u1", "u2")}
    taps["u1"].tick(_view("u1", 1), _ctx(1))
    with pytest.raises(M.I2Error):                                        # 同じ Pulse に二度
        taps["u1"].tick(_view("u1", 1), _ctx(1))
    decider2 = M.I2Decider(WINDOWS, ACTION)
    taps2 = {u: M.CompetitionTap(StubUnit(u, SCRIPT[u]), decider2) for u in ("u1", "u2")}
    taps2["u1"].tick(_view("u1", 1), _ctx(1))
    with pytest.raises(M.I2Error):                                        # Pulse 1 の報告がそろわないまま Pulse 2
        taps2["u1"].tick(_view("u1", 2), _ctx(2))
    decider3 = M.I2Decider(WINDOWS, ACTION)
    taps3 = {u: M.CompetitionTap(StubUnit(u, SCRIPT[u]), decider3) for u in ("u1", "u2")}
    for t in range(1, 6):                                                 # Pulse 5 に u1 が勝つ
        for u in ("u1", "u2"):
            taps3[u].tick(_view(u, t), _ctx(t))
    assert decider3.pending == {"unit": "u1", "action": "A1", "pulse": 6, "record": 0}
    taps3["u2"].tick(_view("u2", 6), _ctx(6))                             # 勝った源の口を Pulse 6 に呼ばない
    with pytest.raises(M.I2Error):
        taps3["u2"].tick(_view("u2", 7), _ctx(7))
    with pytest.raises(ValueError):
        M.I2Decider(WINDOWS, {"u1": "A1", "u2": "A1"})


def test_ct_e9_the_decider_reads_only_unit_pulse_and_firing() -> None:
    assert list(inspect.signature(M.I2Decider.report).parameters) == ["self", "unit_id", "pulse", "fired"]
    assert list(inspect.signature(M.I2Decider.due).parameters) == ["self", "unit_id", "pulse"]
    assert list(inspect.signature(M.I2Decider.emitted).parameters) == ["self", "unit_id", "pulse"]
    system = M.build(SEEDS[0], schedule=TEST_SCHEDULE)
    held = list(vars(system.decider).values())
    assert not any(isinstance(v, (M.AS2bWorld, M.AS2bEffector)) for v in held)          # 世界への参照なし（EC-10）
    assert set(vars(system.decider)) == {"windows", "action_of", "cursor", "pending", "reports_pulse", "reports", "records"}


def test_ct_e6_the_tap_keeps_the_inner_proposals() -> None:
    _, _intents, relays = drive(SCRIPT, WINDOWS, 70)
    assert relays == [(t, u, f"{u}@{t}") for t in range(1, 71) for u in ("u1", "u2")]


# ---- CT-E4（本物の Unit） ------------------------------------------------------------

def test_ct_e4_a_wrapped_unit_evolves_exactly_like_the_unwrapped_unit() -> None:
    system = M.build(SEEDS[0], schedule=TEST_SCHEDULE)
    real = system.taps()[0]._inner
    plain, wrapped_inner = copy.deepcopy(real), copy.deepcopy(real)
    decider = M.I2Decider(((1, 1, 400),), {real.unit_id: "A1", "partner": "A2"})
    tap = M.CompetitionTap(wrapped_inner, decider)
    partner = M.CompetitionTap(StubUnit("partner", ()), decider)
    rng = random.Random("as2b-ct-e4-drives")
    for t in range(1, 401):
        drives = tuple(Drive("x", real.unit_id, rng.choice((0.0, 0.005, 0.01, 1.0)), t - 1) for _ in range(rng.randint(0, 2)))
        view = ReceptiveView(unit_id=real.unit_id, snapshot_id=f"s{t}", pulse=t, deltas=(), drives=drives)
        a = plain.tick(view, _ctx(t))
        b = tap.tick(view, _ctx(t))
        partner.tick(_view("partner", t), _ctx(t))
        assert a.activity == b.activity
        assert a.proposed_deltas == tuple(d for d in b.proposed_deltas if d.kind != DeltaKind.INTENT)
        assert plain.export_state() == tap.export_state() == wrapped_inner.export_state()


# ---- 設計図・役・乱数（CT-E7・CT-E8） ---------------------------------------------------

def test_manifest_is_the_as1_manifest_c0_plus_effector_and_intent_projections() -> None:
    c0, as1 = M.AS1.c0_manifest_raw(), M.AS1.as1_manifest_raw()
    assert {k: v for k, v in as1.items() if k not in ("interfaces", "projections")} == \
           {k: v for k, v in c0.items() if k not in ("interfaces", "projections")}
    assert as1["projections"][len(c0["projections"]):] == [{"from": f"{u}.intent", "to": M.EFFECTOR_ID} for u in M.UNITS]


@pytest.mark.parametrize("seed", TOOL_SEEDS)
def test_roles_are_a_permutation_from_a_named_stream_and_recorded(seed) -> None:
    system = M.build(seed, schedule=TEST_SCHEDULE)
    r = system.roles
    assert sorted((r.cue, r.source1, r.source2)) == sorted(M.UNITS)
    order = list(M.UNITS)
    random.Random(f"as2b-roles-{seed}").shuffle(order)
    assert (r.cue, r.source1, r.source2) == tuple(order)
    assert system.log.of(RuntimeEventType.RUN)[0].data["roles"] == r.as_dict()
    assert r.action_of == {r.source1: "A1", r.source2: "A2"}


def test_ct_e7_birth_states_equal_c0_for_every_cue_role() -> None:
    cues = {}
    for seed in range(9101, 9131):
        cues.setdefault(M.assign_roles(seed).cue, seed)
        if len(cues) == 3:
            break
    assert len(cues) == 3
    for seed in cues.values():
        system = M.build(seed, schedule=TEST_SCHEDULE)
        c0, _ = M.build_c0(seed, exogenous=())
        assert {u.unit_id: u.export_state() for u in system.app.units.all()} == \
               {u.unit_id: u.export_state() for u in c0.units.all()}
        assert system.app.connections.export_state() == c0.connections.export_state()


@pytest.mark.parametrize("seed", SEEDS)
def test_ct_e5_e6_e8_intents_go_only_to_the_effector_and_nothing_is_dropped(seed) -> None:
    system = run(seed, N_TEST)
    events = intent_events(system.log)
    assert events, "道具の確認には、意図が少なくとも 1 つ要る（判定ではない）"
    assert all(e["target_id"] == M.EFFECTOR_ID and e["output_port"] == M.INTENT_PORT for e in events)
    assert all(e["payload"] in M.ACTION_IDS for e in events)
    received = [i[1] for i in system.world.intents]
    assert [e["delta_id"] for e in events] == received == system.app.effectors[M.EFFECTOR_ID].received
    assert all(d.kind != DeltaKind.INTENT for d in system.app.pulse_runtime.brain_state.deltas)
    others = [e for e in system.log.of(RuntimeEventType.DELTA) if e.data["kind"] == DeltaKind.INTENT
              and e.data["target_id"] != M.EFFECTOR_ID]
    assert others == []


# ---- EC-1・CT-E10（二層の突合） --------------------------------------------------------

@pytest.mark.parametrize("seed", SEEDS)
def test_ec1_ct_e10_layer_a_and_layer_b_match_one_to_one(seed) -> None:
    system = run(seed, N_TEST)
    a = M.audit(system)
    assert a["ok"] and a["log_matches_world"] and a["duplicate_delta_ids"] == 0
    emitted = [r for r in system.decider.records if r["emitted"]]
    assert a["matched"] == len(emitted) == len(system.world.intents)
    for r, (pulse, _did, src, act) in zip(emitted, system.world.intents):
        assert (pulse, src, act) == (r["emit_pulse"], r["winner_unit"], r["action"])     # 出どころは勝った源（EC-1）
    assert "delta_id" not in json.dumps(system.decider.export_state())                  # 層 A は識別子を持たない（EC-7）


@pytest.mark.parametrize("seed", SEEDS)
def test_ct_e10_issued_plus_carried_equals_wins_at_any_stop(seed) -> None:
    probe = run(seed, N_TEST)
    stops = sorted({r["decision_pulse"] for r in probe.decider.records if r["decision_pulse"]} | {137, 401, 777})
    system = M.build(seed, schedule=TEST_SCHEDULE)
    for stop in stops:
        M.advance_to(system.app, stop)
        a = M.audit(system)
        assert a["ok"] and a["identity_issued_plus_carried_equals_wins"]
        assert a["issued"] + len(a["carried_over_windows"]) == a["win_windows"]


def test_ct_e10_a_decision_not_yet_emitted_is_counted_as_carried_over() -> None:
    probe = run(SEEDS[0], N_TEST)
    win = next(r for r in probe.decider.records if r["winner_unit"] is not None)
    system = run(SEEDS[0], win["decision_pulse"])
    a = M.audit(system)
    assert a["ok"] and a["carried_over_windows"] == [win["window"]]
    assert system.decider.pending["pulse"] == win["decision_pulse"] + 1


# ---- 世界（CT-W1〜W5） -----------------------------------------------------------------

@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("rule_c", M.ACTION_IDS)
def test_ct_w1_consequences_follow_the_rule_only_for_the_action_c(seed, rule_c) -> None:
    system = run(seed, N_TEST, rule_c=rule_c)
    consequences = [(r.pulse, r.receptor_id, r.origin) for r in system.world.reserved if r.kind == M.CONSEQUENCE]
    expected = [(p + L - 1, system.roles.cue_receptor, did) for p, did, _src, act in system.world.intents if act == rule_c]
    assert consequences == expected
    cues = [(r.pulse, r.receptor_id) for r in system.world.reserved if r.kind == M.CUE]
    assert cues == M.cue_events(system, TEST_SCHEDULE)


def test_w1_delay_must_be_at_least_two() -> None:
    with pytest.raises(ValueError):
        M.build(SEEDS[0], schedule=TEST_SCHEDULE, delay=1)


def test_ct_w2_the_schedule_check_rejects_overlaps_and_t4_violations() -> None:
    with pytest.raises(M.ScheduleConflict):        # c_(k+1) ＝ 30 ＋ 60 ＜ b_k ＋ L ＋ 1 ＝ 30 ＋ 61 ＋ 3
        M.TrialSchedule.periodic(first=30, spacing=60, count=3, offset=2, length=60).check(L)
    with pytest.raises(M.ScheduleConflict):
        M.TrialSchedule((10, 5), 2, 3).check(L)
    with pytest.raises(M.ScheduleConflict):
        M.TrialSchedule((10,), 2, 0).check(L)
    M.TrialSchedule.periodic(first=30, spacing=64, count=3, offset=2, length=60).check(L)     # 等号は許す
    with pytest.raises(M.ScheduleConflict):
        M.build(SEEDS[0], schedule=M.TrialSchedule.periodic(first=30, spacing=60, count=3, offset=2, length=60))


@pytest.mark.parametrize("seed", SEEDS)
def test_ct_w2_w3_no_two_reservations_share_a_pulse_and_sources_get_nothing(seed) -> None:
    system = run(seed, N_TEST)
    realized = system.world.export_state()["realized"]
    assert all(n == 1 for _p, _r, _rids, n in realized)
    source_receptors = set(system.roles.source_receptors)
    assert not any(r in source_receptors for _p, r, _rids, _n in realized)                # K1
    assert not any(r in source_receptors for _p, r in system.log.sensory())


@pytest.mark.parametrize("seed", SEEDS)
def test_ct_w4_windows_do_not_depend_on_outcomes(seed) -> None:
    on, off = run(seed, N_TEST), run(seed, N_TEST, respond=False)
    other_c = run(seed, N_TEST, rule_c="A2")
    assert on.decider.windows == off.decider.windows == other_c.decider.windows == TEST_SCHEDULE.windows
    assert any(r.kind == M.CONSEQUENCE for r in on.world.reserved) == any(a == "A1" for *_x, a in on.world.intents)


@pytest.mark.parametrize("seed", SEEDS)
def test_ct_w5_two_bodies_differ_only_in_rule_c_at_pulse_zero(seed) -> None:
    a = M.sigma(M.build(seed, schedule=TEST_SCHEDULE, rule_c="A1"))
    b = M.sigma(M.build(seed, schedule=TEST_SCHEDULE, rule_c="A2"))
    assert M.sigma_diff(a, b) == [("world", "rule", "rule_c")]


# ---- 複製・再生・移植（CT-Σ・CT-ΣE） ---------------------------------------------------

def _branch_points(seed):
    """「窓の中・未決」（窓の始まりの Pulse の後で、まだ決まっていない）と「決定の後・出す前」の分岐の時点。"""
    probe = run(seed, N_TEST)
    win = next(r for r in probe.decider.records if r["winner_unit"] is not None)
    undecided = next(r for r in probe.decider.records if r["decision_pulse"] is None or r["decision_pulse"] > r["open"])
    return {"window-open-undecided": undecided["open"], "decided-not-emitted": win["decision_pulse"]}


def test_ct_sigma_e1_a_clone_shares_one_decider_between_its_two_taps() -> None:
    system = run(SEEDS[0], 200)
    c = M.clone(system)
    taps = c.taps()
    assert len(taps) == 2 and taps[0].decider is taps[1].decider is c.decider
    assert c.decider is not system.decider and c.world is not system.world


@pytest.mark.parametrize("seed", SEEDS)
def test_ct_sigma1_sigma4_e2_clones_stay_identical_including_both_layers(seed) -> None:
    for label, branch in _branch_points(seed).items():
        original = run(seed, branch)
        c = M.clone(original)
        if label == "decided-not-emitted":
            assert original.decider.pending is not None and c.decider.pending == original.decider.pending
        assert M.sigma(c) == M.sigma(original)
        M.advance_to(original.app, branch + H)
        M.advance_to(c.app, branch + H)
        s_o, s_c = M.sigma(original), M.sigma(c)
        assert s_o == s_c, label
        assert s_o["runtime"]["in_flight"] == 0 and s_o["runtime"]["waiting"] == 0                 # CT-Σ4
        assert s_o["exit"]["reports"] == {} and s_o["exit"]["reports_pulse"] is None


@pytest.mark.parametrize("seed", SEEDS)
def test_ct_sigma2_a_clone_shares_nothing_with_the_original(seed) -> None:
    original = run(seed, 400)
    before = M.sigma(original)
    c = M.clone(original)
    if c.world.pending:
        c.world.cancel(c.world.pending[0].rid)
    c.decider.records.append({"window": -1})
    c.transplant({"s1.main->s2": 0.009})
    assert M.sigma(original) == before


@pytest.mark.parametrize("seed", SEEDS)
def test_ct_sigma3_reexecution_gives_the_same_state_as_the_clone(seed) -> None:
    original = run(seed, 400)
    again = run(seed, 400)
    assert M.sigma(M.clone(original)) == M.sigma(again)


def test_ct_sigma5_cancelling_one_consequence_removes_exactly_its_event() -> None:
    seed = SEEDS[0]
    probe = run(seed, N_TEST, rule_c="A1")
    probe_c = run(seed, N_TEST, rule_c="A2")
    for system, rule_c in ((probe, "A1"), (probe_c, "A2")):
        hit = [(p, did) for p, did, _s, act in system.world.intents if act == rule_c]
        if hit:
            break
    else:
        pytest.skip("どちらの規則でも結果が生じない個体（道具の確認を別の個体で行う）")
    e_pulse, did = hit[0]
    f = run(seed, e_pulse, rule_c=rule_c)
    n = M.clone(f)
    rid = next(r.rid for r in n.world.pending if r.origin == did)
    n.world.cancel(rid)
    M.advance_to(f.app, e_pulse + L - 1)
    M.advance_to(n.app, e_pulse + L - 1)
    sensory_f = [x for x in f.log.sensory() if x[0] > e_pulse]
    sensory_n = [x for x in n.log.sensory() if x[0] > e_pulse]
    missing = list(sensory_f)
    for x in sensory_n:
        missing.remove(x)
    assert missing == [(e_pulse + L - 1, f.roles.cue_receptor)]


@pytest.mark.parametrize("seed", SEEDS)
def test_ct_sigma_e3_replaying_the_external_history_gives_the_same_sensory_events(seed) -> None:
    branch = 700
    original = run(seed, branch)
    schedule = M.replay_schedule(original)
    replay = run(seed, branch, respond=False, world_cues=False, exogenous=schedule)
    assert replay.log.sensory() == original.log.sensory()
    assert brain_view(replay) == brain_view(original)
    # 申し送り ①：手がかりを二重に予約しない。再生の予定は成立した手がかりを一度ずつ含み、世界は手がかりを足さない
    assert not any(r.kind == M.CUE for r in replay.world.reserved)
    cue_r = original.roles.cue_receptor
    assert all(schedule.count((c, cue_r)) == 1 for c in TEST_SCHEDULE.cues if c <= branch)
    assert all(n == 1 for _p, _r, _rids, n in replay.world.export_state()["realized"])
    # 持ち越し（まだ成立していない手がかり・結果）は、再生の系に同じ (Pulse, Receptor) で残る
    assert sorted((r.pulse, r.receptor_id) for r in replay.world.pending) == \
           sorted((r.pulse, r.receptor_id) for r in original.world.pending)
    assert replay.decider.records == original.decider.records
    assert [(p, s, a) for p, _d, s, a in replay.world.intents] == [(p, s, a) for p, _d, s, a in original.world.intents]
    assert not any(r.kind == M.CONSEQUENCE for r in replay.world.reserved)


def test_replaying_with_the_world_cues_on_is_refused_as_a_double_cue() -> None:
    original = run(SEEDS[0], 700)
    with pytest.raises(M.ScheduleConflict):
        M.build(SEEDS[0], schedule=TEST_SCHEDULE, respond=False, exogenous=M.replay_schedule(original))


@pytest.mark.parametrize("seed", SEEDS)
def test_ct_sigma_e4_transplant_and_freeze_do_not_touch_the_exit(seed) -> None:
    system = run(seed, 500)
    before = M.sigma(system)
    system.transplant({"s1.main->s2": 0.0021, "s3.main->s1": 0.0087})
    after = M.sigma(system)
    assert M.sigma_diff(before, after) == [("connections", "s1.main->s2", "weight"), ("connections", "s3.main->s1", "weight")]
    system.declare([M.AS1.Intervention(M.AS1.FREEZE, frozenset({"s1.main->s2"}))], "freeze")
    assert M.sigma(system)["exit"] == before["exit"]


def test_lc1_freezing_all_plastic_connections_from_birth_keeps_the_weights() -> None:
    system = M.build(SEEDS[0], schedule=TEST_SCHEDULE)
    plastic = frozenset(cid for cid in system.app.connections.export_state())
    system.declare([M.AS1.Intervention(M.AS1.FREEZE, plastic)], "LC1")
    w0 = {cid: v["weight"] for cid, v in system.app.connections.export_state().items()}
    M.advance_to(system.app, 600)
    assert {cid: v["weight"] for cid, v in system.app.connections.export_state().items()} == w0


def test_ci1_an_empty_intervention_wrapper_is_identical_to_no_wrapper() -> None:
    a, b = run(SEEDS[0], 600), run(SEEDS[0], 600, interventions=False)
    assert M.sigma_diff(M.sigma(a), M.sigma(b)) == [("interventions",)]


# ---- C0 への還元（CT-G1a′〜c′） ---------------------------------------------------------

@pytest.mark.parametrize("seed", SEEDS)
def test_ct_g1a_prime_removing_the_outlet_reproduces_c0_with_the_same_cues(seed) -> None:
    system = run(seed, N_TEST, outlet=False)
    c0_log = M.AS1.AS1Log()
    c0, _ = M.build_c0(seed, exogenous=M.cue_events(system, TEST_SCHEDULE), log=c0_log)
    M.advance_to(c0, N_TEST)
    assert system.decider is None and system.world.intents == []
    assert {u.unit_id: u.export_state() for u in system.app.units.all()} == {u.unit_id: u.export_state() for u in c0.units.all()}
    assert system.app.connections.export_state() == c0.connections.export_state()
    assert system.log.activity() == c0_log.activity() and system.log.sensory() == c0_log.sensory()


@pytest.mark.parametrize("seed", SEEDS)
def test_ct_g1b_prime_an_unanswering_world_leaves_the_brain_as_without_the_outlet(seed) -> None:
    quiet = run(seed, N_TEST, respond=False)
    bare = run(seed, N_TEST, outlet=False)
    assert brain_view(quiet) == brain_view(bare)
    assert quiet.log.activity() == bare.log.activity()
    assert not any(r.kind == M.CONSEQUENCE for r in quiet.world.reserved)


@pytest.mark.parametrize("seed", SEEDS)
def test_ct_g1c_prime_the_exit_touches_the_brain_only_through_sensory_events(seed) -> None:
    system = run(seed, N_TEST)
    sensory = system.log.sensory()
    c0_log = M.AS1.AS1Log()
    c0, _ = M.build_c0(seed, exogenous=sensory, log=c0_log)
    M.advance_to(c0, N_TEST)
    assert c0_log.sensory() == sensory
    assert c0_log.activity() == system.log.activity()
    assert {u.unit_id: u.export_state() for u in c0.units.all()} == \
           {u.unit_id: u.export_state() for u in system.app.units.all()}
    assert c0.connections.export_state() == system.app.connections.export_state()


# ---- 関門の宣言・解析・走らせるコード（②a では関門を走らせない） ----------------------

def test_the_gate_declaration_is_fixed_by_its_hash_and_recorded_in_the_readme() -> None:
    raw = (GATE_DIR / "gate_declaration.json").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    assert digest == G.DECLARATION_SHA256
    assert digest in (GATE_DIR / "README.md").read_text(encoding="utf-8")
    decl, d2 = G.load_declaration()
    assert d2 == digest
    G._check_supported(decl)


def test_the_declared_schedule_satisfies_the_contract_without_running() -> None:
    decl, _ = G.load_declaration()
    schedule = G.schedule_of(decl, M)
    schedule.check(decl["world"]["delay_L"])
    assert len(schedule.windows) == decl["schedule"]["cue_pulses"]["count"]
    assert schedule.last_outcome_pulse(decl["world"]["delay_L"]) == decl["bodies"]["pulses"]
    seeds = decl["synthetic_seeds"]
    assert seeds["last"] - seeds["first"] + 1 == seeds["count"]
    assert not set(range(seeds["first"], seeds["last"] + 1)) & (set(TOOL_SEEDS) | set(range(9001, 9007)))
    assert seeds["first"] > 30300                                          # これまでの実験の seed と重ならない


def test_a_changed_declaration_is_refused(tmp_path) -> None:
    changed = json.loads((GATE_DIR / "gate_declaration.json").read_text(encoding="utf-8"))
    changed["evaluation"]["q"] = 0.1
    path = tmp_path / "decl.json"
    path.write_text(json.dumps(changed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(G.DeclarationMismatch):
        G.load_declaration(path)


def test_the_declaration_v02_keeps_the_v01_history_and_was_revised_before_any_gate_run() -> None:
    decl, _ = G.load_declaration()
    assert decl["version"] == "0.2"
    h = decl["history"][0]
    assert h["version"] == "0.1" and h["sha256"].startswith("909ab4f8") and h["synthetic_gate_seeds_run_before_revision"] is False
    assert not (GATE_DIR / "attempts").exists() and not (GATE_DIR / "results").exists()     # ②a では関門を走らせていない


def test_without_execute_the_gate_does_not_run_or_claim(tmp_path, capsys) -> None:
    assert G.main(["--out", str(tmp_path / "results")]) == 0
    assert not (tmp_path / "results").exists()
    assert not (GATE_DIR / "results").exists() and not (GATE_DIR / "attempts").exists()


def _test_declaration(tmp_path):
    """道具の確認用の宣言（関門の宣言の形のまま、seed・予定・長さだけを道具の確認用に替える）。札は tmp_path に作る。"""
    decl = json.loads((GATE_DIR / "gate_declaration.json").read_text(encoding="utf-8"))
    decl["schedule"] = {"cue_pulses": {"first": 30, "spacing": 80, "count": 3}, "window_offset_o": 2, "window_length_W": 60}
    decl["synthetic_seeds"] = {"first": TOOL_SEEDS[0], "last": TOOL_SEEDS[1], "count": 2}
    decl["bodies"]["pulses"] = 30 + 2 * 80 + 61 + L
    path = tmp_path / "test_declaration.json"
    path.write_text(json.dumps(decl, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return decl, path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_gate_runner_reports_only_feasibility_quantities_on_a_test_declaration(tmp_path) -> None:
    decl, _path, digest = _test_declaration(tmp_path)
    attempts = tmp_path / "attempts"
    report = G.run_gate(decl, digest, tmp_path / "out", attempts)
    assert set(report) == {"declaration_sha256", "status", "validity", "per_body", "evaluation"}
    assert report["status"] == "completed" and report["validity"] == {"valid": True, "problems": []}
    assert len(report["per_body"]) == 4
    for row in report["per_body"]:
        assert set(row) == {"seed", "rule_c", "feasible", *G.REPORT_KEYS}
        assert row["windows"] == 3 and row["decided"] + row["tie"] + row["none"] == 3
    assert set(report["evaluation"]) == {"individuals", "bodies", "feasible_bodies", "feasible_individuals", "pass"}
    text = (tmp_path / "out" / "report.json").read_text(encoding="utf-8")
    assert "proportion" not in text and '"A1":' not in text and '"A2":' not in text
    assert len(list((tmp_path / "out" / "records").glob("*.json"))) == 4
    assert (attempts / f"claim-{digest}.json").exists() and (attempts / f"attempt-{digest}.completed.json").exists()


def _row(seed, rule_c, decided, a1=True, a2=True, windows=50):
    return {"seed": seed, "rule_c": rule_c, "windows": windows, "decided": decided, "tie": 0, "none": windows - decided,
            "A1_occurred": a1, "A2_occurred": a2}


def test_evaluate_requires_both_conditions_in_the_same_body_and_both_bodies_of_an_individual() -> None:
    decl, _ = G.load_declaration()
    # 80 本体のうち、「決まった窓 ≥ q」が 41 本体、「A1 と A2 の両方」が 41 本体あるが、同じ本体で両方を満たすのは 2 本体
    rows = []
    for k, seed in enumerate(range(31001, 31041)):
        for j, c in enumerate(("A1", "A2")):
            idx = 2 * k + j
            many = idx < 41                      # 0〜40：決まった窓が多い
            both = idx >= 39                     # 39〜79：両方が出た
            rows.append(_row(seed, c, 25 if many else 3, a1=True, a2=both))
    assert sum(1 for r in rows if r["decided"] >= 10) == 41 and sum(1 for r in rows if r["A2_occurred"]) == 41
    ev = G.evaluate(rows, decl)
    assert ev["feasible_bodies"] == 2 and ev["feasible_individuals"] <= 1 and ev["pass"] is False      # 旧い判定なら通っていた


@pytest.mark.parametrize(("feasible", "expected"), [(20, False), (21, True)])
def test_evaluate_needs_a_strict_majority_of_the_forty_individuals(feasible, expected) -> None:
    decl, _ = G.load_declaration()
    rows = []
    for k, seed in enumerate(range(31001, 31041)):
        ok = k < feasible
        rows += [_row(seed, "A1", 10 if ok else 9), _row(seed, "A2", 10)]       # 10/50 ＝ q ちょうどは満たす
    ev = G.evaluate(rows, decl)
    assert ev["individuals"] == 40 and ev["feasible_individuals"] == feasible and ev["pass"] is expected


def test_one_body_failing_makes_the_individual_infeasible() -> None:
    decl, _ = G.load_declaration()
    rows = [_row(31001, "A1", 30), _row(31001, "A2", 30, a1=False)]
    assert G.evaluate(rows, decl)["feasible_individuals"] == 0


def test_a_second_run_is_refused_even_with_another_out(tmp_path) -> None:
    decl, _path, digest = _test_declaration(tmp_path)
    attempts = tmp_path / "attempts"
    G.run_gate(decl, digest, tmp_path / "out1", attempts)
    with pytest.raises(G.AttemptRefused):
        G.run_gate(decl, digest, tmp_path / "out2", attempts)
    assert not (tmp_path / "out2").exists()


def test_a_failure_mid_run_keeps_the_claim_records_the_failure_and_refuses_a_rerun(tmp_path, monkeypatch) -> None:
    decl, _path, digest = _test_declaration(tmp_path)
    attempts = tmp_path / "attempts"
    original = G.run_body
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("途中の停止の模擬")
        return original(*args, **kwargs)

    monkeypatch.setattr(G, "run_body", flaky)
    with pytest.raises(RuntimeError):
        G.run_gate(decl, digest, tmp_path / "out", attempts)
    failed = json.loads((attempts / f"attempt-{digest}.failed.json").read_text(encoding="utf-8"))
    assert failed["status"] == "failed" and failed["finished_bodies"] == 1
    assert (attempts / f"claim-{digest}.json").exists() and not (tmp_path / "out" / "report.json").exists()
    assert len(list((tmp_path / "out" / "records").glob("*.json"))) == 1          # 終わった本体の記録は痕跡として残る
    monkeypatch.setattr(G, "run_body", original)
    with pytest.raises(G.AttemptRefused):
        G.run_gate(decl, digest, tmp_path / "out-again", attempts)


def test_an_audit_mismatch_makes_the_attempt_invalid_not_a_pass(tmp_path, monkeypatch) -> None:
    decl, _path, digest = _test_declaration(tmp_path)
    attempts = tmp_path / "attempts"
    original = G.run_body

    def broken_audit(*args, **kwargs):
        row, record = original(*args, **kwargs)
        record["audit"] = dict(record["audit"], ok=False)
        return row, record

    monkeypatch.setattr(G, "run_body", broken_audit)
    report = G.run_gate(decl, digest, tmp_path / "out", attempts)
    assert report["status"] == "invalid" and report["evaluation"] == {"pass": None}
    assert report["validity"]["valid"] is False and report["validity"]["problems"]
    invalid = json.loads((attempts / f"attempt-{digest}.invalid.json").read_text(encoding="utf-8"))
    assert invalid["valid"] is False and invalid["pass"] is None


# ---- v0.3：対の完全性と、層 A からの独立な計算し直し（関門の seed を走らせない、作った入力だけ） --------

ROLES = {"cue": "s3", "source1": "s1", "source2": "s2"}


def _layer_a(decl, outcomes):
    """窓ごとの結末の列から、整合した層 A の記録を作る（決定は窓の始まりの Pulse）。"""
    out = []
    for (k, a, b), o in zip(G.declared_windows(decl), outcomes, strict=True):
        win = o in ("A1", "A2")
        out.append({"window": k, "open": a, "close": b, "outcome": o,
                    "decision_pulse": a if o != "none" else None,
                    "winner_unit": {"A1": "s1", "A2": "s2"}[o] if win else None, "action": o if win else None,
                    "emit_pulse": a + 1 if win else None, "emitted": win})
    return out


def _body(decl, seed, rule_c, outcomes):
    layer_a = _layer_a(decl, outcomes)
    counts, problems = G.recount_from_layer_a(layer_a, G.declared_windows(decl), ROLES)
    assert problems == []
    row = {"seed": seed, "rule_c": rule_c, **counts}
    audit = {"seed": seed, "rule_c": rule_c, "layer_a": layer_a, "layer_b": [], "roles": ROLES,
             "reached_windows": len(layer_a), "audit": {"ok": True, "carried_over_windows": []}}
    return row, audit


def _feasible_outcomes(decl):
    n = decl["schedule"]["cue_pulses"]["count"]
    return ["A1"] * 6 + ["A2"] * 6 + ["tie"] * 2 + ["none"] * (n - 14)          # 12/50 ≥ q、A1 と A2 の両方


def _all_bodies(decl, outcomes_of=None):
    rows, audits = [], []
    for seed in G.declared_seeds(decl):
        for body in decl["bodies"]["per_individual"]:
            outcomes = outcomes_of(seed, body["rule_c"]) if outcomes_of else _feasible_outcomes(decl)
            r, a = _body(decl, seed, body["rule_c"], outcomes)
            rows.append(r)
            audits.append(a)
    return rows, audits


def test_a_consistent_complete_set_is_valid_and_passes() -> None:
    decl, _ = G.load_declaration()
    rows, audits = _all_bodies(decl)
    assert G.check_validity(rows, audits, decl) == {"valid": True, "problems": []}
    ev = G.evaluate(rows, decl)
    assert ev["individuals"] == 40 and ev["feasible_individuals"] == 40 and ev["pass"] is True


@pytest.mark.parametrize("mutation", ["duplicate_A1_for_a_seed", "missing_A2_for_a_seed", "seed_out_of_range",
                                      "row_and_audit_swapped", "extra_body"])
def test_pairing_defects_make_the_attempt_invalid(mutation) -> None:
    decl, _ = G.load_declaration()
    rows, audits = _all_bodies(decl)
    if mutation == "duplicate_A1_for_a_seed":          # seed 31001 の c ＝ A2 の本体を c ＝ A1 の重複に置き換える
        r, a = _body(decl, 31001, "A1", _feasible_outcomes(decl))
        rows[1], audits[1] = r, a
    elif mutation == "missing_A2_for_a_seed":
        del rows[1], audits[1]
    elif mutation == "seed_out_of_range":               # 40 個体のうち 1 個体を、宣言の範囲外の seed に入れ替える
        for i in (0, 1):
            rows[i]["seed"] = audits[i]["seed"] = 31041
    elif mutation == "row_and_audit_swapped":           # 行と記録の対応を入れ替える（多重集合は同じ）
        audits[0], audits[1] = audits[1], audits[0]
    elif mutation == "extra_body":
        r, a = _body(decl, 31002, "A1", _feasible_outcomes(decl))
        rows.append(r)
        audits.append(a)
    v = G.check_validity(rows, audits, decl)
    assert v["valid"] is False and v["problems"]


def test_evaluate_counts_an_individual_only_with_one_body_for_each_rule_c() -> None:
    decl, _ = G.load_declaration()
    rows, _ = _all_bodies(decl)
    for i in range(0, 42, 2):                          # 21 個体で、c ＝ A2 の本体を c ＝ A1 の重複に置き換える
        rows[i + 1] = dict(rows[i])
    ev = G.evaluate(rows, decl)
    assert ev["feasible_individuals"] == 19 and ev["pass"] is False


def test_evaluate_uses_the_declared_number_of_individuals_as_the_denominator() -> None:
    decl, _ = G.load_declaration()
    rows, _ = _all_bodies(decl)
    ev = G.evaluate(rows[:40], decl)                   # 20 個体の行だけ（どれも成立）：20/40 は過半でない
    assert ev["individuals"] == 40 and ev["feasible_individuals"] == 20 and ev["pass"] is False


def test_the_reviewers_counterexample_rows_claim_choices_that_layer_a_does_not_have() -> None:
    """層 A は 50 窓すべて発火なし・層 B は空・監査は ok だが、報告の行だけが「10 窓で選択、A1 と A2 の両方」と書く。"""
    decl, _ = G.load_declaration()
    n = decl["schedule"]["cue_pulses"]["count"]
    rows, audits = _all_bodies(decl, lambda seed, c: ["none"] * n)
    for r in rows:
        r.update(decided=10, tie=0, none=n - 10, A1_occurred=True, A2_occurred=True)
    assert G.evaluate(rows, decl)["pass"] is True                     # 行だけを見ると合格に見える
    v = G.check_validity(rows, audits, decl)
    assert v["valid"] is False and any("層 A から計算し直した値と一致しない" in p for p in v["problems"])


@pytest.mark.parametrize("mutation", ["flag_without_choice", "tie_none_offset", "decided_overstated",
                                      "duplicate_window_id", "missing_window", "unexpected_outcome",
                                      "window_bounds_differ", "winner_action_mismatch", "unissued_choice"])
def test_layer_a_inconsistencies_make_the_attempt_invalid(mutation) -> None:
    decl, _ = G.load_declaration()
    rows, audits = _all_bodies(decl)
    r, a = rows[0], audits[0]
    la = a["layer_a"]
    if mutation == "flag_without_choice":            # 層 A では A2 が出ていないのに、行は A2 が出たと書く
        a["layer_a"] = la = _layer_a(decl, ["A1"] * 12 + ["none"] * 38)
        r.update(decided=12, tie=0, none=38, A1_occurred=True, A2_occurred=True)
    elif mutation == "tie_none_offset":              # 引き分けと発火なしを入れ替えて、合計は 50 のまま
        r.update(tie=r["tie"] + 3, none=r["none"] - 3)
    elif mutation == "decided_overstated":
        r.update(decided=r["decided"] + 2, none=r["none"] - 2)
    elif mutation == "duplicate_window_id":
        la[1]["window"] = la[0]["window"]
    elif mutation == "missing_window":
        del la[-1]
        a["reached_windows"] = len(la) + 1
    elif mutation == "unexpected_outcome":
        la[20]["outcome"] = "A3"
    elif mutation == "window_bounds_differ":
        la[5]["close"] += 1
    elif mutation == "winner_action_mismatch":       # 源 1（s1）が勝ったのに行動 ID が A2
        la[0]["action"] = la[0]["outcome"] = "A2"
        la[0]["winner_unit"] = "s1"
    elif mutation == "unissued_choice":
        la[0]["emitted"] = False
    v = G.check_validity(rows, audits, decl)
    assert v["valid"] is False and v["problems"]


def test_check_validity_flags_unreached_windows_and_carried_over() -> None:
    decl, _ = G.load_declaration()
    rows, audits = _all_bodies(decl)
    audits[0]["reached_windows"] = 49
    audits[1]["audit"]["carried_over_windows"] = [50]
    audits[2]["audit"]["ok"] = False
    problems = G.check_validity(rows, audits, decl)["problems"]
    assert any("窓の到達" in p for p in problems) and any("未発行の予定" in p for p in problems) \
        and any("CT-E10" in p for p in problems)


def test_preflight_refuses_without_using_the_claim_when_old_records_remain(tmp_path) -> None:
    decl, _path, digest = _test_declaration(tmp_path)
    out = tmp_path / "out"
    (out / "records").mkdir(parents=True)
    (out / "records" / "old.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(G.AttemptRefused):
        G.run_gate(decl, digest, out, tmp_path / "attempts")
    assert not (tmp_path / "attempts" / f"claim-{digest}.json").exists()      # 札は使っていない


def test_main_exit_codes_for_done_refused_invalid_and_failed(tmp_path, monkeypatch, capsys) -> None:
    _decl, path, _digest = _test_declaration(tmp_path)
    kw = {"declaration": path, "expected_sha256": None}
    assert G.main(["--execute", "--out", str(tmp_path / "a")], attempts_dir=tmp_path / "att1", **kw) == G.EXIT_DONE
    assert G.main(["--execute", "--out", str(tmp_path / "b")], attempts_dir=tmp_path / "att1", **kw) == G.EXIT_REFUSED
    original = G.run_body

    def broken_audit(*args, **kwargs):
        row, record = original(*args, **kwargs)
        record["audit"] = dict(record["audit"], ok=False)
        return row, record

    monkeypatch.setattr(G, "run_body", broken_audit)
    assert G.main(["--execute", "--out", str(tmp_path / "c")], attempts_dir=tmp_path / "att2", **kw) == G.EXIT_INVALID

    def boom(*args, **kwargs):
        raise RuntimeError("停止の模擬")

    monkeypatch.setattr(G, "run_body", boom)
    assert G.main(["--execute", "--out", str(tmp_path / "d")], attempts_dir=tmp_path / "att3", **kw) == G.EXIT_FAILED
    assert not (GATE_DIR / "attempts").exists() and not (GATE_DIR / "results").exists()     # 本物の宣言の札は作らない


def test_proposition_t5_closed_form_parts() -> None:
    p = AN.c0_dynamics()
    assert p["refractory_pulses"] == 0 and p["decay"] == 0.85
    assert AN.silent_probability(p) == pytest.approx(0.0049 / 2 / (0.016 / 0.15 * 0.1), rel=1e-9)
    assert AN.silent_probability(p) == pytest.approx(0.2296875, abs=1e-9)
    assert AN.reset_interval_lower_bound(p) == 9
    assert AN.window_length(p) == 19 and 0.85 ** 19 <= 0.05 < 0.85 ** 18
    intervals, fires = AN.isolated_intervals(p, 0.45, 0.088)                 # 範囲の角（最も発火しやすい）
    assert fires[0] == 9 and min(intervals[-3:]) == 23
    _, silent = AN.isolated_intervals(p, 0.55, 0.072)                        # A ＝ 0.48 ＜ θ
    assert silent == []
