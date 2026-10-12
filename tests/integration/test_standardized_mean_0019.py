"""実験 0019 の道具の契約テスト（README §3・§4・§6・§7）。

判定の seed（12001〜12020）は使わない。動作確認の seed（12101〜12106）は操作の確認だけに使い、
smoke.hide の量（E・S・dm_fork・4 本それぞれの差・違った本数・recipient_contrast_displacement・donor_contrast_offset）を計算しない。
A1・A7 の合成の契約（README §4.1）は、合成専用の seed（9600〜9699 のうち 9600・9625）の Birth State の上に、
手で置いた重み・Unit の状態から、0019 と同じ手順（受け手・提供側の 2 つの無入力の本体から、毎 Pulse の独立な試し 300 回）で確かめる。
"""

import copy
import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments" / "0019_standardized_mean"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))
SYNTHETIC_S_ZERO = 9625
SYNTHETIC_S_POSITIVE = 9600
A_RECIPIENT = (0.006, 0.004, 0.0)      # (a_AB, a_AC, a_BC)：組の和 ＝ w_max のまま、w ＝ (w_max ± a)／2
A_DONOR = (-0.006, -0.004, 0.0)
A_DONOR_ACTIVE = (0.002, -0.002, 0.0)    # 境界のずらしの検出用（提供側の重みが試しの区間で動く）


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W = _load("world_0019_test", EXP / "world.py")
W_MAX = W.w_max(PROTOCOL)


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)


@pytest.fixture
def A():
    return _load("analyze_0019_test", EXP / "analyze.py")


@pytest.fixture(scope="module")
def smoke_run():
    """動作確認の seed 1 つを本番と同じ手順で走らせた生の記録（smoke.hide の量は計算しない）。"""
    import os
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        return _load("run_0019_test", EXP / "run.py").run_seed(12101)
    finally:
        os.chdir(cwd)


def test_protocol_and_tools_are_aligned() -> None:
    _load("alignment_0019_test", EXP / "alignment.py").check(PROTOCOL)
    syn = range(PROTOCOL["synthetic_seeds"]["first"], PROTOCOL["synthetic_seeds"]["last"] + 1)
    assert SYNTHETIC_S_ZERO in syn and SYNTHETIC_S_POSITIVE in syn


def test_timeline_is_derived_from_existing_values() -> None:
    assert (W.experience_end(PROTOCOL), W.endpoint(PROTOCOL), W.total_pulses(PROTOCOL)) == (12000, 24000, 24300)
    assert W.probe_times(PROTOCOL) == list(range(24001, 24301))


def test_shuffle_uses_the_0019_stream() -> None:
    o = W.stimuli(PROTOCOL, "ordered", 12101)
    s = W.stimuli(PROTOCOL, "shuffled", 12101)
    assert [t for t, _ in o] == [t for t, _ in s] and o != s
    assert W.W15.RNG_SHUFFLE == "0019-shuffle:{seed}"


def test_readout_formula_on_synthetic_records() -> None:
    u = {"A": "s1", "B": "s2", "C": "s3"}
    rec = {"t0": 100, "activity": {"ordered_m": [[101, "s1"], [102, "s2"]], "shuffled_m": [[101, "s1"], [102, "s3"]]}}
    assert W.readout(rec, u, 2) == 2
    rec = {"t0": 100, "activity": {"ordered_m": [[101, "s1"], [102, "s2"]], "shuffled_m": [[101, "s1"], [102, "s2"]]}}
    assert W.readout(rec, u, 2) == 0
    rec = {"t0": 100, "activity": {"ordered_m": [[102, "s2"], [103, "s3"]], "shuffled_m": []}}
    assert W.readout(rec, u, 2) == 1                       # t0 ＋ 2 だけを読む


# ---- 合成の runtime の全状態 ----------------------------------------------------------------------

def _synthetic(seed: int, a: tuple[float, float, float]):
    """合成の runtime の全状態：合成専用の seed の Birth State、入力なし、手で置いた重み（組の和 ＝ w_max）、
    Unit の activity・adaptation は 0。"""
    log = W.ExperimentLog()
    app = W.build(PROTOCOL, "ordered", seed, log)
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


def _series(seed: int, a_rec, a_don, deliver: bool = True):
    r, rl, u = _synthetic(seed, a_rec)
    d, dl, _ = _synthetic(seed, a_don)
    records = W.probe_series(PROTOCOL, r, rl, d, dl, seed, range(1, W.probe_count(PROTOCOL) + 1), deliver)
    return records, u


# ---- A1・A7：S ＝ 0 と S ＞ 0 の両方が、0019 と同じ手順でありうる（README §4.1） -------------------------

def test_s_can_be_zero_while_arms_differ_at_every_probe() -> None:
    """300 回すべてで m_o ≠ m_s（2 腕の 4 本が実際に違う）のに、300 回すべて E ＝ 0。"""
    records, u = _series(SYNTHETIC_S_ZERO, A_RECIPIENT, A_DONOR)
    assert len(records) == 300
    assert all(W.check_probe(PROTOCOL, SYNTHETIC_S_ZERO, r, W_MAX) == [] for r in records)
    assert all(W.fork_differences(r, u, W_MAX)["changed"] > 0 for r in records)
    assert sum(W.readout(r, u, 2) for r in records) == 0


def test_s_can_be_positive_through_the_same_procedure() -> None:
    records, u = _series(SYNTHETIC_S_POSITIVE, A_RECIPIENT, A_DONOR)
    assert all(W.check_probe(PROTOCOL, SYNTHETIC_S_POSITIVE, r, W_MAX) == [] for r in records)
    assert all(W.fork_differences(r, u, W_MAX)["changed"] > 0 for r in records)
    assert sum(W.readout(r, u, 2) for r in records) > 0


# ---- runtime の順序（README §3.3、B1〜B3） -------------------------------------------------------------

def test_zero_difference_gives_e_zero() -> None:
    """m_o ＝ m_s（提供側を受け手と同じ状態にする）なら、2 腕は t0 ＋ 2 まで同一（E ＝ 0）。S ＞ 0 になる合成の状態の上で確かめる。"""
    records, u = _series(SYNTHETIC_S_POSITIVE, A_RECIPIENT, A_RECIPIENT)
    assert all(W.check_probe(PROTOCOL, SYNTHETIC_S_POSITIVE, r, W_MAX) == [] for r in records)
    assert all(W.fork_differences(r, u, W_MAX)["changed"] == 0 for r in records)
    assert all(r["activity"]["ordered_m"] == r["activity"]["shuffled_m"] for r in records)
    assert sum(W.readout(r, u, 2) for r in records) == 0


def test_no_readout_difference_when_a_does_not_fire_at_t0_plus_1() -> None:
    """s_A が t0 ＋ 1 に発火しない試しでは E ＝ 0（2 腕で違いうるのは A→B・A→C を通る s_A の t0 ＋ 1 の伝達だけ）。"""
    records, u = _series(SYNTHETIC_S_POSITIVE, A_RECIPIENT, A_DONOR, deliver=False)
    silent = [r for r in records if not W.fired_at(r["activity"]["ordered_m"], u["A"], r["t0"] + 1)]
    assert silent
    assert all(W.readout(r, u, 2) == 0 for r in silent)
    assert all([x for x in r["activity"]["ordered_m"] if x[0] == r["t0"] + 1]
               == [x for x in r["activity"]["shuffled_m"] if x[0] == r["t0"] + 1] for r in records)


def test_boundary_matches_both_bodies_and_arms_agree_at_t0_plus_1() -> None:
    """受け手の試しの元の重み ＝ ordered の本体の t0 の終わり、提供側の 4 本 ＝ shuffled の本体の t0 の終わり。"""
    # この合成の状態では A_DONOR の提供側は 300 Pulse のあいだ重みが一度も変わらない（凍結）ので、1 Pulse ずらしても
    # 区別できない。境界の確認が空虚でないことを示すために、重みが動く提供側（A_DONOR_ACTIVE）を使う
    records, u = _series(SYNTHETIC_S_POSITIVE, A_RECIPIENT, A_DONOR_ACTIVE)
    ids = W.four_ids(u)
    for r in records:
        assert W.weights(r["base"]["connections"]) == r["bodies"]["ordered"]
        assert all(r["donor"][k] == r["bodies"]["shuffled"][ids[k]] for k in W.TARGETS)
    # 境界が 1 Pulse ずれると一致しないことも確かめる（確認が空虚でない）：提供側を t0 − 1 の終わりの値にした場合
    shifted = copy.deepcopy(records[1:])
    for prev, r in zip(records, shifted):
        r["bodies"]["shuffled"] = prev["bodies"]["shuffled"]
    assert any(prev["bodies"]["shuffled"] != r["bodies"]["shuffled"] for prev, r in zip(records, records[1:]))
    assert any(W.check_probe(PROTOCOL, SYNTHETIC_S_POSITIVE, r, W_MAX) for r in shifted)


def test_probes_do_not_touch_the_bodies() -> None:
    o_log, s_log = W.ExperimentLog(), W.ExperimentLog()
    o, s = W.build(PROTOCOL, "ordered", 12102, o_log), W.build(PROTOCOL, "shuffled", 12102, s_log)
    W.advance_to(o, 500)
    W.advance_to(s, 500)
    before = (W.snapshot(o), W.snapshot(s), len(o_log.events), len(s_log.events))
    W.probe(PROTOCOL, o, o_log, s, s_log, 12102, 501)
    assert (o.lifecycle.pulse, s.lifecycle.pulse) == (500, 500)
    assert (W.snapshot(o), W.snapshot(s), len(o_log.events), len(s_log.events)) == before


# ---- 本番と同じ手順の動作確認の seed（操作の確認だけ） ---------------------------------------------------

def test_full_smoke_seed_passes_manipulation_from_raw(A, smoke_run) -> None:
    assert A.manipulation([smoke_run]) == []
    assert [p["t0"] for p in smoke_run["probes"]] == list(range(24001, 24301))
    assert all(p <= 12000 for c in W.CONDITIONS for p, _ in smoke_run["conditions"][c]["sensory"])


def test_manipulation_detects_raw_problems(A, smoke_run) -> None:
    def problems(mutate) -> list[str]:
        bad = copy.deepcopy(smoke_run)
        mutate(bad)
        return A.manipulation([bad])

    a_rec = smoke_run["roles"]["receptors"]["A"]
    ids = W.four_ids(smoke_run["roles"]["units"])
    assert any("経験の終わりより後" in p for p in problems(
        lambda b: b["conditions"]["shuffled"]["sensory"].append([12001, a_rec])))
    assert any("再生" in p for p in problems(
        lambda b: b["conditions"]["shuffled"]["connections_endpoint"][ids["AB"]].__setitem__(
            "weight", b["conditions"]["shuffled"]["connections_endpoint"][ids["AB"]]["weight"] + 1e-9)))
    assert any("clone_identity" in p for p in problems(
        lambda b: b["conditions"]["ordered"]["clone"]["activity"].append([24300, "s1"])))
    assert any("前の発火・状態" in p for p in problems(
        lambda b: b["conditions"]["shuffled"]["activity"].insert(0, [0, "s1"])))
    assert any("提供側の試しの元" in p for p in problems(lambda b: b["probes"][5].__setitem__("donor_sensory", [])))
    assert any("式どおりでない" in p for p in problems(
        lambda b: b["probes"][7]["fork"]["shuffled_m"]["connections"][ids["BA"]].__setitem__(
            "weight", b["probes"][7]["fork"]["shuffled_m"]["connections"][ids["BA"]]["weight"] + 1e-4)))
    assert any("shuffled の本体" in p for p in problems(
        lambda b: b["probes"][9]["bodies"]["shuffled"].__setitem__(ids["AC"], 0.0)))
    assert any("ordered の本体" in p for p in problems(
        lambda b: b["probes"][9]["bodies"]["ordered"].__setitem__(ids["AC"], 0.0)))


def test_smoke_report_hides_sealed_quantities(A, smoke_run) -> None:
    data = {"meta": {"smoke": True, "git_commit": "x", "protocol": PROTOCOL, "manifest": W.manifest_raw(PROTOCOL)},
            "runs": [smoke_run]}
    report = A.analyze(data)
    assert not ({"judgment", "per_seed", "records"} & set(report))
    assert set(report) == {"experiment", "smoke", "git_commit", "seeds", "valid", "problems", "note", "smoke_passed"}


def test_invalid_data_does_not_compute_judgment_statistics(A) -> None:
    data = {"meta": {"smoke": False, "git_commit": "x", "protocol": {}, "manifest": {}}, "runs": []}
    report = A.analyze(data)
    assert not report["valid"] and report["judgment"] is None and report["per_seed"] is None
    assert report["records"] is None


def test_manipulation_detects_standardization_problems(A, smoke_run) -> None:
    def problems(mutate) -> list[str]:
        bad = copy.deepcopy(smoke_run)
        mutate(bad)
        return A.manipulation([bad])

    ids = W.four_ids(smoke_run["roles"]["units"])
    assert any("m がその履歴の m と違う" in p for p in problems(
        lambda b: b["probes"][8]["donor"].__setitem__("AB", b["probes"][8]["donor"]["AB"] + 1e-4)))
    assert any("痕跡が変わった" in p for p in problems(
        lambda b: b["probes"][3]["fork"]["ordered_m"]["connections"][ids["AB"]].__setitem__("pre_trace", 0.5)))
    assert any("Unit の状態が受け手の試しの元と違う" in p for p in problems(
        lambda b: b["probes"][4]["base"]["units"].clear()))


def test_standardized_arms_have_zero_contrast_and_history_mean() -> None:
    """2 腕の W は 0、m はそれぞれ受け手・提供側の試しの元の m、2 腕の違いは Δm だけ（README §3.1）。"""
    records, u = _series(SYNTHETIC_S_POSITIVE, (0.004, -0.002, 0.003), (-0.006, 0.001, -0.002))
    assert all(W.check_probe(PROTOCOL, SYNTHETIC_S_POSITIVE, r, W_MAX) == [] for r in records)
    for r in records:
        o = W.target_weights(r["fork"]["ordered_m"]["connections"], u)
        s = W.target_weights(r["fork"]["shuffled_m"]["connections"], u)
        assert abs(W.contrast(o)) < 1e-12 and abs(W.contrast(s)) < 1e-12
        assert abs(W.forward_mean(o) - W.forward_mean(W.target_weights(r["base"]["connections"], u))) < 1e-12
        assert abs(W.forward_mean(s) - W.forward_mean(r["donor"])) < 1e-12
        df = W.fork_differences(r, u, W_MAX)
        assert abs(df["per_weight"]["AB"] - df["dm"]) < 1e-12 and abs(df["per_weight"]["AC"] - df["dm"]) < 1e-12
        assert abs(df["per_weight"]["BA"] + df["dm"]) < 1e-12 and abs(df["per_weight"]["CA"] + df["dm"]) < 1e-12
        # recipient_contrast_displacement は旧値 − 新値（標準化で取り除いた量）＝ W_o
        assert df["recipient_contrast_displacement"] == W.contrast(W.target_weights(r["base"]["connections"], u))
    # この合成の受け手は W が 0 から離れているので、標準化は実際に重みを動かす
    assert all(W.fork_differences(r, u, W_MAX)["recipient_contrast_displacement"] != 0 for r in records)


def test_extreme_mean_stays_in_bounds() -> None:
    """m ＝ 0・w_max でも、W ＝ 0 なら切り詰めなしで 4 本が [0, w_max] に収まる（README §3.2）。"""
    for m in (0.0, W_MAX, W_MAX / 2):
        w = W.standardized_weights(0.0, m, W_MAX)
        assert all(0.0 <= v <= W_MAX for v in w.values())


def test_clopper_pearson_auxiliary_record(A) -> None:
    """補助記録の区間（判定に使わない。常設チェック D6）：既知の値と一致。"""
    lo, hi = A.clopper_pearson(16, 20)
    assert abs(lo - 0.5634) < 1e-4 and abs(hi - 0.9427) < 1e-4
    assert A.clopper_pearson(20, 20)[1] == 1.0 and A.clopper_pearson(0, 20)[0] == 0.0
