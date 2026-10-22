"""実験 0029 の道具の契約テスト（確定した事前登録 v0.2 の README §0〜§14、protocol.yaml）。

本番の seed（22001〜22020）・smoke の seed（22101〜22106）は使わない（実行もしない）。合成の契約テスト専用の範囲
（22201〜22299）だけを使う。合成の個体は、本番と同じ道具（world.measure_seed）・同じ式で、値だけを小さくした Plan
（SMALL：試行 3、遅れ 80。主の区間の長さは式どおり 3 × 60 ＝ 180、τ の窓は式どおり主の区間の直前の 60 Pulse ＝ 201〜260。
試行の数は 0023〜0028 の契約テストと同じ値。遅れは、τ の窓〔幅 60〕が経験の後に収まる最小に近い値として 80 にした）で
実物の runtime を通して作る。結果を見て Plan・seed を選んでいない（seed は範囲の最初から順に使う）。

τ がない個体（README §2.6）の契約テストのためだけに、SMALL の τ の窓を 1 Pulse に狭めた Plan（NOTAU）も使う。その Pulse は、
22201 の SMALL の自然な本体の発火の列で、窓 201〜260 の中の最初の発火の Pulse（どれかの本体が発火した Pulse なので、22201 では
τ がなくなる）。自然な本体の軌道は窓に依らないので、同じ seed の自然な本体は SMALL と NOTAU で同じになる。NOTAU の 20 個体には、
τ がない個体と τ がある個体が両方含まれることを確かめてから使う（片方しかなければテストが失敗する）。

使った合成の seed（PR に開示）：
- 22201〜22220：SMALL と NOTAU の Plan で実物の runtime を通した 20 個体ずつ（確認の再検証・改ざんの検出・合成の集計の通し）
- 22221〜22240：一度限りの実行の契約（dummy の計算。runtime を使わない）
- 22241〜22250：並列数の契約（実際のプロセス。dummy の計算）
- 22299：可塑性の再生の照合に使う乱数の流れの名前だけ（runtime の個体は作らない）
- 本番の Plan（試行 200）での W の札の列の作り方の確認には 22201〜22206 の名前を使う（札の列を作るだけで、runtime の個体は作らない）

τ がない個体の契約（README §2.6 の (1)〜(5)）は §5 で、実行の道具（run.execute で保存した raw）と raw からの再検証（analyze）の
両方で確かめる。
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
EXP = ROOT / "experiments" / "0029_window_start_block_swap"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))
PREREGISTRATION_MERGE = "ec0fe0342e5d3e2eeb00d90661eacf90a90f7e76"   # PR #127 のマージ（README・protocol の確定）
SYN = list(range(22201, 22221))
GUARD_SEEDS = list(range(22221, 22241))
POOL_SEEDS = list(range(22241, 22251))
TOOLS = ("world.py", "run.py", "analyze.py", "alignment.py", "guard.py")
CORRECTIONS = "CORRECTIONS.md"       # 事前登録への技術的な訂正（測定の前。README・protocol は書き換えない）
PREREG = ("README.md", "protocol.yaml")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W = _load("world_0029_test", EXP / "world.py")
G = _load("guard_0029_test", EXP / "guard.py")
A = _load("analyze_0029_test", EXP / "analyze.py")
R = _load("run_0029_test", EXP / "run.py")
sys.modules[R.__name__] = R          # 実際のプロセスへ compute_and_write を渡すため（本番では run.py が __main__）
ALIGN = _load("alignment_0029_test", EXP / "alignment.py")
SMALL = W.make_plan(PROTOCOL, 3, 80)
# run.py・analyze.py はそれぞれ guard.py を読み込むので、GuardError のクラスは 3 つある（どれも同じ契約の拒否）
ERR = (G.GuardError, R.G.GuardError, A.G.GuardError)


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
    """SMALL の τ の窓を、22201 の SMALL の自然な本体が窓の中で最初に発火した Pulse の 1 つに狭めた Plan（τ がない個体を作るため）。"""
    run = W.measure_seed(PROTOCOL, SYN[0], SMALL)
    lo, hi = SMALL.swap_window
    fired = sorted({p for rec in run["natural_bodies"].values() for ps in rec["spikes"].values() for p in ps if lo <= p <= hi})
    assert fired, "SMALL の τ の窓に、22201 の自然な本体の発火がない"
    return dataclasses.replace(SMALL, swap_window=(fired[0], fired[0]))


@pytest.fixture(scope="module")
def notau() -> dict:
    return _raw(W.measure_seed(PROTOCOL, SYN[0], notau_plan()))


def _checks(data: dict, seed: int = SYN[0], plan=SMALL) -> dict:
    return {k: v for k, v in A.check_seed(data, "synthetic", seed, plan).items() if v}


def _tampered(data, f, plan=SMALL) -> dict:
    data = copy.deepcopy(data)
    f(data["run"])
    return _checks(data, plan=plan)


def _swapped(run, block: str, donor: str) -> dict:
    return next(r for r in run["swapped_bodies"] if r["block"] == block and r["donor"] == donor)


def _control(run, name: str) -> dict:
    return next(r for r in run["control_bodies"] if r["name"] == name)


def _mirror(run) -> None:
    """τ ＝ 13500（主の区間の始まりの 1 つ前）の個体で、入れ替えた直後の全状態を改ざんしたとき、同じ時点の全状態にも同じ改ざんを
    写す（その 2 つが同じであることは形の確認なので、改ざんを 1 つの確認に絞るため）。"""
    tau = run["swap"]["tau"]
    if tau == SMALL.pre_main:
        for rec in run["swapped_bodies"] + run["control_bodies"]:
            rec["states"][str(tau)] = copy.deepcopy(rec["state_tau"])


# ---- 1. protocol と道具の対応・固定 -------------------------------------------------------------------------------

def test_protocol_and_tools_are_aligned() -> None:
    ALIGN.check(PROTOCOL)


def _git_show(rev: str, path: str) -> bytes:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{path}"], capture_output=True, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git の履歴がない環境")


def test_preregistration_files_are_unchanged_since_the_merge() -> None:
    """protocol.yaml は事前登録の確定（PR #127 のマージ）からバイト単位で変わっていない。README は確定した §0〜§14 が
    そのまま先頭に残っている（結果は後ろの節に追記する：README §14 の 4）。"""
    rel = f"experiments/{EXP.name}"
    assert (EXP / "protocol.yaml").read_bytes() == _git_show(PREREGISTRATION_MERGE, f"{rel}/protocol.yaml")
    assert (EXP / "README.md").read_bytes().startswith(_git_show(PREREGISTRATION_MERGE, f"{rel}/README.md"))


def test_runtime_core_and_other_experiments_are_unchanged_from_main() -> None:
    """0029 の道具を変える branch では、本体（src/）・設計（config/）・ほかの実験・0029 の事前登録の文書を同時に変えない
    （main との差分）。0029 の道具を変えない branch（後の PR）では確かめない（この PR の範囲の確認なので、後の作業を止めない）。"""
    try:
        base = subprocess.run(["git", "-C", str(ROOT), "merge-base", "HEAD", "origin/main"], capture_output=True,
                              text=True, check=True).stdout.strip()
        diff = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", base, "--", "src", "config", "experiments"],
                              capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git の履歴がない環境")
    tools = {f"experiments/{EXP.name}/{n}" for n in TOOLS}
    if not set(diff) & tools:
        pytest.skip("この branch は 0029 の道具を変えていない")
    assert set(diff) <= tools | {f"experiments/{EXP.name}/{CORRECTIONS}"}, sorted(set(diff) - tools)


FORBIDDEN = [r'"00(0\d|1\d|2[0-8])"', r"'00(0\d|1\d|2[0-8])'", r"data/experiments/00(0\d|1\d|2[0-8])",
             r"00(0\d|1\d|2[0-8])-(shuffle|within)", r"experiments/00(1[3-9]|2[0-8])_",
             r"experiments/0012_passive_world/(?!neuroarchitecture\.yaml)",
             r"(world|guard|run|analyze|alignment)_00(0\d|1\d|2[0-8])"]
SEED_NUMBERS = r"\b(1[3-9]|2[01])[0-2]\d\d\b"   # 0020〜0028 の seed の範囲（13001〜21299）の数


def _code(name: str) -> str:
    """道具のコード（説明の文字列・コメントは除く。alignment.py の使用済みの seed の一覧 SEEN は重なりの確認の記録なので除く）。"""
    src = (EXP / name).read_text(encoding="utf-8")
    src = re.sub(r"SEEN = \(.*?\)\)\)\n", "", src, flags=re.DOTALL)
    src = re.sub(r'""".*?"""', "", src, flags=re.DOTALL)
    return "\n".join(line.split("#")[0] for line in src.splitlines())


def test_tools_hold_no_earlier_experiment_references() -> None:
    """道具は、ほかの実験の ID・出力先・乱数の流れの名前・道具（world.py など）を参照しない。0023〜0028 の道具も読み込まない。
    脳の設計図は protocol の brain.manifest（0014〜0028 と同じ共有の設計図）だけを読み、alignment.py がその名前を確かめる。"""
    for name in TOOLS:
        code = _code(name)
        for pat in FORBIDDEN:
            assert not re.search(pat, code), (name, pat)
        assert "_load(" not in code or all("experiments/" not in line for line in code.splitlines() if "_load(" in line), name
        assert not re.search(SEED_NUMBERS, code), (name, "0020〜0028 の seed の範囲の数")


def test_the_reference_scan_detects_leftovers() -> None:
    for leftover in ('EXPERIMENT = "0028"', 'OUT = "data/experiments/0028"', 'RNG = "0028-within-trial-{i}:{seed}"',
                     '_load("w", ROOT / "experiments/0028_lag1_successor_asymmetry/world.py")',
                     '"experiments/0026_state_block_swap/world.py"', '"experiments/0012_passive_world/world.py"',
                     "world_0028_for_x", "guard_0026"):
        assert any(re.search(p, leftover) for p in FORBIDDEN), leftover
    for leftover in ("SEEDS = range(21001, 21021)", "SYN = range(21201, 21251)", "seed = 19101", "x = 13001"):
        assert re.search(SEED_NUMBERS, leftover), leftover
    for fine in ("first = 13501", "end = 25500", "late = 13500", "lo = 13441", "seed = 22001"):
        assert not re.search(SEED_NUMBERS, fine), fine
    src = (EXP / "alignment.py").read_text(encoding="utf-8")
    assert "range(21001" in src and "range(21001" not in _code("alignment.py") and {21001, 21299, 20299, 19299} <= ALIGN.SEEN


def test_tools_read_identity_from_this_protocol() -> None:
    ex = PROTOCOL["execution"]
    assert R.EXPERIMENT == A.EXPERIMENT == W.EXPERIMENT == PROTOCOL["experiment"] == ex["experiment_id"] == "0029"
    assert str(R.OUT_DIR) == str(A.DEFAULT_DIR) == ex["output_dir"]
    assert str(R.PROTOCOL_PATH) == str(A.PROTOCOL_PATH) == str(W.PROTOCOL_PATH) == ex["protocol_path"]
    assert W.RNG_SHUFFLE == PROTOCOL["conditions"]["within_trial_shuffles"]["rng"] == "0029-within-trial-{i}:{seed}"
    assert PROTOCOL["brain"]["manifest"] == "experiments/0012_passive_world/neuroarchitecture.yaml"
    for mode, key in (("formal", "seeds"), ("smoke", "smoke_seeds"), ("synthetic", "synthetic_seeds")):
        assert list(R.allowed_seeds(mode)) == A.expected_seeds(mode) == list(
            range(PROTOCOL[key]["first"], PROTOCOL[key]["last"] + 1))


def test_the_preregistration_correction_is_pinned_and_recorded() -> None:
    """CORRECTIONS.md（C1：τ がある個体の raw の swap.events は null で、§4.1 の真偽は report に書く。C2：Clopper–Pearson の区間は
    README §6 の意味）。alignment.py は SHA-256 を固定値と照合し、書き換えたら止まる。README・protocol は書き換えない。"""
    text = (EXP / CORRECTIONS).read_text(encoding="utf-8")
    assert "## C1." in text and "## C2." in text and ALIGN.CORRECTIONS_APPLIED == ("C1", "C2")
    assert G.sha256_file(EXP / CORRECTIONS) == ALIGN.CORRECTIONS_SHA256
    assert A.corrections_applied() == {"file": f"experiments/{EXP.name}/{CORRECTIONS}", "sha256": ALIGN.CORRECTIONS_SHA256,
                                       "applied": ["C1", "C2"]}
    real = ALIGN.CORRECTIONS_SHA256
    try:
        ALIGN.CORRECTIONS_SHA256 = "0" * 64
        with pytest.raises(SystemExit, match="CORRECTIONS"):
            ALIGN.check(PROTOCOL)
    finally:
        ALIGN.CORRECTIONS_SHA256 = real


def test_swap_uses_only_the_public_import_state() -> None:
    """README §2.5：入れ替えは Core の公開の import_state だけで行う。道具のコードは Core の内部の欄に触れない。"""
    for name in TOOLS:
        code = _code(name)
        assert not re.search(r"\._(state|plastic|weights|keys|spec|rule|dynamics|output|brain_state)\b", code), name
    code = _code("world.py")
    assert "u.import_state(" in code and "app.connections.import_state(" in code


# ---- 2. Plan・刺激・τ の窓（README §1・§2）--------------------------------------------------------------------------

def test_plan_from_protocol_is_the_registered_timeline() -> None:
    """本番の Plan：経験の終わり 12000、遅れ 1500（＝ 5 × τ_a）、τ の窓 13441〜13500（幅 60 ＝ trials.every）、主の区間
    13501〜25500、本体の終わり 25500。全状態を残す時点は自然な本体 12000・τ・13500・25500、入れ替えた本体 13500・25500。"""
    p = W.plan_from(PROTOCOL)
    assert (p.trials, p.experience_end, p.delay, p.swap_window, p.main, p.body_end) == (200, 12000, 1500, (13441, 13500),
                                                                                        (13501, 25500), 25500)
    assert p.pre_main == 13500 and list(p.snapshots) == [12000, 13500, 25500] and list(p.swapped_snapshots) == [13500, 25500]
    num = PROTOCOL["checks"]["numeric"]["replay_weights_and_traces"]
    assert num["natural_at"] == [12000, "tau", 13500, 25500] and num["swapped_at"] == list(p.swapped_snapshots)
    assert W.plan_of(p.as_dict()) == p and p.first_stimulus == (1, 2)
    assert (SMALL.experience_end, SMALL.swap_window, SMALL.main, SMALL.body_end) == (180, (201, 260), (261, 440), 440)


def test_make_plan_refuses_wrong_formulas_and_windows() -> None:
    for edit in (lambda p: p["timeline"]["count_window_main"].update(first="experience_end + 1"),
                 lambda p: p["timeline"]["swap_window"].update(first="count_window_main.first - 30"),
                 lambda p: p["timeline"]["swap_window"].update(last="count_window_main.first"),
                 lambda p: p["timeline"].update(body_runs_to="swap_window.last"),
                 lambda p: p["timeline"].update(delay="3 * adaptation_tau / pulse_interval_seconds")):
        protocol = copy.deepcopy(PROTOCOL)
        edit(protocol)
        with pytest.raises(ValueError):
            W.plan_from(protocol)
    with pytest.raises(ValueError):                    # 遅れが短く、τ の窓が経験の中に入る（入れ替えた本体に刺激が残る）
        W.make_plan(PROTOCOL, 3, 30)
    for window in ((180, 180), (261, 261), (230, 229)):
        with pytest.raises(ValueError):
            W.check_plan(dataclasses.replace(SMALL, swap_window=window))
    with pytest.raises(ValueError):
        W.measure_seed(PROTOCOL, SYN[0], dataclasses.replace(SMALL, swap_window=(170, 205)))


def _balanced(labels, plan) -> bool:
    at = dict(labels)
    return all(sorted(at.get(t, "") for t in slots) == ["A", "B", "C"] for slots in W.trial_slots(PROTOCOL, plan))


def test_schedules_follow_the_protocol() -> None:
    """O・M・W_i（0025・0027・0028 と同じ作り方：1 本の乱数の流れで、試行の順に [A, B, C] を 1 回ずつ並べ替えて 3 つの枠に置く）。
    W は 20（W1〜W19 は参照のドナー、W20 は受け手）。"""
    plan = W.plan_from(PROTOCOL)
    o = W.ordered_labels(PROTOCOL, plan)
    m = W.labels_of(PROTOCOL, plan, SYN[0], "M")
    assert len(o) == 600 and o[:3] == [(1, "A"), (3, "B"), (31, "C")] and o[-1] == (11971, "C") and _balanced(o, plan)
    assert m[:3] == [(1, "A"), (3, "C"), (31, "B")] and [t for t, _ in m] == [t for t, _ in o] and _balanced(m, plan)
    for seed in SYN[:6]:
        seen = set()
        for i in range(1, 21):
            w = W.labels_of(PROTOCOL, plan, seed, f"W{i}")
            rnd, expected = random.Random(f"0029-within-trial-{i}:{seed}"), []
            for k in range(200):
                roles = ["A", "B", "C"]
                rnd.shuffle(roles)
                t = 1 + 60 * k
                expected += [(t, roles[0]), (t + 2, roles[1]), (t + 30, roles[2])]
            assert w == expected and [t for t, _ in w] == [t for t, _ in o] and _balanced(w, plan) and w not in (o, m)
            seen.add(tuple(x for _, x in w))
        assert len(seen) == 20
    assert W.BODIES == ("O", "M") + tuple(f"W{i}" for i in range(1, 21)) and W.RECIPIENT == "W20"
    assert W.DONORS == ("O", "M") + tuple(f"W{i}" for i in range(1, 20)) and W.REFERENCE == W.DONORS[2:]


def test_alignment_refuses_drift() -> None:
    cases = {
        "時間の流れ": [lambda p: p["timeline"].update(delay="10 * adaptation_tau / pulse_interval_seconds"),
                      lambda p: p["timeline"]["swap_window"].update(first="count_window_main.first - 61")],
        "条件": [lambda p: p["conditions"].pop("M"),
                 lambda p: p["conditions"]["within_trial_shuffles"].update(count=19),
                 lambda p: p["conditions"]["within_trial_shuffles"].update(rng="0029-shuffle-{i}:{seed}")],
        "介入": [lambda p: p["intervention"].update(recipient="W1"),
                 lambda p: p["intervention"]["donors"].remove("M"),
                 lambda p: p["intervention"]["swap_time"]["no_tau"].update(seed_status="failed"),
                 lambda p: p["intervention"]["blocks"]["units"]["replace"].remove("connections.post_trace"),
                 lambda p: p["intervention"].update(plasticity_after_swap=False)],
        "判定の決まり": [lambda p: p["judgment"]["per_family"]["U"]["J_Ca"].update(holds_if="h_Ca >= 4"),
                         lambda p: p["judgment"]["per_family"]["Wt"]["J_OM"].update(per_individual_null_probability_at_most="2/420"),
                         lambda p: p["judgment"]["families"]["U"].update(direction="one_sided"),
                         lambda p: p["judgment"]["per_family"]["alpha_split"].update(J_Ca=0.02),
                         lambda p: p["judgment"]["no_tau_individuals"].update(in_denominator_of_20=False),
                         lambda p: p["judgment"].update(experiment_wide_error_rate_claimed="0.05")],
        "主・補助の量": [lambda p: p["quantities"]["primary"]["per_individual"]["U"].pop("O_and_M_opposite_ends"),
                         lambda p: p["quantities"]["auxiliary"]["when_no_tau"]["null_with_reason_no_tau"].pop()],
        "記録の項目": [lambda p: p["records"]["no_tau"].update(swapped_bodies=None),
                       lambda p: p["records"].update(inconsistent_raw_is_invalid=False)],
        "操作の確認": [lambda p: p["checks"]["no_tau"]["not_applicable"].append("no_clipping"),
                       lambda p: p["checks"]["result_values"].remove("not_applicable"),
                       lambda p: p["checks"]["exact"].remove("lag1_counts_two_ways")],
        "seed": [lambda p: p.update(seeds={"first": 21001, "last": 21020})],
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


# ---- 3. τ の規則・τ がないことの根拠・入れ替えの関数（README §2.2・§2.3・§2.6）----------------------------------------

def test_find_swap_time_is_the_last_quiet_pulse_of_the_window() -> None:
    lo, hi = 10, 20
    sp = {"O": {"s1": [11, 18]}, "M": {"s2": [19, 20]}}
    assert W.find_swap_time(sp, lo, hi) == 17
    full = {"O": {"s1": list(range(lo, hi + 1, 2))}, "W3": {"s3": list(range(lo + 1, hi + 1, 2))}}
    assert W.find_swap_time(full, lo, hi) is None
    assert W.find_swap_time({"O": {}}, lo, hi) == hi


def test_window_witness_is_the_first_firing_in_the_fixed_order() -> None:
    """README §2.6：窓の各 Pulse（昇順）で、本体を O・M・W1〜W20、Unit を s1・s2・s3 の順に見て最初の発火。"""
    sp = {"O": {"s3": [10]}, "M": {"s1": [10, 11]}, "W1": {"s2": [11, 12], "s1": [12]}}
    assert W.window_witness(sp, ("s1", "s2", "s3"), 10, 12) == [
        {"pulse": 10, "body": "O", "unit": "s3"}, {"pulse": 11, "body": "M", "unit": "s1"},
        {"pulse": 12, "body": "W1", "unit": "s1"}]
    with pytest.raises(ValueError):                    # 発火のない Pulse があれば τ がある（根拠を作らない）
        W.window_witness(sp, ("s1", "s2", "s3"), 10, 13)
    assert W.no_tau_events() == {"Wt": dict.fromkeys(W.EVENTS["Wt"], False), "U": dict.fromkeys(W.EVENTS["U"], False),
                                 "not_outside_reason": "no_tau"}


def _app_at(seed: int, body: str, pulse: int):
    log = W.ExperimentLog()
    app = W.build(PROTOCOL, W.labels_of(PROTOCOL, SMALL, seed, body), seed, body, log)
    W.advance_to(app, pulse)
    return app, log


def test_apply_swap_replaces_exactly_the_block_fields() -> None:
    """apply_swap は塊の欄だけをドナーの値にし、ほかの欄（発火の回数・駆動・Delta・Pulse）は受け手のまま。
    2 つの塊を順に入れ替えた結果は、両方を一度に入れ替えた結果と同じ。"""
    t = SMALL.swap_window[0]
    rec_app, _ = _app_at(SYN[1], "W20", t)
    don_app, _ = _app_at(SYN[1], "M", t)
    r0, d0 = W.full_state(rec_app), W.full_state(don_app)
    assert r0 != d0
    for block in W.BLOCK_NAMES:
        app, _ = W.clone(rec_app, W.ExperimentLog())
        W.apply_swap(app, d0, (block,))
        assert W.full_state(app) == A.composed_state(r0, d0, [block])
        assert W.full_state(rec_app) == r0                                # 受け手の元の個体は変わらない
    both, _ = W.clone(rec_app, W.ExperimentLog())
    W.apply_swap(both, d0, W.BLOCK_NAMES)
    seq, _ = W.clone(rec_app, W.ExperimentLog())
    W.apply_swap(seq, d0, ("weights",))
    W.apply_swap(seq, d0, ("units",))
    assert W.full_state(both) == W.full_state(seq) == A.composed_state(r0, d0, W.BLOCK_NAMES)
    assert all(W.full_state(both)["units"][u][3] == r0["units"][u][3] for u in r0["units"])   # 発火の回数は受け手のまま
    with pytest.raises(ValueError):
        W.apply_swap(both, d0, ("drives",))


def test_blocks_partition_the_dynamical_fields() -> None:
    assert W.BLOCKS == {"weights": ((), ("weight",)),
                        "units": (("activity", "adaptation", "refractory_remaining"), ("pre_trace", "post_trace"))}
    assert W.KEPT_UNIT_FIELDS == ("fire_count",) and W.FAMILY_OF == {"weights": "Wt", "units": "U"}
    assert A._block_fields() == {"weights": ([], ["weight"]),
                                 "units": (["activity", "adaptation", "refractory_remaining"], ["pre_trace", "post_trace"])}


# ---- 4. τ がある個体：実物の runtime を通した合成の個体での操作の確認（README §7）---------------------------------------

def test_all_checks_pass_on_a_real_runtime_individual(syn) -> None:
    assert syn["run"]["swap"]["tau_exists"] is True
    assert _checks(syn) == {}
    st = A.check_statuses(A.check_seed(syn, "synthetic", SYN[0], SMALL), A.raw_tau_exists(syn))
    assert set(st.values()) == {"pass"} and set(st) == set(A.CHECK_NAMES) - {A.COUNT_CHECK}
    table, problems = A.count_table(syn["run"], SYN[0], SMALL)
    assert problems == [] and tuple(table["natural"]) == W.BODIES and len(table["controls"]) == 2
    assert all(tuple(table["swapped"][f]) == W.DONORS for f in ("Wt", "U"))


def test_raw_holds_the_preregistered_items(syn) -> None:
    run = syn["run"]
    tau = run["swap"]["tau"]
    assert set(run) == {"seed", "plan", "roles", "swap_window", "swap", "natural_bodies", "swapped_bodies", "control_bodies"}
    assert run["swap"] == {"tau_exists": True, "tau": tau, "window_witness": None, "events": None}
    assert SMALL.swap_window[0] <= tau <= SMALL.swap_window[1] and tuple(run["natural_bodies"]) == W.BODIES
    for b, rec in run["natural_bodies"].items():
        assert {"body", "birth", "dynamics", "labels", "spikes", "states", "state_tau", "first_stimulus", "before_divergence",
                "rng", "sensory", "first_divergence_from_O"} == set(rec)
        assert list(rec["states"]) == [str(p) for p in SMALL.snapshots] and rec["state_tau"]["pulse"] == tau
        assert all(tuple(st) == W.FULL_STATE_FIELDS for st in rec["states"].values())
    assert [(r["block"], r["donor"]) for r in run["swapped_bodies"]] == [(c, d) for c in W.BLOCK_NAMES for d in W.DONORS]
    for r in run["swapped_bodies"] + run["control_bodies"]:
        assert list(r["states"]) == [str(p) for p in SMALL.swapped_snapshots] and r["state_tau"]["pulse"] == tau
        assert r["sensory"] == [] and min((p for ps in r["spikes"].values() for p in ps), default=tau + 1) > tau
    assert [r["name"] for r in run["control_bodies"]] == ["full_swap", "null_swap"]
    assert "probes" not in json.dumps(list(run["natural_bodies"]["O"]))               # 試しの複製は作らない


def test_swapped_states_are_the_composed_states(syn) -> None:
    """入れ替えた状態は、W20 の τ の状態の塊の欄だけをドナーの値にしたもの。Wt では痕跡・Unit の状態が W20 のまま、
    U では重みと発火の回数が W20 のまま（README §2.3・§2.4）。"""
    run = syn["run"]
    w20 = run["natural_bodies"]["W20"]["state_tau"]
    for d in W.DONORS:
        dn = run["natural_bodies"][d]["state_tau"]
        yw, yu = _swapped(run, "weights", d)["state_tau"], _swapped(run, "units", d)["state_tau"]
        assert yw["units"] == w20["units"] and yu["drives"] == yw["drives"] == w20["drives"] == []
        assert all(yw["connections"][c] == [dn["connections"][c][0]] + w20["connections"][c][1:] for c in w20["connections"])
        assert all(yu["connections"][c] == [w20["connections"][c][0]] + dn["connections"][c][1:] for c in w20["connections"])
        assert all(yu["units"][u] == dn["units"][u][:3] + [w20["units"][u][3]] for u in w20["units"])
        assert A.invariant_problems(yu, "x") == [] and A.invariant_problems(yw, "x") == []


def test_a_full_swap_reproduces_the_donor_and_a_null_swap_the_recipient(syn) -> None:
    run = syn["run"]
    tau = run["swap"]["tau"]
    o, w20 = run["natural_bodies"]["O"], run["natural_bodies"]["W20"]
    fs, ns = _control(run, "full_swap"), _control(run, "null_swap")
    for u in A.UNITS:
        assert A.spikes_of(fs["spikes"], u) == A.in_range(o["spikes"], u, tau + 1, SMALL.body_end)
        assert A.spikes_of(ns["spikes"], u) == A.in_range(w20["spikes"], u, tau + 1, SMALL.body_end)
    end = str(SMALL.body_end)
    assert A.without_fire_count(fs["states"][end]) == A.without_fire_count(o["states"][end])
    assert ns["states"] == {k: w20["states"][k] for k in ns["states"]} and ns["state_tau"] == w20["state_tau"]


def test_full_swap_compares_13500_only_when_tau_is_before_it(full_folder, syn) -> None:
    """全部の入れ替えの確認は、τ ＜ 13500（主の区間の始まりの 1 つ前）の個体では 13500 の全状態も比べ、τ ＝ 13500 の個体では
    比べない（その時点の全状態は入れ替えた直後のもので、発火の回数を除けば O と同じ。README §7）。SMALL の合成の 20 個体を
    seed の順に見て、τ ＜ 13500 の最初の個体と τ ＝ 13500 の最初の個体を使う（両方があることも確かめる）。"""
    seeds = {}
    for s in SYN:
        data = json.loads(gzip.decompress((G.seed_dir(full_folder[1], s) / G.RAW).read_bytes()))
        tau = data["run"]["swap"]["tau"]
        if tau is not None:
            seeds.setdefault(tau < SMALL.pre_main, (s, data))
    assert set(seeds) == {True, False}

    def pre_main_state(run):
        _control(run, "full_swap")["states"][str(SMALL.pre_main)]["units"]["s2"][0] += 1e-15
    s, data = seeds[True]
    assert _checks(data, s) == {} and set(_tampered_seed(data, s, pre_main_state)) == {"full_swap_reproduces_donor"}
    s, data = seeds[False]                            # τ ＝ 13500：O とは比べず、入れ替えた直後の全状態と同じことを形で確かめる
    assert _checks(data, s) == {} and set(_tampered_seed(data, s, pre_main_state)) == {"revalidate_from_raw"}


def _tampered_seed(data, seed, f) -> dict:
    data = copy.deepcopy(data)
    f(data["run"])
    return _checks(data, seed)


def test_swap_checks_detect_tampering(syn) -> None:
    run = syn["run"]
    tau = run["swap"]["tau"]

    def composition(run):                            # 入れ替えた状態の重みを 1 つだけドナーと違う値に（組の和は保つ）
        st = _swapped(run, "weights", "W4")["state_tau"]["connections"]
        st["s1.main->s2"][0] += 1e-15
        st["s2.main->s1"][0] -= 1e-15
        _mirror(run)
    assert "swap_composition" in _tampered(syn, composition)

    def record(run):
        _swapped(run, "units", "W9")["swap"]["donor"] = "W8"
    assert set(_tampered(syn, record)) == {"swap_composition"}

    def fire_count(run):                             # 発火の回数をドナーの値に：組み立てが違う
        st = _swapped(run, "units", "M")["state_tau"]
        st["units"]["s1"][3] += 1
        _mirror(run)
    assert set(_tampered(syn, fire_count)) == {"swap_composition"}

    def full_state(run):
        _control(run, "full_swap")["states"][str(SMALL.body_end)]["units"]["s2"][0] += 1e-15
    assert set(_tampered(syn, full_state)) == {"full_swap_reproduces_donor"}

    def full_fire_count(run):                        # 全部の入れ替えは発火の回数を比べない
        _control(run, "full_swap")["states"][str(SMALL.body_end)]["units"]["s2"][3] += 1
    assert set(_tampered(syn, full_fire_count)) == set()

    def full_spike(run):
        sp = _control(run, "full_swap")["spikes"]
        sp["s3"] = sorted(set(sp.get("s3", [])) ^ {SMALL.body_end})
    assert "full_swap_reproduces_donor" in _tampered(syn, full_spike)

    def null_fire_count(run):                        # 入れ替えなしは発火の回数も含めて W20 と同じ
        _control(run, "null_swap")["states"][str(SMALL.body_end)]["units"]["s1"][3] += 1
    assert set(_tampered(syn, null_fire_count)) == {"null_swap_identity"}

    def swapped_weights(run):                        # 入れ替えた本体の終わりの重み（組の和は保つ）
        st = _swapped(run, "units", "W3")["states"][str(SMALL.body_end)]["connections"]
        st["s1.main->s2"][0] += 1e-9
        st["s2.main->s1"][0] -= 1e-9
    assert set(_tampered(syn, swapped_weights)) == {"replay_weights_and_traces"}

    def swapped_input(run):
        _swapped(run, "weights", "W6")["sensory"].append([SMALL.body_end, "receptor.x1"])
    assert set(_tampered(syn, swapped_input)) == {"input_free_after_experience"}

    def control_input(run):
        _control(run, "null_swap")["sensory"].append([SMALL.body_end, "receptor.x2"])
    assert set(_tampered(syn, control_input)) == {"input_free_after_experience"}

    def order(run):                                  # 入れ替えた本体の並び
        run["swapped_bodies"][0], run["swapped_bodies"][1] = run["swapped_bodies"][1], run["swapped_bodies"][0]
    assert set(_tampered(syn, order)) == {"revalidate_from_raw"}

    def donor_state(run):                            # ドナーの τ の状態だけを変えると、組み立てとドナーの再生が食い違う
        run["natural_bodies"]["W11"]["state_tau"]["connections"]["s3.main->s1"][1] += 1e-9
    assert {"swap_composition", "replay_weights_and_traces"} <= set(_tampered(syn, donor_state))

    def i3(run):
        _swapped(run, "units", "W12")["state_tau"]["units"]["s3"][0] = -1.0
        _mirror(run)
    assert {"swap_invariants", "swap_composition"} <= set(_tampered(syn, i3))

    def i4(run):
        _control(run, "full_swap")["state_tau"]["drives"] = [["s1", "s2", 0.005, tau]]
        _mirror(run)
    assert {"swap_invariants", "swap_composition"} <= set(_tampered(syn, i4))


def test_invariants_are_checked_on_the_swapped_states(syn) -> None:
    """I1〜I4：組の和、痕跡が Unit ごとに一つ、activity が正、駆動・Delta がない。"""
    st = _swapped(syn["run"], "weights", "O")["state_tau"]
    assert A.invariant_problems(st, "Y") == []
    cases = {"I1": lambda s: s["connections"]["s1.main->s3"].__setitem__(0, s["connections"]["s1.main->s3"][0] + 1e-9),
             "I2": lambda s: s["connections"]["s1.main->s2"].__setitem__(1, s["connections"]["s1.main->s2"][1] + 1e-15),
             "I3": lambda s: s["units"]["s2"].__setitem__(0, 0.0),
             "I4": lambda s: s["drives"].append(["s1", "s2", 0.005, 1])}
    for name, f in cases.items():
        bad = copy.deepcopy(st)
        f(bad)
        problems = A.invariant_problems(bad, "Y")
        assert problems and all(f"（{name}）" in p for p in problems), (name, problems)
    assert any("（I4）" in p for p in A.invariant_problems(copy.deepcopy(st) | {"deltas": 1}, "Y"))


def _swap_time_problems(data, f, plan=SMALL):
    run = copy.deepcopy(data["run"])
    f(run)
    out = {k: [] for k in A.CHECK_NAMES}
    A._check_swap_time(run, plan, out)
    return out["swap_time_rule"]


def test_swap_time_rule_is_recounted_from_the_spikes(syn) -> None:
    tau = syn["run"]["swap"]["tau"]
    assert _swap_time_problems(syn, lambda run: None) == []

    def spike_at_tau(run):
        sp = run["natural_bodies"]["W5"]["spikes"]
        sp["s2"] = sorted(set(sp.get("s2", [])) | {tau})
    assert any("τ に" in p for p in _swap_time_problems(syn, spike_at_tau))

    def earlier_tau(run):                            # 記録の τ を 1 つ前の静かでない・最後でない Pulse にする
        run["swap"]["tau"] = tau - 1
    assert _swap_time_problems(syn, earlier_tau)


def test_natural_checks_detect_tampering(syn) -> None:
    def m_labels(run):
        run["natural_bodies"]["M"]["labels"] = copy.deepcopy(run["natural_bodies"]["O"]["labels"])
    assert set(_tampered(syn, m_labels)) == {"stimulus_labels"}

    def rng(run):
        run["natural_bodies"]["W2"]["rng"] = f"0029-within-trial-2:{SYN[1]}"
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

    def w12000(run):                                  # 組の和を保って重みを動かす
        st = run["natural_bodies"]["W1"]["states"][str(SMALL.experience_end)]
        st["connections"]["s1.main->s2"][0] += 1e-9
        st["connections"]["s2.main->s1"][0] -= 1e-9
    assert set(_tampered(syn, w12000)) == {"replay_weights_and_traces"}

    b5 = next(b for b in W.SHUFFLES[4:] if syn["run"]["natural_bodies"][b]["first_divergence_from_O"] is not None)

    def pair(run):                                    # 札が O と分かれる本体（札がすべて O と同じ本体は、軌道の一致の確認にもかかる）
        run["natural_bodies"][b5]["states"][str(SMALL.body_end)]["connections"]["s1.main->s3"][0] += 1e-9
    assert set(_tampered(syn, pair)) == {"replay_weights_and_traces", "pair_sum"}

    def clip(run):
        run["natural_bodies"]["W6"]["first_stimulus"]["2"]["connections"]["s2.main->s3"][0] = 0.0100001
    assert "no_clipping" in _tampered(syn, clip)


def test_replay_reports_clipping_and_matches_the_runtime_rule() -> None:
    from anima_ll.neuroarchitecture.plasticity import PlasticState, balanced_pair_window
    spec = W.plasticity(PROTOCOL)
    rnd = random.Random(22299)
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
    assert A.check_seed(syn, "synthetic", SYN[0], W.make_plan(PROTOCOL, 3, 81))["revalidate_from_raw"]
    for edit in (lambda r: r["natural_bodies"].pop("W20"),
                 lambda r: r["natural_bodies"]["O"]["states"].pop(str(SMALL.pre_main)),
                 lambda r: r["natural_bodies"]["M"]["first_stimulus"].pop("2"),
                 lambda r: r["control_bodies"].reverse(),
                 lambda r: r["swapped_bodies"][3]["states"].pop(str(SMALL.body_end)),
                 lambda r: r["natural_bodies"]["O"]["states"][str(SMALL.body_end)].update(extra=1)):
        data = copy.deepcopy(syn)
        edit(data["run"])
        assert "revalidate_from_raw" in _checks(data)
    data = copy.deepcopy(syn)
    data["meta"]["manifest"]["projections"] = []
    assert set(_checks(data)) == {"revalidate_from_raw"}


# ---- 5. τ がない個体の契約（README §2.6 の (1)〜(5)）----------------------------------------------------------------

def test_notau_1_raw_has_the_registered_form(notau) -> None:
    """(1) raw：swap.tau_exists ＝ false・tau ＝ null・window_witness（窓の各 Pulse）・events（8 つすべて false と no_tau）、
    自然な本体の τ の全状態は null（ほかの記録は τ があるときと同じ）、入れ替えた本体・確認の本体は空の配列。"""
    plan = notau_plan()
    run = notau["run"]
    lo, hi = plan.swap_window
    assert run["swap"]["tau_exists"] is False and run["swap"]["tau"] is None
    assert [w["pulse"] for w in run["swap"]["window_witness"]] == list(range(lo, hi + 1))
    assert all(set(w) == {"pulse", "body", "unit"} for w in run["swap"]["window_witness"])
    assert run["swap"]["events"] == W.no_tau_events() and run["swap"]["events"]["not_outside_reason"] == "no_tau"
    assert run["swapped_bodies"] == [] and run["control_bodies"] == []
    assert all(rec["state_tau"] is None for rec in run["natural_bodies"].values())
    assert all(list(rec["states"]) == [str(p) for p in plan.snapshots] for rec in run["natural_bodies"].values())


def test_notau_natural_bodies_are_the_same_as_with_tau(syn, notau) -> None:
    """自然な本体の軌道は τ の窓に依らない（τ の全状態のほかは、SMALL の同じ seed と同じ）。"""
    for b in W.BODIES:
        a, n = syn["run"]["natural_bodies"][b], notau["run"]["natural_bodies"][b]
        assert {k: v for k, v in a.items() if k != "state_tau"} == {k: v for k, v in n.items() if k != "state_tau"}


def test_notau_2_swap_checks_are_not_applicable_and_not_invalid(notau) -> None:
    """(2) 入れ替えに固有の 4 つの確認は not_applicable で、invalid にならない。ほかの確認は自然な本体だけで pass。"""
    plan = notau_plan()
    reasons = A.check_seed(notau, "synthetic", SYN[0], plan)
    assert not any(reasons.values())
    st = A.check_statuses(reasons, A.raw_tau_exists(notau))
    assert {k for k, v in st.items() if v == "not_applicable"} == set(PROTOCOL["checks"]["no_tau"]["not_applicable"])
    assert {k for k, v in st.items() if v == "pass"} == set(A.CHECK_NAMES) - {A.COUNT_CHECK} - set(
        PROTOCOL["checks"]["no_tau"]["not_applicable"])
    table, problems = A.count_table(notau["run"], SYN[0], plan)
    assert problems == [] and table["swapped"] == {"Wt": {}, "U": {}} and table["controls"] == {}
    assert tuple(table["natural"]) == W.BODIES
    failed = A.check_statuses({**reasons, "swap_composition": ["x"]}, False)   # 理由があれば、τ がなくても fail
    assert failed["swap_composition"] == "fail"


def test_notau_3_the_no_tau_proof_holds_and_tampering_the_witness_fails(notau) -> None:
    """(3) τ がないことの証明が成り立ち、window_witness を改ざんすると swap_time_rule だけが fail になる。"""
    plan = notau_plan()
    assert _swap_time_problems(notau, lambda run: None, plan) == []
    w0 = notau["run"]["swap"]["window_witness"][0]
    t = w0["pulse"]
    fired_at_t = [(b, u) for b in W.BODIES for u in A.UNITS
                  if t in A.spikes_of(notau["run"]["natural_bodies"][b]["spikes"], u)]
    assert fired_at_t[0] == (w0["body"], w0["unit"])
    edits = {
        "存在しない発火": lambda run: run["swap"]["window_witness"][0].update(body="W20", unit="s3")
        if ("W20", "s3") not in fired_at_t else run["swap"]["window_witness"][0].update(body="W19", unit="s3"),
        "Pulse の欠け": lambda run: run["swap"]["window_witness"].pop(),
        "Pulse のずれ": lambda run: run["swap"]["window_witness"][0].update(pulse=t + 1),
        "欄の形": lambda run: run["swap"]["window_witness"][0].update(extra=1),
    }
    if len(fired_at_t) > 1:                           # 発火はあるが、決めた順で最初ではない
        edits["最初ではない"] = lambda run: run["swap"]["window_witness"][0].update(body=fired_at_t[1][0], unit=fired_at_t[1][1])
    for name, f in edits.items():
        assert set(_tampered(notau, f, plan)) == {"swap_time_rule"}, name

    def silence_the_window(run):                      # 窓の Pulse の発火を消すと、τ があることになる（証明が成り立たない）
        for rec in run["natural_bodies"].values():
            for u, xs in rec["spikes"].items():
                rec["spikes"][u] = [p for p in xs if p != t]
    assert any("どの自然な本体も発火していない" in p for p in _swap_time_problems(notau, silence_the_window, plan))


def test_notau_4_inconsistent_raw_is_invalid(syn, notau) -> None:
    """(4) README §2.6 の対応から外れた raw は invalid（revalidate_from_raw）。τ がある本当の個体を「τ がない」と偽った記録
    （形は §2.6 どおり）は、τ がないことの証明が成り立たない（swap_time_rule が fail）。"""
    plan = notau_plan()
    cases_no_tau = {
        "入れ替えた本体がある": lambda run: run["swapped_bodies"].append({"block": "weights"}),
        "確認の本体がある": lambda run: run["control_bodies"].append({"name": "full_swap"}),
        "τ が null でない": lambda run: run["swap"].update(tau=plan.swap_window[0]),
        "window_witness がない": lambda run: run["swap"].update(window_witness=None),
        "events が false でない": lambda run: run["swap"]["events"]["U"].update(O_outside=True),
        "events の理由が違う": lambda run: run["swap"]["events"].update(not_outside_reason="frozen"),
        "τ の全状態がある": lambda run: run["natural_bodies"]["O"].update(state_tau=run["natural_bodies"]["O"]["states"][
            str(plan.experience_end)]),
        "tau_exists が真偽でない": lambda run: run["swap"].update(tau_exists=None),
        "swap の欄が足りない": lambda run: run["swap"].pop("events"),
        "tau_exists だけが真": lambda run: run["swap"].update(tau_exists=True),
    }
    for name, f in cases_no_tau.items():
        assert "revalidate_from_raw" in _tampered(notau, f, plan), name
    cases_tau = {
        "τ があるのに配列が空": lambda run: run.update(swapped_bodies=[], control_bodies=[]),
        "τ があるのに根拠がある": lambda run: run["swap"].update(window_witness=[]),
        "τ があるのに events がある": lambda run: run["swap"].update(events=W.no_tau_events()),
        "τ が窓の外": lambda run: run["swap"].update(tau=SMALL.swap_window[0] - 1),
    }
    for name, f in cases_tau.items():
        assert "revalidate_from_raw" in _tampered(syn, f), name

    def fake_no_tau(run):                             # 形は §2.6 どおりに「τ がない」と偽る
        lo, hi = SMALL.swap_window
        run["swap"] = {"tau_exists": False, "tau": None, "events": W.no_tau_events(),
                       "window_witness": [{"pulse": t, "body": "O", "unit": "s1"} for t in range(lo, hi + 1)]}
        run["swapped_bodies"], run["control_bodies"] = [], []
        for rec in run["natural_bodies"].values():
            rec["state_tau"] = None
    got = _tampered(syn, fake_no_tau)
    assert set(got) == {"swap_time_rule"}
    assert any("どの自然な本体も発火していない" in p for p in got["swap_time_rule"])


def test_notau_individual_events_are_false_and_auxiliary_is_null(notau) -> None:
    """τ がない個体の評価：8 つの事象は false、理由 no_tau。自然な本体から決まる補助は記録し、入れ替えた本体から決まる補助は
    null（README §2.6・protocol の when_no_tau）。"""
    plan = notau_plan()
    table, _ = A.count_table(notau["run"], SYN[0], plan)
    run = notau["run"]
    ind = A.individual(table, run["natural_bodies"]["O"]["dynamics"], run["roles"]["units"], None)
    assert ind["events"] == {f: dict.fromkeys(W.EVENTS[f], False) for f in ("Wt", "U")} and ind["not_outside_reason"] == "no_tau"
    aux = ind["auxiliary"]
    assert not aux["tau_exists"] and aux["swap_time"] is None and aux["null_reason"] == "no_tau"
    assert all(aux[k] is None for k in PROTOCOL["quantities"]["auxiliary"]["when_no_tau"]["null_with_reason_no_tau"])
    assert set(aux["natural_comparison"]) == set(A.NATURAL_EVENTS) and tuple(aux["natural_body_components"]) == W.BODIES
    assert set(aux["birth_margin_strata"]) == set(W.ROLES)


# ---- 6. 時間差 1 の発火の組の数（README §3.1。2 通りの算術）------------------------------------------------------------

def test_lag1_counts_follow_the_definition_by_hand() -> None:
    units = {"A": "s1", "B": "s2", "C": "s3"}
    sp = {"s1": [9, 10, 12, 15, 20], "s2": [10, 11, 13, 16, 21], "s3": [12, 13, 21]}
    want = {"N": {"A->B": 3, "B->A": 1, "A->C": 1, "C->A": 0, "B->C": 1, "C->B": 1}, "spikes": {"A": 4, "B": 4, "C": 2}}
    assert A._counts_route1(sp, units, 10, 20) == want == A._counts_route2(sp, units, 10, 20)
    q = A.body_quantities(want)
    assert (q["Delta_AB"], q["Delta_AC"], q["Delta_BC"], q["D"], q["silent_units"]) == (2, 1, 0, 1, [])
    silent = {"s1": [10, 12]}
    zero = A._counts_route1(silent, units, 10, 20)
    assert zero == A._counts_route2(silent, units, 10, 20) and set(zero["N"].values()) == {0}
    assert A.body_quantities(zero)["silent_units"] == ["B", "C"]


def test_count_table_routes_agree_and_detect_inconsistent_spikes(syn) -> None:
    table, problems = A.count_table(syn["run"], SYN[0], SMALL)
    assert problems == []
    units = syn["run"]["roles"]["units"]
    lo, hi = SMALL.main
    for d in W.DONORS:
        rec = _swapped(syn["run"], "units", d)
        assert table["swapped"]["U"][d]["spikes"] == {r: len([p for p in rec["spikes"].get(units[r], []) if lo <= p <= hi])
                                                      for r in W.ROLES}
    data = copy.deepcopy(syn)
    _swapped(data["run"], "weights", "W7")["spikes"][units["A"]] = [hi + 5, lo + 1]   # 並びが崩れた発火の列
    _, problems = A.count_table(data["run"], SYN[0], SMALL)
    assert problems


# ---- 7. 判定の量と主の判定（README §4・§5）---------------------------------------------------------------------------

def _q(ab: int, ac: int, spikes: int = 1) -> dict:
    return {"Delta_AB": ab, "Delta_AC": ac, "D": ab - ac, "spike_counts": {r: spikes for r in W.ROLES},
            "silent_units": [] if spikes else list(W.ROLES)}


def _donors(o, m, ref) -> dict:
    """{ドナー: 量}。o・m は (Δ_AB, Δ_AC)、ref は W1〜W19 の (Δ_AB, Δ_AC) の列。"""
    return {"O": _q(*o), "M": _q(*m)} | {f"W{i}": _q(*x) for i, x in enumerate(ref, 1)}


REF = [(k - 9, 0) for k in range(19)]              # 参照の Δ_AB は −9〜9、Δ_AC は 0（D は −9〜9）


def test_wt_events_are_strict_and_one_sided() -> None:
    assert A.wt_events(_donors((10, 0), (0, 10), REF)) == {"O_Delta_AB_above": True, "O_above": True, "M_below": True,
                                                            "O_and_M_split": True}
    assert not any(A.wt_events(_donors((9, 0), (0, 9), REF)).values())                 # 最大・最小と等しい：外にない
    assert not any(A.wt_events(_donors((-10, 0), (10, 0), REF)).values())             # 予測と逆の向き：外にない
    with pytest.raises(ValueError):
        A.wt_events({"O": _q(0, 0)})


def test_u_events_are_strict_and_two_sided() -> None:
    """U は向きを問わない：上・下のどちらの外れも数える。J_OM^U は O と M が反対の端（どちらの向きの組でも）。"""
    up = A.u_events(_donors((10, 0), (0, 10), REF))
    down = A.u_events(_donors((-10, 0), (10, 0), REF))
    assert up == down == {"O_Delta_AB_outside": True, "O_outside": True, "M_outside": True, "O_and_M_opposite_ends": True}
    same_end = A.u_events(_donors((10, 0), (10, 0), REF))                             # 同じ端：反対の端ではない
    assert same_end["O_outside"] and same_end["M_outside"] and not same_end["O_and_M_opposite_ends"]
    assert not any(A.u_events(_donors((9, 0), (-9, 0), REF)).values())                # 等号：外にない


def test_individual_records_directions_ranks_and_frozen() -> None:
    nat = {b: {"N": {k: 0 for k in A.PAIR_KEYS}, "spikes": {r: 1 for r in W.ROLES}} for b in W.BODIES}
    swapped_q = {"Wt": _donors((-10, 0), (10, 0), REF), "U": _donors((-10, 0), (10, 0), REF)}
    entry = lambda q: {"N": {"A->B": q["Delta_AB"], "B->A": 0, "A->C": q["Delta_AC"], "C->A": 0, "B->C": 0, "C->B": 0},  # noqa: E731
                       "spikes": q["spike_counts"]}
    table = {"natural": nat, "swapped": {f: {d: entry(q) for d, q in swapped_q[f].items()} for f in ("Wt", "U")},
             "controls": {n: entry(_q(0, 0)) for n in W.CONTROLS}}
    dyn = {u: {"decay_per_second": 0.85, "intrinsic_drive_per_second": 0.08, "threshold": 0.5} for u in A.UNITS}
    ind = A.individual(table, dyn, {"A": "s1", "B": "s2", "C": "s3"}, 250)
    assert not any(ind["events"]["Wt"].values()) and all(ind["events"]["U"].values())
    aux = ind["auxiliary"]
    assert aux["Wt_opposite_direction"] == {"Delta_AB_O_below_min": True, "D_O_below_min": True, "D_M_above_max": True}
    assert aux["U_directions"]["O_outside"] == {"above_max": False, "below_min": True}
    assert aux["U_directions"]["O_and_M_opposite_ends"] == "O_below_M_above"
    assert aux["ranks"]["U"]["rank_of_D_O_among_reference"] == {"reference_below": 0, "reference_equal": 0, "reference_above": 19}
    assert not any(aux["frozen_per_judgment"]["Wt"].values()) and aux["swap_time"] == 250
    assert aux["natural_comparison"] == dict.fromkeys(A.NATURAL_EVENTS, False)
    g = 0.08 / (1 - 0.85) - 0.5
    assert all(aux["birth_margin_strata"][r] == {"g": g, "stratum": "active"} for r in W.ROLES)
    zero = {"Wt": _donors((0, 0), (0, 0), [(0, 0)] * 19), "U": _donors((0, 0), (0, 0), [(0, 0)] * 19)}
    assert all(all(A.frozen(zero[f]).values()) for f in ("Wt", "U"))


def test_birth_margin_strata_boundaries() -> None:
    """層：構造的 g ＜ −0.03、条件付き −0.03 ≤ g ＜ 0、活動的 g ≥ 0（README §6）。"""
    lam = 0.85

    def dyn(g):
        c = 0.08
        return {"decay_per_second": lam, "intrinsic_drive_per_second": c, "threshold": c / (1 - lam) - g}
    units = {"A": "s1", "B": "s2", "C": "s3"}
    got = A.birth_margins({"s1": dyn(-0.031), "s2": dyn(-0.029), "s3": dyn(0.001)}, units)
    assert [got[r]["stratum"] for r in W.ROLES] == ["structural", "conditional", "active"]


def test_thresholds_and_family_alpha_are_the_registered_values() -> None:
    """閾値は、割り当てた水準（0.016・0.016・0.016・0.002。和は家族の水準 0.05）と K ＝ 19・向きから決まる最小の整数：
    Wt 4・4・4・2（1/20、1/420）、U 6・6・6・3（2/20、2/420）。"""
    cases = {("Wt", "J_Ca"): (Fraction(1, 20), 4, "0.016"), ("Wt", "J_OM"): (Fraction(1, 420), 2, "0.002"),
             ("U", "J_Ca"): (Fraction(1, 10), 6, "0.016"), ("U", "J_OM"): (Fraction(1, 210), 3, "0.002")}
    for (f, J), (p, h, a) in cases.items():
        assert ALIGN.per_individual_null(f, J, 19) == p and ALIGN.HOLDS_MIN[f][J] == h
        assert A.binom_tail(20, p, h) <= Fraction(a) < A.binom_tail(20, p, h - 1)
    assert abs(float(A.binom_tail(20, Fraction(1, 10), 6)) - 0.011253) < 1e-6
    assert abs(float(A.binom_tail(20, Fraction(1, 210), 3)) - 0.000116) < 1e-6
    assert ALIGN.HOLDS_MIN == {"Wt": {"J_Ca": 4, "J_O": 4, "J_M": 4, "J_OM": 2}, "U": {"J_Ca": 6, "J_O": 6, "J_M": 6, "J_OM": 3}}


def _ind(tau: bool = True, **events) -> dict:
    ev = {f: {e: events.get(f"{f}.{e}", False) for e in W.EVENTS[f]} for f in ("Wt", "U")}
    aux = {"tau_exists": tau, "natural_comparison": dict.fromkeys(A.NATURAL_EVENTS, False),
           "birth_margin_strata": {r: {"g": 0.1, "stratum": "active"} for r in W.ROLES}}
    if tau:
        aux |= {"frozen_per_judgment": {f: dict.fromkeys(ALIGN.JUDGMENTS, False) for f in ("Wt", "U")},
                "swapped_body_silence": {f: {d: [] for d in W.DONORS} for f in ("Wt", "U")},
                "Wt_opposite_direction": dict.fromkeys(("Delta_AB_O_below_min", "D_O_below_min", "D_M_above_max"), False),
                "U_directions": {e: {"above_max": False, "below_min": False} for e in ("O_Delta_AB_outside", "O_outside",
                                                                                      "M_outside")}
                | {"O_and_M_opposite_ends": None}}
    return {"events": ev, "not_outside_reason": None if tau else "no_tau", "auxiliary": aux}


def test_family_judgment_boundaries_and_no_tau_in_the_denominator() -> None:
    for f, J, thr in (("Wt", "J_O", 4), ("Wt", "J_OM", 2), ("U", "J_M", 6), ("U", "J_OM", 3)):
        e = ALIGN.EVENT[f][J]
        for h in (thr - 1, thr):
            ind = {str(s): _ind(**{f"{f}.{e}": k < h}) for k, s in enumerate(SYN)}
            fam = A.family_judgment(ind, f)
            assert (fam[J][ALIGN.STATISTIC[J]], fam[J]["holds"], fam["n"]) == (h, h >= thr, 20)
    # τ がない個体：分母 20 に残り、事象は false、凍結とは別に数える
    ind = {str(s): (_ind(tau=False) if k < 5 else _ind(**{"Wt.O_above": k < 9})) for k, s in enumerate(SYN)}
    fam = A.family_judgment(ind, "Wt")
    assert fam["n"] == 20 and fam["J_O"]["h_O"] == 4 and fam["J_O"]["holds"]
    assert fam["auxiliary"]["no_tau_individuals"] == 5 and fam["auxiliary"]["frozen_among_individuals_with_tau"]["J_O"] == 0


def test_judgment_has_two_families_and_no_combined_quantities() -> None:
    per_seed = {str(s): {"individual": _ind(tau=k >= 2)} for k, s in enumerate(SYN)}
    j = A.judgment(per_seed)
    assert set(j) == {"families", "experiment_wide_error_rate_claimed", "scope", "not_judged", "no_swap_time_individuals",
                      "natural_comparison_counts", "birth_margin_strata_counts", "note"}
    assert j["experiment_wide_error_rate_claimed"] == "none" and set(j["families"]) == {"Wt", "U"}
    assert j["no_swap_time_individuals"] == SYN[:2]
    assert j["families"]["U"]["direction"] == "two_sided" and j["families"]["Wt"]["direction"] == "one_sided"
    assert j["birth_margin_strata_counts"]["A"]["active"]["no_tau"] == 2
    text = json.dumps(j)
    assert not any(k in text for k in ('"total', '"sum', '"combined', '"difference', '"ratio', '"both_families', '"Wt_minus'))


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
                          "started_at": "t", "experiment": "0029", "kind": PROTOCOL["kind"], "mode": "synthetic"})
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
    for mode, seeds in (("synthetic", [22001]), ("synthetic", [22300]), ("synthetic", [22101]), ("smoke", [22201]),
                        ("formal", [22021]), ("formal", [21001]), ("synthetic", [GUARD_SEEDS[0], GUARD_SEEDS[0]]),
                        ("synthetic", [])):
        with pytest.raises(ERR):
            R.execute(mode, seeds, out, repo, head, runner=_dummy, executor_factory=SerialExecutor)
    with pytest.raises(ERR, match="measurement-commit"):
        R.execute("formal", [22001], out, repo, None, runner=_dummy, executor_factory=SerialExecutor)
    with pytest.raises(ERR, match="指定した commit"):
        R.execute("formal", [22001], out, repo, "1" * 40, runner=_dummy, executor_factory=SerialExecutor)
    assert not (out / G.SEEDS_DIR).exists() or not any((out / G.SEEDS_DIR).iterdir())
    (G.seed_dir(out, 22300)).mkdir(parents=True)
    (G.seed_dir(out, 22300) / G.START).write_text("{}", encoding="utf-8")
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
    path = Path(os.environ["ANIMA_0029_TIMING_DIR"]) / f"{seed}.json"
    path.write_text(json.dumps({"seed": seed, "pid": os.getpid(), "t0": t0, "t1": t1}), encoding="utf-8")
    return {"seed": seed}


@pytest.mark.skipif(__import__("multiprocessing").get_start_method(allow_none=False) != "fork",
                    reason="テスト関数を子プロセスへ渡すのに fork が要る（本番の run.py は既定の runner を使う）")
def test_real_processes_never_exceed_two_at_once(repo, tmp_path, monkeypatch) -> None:
    timing = tmp_path / "timing"
    timing.mkdir()
    monkeypatch.setenv("ANIMA_0029_TIMING_DIR", str(timing))
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


# ---- 9. 解析：20 個体の完全性・invalid なら判定しない・一度だけ（README §4・§7・§9）---------------------------------------

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
    """同じ 20 個体を NOTAU の Plan（τ の窓を 1 Pulse に狭めた Plan）で execute したフォルダ（τ がない個体と τ がある個体が混ざる）。"""
    return _folder(tmp_path_factory, "notau20", notau_plan())


def _copy(folder, tmp_path) -> Path:
    out = tmp_path / "copy"
    shutil.copytree(folder[1], out, ignore=shutil.ignore_patterns(G.LOCK))
    return out


def _forbidden_keys(report: dict) -> set:
    """判定の量・現象に関する数値の鍵。invalid・smoke の report には出ない。"""
    text = json.dumps(report)
    return {k for k in ('"N"', '"Delta_AB"', '"Delta_AC"', '"D"', '"h_Ca"', '"h_O"', '"h_M"', '"h_OM"', '"per_seed"',
                        '"spike_counts"', '"silent_units"', '"families"', '"O_Delta_AB_above"', '"frozen_per_judgment"',
                        '"swap_time"', '"tau_exists"', '"no_swap_time_individuals"', '"birth_margin_strata"',
                        '"not_applicable"', '"tau"') if k in text}


def test_complete_valid_records_give_one_judgment_per_family(full_folder, tmp_path) -> None:
    out = _copy(full_folder, tmp_path)
    report = A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
    assert report["records"]["state"] == "complete" and report["valid"] and report["invalid_seeds"] == []
    assert report["count_arithmetic"] == "evaluated"
    assert report["analysis_commit"] == report["records"]["measurement_commit"] == _git(full_folder[0], "rev-parse", "HEAD")
    j = report["judgment"]
    assert set(j["families"]) == {"Wt", "U"} and j["experiment_wide_error_rate_claimed"] == "none"
    for f, fam in j["families"].items():
        assert fam["family"] == f and fam["n"] == 20 and fam["main_judgments"] == list(ALIGN.JUDGMENTS)
        for J in ALIGN.JUDGMENTS:
            stat = ALIGN.STATISTIC[J]
            h = sum(v["individual"]["events"][f][ALIGN.EVENT[f][J]] for v in report["per_seed"].values())
            assert fam[J][stat] == h and fam[J]["holds"] == (h >= ALIGN.HOLDS_MIN[f][J])
            assert len(fam[J]["clopper_pearson_95_of_h_over_n"]) == 2
    assert len(report["per_seed"]) == 20 and j["no_swap_time_individuals"] == []
    assert report["preregistration_corrections"] == A.corrections_applied()
    for s in SYN:                                     # 訂正 C1：raw の events は null、report の events は §4.1 の真偽
        raw = json.loads(gzip.decompress((G.seed_dir(out, s) / G.RAW).read_bytes()))
        assert raw["run"]["swap"]["tau_exists"] is True and raw["run"]["swap"]["events"] is None
        ind = report["per_seed"][str(s)]["individual"]
        assert ind["not_outside_reason"] is None and all(
            isinstance(v, bool) for f in ("Wt", "U") for v in ind["events"][f].values())
        assert {f: tuple(ind["events"][f]) for f in ("Wt", "U")} == W.EVENTS
    assert all(len(fam[J]["clopper_pearson_95_of_h_over_n"]) == 2 for fam in j["families"].values() for J in ALIGN.JUDGMENTS)
    assert all(set(st.values()) == {"pass"} for st in report["check_results"].values())
    assert json.loads((out / A.REPORT).read_text())["judgment"] == j
    with pytest.raises(ERR, match="既にある"):
        A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
    assert [json.loads(x)["event"] for x in (out / A.LOG).read_text().splitlines()] == ["started", "completed"]


def test_notau_5_no_tau_individuals_are_completed_and_counted_as_not_outside(notau_folder, tmp_path) -> None:
    """(5) τ がない個体は、実行の道具で completed として保存され（seed の状態・終了の記録）、raw からの再検証で valid のまま
    集計に入り、8 つの事象が false、h の分母は 20 のまま。入れ替えに固有の確認は not_applicable（失敗ではない）。"""
    plan = notau_plan()
    repo, folder = notau_folder
    no_tau = []
    for s in SYN:
        assert G.seed_status(folder, s) == ("completed", [])
        assert G.read_seed(folder, s)["finish"]["status"] == "completed"
        raw = json.loads(gzip.decompress((G.seed_dir(folder, s) / G.RAW).read_bytes()))
        if raw["run"]["swap"]["tau_exists"] is False:
            no_tau.append(s)
            assert raw["run"]["swapped_bodies"] == [] and raw["run"]["control_bodies"] == []
    assert SYN[0] in no_tau and 0 < len(no_tau) < 20, no_tau                 # 両方の場合が混ざる
    out = _copy(notau_folder, tmp_path)
    report = A.publish(out, "synthetic", plan=plan, seeds=SYN, repo=repo)
    assert report["valid"] and report["invalid_seeds"] == [] and report["records"]["state"] == "complete"
    na = set(PROTOCOL["checks"]["no_tau"]["not_applicable"])
    for s in SYN:
        st = report["check_results"][str(s)]
        assert "fail" not in st.values()
        assert ({k for k, v in st.items() if v == "not_applicable"} == na) == (s in no_tau)
    j = report["judgment"]
    assert j["no_swap_time_individuals"] == no_tau
    for s in no_tau:
        ind = report["per_seed"][str(s)]["individual"]
        assert ind["events"] == {f: dict.fromkeys(W.EVENTS[f], False) for f in ("Wt", "U")}
        assert ind["not_outside_reason"] == "no_tau" and ind["auxiliary"]["frozen_per_judgment"] is None
    for f, fam in j["families"].items():
        assert fam["n"] == 20 and fam["auxiliary"]["no_tau_individuals"] == len(no_tau)
        for J in ALIGN.JUDGMENTS:
            h = sum(report["per_seed"][str(s)]["individual"]["events"][f][ALIGN.EVENT[f][J]] for s in SYN if s not in no_tau)
            assert fam[J][ALIGN.STATISTIC[J]] == h
    strata = j["birth_margin_strata_counts"]
    assert all(sum(strata[r][k]["no_tau"] for k in ALIGN.STRATA) == len(no_tau) for r in W.ROLES)
    assert all(sum(strata[r][k]["individuals"] for k in ALIGN.STRATA) == 20 for r in W.ROLES)


def test_notau_5_a_tampered_no_tau_record_makes_the_experiment_invalid(notau_folder, tmp_path) -> None:
    """(4)・(5) を集計の側で：τ がない個体の raw の根拠を改ざんすると、その個体が invalid になり、判定をしない。"""
    out = _copy(notau_folder, tmp_path)

    def tamper(run):
        run["swap"]["window_witness"][0]["unit"] = "s9"
    _rewrite_raw(out, SYN[0], tamper)
    report = A.analyze(out, "synthetic", notau_plan(), SYN, repo=notau_folder[0])
    assert not report["valid"] and report["invalid_seeds"] == [SYN[0]] and report["judgment"] is None
    assert report["check_results"][str(SYN[0])]["swap_time_rule"] == "fail"


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
        _control(run, "null_swap")["states"][str(SMALL.body_end)]["units"]["s1"][3] += 1
    _rewrite_raw(out, bad, tamper)
    report = A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
    assert report["records"]["state"] == "complete" and not report["valid"]
    assert report["invalid_seeds"] == [bad] and report["judgment"] is None
    assert set(report["checks"][str(bad)]) == {"null_swap_identity"}
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
        run["plan"]["delay"] = 81
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


def test_smoke_analysis_never_computes_quantities_nor_shows_tau(notau_folder, tmp_path, monkeypatch) -> None:
    """smoke（操作の確認だけ）：判定の量を計算する関数は一度も呼ばれず、report に判定の量も現象に関する数値（τ の値・τ の有無）も
    ない。確認の結果は fail か ok だけ（pass と not_applicable を区別しない）。τ がない個体を含む 20 個体を smoke の形に読み替えて
    確かめる（smoke の seed は使わない）。"""
    out = _copy(notau_folder, tmp_path)
    _as_smoke(out)

    def boom(*a, **k):
        raise AssertionError("smoke で判定の量を計算した")
    for name in ("body_quantities", "quantities_for_seed", "individual", "wt_events", "u_events", "family_judgment", "judgment",
                 "natural_events", "birth_margins", "rank", "frozen", "strata_counts"):
        monkeypatch.setattr(A, name, boom)
    monkeypatch.setattr(A, "expected_seeds", lambda mode: list(SYN))
    monkeypatch.setattr(A.W, "plan_from", lambda protocol: notau_plan())
    report = A.analyze(out, "smoke", repo=notau_folder[0])
    assert report["valid"] and report["judgment"] is None and report["count_arithmetic"] == "evaluated"
    assert _forbidden_keys(report) == set()
    assert all(set(st.values()) == {"ok"} for st in report["check_results"].values())
    assert set(report) == {"experiment", "kind", "mode", "seeds", "plan", "records", "analysis_commit", "valid",
                           "invalid_seeds", "count_arithmetic", "checks", "checks_evaluated", "check_results", "judgment", "note",
                           "preregistration_corrections"}
    for s in SYN:                                     # 訂正 C1：smoke の raw に、τ がある個体の判定の量（事象）は保存されていない
        raw = json.loads(gzip.decompress((G.seed_dir(out, s) / G.RAW).read_bytes()))
        assert raw["run"]["swap"]["events"] is None or raw["run"]["swap"]["events"] == W.no_tau_events()


def test_report_destination_isolation(tmp_path, monkeypatch) -> None:
    root = tmp_path / "data" / "experiments"
    own = root / "0029"
    own.mkdir(parents=True)
    monkeypatch.setattr(A, "DATA_ROOT", root)
    monkeypatch.setattr(A, "OWN_DIR", own)
    assert A.report_destination(own, "formal") == own.resolve() / A.REPORT
    for folder, mode in ((root / "0028", "formal"), (tmp_path / "x", "formal"), (own, "smoke"), (root / "0028", "smoke"),
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
    for args in (("formal", SMALL, SYN), ("smoke", SMALL, None), ("synthetic", None, None), ("synthetic", SMALL, [22001]),
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
