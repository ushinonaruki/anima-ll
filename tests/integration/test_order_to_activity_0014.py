"""実験 0014 の道具の契約テスト（README §3.3・§6・§7）。

判定の seed（4001〜4020）は使わない。走らせるのは動作確認の範囲の seed（5001〜5006）だけ。
判定の量（p・w）はここでは計算しない。ΔR を見るのは、A の刺激を入れない試し（deliver=False）で、
A が t0 ＋ 1 に発火しなかったときに 2 腕の B・C が同じになるという、runtime の順序の帰結を確かめるときだけ。
"""

import copy
import importlib.util
import random
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments" / "0014_order_to_activity"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))
SEEDS = range(5001, 5007)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W = _load("world_0014_test", EXP / "world.py")


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)


@pytest.fixture
def A():
    return _load("analyze_0014_test", EXP / "analyze.py")


@pytest.fixture(scope="module")
def smoke_run():
    """動作確認の seed 1 つを本番と同じ手順で走らせた生の記録（判定の量は計算しない）。"""
    import os
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        return _load("run_0014_test", EXP / "run.py").run_seed(5001)
    finally:
        os.chdir(cwd)


def test_protocol_and_tools_are_aligned() -> None:
    _load("alignment_0014_test", EXP / "alignment.py").check(PROTOCOL)


def test_timeline_is_derived_from_existing_values() -> None:
    assert W.probe_count(PROTOCOL) == 300                       # adaptation_tau 300 ÷ 1.0
    assert W.probe_times(PROTOCOL) == list(range(12001, 12301))
    assert W.w_post_pulse(PROTOCOL) == 12000
    assert W.trial_starts(PROTOCOL)[0] == 1 and W.trial_starts(PROTOCOL)[-1] == 11941


@pytest.mark.parametrize("seed", SEEDS)
def test_stimuli_have_equal_counts_and_the_same_times(seed) -> None:
    o, s = W.stimuli(PROTOCOL, "ordered", seed), W.stimuli(PROTOCOL, "shuffled", seed)
    assert [t for t, _ in o] == [t for t, _ in s]
    for x in (o, s):
        assert {r: sum(1 for _, v in x if v == r) for r in "ABC"} == {"A": 200, "B": 200, "C": 200}
    at = dict(o)
    assert all(at[t + 2] == "B" and at[t + 30] == "C" for t, v in o if v == "A")
    assert o[-1] == (11971, "C")
    d = W.first_divergence(PROTOCOL, seed)
    assert d is not None and all(a == b for a, b in zip(o, s) if a[0] < d) and dict(o)[d] != dict(s)[d]


def test_shuffle_uses_the_named_stream() -> None:
    labels = [v for _, v in W.ordered_stimuli(PROTOCOL)]
    random.Random("0014-shuffle:5001").shuffle(labels)
    assert [v for _, v in W.shuffled_stimuli(PROTOCOL, 5001)] == labels
    assert W.shuffled_stimuli(PROTOCOL, 5001) != W.shuffled_stimuli(PROTOCOL, 5002)


def test_equalized_weights_formula() -> None:
    units = {"A": "s1", "B": "s2", "C": "s3"}
    w = {"s1.main->s2": 0.008, "s2.main->s1": 0.002, "s1.main->s3": 0.003, "s3.main->s1": 0.007,
         "s2.main->s3": 0.006, "s3.main->s2": 0.004}
    e = W.equalized_weights(w, units, 0.01)
    assert e == pytest.approx({"s1.main->s2": 0.0055, "s1.main->s3": 0.0055,
                               "s2.main->s1": 0.0045, "s3.main->s1": 0.0045})
    new = w | e
    a = lambda d, i, j: d[f"{i}.main->{j}"] - d[f"{j}.main->{i}"]
    assert a(new, "s1", "s2") == pytest.approx(a(new, "s1", "s3"))
    assert a(new, "s1", "s2") + a(new, "s1", "s3") == pytest.approx(a(w, "s1", "s2") + a(w, "s1", "s3"))
    assert W.w_difference(new, units) == pytest.approx(0)
    assert W.w_difference(w, units) == pytest.approx(0.005)


@pytest.mark.parametrize("seed", SEEDS)
def test_probe_passes_its_checks_and_leaves_the_main_individual_untouched(seed) -> None:
    log = W.ExperimentLog()
    app = W.build(PROTOCOL, "ordered", seed, log)
    W.advance_to(app, 400)
    before, events = W.snapshot(app), len(log.events)
    rec = W.probe(PROTOCOL, app, log, seed, 401)
    assert W.check_probe(PROTOCOL, seed, rec, W.w_max(PROTOCOL)) == []
    assert app.lifecycle.pulse == 400 and W.snapshot(app) == before and len(log.events) == events
    assert {p for p, _ in rec["activity"]["as_is"]} <= {402, 403}


@pytest.mark.parametrize("seed", SEEDS)
def test_runtime_order_arms_differ_only_through_the_t0_plus_1_firing_of_a(seed) -> None:
    """README §3.3 の帰結：t0 の終わりで分けると、2 腕の t0 ＋ 1 の発火は同じで、
    A が t0 ＋ 1 に発火しなかった試しでは、t0 ＋ 2 の B・C も 2 腕で同じ（ΔR ＝ 0）。

    A の刺激を入れない試し（deliver=False）で、A が発火しない場面を作って確かめる。
    """
    log = W.ExperimentLog()
    app = W.build(PROTOCOL, "ordered", seed, log)
    units = W.role_units(PROTOCOL, seed)
    silent = 0
    for t0 in range(2001, 2101):
        W.advance_to(app, t0 - 1)
        rec = W.probe(PROTOCOL, app, log, seed, t0, deliver=False)
        t1 = [x for x in rec["activity"]["as_is"] if x[0] == t0 + 1]
        assert t1 == [x for x in rec["activity"]["equalized"] if x[0] == t0 + 1]
        if not W.fired_at(rec["activity"]["as_is"], units["A"], t0 + 1):
            silent += 1
            # B・C だけを比べる（A 自身の t0 ＋ 2 は、B→A・C→A の違いで 2 腕が分かれうる。README §3.3）
            bc = (units["B"], units["C"])
            t2 = {arm: [x for x in act if x[0] == t0 + 2 and x[1] in bc] for arm, act in rec["activity"].items()}
            assert t2["as_is"] == t2["equalized"]
            assert W.delta_r(rec, units, 2) == 0
    assert silent > 0                     # 空の確認にしない


def test_check_probe_detects_tampering() -> None:
    log = W.ExperimentLog()
    app = W.build(PROTOCOL, "ordered", 5003, log)
    W.advance_to(app, 400)
    rec = W.probe(PROTOCOL, app, log, 5003, 401)
    w_max = W.w_max(PROTOCOL)
    units = W.role_units(PROTOCOL, 5003)
    ids = W.four_ids(units)

    bad = copy.deepcopy(rec)
    bad["fork"]["equalized"]["connections"][ids["AB"]]["pre_trace"] += 1.0
    assert any("痕跡" in p for p in W.check_probe(PROTOCOL, 5003, bad, w_max))
    bad = copy.deepcopy(rec)
    bad["fork"]["equalized"]["connections"][ids["BA"]]["weight"] += 1e-4
    assert any("式どおり" in p for p in W.check_probe(PROTOCOL, 5003, bad, w_max))
    bad = copy.deepcopy(rec)
    bc = W.connection_id(units["B"], units["C"])
    bad["fork"]["equalized"]["connections"][bc]["weight"] += 1e-4
    assert any("対象外" in p for p in W.check_probe(PROTOCOL, 5003, bad, w_max))
    bad = copy.deepcopy(rec)
    bad["fork"]["equalized"]["units"][units["B"]]["adaptation"] += 1e-4
    assert any("Unit の状態" in p for p in W.check_probe(PROTOCOL, 5003, bad, w_max))
    bad = copy.deepcopy(rec)
    bad["activity"]["equalized"].append([402, "s9"])
    assert any("t0 ＋ 1" in p for p in W.check_probe(PROTOCOL, 5003, bad, w_max))
    bad = copy.deepcopy(rec)
    bad["base_sensory"] = []
    assert any("感覚の出来事" in p for p in W.check_probe(PROTOCOL, 5003, bad, w_max))


def test_full_smoke_seed_passes_manipulation_from_raw(A, smoke_run) -> None:
    assert A.manipulation([smoke_run]) == []
    assert all(len(smoke_run["conditions"][c]["probes"]) == 300 for c in ("ordered", "shuffled"))


def test_manipulation_detects_raw_problems(A, smoke_run) -> None:
    bad = copy.deepcopy(smoke_run)
    bad["conditions"]["shuffled"]["sensory"].pop()
    assert any("shuffled" in p for p in A.manipulation([bad]))
    bad = copy.deepcopy(smoke_run)
    bad["conditions"]["ordered"]["clone"]["activity"].append([12300, "s1"])
    assert any("clone_identity" in p for p in A.manipulation([bad]))
    bad = copy.deepcopy(smoke_run)
    bad["conditions"]["ordered"]["birth"]["s1"]["activity"] += 1e-9
    assert any("出生時" in p for p in A.manipulation([bad]))


def test_smoke_report_hides_p_and_w(A, smoke_run) -> None:
    data = {"meta": {"smoke": True, "git_commit": "x", "protocol": PROTOCOL, "manifest": W.manifest_raw(PROTOCOL)},
            "runs": [smoke_run]}
    report = A.analyze(data)
    assert "judgment" not in report and "per_seed" not in report and "records" not in report
    assert not report["valid"]              # 6 個体のうち 1 個体だけなので、完全性で止まる


def test_invalid_data_does_not_compute_judgment_statistics(A) -> None:
    data = {"meta": {"smoke": False, "git_commit": "x", "protocol": {}, "manifest": {}}, "runs": []}
    report = A.analyze(data)
    assert not report["valid"] and report["judgment"] is None and report["per_seed"] is None
    assert report["records"] is None
