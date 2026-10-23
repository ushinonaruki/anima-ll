"""実験 0031 の道具の契約テスト（確定した事前登録 v0.1 の README §0〜§14、protocol.yaml）。

本番の seed（24001〜24020）・smoke の seed（24101〜24106）は使わない（実行もしない）。合成の契約テスト専用の範囲
（24201〜24299）だけを使う。合成の個体は、本番と同じ道具（world.measure_seed）・同じ式で、値だけを小さくした Plan
（SMALL：試行 3、遅れ 80。主の区間の長さは式どおり 3 × 60 ＝ 180、τ の窓は式どおり主の区間の直前の 60 の Pulse 201〜260。
試行の数・遅れは 0029 の契約テストと同じ値。遅れ 80 は τ の窓が経験の後に収まるため）で実物の runtime を通して作る。
結果を見て Plan・seed を選んでいない（seed は範囲の最初から順に使う）。

τ がない個体（README §2.6）の契約テストのためだけに、SMALL の τ の窓を 1 Pulse に狭めた Plan（NOTAU）も使う。その Pulse は、
24201 の SMALL の自然な本体が窓の中で発火した Pulse のうち最後のもの（239。どれかの本体が発火した Pulse なので、24201 では τ が
なくなる）。0030 の契約テストと同じ選び方（テストの中で決定的に求める）。自然な本体の軌道は窓に依らないので、同じ seed の自然な
本体は SMALL と NOTAU で同じになる。NOTAU の 20 個体に、τ がない個体と τ がある個体が両方含まれることを確かめてから使う。

実物の runtime の点の計算の確かめ（§6）には、SYN の中で最初の「どれかの受け手でドナーの D の値が 2 つ以上ある」個体を使う
（テストの中で決定的に求める。凍結していない受け手で、同じ値の多い順位の点を確かめるため）。

使った合成の seed（PR に開示）：
- 24201〜24220：SMALL と NOTAU の Plan で実物の runtime を通した 20 個体ずつ（確認の再検証・改ざんの検出・合成の集計の通し）
- 24221〜24240：一度限りの実行の契約（dummy の計算。runtime を使わない）
- 24241〜24250：並列数の契約（実際のプロセス。dummy の計算）
- 24299：可塑性の再生の照合と、点・入れ子の性質の確かめに使う乱数の流れの名前だけ（runtime の個体は作らない）
- 本番の Plan（試行 200）での W の札の列の作り方の確認には 24201〜24206 の名前を使う（札の列を作るだけで、runtime の個体は作らない）

ご指示の点（ChatGPT のレビュー #5633052640 の後の指示）：順位の点の同値の扱い（§6）、All ⊆ Agg の機械的な検査（§6・§9）、
共通の τ の扱い（§4）、105 本体と 10 の確認の本体の操作の確認（§4）、raw の再検証（§4・§5・§9）、smoke の盲検（§9）。
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
EXP = ROOT / "experiments" / "0031_multi_recipient_weight_swap"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))
PREREGISTRATION_MERGE = "0c6664d6349ac373fa8bfdcdeff0da466847a06a"   # PR #133 のマージ（README・protocol の確定）
SYN = list(range(24201, 24221))
GUARD_SEEDS = list(range(24221, 24241))
POOL_SEEDS = list(range(24241, 24251))
TOOLS = ("world.py", "run.py", "analyze.py", "alignment.py", "guard.py")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W = _load("world_0031_test", EXP / "world.py")
G = _load("guard_0031_test", EXP / "guard.py")
A = _load("analyze_0031_test", EXP / "analyze.py")
R = _load("run_0031_test", EXP / "run.py")
sys.modules[R.__name__] = R          # 実際のプロセスへ compute_and_write を渡すため（本番では run.py が __main__）
ALIGN = _load("alignment_0031_test", EXP / "alignment.py")
SMALL = W.make_plan(PROTOCOL, 3, 80)
# run.py・analyze.py はそれぞれ guard.py を読み込むので、GuardError のクラスは 3 つある（どれも同じ契約の拒否）
ERR = (G.GuardError, R.G.GuardError, A.G.GuardError)
UNITS = ("s1", "s2", "s3")
RECIPIENTS = tuple(f"W{i}" for i in range(20, 25))
DONORS = ("O", "M") + tuple(f"W{i}" for i in range(1, 20))
REFERENCE = DONORS[2:]
EVENTS = ("O_Delta_AB_above", "O_above", "M_below", "O_and_M_split")


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


@functools.cache
def _measured(seed: int, plan) -> str:
    return json.dumps(_raw(W.measure_seed(PROTOCOL, seed, plan)))


def measured(seed: int, plan=SMALL) -> dict:
    """実物の runtime を通した合成の個体の生の記録（同じ seed・Plan は一度だけ計算して使い回す。返すのは複製）。"""
    return json.loads(_measured(seed, plan))


@pytest.fixture(scope="module")
def syn() -> dict:
    return measured(SYN[0])


@functools.cache
def notau_plan() -> "W.Plan":
    """SMALL の τ の窓を、24201 の SMALL の自然な本体が窓の中で発火した最後の Pulse の 1 つに狭めた Plan（τ がない個体を作るため）。"""
    run = measured(SYN[0])["run"]
    lo, hi = SMALL.swap_window
    fired = sorted({p for rec in run["natural_bodies"].values() for ps in rec["spikes"].values() for p in ps if lo <= p <= hi})
    assert fired, "SMALL の τ の窓に、24201 の自然な本体の発火がない"
    return dataclasses.replace(SMALL, swap_window=(fired[-1], fired[-1]))


@pytest.fixture(scope="module")
def notau() -> dict:
    return measured(SYN[0], notau_plan())


def _checks(data: dict, seed: int = SYN[0], plan=SMALL) -> dict:
    return {k: v for k, v in A.check_seed(data, "synthetic", seed, plan).items() if v}


def _tampered(data, f, plan=SMALL, seed=SYN[0]) -> dict:
    data = copy.deepcopy(data)
    f(data["run"])
    return _checks(data, seed, plan)


def _mirror(f, plan=SMALL):
    """入れ替えた直後の全状態を改ざんする関数を包む：τ が主の区間の始まりの 1 つ前（SMALL では 260）なら、その時点の全状態は
    入れ替えた直後の全状態と同じはずなので（構造の確認）、改ざんをその時点の記録にも写す（構造の確認ではなく、目的の確認を試すため）。"""
    def g(run):
        f(run)
        tau = run["swap"]["tau"]
        if tau == plan.pre_main:
            for rec in run["swapped_bodies"] + run["control_bodies"]:
                rec["states"][str(tau)] = copy.deepcopy(rec["state_tau"])
    return g


def _sw(run, r: str, d: str) -> dict:
    return next(x for x in run["swapped_bodies"] if (x["recipient"], x["donor"]) == (r, d))


def _ct(run, r: str, kind: str) -> dict:
    return next(x for x in run["control_bodies"] if (x["recipient"], x["name"]) == (r, kind))


# ---- 1. protocol と道具の対応・固定 -------------------------------------------------------------------------------

def test_protocol_and_tools_are_aligned() -> None:
    ALIGN.check(PROTOCOL)


def _git_show(rev: str, path: str) -> bytes:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{path}"], capture_output=True, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git の履歴がない環境")


def test_preregistration_files_are_unchanged_since_the_merge() -> None:
    """protocol.yaml は事前登録の確定（PR #133 のマージ）からバイト単位で変わっていない。README は確定した §0〜§14 が
    そのまま先頭に残っている（結果は後ろの節に追記する：README §14 の 4）。"""
    rel = f"experiments/{EXP.name}"
    assert (EXP / "protocol.yaml").read_bytes() == _git_show(PREREGISTRATION_MERGE, f"{rel}/protocol.yaml")
    assert (EXP / "README.md").read_bytes().startswith(_git_show(PREREGISTRATION_MERGE, f"{rel}/README.md"))


def test_runtime_core_and_other_experiments_are_unchanged_from_main() -> None:
    """0031 の道具を変える branch では、本体（src/）・設計（config/）・ほかの実験・0031 の事前登録の文書を同時に変えない
    （main との差分）。0031 の道具を変えない branch（後の PR）では確かめない（この PR の範囲の確認なので、後の作業を止めない）。"""
    try:
        base = subprocess.run(["git", "-C", str(ROOT), "merge-base", "HEAD", "origin/main"], capture_output=True,
                              text=True, check=True).stdout.strip()
        diff = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", base, "--", "src", "config", "experiments"],
                              capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git の履歴がない環境")
    tools = {f"experiments/{EXP.name}/{n}" for n in TOOLS}
    if not set(diff) & tools:
        pytest.skip("この branch は 0031 の道具を変えていない")
    assert set(diff) <= tools, sorted(set(diff) - tools)


FORBIDDEN = [r'"00([0-2]\d|30)"', r"'00([0-2]\d|30)'", r"data/experiments/00([0-2]\d|30)",
             r"00([0-2]\d|30)-(shuffle|within)", r"experiments/00(1[3-9]|2\d|30)_",
             r"experiments/0012_passive_world/(?!neuroarchitecture\.yaml)",
             r"(world|guard|run|analyze|alignment)_00([0-2]\d|30)"]
SEED_NUMBERS = r"\b(1[3-9]|2[0-3])[0-2]\d\d\b"   # 0020〜0030 の seed の範囲（13001〜23299）の数


def _code(name: str) -> str:
    """道具のコード（説明の文字列・コメントは除く。alignment.py の使用済みの seed の一覧 SEEN と、protocol を写した固定値の文字列は
    重なりの確認・照合の記録なので除く）。"""
    src = (EXP / name).read_text(encoding="utf-8")
    src = re.sub(r"SEEN = \(.*?\)\)\)\n", "", src, flags=re.DOTALL)
    src = re.sub(r'""".*?"""', "", src, flags=re.DOTALL)
    return "\n".join(line.split("#")[0] for line in src.splitlines())


def test_tools_hold_no_earlier_experiment_references() -> None:
    """道具は、ほかの実験の ID・出力先・乱数の流れの名前・道具（world.py など）を参照しない。0023〜0030 の道具も読み込まない。
    脳の設計図は protocol の brain.manifest（0014〜0030 と同じ共有の設計図）だけを読み、alignment.py がその名前を確かめる。"""
    for name in TOOLS:
        code = _code(name)
        for pat in FORBIDDEN:
            assert not re.search(pat, code), (name, pat)
        assert "_load(" not in code or all("experiments/" not in line for line in code.splitlines() if "_load(" in line), name
        assert not re.search(SEED_NUMBERS, code), (name, "0020〜0030 の seed の範囲の数")


def test_the_reference_scan_detects_leftovers() -> None:
    for leftover in ('EXPERIMENT = "0030"', 'OUT = "data/experiments/0030"', 'RNG = "0030-within-trial-{i}:{seed}"',
                     '_load("w", ROOT / "experiments/0030_post_experience_freeze_and_count_bound/world.py")',
                     '"experiments/0029_window_start_block_swap/world.py"', '"experiments/0012_passive_world/world.py"',
                     "world_0030_for_x", "guard_0029"):
        assert any(re.search(p, leftover) for p in FORBIDDEN), leftover
    for leftover in ("SEEDS = range(23001, 23021)", "SYN = range(22201, 22251)", "seed = 21101", "x = 13001"):
        assert re.search(SEED_NUMBERS, leftover), leftover
    for fine in ("first = 13501", "end = 25500", "lo = 13441", "hi = 13500", "seed = 24001", 'EXPERIMENT = "0031"'):
        assert not re.search(SEED_NUMBERS, fine) and not any(re.search(p, fine) for p in FORBIDDEN), fine
    src = (EXP / "alignment.py").read_text(encoding="utf-8")
    assert "range(23001" in src and "range(23001" not in _code("alignment.py") and {23001, 23299, 22299} <= ALIGN.SEEN


def test_tools_read_identity_from_this_protocol() -> None:
    ex = PROTOCOL["execution"]
    assert R.EXPERIMENT == A.EXPERIMENT == W.EXPERIMENT == PROTOCOL["experiment"] == ex["experiment_id"] == "0031"
    assert str(R.OUT_DIR) == str(A.DEFAULT_DIR) == ex["output_dir"]
    assert str(R.PROTOCOL_PATH) == str(A.PROTOCOL_PATH) == str(W.PROTOCOL_PATH) == ex["protocol_path"]
    assert W.RNG_SHUFFLE == PROTOCOL["conditions"]["within_trial_shuffles"]["rng"] == "0031-within-trial-{i}:{seed}"
    assert PROTOCOL["brain"]["manifest"] == "experiments/0012_passive_world/neuroarchitecture.yaml"
    assert W.RECIPIENTS == A.RECIPIENTS == RECIPIENTS and W.DONORS == A.DONORS == DONORS and W.REFERENCE == A.REFERENCE == REFERENCE
    for mode, key in (("formal", "seeds"), ("smoke", "smoke_seeds"), ("synthetic", "synthetic_seeds")):
        assert list(R.allowed_seeds(mode)) == A.expected_seeds(mode) == list(
            range(PROTOCOL[key]["first"], PROTOCOL[key]["last"] + 1))


def test_tools_use_only_public_core_interfaces() -> None:
    """README §2.5：入れ替えは Core の公開の import_state だけで行う。道具のコードは Core の内部の欄に触れない。"""
    for name in TOOLS:
        code = _code(name)
        assert not re.search(r"\._(state|plastic|weights|keys|spec|rule|dynamics|output|brain_state|pulse)\b", code), name
        assert "amplitude_ratio" not in code, name
    code = _code("world.py")
    assert "u.import_state(" in code and "app.connections.import_state(" in code


# ---- 2. Plan・刺激（README §1・§2.1・§2.2）--------------------------------------------------------------------------

def test_plan_from_protocol_is_the_registered_timeline() -> None:
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
                 lambda p: p["timeline"]["swap_window"].update(first="count_window_main.first - 2 * trials.every"),
                 lambda p: p["timeline"]["swap_window"].update(last="count_window_main.first"),
                 lambda p: p["timeline"].update(body_runs_to="swap_window.last"),
                 lambda p: p["timeline"].update(delay="3 * adaptation_tau / pulse_interval_seconds")):
        protocol = copy.deepcopy(PROTOCOL)
        edit(protocol)
        with pytest.raises(ValueError):
            W.plan_from(protocol)
    for window in ((170, 200), (250, 261), (240, 239)):          # 経験の中・主の区間に入る・空
        with pytest.raises(ValueError):
            W.check_plan(dataclasses.replace(SMALL, swap_window=window))
    with pytest.raises(ValueError):
        W.make_plan(PROTOCOL, 3, 30)                              # 窓（幅 60）が経験の中に入る


def _balanced(labels, plan) -> bool:
    at = dict(labels)
    return all(sorted(at.get(t, "") for t in slots) == ["A", "B", "C"] for slots in W.trial_slots(PROTOCOL, plan))


def test_schedules_follow_the_protocol() -> None:
    """O・M・W_i（0025・0027〜0030 と同じ作り方）。W は 24（W1〜W19 は参照のドナー、W20〜W24 は受け手）。"""
    plan = W.plan_from(PROTOCOL)
    o = W.ordered_labels(PROTOCOL, plan)
    m = W.labels_of(PROTOCOL, plan, SYN[0], "M")
    assert len(o) == 600 and o[:3] == [(1, "A"), (3, "B"), (31, "C")] and o[-1] == (11971, "C") and _balanced(o, plan)
    assert m[:3] == [(1, "A"), (3, "C"), (31, "B")] and [t for t, _ in m] == [t for t, _ in o] and _balanced(m, plan)
    for seed in SYN[:6]:
        seen = set()
        for i in range(1, 25):
            w = W.labels_of(PROTOCOL, plan, seed, f"W{i}")
            rnd, expected = random.Random(f"0031-within-trial-{i}:{seed}"), []
            for k in range(200):
                roles = ["A", "B", "C"]
                rnd.shuffle(roles)
                t = 1 + 60 * k
                expected += [(t, roles[0]), (t + 2, roles[1]), (t + 30, roles[2])]
            assert w == expected and [t for t, _ in w] == [t for t, _ in o] and _balanced(w, plan) and w not in (o, m)
            seen.add(tuple(x for _, x in w))
        assert len(seen) == 24
    assert W.BODIES == ("O", "M") + tuple(f"W{i}" for i in range(1, 25)) and set(W.RECIPIENTS) | set(W.DONORS) == set(W.BODIES)
    assert not set(W.RECIPIENTS) & set(W.DONORS)


def test_alignment_refuses_drift() -> None:
    cases = {
        "時間の流れ": [lambda p: p["timeline"].update(delay="10 * adaptation_tau / pulse_interval_seconds"),
                      lambda p: p["timeline"]["swap_window"].update(first="count_window_main.first - 30")],
        "条件": [lambda p: p["conditions"].pop("M"),
                 lambda p: p["conditions"]["within_trial_shuffles"].update(count=25),
                 lambda p: p["conditions"]["within_trial_shuffles"].update(rng="0031-shuffle-{i}:{seed}")],
        "介入": [lambda p: p["intervention"].update(recipients=["W20", "W21", "W22", "W23"]),
                 lambda p: p["intervention"]["recipients"].append("W19"),
                 lambda p: p["intervention"]["swap_time"].update(common_to_all_recipients=False),
                 lambda p: p["intervention"]["block"].update(replace=["connections.weight", "connections.pre_trace"]),
                 lambda p: p["intervention"]["donors"].remove("M"),
                 lambda p: p["intervention"].update(plasticity_after_swap=False)],
        "判定の決まり": [lambda p: p["judgment"]["per_family"]["All"]["J_Ca"].update(holds_if="h_Ca >= 3"),
                         lambda p: p["judgment"]["per_family"]["Agg"]["J_OM"].update(per_individual_null_probability_at_most="2/420"),
                         lambda p: p["judgment"]["families"]["All"].update(direction="two_sided"),
                         lambda p: p["judgment"]["per_family"]["alpha_split"].update(J_Ca=0.02),
                         lambda p: p["judgment"].update(experiment_wide_error_rate_claimed="none"),
                         lambda p: p["judgment"].update(nesting="none"),
                         lambda p: p["judgment"].update(within_individual_dependence="per_recipient_judgments")],
        "主・補助の量": [lambda p: p["quantities"]["primary"]["per_individual"]["All"].pop("O_and_M_split"),
                         lambda p: p["quantities"]["scores"].update(total_score="S^x(d) = mean over recipients r of s^x_r(d)"),
                         lambda p: p["quantities"]["not_used"].remove("per_recipient_judgments")],
        "記録の項目": [lambda p: p["records"].update(no_judgment_quantities_in_raw=False),
                       lambda p: p["records"]["no_tau"].update(swapped_bodies=None)],
        "操作の確認": [lambda p: p["checks"]["no_tau"]["not_applicable"].append("no_clipping"),
                       lambda p: p["checks"]["exact"].remove("null_swap_identity"),
                       lambda p: p["checks"].update(smoke_report_check_values=["fail", "pass", "not_applicable"])],
        "seed": [lambda p: p.update(seeds={"first": 23001, "last": 23020})],
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


# ---- 3. τ の規則・根拠・入れ替える欄（README §2.2〜§2.6）---------------------------------------------------------------

def test_find_swap_time_is_the_last_quiet_pulse_of_the_window() -> None:
    lo, hi = 10, 20
    sp = {"O": {"s1": [11, 18]}, "W24": {"s2": [19, 20]}}
    assert W.find_swap_time(sp, lo, hi) == 17
    full = {"O": {"s1": list(range(lo, hi + 1, 2))}, "W22": {"s3": list(range(lo + 1, hi + 1, 2))}}
    assert W.find_swap_time(full, lo, hi) is None
    assert W.find_swap_time({"O": {}}, lo, hi) == hi


def test_window_witness_is_the_first_firing_in_the_fixed_order() -> None:
    sp = {"O": {"s3": [10]}, "M": {"s1": [10, 11]}, "W24": {"s2": [11, 12], "s1": [12]}}
    assert W.window_witness(sp, UNITS, 10, 12) == [
        {"pulse": 10, "body": "O", "unit": "s3"}, {"pulse": 11, "body": "M", "unit": "s1"},
        {"pulse": 12, "body": "W24", "unit": "s1"}]
    with pytest.raises(ValueError):
        W.window_witness(sp, UNITS, 10, 13)


def test_apply_swap_changes_only_the_named_fields() -> None:
    """README §2.4：入れ替えた本体は重みだけ、確認の本体は発火の回数を除くすべてをドナーの値にする。ほかの欄は受け手のまま。"""
    plan = SMALL
    labels = W.labels_of(PROTOCOL, plan, SYN[2], "W21")
    app = W.build(PROTOCOL, labels, SYN[2], "W21", W.ExperimentLog())
    W.advance_to(app, plan.experience_end + 5)
    donor_app = W.build(PROTOCOL, W.labels_of(PROTOCOL, plan, SYN[2], "O"), SYN[2], "O", W.ExperimentLog())
    W.advance_to(donor_app, plan.experience_end + 5)
    donor, before = W.full_state(donor_app), W.full_state(app)
    W.apply_swap(app, donor, W.WEIGHTS)
    after = W.full_state(app)
    assert after["units"] == before["units"] and after["drives"] == before["drives"] and after["deltas"] == before["deltas"]
    for cid, v in after["connections"].items():
        assert v == [donor["connections"][cid][0], before["connections"][cid][1], before["connections"][cid][2]]
    W.apply_swap(app, donor, W.EVERYTHING)
    full = W.full_state(app)
    assert full["connections"] == donor["connections"]
    assert all(full["units"][u][:3] == donor["units"][u][:3] and full["units"][u][3] == before["units"][u][3] for u in UNITS)
    with pytest.raises(ValueError):
        W.apply_swap(app, donor, ((), ("weight", "size")))
    with pytest.raises(ValueError):
        W.apply_swap(app, donor, (("fire_count",), ()))


def test_recipient_rebuilt_at_tau_equals_the_natural_body(syn) -> None:
    """README §2.3・world.py の説明：受け手の τ の状態は、同じ受け手を出生から τ まで進め直して作る。進め直した状態は、
    自然な本体の τ の全状態と同じ（決定論的な力学）。"""
    run = syn["run"]
    tau = run["swap"]["tau"]
    for r in RECIPIENTS:
        app, _ = W.recipient_at(PROTOCOL, SMALL, SYN[0], r, W.labels_of(PROTOCOL, SMALL, SYN[0], r), tau)
        assert json.loads(json.dumps(W.full_state(app))) == run["natural_bodies"][r]["state_tau"]
    with pytest.raises(ValueError):
        W.recipient_at(PROTOCOL, SMALL, SYN[0], "W20", [], SMALL.swap_window[0] - 1)


# ---- 4. τ がある個体：105 本体と 10 の確認の本体を実物の runtime で（README §2.3・§2.4・§7）----------------------------

def test_all_checks_pass_on_a_real_runtime_individual(syn) -> None:
    assert syn["run"]["swap"]["tau_exists"] is True
    assert _checks(syn) == {}
    st = A.check_statuses(A.check_seed(syn, "synthetic", SYN[0], SMALL), A.raw_tau_exists(syn))
    assert set(st.values()) == {"pass"} and set(st) == set(A.CHECK_NAMES) - {A.COUNT_CHECK}
    table, problems = A.count_table(syn["run"], SYN[0], SMALL)
    assert problems == [] and tuple(table["natural"]) == W.BODIES and tuple(table["swapped"]) == RECIPIENTS
    assert all(tuple(table["swapped"][r]) == DONORS for r in RECIPIENTS) and len(table["controls"]) == 10


def test_raw_holds_the_preregistered_items_and_no_judgment_quantities(syn) -> None:
    """README §2.6・§8・protocol の records：自然な 26 本体・入れ替えた 105 本体（受け手の順、その中でドナーの順）・確認の 10 本体。
    raw に判定の量（点・事象）を書かない。"""
    run = syn["run"]
    tau = run["swap"]["tau"]
    assert set(run) == A.RUN_KEYS and run["swap"] == {"tau_exists": True, "tau": tau, "window_witness": None}
    assert SMALL.swap_window[0] <= tau <= SMALL.swap_window[1]
    assert tuple(run["natural_bodies"]) == W.BODIES
    for b, rec in run["natural_bodies"].items():
        assert set(rec) == A.NATURAL_KEYS and rec["state_tau"]["pulse"] == tau
        assert list(rec["states"]) == [str(p) for p in SMALL.snapshots]
    assert [(x["recipient"], x["donor"]) for x in run["swapped_bodies"]] == [(r, d) for r in RECIPIENTS for d in DONORS]
    assert [(x["recipient"], x["name"]) for x in run["control_bodies"]] == [(r, c) for r in RECIPIENTS for c in W.CONTROLS]
    for x in run["swapped_bodies"]:
        assert set(x) == A.SWAPPED_KEYS and x["swap"] == {"tau": tau, "block": "weights", "recipient": x["recipient"], "donor": x["donor"]}
        assert x["sensory"] == [] and min((p for ps in x["spikes"].values() for p in ps), default=tau + 1) > tau
    for x in run["control_bodies"]:
        assert set(x) == A.CONTROL_KEYS and x["swap"] == {"tau": tau, "recipient": x["recipient"], "kind": x["name"]}
    text = json.dumps(run)
    for word in ('"events"', '"scores"', '"total_scores"', '"rank_scores"', '"h_O"', '"Delta_AB"', '"D"', '"k"'):
        assert word not in text, word


def test_common_tau_and_weight_only_composition_on_the_runtime(syn) -> None:
    """共通の τ：どの受け手のどの入れ替えた本体も同じ τ の値で作る。Y_r(d) の入れ替えた直後の状態は、受け手 r の τ の状態の
    重みだけを d の τ の重みにしたもの（痕跡・Unit の状態・発火の回数は r のまま）。同じ受け手の 21 本体は重み以外が同じ。"""
    run = syn["run"]
    nat = run["natural_bodies"]
    tau = run["swap"]["tau"]
    assert {x["swap"]["tau"] for x in run["swapped_bodies"] + run["control_bodies"]} == {tau}
    for r in RECIPIENTS:
        bodies = [_sw(run, r, d) for d in DONORS]
        for x in bodies:
            st, rt, dt = x["state_tau"], nat[r]["state_tau"], nat[x["donor"]]["state_tau"]
            assert st["units"] == rt["units"] and st["drives"] == rt["drives"] == [] and st["deltas"] == 0
            assert {c: v[0] for c, v in st["connections"].items()} == {c: v[0] for c, v in dt["connections"].items()}
            assert {c: v[1:] for c, v in st["connections"].items()} == {c: v[1:] for c, v in rt["connections"].items()}
        assert len({json.dumps({c: v[1:] for c, v in x["state_tau"]["connections"].items()}) for x in bodies}) == 1
    assert len({json.dumps(nat[r]["state_tau"]["units"]) for r in RECIPIENTS}) >= 2   # 背景は受け手によって違う


def test_controls_reproduce_o_and_each_recipient(syn) -> None:
    """全部の入れ替え（受け手ごと）は O の自然な軌道を、入れ替えなし（受け手ごと）はその受け手の自然な軌道を再現する。"""
    run = syn["run"]
    nat = run["natural_bodies"]
    tau = run["swap"]["tau"]
    for r in RECIPIENTS:
        fs, ns = _ct(run, r, "full_swap"), _ct(run, r, "null_swap")
        for u in UNITS:
            assert fs["spikes"].get(u, []) == A.in_range(nat["O"]["spikes"], u, tau + 1, SMALL.body_end)
            assert ns["spikes"].get(u, []) == A.in_range(nat[r]["spikes"], u, tau + 1, SMALL.body_end)
        assert A.without_fire_count(fs["states"][str(SMALL.body_end)]) == A.without_fire_count(nat["O"]["states"][str(SMALL.body_end)])
        assert ns["states"] == {k: nat[r]["states"][k] for k in ns["states"]}


def test_swap_checks_detect_tampering(syn) -> None:
    def weight(run):                                 # Y_W22(M) の重みを W5 のものに（組の和は保つ）
        _sw(run, "W22", "M")["state_tau"]["connections"] = copy.deepcopy(_sw(run, "W22", "W5")["state_tau"]["connections"])
        x = _sw(run, "W22", "M")["state_tau"]["connections"]
        x["s1.main->s2"][0] += 1e-9
        x["s2.main->s1"][0] -= 1e-9
    assert "swap_composition" in _tampered(syn, _mirror(weight))

    def trace(run):                                  # 痕跡は受け手のまま（ドナーのものにしない）
        st = _sw(run, "W21", "O")["state_tau"]
        for cid in st["connections"]:
            st["connections"][cid][1] += 0.5
    assert "swap_composition" in _tampered(syn, _mirror(trace))

    def fire_count(run):
        _sw(run, "W23", "W7")["state_tau"]["units"]["s2"][3] += 1
    assert set(_tampered(syn, _mirror(fire_count))) == {"swap_composition"}

    def record(run):
        _sw(run, "W24", "W3")["swap"]["donor"] = "W4"
    assert set(_tampered(syn, record)) == {"swap_composition"}

    def block(run):
        _sw(run, "W20", "W9")["swap"]["block"] = "units"
    assert set(_tampered(syn, block)) == {"swap_composition"}

    def other_tau(run):                              # 共通の τ：一つの受け手だけ別の τ の記録
        for x in run["swapped_bodies"]:
            if x["recipient"] == "W23":
                x["swap"]["tau"] -= 1
    assert set(_tampered(syn, other_tau)) == {"swap_composition"}

    def control_kind(run):
        _ct(run, "W21", "full_swap")["swap"]["kind"] = "null_swap"
    assert set(_tampered(syn, control_kind)) == {"swap_composition"}

    def drives(run):
        _sw(run, "W20", "O")["state_tau"]["drives"] = [["s1", "s2", 0.005, run["swap"]["tau"]]]
    assert {"swap_composition", "swap_invariants"} <= set(_tampered(syn, _mirror(drives)))

    def full_spike(run):
        sp = _ct(run, "W22", "full_swap")["spikes"]
        sp["s3"] = sorted(set(sp.get("s3", [])) ^ {SMALL.body_end})
    assert "full_swap_reproduces_donor" in _tampered(syn, full_spike)

    def full_fire_count(run):                        # 全部の入れ替えは発火の回数を比べない
        _ct(run, "W22", "full_swap")["states"][str(SMALL.body_end)]["units"]["s1"][3] += 7
    assert _tampered(syn, full_fire_count) == {}

    def null_state(run):
        _ct(run, "W24", "null_swap")["states"][str(SMALL.body_end)]["units"]["s1"][0] += 1e-9
    assert set(_tampered(syn, null_state)) == {"null_swap_identity"}

    def swapped_input(run):
        _sw(run, "W21", "W2")["sensory"].append([SMALL.body_end, "receptor.x1"])
    assert set(_tampered(syn, swapped_input)) == {"input_free_after_experience"}

    def replay(run):
        st = _sw(run, "W20", "W11")["states"][str(SMALL.body_end)]["connections"]
        st["s1.main->s3"][0] += 1e-9
        st["s3.main->s1"][0] -= 1e-9
    assert set(_tampered(syn, replay)) == {"replay_weights_and_traces"}


def test_structure_checks_detect_wrong_layout_and_judgment_fields(syn) -> None:
    edits = {
        "run の判定の量": lambda r: r.update(events={"Agg": {}}),
        "入れ替えた本体の点": lambda r: r["swapped_bodies"][4].update(score=3),
        "swap の events": lambda r: r["swap"].update(events=None),
        "入れ替えた本体の並び": lambda r: r["swapped_bodies"].insert(0, r["swapped_bodies"].pop(21)),
        "入れ替えた本体の欠け": lambda r: r["swapped_bodies"].pop(),
        "確認の本体の欠け": lambda r: r["control_bodies"].pop(3),
        "確認の本体の並び": lambda r: r["control_bodies"].reverse(),
        "自然な本体の欠け": lambda r: r["natural_bodies"].pop("W24"),
        "自然な本体の欄": lambda r: r["natural_bodies"]["W20"].update(total_scores={}),
        "全状態の時点": lambda r: r["swapped_bodies"][7]["states"].pop(str(SMALL.body_end)),
    }
    for name, f in edits.items():
        assert "revalidate_from_raw" in _tampered(syn, f), name
    assert set(_checks(copy.deepcopy(syn), SYN[1])) == {"revalidate_from_raw"}
    assert A.check_seed(syn, "synthetic", SYN[0], W.make_plan(PROTOCOL, 3, 81))["revalidate_from_raw"]
    data = copy.deepcopy(syn)
    data["meta"]["manifest"]["projections"] = []
    assert set(_checks(data)) == {"revalidate_from_raw"}


def _swap_time_problems(data, f, plan=SMALL):
    run = copy.deepcopy(data["run"])
    f(run)
    out = {k: [] for k in A.CHECK_NAMES}
    A._check_swap_time(run, plan, out)
    return out["swap_time_rule"]


def test_swap_time_rule_is_recounted_from_all_26_bodies(syn) -> None:
    tau = syn["run"]["swap"]["tau"]
    assert _swap_time_problems(syn, lambda run: None) == []

    def spike_at_tau_in_a_recipient(run):            # 受け手（W24）の発火も τ の規則に入る
        sp = run["natural_bodies"]["W24"]["spikes"]
        sp["s2"] = sorted(set(sp.get("s2", [])) | {tau})
    assert any("τ に" in p for p in _swap_time_problems(syn, spike_at_tau_in_a_recipient))

    def earlier(run):
        run["swap"]["tau"] = tau - 1
    assert _swap_time_problems(syn, earlier)

    def drives_at_tau(run):
        run["natural_bodies"]["W3"]["state_tau"]["drives"] = [["s1", "s2", 0.005, tau]]
    assert any("駆動か Delta" in p for p in _swap_time_problems(syn, drives_at_tau))


def test_natural_checks_detect_tampering(syn) -> None:
    def m_labels(run):
        run["natural_bodies"]["M"]["labels"] = copy.deepcopy(run["natural_bodies"]["O"]["labels"])
    assert set(_tampered(syn, m_labels)) == {"stimulus_labels"}

    def rng(run):
        run["natural_bodies"]["W22"]["rng"] = f"0031-within-trial-21:{SYN[0]}"
    assert set(_tampered(syn, rng)) == {"stimulus_labels"}

    def birth(run):
        run["natural_bodies"]["W23"]["birth"]["units"]["s1"][0] += 1e-15
    assert set(_tampered(syn, birth)) == {"identical_birth_state_natural_bodies"}

    def late_input(run):
        run["natural_bodies"]["W9"]["sensory"].append([SMALL.experience_end + 5, "receptor.x1"])
    assert set(_tampered(syn, late_input)) == {"input_free_after_experience"}

    def before_state(run):
        run["natural_bodies"]["M"]["before_divergence"]["2"]["units"]["s2"][1] += 1e-15
    assert set(_tampered(syn, before_state)) == {"identical_before_label_divergence"}

    def clip(run):
        run["natural_bodies"]["W6"]["first_stimulus"]["2"]["connections"]["s2.main->s3"][0] = 0.0100001
    assert "no_clipping" in _tampered(syn, clip)


def test_replay_reports_clipping_and_matches_the_runtime_rule() -> None:
    from anima_ll.neuroarchitecture.plasticity import PlasticState, balanced_pair_window
    spec = W.plasticity(PROTOCOL)
    rnd = random.Random(24299)
    sp = {"s1": sorted(rnd.sample(range(1, 400), 60)), "s2": sorted(rnd.sample(range(1, 400), 70))}
    r = A.replay([0.005, 0.0, 0.0], "s1", "s2", sp, 0, 400, (0, 200))
    st = PlasticState(0.005)
    for p in range(1, 401):
        st = balanced_pair_window(st, pre_fired=p in sp["s1"], post_fired=p in sp["s2"], delta_time=1.0, spec=spec)
    assert r["end"] == [st.weight, st.pre_trace, st.post_trace] and r["clipped"] == [] and r["at"][0] == [0.005, 0.0, 0.0]
    big = A.replay([0.0099, 500.0, 0.0], "s1", "s2", {"s2": [1]}, 0, 1)
    assert big["clipped"] == [1] and big["end"][0] == spec.w_max


# ---- 5. τ がない個体の契約（README §2.6）-----------------------------------------------------------------------------

def test_notau_1_raw_has_the_registered_form(notau) -> None:
    plan = notau_plan()
    run = notau["run"]
    lo, hi = plan.swap_window
    assert run["swap"]["tau_exists"] is False and run["swap"]["tau"] is None and set(run["swap"]) == {"tau_exists", "tau", "window_witness"}
    assert [w["pulse"] for w in run["swap"]["window_witness"]] == list(range(lo, hi + 1))
    assert run["swapped_bodies"] == [] and run["control_bodies"] == []
    assert all(rec["state_tau"] is None for rec in run["natural_bodies"].values())
    assert "events" not in json.dumps(run)


def test_notau_natural_bodies_are_the_same_as_with_tau(syn, notau) -> None:
    for b in W.BODIES:
        a, n = syn["run"]["natural_bodies"][b], notau["run"]["natural_bodies"][b]
        assert {k: v for k, v in a.items() if k != "state_tau"} == {k: v for k, v in n.items() if k != "state_tau"}


def test_notau_2_swap_checks_are_not_applicable_and_not_invalid(notau) -> None:
    plan = notau_plan()
    reasons = A.check_seed(notau, "synthetic", SYN[0], plan)
    assert not any(reasons.values())
    st = A.check_statuses(reasons, A.raw_tau_exists(notau))
    na = set(PROTOCOL["checks"]["no_tau"]["not_applicable"])
    assert {k for k, v in st.items() if v == "not_applicable"} == na
    assert {k for k, v in st.items() if v == "pass"} == set(A.CHECK_NAMES) - {A.COUNT_CHECK} - na
    table, problems = A.count_table(notau["run"], SYN[0], plan)
    assert problems == [] and table["swapped"] == {} and table["controls"] == {} and tuple(table["natural"]) == W.BODIES
    assert A.check_statuses({**reasons, "swap_composition": ["x"]}, False)["swap_composition"] == "fail"


def test_notau_3_the_no_tau_proof_holds_and_tampering_the_witness_fails(notau) -> None:
    plan = notau_plan()
    assert _swap_time_problems(notau, lambda run: None, plan) == []
    w0 = notau["run"]["swap"]["window_witness"][0]
    t = w0["pulse"]
    fired_at_t = [(b, u) for b in W.BODIES for u in UNITS if t in notau["run"]["natural_bodies"][b]["spikes"].get(u, [])]
    assert fired_at_t[0] == (w0["body"], w0["unit"])
    absent = next((b, u) for b in W.BODIES for u in UNITS if (b, u) not in fired_at_t)
    edits = {"存在しない発火": lambda run: run["swap"]["window_witness"][0].update(body=absent[0], unit=absent[1]),
             "Pulse の欠け": lambda run: run["swap"]["window_witness"].pop(),
             "Pulse のずれ": lambda run: run["swap"]["window_witness"][0].update(pulse=t + 1),
             "欄の形": lambda run: run["swap"]["window_witness"][0].update(extra=1)}
    if len(fired_at_t) > 1:
        edits["最初ではない"] = lambda run: run["swap"]["window_witness"][0].update(body=fired_at_t[1][0], unit=fired_at_t[1][1])
    for name, f in edits.items():
        assert set(_tampered(notau, f, plan)) == {"swap_time_rule"}, name

    def silence(run):
        for rec in run["natural_bodies"].values():
            for u, xs in rec["spikes"].items():
                rec["spikes"][u] = [p for p in xs if p != t]
    assert any("どの自然な本体も発火していない" in p for p in _swap_time_problems(notau, silence, plan))


def test_notau_4_inconsistent_raw_is_invalid(syn, notau) -> None:
    plan = notau_plan()
    for name, f in {"入れ替えた本体がある": lambda run: run["swapped_bodies"].append({"recipient": "W20"}),
                    "確認の本体がある": lambda run: run["control_bodies"].append({"name": "full_swap"}),
                    "τ が null でない": lambda run: run["swap"].update(tau=plan.swap_window[0]),
                    "window_witness がない": lambda run: run["swap"].update(window_witness=None),
                    "τ の全状態がある": lambda run: run["natural_bodies"]["O"].update(
                        state_tau=run["natural_bodies"]["O"]["states"][str(plan.experience_end)]),
                    "tau_exists が真偽でない": lambda run: run["swap"].update(tau_exists=None),
                    "swap の欄が足りない": lambda run: run["swap"].pop("window_witness"),
                    "tau_exists だけが真": lambda run: run["swap"].update(tau_exists=True)}.items():
        assert "revalidate_from_raw" in _tampered(notau, f, plan), name
    for name, f in {"τ があるのに配列が空": lambda run: run.update(swapped_bodies=[], control_bodies=[]),
                    "τ があるのに根拠がある": lambda run: run["swap"].update(window_witness=[]),
                    "τ が窓の外": lambda run: run["swap"].update(tau=SMALL.swap_window[0] - 1)}.items():
        assert "revalidate_from_raw" in _tampered(syn, f), name

    def fake_no_tau(run):
        lo, hi = SMALL.swap_window
        run["swap"] = {"tau_exists": False, "tau": None,
                       "window_witness": [{"pulse": t, "body": "O", "unit": "s1"} for t in range(lo, hi + 1)]}
        run["swapped_bodies"], run["control_bodies"] = [], []
        for rec in run["natural_bodies"].values():
            rec["state_tau"] = None
    got = _tampered(syn, fake_no_tau)
    assert set(got) == {"swap_time_rule"} and any("どの自然な本体も発火していない" in p for p in got["swap_time_rule"])


def test_notau_individual_events_are_false_and_natural_auxiliaries_are_kept(syn, notau) -> None:
    plan = notau_plan()
    t_nt, _ = A.count_table(notau["run"], SYN[0], plan)
    t_sm, _ = A.count_table(syn["run"], SYN[0], SMALL)
    run = notau["run"]
    nt = A.individual(t_nt, run["natural_bodies"]["O"]["dynamics"], run["roles"]["units"], None)
    sm = A.individual(t_sm, run["natural_bodies"]["O"]["dynamics"], run["roles"]["units"], syn["run"]["swap"]["tau"])
    assert nt["events"] == {f: dict.fromkeys(EVENTS, False) for f in ("Agg", "All")} and nt["not_outside_reason"] == "no_tau"
    for key in ("natural_body_components", "natural_comparison", "birth_margin_strata"):
        assert nt["auxiliary"][key] == sm["auxiliary"][key], key
    assert all(nt["auxiliary"][k] is None for k in PROTOCOL["quantities"]["auxiliary"]["when_no_tau"]["null_with_reason_no_tau"])
    assert nt["auxiliary"]["null_reason"] == "no_tau" and not nt["auxiliary"]["tau_exists"]


# ---- 6. 順位の点・同値の扱い・Agg と All・入れ子の機械的な検査（README §3.2・§4.1・§4.3）-----------------------------------

def test_rank_scores_by_hand_with_ties() -> None:
    """s(d) ＝ Σ_{e≠d} sgn(x(d) − x(e))：同じ値は 0、すべて同じなら全員 0、和は 0。"""
    vals = dict.fromkeys(DONORS, 0) | {"O": 5, "M": -3, "W1": 5, "W2": 1}
    s = A.rank_scores(vals)
    assert s["O"] == s["W1"] == 19 and s["M"] == -20 and s["W2"] == 16 and s["W3"] == -2   # W3：M より上（＋1）、O・W1・W2 より下（−3）
    assert sum(s.values()) == 0
    assert set(A.rank_scores(dict.fromkeys(DONORS, 7)).values()) == {0}
    ordered = dict(zip(DONORS, range(21)))
    assert list(A.rank_scores(ordered).values()) == list(range(-20, 21, 2))
    with pytest.raises(ValueError):
        A.rank_scores({"O": 1})


def _q(ab: int, ac: int, na: int = 10, nb: int = 10, nc: int = 10) -> dict:
    return {"Delta_AB": ab, "Delta_AC": ac, "D": ab - ac, "spike_counts": {"A": na, "B": nb, "C": nc},
            "silent_roles": [r for r, n in (("A", na), ("B", nb), ("C", nc)) if n == 0], "N": {}, "Delta_BC": 0}


def _sw_quantities(per_recipient: dict) -> dict:
    """{受け手: {ドナー: (Δ_AB, Δ_AC)}} → {受け手: {ドナー: 量}}（参照の値は受け手ごとに −9〜9 のような列で埋める）。"""
    return {r: {d: _q(*per_recipient[r][d]) for d in DONORS} for r in RECIPIENTS}


def _plain(o=(0, 0), m=(0, 0), spread=1, offset=0) -> dict:
    """1 つの受け手の値：W_i は Δ_AB ＝ D ＝ spread × (i − 10) ＋ offset（Δ_AC ＝ 0）、O・M は与えた値。"""
    out = {"O": o, "M": m}
    for i, w in enumerate(REFERENCE, 1):
        out[w] = (spread * (i - 10) + offset, 0)
    return out


def test_order_preservation_and_single_recipient_reduction_on_random_values() -> None:
    """命題 1：受け手の中で x(d) ＞ x(e) なら s(d) ≥ s(e) ＋ 2、等しければ同じ点。受け手が 1 つなら、点の事象は値の事象（0029 の形）と同じ。"""
    rnd = random.Random(24299)
    for _ in range(3000):
        vals = {d: rnd.randint(-3, 3) for d in DONORS}
        s = A.rank_scores(vals)
        for d, e in itertools_pairs(rnd):
            if vals[d] > vals[e]:
                assert s[d] >= s[e] + 2
            elif vals[d] == vals[e]:
                assert s[d] == s[e]
        d_vals = {d: rnd.randint(-3, 3) for d in DONORS}
        assert A.outside_events(s, A.rank_scores(d_vals)) == A.outside_events(vals, d_vals)


def itertools_pairs(rnd):
    return [(rnd.choice(DONORS), rnd.choice(DONORS)) for _ in range(10)]


def test_all_is_inside_agg_on_random_values_with_ties() -> None:
    """命題 1 の帰結 2：同値の多い乱数の値で、All の事象が成り立てば Agg の事象も成り立つ。どの事象も一度は All・Agg で成り立ち、
    Agg だけが成り立つ例もある（確かめが空でない）。"""
    rnd = random.Random("0031-nesting-check")
    hit_all = dict.fromkeys(EVENTS, 0)
    agg_only = dict.fromkeys(EVENTS, 0)
    for n in range(2500):
        per = {}
        for r in RECIPIENTS:
            per[r] = {d: (rnd.randint(-2, 2), rnd.randint(-2, 2)) for d in DONORS}
            if n % 2 == 0:                            # O・M を外に置きやすくする
                per[r]["O"] = (rnd.randint(2, 4), rnd.randint(-4, -2))
                per[r]["M"] = (rnd.randint(-2, 2), rnd.randint(4, 6))
        sc = A.scores_of(_sw_quantities(per))
        agg = A.outside_events(sc["total_scores"]["Delta_AB"], sc["total_scores"]["D"])
        all_ = {e: all(A.outside_events(sc["values"]["Delta_AB"][r], sc["values"]["D"][r])[e] for r in RECIPIENTS) for e in EVENTS}
        assert A.nesting_violations(agg, all_) == [] and all(agg[e] for e in EVENTS if all_[e])
        for e in EVENTS:
            hit_all[e] += all_[e]
            agg_only[e] += agg[e] and not all_[e]
    assert all(v > 0 for v in hit_all.values()) and all(v > 0 for v in agg_only.values()), (hit_all, agg_only)


def test_total_scores_are_equivariant_under_relabelling_donors() -> None:
    """命題 2 の前提：ドナーのラベルを入れ替えると、どの受け手でも同じ塊が同じように入れ替わり、合計の点も同じく入れ替わる。"""
    rnd = random.Random(24299)
    per = {r: {d: (rnd.randint(-4, 4), rnd.randint(-4, 4)) for d in DONORS} for r in RECIPIENTS}
    perm = list(DONORS)
    rnd.shuffle(perm)
    relabel = dict(zip(DONORS, perm))
    per2 = {r: {relabel[d]: per[r][d] for d in DONORS} for r in RECIPIENTS}
    t1, t2 = A.scores_of(_sw_quantities(per))["total_scores"], A.scores_of(_sw_quantities(per2))["total_scores"]
    for x in ("Delta_AB", "D"):
        assert all(t2[x][relabel[d]] == t1[x][d] for d in DONORS)


def _entry(q):
    return {"N": {"A->B": q["Delta_AB"] + 5, "B->A": 5, "A->C": q["Delta_AC"] + 5, "C->A": 5, "B->C": 0, "C->B": 0},
            "spikes": q["spike_counts"]}


def _table(per: dict, spikes: dict | None = None) -> dict:
    """{受け手: {ドナー: (Δ_AB, Δ_AC)}} から、individual() に渡す table（自然な本体は参照の形で埋める）。"""
    spikes = spikes or {}
    sw = {r: {d: _entry(_q(*per[r][d], **spikes.get((r, d), {}))) for d in DONORS} for r in RECIPIENTS}
    natural = {b: _entry(_q(0, 0)) for b in W.BODIES}
    controls = {f"{c}({r})": _entry(_q(0, 0)) for r in RECIPIENTS for c in W.CONTROLS}
    return {"natural": natural, "swapped": sw, "controls": controls}


DYN = {u: {"decay_per_second": 0.85, "intrinsic_drive_per_second": 0.08, "threshold": 0.5} for u in UNITS}
ROLE_UNITS = {"A": "s1", "B": "s2", "C": "s3"}


def _individual(per, spikes=None, tau=250):
    return A.individual(_table(per, spikes), DYN, ROLE_UNITS, tau)


def test_agg_and_all_events_at_the_boundary() -> None:
    """README §4.1：Agg は合計の点、All はすべての受け手。厳密な不等号。"""
    out = {r: _plain(o=(20, -20), m=(-20, 20)) for r in RECIPIENTS}   # どの受け手でも O が上・M が下
    ind = _individual(out)
    assert ind["events"]["All"] == dict.fromkeys(EVENTS, True) and ind["events"]["Agg"] == dict.fromkeys(EVENTS, True)
    assert ind["auxiliary"]["per_recipient_0029_form_events"]["k"] == dict.fromkeys(EVENTS, 5)
    # 一つの受け手（W22）で O が参照の最大と同じ（等号）：All は成り立たず、Agg は残りの受け手で成り立つ
    tie = out | {"W22": _plain(o=(9, 0), m=(-20, 20))}
    ind = _individual(tie)
    assert not ind["events"]["All"]["O_above"] and not ind["events"]["All"]["O_Delta_AB_above"] and ind["events"]["All"]["M_below"]
    assert ind["events"]["Agg"]["O_above"] and ind["auxiliary"]["per_recipient_0029_form_events"]["k"]["O_above"] == 4
    # 一つの受け手で凍結（21 の値がすべて同じ）：その受け手の点は 0。All は成り立たず、Agg は残りで決まる
    frozen = out | {"W24": {d: (0, 0) for d in DONORS}}
    ind = _individual(frozen)
    assert all(v == 0 for x in ("Delta_AB", "D") for v in ind["auxiliary"]["scores"]["rank_scores"][x]["W24"].values())
    assert not any(ind["events"]["All"].values()) and all(ind["events"]["Agg"].values())
    assert ind["auxiliary"]["frozen_per_judgment"]["All"] == dict.fromkeys(("J_Ca", "J_O", "J_M", "J_OM"), 1)
    assert not any(ind["auxiliary"]["frozen_per_judgment"]["Agg"].values())
    # すべての受け手で凍結：合計の点はすべて 0 で、Agg も凍結（外にない）
    all_frozen = {r: {d: (0, 0) for d in DONORS} for r in RECIPIENTS}
    ind = _individual(all_frozen)
    assert not any(ind["events"]["Agg"].values()) and all(ind["auxiliary"]["frozen_per_judgment"]["Agg"].values())
    assert ind["auxiliary"]["frozen_per_judgment"]["All"] == dict.fromkeys(("J_Ca", "J_O", "J_M", "J_OM"), 5)


def test_agg_can_hold_when_o_is_extreme_in_only_some_recipients() -> None:
    """Agg は合計なので、O がある受け手で外になくても、ほかの受け手の点で外に出うる（All は成り立たない）。逆向きの受け手が
    多ければ Agg も成り立たない。"""
    up = _plain(o=(30, -30), m=(0, 0))
    near = _plain(o=(8, 0), m=(0, 0))                # W24 では O は W19（9）より下：その受け手では外にない
    ind = _individual({"W20": up, "W21": up, "W22": up, "W23": up, "W24": near})
    assert ind["events"]["Agg"]["O_above"] and not ind["events"]["All"]["O_above"]
    tot = ind["auxiliary"]["scores"]["total_scores"]["D"]
    assert (tot["O"], tot["W19"]) == (4 * 20 + 17, 4 * 18 + 20)   # O：4 つで最上・W24 で W19 の次（W18 と同値）
    down = _plain(o=(-30, 30), m=(0, 0))
    ind = _individual({"W20": up, "W21": up, "W22": down, "W23": down, "W24": down})
    assert not ind["events"]["Agg"]["O_above"] and ind["auxiliary"]["Agg_opposite_direction"]["total_D_O_below_min"] is False


def test_individual_refuses_when_all_is_not_inside_agg(monkeypatch) -> None:
    """All ⊆ Agg の機械的な検査：点の計算が壊れて（ここでは点の符号を逆にして）All が成り立つのに Agg が成り立たないとき、
    individual は止まる（解析の誤りとして扱い、判定の量を出さない）。"""
    out = {r: _plain(o=(20, -20), m=(-20, 20)) for r in RECIPIENTS}
    real = A.rank_scores
    monkeypatch.setattr(A, "rank_scores", lambda values: {d: -s for d, s in real(values).items()})
    with pytest.raises(ValueError, match="All ⊆ Agg"):
        _individual(out)


def test_target_only_silence_by_hand() -> None:
    """README §6：受け手ごとに、Y_r(O)（Y_r(M)）の沈黙した役の集合が参照の 19 本のどれとも違うか。"""
    base = {r: _plain() for r in RECIPIENTS}
    spikes = {("W21", "O"): {"na": 0}, ("W23", "M"): {"nb": 0, "nc": 0}}
    for d in DONORS:                                  # W24 ではすべてのドナーで A が沈黙：的の本体だけの沈黙ではない
        spikes[("W24", d)] = {"na": 0}
    ind = _individual(base, spikes)
    tos = ind["auxiliary"]["target_only_silence"]
    assert tos["O"] == {"recipients": ["W21"], "count": 1} and tos["M"] == {"recipients": ["W23"], "count": 1}


def _real_nonfrozen() -> tuple[int, dict]:
    """SYN の中で最初の、どれかの受け手でドナーの D の値が 2 つ以上ある個体（同じ値の多い順位の点を実物の runtime で確かめる）。"""
    for s in SYN:
        data = measured(s)
        if not data["run"]["swap"]["tau_exists"]:
            continue
        table, _ = A.count_table(data["run"], s, SMALL)
        if any(len({A.body_quantities(table["swapped"][r][d])["D"] for d in DONORS}) > 1 for r in RECIPIENTS):
            return s, data
    raise AssertionError("SYN に凍結していない受け手を持つ個体がない")


def test_scores_on_a_real_runtime_individual_match_an_independent_count() -> None:
    """実物の runtime の個体で、点を独立な数え方（下の数 − 上の数）で数え直し、合計・受け手ごとの事象・All ⊆ Agg を確かめる。"""
    s, data = _real_nonfrozen()
    run = data["run"]
    table, _ = A.count_table(run, s, SMALL)
    ind = A.individual(table, run["natural_bodies"]["O"]["dynamics"], run["roles"]["units"], run["swap"]["tau"])
    aux = ind["auxiliary"]
    for x in ("Delta_AB", "D"):
        total = dict.fromkeys(DONORS, 0)
        for r in RECIPIENTS:
            vals = {d: A.body_quantities(table["swapped"][r][d])[x] for d in DONORS}
            for d in DONORS:
                below = sum(vals[e] < vals[d] for e in DONORS)
                above = sum(vals[e] > vals[d] for e in DONORS)
                assert aux["scores"]["rank_scores"][x][r][d] == below - above
                total[d] += below - above
        assert aux["scores"]["total_scores"][x] == total
    for r in RECIPIENTS:
        q = {d: A.body_quantities(table["swapped"][r][d]) for d in DONORS}
        ref = [q[w]["D"] for w in REFERENCE]
        assert aux["per_recipient_0029_form_events"]["events"][r]["O_above"] == (q["O"]["D"] > max(ref))
    assert A.nesting_violations(ind["events"]["Agg"], ind["events"]["All"]) == []
    assert any(0 < c < 5 for c in aux["frozen_per_judgment"]["All"].values()) or not all(aux["frozen_per_judgment"]["Agg"].values())


# ---- 7. 判定と、8 判定の水準（README §4・§5）---------------------------------------------------------------------------

def test_thresholds_and_experiment_wide_alpha_are_the_registered_values() -> None:
    p, q = Fraction(1, 20), Fraction(1, 420)
    assert A.binom_tail(20, p, 4) <= Fraction(16, 1000) < A.binom_tail(20, p, 3)
    assert A.binom_tail(20, q, 2) <= Fraction(2, 1000) < A.binom_tail(20, q, 1)
    assert abs(float(A.binom_tail(20, p, 4)) - 0.015902) < 1e-6 and abs(float(A.binom_tail(20, q, 2)) - 0.001047) < 1e-6
    assert ALIGN.HOLDS_MIN == {f: {"J_Ca": 4, "J_O": 4, "J_M": 4, "J_OM": 2} for f in ("Agg", "All")}
    split = PROTOCOL["judgment"]["per_family"]["alpha_split"]
    assert sum(Fraction(str(v)) for v in split.values()) == Fraction(1, 20) == Fraction(str(PROTOCOL["judgment"]["experiment_wide_error_rate_claimed"]))


def _ind(tau: bool = True, **events) -> dict:
    ev = {f: {e: events.get(f"{f}.{e}", False) for e in EVENTS} for f in ("Agg", "All")}
    aux = {"tau_exists": tau, "natural_comparison": dict.fromkeys(EVENTS, False),
           "birth_margin_strata": {r: {"g": 0.1, "stratum": "active"} for r in ("A", "B", "C")}}
    if tau:
        aux |= {"frozen_per_judgment": {"Agg": dict.fromkeys(("J_Ca", "J_O", "J_M", "J_OM"), False),
                                        "All": dict.fromkeys(("J_Ca", "J_O", "J_M", "J_OM"), 0)},
                "Agg_opposite_direction": dict.fromkeys(("total_Delta_AB_O_below_min", "total_D_O_below_min", "total_D_M_above_max"), False),
                "target_only_silence": {"O": {"recipients": [], "count": 0}, "M": {"recipients": [], "count": 0}},
                "per_recipient_0029_form_events": {"k": dict.fromkeys(EVENTS, 0)},
                "swapped_body_silence": {r: dict.fromkeys(DONORS, []) for r in RECIPIENTS}}
    else:
        aux |= dict.fromkeys(("frozen_per_judgment", "Agg_opposite_direction", "target_only_silence",
                              "per_recipient_0029_form_events", "swapped_body_silence"))
    return {"events": ev, "auxiliary": aux}


def test_family_judgment_boundaries_and_no_tau_in_the_denominator() -> None:
    for f, J, e, thr in (("Agg", "J_O", "O_above", 4), ("Agg", "J_OM", "O_and_M_split", 2),
                         ("All", "J_M", "M_below", 4), ("All", "J_OM", "O_and_M_split", 2)):
        for h in (thr - 1, thr):
            kw = {f"{f}.{e}": True} if f == "Agg" else {f"All.{e}": True, f"Agg.{e}": True}
            ind = {str(s): _ind(**(kw if k < h else {})) for k, s in enumerate(SYN)}
            fam = A.family_judgment(ind, f)
            assert (fam[J][ALIGN.STATISTIC[J]], fam[J]["holds"], fam["n"]) == (h, h >= thr, 20)
    ind = {str(s): (_ind(tau=False) if k < 5 else _ind(**{"Agg.O_above": k < 9})) for k, s in enumerate(SYN)}
    fam = A.family_judgment(ind, "Agg")
    assert fam["n"] == 20 and fam["J_O"]["h_O"] == 4 and fam["J_O"]["holds"] and fam["auxiliary"]["no_tau_individuals"] == 5


def test_judgment_reports_nesting_and_refuses_h_all_above_h_agg() -> None:
    per_seed = {str(s): {"individual": _ind(tau=k >= 2, **({"Agg.O_above": True, "All.O_above": True} if k == 5 else {}))}
                for k, s in enumerate(SYN)}
    j = A.judgment(per_seed)
    assert set(j["families"]) == {"Agg", "All"} and j["experiment_wide_error_rate_claimed"] == 0.05
    assert j["nesting_verified"] == {"per_individual_all_implies_agg": True, "per_judgment_h_all_le_h_agg": True}
    assert j["no_tau_individuals"] == SYN[:2] and j["distribution_of_k_per_event"]["O_above"]["0"] == 18
    assert j["birth_margin_strata_counts"]["A"]["active"]["no_tau"] == 2
    bad = {str(s): {"individual": _ind(**({"All.M_below": True} if k == 3 else {}))} for k, s in enumerate(SYN)}
    with pytest.raises(ValueError, match="h\\^All ＞ h\\^Agg"):
        A.judgment(bad)


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
                          "started_at": "t", "experiment": "0031", "kind": PROTOCOL["kind"], "mode": "synthetic"})
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
    for mode, seeds in (("synthetic", [24001]), ("synthetic", [24300]), ("synthetic", [24101]), ("smoke", [24201]),
                        ("formal", [24021]), ("formal", [23001]), ("synthetic", [GUARD_SEEDS[0], GUARD_SEEDS[0]]),
                        ("synthetic", [])):
        with pytest.raises(ERR):
            R.execute(mode, seeds, out, repo, head, runner=_dummy, executor_factory=SerialExecutor)
    with pytest.raises(ERR, match="measurement-commit"):
        R.execute("formal", [24001], out, repo, None, runner=_dummy, executor_factory=SerialExecutor)
    with pytest.raises(ERR, match="指定した commit"):
        R.execute("formal", [24001], out, repo, "1" * 40, runner=_dummy, executor_factory=SerialExecutor)
    assert not (out / G.SEEDS_DIR).exists() or not any((out / G.SEEDS_DIR).iterdir())
    (G.seed_dir(out, 24300)).mkdir(parents=True)
    (G.seed_dir(out, 24300) / G.START).write_text("{}", encoding="utf-8")
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
    path = Path(os.environ["ANIMA_0031_TIMING_DIR"]) / f"{seed}.json"
    path.write_text(json.dumps({"seed": seed, "pid": os.getpid(), "t0": t0, "t1": t1}), encoding="utf-8")
    return {"seed": seed}


@pytest.mark.skipif(__import__("multiprocessing").get_start_method(allow_none=False) != "fork",
                    reason="テスト関数を子プロセスへ渡すのに fork が要る（本番の run.py は既定の runner を使う）")
def test_real_processes_never_exceed_two_at_once(repo, tmp_path, monkeypatch) -> None:
    timing = tmp_path / "timing"
    timing.mkdir()
    monkeypatch.setenv("ANIMA_0031_TIMING_DIR", str(timing))
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

def _measure_runner(plan, seed):
    return json.loads(_measured(seed, plan))["run"]


def _folder(tmp_path_factory, name: str, plan) -> tuple[Path, Path]:
    base = tmp_path_factory.mktemp(name)
    repo = _make_repo(base)
    out = base / "out"
    R.execute("synthetic", SYN, out, repo, _git(repo, "rev-parse", "HEAD"), runner=functools.partial(_measure_runner, plan),
              executor_factory=SerialExecutor)
    return repo, out


@pytest.fixture(scope="module")
def full_folder(tmp_path_factory) -> tuple[Path, Path]:
    """合成の 20 個体（SMALL の Plan で実物の runtime を通す）を、本番と同じ execute の手順で保存したフォルダ。"""
    return _folder(tmp_path_factory, "syn20", SMALL)


@pytest.fixture(scope="module")
def notau_folder(tmp_path_factory) -> tuple[Path, Path]:
    """同じ 20 個体を NOTAU の Plan で execute したフォルダ（τ がない個体と τ がある個体が混ざる）。"""
    return _folder(tmp_path_factory, "notau20", notau_plan())


def _copy(folder, tmp_path) -> Path:
    out = tmp_path / "copy"
    shutil.copytree(folder[1], out, ignore=shutil.ignore_patterns(G.LOCK))
    return out


def _forbidden_keys(report: dict) -> set:
    """判定の量・現象に関する数値の鍵。invalid・smoke の report には出ない。"""
    text = json.dumps(report)
    return {k for k in ('"N"', '"Delta_AB"', '"Delta_AC"', '"D"', '"h_Ca"', '"h_O"', '"h_M"', '"h_OM"', '"per_seed"',
                        '"spike_counts"', '"silent_roles"', '"families"', '"O_above"', '"scores"', '"total_scores"',
                        '"rank_scores"', '"swap_time"', '"tau_exists"', '"no_tau_individuals"', '"birth_margin_strata"',
                        '"not_applicable"', '"tau"', '"k"', '"target_only_silence"') if k in text}


def test_complete_valid_records_give_one_judgment_per_family(full_folder, tmp_path) -> None:
    out = _copy(full_folder, tmp_path)
    report = A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
    assert report["records"]["state"] == "complete" and report["valid"] and report["invalid_seeds"] == []
    assert report["count_arithmetic"] == "evaluated"
    assert report["analysis_commit"] == report["records"]["measurement_commit"] == _git(full_folder[0], "rev-parse", "HEAD")
    j = report["judgment"]
    assert set(j["families"]) == {"Agg", "All"} and j["experiment_wide_error_rate_claimed"] == 0.05
    assert j["nesting_verified"] == {"per_individual_all_implies_agg": True, "per_judgment_h_all_le_h_agg": True}
    for f, fam in j["families"].items():
        assert fam["family"] == f and fam["n"] == 20 and fam["main_judgments"] == list(ALIGN.JUDGMENTS)
        for J in ALIGN.JUDGMENTS:
            stat = ALIGN.STATISTIC[J]
            h = sum(v["individual"]["events"][f][ALIGN.EVENT[f][J]] for v in report["per_seed"].values())
            assert fam[J][stat] == h and fam[J]["holds"] == (h >= ALIGN.HOLDS_MIN[f][J])
            assert len(fam[J]["clopper_pearson_95_of_h_over_n"]) == 2
    for J in ALIGN.JUDGMENTS:
        assert j["families"]["All"][J][ALIGN.STATISTIC[J]] <= j["families"]["Agg"][J][ALIGN.STATISTIC[J]]
    for v in report["per_seed"].values():
        assert A.nesting_violations(v["individual"]["events"]["Agg"], v["individual"]["events"]["All"]) == []
    assert len(report["per_seed"]) == 20 and all(set(st.values()) == {"pass"} for st in report["check_results"].values())
    for s in SYN:                                     # raw には判定の量がなく、report にだけある
        raw = json.loads(gzip.decompress((G.seed_dir(out, s) / G.RAW).read_bytes()))
        assert "events" not in json.dumps(raw["run"]) and "scores" not in json.dumps(raw["run"])
    assert json.loads((out / A.REPORT).read_text())["judgment"] == j
    with pytest.raises(ERR, match="既にある"):
        A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
    assert [json.loads(x)["event"] for x in (out / A.LOG).read_text().splitlines()] == ["started", "completed"]


def test_notau_5_no_tau_individuals_are_completed_and_counted(notau_folder, tmp_path) -> None:
    """(5) τ がない個体は completed として保存され、raw からの再検証で valid のまま集計に入り、8 つの事象は false、分母は 20。
    入れ替えに固有の確認は not_applicable（失敗ではない）。"""
    plan = notau_plan()
    repo, folder = notau_folder
    no_tau = []
    for s in SYN:
        assert G.seed_status(folder, s) == ("completed", [])
        raw = json.loads(gzip.decompress((G.seed_dir(folder, s) / G.RAW).read_bytes()))
        if raw["run"]["swap"]["tau_exists"] is False:
            no_tau.append(s)
            assert raw["run"]["swapped_bodies"] == [] and raw["run"]["control_bodies"] == []
    assert SYN[0] in no_tau and 0 < len(no_tau) < 20, no_tau
    out = _copy(notau_folder, tmp_path)
    report = A.publish(out, "synthetic", plan=plan, seeds=SYN, repo=repo)
    assert report["valid"] and report["invalid_seeds"] == []
    na = set(PROTOCOL["checks"]["no_tau"]["not_applicable"])
    for s in SYN:
        st = report["check_results"][str(s)]
        assert "fail" not in st.values()
        assert ({k for k, v in st.items() if v == "not_applicable"} == na) == (s in no_tau)
    j = report["judgment"]
    assert j["no_tau_individuals"] == no_tau
    for s in no_tau:
        ind = report["per_seed"][str(s)]["individual"]
        assert ind["events"] == {f: dict.fromkeys(EVENTS, False) for f in ("Agg", "All")} and ind["not_outside_reason"] == "no_tau"
    for f in ("Agg", "All"):
        assert j["families"][f]["n"] == 20 and j["families"][f]["auxiliary"]["no_tau_individuals"] == len(no_tau)
    assert all(sum(j["distribution_of_k_per_event"][e].values()) == 20 - len(no_tau) for e in EVENTS)
    strata = j["birth_margin_strata_counts"]
    assert all(sum(strata[r][k]["no_tau"] for k in ALIGN.STRATA) == len(no_tau) for r in ("A", "B", "C"))


def test_notau_5_a_tampered_no_tau_record_makes_the_experiment_invalid(notau_folder, tmp_path) -> None:
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
        _ct(run, "W23", "null_swap")["states"][str(SMALL.body_end)]["units"]["s1"][0] += 1e-9
    _rewrite_raw(out, bad, tamper)
    report = A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
    assert report["records"]["state"] == "complete" and not report["valid"]
    assert report["invalid_seeds"] == [bad] and report["judgment"] is None
    assert set(report["checks"][str(bad)]) == {"null_swap_identity"}
    assert report["count_arithmetic"] == "not_evaluated"
    assert not ({'"N"', '"Delta_AB"', '"D"', '"per_seed"', '"families"', '"h_Ca"', '"scores"'} & _forbidden_keys(report))


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


def test_a_broken_nesting_stops_the_analysis_before_the_report(full_folder, tmp_path, monkeypatch) -> None:
    """All ⊆ Agg の機械的な検査は解析の中で働く：点の計算が壊れて、受け手ごとの値では O がどこでも上なのに合計の点がすべて同じ、
    という食い違いが起きれば、report を書かずに止まる。"""
    out = _copy(full_folder, tmp_path)
    xs = ("Delta_AB", "D")
    monkeypatch.setattr(A, "scores_of", lambda sw: {
        "values": {x: {r: {d: int(d == "O") for d in A.DONORS} for r in A.RECIPIENTS} for x in xs},
        "rank_scores": {x: {r: dict.fromkeys(A.DONORS, 0) for r in A.RECIPIENTS} for x in xs},
        "total_scores": {x: dict.fromkeys(A.DONORS, 0) for x in xs}})
    with pytest.raises(ValueError, match="All ⊆ Agg"):
        A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
    assert not (out / A.REPORT).exists()
    assert [json.loads(x)["event"] for x in (out / A.LOG).read_text().splitlines()] == ["started", "failed"]


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
    """smoke（操作の確認だけ）：判定の量・点を計算する関数は一度も呼ばれず、report に判定の量も現象に関する数値（τ の値・τ の有無）も
    ない。確認の結果は fail か ok だけ（pass と not_applicable を区別しない）。τ がない個体とある個体を含む 20 個体を smoke の形に
    読み替えて確かめる（smoke の seed は使わない）。"""
    out = _copy(notau_folder, tmp_path)
    _as_smoke(out)

    def boom(*a, **k):
        raise AssertionError("smoke で判定の量を計算した")
    for name in ("body_quantities", "quantities_for_seed", "individual", "rank_scores", "scores_of", "outside_events", "frozen",
                 "nesting_violations", "target_only_silence", "family_judgment", "judgment", "birth_margins", "rank",
                 "strata_counts"):
        monkeypatch.setattr(A, name, boom)
    monkeypatch.setattr(A, "expected_seeds", lambda mode: list(SYN))
    monkeypatch.setattr(A.W, "plan_from", lambda protocol: notau_plan())
    report = A.analyze(out, "smoke", repo=notau_folder[0])
    assert report["valid"] and report["judgment"] is None and report["count_arithmetic"] == "evaluated"
    assert _forbidden_keys(report) == set()
    assert all(set(st.values()) == {"ok"} for st in report["check_results"].values())
    assert set(report) == {"experiment", "kind", "mode", "seeds", "plan", "records", "analysis_commit", "valid",
                           "invalid_seeds", "count_arithmetic", "checks", "checks_evaluated", "check_results", "judgment", "note"}


def test_report_destination_isolation(tmp_path, monkeypatch) -> None:
    root = tmp_path / "data" / "experiments"
    own = root / "0031"
    own.mkdir(parents=True)
    monkeypatch.setattr(A, "DATA_ROOT", root)
    monkeypatch.setattr(A, "OWN_DIR", own)
    assert A.report_destination(own, "formal") == own.resolve() / A.REPORT
    for folder, mode in ((root / "0030", "formal"), (tmp_path / "x", "formal"), (own, "smoke"), (root / "0030", "smoke"),
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
    for args in (("formal", SMALL, SYN), ("smoke", SMALL, None), ("synthetic", None, None), ("synthetic", SMALL, [24001]),
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
