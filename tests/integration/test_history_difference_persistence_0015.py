"""実験 0015 の道具の契約テスト（README §4・§6・§7）。

判定の seed（6001〜6020）は使わない。動作確認の seed（7001〜7006）は、操作の確認だけに使い、D0・DT・P を計算しない。
A1 の構成的なテスト（README §4）は、どの範囲にも属さない合成専用の seed 9001 の Birth State の上に、
手で作った Unit の状態・重みを置いた合成の runtime の全状態から始める（自然な seed の結果は見ない）。
"""

import copy
import importlib.util
import random
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments" / "0015_history_difference_persistence"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))
SYNTHETIC_SEED = 9001


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W = _load("world_0015_test", EXP / "world.py")


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)


@pytest.fixture
def A():
    return _load("analyze_0015_test", EXP / "analyze.py")


@pytest.fixture(scope="module")
def smoke_run():
    """動作確認の seed 1 つを本番と同じ手順で走らせた生の記録（D0・DT・P は計算しない）。"""
    import os
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        return _load("run_0015_test", EXP / "run.py").run_seed(7001)
    finally:
        os.chdir(cwd)


def test_protocol_and_tools_are_aligned() -> None:
    _load("alignment_0015_test", EXP / "alignment.py").check(PROTOCOL)
    assert SYNTHETIC_SEED not in range(6001, 6021) and SYNTHETIC_SEED not in range(7001, 7007)


def test_timeline_is_derived_from_existing_values() -> None:
    assert W.experience_end(PROTOCOL) == 12000 and W.total_pulses(PROTOCOL) == 24000
    times = W.sample_times(PROTOCOL)
    assert times[0] == 0 and times[-1] == 24000 and 12000 in times and times[1] - times[0] == 60


def test_experience_is_the_0014_design_with_a_named_stream() -> None:
    o = W.stimuli(PROTOCOL, "ordered", 7001)
    assert {r: sum(1 for _, v in o if v == r) for r in "ABC"} == {"A": 200, "B": 200, "C": 200}
    assert o[-1] == (11971, "C")
    labels = [v for _, v in o]
    random.Random("0015-shuffle:7001").shuffle(labels)
    assert [v for _, v in W.stimuli(PROTOCOL, "shuffled", 7001)] == labels
    assert [t for t, _ in W.stimuli(PROTOCOL, "shuffled", 7001)] == [t for t, _ in o]


# ---- A1：符号が構造上決まっていないことの構成的な確認（README §4） -----------------------------------

W_MAX = W.plasticity(PROTOCOL).w_max
# 同じ D0（＞ 0）から、DT ＞ 0 になる組と DT ＜ 0 になる組。
# 重みは各相互の組の非対称 a（A–B, A–C, B–C）で与え（組の和 ＝ w_max）、ordered 側は a_AB だけ 0.002 大きい（D0 ＝ 0.001）。
# Unit の状態（activity・adaptation）は、実装が取りうる範囲（0 ≤ activity ＜ threshold、0 ≤ adaptation ≤ 0.1）の合成の値。
CASES = {
    "DT_positive": {
        "a": (-0.006, 0.006, -0.006),
        "shuffled_units": {"s1": (0.11478106158273976, 0.0495435087091941),
                           "s2": (0.20227097915493217, 0.0651592972722763),
                           "s3": (0.35492550801098094, 0.00938595867742349)},
        "ordered_units": {"s1": (0.01275636443490284, 0.08357651039198698),
                          "s2": (0.19474518055727402, 0.0762280082457942),
                          "s3": (0.0009477240079998117, 0.04453871940548015)},
    },
    "DT_negative": {
        "a": (0.006, -0.006, -0.006),
        "shuffled_units": {"s1": (0.4056423559251676, 0.0030589983033553537),
                           "s2": (0.011450637447057361, 0.05414124727934966),
                           "s3": (0.42261712325032974, 0.03812042376882124)},
        "ordered_units": {"s1": (0.09746972870877603, 0.042211657558271734),
                          "s2": (0.013068354408690575, 0.022169166627303505),
                          "s3": (0.19704941714275742, 0.04958122413818507)},
    },
}


def _synthetic(a_ab: float, a_ac: float, a_bc: float, unit_values: dict):
    """合成の runtime の全状態：seed 9001 の Birth State、入力なし、手で置いた重みと Unit の状態。"""
    log = W.ExperimentLog()
    app = W.build(PROTOCOL, "ordered", SYNTHETIC_SEED, log)
    for receptor in app.receptors.values():
        receptor._pulses.clear()                          # 外からの入力なし
    u = W.role_units(PROTOCOL, SYNTHETIC_SEED)
    state = app.connections.export_state()
    for (x, y), a in (((u["A"], u["B"]), a_ab), ((u["A"], u["C"]), a_ac), ((u["B"], u["C"]), a_bc)):
        state[W.connection_id(x, y)]["weight"] = (W_MAX + a) / 2
        state[W.connection_id(y, x)]["weight"] = (W_MAX - a) / 2
    app.connections.import_state(state)
    for unit in app.units.all():
        s = unit.export_state()
        s["activity"], s["adaptation"] = unit_values[unit.unit_id]
        unit.import_state(s)
    return app, u


def _valid(app) -> bool:
    w = W.weights(app.connections.export_state())
    units = ("s1", "s2", "s3")
    pair_sums = all(abs(w[W.connection_id(i, j)] + w[W.connection_id(j, i)] - W_MAX) < 1e-15
                    for i in units for j in units if i < j)
    bounds = all(0 <= v <= W_MAX for v in w.values())
    unit_ok = all(0 <= s["activity"] < s["dynamics"]["threshold"] and 0 <= s["adaptation"] <= 0.1
                  for s in (u.export_state() for u in app.units.all()))
    return pair_sums and bounds and unit_ok


@pytest.mark.parametrize("case", sorted(CASES))
def test_same_positive_d0_can_end_with_either_sign_through_the_real_runtime(case) -> None:
    c = CASES[case]
    a_ab, a_ac, a_bc = c["a"]
    s_app, u = _synthetic(a_ab, a_ac, a_bc, c["shuffled_units"])
    o_app, _ = _synthetic(a_ab + 0.002, a_ac, a_bc, c["ordered_units"])
    assert _valid(s_app) and _valid(o_app)
    d0 = (W.w_contrast(W.weights(o_app.connections.export_state()), u)
          - W.w_contrast(W.weights(s_app.connections.export_state()), u))
    assert d0 == pytest.approx(0.001)
    end = W.experience_end(PROTOCOL)                      # 無入力の区間と同じ長さ
    W.advance_to(s_app, end)
    W.advance_to(o_app, end)
    dt = (W.w_contrast(W.weights(o_app.connections.export_state()), u)
          - W.w_contrast(W.weights(s_app.connections.export_state()), u))
    assert (dt > 0) if case == "DT_positive" else (dt < 0)


# ---- 判定の量の扱い（合成の記録） ---------------------------------------------------------------------

def _fake_run(seed: int, w_ord: dict, w_shuf: dict) -> dict:
    """標本 12000・24000 の w(A→B)・w(A→C) だけを持つ合成の記録（A=s1, B=s2, C=s3）。"""
    def conns(w_ab, w_ac):
        base = {W.connection_id(i, j): {"weight": W_MAX / 2, "pre_trace": 0.0, "post_trace": 0.0}
                for i in ("s1", "s2", "s3") for j in ("s1", "s2", "s3") if i != j}
        base[W.connection_id("s1", "s2")]["weight"] = w_ab
        base[W.connection_id("s1", "s3")]["weight"] = w_ac
        return base
    return {"seed": seed, "roles": {"units": {"A": "s1", "B": "s2", "C": "s3"}},
            "conditions": {"ordered": {"samples": {str(t): conns(*w_ord[t]) for t in w_ord}},
                           "shuffled": {"samples": {str(t): conns(*w_shuf[t]) for t in w_shuf}}}}


def test_statistics_endpoint_sign_and_not_applicable(A) -> None:
    r = _fake_run(1, {12000: (0.007, 0.005), 24000: (0.004, 0.005)}, {12000: (0.005, 0.005), 24000: (0.006, 0.005)})
    s = A.statistics(r)                                   # D0 ＝ 0.002、DT ＝ −0.002
    assert s["applicable"] and s["P"] == pytest.approx(-0.002) and s["p"] is False
    r = _fake_run(2, {12000: (0.003, 0.005), 24000: (0.002, 0.005)}, {12000: (0.005, 0.005), 24000: (0.005, 0.005)})
    s = A.statistics(r)                                   # D0 ＜ 0、DT ＜ 0 → 同じ向き
    assert s["P"] == pytest.approx(0.003) and s["p"] is True
    r = _fake_run(3, {12000: (0.005, 0.005), 24000: (0.009, 0.005)}, {12000: (0.005, 0.005), 24000: (0.005, 0.005)})
    s = A.statistics(r)                                   # D0 ＝ 0 → N/A（0 に潰さない）
    assert not s["applicable"] and s["P"] is None and s["p"] is None


# ---- 本番と同じ手順の動作確認の seed（操作の確認だけ） ---------------------------------------------------

def test_full_smoke_seed_passes_manipulation_from_raw(A, smoke_run) -> None:
    assert A.manipulation([smoke_run]) == []
    for c in ("ordered", "shuffled"):
        assert all(p <= 12000 for p, _ in smoke_run["conditions"][c]["sensory"])
        assert list(smoke_run["conditions"][c]["samples"]) == [str(t) for t in W.sample_times(PROTOCOL)]


def test_run_condition_handles_a_divergence_after_the_first_sample() -> None:
    """札が最初に違う Pulse が 2 以上（d − 1 が最初の標本 0 より後）でも、時刻を戻らずに記録できる。"""
    seed = next(s for s in range(7001, 7007) if W.first_divergence(PROTOCOL, s) > 1)
    import os
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        R = _load("run_0015_test_divergence", EXP / "run.py")
    finally:
        os.chdir(cwd)
    d = W.first_divergence(PROTOCOL, seed)
    rec = R.run_condition(seed, "ordered", d)
    assert rec["before_divergence"] is not None and "0" in rec["samples"] and "24000" in rec["samples"]


def test_manipulation_detects_raw_problems(A, smoke_run) -> None:
    bad = copy.deepcopy(smoke_run)
    bad["conditions"]["ordered"]["sensory"].append([12001, smoke_run["roles"]["receptors"]["A"]])
    assert any("経験の終わりより後" in p for p in A.manipulation([bad]))
    bad = copy.deepcopy(smoke_run)
    cid = next(iter(bad["conditions"]["shuffled"]["samples"]["24000"]))
    bad["conditions"]["shuffled"]["samples"]["24000"][cid]["weight"] += 1e-9
    assert any("再生" in p for p in A.manipulation([bad]))
    bad = copy.deepcopy(smoke_run)
    bad["conditions"]["ordered"]["birth"]["s1"]["activity"] += 1e-9
    assert any("出生時" in p for p in A.manipulation([bad]))
    bad = copy.deepcopy(smoke_run)
    bad["conditions"]["ordered"]["sensory"].pop(0)
    assert any("ordered" in p for p in A.manipulation([bad]))


def test_smoke_report_hides_the_judgment_quantities(A, smoke_run) -> None:
    data = {"meta": {"smoke": True, "git_commit": "x", "protocol": PROTOCOL, "manifest": W.manifest_raw(PROTOCOL)},
            "runs": [smoke_run]}
    report = A.analyze(data)
    assert "judgment" not in report and "per_seed" not in report and "records" not in report


def test_invalid_data_does_not_compute_judgment_statistics(A) -> None:
    data = {"meta": {"smoke": False, "git_commit": "x", "protocol": {}, "manifest": {}}, "runs": []}
    report = A.analyze(data)
    assert not report["valid"] and report["judgment"] is None and report["per_seed"] is None
    assert report["records"] is None
