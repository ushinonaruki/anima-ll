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
    assert replay.decider.records == original.decider.records
    assert [(p, s, a) for p, _d, s, a in replay.world.intents] == [(p, s, a) for p, _d, s, a in original.world.intents]
    assert not any(r.kind == M.CONSEQUENCE for r in replay.world.reserved)


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


def test_without_execute_the_gate_does_not_run(tmp_path, capsys) -> None:
    assert G.main(["--out", str(tmp_path / "results")]) == 0
    assert not (tmp_path / "results").exists()
    assert not (GATE_DIR / "results").exists()


def test_the_gate_runner_reports_only_feasibility_quantities_on_a_test_declaration(tmp_path) -> None:
    decl = json.loads((GATE_DIR / "gate_declaration.json").read_text(encoding="utf-8"))
    decl["schedule"] = {"cue_pulses": {"first": 30, "spacing": 80, "count": 3}, "window_offset_o": 2, "window_length_W": 60}
    decl["synthetic_seeds"] = {"first": TOOL_SEEDS[0], "last": TOOL_SEEDS[1], "count": 2}
    decl["bodies"]["pulses"] = 30 + 2 * 80 + 61 + L
    report = G.run_gate(decl, "test-declaration", tmp_path / "out")
    assert set(report) == {"declaration_sha256", "per_body", "evaluation", "audit_all_ok"}
    assert report["audit_all_ok"]
    assert len(report["per_body"]) == 4
    for row in report["per_body"]:
        assert set(row) == {"seed", "rule_c", *G.REPORT_KEYS}
        assert row["windows"] == 3 and row["decided"] + row["tie"] + row["none"] == 3
    assert set(report["evaluation"]) == {"bodies", "bodies_decided_at_least_q", "bodies_with_both_actions",
                                         "criterion_1", "criterion_2", "pass"}
    text = (tmp_path / "out" / "report.json").read_text(encoding="utf-8")
    assert "proportion" not in text and '"A1":' not in text and '"A2":' not in text
    assert len(list((tmp_path / "out" / "records").glob("*.json"))) == 4


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
