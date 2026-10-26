"""AS1 の最小の研究用の道具の契約テスト（docs/as1-minimal-implementation-contract.md の ②）。

正式な実験ではない。ここで走らせる seed（9001〜）は、事前登録（③）の前の道具の確認だけに使い、
結果（意図の頻度・時刻差・重みの向きなど）は何も判定しない。確かめるのは契約（IC・WC・CT）だけ。
"""

import copy
import importlib.util
from pathlib import Path

import pytest
import yaml

from anima_ll.domain.model.activity import ActivityEvent
from anima_ll.domain.model.delta import DeltaKind, ProposedDelta
from anima_ll.domain.model.runtime_event import RuntimeEventType
from anima_ll.domain.model.unit_step import UnitStepResult

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A = _load("as1_tools_test", ROOT / "experiments" / "as1_closed_loop" / "as1.py")
W12 = _load("world_0012_for_as1_test", ROOT / "experiments" / "0012_passive_world" / "world.py")
PROTOCOL_0012 = yaml.safe_load((ROOT / "experiments" / "0012_passive_world" / "protocol.yaml").read_text(encoding="utf-8"))

SEEDS = (9001, 9002, 9003)     # 源が発火する個体（道具の確認用。判定には使わない）
ALL_SOURCE_ROLES = (9003, 9006, 9001)   # 源が s1・s2・s3 になる個体（監査 019：どの役でも出生時の状態が C0 と同じ）
SILENT_SEED = 9004             # この割り当てでは源が 1500 Pulse のあいだ発火しない個体


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)


def run(seed: int, until: int, **kw):
    system = A.build(seed, **kw)
    A.advance_to(system.app, until)
    return system


def intent_deltas(log):
    return [e.data for e in log.of(RuntimeEventType.DELTA) if e.data["kind"] == DeltaKind.INTENT]


def c0_schedule(seed: int) -> list[tuple[int, str]]:
    """既存の C0 実験（0012 の ordered 条件）の、その seed の刺激の予定 [(Pulse, Receptor)]。"""
    roles = W12.role_receptors(PROTOCOL_0012, seed)
    return [(t, roles[label]) for t, label in W12.stimuli(PROTOCOL_0012, "ordered", seed)]


# ---- 設計図・役 ---------------------------------------------------------------------

def test_manifest_adds_only_the_effector_and_intent_projections() -> None:
    c0, as1 = A.c0_manifest_raw(), A.as1_manifest_raw()
    assert {k: v for k, v in as1.items() if k not in ("interfaces", "projections")} == \
           {k: v for k, v in c0.items() if k not in ("interfaces", "projections")}
    assert as1["interfaces"]["receptors"] == c0["interfaces"]["receptors"]
    assert c0["interfaces"]["effectors"] == [] and as1["interfaces"]["effectors"] == [A.EFFECTOR_ID]
    assert as1["projections"][:len(c0["projections"])] == c0["projections"]
    added = as1["projections"][len(c0["projections"]):]
    assert added == [{"from": f"{u}.intent", "to": A.EFFECTOR_ID} for u in A.UNITS]


@pytest.mark.parametrize("seed", SEEDS + (SILENT_SEED,))
def test_roles_are_a_permutation_and_recorded(seed) -> None:
    system = A.build(seed)
    roles = system.roles
    assert sorted((roles.source, roles.receiver, roles.other)) == sorted(A.UNITS)
    run_event = system.log.of(RuntimeEventType.RUN)[0]
    assert run_event.data["roles"] == roles.as_dict()
    assert A.assign_roles(seed) == roles                     # 同じ seed なら同じ割り当て


# ---- 出口（IC-1〜IC-6） ---------------------------------------------------------------

@pytest.mark.parametrize("seed", SEEDS)
def test_ic1_ic5_one_intent_per_source_firing_and_nothing_is_dropped(seed) -> None:
    system = run(seed, 1500)
    source_fires = [p for p, u in system.log.activity() if u == system.roles.source]
    deltas = intent_deltas(system.log)
    assert source_fires, "道具の確認用の個体では源が発火していること"
    assert [d["created_pulse"] for d in deltas] == source_fires                 # IC-1：発火 1 回に意図 1 つ
    assert {d["source_id"] for d in deltas} == {system.roles.source}            # 源以外から出ない
    effector = system.app.effectors[A.EFFECTOR_ID]
    assert effector.received == [d["delta_id"] for d in deltas]                 # IC-5：Effector が全部受けた
    assert system.world.intents == [(d["created_pulse"], d["delta_id"]) for d in deltas]   # 世界が全部記録した


@pytest.mark.parametrize("seed", SEEDS)
def test_ic3_ic6_intents_go_only_to_the_effector_on_the_intent_port(seed) -> None:
    system = run(seed, 1500)
    deltas = [e.data for e in system.log.of(RuntimeEventType.DELTA)]
    assert deltas, "意図の Delta がある"
    for d in deltas:
        assert d["kind"] == DeltaKind.INTENT
        assert d["target_id"] == A.EFFECTOR_ID and d["output_port"] == A.INTENT_PORT
        assert d["payload"] == A.ACTION_ID                                       # IC-6：行動の ID だけ
    assert system.app.pulse_runtime.brain_state.deltas == ()                    # CT-G1b：脳の中に Delta がない


class _FakeUnit:
    """IC-2 の確かめのための中身（決めた提案と発火を返す）。"""

    unit_id = "s1"

    def __init__(self, fired: bool) -> None:
        self._fired = fired
        self.proposal = ProposedDelta(kind=DeltaKind.CONTENT, payload="relay", cited_delta_ids=("d000001",))

    def tick(self, view, context):
        return UnitStepResult(proposed_deltas=(self.proposal,),
                              activity=ActivityEvent("s1", 1) if self._fired else None)


@pytest.mark.parametrize("fired", [True, False])
def test_ic2_the_inner_proposals_are_kept_and_one_intent_is_added_only_on_firing(fired) -> None:
    inner = _FakeUnit(fired)
    step = A.IntentSourceUnit(inner).tick(None, None)
    assert step.proposed_deltas[0] == inner.proposal                            # 中の提案はそのまま
    if fired:
        assert step.proposed_deltas[1:] == (ProposedDelta(kind=DeltaKind.INTENT, payload="X", output_port="intent"),)
    else:
        assert step.proposed_deltas == (inner.proposal,)


# ---- 世界（W-1・WC-1〜WC-6・W-2） --------------------------------------------------------

def test_w1_delay_must_be_at_least_two() -> None:
    with pytest.raises(ValueError):
        A.AS1World(consequence_receptor="receptor.x1", delay=1)
    world = A.AS1World(consequence_receptor="receptor.x1", delay=2)
    world.drain("receptor.x1", 5)
    with pytest.raises(A.PastPulseReservation):
        world.reserve(A.CONSEQUENCE, "receptor.x1", 5)


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("delay", [2, 3])
def test_wc1_wc2_k1_consequences_follow_the_rule_and_come_only_from_the_world(seed, delay) -> None:
    horizon = 1500
    system = run(seed, horizon, delay=delay)
    roles = system.roles
    expected = [(p + delay - 1, roles.consequence_receptor) for p, _ in system.world.intents if p + delay - 1 <= horizon]
    assert system.log.sensory() == expected                                       # WC-2：規則どおり
    assert all(r != roles.source_receptor for _, r in system.log.sensory())      # K1：源の Receptor に刺激なし
    realized = [(p, r) for p, r, _, n in system.world.realized for _ in range(n)]
    assert realized == expected                                                   # WC-1b：出来事は世界の正本どおり
    for receptor in system.app.receptors.values():
        assert isinstance(receptor, A.WorldReceptor)                              # Receptor は予定を持たない
        assert set(vars(receptor)) == {"_receptor_id", "world"}


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("delay", [2, 3])
def test_w2_consequence_reservations_never_share_a_pulse_in_the_minimal_as1(seed, delay) -> None:
    system = run(seed, 1500, delay=delay)
    assert all(len(rids) == 1 for _, _, rids, _ in system.world.realized)


def test_silent_source_gets_nothing_from_the_world() -> None:
    system = run(SILENT_SEED, 1500)
    assert system.world.intents == [] and system.log.sensory() == []           # 何もしなければ何も来ない


@pytest.mark.parametrize("rule,expected_counts", [(A.PER_RESERVATION, (2, 1)), (A.MERGE, (1, 1))])
def test_wc1c_cancel_acts_on_one_reservation_and_events_follow_the_multiplicity_rule(rule, expected_counts) -> None:
    def world_with_two():
        w = A.AS1World(consequence_receptor="receptor.x2", delay=2, multiplicity=rule)
        w.reserve(A.EXOGENOUS, "receptor.x2", 10)
        e = w.reserve(A.CONSEQUENCE, "receptor.x2", 10, origin="d000001")
        return w, e
    full, _ = world_with_two()
    cut, e = world_with_two()
    assert cut.cancel(e.rid) == e
    assert [r.rid for r in cut.pending] == [r.rid for r in full.pending if r.rid != e.rid]   # 予約の差は e だけ
    assert (full.drain("receptor.x2", 10), cut.drain("receptor.x2", 10)) == expected_counts
    with pytest.raises(KeyError):
        cut.cancel(e.rid)


# ---- C0 への還元（WC-6・CT-G1a） ------------------------------------------------------------

@pytest.mark.parametrize("seed", ALL_SOURCE_ROLES)
@pytest.mark.parametrize("outlet", [True, False])
def test_g1a_ignoring_intents_with_the_c0_schedule_reproduces_the_existing_c0_experiment(seed, outlet) -> None:
    until = 2400                                   # 0012 の試行（1800 から）を含む
    c0_log = W12.ExperimentLog()
    c0 = W12.build(PROTOCOL_0012, "ordered", seed, c0_log)
    W12.advance_to(c0, until)
    system = run(seed, until, respond=False, exogenous=c0_schedule(seed), outlet=outlet)
    assert [list(x) for x in system.log.activity()] == c0_log.activity()
    assert [list(x) for x in system.log.sensory()] == c0_log.sensory()
    assert {u.unit_id: u.export_state() for u in system.app.units.all()} == \
           {u.unit_id: u.export_state() for u in c0.units.all()}
    assert system.app.connections.export_state() == c0.connections.export_state()


@pytest.mark.parametrize("seed", SEEDS)
def test_g1a_without_exogenous_input_the_open_loop_equals_c0_without_input(seed) -> None:
    c0, _ = A.build_c0(seed, exogenous=())
    A.advance_to(c0, 1500)
    system = run(seed, 1500, respond=False)
    assert {u.unit_id: u.export_state() for u in system.app.units.all()} == \
           {u.unit_id: u.export_state() for u in c0.units.all()}
    assert system.app.connections.export_state() == c0.connections.export_state()


# ---- 完全な複製（CT-Σ1〜Σ5） ------------------------------------------------------------

@pytest.mark.parametrize("seed", SEEDS)
def test_sigma1_sigma4_a_clone_without_intervention_stays_identical(seed) -> None:
    branch, horizon = 400, 900
    original = run(seed, branch)
    twin = A.clone(original)
    s0 = A.sigma(original)
    assert A.sigma(twin) == s0
    assert s0["runtime"] == {"intent_seq": 0, "degraded": False, "in_flight": 0}     # CT-Σ4
    A.advance_to(original.app, horizon)
    A.advance_to(twin.app, horizon)
    assert A.sigma(twin) == A.sigma(original)                                         # CT-Σ1
    after = [x for x in original.log.activity() if x[0] > branch]
    assert twin.log.activity() == after


@pytest.mark.parametrize("seed", SEEDS)
def test_sigma2_a_clone_shares_nothing_with_the_original(seed) -> None:
    original = run(seed, 400)
    before = A.sigma(original)
    twin = A.clone(original)
    twin.world.reserve(A.EXOGENOUS, twin.roles.consequence_receptor, 450)
    A.transplant(twin.app, {f"{twin.roles.receiver}.main->{twin.roles.source}": 0.0})
    twin.connections.declare([A.Intervention(A.FB1, frozenset({f"{twin.roles.receiver}.main->{twin.roles.source}"}))])
    A.advance_to(twin.app, 500)
    assert A.sigma(original) == before


@pytest.mark.parametrize("seed", SEEDS)
def test_sigma3_reexecution_gives_the_same_state_as_the_clone(seed) -> None:
    original = run(seed, 400)
    twin = A.clone(original)
    again = run(seed, 400)                                                            # M2
    assert A.sigma(again) == A.sigma(twin) == A.sigma(original)


def _g6_pair(seed: int, k: int = 2, **kw):
    """k 番目の意図の Pulse t の処理の後で分岐し、系 N では、その意図の結果 e の予約だけを取り消す。"""
    probe = run(seed, 1500, **kw)
    t, delta_id = probe.world.intents[k]
    f = run(seed, t, **kw)
    n = A.clone(f)
    e = next(r for r in n.world.pending if r.origin == delta_id)
    assert e.pulse == t + f.world.delay - 1
    n.world.cancel(e.rid)
    return f, n, t, e


@pytest.mark.parametrize("seed", SEEDS)
def test_sigma5_cancelling_e_removes_only_e_and_exactly_its_event(seed) -> None:
    f, n, t, e = _g6_pair(seed)
    pf, pn = A.sigma(f)["world"]["pending"], A.sigma(n)["world"]["pending"]
    assert [row for row in pf if row[0] != e.rid] == pn and len(pf) == len(pn) + 1  # (i) 予約の差は e だけ
    horizon = t + 300
    A.advance_to(f.app, horizon)
    A.advance_to(n.app, horizon)
    first = [x for x in (A.first_intent_after(f, t), A.first_intent_after(n, t)) if x is not None]
    stop = min(first) if first else horizon
    sens_f = [x for x in f.log.sensory() if t < x[0] <= stop]
    sens_n = [x for x in n.log.sensory() if x[0] <= stop]
    assert sens_f.count((e.pulse, e.receptor_id)) == sens_n.count((e.pulse, e.receptor_id)) + 1   # (ii)
    assert [x for x in sens_f if x != (e.pulse, e.receptor_id)] == \
           [x for x in sens_n if x != (e.pulse, e.receptor_id)]                                     # (iii)


def test_sigma5_with_merge_a_cancelled_reservation_may_leave_the_event() -> None:
    seed = SEEDS[0]
    probe = run(seed, 1500)
    t, _ = probe.world.intents[2]
    clash = [(t + 1, A.assign_roles(seed).consequence_receptor)]                  # 結果と同じ Receptor・同じ Pulse の外生の刺激
    f, n, t2, e = _g6_pair(seed, multiplicity=A.MERGE, exogenous=clash)
    assert t2 == t
    A.advance_to(f.app, t + 1)
    A.advance_to(n.app, t + 1)
    at = (t + 1, e.receptor_id)
    assert f.log.sensory().count(at) == 1 and n.log.sensory().count(at) == 1    # 予約は消えても、出来事は残る


# ---- 介入（CT-I1〜I6） ----------------------------------------------------------------

def _strip(s: dict) -> dict:
    return {k: v for k, v in s.items() if k != "interventions"}


@pytest.mark.parametrize("seed", SEEDS)
def test_i1_an_empty_wrapper_is_identical_to_no_wrapper(seed) -> None:
    wrapped = run(seed, 1500, interventions=True)
    bare = run(seed, 1500, interventions=False)
    assert _strip(A.sigma(wrapped)) == _strip(A.sigma(bare))
    assert wrapped.log.activity() == bare.log.activity()


def _replay_store(system, start_state: dict, fired_by_pulse: dict, first: int, last: int):
    """同じ発火の列を、介入のない ConnectionStore に、区間の始まりの状態から与え直す（規則どおりの参照）。"""
    store = copy.deepcopy(system.connections.inner)
    store.import_state(start_state)
    for pulse in range(first, last + 1):
        store.apply_activity(fired_by_pulse.get(pulse, ()), A.PULSE_INTERVAL_SECONDS)
    return store.export_state()


def _fired(log) -> dict:
    out: dict = {}
    for p, u in log.activity():
        out.setdefault(p, []).append(u)
    return out


@pytest.mark.parametrize("seed", SEEDS)
def test_i2_fb1_zeroes_only_the_target_transmission_and_the_target_weight_keeps_its_rule(seed) -> None:
    keep = A.AS1Log.DEFAULT_KEEP | {RuntimeEventType.VIEW}
    t1, t2 = 300, 600
    system = run(seed, t1, log=A.AS1Log(keep=keep))
    roles = system.roles
    target = f"{roles.receiver}.main->{roles.source}"
    target_key = (roles.receiver, "main", roles.source)
    start = system.app.connections.export_state()
    system.declare([A.Intervention(A.FB1, frozenset({target}))])
    for pulse in range(t1 + 1, t2 + 1):
        A.advance_to(system.app, pulse)
        returned, inner = system.connections.last_returned, system.connections.last_inner
        assert returned[target_key] == 0.0                                                   # (i)
        assert {k: v for k, v in returned.items() if k != target_key} == \
               {k: v for k, v in inner.items() if k != target_key}                          # (ii) 非介入性
    views = [e.data for e in system.log.of(RuntimeEventType.VIEW)
             if t1 + 2 <= e.pulse <= t2 + 1 and e.data["unit_id"] == roles.source]
    drives = [w for v in views for src, w in v["drives"] if src == roles.receiver]
    assert drives and all(w == 0.0 for w in drives)                                         # 重み 0 の駆動は残る
    replay = _replay_store(system, start, _fired(system.log), t1 + 1, t2)
    assert system.app.connections.export_state()[target] == replay[target]                  # (iii) 規則どおり


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("policy", [A.ADVANCE, A.HOLD])
def test_i3_freeze_holds_the_target_weights_and_leaves_the_rest_to_the_rule(seed, policy) -> None:
    t1, t2 = 300, 600
    system = run(seed, t1)
    roles = system.roles
    target = f"{roles.receiver}.main->{roles.source}"
    start = system.app.connections.export_state()
    system.declare([A.Intervention(A.FREEZE, frozenset({target}), policy)])
    A.advance_to(system.app, t2)
    end = system.app.connections.export_state()
    replay = _replay_store(system, start, _fired(system.log), t1 + 1, t2)
    assert end[target]["weight"] == start[target]["weight"]
    if policy == A.ADVANCE:
        assert (end[target]["pre_trace"], end[target]["post_trace"]) == \
               (replay[target]["pre_trace"], replay[target]["post_trace"])
    else:
        assert (end[target]["pre_trace"], end[target]["post_trace"]) == \
               (start[target]["pre_trace"], start[target]["post_trace"])
    assert {c: v for c, v in end.items() if c != target} == {c: v for c, v in replay.items() if c != target}


@pytest.mark.parametrize("seed", SEEDS)
def test_i4_transplant_replaces_only_the_declared_weight(seed) -> None:
    system = run(seed, 400)
    roles = system.roles
    target = f"{roles.receiver}.main->{roles.source}"
    before = A.sigma(system)
    A.transplant(system.app, {target: 0.005})
    after = A.sigma(system)
    assert after["connections"][target] == {**before["connections"][target], "weight": 0.005}
    assert {k: v for k, v in after.items() if k != "connections"} == {k: v for k, v in before.items() if k != "connections"}
    assert {c: v for c, v in after["connections"].items() if c != target} == \
           {c: v for c, v in before["connections"].items() if c != target}


@pytest.mark.parametrize("seed", SEEDS)
def test_i5_one_sided_freeze_is_reported_by_the_pair_sum(seed) -> None:
    t1, t2 = 300, 900
    w_max = 0.01
    roles = A.assign_roles(seed)
    pair = tuple(sorted((roles.receiver, roles.source)))
    one = run(seed, t1)
    one.connections.declare([A.Intervention(A.FREEZE, frozenset({f"{roles.receiver}.main->{roles.source}"}))])
    both = run(seed, t1)
    both.connections.declare([A.Intervention(A.FREEZE, frozenset({f"{roles.receiver}.main->{roles.source}",
                                                                   f"{roles.source}.main->{roles.receiver}"}))])
    A.advance_to(one.app, t2)
    A.advance_to(both.app, t2)
    assert A.pair_sums(both.app.connections.export_state())[pair] == pytest.approx(w_max, abs=1e-15)
    assert A.pair_sums(one.app.connections.export_state())[pair] != pytest.approx(w_max, abs=1e-12)   # F1 を破る


@pytest.mark.parametrize("seed", SEEDS)
def test_i6_interventions_do_not_touch_receptor_inputs_or_unit_dynamics(seed) -> None:
    system = run(seed, 300)
    plastic = [cid for cid in system.app.connections.export_state()]
    system.connections.declare([A.Intervention(A.FB1, frozenset(plastic))])
    A.advance_to(system.app, 301)
    returned = system.connections.last_returned
    for receptor, unit in (("receptor.x1", "s1"), ("receptor.x2", "s2"), ("receptor.x3", "s3")):
        assert returned[(receptor, "main", unit)] == 1.0
    source = (ROOT / "experiments" / "as1_closed_loop" / "as1.py").read_text(encoding="utf-8")
    assert "anima_ll.unit.dynamics" not in source and "SimpleActivityDynamics" not in source


# ---- 開いたループ（OPEN-LOOP）と命題 G-2 -------------------------------------------------------

@pytest.mark.parametrize("seed", SEEDS)
def test_open_loop_replay_of_the_own_sensory_sequence_reproduces_the_closed_loop(seed) -> None:
    closed = run(seed, 1500)
    recorded = [(p, r) for p, r in closed.log.sensory()]
    opened = run(seed, 1500, respond=False, exogenous=recorded)
    assert opened.log.activity() == closed.log.activity()
    assert opened.app.connections.export_state() == closed.app.connections.export_state()
    assert opened.world.intents == closed.world.intents        # 意図は記録されるが、結果は持たない


# ---- 監査 019〜021 -----------------------------------------------------------------------

def test_019_the_seeds_cover_every_source_role() -> None:
    assert sorted(A.assign_roles(s).source for s in ALL_SOURCE_ROLES) == list(A.UNITS)


@pytest.mark.parametrize("seed", ALL_SOURCE_ROLES)
def test_019_birth_states_and_the_birth_random_stream_are_those_of_c0(seed) -> None:
    system = A.build(seed)
    c0, _ = A.build_c0(seed, exogenous=())
    assert {u.unit_id: u.export_state() for u in system.app.units.all()} == \
           {u.unit_id: u.export_state() for u in c0.units.all()}                  # Pulse 0：出生時の状態が同じ
    assert isinstance(system.app.units.get(system.roles.source), A.IntentSourceUnit)
    assert system.app.connections.export_state() == c0.connections.export_state()


@pytest.mark.parametrize("seed", SEEDS)
def test_020_a_declaration_between_pulses_starts_at_the_next_pulse(seed) -> None:
    keep = A.AS1Log.DEFAULT_KEEP | {RuntimeEventType.VIEW}
    probe = run(seed, 1500)
    t = next(p for p, u in probe.log.activity() if u == probe.roles.receiver and p > 200)   # 受が発火した Pulse
    system = run(seed, t, log=A.AS1Log(keep=keep))
    roles = system.roles
    target = f"{roles.receiver}.main->{roles.source}"
    system.declare([A.Intervention(A.FB1, frozenset({target}))])
    assert system.connections.history[-1][0] == t                                  # 境界の記録
    A.advance_to(system.app, t + 1)
    view = next(e.data for e in system.log.of(RuntimeEventType.VIEW)
                if e.pulse == t + 1 and e.data["unit_id"] == roles.source)
    carried = [w for src, w in view["drives"] if src == roles.receiver]
    assert carried and carried[0] > 0.0              # Pulse t に成立した駆動は、宣言の前の重みのまま届く
    assert system.connections.last_returned[(roles.receiver, "main", roles.source)] == 0.0   # Pulse t + 1 の伝達から 0


@pytest.mark.parametrize("seed", SEEDS)
def test_020_observing_the_wrapper_does_not_move_the_intervals(seed) -> None:
    def scenario(observe: bool):
        system = run(seed, 300)
        target = f"{system.roles.receiver}.main->{system.roles.source}"
        system.declare([A.Intervention(A.FB1, frozenset({target}))])
        for pulse in range(301, 501):
            A.advance_to(system.app, pulse)
            if observe:
                for _ in range(3):
                    system.connections.weights()
                    system.connections.export_state()
        system.clear()
        A.advance_to(system.app, 800)
        return system
    seen, unseen = scenario(True), scenario(False)
    assert seen.log.activity() == unseen.log.activity()
    assert seen.app.connections.export_state() == unseen.app.connections.export_state()


@pytest.mark.parametrize("seed", SEEDS)
def test_020_the_first_intent_is_found_from_the_source_firing(seed) -> None:
    probe = run(seed, 1500)
    t = probe.world.intents[3][0]
    expected = probe.world.intents[4][0]
    system = run(seed, t)
    tau = A.advance_until_first_intent(system, t, t + 300)
    assert tau == expected and system.pulse == tau
    assert system.world.intents[-1][0] == tau        # 同じ Pulse の 7 で世界にも届いている
    assert A.advance_until_first_intent(run(SILENT_SEED, 100), 100, 400) is None   # 打ち切り


@pytest.mark.parametrize("seed", SEEDS)
def test_021_one_connection_state_is_the_source_for_runtime_lifecycle_and_tools(seed) -> None:
    system = run(seed, 300)
    store, wrapper = system.app.connections, system.connections
    assert wrapper.inner is store
    assert system.app.pulse_runtime._connections is wrapper and system.app.lifecycle._connections is wrapper
    assert system.app.lifecycle.save_snapshot().connections == store.export_state()
    twin = A.clone(system)
    assert twin.connections.inner is twin.app.connections and twin.app.connections is not store
    assert twin.app.pulse_runtime._connections is twin.connections
    target = f"{system.roles.receiver}.main->{system.roles.source}"
    A.transplant(system.app, {target: 0.002})
    assert wrapper.weights()[(system.roles.receiver, "main", system.roles.source)] == 0.002   # 観察と実の重みが一致
    assert A.pair_sums(store.export_state()) != A.pair_sums(twin.app.connections.export_state())
