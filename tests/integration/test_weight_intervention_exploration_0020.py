"""探索 0020 の道具の契約テスト（README §3〜§6）。

探索の seed（13001〜13100）は使わない。合成・確認専用の範囲（13101〜13200）だけを使う。
合成の状態は 0017〜0019 の契約と同じ作り方（合成専用の seed の Birth State、入力なし、手で置いた重み、Unit の activity・adaptation は 0）。
ここで使った seed：13101（2 腕の発火の列が分かれる）・13102（A が両腕で沈黙し、列が同じ）・
13106（A が発火するのに、600 Pulse のあいだ列が同じ）・13199（実物の手順の通しの確認）。探索の経緯は PR に開示する。
"""

import copy
import importlib.util
import math
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments" / "0020_weight_intervention_exploration"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))
SPEC = None
DIVERGES, SILENT_IDENTICAL, ACTIVE_IDENTICAL, CHECK_SEED = 13101, 13102, 13106, 13199
A_CONTROL = (0.006, -0.004, 0.0)        # (a_AB, a_AC, a_BC)：組の和 ＝ w_max のまま w ＝ (w_max ± a)／2
A_INTERVENTION = (-0.006, 0.004, 0.0)
N = 600


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W = _load("world_0020_test", EXP / "world.py")
SPEC = W.plasticity(PROTOCOL)
W_MAX = SPEC.w_max


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)


@pytest.fixture
def A():
    return _load("analyze_0020_test", EXP / "analyze.py")


def _synthetic(seed: int, a):
    log = W.ExperimentLog()
    app = W.build(PROTOCOL, "ordered", seed, log)
    for receptor in app.receptors.values():
        receptor._pulses.clear()
    u = W.role_units(PROTOCOL, seed)
    state = app.connections.export_state()
    for (x, y), v in zip(((u["A"], u["B"]), (u["A"], u["C"]), (u["B"], u["C"])), a):
        state[W.connection_id(x, y)]["weight"] = (W_MAX + v) / 2
        state[W.connection_id(y, x)]["weight"] = (W_MAX - v) / 2
    app.connections.import_state(state)
    for unit in app.units.all():
        s = unit.export_state()
        s["activity"], s["adaptation"] = 0.0, 0.0
        unit.import_state(s)
    return app, log, u


def _pair(seed: int, a_control=A_CONTROL, a_intervention=A_INTERVENTION, n: int = N):
    """0020 と同じ手順を合成の状態で：control を複製して介入腕にし、4 本だけを別の状態の値に置き換え、並べて進める。"""
    c, cl, u = _synthetic(seed, a_control)
    i, il = W.clone(c, cl)
    donor, _, _ = _synthetic(seed, a_intervention)
    W.transplant(i, u, W.target_weights(donor.connections.export_state(), u))
    fork = {"control": W.snapshot(c), "intervention": W.snapshot(i)}
    res = W.run_arms({"control": (c, cl), "intervention": (i, il)}, 0, n, 60, u)
    ends = {"control": c.connections.export_state(), "intervention": i.connections.export_state()}
    return res, fork, ends, u


def _affine(res, fork, arm, cid, n=N):
    src, dst = W.unit_of(cid)
    sp = res["spikes"][arm]
    return W.affine(fork[arm]["connections"][cid], [p for p, x in sp if x == src], [p for p, x in sp if x == dst],
                    0, n, SPEC, 1.0)


def test_protocol_and_tools_are_aligned() -> None:
    _load("alignment_0020_test", EXP / "alignment.py").check(PROTOCOL)
    syn = range(PROTOCOL["synthetic_seeds"]["first"], PROTOCOL["synthetic_seeds"]["last"] + 1)
    assert all(s in syn for s in (DIVERGES, SILENT_IDENTICAL, ACTIVE_IDENTICAL, CHECK_SEED))


def test_affine_reconstruction_matches_runtime_in_both_arms() -> None:
    """各腕の終わりの重み ＝ 本体の更新を呼ぶ道筋 ＝ S·w₀ ＋ B（1e-12）。6 本すべて。"""
    res, fork, ends, _ = _pair(DIVERGES)
    for arm in W.ARMS:
        for cid, st in ends[arm].items():
            a = _affine(res, fork, arm, cid)
            w0 = fork[arm]["connections"][cid]["weight"]
            assert abs(a["w_end"] - st["weight"]) < 1e-12
            assert abs(a["S"] * w0 + a["B"] - st["weight"]) < 1e-12
            assert 0 < a["S"] <= 1 and (a["S"] == 1.0 or abs(math.log(a["S"]) - a["log_S"]) < 1e-9)


def test_first_pulse_after_intervention_is_identical() -> None:
    res, _, _, _ = _pair(DIVERGES)
    assert [x for x in res["spikes"]["control"] if x[0] == 1] == [x for x in res["spikes"]["intervention"] if x[0] == 1]


def test_divergence_is_found_and_its_firing_is_reconstructed() -> None:
    """列が分かれる例：最初の分岐の Pulse の発火の判定を、直前 2 Pulse の状態から再構成すると、両腕とも実際と一致。"""
    res, _, _, _ = _pair(DIVERGES)
    dv = res["divergence"]
    assert dv is not None and dv["pulse"] > 1 and dv["before"]["t-2"] is not None
    for arm in W.ARMS:
        rec = W.reconstruct_firing(dv["before"]["t-1"][arm]["units"], dv["before"]["t-2"][arm]["connections"],
                                   dv["spikes"]["t-1"][arm], 1.0)
        assert sorted(u for u, r in rec.items() if r["fires"]) == sorted(u for _, u in dv["spikes"]["t"][arm])


def test_firing_reconstruction_matches_runtime_at_every_pulse() -> None:
    """再構成の式そのものを、合成の活動のある状態で 1 Pulse ずつ、300 Pulse すべてで確かめる（分岐の時点だけに頼らない）。"""
    app, log, _ = _synthetic(DIVERGES, A_CONTROL)
    reader = W._SpikeReader(log)
    hist, last = [W.snapshot(app)], []
    checked = 0
    for t in range(1, 301):
        W.advance_to(app, t)
        now = reader.new()
        if len(hist) == 2:
            rec = W.reconstruct_firing(hist[-1]["units"], hist[0]["connections"], last, 1.0)
            assert sorted(u for u, r in rec.items() if r["fires"]) == sorted(u for _, u in now)
            checked += 1
        hist, last = (hist + [W.snapshot(app)])[-2:], now
    assert checked == 299 and log.activity()


@pytest.mark.parametrize("seed", [SILENT_IDENTICAL, ACTIVE_IDENTICAL])
def test_identical_trains_contract_per_weight_differences(seed) -> None:
    """列が同じなら（README §3）：1 本ずつの差は符号が保たれ、0 にならず、大きさは増えない。ΔS ＝ 0 なので M_I ＝ M_C ＝ 0。
    13102 は A が両腕で沈黙、13106 は A が発火するのに列が同じ（どちらも 600 Pulse）。"""
    res, fork, ends, u = _pair(seed)
    assert res["divergence"] is None
    a_spikes = sum(1 for _, x in res["spikes"]["control"] if x == u["A"])
    assert (a_spikes == 0) == (seed == SILENT_IDENTICAL)
    ids = W.four_ids(u)
    samples = res["samples"]
    times = sorted(samples["control"], key=int)
    for k in W.TARGETS:
        diffs = [samples["intervention"][t]["targets"][k] - samples["control"][t]["targets"][k] for t in times]
        assert all(d != 0 and (d > 0) == (diffs[0] > 0) for d in diffs)
        assert all(abs(b) <= abs(a) for a, b in zip(diffs, diffs[1:]))
        if k in ("AB", "AC"):
            ac, ai = _affine(res, fork, "control", ids[k]), _affine(res, fork, "intervention", ids[k])
            assert ac["S"] == ai["S"] and ac["B"] == ai["B"]


def test_zero_intervention_keeps_the_arms_identical() -> None:
    """介入の値が control と同じなら、2 腕は終わりまで同一。"""
    res, _, ends, _ = _pair(DIVERGES, A_CONTROL, A_CONTROL)
    assert res["divergence"] is None and res["spikes"]["control"] == res["spikes"]["intervention"]
    assert ends["control"] == ends["intervention"]


def test_min_margin_is_recorded_for_non_firing_pulses() -> None:
    res, _, _, u = _pair(SILENT_IDENTICAL)
    m, t = res["min_margin"]["control"][u["A"]]
    assert m > 0 and 1 <= t <= N                     # A は一度も発火しない（余裕は正のまま）


# ---- 実物の手順の通しの確認（合成・確認専用の範囲の seed。記録の量は見ない） ------------------------------

@pytest.fixture(scope="module")
def check_run():
    import os
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        return W.explore_seed(PROTOCOL, CHECK_SEED)
    finally:
        os.chdir(cwd)


def test_full_procedure_passes_checks_from_raw(A, check_run) -> None:
    assert A.check_run(check_run, 1e-12, 1e-12) == []


def test_checks_detect_raw_problems(A, check_run) -> None:
    def problems(mutate) -> list[str]:
        bad = copy.deepcopy(check_run)
        mutate(bad)
        return A.check_run(bad, 1e-12, 1e-12)

    u = check_run["roles"]["units"]
    ids = W.four_ids(u)
    assert any("経験の終わりより後" in p for p in problems(
        lambda b: b["conditions"]["shuffled"]["sensory"].append([12001, b["roles"]["receptors"]["A"]])))
    assert any("clone_identity" in p for p in problems(lambda b: b["twin"]["activity"].append([24000, "s1"])))
    assert any("shuffled の 12000 の値と違う" in p for p in problems(
        lambda b: b["fork"]["intervention"]["connections"][ids["AB"]].__setitem__("weight", 0.001)))
    assert any("痕跡が介入で変わった" in p for p in problems(
        lambda b: b["fork"]["intervention"]["connections"][ids["BA"]].__setitem__("pre_trace", 0.5)))
    assert any("自分の発火の列からの再構成と合わない" in p for p in problems(
        lambda b: b["arms"]["connections_24000"]["intervention"][ids["AC"]].__setitem__(
            "weight", b["arms"]["connections_24000"]["intervention"][ids["AC"]]["weight"] + 1e-9)))
    assert any("12000 の再生" in p for p in problems(
        lambda b: b["conditions"]["ordered"]["connections_12000"][ids["AB"]].__setitem__(
            "weight", b["conditions"]["ordered"]["connections_12000"][ids["AB"]]["weight"] + 1e-9)))


def test_check_report_hides_records(A, check_run) -> None:
    data = {"meta": {"git_commit": "x", "protocol": PROTOCOL, "manifest": W.manifest_raw(PROTOCOL)},
            "runs": [check_run]}
    report = A.analyze(data, check_only=True)
    assert report["valid"] and not ({"summary", "per_seed"} & set(report))


def test_record_structure_and_identities(A, check_run) -> None:
    """記録の計算が動き、恒等式（J ＝ M_I − M_C、M の 1 次式）が成り立つ（値の中身はここでは見ない）。"""
    rec = A.record_run(check_run)
    assert {"rho_birth", "A_silent", "divergence", "trains_identical", "affine", "dS", "dB", "M_I", "M_C", "J",
            "underflow_audit", "natural", "min_margin"} <= set(rec)
    for k in ("AB", "AC", "W"):
        assert abs(rec["J"][k] - (rec["M_I"][k] - rec["M_C"][k])) < 1e-15
    d0 = rec["delta_targets_12000"]
    for k in ("AB", "AC"):
        assert abs(rec["J"][k] - rec["dS"][k] * d0[k]) < 1e-15
