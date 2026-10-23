"""実験 0030 の道具の契約テスト（確定した事前登録 v0.1 の README §0〜§14、protocol.yaml）。

本番の seed（23001〜23020）・smoke の seed（23101〜23106）は使わない（実行もしない）。合成の契約テスト専用の範囲
（23201〜23299）だけを使う。合成の個体は、本番と同じ道具（world.measure_seed）・同じ式で、値だけを小さくした Plan
（SMALL：試行 3、遅れ 30。主の区間の長さは式どおり 3 × 60 ＝ 180、T_0 の窓は式どおり最後の刺激 151 の次〜経験の終わり 180 の
152〜180。試行の数・遅れは 0028 の契約テストと同じ値）で実物の runtime を通して作る。結果を見て Plan・seed を選んでいない
（seed は範囲の最初から順に使う）。

T_0 がない個体（README §2.6）の契約テストのためだけに、SMALL の T_0 の窓を 1 Pulse に狭めた Plan（NOTAU）も使う。その Pulse は、
23201 の SMALL の自然な本体が窓の中で発火した Pulse のうち最後のもの（176。どれかの本体が発火した Pulse なので、23201 では T_0 が
なくなる）。最初の発火の Pulse（152）は最後の刺激の直後で、どの合成の個体でも発火があり T_0 のない個体しか作れないので、最後のもの
にした（開示）。自然な本体の軌道は窓に依らないので、同じ seed の自然な本体は SMALL と NOTAU で同じになる。NOTAU の 20 個体には、
T_0 がない個体と T_0 がある個体が両方含まれることを確かめてから使う（片方しかなければテストが失敗する）。

使った合成の seed（PR に開示）：
- 23201〜23220：SMALL と NOTAU の Plan で実物の runtime を通した 20 個体ずつ（確認の再検証・改ざんの検出・合成の集計の通し）
- 23221〜23240：一度限りの実行の契約（dummy の計算。runtime を使わない）
- 23241〜23250：並列数の契約（実際のプロセス。dummy の計算）
- 23299：可塑性の再生の照合と、命題 3 の性質の確かめに使う乱数の流れの名前だけ（runtime の個体は作らない）
- 本番の Plan（試行 200）での W の札の列の作り方の確認には 23201〜23206 の名前を使う（札の列を作るだけで、runtime の個体は作らない）

ご指示の点（ChatGPT のレビュー #5619411359 の後の指示）：F の組み立てと R(O) の再現（§4）、T_0 がある・ない両方の分かれ道（§4・§5）、
N^cnt の境界の条件（§6）、raw の再検証（§4・§5・§9）、smoke の盲検（§9）を、実物の runtime で確かめる。
"""

import copy
import dataclasses
import functools
import gzip
import importlib.util
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import Future
from fractions import Fraction
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments" / "0030_post_experience_freeze_and_count_bound"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))
PREREGISTRATION_MERGE = "084ed38d447ef41d0fbb495a5ff6c1f9da731998"   # PR #130 のマージ（README・protocol の確定）
SYN = list(range(23201, 23221))
GUARD_SEEDS = list(range(23221, 23241))
POOL_SEEDS = list(range(23241, 23251))
TOOLS = ("world.py", "run.py", "analyze.py", "alignment.py", "guard.py")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W = _load("world_0030_test", EXP / "world.py")
G = _load("guard_0030_test", EXP / "guard.py")
A = _load("analyze_0030_test", EXP / "analyze.py")
R = _load("run_0030_test", EXP / "run.py")
sys.modules[R.__name__] = R          # 実際のプロセスへ compute_and_write を渡すため（本番では run.py が __main__）
ALIGN = _load("alignment_0030_test", EXP / "alignment.py")
SMALL = W.make_plan(PROTOCOL, 3, 30)
# run.py・analyze.py はそれぞれ guard.py を読み込むので、GuardError のクラスは 3 つある（どれも同じ契約の拒否）
ERR = (G.GuardError, R.G.GuardError, A.G.GuardError)
UNITS = ("s1", "s2", "s3")


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)


class SerialExecutor:
    """契約テスト用：submit をその場で実行する（並列にしない）。"""

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


def _raw(run: dict, mode: str = "synthetic", commit: str | None = None, sha: str | None = None) -> dict:
    """run.py が書くのと同じ形の生の記録（JSON を通して、保存したものと同じ値の型にする）。"""
    meta = {"experiment": PROTOCOL["experiment"], "kind": PROTOCOL["kind"], "mode": mode, "seed": run["seed"],
            "measurement_commit": commit, "protocol_sha256": sha, "protocol": PROTOCOL, "manifest": W.manifest_raw(PROTOCOL)}
    return json.loads(json.dumps({"meta": meta, "run": run}))


@pytest.fixture(scope="module")
def syn() -> dict:
    return _raw(W.measure_seed(PROTOCOL, SYN[0], SMALL))


@functools.cache
def notau_plan() -> "W.Plan":
    """SMALL の T_0 の窓を、23201 の SMALL の自然な本体が窓の中で発火した最後の Pulse の 1 つに狭めた Plan（T_0 がない個体を作るため）。"""
    run = W.measure_seed(PROTOCOL, SYN[0], SMALL)
    lo, hi = SMALL.freeze_window
    fired = sorted({p for rec in run["natural_bodies"].values() for ps in rec["spikes"].values() for p in ps if lo <= p <= hi})
    assert fired, "SMALL の T_0 の窓に、23201 の自然な本体の発火がない"
    return dataclasses.replace(SMALL, freeze_window=(fired[-1], fired[-1]))


@pytest.fixture(scope="module")
def notau() -> dict:
    return _raw(W.measure_seed(PROTOCOL, SYN[0], notau_plan()))


def _checks(data: dict, seed: int = SYN[0], plan=SMALL) -> dict:
    return {k: v for k, v in A.check_seed(data, "synthetic", seed, plan).items() if v}


def _tampered(data, f, plan=SMALL, seed=SYN[0]) -> dict:
    data = copy.deepcopy(data)
    f(data["run"])
    return _checks(data, seed, plan)


def _f(run, b: str) -> dict:
    return next(r for r in run["f_bodies"] if r["original_body"] == b)


def _diverging_f(run) -> str:
    """F 本体の発火の列が、自然な本体の T_0 より後の発火の列と違う本体（可塑性を止めたことが軌道を変えた本体）。"""
    t0 = run["freeze"]["t0"]
    for b in W.BODIES:
        nat = {u: [p for p in ps if p > t0] for u, ps in run["natural_bodies"][b]["spikes"].items()}
        if {u: ps for u, ps in nat.items() if ps} != {u: ps for u, ps in _f(run, b)["spikes"].items() if ps}:
            return b
    raise AssertionError("どの F 本体も自然な本体と同じ軌道")


# ---- 1. protocol と道具の対応・固定 -------------------------------------------------------------------------------

def test_protocol_and_tools_are_aligned() -> None:
    ALIGN.check(PROTOCOL)


def _git_show(rev: str, path: str) -> bytes:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{path}"], capture_output=True, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git の履歴がない環境")


def test_preregistration_files_are_unchanged_since_the_merge() -> None:
    """protocol.yaml は事前登録の確定（PR #130 のマージ）からバイト単位で変わっていない。README は確定した §0〜§14 が
    そのまま先頭に残っている（結果は後ろの節に追記する：README §14 の 4）。"""
    rel = f"experiments/{EXP.name}"
    assert (EXP / "protocol.yaml").read_bytes() == _git_show(PREREGISTRATION_MERGE, f"{rel}/protocol.yaml")
    assert (EXP / "README.md").read_bytes().startswith(_git_show(PREREGISTRATION_MERGE, f"{rel}/README.md"))


def test_runtime_core_and_other_experiments_are_unchanged_from_main() -> None:
    """0030 の道具を変える branch では、本体（src/）・設計（config/）・ほかの実験・0030 の事前登録の文書を同時に変えない
    （main との差分）。0030 の道具を変えない branch（後の PR）では確かめない（この PR の範囲の確認なので、後の作業を止めない）。"""
    try:
        base = subprocess.run(["git", "-C", str(ROOT), "merge-base", "HEAD", "origin/main"], capture_output=True,
                              text=True, check=True).stdout.strip()
        diff = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", base, "--", "src", "config", "experiments"],
                              capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git の履歴がない環境")
    tools = {f"experiments/{EXP.name}/{n}" for n in TOOLS}
    if not set(diff) & tools:
        pytest.skip("この branch は 0030 の道具を変えていない")
    assert set(diff) <= tools, sorted(set(diff) - tools)


FORBIDDEN = [r'"00(0\d|1\d|2\d)"', r"'00(0\d|1\d|2\d)'", r"data/experiments/00(0\d|1\d|2\d)",
             r"00(0\d|1\d|2\d)-(shuffle|within)", r"experiments/00(1[3-9]|2\d)_",
             r"experiments/0012_passive_world/(?!neuroarchitecture\.yaml)",
             r"(world|guard|run|analyze|alignment)_00(0\d|1\d|2\d)"]
SEED_NUMBERS = r"\b(1[3-9]|2[0-2])[0-2]\d\d\b"   # 0020〜0029 の seed の範囲（13001〜22299）の数


def _code(name: str) -> str:
    """道具のコード（説明の文字列・コメントは除く。alignment.py の使用済みの seed の一覧 SEEN と、protocol を写した固定値の文字列は
    重なりの確認・照合の記録なので除く）。"""
    src = (EXP / name).read_text(encoding="utf-8")
    src = re.sub(r"SEEN = \(.*?\)\)\)\n", "", src, flags=re.DOTALL)
    src = re.sub(r'""".*?"""', "", src, flags=re.DOTALL)
    return "\n".join(line.split("#")[0] for line in src.splitlines())


def test_tools_hold_no_earlier_experiment_references() -> None:
    """道具は、ほかの実験の ID・出力先・乱数の流れの名前・道具（world.py など）を参照しない。0023〜0029 の道具も読み込まない。
    脳の設計図は protocol の brain.manifest（0014〜0029 と同じ共有の設計図）だけを読み、alignment.py がその名前を確かめる。"""
    for name in TOOLS:
        code = _code(name)
        for pat in FORBIDDEN:
            assert not re.search(pat, code), (name, pat)
        assert "_load(" not in code or all("experiments/" not in line for line in code.splitlines() if "_load(" in line), name
        assert not re.search(SEED_NUMBERS, code), (name, "0020〜0029 の seed の範囲の数")


def test_the_reference_scan_detects_leftovers() -> None:
    for leftover in ('EXPERIMENT = "0029"', 'OUT = "data/experiments/0029"', 'RNG = "0029-within-trial-{i}:{seed}"',
                     '_load("w", ROOT / "experiments/0029_window_start_block_swap/world.py")',
                     '"experiments/0028_lag1_successor_asymmetry/world.py"', '"experiments/0012_passive_world/world.py"',
                     "world_0029_for_x", "guard_0026"):
        assert any(re.search(p, leftover) for p in FORBIDDEN), leftover
    for leftover in ("SEEDS = range(22001, 22021)", "SYN = range(22201, 22251)", "seed = 21101", "x = 13001"):
        assert re.search(SEED_NUMBERS, leftover), leftover
    for fine in ("first = 13501", "end = 25500", "lo = 11972", "hi = 12000", "seed = 23001"):
        assert not re.search(SEED_NUMBERS, fine), fine
    src = (EXP / "alignment.py").read_text(encoding="utf-8")
    assert "range(22001" in src and "range(22001" not in _code("alignment.py") and {22001, 22299, 21299, 20299} <= ALIGN.SEEN


def test_tools_read_identity_from_this_protocol() -> None:
    ex = PROTOCOL["execution"]
    assert R.EXPERIMENT == A.EXPERIMENT == W.EXPERIMENT == PROTOCOL["experiment"] == ex["experiment_id"] == "0030"
    assert str(R.OUT_DIR) == str(A.DEFAULT_DIR) == ex["output_dir"]
    assert str(R.PROTOCOL_PATH) == str(A.PROTOCOL_PATH) == str(W.PROTOCOL_PATH) == ex["protocol_path"]
    assert W.RNG_SHUFFLE == PROTOCOL["conditions"]["within_trial_shuffles"]["rng"] == "0030-within-trial-{i}:{seed}"
    assert PROTOCOL["brain"]["manifest"] == "experiments/0012_passive_world/neuroarchitecture.yaml"
    for mode, key in (("formal", "seeds"), ("smoke", "smoke_seeds"), ("synthetic", "synthetic_seeds")):
        assert list(R.allowed_seeds(mode)) == A.expected_seeds(mode) == list(
            range(PROTOCOL[key]["first"], PROTOCOL[key]["last"] + 1))


def test_tools_use_only_public_core_interfaces() -> None:
    """README §2.4：F の変種は設計図の値と Core の公開の import_state だけで作る。道具のコードは Core の内部の欄に触れず、
    可塑性の振幅（amplitude_ratio）を変えない。"""
    for name in TOOLS:
        code = _code(name)
        assert not re.search(r"\._(state|plastic|weights|keys|spec|rule|dynamics|output|brain_state|pulse)\b", code), name
        assert "amplitude_ratio" not in code, name
    code = _code("world.py")
    assert "u.import_state(" in code and "app.connections.import_state(" in code


# ---- 2. Plan・刺激・T_0 の窓（README §1・§2）--------------------------------------------------------------------------

def test_plan_from_protocol_is_the_registered_timeline() -> None:
    """本番の Plan：経験の終わり 12000、最後の刺激 11971、遅れ 1500、T_0 の窓 11972〜12000（0026 の T の窓と同じ式）、主の区間
    13501〜25500、本体の終わり 25500。全状態を残す時点は自然な本体 12000・T_0・13500・25500、F 本体・R(O) 13500・25500。"""
    p = W.plan_from(PROTOCOL)
    assert (p.trials, p.experience_end, p.last_stimulus, p.delay, p.freeze_window, p.main, p.body_end) == (
        200, 12000, 11971, 1500, (11972, 12000), (13501, 25500), 25500)
    assert p.pre_main == 13500 and list(p.snapshots) == [12000, 13500, 25500] and list(p.rebuilt_snapshots) == [13500, 25500]
    num = PROTOCOL["checks"]["numeric"]["replay_weights_and_traces"]
    assert num["natural_at"] == [12000, "T0", 13500, 25500] and num["rebuild_control_at"] == list(p.rebuilt_snapshots)
    assert W.plan_of(p.as_dict()) == p and p.first_stimulus == (1, 2)
    assert (SMALL.experience_end, SMALL.last_stimulus, SMALL.freeze_window, SMALL.main, SMALL.body_end) == (
        180, 151, (152, 180), (211, 390), 390)
    assert max(t for t, _ in W.ordered_labels(PROTOCOL, p)) == p.last_stimulus


def test_make_plan_refuses_wrong_formulas_and_windows() -> None:
    for edit in (lambda p: p["timeline"]["count_window_main"].update(first="experience_end + 1"),
                 lambda p: p["timeline"]["freeze_window"].update(first="last_stimulus"),
                 lambda p: p["timeline"]["freeze_window"].update(last="experience_end + 1"),
                 lambda p: p["timeline"].update(last_stimulus="trials.first + trials.count * trials.every"),
                 lambda p: p["timeline"].update(body_runs_to="freeze_window.last"),
                 lambda p: p["timeline"].update(delay="3 * adaptation_tau / pulse_interval_seconds")):
        protocol = copy.deepcopy(PROTOCOL)
        edit(protocol)
        with pytest.raises(ValueError):
            W.plan_from(protocol)
    for window in ((151, 160), (170, 181), (175, 174)):          # 最後の刺激を含む・経験の後に出る・空
        with pytest.raises(ValueError):
            W.check_plan(dataclasses.replace(SMALL, freeze_window=window))
    with pytest.raises(ValueError):
        W.measure_seed(PROTOCOL, SYN[0], dataclasses.replace(SMALL, freeze_window=(140, 160)))


def _balanced(labels, plan) -> bool:
    at = dict(labels)
    return all(sorted(at.get(t, "") for t in slots) == ["A", "B", "C"] for slots in W.trial_slots(PROTOCOL, plan))


def test_schedules_follow_the_protocol() -> None:
    """O・M・W_i（0025・0027〜0029 と同じ作り方：1 本の乱数の流れで、試行の順に [A, B, C] を 1 回ずつ並べ替えて 3 つの枠に置く）。
    W は 19（すべて参照）。"""
    plan = W.plan_from(PROTOCOL)
    o = W.ordered_labels(PROTOCOL, plan)
    m = W.labels_of(PROTOCOL, plan, SYN[0], "M")
    assert len(o) == 600 and o[:3] == [(1, "A"), (3, "B"), (31, "C")] and o[-1] == (11971, "C") and _balanced(o, plan)
    assert m[:3] == [(1, "A"), (3, "C"), (31, "B")] and [t for t, _ in m] == [t for t, _ in o] and _balanced(m, plan)
    for seed in SYN[:6]:
        seen = set()
        for i in range(1, 20):
            w = W.labels_of(PROTOCOL, plan, seed, f"W{i}")
            rnd, expected = random.Random(f"0030-within-trial-{i}:{seed}"), []
            for k in range(200):
                roles = ["A", "B", "C"]
                rnd.shuffle(roles)
                t = 1 + 60 * k
                expected += [(t, roles[0]), (t + 2, roles[1]), (t + 30, roles[2])]
            assert w == expected and [t for t, _ in w] == [t for t, _ in o] and _balanced(w, plan) and w not in (o, m)
            seen.add(tuple(x for _, x in w))
        assert len(seen) == 19
    assert W.BODIES == ("O", "M") + tuple(f"W{i}" for i in range(1, 20)) and W.REFERENCE == W.BODIES[2:]


def test_alignment_refuses_drift() -> None:
    cases = {
        "時間の流れ": [lambda p: p["timeline"].update(delay="10 * adaptation_tau / pulse_interval_seconds"),
                      lambda p: p["timeline"]["freeze_window"].update(first="last_stimulus + 2")],
        "条件": [lambda p: p["conditions"].pop("M"),
                 lambda p: p["conditions"]["within_trial_shuffles"].update(count=20),
                 lambda p: p["conditions"].update(swaps="weights"),
                 lambda p: p["conditions"]["within_trial_shuffles"].update(rng="0030-shuffle-{i}:{seed}")],
        "F の変種": [lambda p: p["f_variant"].update(plastic_connections="six_s_to_s"),
                    lambda p: p["f_variant"].update(connection_state="copied"),
                    lambda p: p["f_variant"]["rebuild_control"].update(expected="none")],
        "T_0": [lambda p: p["freeze"]["time"]["no_t0"].update(ncnt="not_outside"),
                lambda p: p["freeze"]["reference_bodies"].pop()],
        "判定の決まり": [lambda p: p["judgment"]["per_family"]["Ncnt"]["J_Ca"].update(holds_if="h_Ca >= 3"),
                         lambda p: p["judgment"]["per_family"]["F"]["J_OM"].update(per_individual_null_probability_at_most="2/420"),
                         lambda p: p["judgment"]["families"]["F"].update(direction="two_sided"),
                         lambda p: p["judgment"]["per_family"]["alpha_split"].update(J_Ca=0.02),
                         lambda p: p["judgment"]["no_t0_individuals"].update(Ncnt_events="false"),
                         lambda p: p["judgment"].update(experiment_wide_error_rate_claimed="0.05")],
        "主・補助の量": [lambda p: p["quantities"]["primary"]["per_individual"]["Ncnt"].pop("E_OM_cnt"),
                         lambda p: p["quantities"]["primary"]["per_individual"]["Ncnt"].update(
                             E_Ca_cnt="for all i: Delta_AB(O) - Delta_AB(W_i) >= |N_A(O) - N_A(W_i)| + |N_B(O) - N_B(W_i)|"),
                         lambda p: p["quantities"]["not_used"].remove("Ncnt_form_on_F_bodies")],
        "記録の項目": [lambda p: p["records"].update(no_judgment_quantities_in_raw=False),
                       lambda p: p["records"]["no_t0"].update(f_bodies=None)],
        "操作の確認": [lambda p: p["checks"]["no_t0"]["not_applicable"].append("no_clipping"),
                       lambda p: p["checks"]["exact"].remove("rebuild_identity"),
                       lambda p: p["checks"].update(smoke_report_check_values=["fail", "pass", "not_applicable"])],
        "seed": [lambda p: p.update(seeds={"first": 22001, "last": 22020})],
    }
    for what, edits in cases.items():
        for edit in edits:
            protocol = copy.deepcopy(PROTOCOL)
            edit(protocol)
            with pytest.raises((SystemExit, ValueError)) as e:
                ALIGN.check(protocol)
            assert e.type is not SystemExit or "ずれている" in str(e.value), (what, str(e.value))


def test_roles_cycle_through_the_six_orders() -> None:
    orders = {tuple(W.role_receptors(PROTOCOL, s).values()) for s in SYN[:6]}
    assert len(orders) == 6


# ---- 3. T_0 の規則・根拠・F の変種の設計図（README §2.2・§2.4・§2.6）--------------------------------------------------

def test_find_freeze_time_is_the_last_quiet_pulse_of_the_window() -> None:
    lo, hi = 10, 20
    sp = {"O": {"s1": [11, 18]}, "M": {"s2": [19, 20]}}
    assert W.find_freeze_time(sp, lo, hi) == 17
    full = {"O": {"s1": list(range(lo, hi + 1, 2))}, "W3": {"s3": list(range(lo + 1, hi + 1, 2))}}
    assert W.find_freeze_time(full, lo, hi) is None
    assert W.find_freeze_time({"O": {}}, lo, hi) == hi


def test_window_witness_is_the_first_firing_in_the_fixed_order() -> None:
    sp = {"O": {"s3": [10]}, "M": {"s1": [10, 11]}, "W1": {"s2": [11, 12], "s1": [12]}}
    assert W.window_witness(sp, UNITS, 10, 12) == [
        {"pulse": 10, "body": "O", "unit": "s3"}, {"pulse": 11, "body": "M", "unit": "s1"},
        {"pulse": 12, "body": "W1", "unit": "s1"}]
    with pytest.raises(ValueError):                    # 発火のない Pulse があれば T_0 がある（根拠を作らない）
        W.window_witness(sp, UNITS, 10, 13)


def test_f_variant_removes_only_the_six_plastic_flags_and_sets_the_weights() -> None:
    """README §2.4：C0 の設計図の値から、s のあいだの 6 本の plastic: true だけを除き、weight を替える。ほかの値・配線は同じ。
    読み込みで拒まれない（可塑的でない接続の weight は有限の値なら受け付けられる）。Unit の並びは C0 と同じ。"""
    from anima_ll.adapter.config.yaml_config_source import parse_neuroarchitecture
    raw = W.manifest_raw(PROTOCOL)
    weights = {W.connection_id(a, b): 0.0001 * (k + 1) + 0.003 for k, (a, b) in
               enumerate((a, b) for a in UNITS for b in UNITS if a != b)}
    v = W.f_variant_manifest(PROTOCOL, weights)
    assert {k: x for k, x in v.items() if k != "projections"} == {k: x for k, x in raw.items() if k != "projections"}
    assert len(v["projections"]) == len(raw["projections"]) == 9
    for p, q in zip(v["projections"], raw["projections"]):
        src = p["from"].split(".")[0]
        if src in UNITS:
            assert "plastic" not in p and p["weight"] == weights[W.connection_id(src, p["to"])]
            assert {k: x for k, x in p.items() if k != "weight"} == {k: x for k, x in q.items() if k not in ("weight", "plastic")}
        else:
            assert p == q
    m, c0 = parse_neuroarchitecture(v), parse_neuroarchitecture(raw)
    assert not any(p.plastic for p in m.projections) and [u.unit_id for u in m.units] == [u.unit_id for u in c0.units]
    assert v == A.expected_variant(raw, weights)
    with pytest.raises(ValueError):                    # 6 本でない重み・知らない接続
        W.f_variant_manifest(PROTOCOL, dict(list(weights.items())[:5]))
    with pytest.raises(ValueError):
        W.f_variant_manifest(PROTOCOL, weights | {"s9.main->s1": 0.005})


def test_rebuilt_individual_has_the_natural_birth_dynamics() -> None:
    """同じ seed から F の変種の設計図で組み立てた個体の Unit の力学・出生時の Unit の状態は、C0 の設計図の自然な本体と同じ
    （Unit の出生時の値の乱数は Unit の並びの順に消費され、接続の plastic・weight に依らない）。"""
    nat = W.build(PROTOCOL, [], SYN[1], "O", W.ExperimentLog())
    weights = {cid: 0.002 + 0.001 * k for k, cid in enumerate(sorted(W.initial_connections(PROTOCOL)))}
    f = W.build(PROTOCOL, [], SYN[1], "F(O)", W.ExperimentLog(), W.f_variant_manifest(PROTOCOL, weights))
    assert W.unit_dynamics(f) == W.unit_dynamics(nat)
    assert W.full_state(f)["units"] == W.full_state(nat)["units"] and W.full_state(f)["connections"] == {}


# ---- 4. T_0 がある個体：F の組み立てと R(O) を実物の runtime で（README §2.3・§2.4・§7）----------------------------------

def test_all_checks_pass_on_a_real_runtime_individual(syn) -> None:
    assert syn["run"]["freeze"]["t0_exists"] is True
    assert _checks(syn) == {}
    st = A.check_statuses(A.check_seed(syn, "synthetic", SYN[0], SMALL), A.raw_t0_exists(syn))
    assert set(st.values()) == {"pass"} and set(st) == set(A.CHECK_NAMES) - {A.COUNT_CHECK}
    table, problems = A.count_table(syn["run"], SYN[0], SMALL)
    assert problems == [] and tuple(table["natural"]) == W.BODIES and tuple(table["F"]) == W.BODIES


def test_raw_holds_the_preregistered_items_and_no_judgment_quantities(syn) -> None:
    """README §8・protocol の records：自然な本体・F 本体・R(O) の記録の項目。raw に判定の量（主の事象）を書かない。"""
    run = syn["run"]
    t0 = run["freeze"]["t0"]
    assert set(run) == {"seed", "plan", "roles", "freeze_window", "freeze", "natural_bodies", "f_bodies", "control_bodies"}
    assert run["freeze"] == {"t0_exists": True, "t0": t0, "window_witness": None}
    assert SMALL.freeze_window[0] <= t0 <= SMALL.freeze_window[1]
    for b, rec in run["natural_bodies"].items():
        assert set(rec) == {"body", "birth", "dynamics", "labels", "spikes", "states", "state_t0", "first_stimulus",
                            "before_divergence", "rng", "sensory", "first_divergence_from_O"}
        assert list(rec["states"]) == [str(p) for p in SMALL.snapshots] and rec["state_t0"]["pulse"] == t0
    assert [r["original_body"] for r in run["f_bodies"]] == list(W.BODIES)
    for r in run["f_bodies"]:
        assert set(r) == {"original_body", "dynamics", "start", "states", "sensory", "spikes", "frozen_weights"}
        assert list(r["states"]) == [str(p) for p in SMALL.rebuilt_snapshots] and r["start"]["pulse"] == t0
        assert r["sensory"] == [] and min((p for ps in r["spikes"].values() for p in ps), default=t0 + 1) > t0
    assert [c["name"] for c in run["control_bodies"]] == ["R_O"]
    text = json.dumps(run)
    for word in ('"events"', '"O_above"', '"E_Ca_cnt"', '"h_O"', '"Delta_AB"', '"D"'):
        assert word not in text, word


def test_f_body_is_frozen_at_the_t0_weights(syn) -> None:
    """F(b) の固定した重みは b の T_0 の重みちょうど。始まりの全状態は b の T_0 の Unit の状態で、接続の状態・駆動・Delta がない。
    記録したすべての全状態で接続の状態が空。"""
    run = syn["run"]
    t0 = run["freeze"]["t0"]
    for r in run["f_bodies"]:
        nat = run["natural_bodies"][r["original_body"]]
        assert r["frozen_weights"] == {cid: v[0] for cid, v in nat["state_t0"]["connections"].items()}
        assert r["start"] == {"pulse": t0, "units": nat["state_t0"]["units"], "connections": {}, "drives": [], "deltas": 0}
        assert r["dynamics"] == nat["dynamics"] and all(st["connections"] == {} for st in r["states"].values())


def test_f_drives_carry_the_frozen_weights_pulse_by_pulse(syn) -> None:
    """README §7 の F の重みの一定を、記録した全状態の外でも、実物の runtime で 1 Pulse ずつ確かめる（記録した時点に駆動が
    なければ raw の確認は空になりうるので）。F 本体の Unit → Unit の駆動の重みは、どの Pulse でも T_0 の重みちょうどで、
    接続の重みは一度も変わらない。自然な本体のほうは、同じ区間で重みが変わる（可塑性を止めたことが意味を持つ）。"""
    run = syn["run"]
    t0 = run["freeze"]["t0"]
    b = _diverging_f(run)
    state = run["natural_bodies"][b]["state_t0"]
    weights = {cid: v[0] for cid, v in state["connections"].items()}
    app = W.build(PROTOCOL, [], SYN[0], f"F({b})", W.ExperimentLog(), W.f_variant_manifest(PROTOCOL, weights))
    W.import_unit_states(app, state)
    seen = 0
    for e in range(1, SMALL.body_end - t0 + 1):
        W.advance_to(app, e)
        assert {W.connection_id(s, t): w for (s, _p, t), w in app.connections.weights().items() if s in UNITS} == weights
        for d in app.pulse_runtime.brain_state.drives:
            if d.source_id in UNITS:
                assert d.weight == weights[W.connection_id(d.source_id, d.target_id)]
                seen += 1
    assert seen > 0, "F 本体の Unit → Unit の駆動が一度も起きなかった（確認が空）"
    nat_end = run["natural_bodies"][b]["states"][str(SMALL.body_end)]["connections"]
    assert any(nat_end[cid][0] != w for cid, w in weights.items())


def test_f_matches_the_natural_body_until_the_first_spike_and_may_diverge_after(syn) -> None:
    """F(b) の発火の列は、T_0 より後の b の最初の発火の Pulse まで（含む）b と一致する。その後は分かれうる（少なくとも 1 本体で
    分かれることを確かめ、確認が自明でないことを示す）。"""
    run = syn["run"]
    t0 = run["freeze"]["t0"]
    for r in run["f_bodies"]:
        nat = run["natural_bodies"][r["original_body"]]["spikes"]
        p1 = min(p for ps in nat.values() for p in ps if p > t0)
        for u in UNITS:
            assert [p for p in nat.get(u, []) if t0 < p <= p1] == [p for p in r["spikes"].get(u, []) if p <= p1]
    _diverging_f(run)


def test_rebuild_control_reproduces_the_natural_o(syn) -> None:
    """R(O)：同じ組み立て方で可塑性を残し、O の T_0 の全状態を写した本体は、自然な O の T_0 より後の発火と 13500・25500 の全状態
    （発火の回数を含む）を再現する（組み立て直し・Pulse の番号のそろえ方が、可塑性を止めること以外に軌道を変えない）。"""
    run = syn["run"]
    t0 = run["freeze"]["t0"]
    o, r = run["natural_bodies"]["O"], run["control_bodies"][0]
    assert r["start"] == o["state_t0"] and r["dynamics"] == o["dynamics"]
    for u in UNITS:
        assert r["spikes"].get(u, []) == A.in_range(o["spikes"], u, t0 + 1, SMALL.body_end)
    assert r["states"] == {k: o["states"][k] for k in r["states"]}


def test_f_checks_detect_tampering(syn) -> None:
    run = syn["run"]
    b = _diverging_f(run)

    def frozen_weight(run):                          # 固定した重みを 1 つだけ T_0 の重みと違う値に
        w = _f(run, "W4")["frozen_weights"]
        w[next(iter(w))] += 1e-15
    assert set(_tampered(syn, frozen_weight)) == {"f_construction"}

    def start_units(run):
        _f(run, "M")["start"]["units"]["s2"][0] += 1e-15
    assert set(_tampered(syn, start_units)) == {"f_construction"}

    def start_connections(run):
        _f(run, "W2")["start"]["connections"] = {"s1.main->s2": [0.005, 0.0, 0.0]}
    assert {"f_construction", "f_weights_constant"} <= set(_tampered(syn, start_connections))

    def dynamics(run):
        _f(run, "W6")["dynamics"]["s1"] = {"x": 1}
    assert set(_tampered(syn, dynamics)) == {"f_construction"}

    def drive_weight(run):                           # 記録した全状態に、固定した重みと違う重みの駆動を置く
        st = _f(run, "W7")["states"][str(SMALL.body_end)]
        st["drives"] = [["s1", "s2", _f(run, "W7")["frozen_weights"]["s1.main->s2"] + 1e-15, SMALL.body_end]]
    assert set(_tampered(syn, drive_weight)) == {"f_weights_constant"}

    def connections_later(run):
        _f(run, "W8")["states"][str(SMALL.pre_main)]["connections"] = {"s1.main->s2": [0.005, 0.0, 0.0]}
    assert set(_tampered(syn, connections_later)) == {"f_weights_constant"}

    def early_spike(run):                            # T_0 より後の最初の発火より前に、F 本体だけに発火を足す
        t0 = run["freeze"]["t0"]
        nat = run["natural_bodies"][b]["spikes"]
        p1 = min(p for ps in nat.values() for p in ps if p > t0)
        u = next(u for u in UNITS if t0 + 1 not in nat.get(u, []))
        sp = _f(run, b)["spikes"]
        sp[u] = sorted(set(sp.get(u, [])) | {t0 + 1}) if t0 + 1 < p1 else sp.get(u, [])
        if t0 + 1 >= p1:                             # 最初の発火が T_0 ＋ 1 なら、その発火を F 本体から除く
            v = next(v for v in UNITS if p1 in nat.get(v, []))
            sp[v] = [p for p in sp.get(v, []) if p != p1]
    assert "f_matches_natural_until_first_spike" in _tampered(syn, early_spike)

    def f_input(run):
        _f(run, "W9")["sensory"].append([SMALL.body_end, "receptor.x1"])
    assert set(_tampered(syn, f_input)) == {"input_free_after_experience"}

    def f_order(run):
        run["f_bodies"][0], run["f_bodies"][1] = run["f_bodies"][1], run["f_bodies"][0]
    assert set(_tampered(syn, f_order)) == {"revalidate_from_raw"}


def test_rebuild_checks_detect_tampering(syn) -> None:
    def r_state(run):
        run["control_bodies"][0]["states"][str(SMALL.body_end)]["units"]["s1"][3] += 1
    assert set(_tampered(syn, r_state)) == {"rebuild_identity"}

    def r_spike(run):
        sp = run["control_bodies"][0]["spikes"]
        sp["s3"] = sorted(set(sp.get("s3", [])) ^ {SMALL.body_end})
    assert "rebuild_identity" in _tampered(syn, r_spike)

    def r_start(run):
        run["control_bodies"][0]["start"]["units"]["s2"][1] += 1e-15
    assert set(_tampered(syn, r_start)) == {"rebuild_identity"}

    def r_weights(run):                              # R(O) の終わりの重み（組の和は保つ）：再生とも O とも合わない
        st = run["control_bodies"][0]["states"][str(SMALL.body_end)]["connections"]
        st["s1.main->s2"][0] += 1e-9
        st["s2.main->s1"][0] -= 1e-9
    assert set(_tampered(syn, r_weights)) == {"rebuild_identity", "replay_weights_and_traces"}

    def r_missing(run):
        run["control_bodies"] = []
    assert set(_tampered(syn, r_missing)) == {"revalidate_from_raw"}


def _freeze_problems(data, f, plan=SMALL):
    run = copy.deepcopy(data["run"])
    f(run)
    out = {k: [] for k in A.CHECK_NAMES}
    A._check_freeze_time(run, plan, out)
    return out["freeze_time_rule"]


def test_freeze_time_rule_is_recounted_from_the_spikes(syn) -> None:
    t0 = syn["run"]["freeze"]["t0"]
    assert _freeze_problems(syn, lambda run: None) == []

    def spike_at_t0(run):
        sp = run["natural_bodies"]["W5"]["spikes"]
        sp["s2"] = sorted(set(sp.get("s2", [])) | {t0})
    assert any("T_0 に" in p for p in _freeze_problems(syn, spike_at_t0))

    def earlier_t0(run):
        run["freeze"]["t0"] = t0 - 1
    assert _freeze_problems(syn, earlier_t0)

    def drives_at_t0(run):
        run["natural_bodies"]["W3"]["state_t0"]["drives"] = [["s1", "s2", 0.005, t0]]
    assert any("駆動か Delta" in p for p in _freeze_problems(syn, drives_at_t0))


def test_natural_checks_detect_tampering(syn) -> None:
    def m_labels(run):
        run["natural_bodies"]["M"]["labels"] = copy.deepcopy(run["natural_bodies"]["O"]["labels"])
    assert set(_tampered(syn, m_labels)) == {"stimulus_labels"}

    def rng(run):
        run["natural_bodies"]["W2"]["rng"] = f"0030-within-trial-2:{SYN[1]}"
    assert set(_tampered(syn, rng)) == {"stimulus_labels"}

    def birth(run):
        run["natural_bodies"]["W4"]["birth"]["units"]["s1"][0] += 1e-15
    assert set(_tampered(syn, birth)) == {"identical_birth_state_natural_bodies"}

    def late_input(run):
        run["natural_bodies"]["W9"]["sensory"].append([SMALL.experience_end + 5, "receptor.x1"])
    assert set(_tampered(syn, late_input)) == {"input_free_after_experience"}

    def before_state(run):
        run["natural_bodies"]["M"]["before_divergence"]["2"]["units"]["s2"][1] += 1e-15
    assert set(_tampered(syn, before_state)) == {"identical_before_label_divergence"}

    b5 = next(b for b in W.SHUFFLES[4:] if syn["run"]["natural_bodies"][b]["first_divergence_from_O"] is not None)

    def w12000(run):                                  # 組の和を保って重みを動かす（O 以外・札が分かれる本体）
        st = run["natural_bodies"][b5]["states"][str(SMALL.experience_end)]
        st["connections"]["s1.main->s2"][0] += 1e-9
        st["connections"]["s2.main->s1"][0] -= 1e-9
    assert set(_tampered(syn, w12000)) == {"replay_weights_and_traces"}

    def pair(run):
        run["natural_bodies"][b5]["states"][str(SMALL.body_end)]["connections"]["s1.main->s3"][0] += 1e-9
    assert set(_tampered(syn, pair)) == {"replay_weights_and_traces", "pair_sum"}

    def clip(run):
        run["natural_bodies"]["W6"]["first_stimulus"]["2"]["connections"]["s2.main->s3"][0] = 0.0100001
    assert "no_clipping" in _tampered(syn, clip)


def test_replay_reports_clipping_and_matches_the_runtime_rule() -> None:
    from anima_ll.neuroarchitecture.plasticity import PlasticState, balanced_pair_window
    spec = W.plasticity(PROTOCOL)
    rnd = random.Random(23299)
    sp = {"s1": sorted(rnd.sample(range(1, 400), 60)), "s2": sorted(rnd.sample(range(1, 400), 70))}
    r = A.replay([0.005, 0.0, 0.0], "s1", "s2", sp, 0, 400, (0, 200))
    st = PlasticState(0.005)
    for p in range(1, 401):
        st = balanced_pair_window(st, pre_fired=p in sp["s1"], post_fired=p in sp["s2"], delta_time=1.0, spec=spec)
    assert r["end"] == [st.weight, st.pre_trace, st.post_trace] and r["clipped"] == [] and r["at"][0] == [0.005, 0.0, 0.0]
    big = A.replay([0.0099, 500.0, 0.0], "s1", "s2", {"s2": [1]}, 0, 1)
    assert big["clipped"] == [1] and big["end"][0] == spec.w_max


def test_structure_checks_detect_wrong_plan_seed_and_shape(syn) -> None:
    assert set(_checks(copy.deepcopy(syn), SYN[1])) == {"revalidate_from_raw"}
    assert A.check_seed(syn, "synthetic", SYN[0], W.make_plan(PROTOCOL, 3, 31))["revalidate_from_raw"]
    for edit in (lambda r: r["natural_bodies"].pop("W19"),
                 lambda r: r["natural_bodies"]["O"]["states"].pop(str(SMALL.pre_main)),
                 lambda r: r["natural_bodies"]["M"]["first_stimulus"].pop("2"),
                 lambda r: r["f_bodies"][3]["states"].pop(str(SMALL.body_end)),
                 lambda r: r["f_bodies"][2].update(events={"O_above": True}),
                 lambda r: r.update(events={"F": {}}),
                 lambda r: r["natural_bodies"]["O"]["states"][str(SMALL.body_end)].update(extra=1)):
        data = copy.deepcopy(syn)
        edit(data["run"])
        assert "revalidate_from_raw" in _checks(data)
    data = copy.deepcopy(syn)
    data["meta"]["manifest"]["projections"] = []
    assert set(_checks(data)) == {"revalidate_from_raw"}


# ---- 5. T_0 がない個体の契約（README §2.6）-----------------------------------------------------------------------------

def test_notau_1_raw_has_the_registered_form(notau) -> None:
    """(1) raw：freeze.t0_exists ＝ false・t0 ＝ null・window_witness（窓の各 Pulse）、自然な本体の T_0 の全状態は null（ほかの記録は
    T_0 があるときと同じ）、F 本体・R(O) は空の配列。判定の量は raw にない。"""
    plan = notau_plan()
    run = notau["run"]
    lo, hi = plan.freeze_window
    assert run["freeze"]["t0_exists"] is False and run["freeze"]["t0"] is None
    assert [w["pulse"] for w in run["freeze"]["window_witness"]] == list(range(lo, hi + 1))
    assert all(set(w) == {"pulse", "body", "unit"} for w in run["freeze"]["window_witness"])
    assert run["f_bodies"] == [] and run["control_bodies"] == []
    assert all(rec["state_t0"] is None for rec in run["natural_bodies"].values())
    assert "events" not in json.dumps(run)


def test_notau_natural_bodies_are_the_same_as_with_t0(syn, notau) -> None:
    for b in W.BODIES:
        a, n = syn["run"]["natural_bodies"][b], notau["run"]["natural_bodies"][b]
        assert {k: v for k, v in a.items() if k != "state_t0"} == {k: v for k, v in n.items() if k != "state_t0"}


def test_notau_2_f_checks_are_not_applicable_and_not_invalid(notau) -> None:
    """(2) F に固有の 4 つの確認は not_applicable で、invalid にならない。ほかの確認は自然な本体だけで pass。"""
    plan = notau_plan()
    reasons = A.check_seed(notau, "synthetic", SYN[0], plan)
    assert not any(reasons.values())
    st = A.check_statuses(reasons, A.raw_t0_exists(notau))
    na = set(PROTOCOL["checks"]["no_t0"]["not_applicable"])
    assert {k for k, v in st.items() if v == "not_applicable"} == na
    assert {k for k, v in st.items() if v == "pass"} == set(A.CHECK_NAMES) - {A.COUNT_CHECK} - na
    table, problems = A.count_table(notau["run"], SYN[0], plan)
    assert problems == [] and table["F"] == {} and tuple(table["natural"]) == W.BODIES
    assert A.check_statuses({**reasons, "f_construction": ["x"]}, False)["f_construction"] == "fail"


def test_notau_3_the_no_t0_proof_holds_and_tampering_the_witness_fails(notau) -> None:
    """(3) T_0 がないことの証明が成り立ち、window_witness を改ざんすると freeze_time_rule だけが fail になる。"""
    plan = notau_plan()
    assert _freeze_problems(notau, lambda run: None, plan) == []
    w0 = notau["run"]["freeze"]["window_witness"][0]
    t = w0["pulse"]
    fired_at_t = [(b, u) for b in W.BODIES for u in UNITS if t in notau["run"]["natural_bodies"][b]["spikes"].get(u, [])]
    assert fired_at_t[0] == (w0["body"], w0["unit"])
    absent = next((b, u) for b in W.BODIES for u in UNITS if (b, u) not in fired_at_t)
    edits = {"存在しない発火": lambda run: run["freeze"]["window_witness"][0].update(body=absent[0], unit=absent[1]),
             "Pulse の欠け": lambda run: run["freeze"]["window_witness"].pop(),
             "Pulse のずれ": lambda run: run["freeze"]["window_witness"][0].update(pulse=t + 1),
             "欄の形": lambda run: run["freeze"]["window_witness"][0].update(extra=1)}
    if len(fired_at_t) > 1:
        edits["最初ではない"] = lambda run: run["freeze"]["window_witness"][0].update(body=fired_at_t[1][0], unit=fired_at_t[1][1])
    for name, f in edits.items():
        assert set(_tampered(notau, f, plan)) == {"freeze_time_rule"}, name

    def silence(run):                                 # 窓の Pulse の発火を消すと、T_0 があることになる（証明が成り立たない）
        for rec in run["natural_bodies"].values():
            for u, xs in rec["spikes"].items():
                rec["spikes"][u] = [p for p in xs if p != t]
    assert any("どの自然な本体も発火していない" in p for p in _freeze_problems(notau, silence, plan))


def test_notau_4_inconsistent_raw_is_invalid(syn, notau) -> None:
    """(4) README §2.6 の対応から外れた raw は invalid。T_0 がある本当の個体を形どおりに「T_0 がない」と偽った記録は、T_0 がない
    ことの証明が成り立たない。"""
    plan = notau_plan()
    for name, f in {"F 本体がある": lambda run: run["f_bodies"].append({"original_body": "O"}),
                    "確認の本体がある": lambda run: run["control_bodies"].append({"name": "R_O"}),
                    "T_0 が null でない": lambda run: run["freeze"].update(t0=plan.freeze_window[0]),
                    "window_witness がない": lambda run: run["freeze"].update(window_witness=None),
                    "T_0 の全状態がある": lambda run: run["natural_bodies"]["O"].update(
                        state_t0=run["natural_bodies"]["O"]["states"][str(plan.experience_end)]),
                    "t0_exists が真偽でない": lambda run: run["freeze"].update(t0_exists=None),
                    "freeze の欄が足りない": lambda run: run["freeze"].pop("window_witness"),
                    "t0_exists だけが真": lambda run: run["freeze"].update(t0_exists=True)}.items():
        assert "revalidate_from_raw" in _tampered(notau, f, plan), name
    for name, f in {"T_0 があるのに配列が空": lambda run: run.update(f_bodies=[], control_bodies=[]),
                    "T_0 があるのに根拠がある": lambda run: run["freeze"].update(window_witness=[]),
                    "T_0 が窓の外": lambda run: run["freeze"].update(t0=SMALL.freeze_window[0] - 1)}.items():
        assert "revalidate_from_raw" in _tampered(syn, f), name

    def fake_no_t0(run):
        lo, hi = SMALL.freeze_window
        run["freeze"] = {"t0_exists": False, "t0": None,
                         "window_witness": [{"pulse": t, "body": "O", "unit": "s1"} for t in range(lo, hi + 1)]}
        run["f_bodies"], run["control_bodies"] = [], []
        for rec in run["natural_bodies"].values():
            rec["state_t0"] = None
    got = _tampered(syn, fake_no_t0)
    assert set(got) == {"freeze_time_rule"} and any("どの自然な本体も発火していない" in p for p in got["freeze_time_rule"])


def test_notau_individual_f_events_are_false_and_ncnt_is_computed_as_usual(syn, notau) -> None:
    """T_0 がない個体：F の 4 つの事象は false（理由 no_t0）、F 本体から決まる補助は null。N^cnt の事象と自然な本体から決まる補助は、
    T_0 がある場合と同じ自然な本体から同じ値で計算する（自然な本体は窓に依らない）。"""
    plan = notau_plan()
    t_nt, _ = A.count_table(notau["run"], SYN[0], plan)
    t_sm, _ = A.count_table(syn["run"], SYN[0], SMALL)
    run = notau["run"]
    nt = A.individual(t_nt, run["natural_bodies"]["O"]["dynamics"], run["roles"]["units"], None)
    sm = A.individual(t_sm, run["natural_bodies"]["O"]["dynamics"], run["roles"]["units"], syn["run"]["freeze"]["t0"])
    assert nt["events"]["F"] == dict.fromkeys(A.EVENTS["F"], False) and nt["not_outside_reason"] == {"F": "no_t0", "Ncnt": None}
    assert nt["events"]["Ncnt"] == sm["events"]["Ncnt"]
    for key in ("natural_body_components", "natural_0028_form_events", "ncnt_margins", "Ncnt_frozen", "birth_margin_strata"):
        assert nt["auxiliary"][key] == sm["auxiliary"][key], key
    assert all(nt["auxiliary"][k] is None for k in PROTOCOL["quantities"]["auxiliary"]["when_no_t0"]["null_with_reason_no_t0"])
    assert nt["auxiliary"]["null_reason"] == "no_t0" and not nt["auxiliary"]["t0_exists"]


# ---- 6. 時間差 1 の組の数と N^cnt の境界の条件（README §3）--------------------------------------------------------------

def test_lag1_counts_follow_the_definition_by_hand() -> None:
    units = {"A": "s1", "B": "s2", "C": "s3"}
    sp = {"s1": [9, 10, 12, 15, 20], "s2": [10, 11, 13, 16, 21], "s3": [12, 13, 21]}
    want = {"N": {"A->B": 3, "B->A": 1, "A->C": 1, "C->A": 0, "B->C": 1, "C->B": 1}, "spikes": {"A": 4, "B": 4, "C": 2}}
    assert A._counts_route1(sp, units, 10, 20) == want == A._counts_route2(sp, units, 10, 20)
    q = A.body_quantities(want)
    assert (q["Delta_AB"], q["Delta_AC"], q["Delta_BC"], q["D"], q["silent_roles"]) == (2, 1, 0, 1, [])
    zero = A._counts_route1({"s1": [10, 12]}, units, 10, 20)
    assert zero == A._counts_route2({"s1": [10, 12]}, units, 10, 20) and set(zero["N"].values()) == {0}
    assert A.body_quantities(zero)["silent_roles"] == ["B", "C"]


def _q(ab: int, ac: int, na: int = 10, nb: int = 10, nc: int = 10) -> dict:
    return {"Delta_AB": ab, "Delta_AC": ac, "D": ab - ac, "spike_counts": {"A": na, "B": nb, "C": nc},
            "silent_roles": [r for r, n in (("A", na), ("B", nb), ("C", nc)) if n == 0]}


def _bodies(o, m, ref) -> dict:
    return {"O": o, "M": m} | {f"W{i}": x for i, x in enumerate(ref, 1)}


REF = [_q(k - 9, 0) for k in range(19)]              # 参照の Δ_AB は −9〜9、Δ_AC は 0（D は −9〜9）、発火の数はどれも 10


def test_ncnt_events_at_the_boundary() -> None:
    """README §3.3：参照の 19 本すべてで厳密な ＞。右辺は発火の数の差から。等号は成り立たない（左辺 − 右辺 ＞ 0 が要る）。"""
    # 発火の数が同じ（右辺 0）：0028 の形の事象と同じになる
    assert A.cnt_events(_bodies(_q(10, 0), _q(0, 10), REF)) == {"E_Ca_cnt": True, "E_O_cnt": True, "E_M_cnt": True, "E_OM_cnt": True}
    # O の A の発火の数が 3 違うと、Ca の右辺は 3（|ΔN_A| ＋ |ΔN_B|）、O の右辺は 6（2|ΔN_A|）
    o = _q(9 + 3, 0, na=13)                          # 最大の参照（9）との差 3 ＝ 右辺 3：等号で成り立たない
    assert not A.cnt_events(_bodies(o, _q(0, 0), REF))["E_Ca_cnt"]
    o = _q(9 + 4, 0, na=13)                          # 差 4 ＞ 3：Ca は成り立つ。D の差 4 ≤ 6：O は成り立たない
    ev = A.cnt_events(_bodies(o, _q(0, 0), REF))
    assert ev["E_Ca_cnt"] and not ev["E_O_cnt"]
    o = _q(9 + 7, 0, na=13)                          # D の差 7 ＞ 6：O も成り立つ
    assert A.cnt_events(_bodies(o, _q(0, 0), REF))["E_O_cnt"]
    # B・C の差の重み（D の右辺は 2|ΔN_A| ＋ |ΔN_B| ＋ |ΔN_C|）
    m = _q(0, 9 + 2, nb=11, nc=12)                   # D(M) ＝ −11、min の参照 −9 との差 2、右辺 1 ＋ 2 ＝ 3：成り立たない
    assert not A.cnt_events(_bodies(_q(0, 0), m, REF))["E_M_cnt"]
    m = _q(0, 9 + 4, nb=11, nc=12)                   # 差 4 ＞ 3：成り立つ（M の向きは D(W_i) − D(M)）
    assert A.cnt_events(_bodies(_q(0, 0), m, REF))["E_M_cnt"]
    # 1 本の参照だけが届かないと、事象は成り立たない
    ref = list(REF)
    ref[0] = _q(-9, 0, na=40)                        # Δ_AB(O) − Δ_AB(W1) は大きいが、|ΔN_A| が 30 で届かない
    ev = A.cnt_events(_bodies(_q(15, 0, na=10), _q(0, 0), ref))
    assert not ev["E_Ca_cnt"] and A.cnt_margins(_bodies(_q(15, 0, na=10), _q(0, 0), ref))["E_Ca_cnt"]["satisfied"] == 18
    # E_OM は積
    assert not A.cnt_events(_bodies(_q(10, 0), _q(0, 0), REF))["E_OM_cnt"]


def test_ncnt_silence_of_a_only_in_o_does_not_make_the_event() -> None:
    """担い手の設計 §3.3 (iii)：A が O だけで沈黙して Δ_AB(O) ＝ 0 になっても、右辺に N_A(W_i) が入るので、沈黙だけによる外れは
    E^cnt を満たさない（ここでは参照の Δ_AB をすべて負にし、0028 の形の事象は成り立つが E_Ca^cnt は成り立たない例）。"""
    ref = [_q(-(k + 1), 0, na=10) for k in range(19)]
    o = _q(0, 0, na=0)
    q = _bodies(o, _q(0, 0), ref)
    assert A.order_events(q)["O_Delta_AB_above"] and not A.cnt_events(q)["E_Ca_cnt"]
    assert A.cnt_margins(q)["E_Ca_cnt"]["satisfied"] == 9          # 差 k ＋ 1 が右辺 10 を超えるのは k ≥ 10 の 9 本


def test_ncnt_events_are_subsets_of_the_0028_events() -> None:
    """README §4.4 の命題：右辺が 0 以上なので、N^cnt の各事象は 0028 の形の事象を含意する。乱数で作った量で確かめる。"""
    rnd = random.Random("0030-subset-check")
    pairs = {"E_Ca_cnt": "O_Delta_AB_above", "E_O_cnt": "O_above", "E_M_cnt": "M_below", "E_OM_cnt": "O_and_M_split"}
    hit = dict.fromkeys(pairs, 0)
    for _ in range(4000):
        q = {b: _q(rnd.randint(-6, 6), rnd.randint(-6, 6), *(rnd.randint(0, 3) for _ in range(3))) for b in W.BODIES}
        if rnd.random() < 0.5:
            q["O"] = _q(rnd.randint(5, 30), rnd.randint(-6, 6), *(rnd.randint(0, 3) for _ in range(3)))
            q["M"] = _q(rnd.randint(-6, 6), rnd.randint(5, 30), *(rnd.randint(0, 3) for _ in range(3)))
        ce, oe = A.cnt_events(q), A.order_events(q)
        for c, o in pairs.items():
            assert not ce[c] or oe[o], (c, q)
            hit[c] += ce[c]
    assert all(v > 0 for v in hit.values()), hit         # どの事象も一度は成り立つ（含意の確かめが空でない）


def _delta_ab(sp, units, lo, hi):
    q = A.body_quantities(A._counts_route1(sp, units, lo, hi))
    return q["Delta_AB"], q["D"], q["spike_counts"]


def test_proposition_3_edit_bound_holds_on_random_spike_trains() -> None:
    """担い手の設計 命題 3 (i)・(ii)(a)：発火を足し引きしたとき、|ΔΔ_AB| ≤ |ΔN_A| ＋ |ΔN_B|、|ΔD| ≤ 2|ΔN_A| ＋ |ΔN_B| ＋ |ΔN_C|。
    E^cnt の右辺が「数だけの違い」の上界であることの、数え方の側からの確かめ（N^cnt の境界）。"""
    units = {"A": "s1", "B": "s2", "C": "s3"}
    rnd = random.Random(23299)
    lo, hi = 1, 120
    for _ in range(300):
        y = {u: sorted(rnd.sample(range(lo, hi + 1), rnd.randint(0, 40))) for u in UNITS}
        x = {u: list(v) for u, v in y.items()}
        for u in UNITS:                               # 足すだけ・除くだけ（共通の発火の時刻は動かさない）
            if rnd.random() < 0.5:
                x[u] = sorted(set(x[u]) | set(rnd.sample(range(lo, hi + 1), rnd.randint(0, 10))))
            else:
                x[u] = sorted(set(x[u]) - set(rnd.sample(x[u], min(len(x[u]), rnd.randint(0, 10)))))
        ab_x, d_x, n_x = _delta_ab(x, units, lo, hi)
        ab_y, d_y, n_y = _delta_ab(y, units, lo, hi)
        dn = {r: abs(n_x[r] - n_y[r]) for r in ("A", "B", "C")}
        assert abs(ab_x - ab_y) <= dn["A"] + dn["B"]
        assert abs(d_x - d_y) <= 2 * dn["A"] + dn["B"] + dn["C"]


def test_count_table_routes_agree_and_detect_inconsistent_spikes(syn) -> None:
    table, problems = A.count_table(syn["run"], SYN[0], SMALL)
    assert problems == []
    units = syn["run"]["roles"]["units"]
    lo, hi = SMALL.main
    for b in W.BODIES:
        rec = _f(syn["run"], b)
        assert table["F"][b]["spikes"] == {r: len([p for p in rec["spikes"].get(units[r], []) if lo <= p <= hi]) for r in W.ROLES}
    data = copy.deepcopy(syn)
    _f(data["run"], "W7")["spikes"][units["A"]] = [hi + 5, lo + 1]
    _, problems = A.count_table(data["run"], SYN[0], SMALL)
    assert problems


# ---- 7. 判定の量と主の判定（README §4・§5）---------------------------------------------------------------------------

def test_order_events_are_strict_and_one_sided() -> None:
    assert A.order_events(_bodies(_q(10, 0), _q(0, 10), REF)) == {"O_Delta_AB_above": True, "O_above": True, "M_below": True,
                                                                  "O_and_M_split": True}
    assert not any(A.order_events(_bodies(_q(9, 0), _q(0, 9), REF)).values())        # 等号：外にない
    assert not any(A.order_events(_bodies(_q(-10, 0), _q(10, 0), REF)).values())     # 予測と逆の向き：外にない
    with pytest.raises(ValueError):
        A.order_events({"O": _q(0, 0)})
    with pytest.raises(ValueError):
        A.cnt_events({"O": _q(0, 0)})


def _entry(q):
    return {"N": {"A->B": q["Delta_AB"] + 5, "B->A": 5, "A->C": q["Delta_AC"] + 5, "C->A": 5, "B->C": 0, "C->B": 0},
            "spikes": q["spike_counts"]}


def test_individual_records_events_and_auxiliary() -> None:
    nat = _bodies(_q(10, 0), _q(0, 10), REF)
    fq = _bodies(_q(-10, 0), _q(0, -10), REF)
    table = {"natural": {b: _entry(q) for b, q in nat.items()}, "F": {b: _entry(q) for b, q in fq.items()}}
    dyn = {u: {"decay_per_second": 0.85, "intrinsic_drive_per_second": 0.08, "threshold": 0.5} for u in UNITS}
    ind = A.individual(table, dyn, {"A": "s1", "B": "s2", "C": "s3"}, 11990)
    assert all(ind["events"]["Ncnt"].values()) and not any(ind["events"]["F"].values())
    aux = ind["auxiliary"]
    assert aux["F_opposite_direction"] == {"Delta_AB_FO_below_min": True, "D_FO_below_min": True, "D_FM_above_max": True}
    assert aux["F_ranks"]["rank_of_D_FO_among_reference"] == {"reference_below": 0, "reference_equal": 0, "reference_above": 19}
    assert aux["natural_0028_form_events"] == dict.fromkeys(A.NATURAL_EVENTS, True) and aux["freeze_time"] == 11990
    assert aux["ncnt_margins"]["E_Ca_cnt"] == {"satisfied": 19, "largest_shortfall_margin": None}
    assert not any(aux["F_frozen"].values()) and not any(aux["Ncnt_frozen"].values())
    g = 0.08 / (1 - 0.85) - 0.5
    assert all(aux["birth_margin_strata"][r] == {"g": g, "stratum": "active"} for r in W.ROLES)
    zero = _bodies(_q(0, 0), _q(0, 0), [_q(0, 0)] * 19)
    assert all(A.frozen(zero).values()) and not any(A.cnt_events(zero).values())


def test_birth_margin_strata_boundaries() -> None:
    lam = 0.85

    def dyn(g):
        c = 0.08
        return {"decay_per_second": lam, "intrinsic_drive_per_second": c, "threshold": c / (1 - lam) - g}
    got = A.birth_margins({"s1": dyn(-0.031), "s2": dyn(-0.029), "s3": dyn(0.001)}, {"A": "s1", "B": "s2", "C": "s3"})
    assert [got[r]["stratum"] for r in W.ROLES] == ["structural", "conditional", "active"]


def test_thresholds_and_family_alpha_are_the_registered_values() -> None:
    """閾値 4・4・4・2 は、割り当てた水準（0.016・0.016・0.016・0.002。和は家族の水準 0.05）と K ＝ 19 から決まる最小の整数。
    F・N^cnt の両方の家族で同じ。"""
    p, q = Fraction(1, 20), Fraction(1, 420)
    assert A.binom_tail(20, p, 4) <= Fraction(16, 1000) < A.binom_tail(20, p, 3)
    assert A.binom_tail(20, q, 2) <= Fraction(2, 1000) < A.binom_tail(20, q, 1)
    assert abs(float(A.binom_tail(20, p, 4)) - 0.015902) < 1e-6 and abs(float(A.binom_tail(20, q, 2)) - 0.001047) < 1e-6
    assert ALIGN.HOLDS_MIN == {f: {"J_Ca": 4, "J_O": 4, "J_M": 4, "J_OM": 2} for f in ("F", "Ncnt")}
    assert ALIGN.per_individual_null("J_OM", 19) == q and ALIGN.per_individual_null("J_Ca", 19) == p


def _ind(t0: bool = True, **events) -> dict:
    ev = {f: {e: events.get(f"{f}.{e}", False) for e in A.EVENTS[f]} for f in ("F", "Ncnt")}
    aux = {"t0_exists": t0, "natural_0028_form_events": dict.fromkeys(A.NATURAL_EVENTS, False),
           "Ncnt_frozen": dict.fromkeys(ALIGN.JUDGMENTS, False),
           "natural_body_components": {b: {"silent_roles": []} for b in W.BODIES},
           "birth_margin_strata": {r: {"g": 0.1, "stratum": "active"} for r in W.ROLES}}
    if t0:
        aux |= {"F_frozen": dict.fromkeys(ALIGN.JUDGMENTS, False), "F_body_silence": {b: [] for b in W.BODIES},
                "F_opposite_direction": dict.fromkeys(("Delta_AB_FO_below_min", "D_FO_below_min", "D_FM_above_max"), False)}
    else:
        aux |= {"F_frozen": None, "F_body_silence": None, "F_opposite_direction": None}
    return {"events": ev, "auxiliary": aux}


def test_family_judgment_boundaries_and_no_t0_in_the_denominator() -> None:
    for f, J, thr in (("F", "J_O", 4), ("F", "J_OM", 2), ("Ncnt", "J_M", 4), ("Ncnt", "J_OM", 2)):
        e = ALIGN.EVENT[f][J]
        for h in (thr - 1, thr):
            ind = {str(s): _ind(**{f"{f}.{e}": k < h}) for k, s in enumerate(SYN)}
            fam = A.family_judgment(ind, f)
            assert (fam[J][ALIGN.STATISTIC[J]], fam[J]["holds"], fam["n"]) == (h, h >= thr, 20)
    # T_0 がない個体：分母 20 に残り、F の事象は false、凍結とは別に数える。N^cnt は T_0 がない個体の事象も数える
    ind = {str(s): (_ind(t0=False, **{"Ncnt.E_O_cnt": True}) if k < 5 else _ind(**{"F.O_above": k < 9})) for k, s in enumerate(SYN)}
    fam = A.family_judgment(ind, "F")
    assert fam["n"] == 20 and fam["J_O"]["h_O"] == 4 and fam["J_O"]["holds"]
    assert fam["auxiliary"]["no_t0_individuals"] == 5 and fam["auxiliary"]["frozen_among_individuals_with_t0"]["J_O"] == 0
    assert A.family_judgment(ind, "Ncnt")["J_O"]["h_O"] == 5


def test_judgment_has_two_families_and_no_combined_quantities() -> None:
    per_seed = {str(s): {"individual": _ind(t0=k >= 2)} for k, s in enumerate(SYN)}
    j = A.judgment(per_seed)
    assert set(j) == {"families", "experiment_wide_error_rate_claimed", "scope", "not_judged", "no_t0_individuals",
                      "birth_margin_strata_counts", "note"}
    assert j["experiment_wide_error_rate_claimed"] == "none" and set(j["families"]) == {"F", "Ncnt"}
    assert j["no_t0_individuals"] == SYN[:2] and j["birth_margin_strata_counts"]["A"]["active"]["no_t0"] == 2
    assert all(j["families"][f]["direction"] == "one_sided" for f in ("F", "Ncnt"))
    text = json.dumps(j)
    assert not any(k in text for k in ('"total', '"sum', '"combined', '"difference', '"ratio', '"both_families', '"F_minus'))


def test_clopper_pearson_reference_values() -> None:
    lo, hi = A.clopper_pearson(5, 20)
    assert abs(lo - 0.0866) < 1e-4 and abs(hi - 0.4910) < 1e-4


# ---- 8. seed を単位にした一度限りの実行（README §9、protocol execution.per_seed）------------------------------------

def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


def _make_repo(base: Path) -> Path:
    r = base / "repo"
    (r / EXP.relative_to(ROOT)).mkdir(parents=True)
    (r / EXP.relative_to(ROOT) / "protocol.yaml").write_bytes((EXP / "protocol.yaml").read_bytes())
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@example.invalid")
    _git(r, "config", "user.name", "t")
    _git(r, "config", "commit.gpgsign", "false")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "init")
    return r


@pytest.fixture
def repo(tmp_path) -> Path:
    return _make_repo(tmp_path)


def _dummy(seed: int) -> dict:
    return {"seed": seed, "dummy": True}


def _exec(repo, out, seeds, runner=_dummy, mode="synthetic"):
    return R.execute(mode, seeds, out, repo, _git(repo, "rev-parse", "HEAD"), runner=runner, executor_factory=SerialExecutor)


def test_guard_requires_a_clean_real_commit(repo, monkeypatch) -> None:
    head = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setenv("ANIMA_GIT_COMMIT", "f" * 40)
    assert G.verify_clean_commit(repo) == head == G.verify_clean_commit(repo, head)
    with pytest.raises(ERR, match="指定した commit"):
        G.verify_clean_commit(repo, "1" * 40)
    (repo / "untracked.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ERR, match="作業ツリー"):
        G.verify_clean_commit(repo, head)


def test_start_record_is_exclusive(tmp_path) -> None:
    out, seed = tmp_path / "out", GUARD_SEEDS[0]
    rec = {"seed": seed, "measurement_commit": "a" * 40, "protocol_sha256": "b" * 64, "started_at": "t"}
    G.begin_seed(out, seed, rec)
    with pytest.raises(ERR, match="既に開始"):
        G.begin_seed(out, seed, rec)
    seed2 = GUARD_SEEDS[1]
    rec2 = rec | {"seed": seed2}
    results, barrier = [], threading.Barrier(16)

    def attempt():
        barrier.wait()
        try:
            G.begin_seed(out, seed2, rec2)
            results.append("ok")
        except ERR:
            results.append("refused")
    threads = [threading.Thread(target=attempt) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("ok") == 1 and results.count("refused") == 15
    stray = G.seed_dir(out, GUARD_SEEDS[2])
    stray.mkdir(parents=True)
    (stray / G.RAW).write_bytes(b"x")
    with pytest.raises(ERR, match="開始の記録がないまま"):
        G.begin_seed(out, GUARD_SEEDS[2], rec | {"seed": GUARD_SEEDS[2]})
    assert not (stray / G.START).exists()


def test_finish_record_is_written_once_and_requires_a_start(tmp_path) -> None:
    out, seed = tmp_path / "out", GUARD_SEEDS[0]
    fin = {"seed": seed, "status": "completed", "finished_at": "t", "raw_file_sha256": "c" * 64, "raw_file_bytes": 1}
    with pytest.raises(ERR, match="開始の記録がない"):
        G.finish_seed(out, seed, fin)
    G.begin_seed(out, seed, {"seed": seed, "measurement_commit": "a" * 40, "protocol_sha256": "b" * 64, "started_at": "t"})
    G.finish_seed(out, seed, fin)
    with pytest.raises(ERR, match="既にある"):
        G.finish_seed(out, seed, fin | {"status": "failed"})
    assert json.loads((G.seed_dir(out, seed) / G.FINISH).read_text())["status"] == "completed"
    with pytest.raises(ERR):
        G.finish_seed(out, GUARD_SEEDS[1], fin | {"seed": GUARD_SEEDS[1], "status": "maybe"})


def test_execute_runs_each_seed_once_and_records_hashes(repo, tmp_path) -> None:
    out = tmp_path / "out"
    seeds = GUARD_SEEDS[:3]
    res = _exec(repo, out, seeds)
    assert res == {"completed": seeds, "failed": [], "not_started": []}
    head = _git(repo, "rev-parse", "HEAD")
    for s in seeds:
        r = G.read_seed(out, s)
        assert all(k in r["start"] for k in G.START_FIELDS) and r["start"]["measurement_commit"] == head
        assert r["start"]["protocol_sha256"] == G.sha256_file(repo / R.PROTOCOL_PATH)
        assert r["finish"]["status"] == "completed" and all(k in r["finish"] for k in G.FINISH_FIELDS)
        assert (r["finish"]["raw_file_sha256"], r["finish"]["raw_file_bytes"]) == (r["raw_sha256"], r["raw_bytes"])
        raw = json.loads(gzip.decompress((G.seed_dir(out, s) / G.RAW).read_bytes()))
        assert raw["run"]["seed"] == s and raw["meta"]["manifest"] == W.manifest_raw(PROTOCOL)
        assert G.seed_status(out, s) == ("completed", [])
    for again in (seeds[:1], [seeds[2], GUARD_SEEDS[3]]):
        with pytest.raises(ERR, match="既に開始"):
            _exec(repo, out, again)
    assert not G.seed_dir(out, GUARD_SEEDS[3]).exists()
    assert _exec(repo, out, [GUARD_SEEDS[3]])["completed"] == [GUARD_SEEDS[3]]


def test_a_started_seed_without_finish_is_never_rerun_and_blocks_new_seeds(repo, tmp_path) -> None:
    out = tmp_path / "out"
    s = GUARD_SEEDS[0]
    G.begin_seed(out, s, {"seed": s, "measurement_commit": _git(repo, "rev-parse", "HEAD"), "protocol_sha256": "x",
                          "started_at": "t", "experiment": "0030", "kind": PROTOCOL["kind"], "mode": "synthetic"})
    assert G.seed_status(out, s) == ("started", [])
    for seeds in ([s], [GUARD_SEEDS[1]]):
        with pytest.raises(ERR, match="started"):
            _exec(repo, out, seeds)
    assert not G.seed_dir(out, GUARD_SEEDS[1]).exists()


def test_a_failure_midway_is_recorded_and_stops_everything(repo, tmp_path) -> None:
    out = tmp_path / "out"
    seeds = GUARD_SEEDS[:4]

    def runner(seed):
        if seed == seeds[1]:
            raise RuntimeError("途中の失敗")
        return _dummy(seed)
    with pytest.raises(ERR, match="失敗"):
        _exec(repo, out, seeds, runner)
    assert G.seed_status(out, seeds[0])[0] == "completed"
    fin = G.read_seed(out, seeds[1])["finish"]
    assert fin["status"] == "failed" and "途中の失敗" in fin["reason"] and fin["raw_file_sha256"] is None
    assert not G.seed_dir(out, seeds[2]).exists() and not G.seed_dir(out, seeds[3]).exists()
    for again in ([seeds[1]], [seeds[2]], [GUARD_SEEDS[10]]):
        with pytest.raises(ERR, match="failed"):
            _exec(repo, out, again)
    assert G.seed_status(out, seeds[1])[0] == "failed"


@pytest.mark.parametrize("name", ["別の seed", "辞書でない"])
def test_a_wrong_result_is_failed_not_completed(repo, tmp_path, name) -> None:
    out = tmp_path / "out"
    runner = (lambda s: {"seed": s + 1}) if name == "別の seed" else (lambda s: None)
    with pytest.raises(ERR):
        _exec(repo, out, [GUARD_SEEDS[0]], runner)
    assert G.seed_status(out, GUARD_SEEDS[0])[0] == "failed"
    assert not (G.seed_dir(out, GUARD_SEEDS[0]) / G.RAW).exists()


def test_head_or_protocol_moving_during_a_seed_fails_it(repo, tmp_path) -> None:
    out = tmp_path / "out"

    def moves_head(seed):
        (repo / "x.txt").write_text("x", encoding="utf-8")
        _git(repo, "add", "x.txt")
        _git(repo, "commit", "-q", "-m", "move")
        return _dummy(seed)
    with pytest.raises(ERR):
        _exec(repo, out, [GUARD_SEEDS[0]], moves_head)
    fin = G.read_seed(out, GUARD_SEEDS[0])["finish"]
    assert fin["status"] == "failed" and fin["raw_file_sha256"] is not None

    repo2 = _make_repo(tmp_path / "second")
    out2 = tmp_path / "out2"

    def edits_protocol(seed):
        p = repo2 / R.PROTOCOL_PATH
        p.write_bytes(p.read_bytes() + b"\n")
        return _dummy(seed)
    with pytest.raises(ERR):
        _exec(repo2, out2, [GUARD_SEEDS[1]], edits_protocol)
    assert G.seed_status(out2, GUARD_SEEDS[1])[0] == "failed"


def test_execute_refuses_out_of_range_replacement_and_missing_commit(repo, tmp_path) -> None:
    out = tmp_path / "out"
    head = _git(repo, "rev-parse", "HEAD")
    for mode, seeds in (("synthetic", [23001]), ("synthetic", [23300]), ("synthetic", [23101]), ("smoke", [23201]),
                        ("formal", [23021]), ("formal", [22001]), ("synthetic", [GUARD_SEEDS[0], GUARD_SEEDS[0]]),
                        ("synthetic", [])):
        with pytest.raises(ERR):
            R.execute(mode, seeds, out, repo, head, runner=_dummy, executor_factory=SerialExecutor)
    with pytest.raises(ERR, match="measurement-commit"):
        R.execute("formal", [23001], out, repo, None, runner=_dummy, executor_factory=SerialExecutor)
    with pytest.raises(ERR, match="指定した commit"):
        R.execute("formal", [23001], out, repo, "1" * 40, runner=_dummy, executor_factory=SerialExecutor)
    assert not (out / G.SEEDS_DIR).exists() or not any((out / G.SEEDS_DIR).iterdir())
    (G.seed_dir(out, 23300)).mkdir(parents=True)
    (G.seed_dir(out, 23300) / G.START).write_text("{}", encoding="utf-8")
    with pytest.raises(ERR, match="範囲の外"):
        _exec(repo, out, [GUARD_SEEDS[5]])


def test_completed_seeds_must_share_the_measurement_commit(repo, tmp_path) -> None:
    out = tmp_path / "out"
    _exec(repo, out, [GUARD_SEEDS[0]])
    (repo / "y.txt").write_text("y", encoding="utf-8")
    _git(repo, "add", "y.txt")
    _git(repo, "commit", "-q", "-m", "next")
    with pytest.raises(ERR, match="別の測定の commit"):
        _exec(repo, out, [GUARD_SEEDS[1]])


def test_seed_status_detects_broken_records(repo, tmp_path) -> None:
    out = tmp_path / "out"
    _exec(repo, out, GUARD_SEEDS[:5])
    d = [G.seed_dir(out, s) for s in GUARD_SEEDS[:5]]
    (d[0] / G.RAW).write_bytes((d[0] / G.RAW).read_bytes() + b"\0")
    (d[1] / G.START).unlink()
    (d[2] / (G.RAW + ".tmp")).write_bytes(b"")
    fin = json.loads((d[3] / G.FINISH).read_text())
    (d[3] / G.FINISH).write_text(json.dumps(fin | {"status": "done"}))
    (d[4] / G.RAW).unlink()
    assert [G.seed_status(out, s)[0] for s in GUARD_SEEDS[:5]] == ["broken"] * 5
    with pytest.raises(ERR, match="broken"):
        _exec(repo, out, [GUARD_SEEDS[6]])


def test_session_lock_allows_one_run_per_output_folder(tmp_path) -> None:
    out = tmp_path / "out"
    with G.session_lock(out):
        with pytest.raises(ERR, match="ほかの実行"):
            with G.session_lock(out):
                pass
    with G.session_lock(out):
        pass


def _timed_runner(seed):
    """実際のプロセスで、開始・終了の時刻と pid を記録する（並列数の契約のためだけ。seed の計算はしない）。"""
    t0 = time.monotonic()
    time.sleep(0.2)
    t1 = time.monotonic()
    path = Path(os.environ["ANIMA_0030_TIMING_DIR"]) / f"{seed}.json"
    path.write_text(json.dumps({"seed": seed, "pid": os.getpid(), "t0": t0, "t1": t1}), encoding="utf-8")
    return {"seed": seed}


@pytest.mark.skipif(__import__("multiprocessing").get_start_method(allow_none=False) != "fork",
                    reason="テスト関数を子プロセスへ渡すのに fork が要る（本番の run.py は既定の runner を使う）")
def test_real_processes_never_exceed_two_at_once(repo, tmp_path, monkeypatch) -> None:
    timing = tmp_path / "timing"
    timing.mkdir()
    monkeypatch.setenv("ANIMA_0030_TIMING_DIR", str(timing))
    monkeypatch.setattr("os.cpu_count", lambda: 64)
    sizes = []
    real = R.ProcessPoolExecutor

    def factory(n):
        sizes.append(n)
        return real(max_workers=n)
    res = R.execute("synthetic", POOL_SEEDS, tmp_path / "out", repo, _git(repo, "rev-parse", "HEAD"),
                    runner=_timed_runner, executor_factory=factory)
    assert res["completed"] == POOL_SEEDS and sizes == [2] == [R.MAX_WORKERS]
    rec = [json.loads(p.read_text()) for p in timing.glob("*.json")]
    assert sorted(r["seed"] for r in rec) == POOL_SEEDS and len({r["pid"] for r in rec}) <= 2
    events = sorted([(r["t0"], 1) for r in rec] + [(r["t1"], -1) for r in rec])
    running = peak = 0
    for _, d in events:
        running += d
        peak = max(peak, running)
    assert peak <= 2


def test_main_refuses_unsafe_invocations(monkeypatch, tmp_path) -> None:
    called = []
    monkeypatch.setattr(R, "execute", lambda *a, **k: called.append(a))
    for argv in (["run.py"], ["run.py", "--measurement-commit", "a" * 40, "--out", str(tmp_path)],
                 ["run.py", "--smoke"], ["run.py", "--smoke", "--out", str(ROOT / "data" / "experiments" / "x")]):
        monkeypatch.setattr("sys.argv", argv)
        with pytest.raises(SystemExit):
            R.main()
    assert called == []


# ---- 9. 解析：20 個体の完全性・invalid なら判定しない・一度だけ・smoke の盲検（README §4・§7・§9）----------------------------

def _folder(tmp_path_factory, name: str, plan) -> tuple[Path, Path]:
    base = tmp_path_factory.mktemp(name)
    repo = _make_repo(base)
    out = base / "out"
    runner = functools.partial(W.measure_seed, PROTOCOL, plan=plan)
    R.execute("synthetic", SYN, out, repo, _git(repo, "rev-parse", "HEAD"), runner=runner, executor_factory=SerialExecutor)
    return repo, out


@pytest.fixture(scope="module")
def full_folder(tmp_path_factory) -> tuple[Path, Path]:
    """合成の 20 個体（SMALL の Plan で実物の runtime を通す）を、本番と同じ execute の手順で保存したフォルダ。"""
    return _folder(tmp_path_factory, "syn20", SMALL)


@pytest.fixture(scope="module")
def notau_folder(tmp_path_factory) -> tuple[Path, Path]:
    """同じ 20 個体を NOTAU の Plan で execute したフォルダ（T_0 がない個体と T_0 がある個体が混ざる）。"""
    return _folder(tmp_path_factory, "notau20", notau_plan())


def _copy(folder, tmp_path) -> Path:
    out = tmp_path / "copy"
    shutil.copytree(folder[1], out, ignore=shutil.ignore_patterns(G.LOCK))
    return out


def _forbidden_keys(report: dict) -> set:
    """判定の量・現象に関する数値の鍵。invalid・smoke の report には出ない。"""
    text = json.dumps(report)
    return {k for k in ('"N"', '"Delta_AB"', '"Delta_AC"', '"D"', '"h_Ca"', '"h_O"', '"h_M"', '"h_OM"', '"per_seed"',
                        '"spike_counts"', '"silent_roles"', '"families"', '"O_Delta_AB_above"', '"E_Ca_cnt"', '"F_frozen"',
                        '"freeze_time"', '"t0_exists"', '"no_t0_individuals"', '"birth_margin_strata"', '"ncnt_margins"',
                        '"not_applicable"', '"t0"') if k in text}


def test_complete_valid_records_give_one_judgment_per_family(full_folder, tmp_path) -> None:
    out = _copy(full_folder, tmp_path)
    report = A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
    assert report["records"]["state"] == "complete" and report["valid"] and report["invalid_seeds"] == []
    assert report["count_arithmetic"] == "evaluated"
    assert report["analysis_commit"] == report["records"]["measurement_commit"] == _git(full_folder[0], "rev-parse", "HEAD")
    j = report["judgment"]
    assert set(j["families"]) == {"F", "Ncnt"} and j["experiment_wide_error_rate_claimed"] == "none"
    for f, fam in j["families"].items():
        assert fam["family"] == f and fam["n"] == 20 and fam["main_judgments"] == list(ALIGN.JUDGMENTS)
        for J in ALIGN.JUDGMENTS:
            stat = ALIGN.STATISTIC[J]
            h = sum(v["individual"]["events"][f][ALIGN.EVENT[f][J]] for v in report["per_seed"].values())
            assert fam[J][stat] == h and fam[J]["holds"] == (h >= ALIGN.HOLDS_MIN[f][J])
            assert len(fam[J]["clopper_pearson_95_of_h_over_n"]) == 2
    assert len(report["per_seed"]) == 20 and j["no_t0_individuals"] == []
    assert all(set(st.values()) == {"pass"} for st in report["check_results"].values())
    for s in SYN:                                     # raw には判定の量がなく、report にだけある
        raw = json.loads(gzip.decompress((G.seed_dir(out, s) / G.RAW).read_bytes()))
        assert "events" not in json.dumps(raw["run"])
        assert {f: tuple(report["per_seed"][str(s)]["individual"]["events"][f]) for f in ("F", "Ncnt")} == A.EVENTS
    assert json.loads((out / A.REPORT).read_text())["judgment"] == j
    with pytest.raises(ERR, match="既にある"):
        A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
    assert [json.loads(x)["event"] for x in (out / A.LOG).read_text().splitlines()] == ["started", "completed"]


def test_notau_5_no_t0_individuals_are_completed_and_counted(notau_folder, full_folder, tmp_path) -> None:
    """(5) T_0 がない個体は、実行の道具で completed として保存され、raw からの再検証で valid のまま集計に入る。F の 4 つの事象は
    false で分母は 20 のまま。N^cnt の事象は、同じ個体の SMALL の report（T_0 がある）と同じ値で計算される。F に固有の確認は
    not_applicable（失敗ではない）。"""
    plan = notau_plan()
    repo, folder = notau_folder
    no_t0 = []
    for s in SYN:
        assert G.seed_status(folder, s) == ("completed", []) and G.read_seed(folder, s)["finish"]["status"] == "completed"
        raw = json.loads(gzip.decompress((G.seed_dir(folder, s) / G.RAW).read_bytes()))
        if raw["run"]["freeze"]["t0_exists"] is False:
            no_t0.append(s)
            assert raw["run"]["f_bodies"] == [] and raw["run"]["control_bodies"] == []
    assert SYN[0] in no_t0 and 0 < len(no_t0) < 20, no_t0
    out = _copy(notau_folder, tmp_path / "n")
    report = A.publish(out, "synthetic", plan=plan, seeds=SYN, repo=repo)
    assert report["valid"] and report["invalid_seeds"] == [] and report["records"]["state"] == "complete"
    na = set(PROTOCOL["checks"]["no_t0"]["not_applicable"])
    for s in SYN:
        st = report["check_results"][str(s)]
        assert "fail" not in st.values()
        assert ({k for k, v in st.items() if v == "not_applicable"} == na) == (s in no_t0)
    j = report["judgment"]
    assert j["no_t0_individuals"] == no_t0
    small = A.analyze(_copy(full_folder, tmp_path / "s"), "synthetic", SMALL, SYN, repo=full_folder[0])
    for s in SYN:
        ind = report["per_seed"][str(s)]["individual"]
        assert ind["events"]["Ncnt"] == small["per_seed"][str(s)]["individual"]["events"]["Ncnt"]
        if s in no_t0:
            assert ind["events"]["F"] == dict.fromkeys(A.EVENTS["F"], False) and ind["not_outside_reason"]["F"] == "no_t0"
            assert ind["auxiliary"]["F_frozen"] is None
    fam = j["families"]["F"]
    assert fam["n"] == 20 and fam["auxiliary"]["no_t0_individuals"] == len(no_t0)
    for J in ALIGN.JUDGMENTS:
        h = sum(report["per_seed"][str(s)]["individual"]["events"]["F"][ALIGN.EVENT["F"][J]] for s in SYN if s not in no_t0)
        assert fam[J][ALIGN.STATISTIC[J]] == h
    assert j["families"]["Ncnt"]["n"] == 20
    for J in ALIGN.JUDGMENTS:
        assert j["families"]["Ncnt"][J] == small["judgment"]["families"]["Ncnt"][J]
    strata = j["birth_margin_strata_counts"]
    assert all(sum(strata[r][k]["no_t0"] for k in ALIGN.STRATA) == len(no_t0) for r in W.ROLES)
    assert all(sum(strata[r][k]["individuals"] for k in ALIGN.STRATA) == 20 for r in W.ROLES)


def test_notau_5_a_tampered_no_t0_record_makes_the_experiment_invalid(notau_folder, tmp_path) -> None:
    out = _copy(notau_folder, tmp_path)

    def tamper(run):
        run["freeze"]["window_witness"][0]["unit"] = "s9"
    _rewrite_raw(out, SYN[0], tamper)
    report = A.analyze(out, "synthetic", notau_plan(), SYN, repo=notau_folder[0])
    assert not report["valid"] and report["invalid_seeds"] == [SYN[0]] and report["judgment"] is None
    assert report["check_results"][str(SYN[0])]["freeze_time_rule"] == "fail"


def test_incomplete_records_are_not_analyzed_and_nothing_is_written(full_folder, tmp_path) -> None:
    out = _copy(full_folder, tmp_path)
    shutil.rmtree(G.seed_dir(out, SYN[-1]))
    with pytest.raises(ERR, match="未完了"):
        A.analyze(out, "synthetic", SMALL, SYN, repo=full_folder[0])
    with pytest.raises(ERR, match="未完了"):
        A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
    assert not any((out / n).exists() for n in (A.REPORT, A.LOG, G.LOCK))


def _rewrite_raw(out: Path, seed: int, f) -> None:
    """生の記録を改ざんし、終了の記録のハッシュも書き直す（記録は整っていても、確認で invalid になる場合を作る）。"""
    d = G.seed_dir(out, seed)
    data = json.loads(gzip.decompress((d / G.RAW).read_bytes()))
    f(data["run"])
    payload = gzip.compress(json.dumps(data).encode("utf-8"), mtime=0)
    (d / G.RAW).write_bytes(payload)
    fin = json.loads((d / G.FINISH).read_text())
    (d / G.FINISH).write_text(json.dumps(fin | {"raw_file_sha256": G.sha256_bytes(payload), "raw_file_bytes": len(payload)}))


def test_one_invalid_individual_makes_the_experiment_invalid_without_quantities(full_folder, tmp_path) -> None:
    out = _copy(full_folder, tmp_path)
    bad = SYN[7]

    def tamper(run):
        run["control_bodies"][0]["states"][str(SMALL.body_end)]["units"]["s1"][3] += 1
    _rewrite_raw(out, bad, tamper)
    report = A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
    assert report["records"]["state"] == "complete" and not report["valid"]
    assert report["invalid_seeds"] == [bad] and report["judgment"] is None
    assert set(report["checks"][str(bad)]) == {"rebuild_identity"}
    assert report["count_arithmetic"] == "not_evaluated"
    assert not ({'"N"', '"Delta_AB"', '"D"', '"per_seed"', '"families"', '"h_Ca"'} & _forbidden_keys(report))


def test_count_arithmetic_failure_makes_the_experiment_invalid(full_folder, tmp_path, monkeypatch) -> None:
    out = _copy(full_folder, tmp_path)
    real = A._counts_route2

    def off_by_one(sp, units, lo, hi):
        r = real(sp, units, lo, hi)
        r["N"]["A->B"] += 1
        return r
    monkeypatch.setattr(A, "_counts_route2", off_by_one)
    report = A.analyze(out, "synthetic", SMALL, SYN, repo=full_folder[0])
    assert not report["valid"] and report["count_arithmetic"] == "evaluated" and report["judgment"] is None
    assert report["invalid_seeds"] == SYN and all(set(c) == {"lag1_counts_two_ways"} for c in report["checks"].values())


def test_record_problems_block_the_judgment(full_folder, tmp_path) -> None:
    cases = {}
    out = _copy(full_folder, tmp_path / "a")
    p = G.seed_dir(out, SYN[3]) / G.RAW
    b = bytearray(p.read_bytes())
    b[len(b) // 2] ^= 0xFF
    p.write_bytes(bytes(b))
    cases["hash"] = out
    out = _copy(full_folder, tmp_path / "b")
    fin = G.seed_dir(out, SYN[4]) / G.FINISH
    fin.write_text(json.dumps(json.loads(fin.read_text()) | {"status": "failed"}))
    cases["failed"] = out
    out = _copy(full_folder, tmp_path / "c")
    (G.seed_dir(out, SYN[5]) / G.FINISH).unlink()
    (G.seed_dir(out, SYN[5]) / G.RAW).unlink()
    cases["interrupted"] = out
    out = _copy(full_folder, tmp_path / "d")
    shutil.copytree(G.seed_dir(out, SYN[0]), G.seed_dir(out, GUARD_SEEDS[0]))
    cases["extra"] = out
    for name, out in cases.items():
        report = A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
        assert report["records"]["state"] == "failed", name
        assert not report["valid"] and report["judgment"] is None and "per_seed" not in report, name


def test_analysis_refuses_mismatched_raw_and_records(full_folder, tmp_path) -> None:
    out = _copy(full_folder, tmp_path)

    def other_plan(run):
        run["plan"]["delay"] = 31
    _rewrite_raw(out, SYN[2], other_plan)
    report = A.analyze(out, "synthetic", SMALL, SYN, repo=full_folder[0])
    assert report["invalid_seeds"] == [SYN[2]] and "revalidate_from_raw" in report["checks"][str(SYN[2])]
    assert report["judgment"] is None


def _as_smoke(folder: Path) -> None:
    for s in SYN:
        d = G.seed_dir(folder, s)
        for name in (G.START, G.FINISH):
            rec = json.loads((d / name).read_text())
            (d / name).write_text(json.dumps(rec | {"mode": "smoke"}))
        data = json.loads(gzip.decompress((d / G.RAW).read_bytes()))
        data["meta"]["mode"] = "smoke"
        payload = gzip.compress(json.dumps(data).encode("utf-8"), mtime=0)
        (d / G.RAW).write_bytes(payload)
        fin = json.loads((d / G.FINISH).read_text())
        (d / G.FINISH).write_text(json.dumps(fin | {"raw_file_sha256": G.sha256_bytes(payload), "raw_file_bytes": len(payload)}))


def test_smoke_analysis_never_computes_quantities_nor_shows_t0(notau_folder, tmp_path, monkeypatch) -> None:
    """smoke（操作の確認だけ）：判定の量を計算する関数は一度も呼ばれず、report に判定の量も現象に関する数値（T_0 の値・T_0 の有無）も
    ない。確認の結果は fail か ok だけ（pass と not_applicable を区別しない）。smoke の raw に判定の量はない。T_0 がない個体と
    ある個体を含む 20 個体を smoke の形に読み替えて確かめる（smoke の seed は使わない）。"""
    out = _copy(notau_folder, tmp_path)
    _as_smoke(out)

    def boom(*a, **k):
        raise AssertionError("smoke で判定の量を計算した")
    for name in ("body_quantities", "quantities_for_seed", "individual", "order_events", "cnt_events", "cnt_margins",
                 "family_judgment", "judgment", "birth_margins", "rank", "frozen", "strata_counts"):
        monkeypatch.setattr(A, name, boom)
    monkeypatch.setattr(A, "expected_seeds", lambda mode: list(SYN))
    monkeypatch.setattr(A.W, "plan_from", lambda protocol: notau_plan())
    report = A.analyze(out, "smoke", repo=notau_folder[0])
    assert report["valid"] and report["judgment"] is None and report["count_arithmetic"] == "evaluated"
    assert _forbidden_keys(report) == set()
    assert all(set(st.values()) == {"ok"} for st in report["check_results"].values())
    assert set(report) == {"experiment", "kind", "mode", "seeds", "plan", "records", "analysis_commit", "valid",
                           "invalid_seeds", "count_arithmetic", "checks", "checks_evaluated", "check_results", "judgment", "note"}
    for s in SYN:
        raw = json.loads(gzip.decompress((G.seed_dir(out, s) / G.RAW).read_bytes()))
        assert "events" not in json.dumps(raw["run"])


def test_report_destination_isolation(tmp_path, monkeypatch) -> None:
    root = tmp_path / "data" / "experiments"
    own = root / "0030"
    own.mkdir(parents=True)
    monkeypatch.setattr(A, "DATA_ROOT", root)
    monkeypatch.setattr(A, "OWN_DIR", own)
    assert A.report_destination(own, "formal") == own.resolve() / A.REPORT
    for folder, mode in ((root / "0029", "formal"), (tmp_path / "x", "formal"), (own, "smoke"), (root / "0029", "smoke"),
                         (own, "synthetic")):
        with pytest.raises(ERR):
            A.report_destination(folder, mode)
    (own / A.REPORT).write_text("{}")
    with pytest.raises(ERR, match="既にある"):
        A.report_destination(own, "formal", resume=True)


def test_resume_only_with_identical_inputs(full_folder, tmp_path) -> None:
    out = _copy(full_folder, tmp_path)
    A._append(out, {"event": "started", "context": A.analysis_context(out, "synthetic")}, create=True)
    with pytest.raises(ERR, match="既にある"):
        A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
    report = A.publish(out, "synthetic", resume=True, plan=SMALL, seeds=SYN, repo=full_folder[0])
    assert report["valid"]
    out2 = _copy(full_folder, tmp_path / "b")
    A._append(out2, {"event": "started", "context": A.analysis_context(out2, "synthetic")}, create=True)
    p = G.seed_dir(out2, SYN[0]) / G.START
    p.write_text(p.read_text() + " ")
    with pytest.raises(ERR, match="開始のとき"):
        A.publish(out2, "synthetic", resume=True, plan=SMALL, seeds=SYN, repo=full_folder[0])
    assert not (out2 / A.REPORT).exists()


def test_formal_and_smoke_use_only_the_protocol_plan_and_seeds(tmp_path) -> None:
    for args in (("formal", SMALL, SYN), ("smoke", SMALL, None), ("synthetic", None, None), ("synthetic", SMALL, [23001]),
                 ("other", SMALL, SYN)):
        with pytest.raises(ERR):
            A.analyze(tmp_path, *args)
    with pytest.raises(ERR, match="未完了"):
        A.analyze(tmp_path, "formal")


# ---- 10. 解析の道具の commit ＝ 測定の commit（protocol の execution.analysis_commit_must_equal_measurement_commit）------

def _repo_copy(folder, where: Path) -> Path:
    r = where / "repo"
    shutil.copytree(folder[0], r)
    return r


def test_analysis_refuses_unless_head_is_the_clean_measurement_commit(full_folder, tmp_path, monkeypatch) -> None:
    cases = {}
    r = _repo_copy(full_folder, tmp_path / "later")
    (r / "analyze_changed.py").write_text("x = 1\n", encoding="utf-8")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "測定の後に解析の道具を変えた")
    cases["later"] = (r, "指定した commit")
    r = _repo_copy(full_folder, tmp_path / "modified")
    p = r / R.PROTOCOL_PATH
    p.write_bytes(p.read_bytes() + b"\n")
    cases["modified"] = (r, "作業ツリー")
    r = _repo_copy(full_folder, tmp_path / "untracked")
    (r / "untracked.py").write_text("x = 1\n", encoding="utf-8")
    cases["untracked"] = (r, "作業ツリー")

    def boom(*a, **k):
        raise AssertionError("解析の道具が測定の commit のままでないのに、記録を読んだ・判定の量を計算した")
    for name in ("read_raw", "check_seed", "count_table", "body_quantities", "quantities_for_seed", "individual", "judgment"):
        monkeypatch.setattr(A, name, boom)
    for name, (repo, msg) in cases.items():
        out = _copy(full_folder, tmp_path / name)
        with pytest.raises(ERR, match=msg):
            A.analyze(out, "synthetic", SMALL, SYN, repo=repo)
        with pytest.raises(ERR, match=msg):
            A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=repo)
        assert not any((out / n).exists() for n in (A.REPORT, A.LOG, G.LOCK)), name


def test_analysis_refuses_when_the_measurement_commit_is_not_unique(full_folder, tmp_path, monkeypatch) -> None:
    out = _copy(full_folder, tmp_path)
    p = G.seed_dir(out, SYN[9]) / G.START
    p.write_text(json.dumps(json.loads(p.read_text()) | {"measurement_commit": "f" * 40}))
    monkeypatch.setattr(A, "read_raw", lambda *a, **k: (_ for _ in ()).throw(AssertionError("記録を読んだ")))
    assert A.verify_records(out, "synthetic", SYN)["measurement_commit"] is None
    with pytest.raises(ERR, match="1 つに定まらない"):
        A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
    assert not any((out / n).exists() for n in (A.REPORT, A.LOG, G.LOCK))


def test_analysis_stops_before_quantities_if_head_moves_during_the_analysis(full_folder, tmp_path, monkeypatch) -> None:
    repo = _repo_copy(full_folder, tmp_path)
    out = _copy(full_folder, tmp_path / "o")
    real_check, computed = A.check_seed, []

    def moving(*a, **k):
        if not (repo / "late.py").exists():
            (repo / "late.py").write_text("x = 1\n", encoding="utf-8")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-q", "-m", "解析の途中で道具を変えた")
        return real_check(*a, **k)
    monkeypatch.setattr(A, "check_seed", moving)
    monkeypatch.setattr(A, "quantities_for_seed", lambda *a, **k: computed.append(1))
    with pytest.raises(ERR, match="指定した commit"):
        A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=repo)
    assert computed == [] and not (out / A.REPORT).exists()
    assert [json.loads(x)["event"] for x in (out / A.LOG).read_text().splitlines()] == ["started", "failed"]
