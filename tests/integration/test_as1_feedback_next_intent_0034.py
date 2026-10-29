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
import re
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
                     "manifest": M.manifest_raw(), "blind": mode == "smoke"}, "run": run}


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
    _tampered(lambda r: r["events"][0]["systems"]["F_FB"]["masked_weights"][0].__setitem__(1, 0.004), "O5")   # 値
    _tampered(lambda r: r["events"][0]["systems"]["N_FB"]["masked_weights"].pop(), "O5")              # 最後の Pulse の欠け
    _tampered(lambda r: r["events"][0]["systems"]["F_CF"]["interventions"]["active"].clear(), "O5")
    _tampered(lambda r: r["events"][0]["systems"]["N"]["history"].append([0, "x", []]), "O5")
    _tampered(lambda r: next(iter(r["events"][0]["systems"]["F_CF"]["interventions"]["frozen"].values())).update(weight=0.0042), "O5")
    _tampered(lambda r: r["events"][0]["systems"]["N_CF"].update(baseline_weights={}), "O5")
    _tampered(lambda r: r["events"][0]["systems"]["F_CF"]["baseline_weights"].update({AN.PLASTIC[0]: 0.0047}), "O5")   # 基準の改ざん
    _tampered(lambda r: [r["events"][0]["systems"][n]["baseline_weights"].update({AN.PLASTIC[0]: 0.0047})
                         for n in ("F_CF", "N_CF")], "O5")                       # 両方の基準を同じに書き換えても、凍結の参照・Pulse ごとの値と合わない


def _longest_cf_event(run) -> int:
    """CF の系の Pulse ごとの記録がいちばん長い出来事の番号（中間の Pulse の欠けを作るため。決定的に選ぶ）。"""
    lengths = [len(ev["systems"]["F_CF"]["pulse_weights"]) for ev in run["events"]]
    return max(range(len(lengths)), key=lambda i: (lengths[i], -i))


def test_o5_detects_a_missing_middle_pulse_or_a_changed_value_in_freeze() -> None:
    seed = first_with_events()
    base = measured(seed)
    k = _longest_cf_event(base["run"])
    assert len(base["run"]["events"][k]["systems"]["F_CF"]["pulse_weights"]) >= 3   # 中間の Pulse がある
    for f in (lambda rows: rows.pop(len(rows) // 2),                                  # 中間の Pulse の欠け
              lambda rows: rows[len(rows) // 2][1].update({next(iter(rows[0][1])): 0.0049}),   # 値の変更
              lambda rows: rows[len(rows) // 2][1].pop(next(iter(rows[0][1]))),       # 接続の欠け
              lambda rows: rows.__setitem__(len(rows) // 2, [rows[len(rows) // 2][0] + 1000, rows[len(rows) // 2][1]])):
        data = measured(seed)
        f(data["run"]["events"][k]["systems"]["N_CF"]["pulse_weights"])
        assert "O5" in failures(data, seed)


def test_o5_detects_a_missing_middle_pulse_in_fb1() -> None:
    seed = first_with_events()
    data = measured(seed)
    lengths = [len(ev["systems"]["F_FB"]["masked_weights"]) for ev in data["run"]["events"]]
    k = max(range(len(lengths)), key=lambda i: (lengths[i], -i))
    rows = data["run"]["events"][k]["systems"]["F_FB"]["masked_weights"]
    assert len(rows) >= 3
    rows.pop(len(rows) // 2)
    assert "O5" in failures(data, seed)


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
                          "body": {"intents": [[10, "d"]], "activity": [], "birth_units": {}}, "events": []})
    assert none["applicable"] is False and none["P_i"] is False                     # 出来事なし：N/A
    zeros = AN.individual({"plan": {"horizon": 60}, "roles": {"source": "s1"}, "body": {"intents": [[10, "d"], [20, "d"]], "activity": [], "birth_units": {}},
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


def test_analysis_of_the_synthetic_individuals_runs_through() -> None:
    runs = {s: measured(s) for s in SYN}
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=[])
    assert report["valid"] is True and set(report["judgment"]["J_A"]) >= {"m", "count_P_i", "status"}
    assert set(report["individuals"]) == {str(s) for s in SYN} and report["O1"]["status"] == "ok"


def test_an_invalid_individual_or_a_failed_o1_blocks_the_judgment() -> None:
    runs = {s: measured(s) for s in SYN}
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=["x"])
    assert report["valid"] is False and report["judgment"] is None and report["O1"]["status"] == "fail"
    s = first_with_events()
    runs[s]["run"]["events"][0]["n_pending"] = copy.deepcopy(runs[s]["run"]["events"][0]["body_pending"])
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=[])
    assert report["valid"] is False and report["judgment"] is None and str(s) in report["failed_checks"]


def test_meta_blind_must_match_the_mode() -> None:
    s = SYN[0]
    data = measured(s)
    data["meta"]["blind"] = "no"
    assert "structure" in failures(data, s)
    assert AN.check_seed(dict(measured(s), meta=dict(measured(s)["meta"], blind=True)), "synthetic", s, SMALL)["structure"] == []
    assert AN.check_seed(dict(measured(s), meta=dict(measured(s)["meta"], blind=True)), "formal", s, SMALL)["structure"]


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
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=[])
    assert report["valid"] is True and report["judgment"]["J_A"]["status"] == "inconclusive"   # 3 個体なので m ＜ 10


# ---- smoke の盲検（#150 のレビューの必須 1）：現象の数値を保存しない -------------------------------------------

# 盲検の記録・実行の記録に現れてはいけない欄（生の記録の欄と、判定の量）
FORBIDDEN_KEYS = ((AN.RUN_KEYS - {"seed", "plan", "roles"}) | AN.BODY_KEYS | AN.EVENT_KEYS | AN.SYSTEM_KEYS
                  | {"run", "s_e", "d_e", "n_plus", "n_minus", "P_i", "J_A", "judgment", "individuals", "R5_weights"})
META_KEYS = {"experiment", "kind", "mode", "seed", "measurement_commit", "protocol_sha256", "protocol", "manifest", "blind"}


def _keys(x, path=()):
    """JSON の値の中の、すべての (経路, 欄の名前)。meta の protocol・manifest（実行の前に決まっている定数）は見ない。"""
    if isinstance(x, dict):
        for k, v in x.items():
            yield path, k
            if path == ("meta",) and k in ("protocol", "manifest"):
                continue
            yield from _keys(v, path + (k,))
    elif isinstance(x, list):
        for v in x:
            yield from _keys(v, path)


ISO_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
NUMERIC_OK = {"seed", "raw_file_bytes", "max_workers", "pid"}       # 実行の記録に数値で残ってよい欄（時間の手がかりにならない）


def _numeric_keys(x, key=None):
    if isinstance(x, bool):
        return set()
    if isinstance(x, (int, float)):
        return {key}
    if isinstance(x, dict):
        return set().union(*(_numeric_keys(v, k) for k, v in x.items())) if x else set()
    if isinstance(x, list):
        return set().union(*(_numeric_keys(v, key) for v in x)) if x else set()
    return set()


def _blind_exec(repo, out, seeds, runner=None, workers=None):
    def factory(n):
        if workers is not None:
            workers.append(n)
        return SerialExecutor(n)
    return R.execute("synthetic", seeds, out, repo, _git(repo, "rev-parse", "HEAD"),
                     runner=runner or functools.partial(M.measure_seed, PROTOCOL, plan=SMALL),
                     executor_factory=factory, blind=True, check_plan=SMALL)


def _assert_no_timing(out: Path) -> None:
    """盲検の出力先から、seed ごとの実行の時間を戻せないこと（#150 の再レビュー 5692062243）：
    開始・終了の記録の時刻の欄は非公開の値、時刻の形の文字列も時間の数値もなく、ファイル・フォルダの時刻はすべて揃っている。"""
    for d in [out, *out.rglob("*")]:                                  # 読むと変わるアクセスの時刻は見ない（中身の更新の時刻を見る）
        assert d.stat().st_mtime == R.CONCEALED_MTIME, d
    for d in sorted((out / R.G.SEEDS_DIR).iterdir()):
        start = json.loads((d / R.G.START).read_text(encoding="utf-8"))
        finish = json.loads((d / R.G.FINISH).read_text(encoding="utf-8"))
        assert start["started_at"] == R.BLINDED_TIME and finish["finished_at"] == R.BLINDED_TIME
        assert finish["seconds"] is None and start["max_workers"] == 1
        for rec in (start, finish):
            assert not ISO_TIME.search(json.dumps(rec)), rec
            assert _numeric_keys(rec) <= NUMERIC_OK, _numeric_keys(rec)
        if (d / R.G.RAW).exists():
            raw = json.loads(gzip.decompress((d / R.G.RAW).read_bytes()))
            assert not ISO_TIME.search(json.dumps(raw["blind"])) and set(raw["meta"]) == META_KEYS


def test_blind_execution_stores_no_phenomenon_values(repo, tmp_path, monkeypatch, capsys) -> None:
    """smoke と同じ盲検の実行を合成の seed で行い、出力先のすべてのファイルに、現象の数値・判定の量が無いことを確かめる。"""
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    seeds = [first_with_events(), next(s for s in SYN if not measured(s)["run"]["events"]), SYN[-1]]
    workers: list[int] = []
    done = _blind_exec(repo, out, seeds, workers=workers)
    assert done["completed"] == sorted(seeds) and workers == [1]     # 盲検は 1 つずつ（終わる順を残さない）
    assert capsys.readouterr().out == ""                             # seed ごとの進み具合・時間を表示しない
    _assert_no_timing(out)
    assert AN.verify_records(out, "synthetic", sorted(seeds))["state"] == "complete"   # 非公開の時刻でも一度限りの記録として読める
    with pytest.raises(R.G.GuardError):
        _blind_exec(repo, out, seeds[:1])                            # 二度と始めない
    files = sorted(p for p in out.rglob("*") if p.is_file() and p != out / R.G.LOCK)
    assert (out / R.G.LOCK).read_bytes() == b""                 # 同時の実行を止める鍵のファイル（空）
    assert {p.name for p in files} == {R.G.START, R.G.FINISH, R.G.RAW} and len(files) == 3 * len(seeds)
    for p in files:
        data = json.loads(gzip.decompress(p.read_bytes()) if p.name.endswith(".gz") else p.read_bytes())
        bad = {k for _, k in _keys(data) if k in FORBIDDEN_KEYS}
        assert not bad, (p, bad)
        if p.name == R.G.FINISH:
            assert data["seconds"] is None                      # 実行の時間（出来事の多さの手がかり）も残さない
        if p.name == R.G.RAW:
            s = data["meta"]["seed"]
            assert set(data) == {"meta", "blind"} and set(data["meta"]) == META_KEYS and set(data["blind"]) == AN.BLIND_KEYS
            assert data["meta"]["protocol"] == json.loads(json.dumps(PROTOCOL)) and data["meta"]["manifest"] == M.manifest_raw()
            assert data["blind"]["checks"] == {k: "ok" for k in AN.CHECK_NAMES}
            # 整合の記録：メモリの中の生の記録（同じ計算をし直したもの）の SHA-256 と一致する（中身は戻せない）
            again = {"meta": data["meta"], "run": M.measure_seed(PROTOCOL, s, SMALL)}
            canonical = json.dumps(json.loads(json.dumps(again)), separators=(",", ":"), sort_keys=True).encode("utf-8")
            assert data["blind"]["raw_sha256"] == R.G.sha256_bytes(canonical)
            assert AN.check_blinded(data, s, "synthetic") == {k: "ok" for k in AN.CHECK_NAMES}


def test_blind_failure_keeps_no_timing_or_reason_text(repo, tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"

    def boom(seed: int) -> dict:
        if seed == GUARD_SEEDS[1]:
            raise RuntimeError("Pulse 1234：x")
        return M.measure_seed(PROTOCOL, seed, SMALL)
    with pytest.raises(R.G.GuardError) as err:
        _blind_exec(repo, out, GUARD_SEEDS[:3], runner=boom)
    assert "1234" not in str(err.value)
    statuses = {s: st for s, (st, _) in R.G.scan(out)["seeds"].items()}
    assert statuses == {GUARD_SEEDS[0]: "completed", GUARD_SEEDS[1]: "failed"}
    finish = json.loads((R.G.seed_dir(out, GUARD_SEEDS[1]) / R.G.FINISH).read_text(encoding="utf-8"))
    assert finish["reason"] == "RuntimeError"                        # 例外の文（Pulse の番号）を残さない
    assert all("1234" not in p.read_bytes().decode("utf-8", "replace") for p in out.rglob("*") if p.is_file())
    assert capsys.readouterr().out == ""
    _assert_no_timing(out)


def test_non_blind_runs_keep_real_times(repo, tmp_path, monkeypatch) -> None:
    """本番の形（盲検でない）では、これまでどおり時刻・時間・並列数を残す（盲検の扱いは smoke にだけ効く）。"""
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    _exec(repo, out, GUARD_SEEDS[:1])
    d = R.G.seed_dir(out, GUARD_SEEDS[0])
    start = json.loads((d / R.G.START).read_text(encoding="utf-8"))
    finish = json.loads((d / R.G.FINISH).read_text(encoding="utf-8"))
    assert ISO_TIME.match(start["started_at"]) and ISO_TIME.match(finish["finished_at"])
    assert isinstance(finish["seconds"], float) and start["max_workers"] == R.MAX_WORKERS
    assert (d / R.G.START).stat().st_mtime != R.CONCEALED_MTIME


def test_blinded_record_marks_a_failed_check_without_reasons() -> None:
    s = first_with_events()
    data = measured(s)
    data["meta"]["blind"] = True
    data["run"]["events"][0]["n_pending"] = copy.deepcopy(data["run"]["events"][0]["body_pending"])
    rec = R.blinded(data, "synthetic", s, SMALL)
    assert set(rec) == {"meta", "blind"} and set(rec["blind"]) == AN.BLIND_KEYS
    assert rec["blind"]["checks"]["O4"] == "fail" and set(rec["blind"]["checks"].values()) <= {"ok", "fail"}


def test_smoke_report_reads_blinded_records_and_rechecks_o6() -> None:
    s = SYN[0]
    data = measured(s)
    data["meta"]["blind"] = True
    rec = R.blinded(data, "synthetic", s, SMALL)
    rec["meta"]["mode"] = "smoke"
    report = AN.analyze_runs({s: rec}, "smoke", o1=[])
    assert set(report) == {"mode", "O1", "checks", "valid"} and report["O1"] == "ok"
    assert report["checks"][str(s)]["O6"] == "fail" and report["valid"] is False        # 合成の seed は smoke の範囲の外
    assert {v for k, v in report["checks"][str(s)].items() if k != "O6"} == {"ok"}
    broken = copy.deepcopy(rec)
    broken["blind"]["extra"] = 1
    assert AN.check_blinded(broken, s, "smoke") == {k: "fail" for k in AN.CHECK_NAMES}
    leaked = dict(copy.deepcopy(rec), run=data["run"])                                    # 生の記録を混ぜた記録は通さない
    assert AN.check_blinded(leaked, s, "smoke") == {k: "fail" for k in AN.CHECK_NAMES}
    assert AN.analyze_runs({s: rec}, "smoke", o1=["x"])["O1"] == "fail"


def test_smoke_must_be_blind_and_formal_must_not(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    commit = _git(repo, "rev-parse", "HEAD")
    for mode, kw in (("smoke", {"blind": False}), ("formal", {"blind": True}), ("smoke", {"check_plan": SMALL}),
                     ("formal", {"check_plan": SMALL})):
        out = tmp_path / f"o_{mode}_{len(kw)}_{sorted(kw)[0]}"
        with pytest.raises(R.G.GuardError):                     # seed に触れる前に止まる（seed は合成の範囲のもの）
            R.execute(mode, GUARD_SEEDS[:1], out, repo, commit, runner=_dummy, executor_factory=SerialExecutor, **kw)
        assert not out.exists()


# ---- O1 の証拠（測定の commit で契約テストを実際に走らせた記録） ---------------------------------------------

class _Proc:
    def __init__(self, code: int, stdout: str) -> None:
        self.returncode, self.stdout = code, stdout


def _o1_repo(repo: Path) -> str:
    for f in AN.CONTRACT_TESTS:
        (repo / f).parent.mkdir(parents=True, exist_ok=True)
        (repo / f).write_text(f"# {f}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "tests")
    return _git(repo, "rev-parse", "HEAD")


def test_o1_records_the_real_contract_test_run_once(repo, tmp_path, monkeypatch) -> None:
    commit = _o1_repo(repo)
    monkeypatch.setattr(AN, "REPO", repo)
    calls = []

    def ok(cmd, **kw):
        calls.append((cmd, kw["cwd"]))
        return _Proc(0, "....\n150 passed in 9.0s\n")
    out = tmp_path / "out"
    rec = R.record_contract_tests(repo, out, commit, run=ok)
    assert rec["exit_code"] == 0 and rec["summary"] == "150 passed in 9.0s" and calls[0][1] == repo
    assert calls[0][0][1:] == ["-m", "pytest", "-q", *AN.CONTRACT_TESTS]
    assert AN.o1_check(out, commit) == []
    R.record_contract_tests(repo, out, commit, run=lambda *a, **k: pytest.fail("走らせ直さない"))
    assert AN.o1_check(out, "0" * 40)                                  # 別の commit の記録としては通らない
    with pytest.raises(R.G.GuardError):
        R.record_contract_tests(repo, out, "0" * 40, run=ok)


def test_o1_failure_or_tampering_is_detected(repo, tmp_path, monkeypatch) -> None:
    commit = _o1_repo(repo)
    monkeypatch.setattr(AN, "REPO", repo)
    out = tmp_path / "out"
    assert AN.o1_check(out, commit)                                    # 記録がない
    with pytest.raises(R.G.GuardError):
        R.record_contract_tests(repo, out, commit, run=lambda *a, **k: _Proc(1, "1 failed, 149 passed in 9.0s\n"))
    assert AN.o1_check(out, commit)                                    # 通らなかった記録
    with pytest.raises(R.G.GuardError):
        R.record_contract_tests(repo, out, commit, run=lambda *a, **k: _Proc(0, "150 passed\n"))   # 書き直さない
    out2 = tmp_path / "out2"
    R.record_contract_tests(repo, out2, commit, run=lambda *a, **k: _Proc(0, "150 passed in 9.0s\n"))
    path = out2 / AN.O1_FILE
    good = json.loads(path.read_text(encoding="utf-8"))
    for tamper in (lambda r: r.update(exit_code=2), lambda r: r.update(summary="2 failed, 148 passed"),
                   lambda r: r["test_files_sha256"].update({AN.CONTRACT_TESTS[0]: "0" * 64}),
                   lambda r: r.update(command=["python", "-m", "pytest", "-q"]), lambda r: r.pop("at")):
        bad = copy.deepcopy(good)
        tamper(bad)
        path.write_text(json.dumps(bad), encoding="utf-8")
        assert AN.o1_check(out2, commit), bad
    (repo / AN.CONTRACT_TESTS[1]).write_text("# changed\n", encoding="utf-8")         # テストのファイルが測定の commit と違う
    path.write_text(json.dumps(good), encoding="utf-8")
    assert AN.o1_check(out2, commit)
    with pytest.raises(R.G.GuardError):                                # 作業ツリーが汚れていれば走らせない
        R.record_contract_tests(repo, tmp_path / "out3", commit, run=lambda *a, **k: _Proc(0, "1 passed\n"))


# ---- 結果の写し（guard の形 → results/）の照合 ------------------------------------------------------------

def test_results_copy_is_verified_byte_for_byte(repo, tmp_path, monkeypatch) -> None:
    import shutil
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    _exec(repo, out, GUARD_SEEDS[:2])
    (out / AN.REPORT).write_text(json.dumps({"measurement_commit": _git(repo, "rev-parse", "HEAD")}), encoding="utf-8")

    def copy_to(name: str) -> Path:
        dst = tmp_path / name
        shutil.copytree(out, dst, ignore=shutil.ignore_patterns(R.G.LOCK))
        return dst
    assert AN.verify_results_copy(out, copy_to("ok")) == []
    swap = copy_to("swap")
    a, b = (R.G.seed_dir(swap, s) / R.G.RAW for s in GUARD_SEEDS[:2])
    da, db = a.read_bytes(), b.read_bytes()
    a.write_bytes(db)
    b.write_bytes(da)
    assert AN.verify_results_copy(out, swap)                              # seed の取り違え
    gone = copy_to("gone")
    (R.G.seed_dir(gone, GUARD_SEEDS[1]) / R.G.RAW).unlink()
    assert AN.verify_results_copy(out, gone)                              # 欠け
    extra = copy_to("extra")
    (extra / "note.txt").write_text("x", encoding="utf-8")
    assert AN.verify_results_copy(out, extra)                             # 余分なファイル
    rep = copy_to("rep")
    (rep / AN.REPORT).write_text(json.dumps({"measurement_commit": "0" * 40}), encoding="utf-8")
    assert AN.verify_results_copy(out, rep)


# ---- R4・R5 の report の欄（監査 029）。判定は、欄を足す前（測定の commit 候補 b831d9a）の analyze.py と同じ --------------

BEFORE_R4_R5 = "b831d9ab65c0024e80a1d0b4b960ca4ed12ed2d1"
JUDGMENT_KEYS = ("applicable", "n_plus", "n_minus", "n_zero", "n_unknown", "P_i", "events_in_window", "fraction_nonzero",
                 "median_d_e", "B", "FB", "events")


@functools.lru_cache(maxsize=None)
def _analyze_before():
    """欄を足す前の analyze.py（git の履歴から読む。ほかの道具は今のものを使う：この変更で analyze.py のほかは変えていない）。"""
    src = subprocess.run(["git", "-C", str(ROOT), "show", f"{BEFORE_R4_R5}:experiments/0034_as1_feedback_next_intent/analyze.py"],
                         capture_output=True, text=True, check=True).stdout
    import types
    module = types.ModuleType("analyze_0034_before_r4_r5")
    module.__file__ = str(EXP / "analyze.py")
    exec(compile(src, f"analyze.py@{BEFORE_R4_R5[:7]}", "exec"), module.__dict__)
    return module


def test_only_analyze_changed_since_the_previous_candidate() -> None:
    """欄を足す前の候補から変えた道具は analyze.py だけ（測定・実行・照合の道具、AS1 の道具、Core は同じ）。"""
    tools = [f"experiments/0034_as1_feedback_next_intent/{f}" for f in ("measure.py", "run.py", "guard.py", "alignment.py",
                                                                         "README.md", "protocol.yaml")]
    changed = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", BEFORE_R4_R5, "--", *tools,
                              "experiments/as1_closed_loop", "src"], capture_output=True, text=True, check=True).stdout.split()
    assert changed == [], changed


def _both_reports(runs, plan):
    return AN.analyze_runs(runs, "synthetic", plan, o1=[]), _analyze_before().analyze_runs(runs, "synthetic", plan, o1=[])


def test_judgment_is_unchanged_by_the_r4_r5_fields() -> None:
    """合成の個体（SMALL の 10 個体と、本番の Plan の個体）で、主の判定・個体ごとの判定の欄・R5 の重みと組の和が、欄を足す前と
    同じであること（値は見ずに、同じかどうかだけを確かめる）。"""
    seed, text = _formal_synthetic()
    for runs, plan in (({s: measured(s) for s in SYN}, SMALL), ({seed: json.loads(text)}, M.formal_plan(PROTOCOL))):
        new, old = _both_reports(runs, plan)
        assert new["valid"] is old["valid"] is True
        assert new["judgment"] == old["judgment"]
        for s in new["individuals"]:
            a, b = new["individuals"][s], old["individuals"][s]
            assert {k: a[k] for k in JUDGMENT_KEYS} == {k: b[k] for k in JUDGMENT_KEYS}
            assert a["intervals"]["whole_run"] == b["intervals"]                # 全期間の間隔は、名前を分けただけ
        for s in new["R5_weights"]:
            for p in new["R5_weights"][s]:
                x, y = new["R5_weights"][s][p], old["R5_weights"][s][p]
                assert (x["weights"], x["pair_sums"]) == (y["weights"], y["pair_sums"])


def test_r4_r5_fields_come_from_the_raw_record() -> None:
    runs = {s: measured(s) for s in SYN}
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=[])
    for s, data in runs.items():
        run, ind = data["run"], report["individuals"][str(s)]
        assert ind["roles"] == run["roles"] and ind["birth_units"] == run["body"]["birth_units"]
        fires = [p for p, u in run["body"]["activity"] if u == run["roles"]["source"]]
        window = sorted(ev["t"] for ev in run["events"])
        assert ind["source_fires"] == {"whole_run": len(fires), "intents_in_window": len(window)}
        assert ind["source_fires"]["intents_in_window"] == ind["events_in_window"]
        assert ind["intervals"]["window"] == AN._interval_summary(window)
        assert ind["intervals"]["whole_run"] == AN._interval_summary(fires)
        if len(window) >= 2:                                                   # 区間 W の間隔は W の意図だけから
            assert ind["intervals"]["window"]["count"] == len(window) - 1
        for p, st in run["body"]["checkpoints"].items():
            r5 = report["R5_weights"][str(s)][p]
            assert set(r5) == {"weights", "traces", "pair_sums"} and sorted(r5["traces"]) == sorted(st)
            assert all(r5["traces"][c] == {"pre_trace": v["pre_trace"], "post_trace": v["post_trace"]} for c, v in st.items())
    assert any(report["individuals"][str(s)]["intervals"]["window"] is None for s in SYN)   # W に意図が 2 つ未満の個体もある


def test_window_is_on_the_consequence_pulse_and_intents_are_its_causes() -> None:
    """区間 W は結果の予約 e の Pulse で定める（README §2）。R4 の「W の意図」は、その e の原因の意図の Pulse t（＝ e の Pulse − (L − 1)）。
    両者を混同しないこと：L が一定なので、意図どうしの間隔と e どうしの間隔は同じ。"""
    lag = PROTOCOL["world"]["delay_L"] - 1
    for s in SYN:
        data = measured(s)
        run = data["run"]
        e_pulses = sorted(ev["e"]["pulse"] for ev in run["events"])
        assert all(SMALL.window_first <= p <= SMALL.window_last for p in e_pulses)
        assert all(ev["e"]["pulse"] == ev["t"] + lag for ev in run["events"])
        ind = AN.individual(run)
        assert ind["intervals"]["window"] == AN._interval_summary(e_pulses)


def test_interval_summary_definition() -> None:
    assert AN._interval_summary([]) is None and AN._interval_summary([5]) is None
    assert AN._interval_summary([3, 10, 12, 30]) == {"count": 3, "min": 2, "median": 7, "max": 18}
