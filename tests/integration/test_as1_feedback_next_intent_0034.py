"""実験 0034 の道具の契約テスト（確定した事前登録 v0.2 の README・protocol.yaml、#149 merge `8b7ff8e`）。

本番の seed（27001〜27020）・smoke の seed（27101〜27106）は使わない（実行もしない）。合成の契約テスト専用の範囲（27201〜27299）だけを
使う。合成の個体は、本番と同じ道具（measure.measure_seed）・同じ式で、区間だけを小さくした Plan（SMALL：区間 W は e の Pulse
31〜180、H ＝ 60、本体は 239 まで、O3 の複製は 30 の後に作り 90 で比べる）で、実物の runtime を通して作る。結果を見て Plan・seed を
選んでいない（seed は範囲の最初から順に使う）。テストは操作の確認・記録の形・判定の算術だけを確かめ、合成の個体の判定の量（s_e・d_e・
n₊・n₋・P_i・J_A）の値を表示も判定もしない。

使った合成の seed（PR に開示）：27201〜27210（SMALL で実物の runtime を通す）、27221〜27226（一度限りの実行の契約。dummy の計算）、
27290〜27299 のうち 27299 から順に最初の出来事のある個体（本番の Plan で実物の runtime を通す確かめ）。
"""

import copy
import functools
import gzip
import importlib.util
import json
import subprocess
from concurrent.futures import Future
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments" / "0034_as1_feedback_next_intent"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = _load("measure_0034_test", EXP / "measure.py")
AN = _load("analyze_0034_test", EXP / "analyze.py")
AL = _load("alignment_0034_test", EXP / "alignment.py")
R = _load("run_0034_test", EXP / "run.py")
SMALL = M.Plan(window_first=31, window_last=180, horizon=60, body_runs_to=239, checkpoints=(30, 120, 239),
               clone_check_at=30, clone_check_until=90)
SYN = list(range(27201, 27211))
GUARD_SEEDS = list(range(27221, 27227))


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)


def _raw(run: dict, mode: str = "synthetic") -> dict:
    return {"meta": {"experiment": "0034", "kind": PROTOCOL["kind"], "mode": mode, "seed": run["seed"],
                     "manifest": M.manifest_raw()}, "run": run}


@functools.lru_cache(maxsize=None)
def _measured(seed: int) -> str:
    return json.dumps(_raw(M.measure_seed(PROTOCOL, seed, SMALL)))


def measured(seed: int) -> dict:
    """SMALL の Plan で実物の runtime を通した合成の個体の生の記録（JSON を通した形。返すのは複製）。"""
    return json.loads(_measured(seed))


def failures(data: dict, seed: int) -> dict:
    return {k: v for k, v in AN.check_seed(data, "synthetic", seed, SMALL).items() if v}


def first_with_events() -> int:
    """合成の範囲の最初から順に見て、SMALL の区間 W に出来事がある最初の個体（決定的に求める。出来事の中身は見ない）。"""
    return next(s for s in SYN if measured(s)["run"]["events"])


# ---- protocol と道具の一致 ----------------------------------------------------------------------

def test_protocol_and_tools_are_aligned() -> None:
    AL.check(PROTOCOL)


def test_formal_plan_follows_the_protocol_formulas() -> None:
    plan = M.formal_plan(PROTOCOL)
    assert (plan.window_first, plan.window_last, plan.horizon, plan.body_runs_to) == (301, 1800, 300, 2099)
    assert plan.checkpoints == (300, 600, 900, 1200, 1500, 1800, 2099)


def test_the_run_entry_point_uses_only_the_protocol_plan() -> None:
    import inspect
    assert inspect.signature(R.measure).parameters.keys() == {"seed"}
    assert "measure_seed(PROTOCOL, seed)" in inspect.getsource(R.measure)
    assert R.OUT_DIR == Path("data/experiments/0034") and R.MAX_WORKERS == 2


# ---- 実物の runtime を通した合成の個体：操作の確認がすべて成り立つ -----------------------------------

@pytest.mark.parametrize("seed", SYN)
def test_synthetic_individuals_pass_every_operation_check(seed) -> None:
    assert failures(measured(seed), seed) == {}


@functools.lru_cache(maxsize=None)
def _formal_synthetic() -> tuple[int, str]:
    """本番の Plan での確かめ：合成の範囲の最後（27299）から順に見て、本番の Plan の区間 W に出来事がある最初の個体（決定的に求める）。"""
    plan = M.formal_plan(PROTOCOL)
    for seed in range(27299, 27289, -1):
        run = M.measure_seed(PROTOCOL, seed, plan)
        if run["events"]:
            return seed, json.dumps(_raw(run))
    raise AssertionError("27290〜27299 に出来事のある個体がない")


def test_the_formal_plan_through_the_runtime_passes_every_operation_check() -> None:
    seed, text = _formal_synthetic()
    data = json.loads(text)
    assert {k: v for k, v in AN.check_seed(data, "synthetic", seed, M.formal_plan(PROTOCOL)).items() if v} == {}
    assert data["run"]["clone_check"]["at"] == 300 and data["run"]["clone_check"]["until"] == 600
    assert sorted(map(int, data["run"]["body"]["checkpoints"])) == [300, 600, 900, 1200, 1500, 1800, 2099]


def test_the_synthetic_range_contains_individuals_with_and_without_events() -> None:
    have = [bool(measured(s)["run"]["events"]) for s in SYN]
    assert any(have) and not all(have)                    # 適用できる個体と N/A の個体の両方を確かめられる


def test_raw_has_no_judgment_quantities() -> None:
    run = measured(first_with_events())["run"]
    text = json.dumps(run)
    for name in ("s_e", "d_e", "n_plus", "n_minus", "P_i", "J_A", '"B"', "d_CF", "d_FB"):
        assert name not in text, name


# ---- 改ざん・欠けの検出（確認が成り立たなくなる） ------------------------------------------------------

def _tampered(f, check: str) -> None:
    seed = first_with_events()
    data = measured(seed)
    f(data["run"])
    got = failures(data, seed)
    assert check in got, (check, got)


def test_o2_detects_an_extra_or_missing_sensory_event() -> None:
    _tampered(lambda r: r["body"]["sensory"].append([r["plan"]["body_runs_to"], r["roles"]["source_receptor"]]), "O2")
    _tampered(lambda r: r["body"]["sensory"].pop(0), "O2")
    _tampered(lambda r: r["body"]["intents"].pop(), "O2")


def test_o3_detects_a_clone_that_differs() -> None:
    _tampered(lambda r: r["clone_check"]["sigma_clone"]["units"][r["roles"]["source"]].update(activity=0.123), "O3")
    _tampered(lambda r: r["clone_check"]["activity_clone"].append([r["plan"]["clone_check_until"], "s1"]), "O3")


def test_o4_detects_wrong_cancellation_or_sensory() -> None:
    _tampered(lambda r: r["events"][0].update(n_pending=copy.deepcopy(r["events"][0]["body_pending"])), "O4")   # e を取り消していない
    _tampered(lambda r: r["events"][0]["systems"]["N"]["sensory"].append(list(r["events"][0]["systems"]["N"]["sensory"][0])
                                                                       if r["events"][0]["systems"]["N"]["sensory"]
                                                                       else [r["events"][0]["t"] + 1, r["events"][0]["e"]["receptor"]]), "O4")
    _tampered(lambda r: r["events"].pop(0), "O4")                   # 出来事が欠けた（A3 の適用の対象が崩れる）
    _tampered(lambda r: r["events"][0]["e"].update(pulse=r["events"][0]["e"]["pulse"] + 1), "O4")


def test_o5_detects_a_broken_intervention() -> None:
    _tampered(lambda r: r["events"][0]["systems"]["F_FB"]["masked_weights"].__setitem__(0, 0.004), "O5")
    _tampered(lambda r: r["events"][0]["systems"]["N_CF"]["weight_changes"].append(
        [r["events"][0]["t"] + 1, r["events"][0]["systems"]["N_CF"]["weight_changes"][0][1]]), "O5")
    _tampered(lambda r: r["events"][0]["systems"]["F_CF"]["interventions"]["active"].clear(), "O5")
    _tampered(lambda r: r["events"][0]["systems"]["N"]["history"].append([0, "x", []]), "O5")
    _tampered(lambda r: next(iter(r["events"][0]["systems"]["F_CF"]["interventions"]["frozen"].values())).update(weight=0.0042), "O5")
    _tampered(lambda r: r["events"][0]["systems"]["N_FB"]["masked_weights"].pop(), "O5")    # Pulse ごとの証拠の欠け


def test_o4_compares_only_the_post_branch_slice() -> None:
    """監査 025：本体の分岐の前の感覚の出来事は比べない（N のログは分岐から始まる）。分岐の後に余計な刺激があれば不合格。"""
    seed = first_with_events()
    data = measured(seed)
    ev = data["run"]["events"][-1]
    if len(data["run"]["events"]) > 1:
        assert any(x[0] <= ev["t"] for x in data["run"]["body"]["sensory"])          # 本体には分岐の前の出来事がある
    assert not any(x[0] <= ev["t"] for x in ev["systems"]["N"]["sensory"])            # N のログは分岐から始まる
    assert failures(data, seed) == {}
    ev["systems"]["N"]["sensory"].append([ev["t"] + 1, data["run"]["roles"]["other"].replace("s", "receptor.x")])
    assert "O4" in failures(data, seed)


def test_structure_detects_extra_fields_and_wrong_roles() -> None:
    _tampered(lambda r: r.update(judgment={"J_A": True}), "structure")
    _tampered(lambda r: r["roles"].update(source="s9"), "structure")
    _tampered(lambda r: r["plan"].update(horizon=61), "structure")


def test_o6_rejects_seeds_outside_the_range_or_seen() -> None:
    out: list = []
    AN._o6(27001, "synthetic", out)
    assert out
    out = []
    AN._o6(27201, "synthetic", out)
    assert out == []


# ---- 出来事ごとの量・個体の量・判定の算術（合成の入力） ----------------------------------------------------

@pytest.mark.parametrize("tf,tn,sign,d", [(110, 115, "+", 5), (110, 105, "-", -5), (110, 110, "0", 0),
                                          (110, None, "+", None), (None, 105, "-", None), (None, None, "?", None)])
def test_sign_follows_the_censoring_table(tf, tn, sign, d) -> None:
    assert AN.sign_of(tf, tn) == sign and AN.difference(tf, tn) == d


def test_first_after_respects_the_horizon() -> None:
    assert AN.first_after([90, 101, 160], 100, 60) == 101
    assert AN.first_after([90, 161], 100, 60) is None
    assert AN.first_after([160], 100, 60) == 160


def test_individual_applicability_depends_only_on_body_events() -> None:
    none = AN.individual({"plan": {"horizon": 60}, "roles": {"source": "s1"},
                          "body": {"intents": [[10, "d"]], "activity": []}, "events": []})
    assert none["applicable"] is False and none["P_i"] is False                     # 出来事なし：N/A
    zeros = AN.individual({"plan": {"horizon": 60}, "roles": {"source": "s1"}, "body": {"intents": [[10, "d"], [20, "d"]], "activity": []},
                           "events": [{"t": 10, "e": {"pulse": 11}, "systems": {k: {"tau": 20 if k == "N" else None} for k in AN.SYSTEMS}}]})
    assert zeros["applicable"] is True and zeros["n_zero"] == 1 and zeros["P_i"] is False   # 効果 0 でも適用できる・不成立


def test_judge_thresholds_and_inconclusive() -> None:
    def inds(n_app: int, n_hold: int, n_na: int = 0) -> dict:
        d = {}
        for i in range(n_app):
            d[str(i)] = {"applicable": True, "P_i": i < n_hold}
        for i in range(n_na):
            d[f"na{i}"] = {"applicable": False, "P_i": False}
        return d
    assert AN.judge(inds(9, 9, 11))["status"] == "inconclusive"
    assert AN.judge(inds(10, 9, 10))["status"] == "established"
    assert AN.judge(inds(10, 8, 10))["status"] == "not_established"
    assert AN.judge(inds(20, 15))["status"] == "established" and AN.judge(inds(20, 14))["status"] == "not_established"
    assert AN.judge(inds(13, 10, 7))["k"] == 10


def test_k_of_m_matches_the_protocol_table() -> None:
    for m, k in PROTOCOL["judgment"]["J_A"]["k_of_m"].items():
        assert AN.k_of_m(m, 0.05) == k


def test_clopper_pearson_known_values() -> None:
    lo, hi = AN.clopper_pearson(16, 20)
    assert round(lo, 4) == 0.5634 and round(hi, 4) == 0.9427
    assert AN.clopper_pearson(0, 10)[0] == 0.0 and AN.clopper_pearson(10, 10)[1] == 1.0


def test_analysis_of_the_synthetic_individuals_runs_through_and_smoke_is_blind() -> None:
    runs = {s: measured(s) for s in SYN}
    report = AN.analyze_runs(runs, "synthetic", SMALL)
    assert report["valid"] is True and set(report["judgment"]["J_A"]) >= {"m", "count_P_i", "status"}
    assert set(report["individuals"]) == {str(s) for s in SYN}
    smoke = AN.analyze_runs({s: dict(measured(s), meta=dict(measured(s)["meta"], mode="smoke")) for s in SYN[:2]}, "smoke", SMALL)
    text = json.dumps(smoke)
    assert set(smoke) == {"mode", "checks", "valid"}
    for name in ("events", "tau", "d_e", "n_plus", "P_i", "weights", "judgment"):
        assert name not in text, name


def test_an_invalid_individual_blocks_the_judgment() -> None:
    runs = {s: measured(s) for s in SYN}
    s = first_with_events()
    runs[s]["run"]["events"][0]["n_pending"] = copy.deepcopy(runs[s]["run"]["events"][0]["body_pending"])
    report = AN.analyze_runs(runs, "synthetic", SMALL)
    assert report["valid"] is False and report["judgment"] is None and str(s) in report["failed_checks"]


# ---- 一度限りの実行（guard と run.execute。dummy の計算） -------------------------------------------------

class SerialExecutor:
    def __init__(self, n: int) -> None:
        self.n = n

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def submit(self, fn, *args, **kwargs):
        f = Future()
        try:
            f.set_result(fn(*args, **kwargs))
        except BaseException as e:                     # noqa: BLE001
            f.set_exception(e)
        return f


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path) -> Path:
    r = tmp_path / "repo"
    (r / EXP.relative_to(ROOT)).mkdir(parents=True)
    (r / EXP.relative_to(ROOT) / "protocol.yaml").write_bytes((EXP / "protocol.yaml").read_bytes())
    _git(r, "init", "-q")
    for k, v in (("user.email", "t@example.invalid"), ("user.name", "t"), ("commit.gpgsign", "false")):
        _git(r, "config", k, v)
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "init")
    return r


def _dummy(seed: int) -> dict:
    return {"seed": seed, "dummy": True}


def _exec(repo, out, seeds, runner=_dummy):
    return R.execute("synthetic", seeds, out, repo, _git(repo, "rev-parse", "HEAD"), runner=runner,
                     executor_factory=SerialExecutor)


def test_each_seed_runs_once_and_a_failure_stops_the_rest(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    done = _exec(repo, out, GUARD_SEEDS[:2])
    assert done["completed"] == GUARD_SEEDS[:2]
    with pytest.raises(R.G.GuardError):
        _exec(repo, out, GUARD_SEEDS[:1])                                # 二度と始めない

    def boom(seed: int) -> dict:
        if seed == GUARD_SEEDS[3]:
            raise RuntimeError("x")
        return _dummy(seed)
    out2 = tmp_path / "out2"
    with pytest.raises(R.G.GuardError):
        _exec(repo, out2, GUARD_SEEDS[2:6], runner=boom)
    statuses = {s: st for s, (st, _) in R.G.scan(out2)["seeds"].items()}
    assert statuses[GUARD_SEEDS[3]] == "failed" and GUARD_SEEDS[5] not in statuses
    with pytest.raises(R.G.GuardError):
        _exec(repo, out2, GUARD_SEEDS[5:6])                              # 失敗があれば、どの seed も始めない


def test_formal_requires_the_measurement_commit_and_the_range(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    with pytest.raises(R.G.GuardError):
        R.execute("formal", [27001], tmp_path / "o", repo, None, runner=_dummy, executor_factory=SerialExecutor)
    with pytest.raises(R.G.GuardError):
        R.execute("synthetic", [27001], tmp_path / "o", repo, _git(repo, "rev-parse", "HEAD"), runner=_dummy,
                  executor_factory=SerialExecutor)


def test_records_state_and_the_synthetic_pipeline_through_run_and_analyze(repo, tmp_path, monkeypatch) -> None:
    """run.execute（合成の mode、SMALL の Plan の実物の計算）→ 記録の確認 → 生の記録からの解析、を通す（判定の値は見ない）。"""
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    seeds = SYN[:3]
    runner = functools.partial(M.measure_seed, PROTOCOL, plan=SMALL)
    _exec(repo, out, seeds[:2], runner=runner)
    assert AN.verify_records(out, "synthetic", seeds)["state"] == "incomplete"
    _exec(repo, out, seeds[2:], runner=runner)
    records = AN.verify_records(out, "synthetic", seeds)
    assert records["state"] == "complete" and records["measurement_commit"] == _git(repo, "rev-parse", "HEAD")
    runs = {s: AN.read_raw(R.G.seed_dir(out, s) / R.G.RAW) for s in seeds}
    report = AN.analyze_runs(runs, "synthetic", SMALL)
    assert report["valid"] is True and report["judgment"]["J_A"]["status"] == "inconclusive"   # 3 個体なので m ＜ 10
