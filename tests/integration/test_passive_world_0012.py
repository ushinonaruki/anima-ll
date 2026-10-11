"""実験 0012 の人工世界と複製・試しの道具の契約テスト。

事前登録：experiments/0012_passive_world/README.md §3.4・§5.3。
判定に使う seed（1〜20）の結果は見ない。ここで走らせるのは範囲外の seed（1001〜1006）だけ。
"""

import importlib.util
from collections import Counter
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments" / "0012_passive_world"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))
SEED = 1001
STATE_SEEDS = range(1001, 1007)   # (seed − 1) mod 6 が 6 通りすべてになる


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W = _load("world_0012_test", EXP / "world.py")


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)   # protocol の dynamics_from はリポジトリ直下からの相対パス


def full_state(app) -> dict:
    return {
        "pulse": app.lifecycle.pulse,
        "units": {u.unit_id: u.export_state() for u in app.units.all()},
        "connections": app.connections.export_state(),
        "drives": [(d.source_id, d.target_id, d.weight, d.created_pulse) for d in app.pulse_runtime.brain_state.drives],
    }


def test_protocol_and_tools_are_aligned() -> None:
    _load("alignment_0012_test", EXP / "alignment.py").check(PROTOCOL)


def test_role_assignment_uses_each_order_4_4_3_3_3_3_times_over_seeds_1_to_20() -> None:
    # 個体の結果ではなく、seed の番号からの割り当ての算術だけを確かめる
    first, last = PROTOCOL["seeds"]["first"], PROTOCOL["seeds"]["last"]
    used = Counter(tuple(W.role_receptors(PROTOCOL, s).values()) for s in range(first, last + 1))
    assert sorted(used.values(), reverse=True) == [4, 4, 3, 3, 3, 3]


@pytest.mark.parametrize("seed", STATE_SEEDS)
def test_stimulus_counts_match_the_protocol(seed) -> None:
    expected = PROTOCOL["judgment"]["manipulation"]["expected_counts"]
    delta = PROTOCOL["stimulus"]["delta_pulses"]
    for condition in PROTOCOL["stimulus"]["conditions"]:
        counts = W.stimulus_counts(W.stimuli(PROTOCOL, condition, seed), delta)
        assert {k: counts[k] for k in expected[condition]} == expected[condition]


def test_shuffled_keeps_the_ordered_timestamps_and_label_counts() -> None:
    ordered = W.ordered_stimuli(PROTOCOL, SEED)
    shuffled = W.shuffled_stimuli(PROTOCOL, SEED)
    assert [t for t, _ in shuffled] == [t for t, _ in ordered]
    assert Counter(l for _, l in shuffled) == Counter(l for _, l in ordered)
    assert [l for _, l in shuffled] != [l for _, l in ordered]


def test_sensory_events_happen_exactly_at_the_scheduled_pulses() -> None:
    log = W.ExperimentLog()
    app = W.build(PROTOCOL, "ordered", SEED, log)
    W.advance_to(app, 2400)
    roles = W.role_receptors(PROTOCOL, SEED)
    expected = sorted([t, roles[l]] for t, l in W.ordered_stimuli(PROTOCOL, SEED) if t <= 2400)
    assert sorted(log.sensory()) == expected


def test_running_in_segments_is_the_same_as_running_through() -> None:
    log_a, log_b = W.ExperimentLog(), W.ExperimentLog()
    a = W.build(PROTOCOL, "ordered", SEED, log_a)
    b = W.build(PROTOCOL, "ordered", SEED, log_b)
    W.advance_to(a, 2100)
    for stop in (599, 600, 1799, 1801, 2100):
        W.advance_to(b, stop)
    assert log_a.activity() == log_b.activity()
    assert full_state(a) == full_state(b)


def test_clone_without_probe_continues_exactly_like_the_main_individual() -> None:
    # 刺激と可塑性の変化を含む区間（経験の開始 1800 をまたぐ）で比べる
    log = W.ExperimentLog()
    app = W.build(PROTOCOL, "ordered", SEED, log)
    W.advance_to(app, 1795)
    copied, clone_log = W.clone(app, log)
    W.advance_to(copied, 1900)
    W.advance_to(app, 1900)
    assert [a for a in log.activity() if a[0] > 1795] == clone_log.activity()
    assert full_state(copied) == full_state(app)
    assert W.weights_of(app) != {cid: 0.25 for cid in W.weights_of(app)}   # 区間内で重みが実際に動いている


def test_probe_does_not_touch_the_main_individual() -> None:
    log_a, log_b = W.ExperimentLog(), W.ExperimentLog()
    a = W.build(PROTOCOL, "silent", SEED, log_a)
    b = W.build(PROTOCOL, "silent", SEED, log_b)
    a_receptor = W.role_receptors(PROTOCOL, SEED)["A"]
    for t0 in W.probe_times(PROTOCOL, "pre"):
        W.advance_to(a, t0 - 1)
        W.probe(PROTOCOL, a, log_a, a_receptor, t0)
    W.advance_to(a, 1799)
    W.advance_to(b, 1799)
    assert log_a.activity() == log_b.activity()
    assert log_a.sensory() == []          # 試しの A は本体に届かない
    assert full_state(a) == full_state(b)


def test_probe_gives_a_only_to_the_clone_at_t0_and_s_a_is_driven_at_t0_plus_1() -> None:
    log = W.ExperimentLog()
    app = W.build(PROTOCOL, "silent", SEED, log)
    t0 = W.probe_times(PROTOCOL, "pre")[0]
    W.advance_to(app, t0 - 1)
    copied, clone_log = W.clone(app, log)
    roles = W.role_receptors(PROTOCOL, SEED)
    copied.receptors[roles["A"]].inject(t0)
    W.advance_to(copied, t0)
    assert clone_log.sensory() == [[t0, roles["A"]]]
    s_a = W.role_units(PROTOCOL, SEED)["A"]
    assert [(d.source_id, d.target_id, d.created_pulse) for d in copied.pulse_runtime.brain_state.drives
            if d.source_id == roles["A"]] == [(roles["A"], s_a, t0)]


def test_inject_into_a_past_pulse_is_refused() -> None:
    log = W.ExperimentLog()
    app = W.build(PROTOCOL, "silent", SEED, log)
    W.advance_to(app, 10)
    with pytest.raises(ValueError):
        app.receptors["receptor.x1"].inject(10)


def test_conditions_are_identical_before_the_experience_starts() -> None:
    before = PROTOCOL["judgment"]["manipulation"]["identical_before_pulse"]
    results = []
    for condition in PROTOCOL["stimulus"]["conditions"]:
        log = W.ExperimentLog()
        app = W.build(PROTOCOL, condition, SEED, log)
        W.advance_to(app, before - 1)
        results.append((log.activity(), full_state(app)))
    assert results[0] == results[1] == results[2]
