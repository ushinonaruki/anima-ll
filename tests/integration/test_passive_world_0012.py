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
    initial = W.weights_of(app)
    W.advance_to(app, 1795)
    copied, clone_log = W.clone(app, log)
    W.advance_to(copied, 1900)
    W.advance_to(app, 1900)
    assert [a for a in log.activity() if a[0] > 1795] == clone_log.activity()
    assert full_state(copied) == full_state(app)
    assert W.weights_of(app) != initial   # 重みが実際に動いている（複製が可塑性の状態まで写していることの確認になる）


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


# ---- 動作確認 S1〜S3 の数え方（v0.3 §5.5。合成した記録で確かめる） ---------------------------------

S = _load("smoke_0012_test", EXP / "smoke.py")


def test_t_min_from_the_protocol_is_9_for_minimal_v3() -> None:
    assert S.t_min(PROTOCOL) == 9


def test_reexcitation_counts_intervals_below_t_min_but_not_at_t_min() -> None:
    firings = [(100, "s1"), (108, "s1"), (200, "s2"), (209, "s2")]
    found = S.reexcitations(firings, [], PROTOCOL)
    assert [(x["unit"], x["interval"]) for x in found] == [("s1", 8)]


def test_reexcitation_excludes_firings_caused_by_the_sensory_event() -> None:
    # s3 の Receptor は receptor.x3。p − 1 に感覚の出来事があれば、p の発火は感覚の入力による
    firings = [(1802, "s3"), (1803, "s3"), (1805, "s3")]
    sensory = [(1802, "receptor.x3")]
    found = S.reexcitations(firings, sensory, PROTOCOL)
    assert [(x["first"], x["second"]) for x in found] == [(1803, 1805)]   # v0.2 の seed 1001 の形


def test_clone_reexcitation_joins_main_history_and_ignores_the_probe_a() -> None:
    roles = W.role_receptors(PROTOCOL, SEED)
    units = W.role_units(PROTOCOL, SEED)
    run = {
        "seed": SEED, "condition": "ordered", "roles": roles, "role_units": units,
        "activity": [[595, units["B"]]], "sensory": [],
        "probes": [{"phase": "pre", "t0": 600,
                    "fires": [[1, units["A"]], [3, units["B"]], [5, units["A"]]]}],
    }
    found = S.s2_reexcitations([run], PROTOCOL)["pre_probe_clones"]
    # s_B：595（本体）→ 603（複製）は間隔 8 で数える。s_A：601 は A の感覚によるもの、605 は 601 から間隔 4 で数える
    assert sorted((x["unit"], x["first"], x["second"]) for x in found) == sorted(
        [(units["B"], 595, 603), (units["A"], 601, 605)])


def test_s1_and_s3_fractions_from_synthetic_records() -> None:
    units = W.role_units(PROTOCOL, SEED)
    starts = W.trial_starts(PROTOCOL)
    run = {
        "seed": SEED, "condition": "ordered", "role_units": units,
        "probes": [{"phase": "pre", "t0": 600, "fires": [[2, units["B"]], [4, units["C"]]]},
                   {"phase": "pre", "t0": 660, "fires": [[3, units["B"]], [5, units["C"]]]},
                   {"phase": "post", "t0": 13800, "fires": [[2, units["C"]]]}],
        "activity": [[starts[0] + 2, units["B"]], [starts[0] + 2, units["C"]], [starts[1] + 2, units["B"]]],
    }
    s1 = S.s1_fractions([run], PROTOCOL)
    assert (s1["B"], s1["C"], s1["probes"]) == (1.0, 0.5, 2)   # 窓は t0＋2〜4。post は数えない
    s3 = S.s3_fraction([run], PROTOCOL, starts)
    assert s3 == {"fraction": 1 / len(starts), "trials": len(starts)}
