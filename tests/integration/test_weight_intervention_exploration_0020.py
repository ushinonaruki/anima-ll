"""探索 0020 の道具の契約テスト（README §3〜§6）。

探索の seed（13001〜13100）は使わない。合成・確認専用の範囲（13101〜13200）だけを使う。
合成の状態は 0017〜0019 の契約と同じ作り方（合成専用の seed の Birth State、入力なし、手で置いた重み、Unit の activity・adaptation は 0）。
ここで使った seed：13101（2 腕の発火の列が分かれる）・13102（A が両腕で沈黙し、列が同じ）・
13106（A が発火するのに、600 Pulse のあいだ列が同じ）・13199（実物の手順の通しの確認）。探索の経緯は PR に開示する。
"""

import copy
import importlib.util
import json
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
G = _load("guard_0020_test", EXP / "guard.py")
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


FAKE_COMMIT = "0" * 40


def _check_data(check_run, mode="check", commit=FAKE_COMMIT, runs=None):
    """通しの確認のデータと、それに合う開始・終了の記録（in-memory。結果のファイルの sha256 は固定の値で代える）。"""
    runs = [check_run] if runs is None else runs
    seeds = [r["seed"] for r in runs]
    data = {"meta": {"experiment": "0020", "kind": "exploration", "mode": mode, "git_commit": commit,
                     "protocol": PROTOCOL, "manifest": W.manifest_raw(PROTOCOL), "seeds": seeds},
            "runs": runs}
    proto_sha = G.sha256_file(EXP / "protocol.yaml")
    ek = {"experiment": "0020", "kind": "exploration"}
    records = {"start": ek | {"mode": mode, "git_commit": commit, "seeds": seeds, "protocol_sha256": proto_sha},
               "finish": ek | {"status": "completed", "mode": mode, "git_commit_start": commit,
                               "git_commit_end": commit, "seeds": seeds, "runs_sha256": "f" * 64},
               "runs_sha256": "f" * 64}
    return data, records


def test_check_report_hides_records(A, check_run) -> None:
    data, records = _check_data(check_run)
    report = A.analyze(data, "check", records)
    assert report["valid"], report["problems"]
    assert not ({"summary", "per_seed"} & set(report))


def test_check_completeness_rejects_bad_data(A, check_run) -> None:
    """空のデータ・seed の重複・meta と実データの不一致・mode の偽装・commit の偽装・範囲外の seed は invalid（README §5）。"""
    def invalid(data, records, mode="check", needle=None):
        r = A.analyze(data, mode, records)
        assert not r["valid"]
        if needle:
            assert any(needle in p for p in r["problems"]), r["problems"]

    # レビューで再現された形：runs ＝ []、git_commit ＝ "unknown"、mode の印なし、meta.seeds ＝ [13001]
    repro = {"meta": {"git_commit": "unknown", "check": False, "seeds": [13001], "protocol": PROTOCOL,
                      "manifest": W.manifest_raw(PROTOCOL)}, "runs": []}
    invalid(repro, None, needle="個体が 1 つもない")
    data, rec = _check_data(check_run, runs=[])
    invalid(data, rec, needle="個体が 1 つもない")
    data, rec = _check_data(check_run, runs=[check_run, check_run])
    invalid(data, rec, needle="seed が重複")
    data, rec = _check_data(check_run)
    data["meta"]["seeds"] = [13198]
    invalid(data, rec, needle="meta の seed の列")
    data, rec = _check_data(check_run, mode="exploration")
    invalid(data, rec, mode="check", needle="データの mode")        # 探索のデータを通しの確認として解析しない
    data, rec = _check_data(check_run)
    invalid(data, rec, mode="exploration", needle="データの mode")  # 通しの確認のデータを探索として解析しない
    invalid(data, rec, mode="exploration", needle="13001〜13100 の全件ではない")
    data, rec = _check_data(check_run, commit="unknown")
    invalid(data, rec, needle="40 桁の commit")
    data, rec = _check_data(check_run)
    data["meta"]["experiment"] = "0019"
    invalid(data, rec, needle="experiment・kind")
    bad = copy.deepcopy(check_run)
    bad["seed"] = 13001                                               # 探索の範囲の seed（中身は 13199 のまま）
    data, rec = _check_data(check_run, runs=[bad])
    invalid(data, rec, needle="範囲の外の seed")


def test_run_records_are_verified(A, check_run) -> None:
    """開始・終了の記録がない・failed・commit や sha256 の不一致は invalid（README §7.1）。"""
    data, rec = _check_data(check_run)
    for mutate, needle in [
        (lambda r: r.__setitem__("start", None), "開始の記録"),
        (lambda r: r.__setitem__("finish", None), "終了の記録"),
        (lambda r: r["finish"].__setitem__("status", "failed"), "completed ではない"),
        (lambda r: r["finish"].__setitem__("git_commit_end", "1" * 40), "commit"),
        (lambda r: r.__setitem__("runs_sha256", "e" * 64), "sha256"),
        (lambda r: r["start"].__setitem__("protocol_sha256", "e" * 64), "protocol.yaml"),
        (lambda r: r["start"].__setitem__("mode", "exploration"), "mode"),
        (lambda r: r["start"].__setitem__("experiment", "0019"), "experiment・kind"),
        (lambda r: r["finish"].__setitem__("kind", "verification"), "experiment・kind"),
    ]:
        r = copy.deepcopy(rec)
        mutate(r)
        report = A.analyze(data, "check", r)
        assert not report["valid"] and any(needle in p for p in report["problems"]), (needle, report["problems"])


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



def test_trains_identical_is_derived_from_full_trains(A, check_run) -> None:
    """trains_identical は保存した分岐の記録ではなく、全発火の列から決まる（記録を消しても変わらない）。"""
    sp = check_run["arms"]["spikes"]
    expected = A.first_difference(sp["control"], sp["intervention"]) is None
    bad = copy.deepcopy(check_run)
    bad["arms"]["divergence"] = None
    assert A.record_run(bad)["trains_identical"] == expected == A.record_run(check_run)["trains_identical"]


# ---- 分岐の記録の独立な再検証（README §5）。合成の 2 腕で ---------------------------------------------------

def _arms(res):
    return {"spikes": res["spikes"], "divergence": res["divergence"]}


def test_divergence_record_is_revalidated_from_full_trains(A) -> None:
    res, fork, _, _ = _pair(DIVERGES)
    assert A.check_divergence(_arms(res), fork, 0, N, 1e-12) == []
    t = res["divergence"]["pulse"]
    assert A.first_difference(res["spikes"]["control"], res["spikes"]["intervention"])[0] == t

    def problems(mutate):
        arms = copy.deepcopy(_arms(res))
        mutate(arms)
        return A.check_divergence(arms, fork, 0, N, 1e-12)

    # 欠落・時刻の改変・Unit の改変・発火のコピーの改変・直前の状態の改変を検出する
    assert any("分岐の記録がない" in p for p in problems(lambda a: a.__setitem__("divergence", None)))
    assert any("Pulse・Unit" in p for p in problems(lambda a: a["divergence"].__setitem__("pulse", t + 1)))
    assert any("Pulse・Unit" in p for p in problems(lambda a: a["divergence"].__setitem__("units", ["s9"])))
    assert any("コピー（t）" in p for p in problems(
        lambda a: a["divergence"]["spikes"]["t"]["control"].append([t, "s9"])))
    assert any("コピー（t-1）" in p for p in problems(
        lambda a: a["divergence"]["spikes"]["t-1"]["intervention"].clear() if a["divergence"]["spikes"]["t-1"]["intervention"]
        else a["divergence"]["spikes"]["t-1"]["intervention"].append([t - 1, "s9"])))
    cid = next(iter(fork["control"]["connections"]))
    assert any("接続の状態" in p for p in problems(
        lambda a: a["divergence"]["before"]["t-2"]["control"]["connections"][cid].__setitem__(
            "weight", a["divergence"]["before"]["t-2"]["control"]["connections"][cid]["weight"] + 1e-9)))
    uid = next(iter(fork["control"]["units"]))
    assert any("fire_count" in p for p in problems(
        lambda a: a["divergence"]["before"]["t-1"]["intervention"]["units"][uid].__setitem__(
            "fire_count", a["divergence"]["before"]["t-1"]["intervention"]["units"][uid]["fire_count"] + 1)))
    assert any("再構成" in p for p in problems(
        lambda a: a["divergence"]["before"]["t-1"]["control"]["units"][uid].__setitem__("activity", 10.0)))
    # 全発火の列そのものを改変すると、最初の差が変わる（記録の Pulse・Unit と合わなくなる）
    assert problems(lambda a: a["spikes"]["intervention"].__setitem__(
        slice(None), [x for x in a["spikes"]["intervention"] if x[0] != t] + [[t, u] for u in spikes_at_(a, "control", t)]))


def spikes_at_(arms, arm, t):
    return sorted(u for p, u in arms["spikes"][arm] if p == t)


def test_divergence_record_on_identical_trains(A) -> None:
    """列が同じなら分岐の記録は None でなければならない（作り話の分岐を検出する）。"""
    res, fork, _, _ = _pair(SILENT_IDENTICAL)
    assert res["divergence"] is None and A.check_divergence(_arms(res), fork, 0, N, 1e-12) == []
    arms = copy.deepcopy(_arms(res))
    arms["divergence"] = {"pulse": 5, "units": ["s1"], "before": {}, "spikes": {}}
    assert any("一度も分かれないのに" in p for p in A.check_divergence(arms, fork, 0, N, 1e-12))


def test_spike_trains_must_be_well_formed(A) -> None:
    res, fork, _, _ = _pair(SILENT_IDENTICAL)
    for mutate, needle in [(lambda a: a["spikes"]["control"].append([N + 1, "s1"]), "外の Pulse"),
                           (lambda a: a["spikes"]["control"].insert(0, [N, "s1"]), "順に並んでいない"),
                           (lambda a: a["spikes"]["control"].extend([[N, "s2"], [N, "s2"]]), "重複")]:
        arms = copy.deepcopy(_arms(res))
        mutate(arms)
        assert any(needle in p for p in A.check_divergence(arms, fork, 0, N, 1e-12)), needle


def test_sign_relation_does_not_count_zeros_as_agreement(A) -> None:
    assert A.sign_relation(0.0, 0.0) == "both_zero"
    assert A.sign_relation(0.0, 1e-9) == A.sign_relation(-1e-9, 0.0) == "one_zero"
    assert A.sign_relation(2.0, 1e-9) == "agree" and A.sign_relation(-2.0, 1e-9) == "disagree"


# ---- 一度限りの実行の保護（README §7.1）。使い捨ての git リポジトリで ------------------------------------

import subprocess  # noqa: E402


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """protocol.yaml だけを置いた使い捨てのリポジトリ（execute が protocol の sha256 を読むため）。"""
    r = tmp_path / "repo"
    (r / "experiments" / "0020_weight_intervention_exploration").mkdir(parents=True)
    (r / "experiments" / "0020_weight_intervention_exploration" / "protocol.yaml").write_bytes(
        (EXP / "protocol.yaml").read_bytes())
    (r / ".gitignore").write_text("/out/\n", encoding="utf-8")
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@example.invalid")
    _git(r, "config", "user.name", "t")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "init")
    return r


@pytest.fixture
def R():
    return _load("run_0020_test", EXP / "run.py")


def _serial(fn, seeds):
    return (fn(s) for s in seeds)


def test_guard_requires_a_clean_real_commit(repo, monkeypatch) -> None:
    head = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setenv("ANIMA_GIT_COMMIT", "f" * 40)                 # 環境変数では commit を代えられない
    assert G.verify_clean_commit(repo) == head == G.verify_clean_commit(repo, head)
    with pytest.raises(G.GuardError, match="指定した commit"):
        G.verify_clean_commit(repo, "1" * 40)
    (repo / "untracked.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(G.GuardError, match="作業ツリー"):
        G.verify_clean_commit(repo, head)
    (repo / "untracked.py").unlink()
    (repo / "experiments" / "0020_weight_intervention_exploration" / "protocol.yaml").write_text("x: 1\n")
    with pytest.raises(G.GuardError, match="作業ツリー"):
        G.verify_clean_commit(repo, head)
    with pytest.raises(G.GuardError, match="git"):
        G.verify_clean_commit(repo.parent / "not_a_repo")


def test_execute_runs_once_and_saves_atomically(repo, R) -> None:
    out = repo / "out"
    head = _git(repo, "rev-parse", "HEAD")
    calls = []
    runner = lambda s: calls.append(s) or {"seed": s}
    rec = R.execute("check", [13101, 13102], out, repo, head, runner=runner, mapper=_serial)
    assert rec["status"] == "completed" and rec["git_commit_start"] == rec["git_commit_end"] == head
    assert calls == [13101, 13102]
    assert sorted(p.name for p in out.iterdir()) == [G.FINISH, G.START, G.RUNS]   # 一時ファイルが残らない
    assert G.sha256_file(out / G.RUNS) == rec["runs_sha256"]
    start = json.loads((out / G.START).read_text(encoding="utf-8"))
    assert start["git_commit"] == head and start["seeds"] == [13101, 13102] and start["mode"] == "check"
    before = {p.name: p.read_bytes() for p in out.iterdir()}
    # 2 回目は、seed に触れる前に拒否し、何も上書きしない
    with pytest.raises(R.G.GuardError):
        R.execute("check", [13101, 13102], out, repo, head, runner=runner, mapper=_serial)
    assert calls == [13101, 13102] and {p.name: p.read_bytes() for p in out.iterdir()} == before


def test_execute_refuses_before_touching_seeds(repo, R) -> None:
    head = _git(repo, "rev-parse", "HEAD")
    calls = []
    runner = lambda s: calls.append(s) or {"seed": s}
    with pytest.raises(R.G.GuardError, match="指定した commit"):
        R.execute("exploration", [13001], repo.parent / "out1", repo, "1" * 40, runner=runner, mapper=_serial)
    (repo / "dirty.txt").write_text("x", encoding="utf-8")
    with pytest.raises(R.G.GuardError, match="作業ツリー"):
        R.execute("exploration", [13001], repo.parent / "out2", repo, head, runner=runner, mapper=_serial)
    (repo / "dirty.txt").unlink()
    (repo.parent / "out3").mkdir()
    (repo.parent / "out3" / G.START).write_text("{}", encoding="utf-8")       # 中断した実行の跡
    with pytest.raises(R.G.GuardError, match="既にある"):
        R.execute("exploration", [13001], repo.parent / "out3", repo, head, runner=runner, mapper=_serial)
    (repo.parent / "out4").mkdir()
    (repo.parent / "out4" / G.FINISH).write_text("{}", encoding="utf-8")      # 終了の記録だけが残っている
    with pytest.raises(R.G.GuardError, match="既にある"):
        R.execute("exploration", [13001], repo.parent / "out4", repo, head, runner=runner, mapper=_serial)
    with pytest.raises(R.G.GuardError):
        R.execute("exploration", [], repo.parent / "out5", repo, head, runner=runner, mapper=_serial)
    with pytest.raises(R.G.GuardError):
        R.execute("exploration", [13001, 13001], repo.parent / "out6", repo, head, runner=runner, mapper=_serial)
    assert calls == []
    assert not (repo.parent / "out1").exists() and not (repo.parent / "out2").exists()


def test_execute_records_failure_and_does_not_save_results(repo, R) -> None:
    head = _git(repo, "rev-parse", "HEAD")

    def runner(s):
        if s == 13102:
            raise RuntimeError("boom")
        return {"seed": s}

    out = repo / "out"
    with pytest.raises(RuntimeError, match="boom"):
        R.execute("check", [13101, 13102], out, repo, head, runner=runner, mapper=_serial)
    fin = json.loads((out / G.FINISH).read_text(encoding="utf-8"))
    assert fin["status"] == "failed" and fin["seeds_touched"] == [13101, 13102] and "boom" in fin["reason"]
    assert not (out / G.RUNS).exists()
    with pytest.raises(R.G.GuardError):                                  # 失敗した範囲を黙って再実行しない
        R.execute("check", [13101, 13102], out, repo, head, runner=lambda s: {"seed": s}, mapper=_serial)


def test_execute_detects_head_moving_during_the_run(repo, R) -> None:
    head = _git(repo, "rev-parse", "HEAD")

    def runner(s):                                                     # 計測の途中で HEAD が動く
        (repo / f"moved_{s}.txt").write_text("x", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", f"moved {s}")
        return {"seed": s}

    out = repo / "out"
    with pytest.raises(R.G.GuardError, match="指定した commit"):
        R.execute("check", [13101], out, repo, head, runner=runner, mapper=_serial)
    fin = json.loads((out / G.FINISH).read_text(encoding="utf-8"))
    assert fin["status"] == "failed" and fin["git_commit_start"] == head
    assert not (out / G.RUNS).exists()


def test_main_refuses_unsafe_invocations(R, monkeypatch, tmp_path) -> None:
    """探索の起動は --measurement-commit が必須で、出力先は固定。--check は探索の出力先・範囲外の seed を使えない。"""
    for argv, needle in [
        ([], "--measurement-commit"),
        (["--measurement-commit", "0" * 40, "--out", str(tmp_path)], "固定"),
        (["--check", "13199"], "--out"),
        (["--check", "13001", "--out", str(tmp_path)], "合成・確認専用"),
        (["--check", "13199", "--out", str(ROOT / "data" / "experiments" / "0020")], "探索の出力先"),
    ]:
        monkeypatch.setattr("sys.argv", ["run.py", *argv])
        with pytest.raises(SystemExit, match=needle):
            R.main()
    assert not (ROOT / "data" / "experiments" / "0020" / G.START).exists()



# ---- 並列数の上限と、保存の前の全件の一致（README §7.1、#82 再レビュー） ------------------------------------

def test_pool_map_uses_the_fixed_worker_cap_regardless_of_cpu_count(R, monkeypatch) -> None:
    """同時に動かすプロセスの上限は protocol の 2 で、CPU 数が多くても増えない。"""
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
    assert [r["seed"] for r in R._pool_map(lambda s: {"seed": s}, list(range(13001, 13101)))] == list(range(13001, 13101))
    assert [r["seed"] for r in R._pool_map(lambda s: {"seed": s}, [13101])] == [13101]
    assert seen == [2, 1]


def _timed_worker(seed):
    """実際のプロセスで、開始・終了の時刻と pid を記録する（並列数の契約のためだけ）。"""
    import os as _os
    import time as _time
    t0 = _time.monotonic()
    _time.sleep(0.15)
    t1 = _time.monotonic()
    path = Path(_os.environ["ANIMA_0020_TIMING_DIR"]) / f"{seed}.json"
    path.write_text(json.dumps({"seed": seed, "pid": _os.getpid(), "t0": t0, "t1": t1}), encoding="utf-8")
    return {"seed": seed}


@pytest.mark.skipif(__import__("multiprocessing").get_start_method(allow_none=False) != "fork",
                    reason="テスト関数を子プロセスへ渡すのに fork が要る（本番の run.py は fork・spawn のどちらでも動く）")
def test_pool_map_never_runs_more_than_two_processes_at_once(R, monkeypatch, tmp_path) -> None:
    """実際のプロセスで：同時に動くのは 2 つまで、使うプロセスも 2 つまで、各 seed はちょうど 1 回、結果は seed の順。"""
    monkeypatch.setenv("ANIMA_0020_TIMING_DIR", str(tmp_path))
    seeds = list(range(13101, 13111))
    out = list(R._pool_map(_timed_worker, seeds))
    assert [r["seed"] for r in out] == seeds
    rec = [json.loads(p.read_text(encoding="utf-8")) for p in tmp_path.glob("*.json")]
    assert sorted(r["seed"] for r in rec) == seeds                     # 各 seed ちょうど 1 回
    assert len({r["pid"] for r in rec}) <= 2
    events = sorted([(r["t0"], 1) for r in rec] + [(r["t1"], -1) for r in rec])
    running = peak = 0
    for _, d in events:
        running += d
        peak = max(peak, running)
    assert peak <= 2


@pytest.mark.parametrize("name,bad_mapper", [
    ("欠落", lambda fn, seeds: (fn(s) for s in seeds[:-1])),
    ("重複", lambda fn, seeds: (fn(s) for s in [seeds[0], seeds[0]])),
    ("別の seed", lambda fn, seeds: (fn(s + 1000) for s in seeds)),
    ("多すぎる", lambda fn, seeds: (fn(s) for s in seeds + seeds[:1])),
    ("順序", lambda fn, seeds: (fn(s) for s in reversed(seeds))),
    ("辞書でない", lambda fn, seeds: (None for _ in seeds)),
])
def test_execute_never_marks_incomplete_results_completed(repo, R, name, bad_mapper) -> None:
    """mapper が正常に終わっても結果が期待の seed の列と一致しなければ、failed を残し、結果も completed も作らない。"""
    head = _git(repo, "rev-parse", "HEAD")
    out = repo.parent / f"out_{name}"
    with pytest.raises(R.G.GuardError, match="結果"):
        R.execute("check", [13101, 13102], out, repo, head, runner=lambda s: {"seed": s}, mapper=bad_mapper)
    fin = json.loads((out / G.FINISH).read_text(encoding="utf-8"))
    assert fin["status"] == "failed" and fin["seeds_touched"] == [13101, 13102]
    assert fin["experiment"] == "0020" and fin["kind"] == "exploration"
    assert not (out / G.RUNS).exists()
