"""実験 0016 の道具の契約テスト（README §3・§4・§6・§7）。

判定の seed（8001〜8020）は使わない。動作確認の seed（8101〜8106）は操作の確認だけに使い、E・S を計算しない。
A1・A7 の合成の契約（README §4）は、どの範囲にも属さない合成専用の seed（9015・9082）の Birth State の上に、
手で置いた重み・Unit の状態から、0016 と同じ手順（無入力の本体から毎 Pulse の独立な試し 300 回）で確かめる。
"""

import copy
import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments" / "0016_endpoint_readout"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))
SYNTHETIC_SEEDS = (9015, 9082)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W = _load("world_0016_test", EXP / "world.py")
W_MAX = W.w_max(PROTOCOL)


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)


@pytest.fixture
def A():
    return _load("analyze_0016_test", EXP / "analyze.py")


@pytest.fixture(scope="module")
def smoke_run():
    """動作確認の seed 1 つを本番と同じ手順で走らせた生の記録（E・S は計算しない）。"""
    import os
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        return _load("run_0016_test", EXP / "run.py").run_seed(8101)
    finally:
        os.chdir(cwd)


def test_protocol_and_tools_are_aligned() -> None:
    _load("alignment_0016_test", EXP / "alignment.py").check(PROTOCOL)
    for s in SYNTHETIC_SEEDS:
        assert s not in range(8001, 8021) and s not in range(8101, 8107)


def test_timeline_is_derived_from_existing_values() -> None:
    assert (W.experience_end(PROTOCOL), W.endpoint(PROTOCOL), W.total_pulses(PROTOCOL)) == (12000, 24000, 24300)
    assert W.probe_times(PROTOCOL) == list(range(24001, 24301))


def test_readout_formula_on_synthetic_records() -> None:
    u = {"A": "s1", "B": "s2", "C": "s3"}
    rec = {"t0": 100, "activity": {"as_is": [[101, "s1"], [102, "s2"]], "equalized": [[101, "s1"], [102, "s3"]]}}
    assert W.readout(rec, u, 2) == 2
    rec = {"t0": 100, "activity": {"as_is": [[101, "s1"], [102, "s2"]], "equalized": [[101, "s1"], [102, "s2"]]}}
    assert W.readout(rec, u, 2) == 0
    rec = {"t0": 100, "activity": {"as_is": [[102, "s2"], [103, "s3"]], "equalized": []}}
    assert W.readout(rec, u, 2) == 1                       # t0 ＋ 2 だけを読む


# ---- A1・A7：S ＝ 0 と S ＞ 0 の両方が、0016 と同じ手順でありうる（README §4） -------------------------

def _synthetic(seed: int, a: tuple[float, float, float]):
    """合成の runtime の全状態：合成専用の seed の Birth State、入力なし、手で置いた重み（組の和 ＝ w_max）、
    Unit の activity・adaptation は 0。"""
    log = W.ExperimentLog()
    app = W.build(PROTOCOL, seed, log)
    for receptor in app.receptors.values():
        receptor._pulses.clear()                          # 外からの入力なし（試しの A だけが入る）
    u = W.role_units(PROTOCOL, seed)
    state = app.connections.export_state()
    for (x, y), v in zip(((u["A"], u["B"]), (u["A"], u["C"]), (u["B"], u["C"])), a):
        state[W.W14.connection_id(x, y)]["weight"] = (W_MAX + v) / 2
        state[W.W14.connection_id(y, x)]["weight"] = (W_MAX - v) / 2
    app.connections.import_state(state)
    for unit in app.units.all():
        s = unit.export_state()
        s["activity"], s["adaptation"] = 0.0, 0.0
        unit.import_state(s)
    return app, log, u


def _run_probes(seed: int, a: tuple[float, float, float]):
    app, log, u = _synthetic(seed, a)
    records = []
    for t0 in range(1, W.probe_count(PROTOCOL) + 1):      # 0016 と同じ：毎 Pulse、τ_a の 1 区間、本体から独立に
        W.advance_to(app, t0 - 1)
        records.append(W.probe(PROTOCOL, app, log, seed, t0))
    assert all(W.check_probe(PROTOCOL, seed, r, W_MAX) == [] for r in records)
    return records, u


def test_s_can_be_zero_while_every_probe_changes_the_weights() -> None:
    """300 回すべてで W_probe ≠ 0（毎回 equalize が実際に 4 本の重みを変える）のに、300 回すべて E ＝ 0。"""
    records, u = _run_probes(9015, (0.008, -0.008, 0.0))
    assert all(W.w_probe(r, u) != 0 for r in records)
    assert all(r["fork"]["as_is"]["connections"] != r["fork"]["equalized"]["connections"] for r in records)
    assert sum(W.readout(r, u, 2) for r in records) == 0


def test_s_can_be_positive_through_the_same_procedure() -> None:
    records, u = _run_probes(9082, (0.008, -0.008, 0.0))
    assert all(W.w_probe(r, u) != 0 for r in records)
    assert sum(W.readout(r, u, 2) for r in records) > 0


# ---- 本番と同じ手順の動作確認の seed（操作の確認だけ） ---------------------------------------------------

def test_full_smoke_seed_passes_manipulation_from_raw(A, smoke_run) -> None:
    assert A.manipulation([smoke_run]) == []
    assert [p["t0"] for p in smoke_run["probes"]] == list(range(24001, 24301))
    assert all(p <= 12000 for p, _ in smoke_run["sensory"])


def test_probes_do_not_touch_the_main_individual() -> None:
    log = W.ExperimentLog()
    app = W.build(PROTOCOL, 8102, log)
    W.advance_to(app, 500)
    before, events = W.snapshot(app), len(log.events)
    W.probe(PROTOCOL, app, log, 8102, 501)
    assert app.lifecycle.pulse == 500 and W.snapshot(app) == before and len(log.events) == events


def test_manipulation_detects_raw_problems(A, smoke_run) -> None:
    bad = copy.deepcopy(smoke_run)
    bad["sensory"].append([12001, smoke_run["roles"]["receptors"]["A"]])
    assert any("経験の終わりより後" in p for p in A.manipulation([bad]))
    bad = copy.deepcopy(smoke_run)
    cid = next(iter(bad["connections_endpoint"]))
    bad["connections_endpoint"][cid]["weight"] += 1e-9
    assert any("再生" in p for p in A.manipulation([bad]))
    bad = copy.deepcopy(smoke_run)
    bad["clone"]["activity"].append([24300, "s1"])
    assert any("clone_identity" in p for p in A.manipulation([bad]))
    bad = copy.deepcopy(smoke_run)
    bad["probes"][5]["base_sensory"] = []
    assert any("感覚の出来事" in p for p in A.manipulation([bad]))
    bad = copy.deepcopy(smoke_run)
    ids = W.W14.four_ids(smoke_run["roles"]["units"])
    bad["probes"][7]["fork"]["equalized"]["connections"][ids["BA"]]["weight"] += 1e-4
    assert any("式どおり" in p for p in A.manipulation([bad]))


def test_smoke_report_hides_e_and_s(A, smoke_run) -> None:
    data = {"meta": {"smoke": True, "git_commit": "x", "protocol": PROTOCOL, "manifest": W.manifest_raw(PROTOCOL)},
            "runs": [smoke_run]}
    report = A.analyze(data)
    assert not ({"judgment", "per_seed", "records"} & set(report))


def test_invalid_data_does_not_compute_judgment_statistics(A) -> None:
    data = {"meta": {"smoke": False, "git_commit": "x", "protocol": {}, "manifest": {}}, "runs": []}
    report = A.analyze(data)
    assert not report["valid"] and report["judgment"] is None and report["per_seed"] is None
    assert report["records"] is None
