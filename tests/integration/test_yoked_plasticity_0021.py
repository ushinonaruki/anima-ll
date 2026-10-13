"""実験 0021 の道具の契約テスト（事前登録 v0.1 の README §2〜§7）。

本番の seed（14001〜14100）は使わない（実行もしない）。合成・確認専用の範囲（14101〜14200）だけを使う。
合成の状態は 0017〜0020 の契約と同じ作り方（合成専用の seed の Birth State、入力なし、手で置いた重み、
Unit の activity・adaptation は 0）。窓は 0〜600 Pulse。

使った合成の seed（PR に開示）：
- 例を選ぶための走査：14101〜14130 を、2 通りの合成の重みで 600 Pulse（t1・t2 の有無だけを見た）
- 14101（t1 なし）・14103（t1 あり・t2 なし）・14112（t1・t2 あり）：契約テストの合成の例
- 14199：実物の手順の通しの確認（操作の確認だけ。観測の量は表示しない）
"""

import copy
import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments" / "0021_yoked_plasticity"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))
NO_T1, T1_ONLY, T1_T2, CHECK_SEED = 14101, 14103, 14112, 14199
A_CONTROL = (0.006, -0.004, 0.0)        # (a_AB, a_AC, a_BC)：組の和 ＝ w_max のまま w ＝ (w_max ± a)／2
A_INTERVENTION = (-0.006, 0.004, 0.0)
N = 600


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W = _load("world_0021_test", EXP / "world.py")
G = _load("guard_0021_test", EXP / "guard.py")
SPEC = W.plasticity(PROTOCOL)
W_MAX = SPEC.w_max


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)


@pytest.fixture(scope="module")
def A():
    return _load("analyze_0021_test", EXP / "analyze.py")


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


def _five(seed: int, a_control=A_CONTROL, a_intervention=A_INTERVENTION, n: int = N):
    """0021 と同じ手順を合成の状態で：C を複製して I（4 本を移植）・Y（I の複製、yoked）・twin・Y0（yoked）を作り、並べて進める。"""
    C, Cl, u = _synthetic(seed, a_control)
    I, Il = W.clone(C, Cl)
    donor, _, _ = _synthetic(seed, a_intervention)
    W.transplant(I, u, W.target_weights(donor.connections.export_state(), u))
    Y, Yl = W.clone(I, Il)
    tw, twl = W.clone(C, Cl)
    Y0, Y0l = W.clone(C, Cl)
    arms = {"C": (C, Cl), "I": (I, Il), "Y": (Y, Yl), "twin": (tw, twl), "Y0": (Y0, Y0l)}
    fork = {k: W.snapshot(app) for k, (app, _) in arms.items()}
    yokes = {k: W.make_yoked(arms[k][0]) for k in W.YOKED}
    res = W.run_arms(arms, yokes, 0, n, 60)
    ends = {k: W.snapshot(app) for k, (app, _) in arms.items()}
    return {"seed": seed, "roles": {"units": u}, "arms": res, "fork": fork, "endpoints": ends}


@pytest.fixture(scope="module")
def cases():
    return {s: _five(s) for s in (NO_T1, T1_ONLY, T1_T2)}


def _arms_problems(A, run, n=N) -> dict:
    out = {k: [] for k in A.CHECK_NAMES}
    before = {c: v["weight"] for c, v in run["fork"]["C"]["connections"].items()}   # 合成：0 より前の伝達はない
    A.check_arms(run, out, 0, n, before)
    return {k: v for k, v in out.items() if v}


def test_protocol_and_tools_are_aligned() -> None:
    _load("alignment_0021_test", EXP / "alignment.py").check(PROTOCOL)
    syn = range(PROTOCOL["synthetic_seeds"]["first"], PROTOCOL["synthetic_seeds"]["last"] + 1)
    assert all(s in syn for s in (NO_T1, T1_ONLY, T1_T2, CHECK_SEED))


def test_examples_cover_the_three_structural_categories(A, cases) -> None:
    assert A.category(A.record_run(cases[NO_T1], 0, N)) == "a_no_t1"
    assert A.category(A.record_run(cases[T1_ONLY], 0, N)) == "b_t1_no_t2"
    assert A.category(A.record_run(cases[T1_T2], 0, N)) == "c_t1_t2"


@pytest.mark.parametrize("seed", [NO_T1, T1_ONLY, T1_T2])
def test_all_arm_checks_pass_on_synthetic_runs(A, cases, seed) -> None:
    assert _arms_problems(A, cases[seed]) == {}


# ---- yoke（README §2）---------------------------------------------------------------------------------

def test_yoke_passes_control_firing_only_to_plasticity(A, cases) -> None:
    """Y の可塑性は C の発火の列で進み（出来事と痕跡）、Y の Unit の判定・伝達は Y 自身の重みで進む。"""
    run = cases[T1_T2]
    sp, ends = run["arms"]["spikes"], run["endpoints"]
    assert sp["Y"] != sp["C"]                                      # Y の活動は自分の重み（移植した差）で進む
    by_c = A.replay_arm(run, "Y", (), 0, N)                         # 可塑性の列は C
    assert all(by_c[c]["end"] == ends["Y"]["connections"][c] for c in by_c)   # ビット単位で一致
    own = W.fired_by_pulse(sp["Y"])
    by_own = {c: W.replay(st, c, own, 0, N, SPEC, 1.0) for c, st in run["fork"]["Y"]["connections"].items()}
    assert any(by_own[c]["end"]["weight"] != ends["Y"]["connections"][c]["weight"] for c in by_own)
    for t in run["arms"]["samples"]["C"]:                           # 痕跡は C と同じ（全 6 接続）
        for c, v in run["arms"]["samples"]["C"][t]["connections"].items():
            y = run["arms"]["samples"]["Y"][t]["connections"][c]
            assert (y["pre_trace"], y["post_trace"]) == (v["pre_trace"], v["post_trace"])


@pytest.mark.parametrize("seed", [NO_T1, T1_ONLY, T1_T2])
def test_twin_and_Y0_equal_C_exactly(cases, seed) -> None:
    run = cases[seed]
    for arm in ("twin", "Y0"):
        assert run["arms"]["spikes"][arm] == run["arms"]["spikes"]["C"]
        assert run["arms"]["samples"][arm] == run["arms"]["samples"]["C"]
        assert run["endpoints"][arm] == run["endpoints"]["C"]


def test_yoke_contract_errors() -> None:
    """渡し忘れ・Pulse 番号の違い・二重の渡しは YokeError（黙って自分の発火で更新しない）。"""
    app, log, _ = _synthetic(T1_T2, A_CONTROL)
    y = W.make_yoked(app)
    assert app.pulse_runtime._connections is y and app.connections is y.inner      # 本物は app.connections のまま
    with pytest.raises(W.YokeError, match="渡されていない"):
        W.advance_to(app, 1)
    app2, _, _ = _synthetic(T1_T2, A_CONTROL)
    y2 = W.make_yoked(app2)
    y2.provide(2, set())
    with pytest.raises(W.YokeError, match="Pulse"):
        W.advance_to(app2, 1)
    app3, _, _ = _synthetic(T1_T2, A_CONTROL)
    y3 = W.make_yoked(app3)
    y3.provide(1, set())
    with pytest.raises(W.YokeError, match="まだ使われていない"):
        y3.provide(1, set())


def test_runtime_core_is_not_yoked_for_C_I_twin() -> None:
    run_apps = {}
    C, Cl, u = _synthetic(T1_T2, A_CONTROL)
    I, _ = W.clone(C, Cl)
    Y, _ = W.clone(I, Cl)
    W.make_yoked(Y)
    run_apps.update(C=C, I=I, Y=Y)
    assert type(C.pulse_runtime._connections).__name__ == type(I.pulse_runtime._connections).__name__ == "ConnectionStore"
    assert isinstance(Y.pulse_runtime._connections, W.YokedConnections)


# ---- t1・t2 と設計から決まる性質（メモ §5.4、README §3.2）-------------------------------------------------

def test_I_equals_Y_until_t1_and_t2_bounds(A, cases) -> None:
    run = cases[T1_T2]
    sp = run["arms"]["spikes"]
    (t1, u1), (t2, _) = A.first_difference(sp["C"], sp["I"]), A.first_difference(sp["I"], sp["Y"])
    assert A.first_difference(sp["C"], sp["Y"]) == (t1, u1)
    assert [x for x in sp["I"] if x[0] <= t1] == [x for x in sp["Y"] if x[0] <= t1]
    assert t2 >= t1 + 2
    ri, ry = A.replay_arm(run, "I", range(0, t2), 0, N), A.replay_arm(run, "Y", range(0, t2), 0, N)
    for m in range(0, t2):
        same = all(ri[c]["at"][m] == ry[c]["at"][m] for c in ri)
        assert same == (m <= t1 - 1), m                              # 重みが分かれるのは t1 の終わりから
    run_b = cases[T1_ONLY]
    assert A.first_difference(run_b["arms"]["spikes"]["I"], run_b["arms"]["spikes"]["Y"]) is None
    run_a = cases[NO_T1]
    assert run_a["arms"]["spikes"]["I"] == run_a["arms"]["spikes"]["Y"] == run_a["arms"]["spikes"]["C"]
    assert run_a["endpoints"]["I"]["connections"] == run_a["endpoints"]["Y"]["connections"]


def test_t2_contributions_satisfy_the_decomposition_identity(A, cases) -> None:
    """Σ_i K_ij(t2) ＝ ã^I − ã^Y（README §3.2）。和の下限は t1 ＋ 2、t1 以前の重みの差は 0。"""
    run = cases[T1_T2]
    sp = run["arms"]["spikes"]
    fd1, fd2 = A.first_difference(sp["C"], sp["I"]), A.first_difference(sp["I"], sp["Y"])
    k = A.t2_contributions(run, fd1, fd2, 0, N)
    assert set(k) == set(fd2[1])
    for j, c in k.items():
        assert abs(c["sum"] - c["activity_difference"]) < 1e-12
        fired_in_I = j in A.spikes_at(sp["I"], fd2[0])
        assert (c["activity_difference"] > 0) == fired_in_I            # 閾値が同じなので、発火した腕の方が大きい
    # 下限：t1 + 2 より前に入る差があると仮定しても、和に入らない（k ≥ t1 + 2）
    fake = lambda m: {cid: 1.0 for cid in run["fork"]["I"]["connections"]}
    j = fd2[1][0]
    lo = A.contributions(j, fd2[0], fd1[0] + 2, sp["I"], fake, 0.5, 0)
    hi = A.contributions(j, fd2[0], 0, sp["I"], fake, 0.5, 0)
    assert sum(lo.values()) <= sum(hi.values())


def test_contributions_respect_reset_and_delay(A) -> None:
    """r_j のリセットより前の項は入らない。Δw(k − 2) は送り手が k − 1 に発火したときだけ k に入る。"""
    cid = "s1.main->s2"
    spikes = [[3, "s1"], [5, "s2"], [7, "s1"]]
    diff = lambda m: {cid: 0.001 * m}
    k = A.contributions("s2", 9, 0, spikes, diff, 0.5, 0)
    # s2 は 5 に発火（r ＝ 5）→ k ＝ 6〜9。s1 の発火 7 → k ＝ 8 の項：0.5^(9 − 8)·Δw(6)
    assert k == {"s1": 0.5 * 0.001 * 6}


# ---- 欠測 null と観測値 0（protocol の observations.missing_values）------------------------------------------

def test_missing_values_are_null_and_real_zeros_are_kept(A, cases) -> None:
    a = A.record_run(cases[NO_T1], 0, N)
    for key in ("t1", "U1", "remaining_after_t1", "t2_detectable_pulses", "t1_contributions",
                "t2", "U2", "t2_minus_t1", "spike_counts_per_unit_from_t2", "t2_contributions"):
        assert a[key] is None, key
    assert a["differing_pulses"] == {"I_Y": 0, "C_I": 0, "C_Y": 0}               # 実際の 0（null ではない）
    assert all(isinstance(v, int) for arm in a["spike_counts_per_unit"].values() for v in arm.values())
    b = A.record_run(cases[T1_ONLY], 0, N)
    for key in ("t2", "U2", "t2_minus_t1", "spike_counts_per_unit_from_t2", "t2_contributions"):
        assert b[key] is None, key
    assert b["remaining_after_t1"] == N - b["t1"]
    assert b["t2_detectable_pulses"] == max(0, N - b["t1"] - 1) > 0              # t2 がなくても 0 にしない
    assert b["differing_pulses"]["I_Y"] == 0 and b["t1_contributions"] is not None
    c = A.record_run(cases[T1_T2], 0, N)
    assert c["t2_minus_t1"] == c["t2"] - c["t1"] and c["spike_counts_per_unit_from_t2"] is not None
    assert c["differing_pulses"]["I_Y"] > 0


def test_distribution_excludes_nulls_and_reports_their_count(A) -> None:
    d = A._describe([None, 3, None, 5, 7])
    assert d == {"n": 3, "null": 2, "median": 5, "min": 3, "max": 7}
    assert A._describe([None, None]) == {"n": 0, "null": 2, "median": None, "min": None, "max": None}


def test_relations_do_not_count_zero_as_agreement(A) -> None:
    assert A.relation(0.0, 0.0, "opposite") == "both_zero"
    assert A.relation(0.0, 1e-9, "opposite") == A.relation(-1e-9, 0.0, "reversed") == "one_zero"
    assert A.relation(2.0, 1e-9, "opposite") == "same" and A.relation(-2.0, 1e-9, "reversed") == "reversed"


def test_record_keys_match_the_preregistered_observations(A, cases) -> None:
    rec = A.record_run(cases[T1_T2], 0, N)
    obs = PROTOCOL["observations"]
    primary = {k if isinstance(k, str) else next(iter(k)) for k in obs["primary"]} - {"full_trains"}   # 全発火の列は生の記録
    secondary = {"t2_contributions", "t1_contributions", "P_F_D", "W_contrast"}
    assert set(rec) == primary | secondary
    for name, v in rec["P_F_D"].items():
        assert abs(v["D"] - (v["P"] + v["F"])) < 1e-15
    assert rec["P_F_D"]["BC"]["P"] == rec["P_F_D"]["CB"]["P"] == 0.0              # 全 6 接続 yoke：移植していない組の P は 0


# ---- 改ざん・不整合の検出（生の記録からの再検証）-------------------------------------------------------------

def _mutated(A, run, mutate) -> dict:
    bad = copy.deepcopy(run)
    mutate(bad)
    return _arms_problems(A, bad)


def test_arm_checks_detect_tampering(A, cases) -> None:
    run = cases[T1_T2]
    u = run["roles"]["units"]
    ids = W.four_ids(u)
    bc = W.connection_id(u["B"], u["C"])
    t2 = run["arms"]["t2"]["pulse"]
    t_sample = "120"
    cases_ = [
        (lambda b: b["arms"]["spikes"]["Y0"].append([N, u["A"]]), "Y0_equals_C"),
        (lambda b: b["endpoints"]["twin"]["connections"][bc].__setitem__("pre_trace", 9.0), "twin_equals_C"),
        (lambda b: b["arms"]["samples"]["Y"][t_sample]["connections"][bc].__setitem__("pre_trace", 9.0), "Y_traces_equal_C_traces"),
        (lambda b: b["arms"]["samples"]["Y"][t_sample]["connections"][bc].__setitem__(
            "weight", b["arms"]["samples"]["Y"][t_sample]["connections"][bc]["weight"] + 1e-9), "P_zero_on_untransplanted_pairs"),
        (lambda b: b["arms"]["samples"]["Y"][t_sample]["connections"][ids["AB"]].__setitem__(
            "weight", b["arms"]["samples"]["Y"][t_sample]["connections"][ids["AB"]]["weight"] + 1e-9), "P_identity"),
        (lambda b: b["endpoints"]["I"]["connections"][ids["AC"]].__setitem__(
            "weight", b["endpoints"]["I"]["connections"][ids["AC"]]["weight"] + 1e-9), "affine_reconstruction_T"),
        (lambda b: b["arms"]["t2"].__setitem__("pulse", t2 + 1), "revalidate_from_raw"),
        (lambda b: b["arms"]["t2"].__setitem__("units", ["s9"]), "revalidate_from_raw"),
        (lambda b: b["arms"]["t2"]["spikes"]["t"]["I"].append([t2, "s9"]), "revalidate_from_raw"),
        (lambda b: b["arms"]["t2"]["before"]["t-2"]["Y"]["connections"][bc].__setitem__("weight", 0.004), "revalidate_from_raw"),
        (lambda b: b["arms"]["t2"]["before"]["t-1"]["I"]["units"][u["A"]].__setitem__(
            "fire_count", b["arms"]["t2"]["before"]["t-1"]["I"]["units"][u["A"]]["fire_count"] + 1), "revalidate_from_raw"),
        (lambda b: b["arms"].__setitem__("t1", None), "revalidate_from_raw"),
        (lambda b: b["arms"]["t2"]["before"]["t-1"]["Y"]["units"][u["B"]].__setitem__(
            "activity", b["arms"]["t2"]["before"]["t-1"]["Y"]["units"][u["B"]]["activity"] + 1e-9), "divergence_activity_reconstruction"),
        (lambda b: b["arms"]["sensory"]["Y"].append([5, "receptor.x1"]), "input_free_after_experience"),
        (lambda b: b["arms"]["spikes"]["I"].insert(0, [1, u["C"]]), "first_pulse_identical"),
    ]
    for mutate, name in cases_:
        assert name in _mutated(A, run, mutate), name


def test_fabricated_divergence_is_detected(A, cases) -> None:
    run = cases[NO_T1]
    assert "revalidate_from_raw" in _mutated(A, run, lambda b: b["arms"].__setitem__(
        "t2", {"pulse": 5, "units": ["s1"], "before": {}, "spikes": {}}))
    # I と Y の発火を t1 より前で変えると、I ＝ Y の確認と t1′ ＝ t1 の確認が落ちる
    run = cases[T1_T2]
    t1 = run["arms"]["t1"]["pulse"]
    got = _mutated(A, run, lambda b: b["arms"]["spikes"]["Y"].insert(0, [t1 - 1, "s9"]))
    assert "I_equals_Y_until_t1" in got


def test_t2_bound_check_detects_violation(A, cases) -> None:
    """t2 ≥ t1 ＋ 2 の確認そのもの：I と Y の列を t1 ＋ 1 で違えると検出する。"""
    run = cases[T1_T2]
    t1 = run["arms"]["t1"]["pulse"]
    got = _mutated(A, run, lambda b: b["arms"]["spikes"]["Y"].append([t1 + 1, "s9"])
                   or b["arms"]["spikes"]["Y"].sort())
    assert "t2_at_least_t1_plus_2" in got


def test_spike_trains_must_be_well_formed(A, cases) -> None:
    run = cases[NO_T1]
    for mutate in (lambda b: b["arms"]["spikes"]["C"].append([N + 1, "s1"]),
                   lambda b: b["arms"]["spikes"]["C"].extend([[N, "s2"], [N, "s2"]])):
        assert "revalidate_from_raw" in _mutated(A, run, mutate)


# ---- 実物の手順の通しの確認（合成・確認専用の範囲の seed。観測の量は見ない）---------------------------------------

@pytest.fixture(scope="module")
def check_run():
    import os
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        return W.measure_seed(PROTOCOL, CHECK_SEED)
    finally:
        os.chdir(cwd)


def test_full_procedure_passes_checks_from_raw(A, check_run) -> None:
    out = A.check_run(check_run)
    assert {k: v for k, v in out.items() if v} == {}


def test_condition_checks_detect_raw_problems(A, check_run) -> None:
    def failed(mutate) -> set:
        bad = copy.deepcopy(check_run)
        mutate(bad)
        return {k for k, v in A.check_run(bad).items() if v}

    u = check_run["roles"]["units"]
    ids = W.four_ids(u)
    assert "input_free_after_experience" in failed(
        lambda b: b["conditions"]["shuffled"]["sensory"].append([12001, b["roles"]["receptors"]["A"]]))
    assert "transplant" in failed(lambda b: b["fork"]["I"]["connections"][ids["AB"]].__setitem__("weight", 0.001))
    assert "transplant" in failed(lambda b: b["fork"]["Y"]["connections"][ids["BA"]].__setitem__("pre_trace", 0.5))
    assert "replay_history_12000" in failed(lambda b: b["conditions"]["ordered"]["connections_12000"][ids["AB"]].__setitem__(
        "weight", b["conditions"]["ordered"]["connections_12000"][ids["AB"]]["weight"] + 1e-9))
    assert "stimulus_counts" in failed(lambda b: b["conditions"]["ordered"]["sensory"].pop())


FAKE_COMMIT = "0" * 40


def _check_data(check_run, mode="check", commit=FAKE_COMMIT, runs=None):
    runs = [check_run] if runs is None else runs
    seeds = [r["seed"] for r in runs]
    ek = {"experiment": PROTOCOL["experiment"], "kind": PROTOCOL["kind"]}
    data = {"meta": ek | {"mode": mode, "git_commit": commit, "protocol": PROTOCOL,
                          "manifest": W.manifest_raw(PROTOCOL), "seeds": seeds}, "runs": runs}
    proto_sha = G.sha256_file(EXP / "protocol.yaml")
    records = {"start": ek | {"mode": mode, "git_commit": commit, "seeds": seeds, "protocol_sha256": proto_sha},
               "finish": ek | {"status": "completed", "mode": mode, "git_commit_start": commit,
                               "git_commit_end": commit, "seeds": seeds, "runs_sha256": "f" * 64},
               "runs_sha256": "f" * 64}
    return data, records


def test_check_report_hides_observations(A, check_run) -> None:
    data, records = _check_data(check_run)
    report = A.analyze(data, "check", records)
    assert report["valid"], report["problems"]
    assert not ({"summary", "per_seed"} & set(report))
    assert report["individuals"] == {str(CHECK_SEED): {"valid": True, "failed_checks": {}}}


def test_invalid_individuals_are_reported_not_dropped(A, check_run) -> None:
    bad = copy.deepcopy(check_run)
    bad["arms"]["spikes"]["Y0"].append([24000, "s9"])
    data, records = _check_data(check_run, runs=[bad])
    report = A.analyze(data, "check", records)
    assert not report["valid"]
    ind = report["individuals"][str(CHECK_SEED)]
    assert not ind["valid"] and "Y0_equals_C" in ind["failed_checks"]


def test_completeness_rejects_bad_data(A, check_run) -> None:
    def invalid(data, records, mode="check", needle=None):
        r = A.analyze(data, mode, records)
        assert not r["valid"]
        if needle:
            assert any(needle in p for p in r["problems"]), r["problems"]

    data, rec = _check_data(check_run, runs=[])
    invalid(data, rec, needle="個体が 1 つもない")
    data, rec = _check_data(check_run, runs=[check_run, check_run])
    invalid(data, rec, needle="seed が重複")
    data, rec = _check_data(check_run)
    data["meta"]["seeds"] = [14198]
    invalid(data, rec, needle="meta の seed の列")
    data, rec = _check_data(check_run, mode="formal")
    invalid(data, rec, mode="check", needle="データの mode")
    data, rec = _check_data(check_run)
    invalid(data, rec, mode="formal", needle="データの mode")
    invalid(data, rec, mode="formal", needle="全件ではない")
    data, rec = _check_data(check_run, commit="unknown")
    invalid(data, rec, needle="40 桁の commit")
    data, rec = _check_data(check_run)
    data["meta"]["experiment"] = "0020"                               # 別の実験のデータを 0021 として解析しない
    invalid(data, rec, needle="experiment・kind")
    bad = copy.deepcopy(check_run)
    bad["seed"] = 13101                                               # 0020 の範囲の seed
    data, rec = _check_data(check_run, runs=[bad])
    invalid(data, rec, needle="範囲の外の seed")


def test_run_records_are_verified(A, check_run) -> None:
    data, rec = _check_data(check_run)
    for mutate, needle in [
        (lambda r: r.__setitem__("start", None), "開始の記録"),
        (lambda r: r.__setitem__("finish", None), "終了の記録"),
        (lambda r: r["finish"].__setitem__("status", "failed"), "completed ではない"),
        (lambda r: r["finish"].__setitem__("git_commit_end", "1" * 40), "commit"),
        (lambda r: r.__setitem__("runs_sha256", "e" * 64), "sha256"),
        (lambda r: r["start"].__setitem__("protocol_sha256", "e" * 64), "protocol.yaml"),
        (lambda r: r["start"].__setitem__("mode", "formal"), "mode"),
        (lambda r: r["start"].__setitem__("experiment", "0020"), "experiment・kind"),
        (lambda r: r["finish"].__setitem__("kind", "exploration"), "experiment・kind"),
    ]:
        r = copy.deepcopy(rec)
        mutate(r)
        report = A.analyze(data, "check", r)
        assert not report["valid"] and any(needle in p for p in report["problems"]), (needle, report["problems"])


# ---- 0020 から完全に分離（README §7.1）----------------------------------------------------------------------

FORBIDDEN = [r'"0020"', r"'0020'", r"experiments/0020", r"0020_weight_intervention", r"0020-shuffle"]


def test_tools_hold_no_0020_constants() -> None:
    """0021 の道具のコードに、0020 の experiment ID・出力先・protocol のパス・乱数の流れの名前・seed の範囲の定数がない。
    （alignment.py の使用済みの seed の一覧 SEEN は、重ならないことを確かめるための記録なので除く）"""
    for name in ("world.py", "run.py", "analyze.py", "alignment.py", "guard.py"):
        src = (EXP / name).read_text(encoding="utf-8")
        if name == "alignment.py":
            src = re.sub(r"SEEN = \(.*?\)\)\)\n", "", src, flags=re.S)
        for pat in FORBIDDEN:
            assert not re.search(pat, src), (name, pat)
        assert not re.search(r"\b13[0-2]\d\d\b", src), (name, "0020 の seed の範囲の数")


def test_tools_read_identity_from_this_protocol() -> None:
    R = _load("run_0021_identity", EXP / "run.py")
    A_ = _load("analyze_0021_identity", EXP / "analyze.py")
    ex = PROTOCOL["execution"]
    assert R.EXPERIMENT == A_.EXPERIMENT == W.EXPERIMENT == PROTOCOL["experiment"] == ex["experiment_id"]
    assert str(R.OUT_DIR) == str(A_.DEFAULT_DIR) == ex["output_dir"]
    assert str(R.PROTOCOL_PATH) == str(A_.PROTOCOL_PATH) == str(W.PROTOCOL_PATH) == ex["protocol_path"]
    assert W.RNG_SHUFFLE == W.W15.RNG_SHUFFLE == PROTOCOL["stimulus"]["rng_shuffle"]
    assert list(R.allowed_seeds("formal")) == list(range(PROTOCOL["seeds"]["first"], PROTOCOL["seeds"]["last"] + 1))
    assert list(R.allowed_seeds("check")) == list(range(14101, 14201))


# ---- 一度限りの実行の保護（README §7.1）。使い捨ての git リポジトリで。seed の計算は dummy で、本番の seed は使わない ---------

def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / EXP.relative_to(ROOT)).mkdir(parents=True)
    (r / EXP.relative_to(ROOT) / "protocol.yaml").write_bytes((EXP / "protocol.yaml").read_bytes())
    (r / ".gitignore").write_text("/out/\n", encoding="utf-8")
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@example.invalid")
    _git(r, "config", "user.name", "t")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "init")
    return r


@pytest.fixture
def R():
    return _load("run_0021_test", EXP / "run.py")


def _serial(fn, seeds):
    return (fn(s) for s in seeds)


def test_guard_requires_a_clean_real_commit(repo, monkeypatch) -> None:
    head = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setenv("ANIMA_GIT_COMMIT", "f" * 40)
    assert G.verify_clean_commit(repo) == head == G.verify_clean_commit(repo, head)
    with pytest.raises(G.GuardError, match="指定した commit"):
        G.verify_clean_commit(repo, "1" * 40)
    (repo / "untracked.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(G.GuardError, match="作業ツリー"):
        G.verify_clean_commit(repo, head)


def test_execute_runs_once_and_saves_atomically(repo, R) -> None:
    out = repo / "out"
    head = _git(repo, "rev-parse", "HEAD")
    calls = []
    runner = lambda s: calls.append(s) or {"seed": s}
    rec = R.execute("check", [14101, 14102], out, repo, head, runner=runner, mapper=_serial)
    assert rec["status"] == "completed" and rec["experiment"] == PROTOCOL["experiment"] and rec["kind"] == PROTOCOL["kind"]
    assert calls == [14101, 14102]
    assert sorted(p.name for p in out.iterdir()) == [G.FINISH, G.START, G.RUNS]
    assert G.sha256_file(out / G.RUNS) == rec["runs_sha256"]
    start = json.loads((out / G.START).read_text(encoding="utf-8"))
    assert start["experiment"] == PROTOCOL["experiment"] and start["protocol_sha256"] == G.sha256_file(EXP / "protocol.yaml")
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    with pytest.raises(R.G.GuardError):
        R.execute("check", [14101, 14102], out, repo, head, runner=runner, mapper=_serial)
    assert calls == [14101, 14102] and {p.name: p.read_bytes() for p in out.iterdir()} == before


def test_execute_refuses_before_touching_seeds(repo, R) -> None:
    head = _git(repo, "rev-parse", "HEAD")
    calls = []
    runner = lambda s: calls.append(s) or {"seed": s}
    with pytest.raises(R.G.GuardError, match="指定した commit"):
        R.execute("check", [14101], repo.parent / "out1", repo, "1" * 40, runner=runner, mapper=_serial)
    (repo.parent / "out3").mkdir()
    (repo.parent / "out3" / G.START).write_text("{}", encoding="utf-8")
    with pytest.raises(R.G.GuardError, match="既にある"):
        R.execute("check", [14101], repo.parent / "out3", repo, head, runner=runner, mapper=_serial)
    with pytest.raises(R.G.GuardError, match="範囲の外"):
        R.execute("check", [13101], repo.parent / "out4", repo, head, runner=runner, mapper=_serial)   # 0020 の範囲
    with pytest.raises(R.G.GuardError, match="範囲の外"):
        R.execute("formal", [14101], repo.parent / "out5", repo, head, runner=runner, mapper=_serial)  # 本番に合成の seed
    with pytest.raises(R.G.GuardError):
        R.execute("check", [], repo.parent / "out6", repo, head, runner=runner, mapper=_serial)
    with pytest.raises(R.G.GuardError):
        R.execute("check", [14101, 14101], repo.parent / "out7", repo, head, runner=runner, mapper=_serial)
    assert calls == []
    assert not (repo.parent / "out1").exists() and not (repo.parent / "out4").exists() and not (repo.parent / "out5").exists()


def test_execute_records_failure_and_does_not_save_results(repo, R) -> None:
    head = _git(repo, "rev-parse", "HEAD")

    def runner(s):
        if s == 14102:
            raise RuntimeError("boom")
        return {"seed": s}

    out = repo / "out"
    with pytest.raises(RuntimeError, match="boom"):
        R.execute("check", [14101, 14102], out, repo, head, runner=runner, mapper=_serial)
    fin = json.loads((out / G.FINISH).read_text(encoding="utf-8"))
    assert fin["status"] == "failed" and fin["seeds_touched"] == [14101, 14102] and fin["experiment"] == PROTOCOL["experiment"]
    assert not (out / G.RUNS).exists()


def test_execute_detects_head_moving_during_the_run(repo, R) -> None:
    head = _git(repo, "rev-parse", "HEAD")

    def runner(s):
        (repo / f"moved_{s}.txt").write_text("x", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", f"moved {s}")
        return {"seed": s}

    out = repo / "out"
    with pytest.raises(R.G.GuardError, match="指定した commit"):
        R.execute("check", [14101], out, repo, head, runner=runner, mapper=_serial)
    assert json.loads((out / G.FINISH).read_text(encoding="utf-8"))["status"] == "failed"
    assert not (out / G.RUNS).exists()


def test_main_refuses_unsafe_invocations(R, monkeypatch, tmp_path) -> None:
    """本番は --measurement-commit が必須で出力先は固定。--check は本番・0020 の seed、data/experiments の下を使えない。"""
    for argv, needle in [
        ([], "--measurement-commit"),
        (["--measurement-commit", "0" * 40, "--out", str(tmp_path)], "固定"),
        (["--check", "14199"], "--out"),
        (["--check", "14001", "--out", str(tmp_path)], "合成・確認専用"),
        (["--check", "13199", "--out", str(tmp_path)], "合成・確認専用"),
        (["--check", "14199", "--out", str(ROOT / PROTOCOL["execution"]["output_dir"])], "data/experiments"),
        (["--check", "14199", "--out", str(ROOT / "data" / "experiments" / "0020")], "data/experiments"),
    ]:
        monkeypatch.setattr("sys.argv", ["run.py", *argv])
        with pytest.raises(SystemExit, match=needle):
            R.main()
    assert not (ROOT / PROTOCOL["execution"]["output_dir"] / G.START).exists()


def test_pool_map_uses_the_fixed_worker_cap_regardless_of_cpu_count(R, monkeypatch) -> None:
    assert R.MAX_WORKERS == PROTOCOL["execution"]["max_workers"] == 2
    seen = []

    class FakePool:
        def __init__(self, max_workers):
            seen.append(max_workers)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def map(self, fn, seeds):
            return map(fn, seeds)

    monkeypatch.setattr(R, "ProcessPoolExecutor", FakePool)
    monkeypatch.setattr("os.cpu_count", lambda: 64)
    seeds = list(range(14101, 14201))
    assert [r["seed"] for r in R._pool_map(lambda s: {"seed": s}, seeds)] == seeds
    assert [r["seed"] for r in R._pool_map(lambda s: {"seed": s}, [14101])] == [14101]
    assert seen == [2, 1]


@pytest.mark.parametrize("name,bad_mapper", [
    ("欠落", lambda fn, seeds: (fn(s) for s in seeds[:-1])),
    ("重複", lambda fn, seeds: (fn(s) for s in [seeds[0], seeds[0]])),
    ("別の seed", lambda fn, seeds: (fn(s + 50) for s in seeds)),
    ("多すぎる", lambda fn, seeds: (fn(s) for s in seeds + seeds[:1])),
    ("順序", lambda fn, seeds: (fn(s) for s in reversed(seeds))),
    ("辞書でない", lambda fn, seeds: (None for _ in seeds)),
])
def test_execute_never_marks_incomplete_results_completed(repo, R, name, bad_mapper) -> None:
    head = _git(repo, "rev-parse", "HEAD")
    out = repo.parent / f"out_{name}"
    with pytest.raises(R.G.GuardError, match="結果"):
        R.execute("check", [14101, 14102], out, repo, head, runner=lambda s: {"seed": s}, mapper=bad_mapper)
    fin = json.loads((out / G.FINISH).read_text(encoding="utf-8"))
    assert fin["status"] == "failed" and fin["experiment"] == PROTOCOL["experiment"]
    assert not (out / G.RUNS).exists()


def test_the_0020_constant_scan_detects_leftovers() -> None:
    """上の検査そのものが、混入した 0020 の定数を見逃さないこと（検査の検査）。"""
    src = (EXP / "alignment.py").read_text(encoding="utf-8")
    stripped = re.sub(r"SEEN = \(.*?\)\)\)\n", "", src, flags=re.S)
    assert "range(13001" in src and "range(13001" not in stripped and "SEEN = (" not in stripped
    for leftover in ('EXPERIMENT = "0020"', 'OUT = "data/experiments/0020"', 'RNG = "0020-shuffle:{seed}"',
                     "SEEDS = range(13001, 13101)"):
        assert any(re.search(p, leftover) for p in FORBIDDEN) or re.search(r"\b13[0-2]\d\d\b", leftover), leftover


def _timed_worker(seed):
    """実際のプロセスで、開始・終了の時刻と pid を記録する（並列数の契約のためだけ。seed の計算はしない）。"""
    import os as _os
    import time as _time
    t0 = _time.monotonic()
    _time.sleep(0.15)
    t1 = _time.monotonic()
    path = Path(_os.environ["ANIMA_YOKED_TIMING_DIR"]) / f"{seed}.json"
    path.write_text(json.dumps({"seed": seed, "pid": _os.getpid(), "t0": t0, "t1": t1}), encoding="utf-8")
    return {"seed": seed}


@pytest.mark.skipif(__import__("multiprocessing").get_start_method(allow_none=False) != "fork",
                    reason="テスト関数を子プロセスへ渡すのに fork が要る（本番の run.py は fork・spawn のどちらでも動く）")
def test_pool_map_never_runs_more_than_two_processes_at_once(R, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ANIMA_YOKED_TIMING_DIR", str(tmp_path))
    seeds = list(range(14101, 14111))
    out = list(R._pool_map(_timed_worker, seeds))
    assert [r["seed"] for r in out] == seeds
    rec = [json.loads(p.read_text(encoding="utf-8")) for p in tmp_path.glob("*.json")]
    assert sorted(r["seed"] for r in rec) == seeds
    assert len({r["pid"] for r in rec}) <= 2
    events = sorted([(r["t0"], 1) for r in rec] + [(r["t1"], -1) for r in rec])
    running = peak = 0
    for _, d in events:
        running += d
        peak = max(peak, running)
    assert peak <= 2
