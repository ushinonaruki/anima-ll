"""実験 0028 の道具の契約テスト（確定した事前登録 v0.2 の README §0〜§14、protocol.yaml、neuroarchitecture-v1.yaml）。

本番の seed（21001〜21020）・smoke の seed（21101〜21106）は使わない（実行もしない）。合成の契約テスト専用の範囲
（21201〜21299）だけを使う。合成の個体は、本番と同じ道具（world.measure_seed）・同じ式で、値だけを小さくした Plan
（SMALL：試行 3、遅れ 30。主の区間の長さは式どおり 3 × 60 ＝ 180。試行の数は 0023〜0027 の契約テストと同じ値、遅れは 0027 の
契約テストと同じ値）で実物の runtime を通して作る。結果を見て Plan・seed を選んでいない（seed は範囲の最初から順に使う）。

使った合成の seed（PR に開示）：
- 21201〜21220：SMALL の Plan で実物の runtime を通した 20 個体（確認の再検証・改ざんの検出・合成の集計の通し）
- 21221〜21240：一度限りの実行の契約（dummy の計算。runtime を使わない）
- 21241〜21250：並列数の契約（実際のプロセス。dummy の計算）
- 21299：可塑性の再生の照合に使う乱数の流れの名前だけ（runtime の個体は作らない）
- 本番の Plan（試行 200）での W の札の列の作り方の確認には 21201〜21206 の名前を使う（札の列を作るだけで、runtime の個体は作らない）

主の判定は家族（C0・V1）ごとに J_Ca・J_O・J_M・J_OM の 4 つ。**J_Ca は C-a の正式な主の判定（補助ではない）**ことを、§5 で明示的に
確かめる（protocol・道具・判定の量・report のすべてで）。
"""

import copy
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
EXP = ROOT / "experiments" / "0028_lag1_successor_asymmetry"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))
PREREGISTRATION_MERGE = "0cb4f14947dd4a77e5c6334760b207daee77b7df"   # PR #123 のマージ（README・protocol・V1 設計図の確定）
SYN = list(range(21201, 21221))
GUARD_SEEDS = list(range(21221, 21241))
POOL_SEEDS = list(range(21241, 21251))
TOOLS = ("world.py", "run.py", "analyze.py", "alignment.py", "guard.py")
PREREG = ("README.md", "protocol.yaml", "neuroarchitecture-v1.yaml")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W = _load("world_0028_test", EXP / "world.py")
G = _load("guard_0028_test", EXP / "guard.py")
A = _load("analyze_0028_test", EXP / "analyze.py")
R = _load("run_0028_test", EXP / "run.py")
sys.modules[R.__name__] = R          # 実際のプロセスへ compute_and_write を渡すため（本番では run.py が __main__）
ALIGN = _load("alignment_0028_test", EXP / "alignment.py")
SMALL = W.make_plan(PROTOCOL, 3, 30)
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
            "measurement_commit": commit, "protocol_sha256": sha, "protocol": PROTOCOL,
            "manifests": {d: W.manifest_raw(PROTOCOL, d) for d in W.DESIGNS}}
    return json.loads(json.dumps({"meta": meta, "run": run}))


@pytest.fixture(scope="module")
def syn() -> dict:
    return _raw(W.measure_seed(PROTOCOL, SYN[0], SMALL))


def _checks(data: dict, seed: int = SYN[0]) -> dict:
    return {k: v for k, v in A.check_seed(data, "synthetic", seed, SMALL).items() if v}


# ---- 1. protocol と道具の対応・固定 -------------------------------------------------------------------------------

def test_protocol_and_tools_are_aligned() -> None:
    ALIGN.check(PROTOCOL)


def _git_show(rev: str, path: str) -> bytes:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{path}"], capture_output=True, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git の履歴がない環境")


def test_preregistration_files_are_unchanged_since_the_merge() -> None:
    """protocol.yaml・V1 の設計図は事前登録の確定（PR #123 のマージ）からバイト単位で変わっていない。README は確定した §0〜§14 が
    そのまま先頭に残っている（結果は後ろの節に追記する：README §14 の 4）。"""
    rel = f"experiments/{EXP.name}"
    assert (EXP / "protocol.yaml").read_bytes() == _git_show(PREREGISTRATION_MERGE, f"{rel}/protocol.yaml")
    assert (EXP / "neuroarchitecture-v1.yaml").read_bytes() == _git_show(PREREGISTRATION_MERGE, f"{rel}/neuroarchitecture-v1.yaml")
    assert (EXP / "README.md").read_bytes().startswith(_git_show(PREREGISTRATION_MERGE, f"{rel}/README.md"))


def test_runtime_core_and_other_experiments_are_unchanged_from_main() -> None:
    """0028 の道具を変える branch では、本体（src/）・設計（config/）・ほかの実験・0028 の事前登録の文書を同時に変えない
    （main との差分）。0028 の道具を変えない branch（後の PR）では確かめない（この PR の範囲の確認なので、後の作業を止めない）。"""
    try:
        base = subprocess.run(["git", "-C", str(ROOT), "merge-base", "HEAD", "origin/main"], capture_output=True,
                              text=True, check=True).stdout.strip()
        diff = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", base, "--", "src", "config", "experiments"],
                              capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git の履歴がない環境")
    tools = {f"experiments/{EXP.name}/{n}" for n in TOOLS}
    if not set(diff) & tools:
        pytest.skip("この branch は 0028 の道具を変えていない")
    assert set(diff) <= tools, sorted(set(diff) - tools)


def test_v1_manifest_body_is_the_0024_v1_body() -> None:
    """protocol の brains.V1.variant の注（「Body identical to …」）を、テストの側で確かめる（道具はそのファイルを読まない）。"""
    other = ROOT / "experiments" / "0024_learning_free_order_readout" / "neuroarchitecture-v1.yaml"
    assert yaml.safe_load(other.read_text(encoding="utf-8")) == W.manifest_raw(PROTOCOL, "V1")
    assert other.relative_to(ROOT).as_posix() in PROTOCOL["brains"]["V1"]["variant"]


FORBIDDEN = [r'"00(0\d|1\d|2[0-7])"', r"'00(0\d|1\d|2[0-7])'", r"data/experiments/00(0\d|1\d|2[0-7])",
             r"00(0\d|1\d|2[0-7])-(shuffle|within)", r"experiments/00(1[3-9]|2[0-7])_",
             r"experiments/0012_passive_world/(?!neuroarchitecture\.yaml)",
             r"(world|guard|run|analyze|alignment)_00(0\d|1\d|2[0-7])"]
SEED_NUMBERS = r"\b(1[3-9]|20)[0-2]\d\d\b"   # 0020〜0027 の seed の範囲（13001〜20299）の数


def _code(name: str) -> str:
    """道具のコード（説明の文字列・コメントは除く。alignment.py の使用済みの seed の一覧 SEEN は重なりの確認の記録なので除く）。"""
    src = (EXP / name).read_text(encoding="utf-8")
    src = re.sub(r"SEEN = \(.*?\)\)\)\n", "", src, flags=re.DOTALL)
    src = re.sub(r'""".*?"""', "", src, flags=re.DOTALL)
    return "\n".join(line.split("#")[0] for line in src.splitlines())


def test_tools_hold_no_earlier_experiment_references() -> None:
    """道具は、ほかの実験の ID・出力先・乱数の流れの名前・道具（world.py など）を参照しない。0023〜0027 の道具も読み込まない。
    脳の設計図は protocol の brains（C0 は 0014〜0027 と同じ共有の設計図、V1 はこのフォルダのもの）だけを読み、alignment.py が
    その名前を確かめる。"""
    for name in TOOLS:
        code = _code(name)
        for pat in FORBIDDEN:
            assert not re.search(pat, code), (name, pat)
        assert "_load(" not in code or all("experiments/" not in line for line in code.splitlines() if "_load(" in line), name
        assert not re.search(SEED_NUMBERS, code), (name, "0020〜0027 の seed の範囲の数")


def test_the_reference_scan_detects_leftovers() -> None:
    for leftover in ('EXPERIMENT = "0027"', 'OUT = "data/experiments/0027"', 'RNG = "0027-within-trial-{i}:{seed}"',
                     '_load("w", ROOT / "experiments/0027_delayed_order_readout/world.py")',
                     'V1 = "experiments/0024_learning_free_order_readout/neuroarchitecture-v1.yaml"',
                     '"experiments/0012_passive_world/world.py"', "world_0027_for_x", "guard_0026"):
        assert any(re.search(p, leftover) for p in FORBIDDEN), leftover
    for leftover in ("SEEDS = range(20001, 20021)", "SYN = range(20201, 20251)", "seed = 19101", "x = 13001"):
        assert re.search(SEED_NUMBERS, leftover), leftover
    for fine in ("first = 13501", "end = 25500", "late = 13500", "seed = 21001"):
        assert not re.search(SEED_NUMBERS, fine), fine
    src = (EXP / "alignment.py").read_text(encoding="utf-8")
    assert "range(20001" in src and "range(20001" not in _code("alignment.py") and {20001, 20299, 19299, 16299} <= ALIGN.SEEN


def test_tools_read_identity_from_this_protocol() -> None:
    ex = PROTOCOL["execution"]
    assert R.EXPERIMENT == A.EXPERIMENT == W.EXPERIMENT == PROTOCOL["experiment"] == ex["experiment_id"] == "0028"
    assert str(R.OUT_DIR) == str(A.DEFAULT_DIR) == ex["output_dir"]
    assert str(R.PROTOCOL_PATH) == str(A.PROTOCOL_PATH) == str(W.PROTOCOL_PATH) == ex["protocol_path"]
    assert W.RNG_SHUFFLE == PROTOCOL["conditions"]["within_trial_shuffles"]["rng"] == "0028-within-trial-{i}:{seed}"
    assert PROTOCOL["brains"]["C0"]["manifest"] == "experiments/0012_passive_world/neuroarchitecture.yaml"
    assert PROTOCOL["brains"]["V1"]["manifest"] == f"experiments/{EXP.name}/neuroarchitecture-v1.yaml"
    for mode, key in (("formal", "seeds"), ("smoke", "smoke_seeds"), ("synthetic", "synthetic_seeds")):
        assert list(R.allowed_seeds(mode)) == A.expected_seeds(mode) == list(
            range(PROTOCOL[key]["first"], PROTOCOL[key]["last"] + 1))


# ---- 2. Plan・刺激・設計（README §1・§2・§3.4）-----------------------------------------------------------------------

def test_plan_from_protocol_is_the_registered_timeline() -> None:
    """本番の Plan：経験の終わり 12000、遅れ 1500（＝ 5 × τ_a）、早い区間 12001〜13500、主の区間 13501〜25500（12000 Pulse ＝
    経験の長さ）、本体の終わり 25500。全状態を残す時点は 12000・13500・25500（protocol の records・checks）。"""
    p = W.plan_from(PROTOCOL)
    assert (p.trials, p.experience_end, p.delay, p.early, p.main, p.body_end) == (200, 12000, 1500, (12001, 13500),
                                                                                (13501, 25500), 25500)
    assert p.main[1] - p.main[0] + 1 == 12000 == 200 * 60 and p.delay == W.DELAY_MULTIPLE * 300 and W.DELAY_MULTIPLE == 5
    assert list(p.snapshots) == PROTOCOL["checks"]["numeric"]["C0_replay_weights_and_traces"]["at"] == [12000, 13500, 25500]
    assert p.first_stimulus == (1, 2) and p.window("main") == p.main and p.window("early") == p.early
    assert W.plan_of(p.as_dict()) == p
    assert (SMALL.experience_end, SMALL.early, SMALL.main, SMALL.body_end) == (180, (181, 210), (211, 390), 390)


def test_make_plan_refuses_wrong_formulas() -> None:
    for edit in (lambda p: p["timeline"]["count_window_main"].update(first="experience_end + 1"),
                 lambda p: p["timeline"]["count_window_main"].update(length="adaptation_tau"),
                 lambda p: p["timeline"].update(body_runs_to="count_window_early.last"),
                 lambda p: p["timeline"].update(delay="3 * adaptation_tau / pulse_interval_seconds")):
        protocol = copy.deepcopy(PROTOCOL)
        edit(protocol)
        with pytest.raises(ValueError):
            W.plan_from(protocol)
    with pytest.raises(ValueError):
        W.make_plan(PROTOCOL, 3, 0)


def _balanced(labels, plan) -> bool:
    at = dict(labels)
    return all(sorted(at.get(t, "") for t in slots) == ["A", "B", "C"] for slots in W.trial_slots(PROTOCOL, plan))


def test_schedules_follow_the_protocol() -> None:
    """O・M・W_i（0025・0027 と同じ作り方：1 本の乱数の流れで、試行の順に [A, B, C] を 1 回ずつ並べ替えて 3 つの枠に置く）。
    札の列は設計に依らない（V1 の本体は C0 の同じ名前の本体と同じ列）。"""
    plan = W.plan_from(PROTOCOL)
    o = W.ordered_labels(PROTOCOL, plan)
    m = W.labels_of(PROTOCOL, plan, SYN[0], "M")
    assert len(o) == 600 and o[:3] == [(1, "A"), (3, "B"), (31, "C")] and o[-1] == (11971, "C") and _balanced(o, plan)
    assert m[:3] == [(1, "A"), (3, "C"), (31, "B")] and [t for t, _ in m] == [t for t, _ in o] and _balanced(m, plan)
    assert W.first_label_divergence(o, m) == 3
    for seed in SYN[:6]:
        seen = set()
        for i in range(1, 20):
            w = W.labels_of(PROTOCOL, plan, seed, f"W{i}")
            rnd, expected = random.Random(f"0028-within-trial-{i}:{seed}"), []
            for k in range(200):
                roles = ["A", "B", "C"]
                rnd.shuffle(roles)
                t = 1 + 60 * k
                expected += [(t, roles[0]), (t + 2, roles[1]), (t + 30, roles[2])]
            assert w == expected and [t for t, _ in w] == [t for t, _ in o] and _balanced(w, plan) and w not in (o, m)
            seen.add(tuple(x for _, x in w))
        assert len(seen) == 19
    assert W.BODIES == ("O", "M") + tuple(f"W{i}" for i in range(1, 20)) and W.DESIGNS == ("C0", "V1")


def test_alignment_refuses_drift() -> None:
    cases = {
        "時間の流れ": [lambda p: p["timeline"].update(delay="10 * adaptation_tau / pulse_interval_seconds"),
                      lambda p: p["timeline"]["count_window_main"].update(role="auxiliary"),
                      lambda p: p["timeline"]["count_window_early"].update(first="experience_end + 2")],
        "条件": [lambda p: p["conditions"].update(designs=["C0"]),
                 lambda p: p["conditions"].pop("M"),
                 lambda p: p["conditions"]["within_trial_shuffles"].update(count=20),
                 lambda p: p["conditions"]["within_trial_shuffles"].update(rng="0028-shuffle-{i}:{seed}")],
        "判定の決まり": [lambda p: p["judgment"]["per_family"].pop("J_Ca"),
                         lambda p: p["judgment"]["per_family"]["alpha_split"].update(J_Ca=0.02),
                         lambda p: p["judgment"]["per_family"]["J_OM"].update(holds_if="h_OM >= 1"),
                         lambda p: p["judgment"].update(experiment_wide_error_rate_claimed="0.05"),
                         lambda p: p["judgment"]["not_judged"].pop()],
        "主・補助の量": [lambda p: p["quantities"]["primary"]["per_individual_and_design"].pop("O_Delta_AB_above"),
                         lambda p: p["quantities"]["not_used"].remove("normalizations")],
        "記録の項目": [lambda p: p["records"]["per_body"].remove("full_state_13500")],
        "操作の確認": [lambda p: p["checks"]["numeric"].pop("C0_pair_sum"),
                       lambda p: p["checks"]["exact"].remove("lag1_counts_two_ways")],
        "V1": [lambda p: p["brains"]["V1"].update(fixed_weights={"s_to_s": 0.004}),
               lambda p: p["brains"]["V1"].update(variant="remove plastic: true")],
        "seed": [lambda p: p.update(seeds={"first": 20001, "last": 20020})],
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


# ---- 3. 実物の runtime を通した合成の個体での操作の確認（README §7）---------------------------------------------------

def test_all_checks_pass_on_a_real_runtime_individual(syn) -> None:
    assert _checks(syn) == {}
    table, problems = A.count_table(syn["run"], SYN[0], SMALL)
    assert problems == [] and tuple(table) == W.DESIGNS
    assert all(tuple(table[d]) == W.BODIES and all(set(v) == set(W.WINDOWS) for v in table[d].values()) for d in W.DESIGNS)


def test_raw_holds_the_preregistered_items(syn) -> None:
    run = syn["run"]
    assert tuple(run["designs"]) == ("C0", "V1") and all(tuple(run["designs"][d]) == W.BODIES for d in W.DESIGNS)
    for d in W.DESIGNS:
        for b, rec in run["designs"][d].items():
            assert {"design", "body", "birth", "labels", "spikes", "states", "first_stimulus", "before_divergence", "rng",
                    "sensory", "first_divergence_from_O"} <= set(rec)
            assert rec["design"] == d and rec["body"] == b
            assert list(rec["states"]) == [str(p) for p in SMALL.snapshots] and list(rec["first_stimulus"]) == ["1", "2"]
            assert all(tuple(st) == W.FULL_STATE_FIELDS for st in rec["states"].values())
            assert len(rec["states"][str(SMALL.body_end)]["connections"]) == (6 if d == "C0" else 0)
            assert max(p for ps in rec["spikes"].values() for p in ps) <= SMALL.body_end
    assert "probes" not in json.dumps(list(run["designs"]["C0"]["O"]))                 # 試しの複製は作らない


def test_birth_state_is_shared_by_all_42_bodies(syn) -> None:
    """42 の本体の Unit の状態・力学は同じ。接続の状態だけが設計の違い（C0：6 本の [0.005, 0, 0]、V1：空）。"""
    run = syn["run"]
    ref = run["designs"]["C0"]["O"]
    for d in W.DESIGNS:
        for rec in run["designs"][d].values():
            assert rec["dynamics"] == ref["dynamics"] and rec["birth"]["units"] == ref["birth"]["units"]
            assert rec["birth"]["connections"] == W.initial_connections(PROTOCOL, d)
    assert W.initial_connections(PROTOCOL, "V1") == {} and len(W.initial_connections(PROTOCOL, "C0")) == 6


def test_v1_weights_never_change_and_the_drive_checks_are_not_vacuous(syn) -> None:
    """V1：記録したすべての全状態で connections が空、Unit → Unit の駆動は 0.005、Receptor の駆動は 1.0。
    最初の刺激とその次の全状態を残すので、どの本体でも Receptor の駆動が、多くの本体で Unit → Unit の駆動が記録に現れる
    （確認が空にならない）。"""
    run = syn["run"]
    receptor_seen, unit_seen = {}, {}
    for d in W.DESIGNS:
        for b, rec in run["designs"][d].items():
            states = list(A.recorded_states(d, {b: rec}))
            drives = [dr for _, st in states for dr in st["drives"]]
            receptor_seen[(d, b)] = any(src in A.RECEPTOR_UNIT and w == 1.0 for src, _, w, _ in drives)
            unit_seen[(d, b)] = any(src in A.UNITS for src, *_ in drives)
            if d == "V1":
                assert all(st["connections"] == {} for _, st in states)
                assert all(w == 0.005 for src, _, w, _ in drives if src in A.UNITS)
    assert all(receptor_seen.values())
    assert sum(unit_seen[("V1", b)] for b in W.BODIES) >= len(W.BODIES) // 2


def _tampered(syn, f) -> dict:
    data = copy.deepcopy(syn)
    f(data["run"])
    return _checks(data)


def _first_divergence_one(run) -> str:
    """札が最初の Pulse から O と違う本体（最初の刺激の全状態が O と比べられない本体）。"""
    return next(b for b in W.SHUFFLES if run["designs"]["C0"][b]["first_divergence_from_O"] == 1)


def test_v1_and_drive_checks_detect_tampering(syn) -> None:
    run = syn["run"]
    b1 = _first_divergence_one(run)
    end = str(SMALL.body_end)

    def v1_conn(run):
        run["designs"]["V1"]["W3"]["states"][end]["connections"] = {"s1.main->s2": [0.005, 0.0, 0.0]}
    assert set(_tampered(syn, v1_conn)) == {"V1_connections_empty_all_recorded_states"}

    st2 = run["designs"]["V1"][b1]["first_stimulus"]["2"]
    k = next(i for i, dr in enumerate(st2["drives"]) if dr[0] in A.UNITS)

    def v1_drive(run):
        run["designs"]["V1"][b1]["first_stimulus"]["2"]["drives"][k][2] = 0.0050000000001
    assert set(_tampered(syn, v1_drive)) == {"V1_s_to_s_drive_weights_all_0_005"}

    for d in W.DESIGNS:
        st1 = run["designs"][d][b1]["first_stimulus"]["1"]
        j = next(i for i, dr in enumerate(st1["drives"]) if dr[0] in A.RECEPTOR_UNIT)

        def receptor(run, d=d, j=j):
            run["designs"][d][b1]["first_stimulus"]["1"]["drives"][j][2] = 0.9999999999
        assert set(_tampered(syn, receptor)) == {"receptor_drive_weights_all_1_0"}, d

    def wiring(run):                                  # 設計図にない配線の駆動は、記録の形の問題
        run["designs"]["V1"][b1]["first_stimulus"]["1"]["drives"].append(["s1", "s1", 0.005, 1])
    assert set(_tampered(syn, wiring)) == {"revalidate_from_raw"}


def test_label_birth_input_and_divergence_checks_detect_tampering(syn) -> None:
    def v1_labels(run):                               # V1 の M の札を O の札にする（C0 の M と違う）
        run["designs"]["V1"]["M"]["labels"] = copy.deepcopy(run["designs"]["V1"]["O"]["labels"])
    assert set(_tampered(syn, v1_labels)) == {"stimulus_labels"}

    def rng(run):
        run["designs"]["C0"]["W2"]["rng"] = f"0028-within-trial-2:{SYN[1]}"
    assert set(_tampered(syn, rng)) == {"stimulus_labels"}

    def birth(run):
        run["designs"]["V1"]["W4"]["birth"]["units"]["s1"][0] += 1e-15
    assert set(_tampered(syn, birth)) == {"identical_birth_state_all_42_bodies"}

    def v1_dynamics(run):                             # V1 の全本体の力学だけを変える（V1 の中では同じ、C0 と違う）
        for rec in run["designs"]["V1"].values():
            rec["dynamics"]["s2"] = {"x": 1}
    assert set(_tampered(syn, v1_dynamics)) == {"identical_birth_state_all_42_bodies"}

    def late_input(run):
        run["designs"]["V1"]["W9"]["sensory"].append([SMALL.experience_end + 5, "receptor.x1"])
    assert set(_tampered(syn, late_input)) == {"input_free_after_experience"}

    def before_state(run):
        run["designs"]["C0"]["M"]["before_divergence"]["2"]["units"]["s2"][1] += 1e-15
    assert set(_tampered(syn, before_state)) == {"identical_before_label_divergence_within_each_design"}

    def before_spike(run):                            # V1 の M に、札が分かれる前（Pulse 1）の発火を足す
        sp = run["designs"]["V1"]["M"]["spikes"]
        u = next(u for u in A.UNITS if 1 not in sp.get(u, []))
        sp[u] = sorted(set(sp.get(u, [])) | {1})
    assert set(_tampered(syn, before_spike)) == {"identical_before_label_divergence_within_each_design"}

    def first_stimulus_state(run):                    # 札が分かれる前の、最初の刺激の全状態
        rec = run["designs"]["V1"]["M"]
        rec["first_stimulus"]["1"]["units"]["s3"][0] += 1e-15
    assert set(_tampered(syn, first_stimulus_state)) == {"identical_before_label_divergence_within_each_design"}


def test_c0_replay_pair_sum_and_clipping_checks_detect_tampering(syn) -> None:
    def w12000(run):                                  # 組の和を保って重みを動かす
        st = run["designs"]["C0"]["W1"]["states"][str(SMALL.experience_end)]
        st["connections"]["s1.main->s2"][0] += 1e-9
        st["connections"]["s2.main->s1"][0] -= 1e-9
    assert set(_tampered(syn, w12000)) == {"C0_replay_weights_and_traces"}

    def trace(run):
        run["designs"]["C0"]["O"]["states"][str(SMALL.early[1])]["connections"]["s3.main->s1"][1] += 1e-9
    assert set(_tampered(syn, trace)) == {"C0_replay_weights_and_traces"}

    def pair(run):
        run["designs"]["C0"]["W5"]["states"][str(SMALL.body_end)]["connections"]["s1.main->s3"][0] += 1e-9
    assert set(_tampered(syn, pair)) == {"C0_replay_weights_and_traces", "C0_pair_sum"}

    def clip(run):
        run["designs"]["C0"]["W6"]["first_stimulus"]["2"]["connections"]["s2.main->s3"][0] = 0.0100001
    assert "C0_no_clipping" in _tampered(syn, clip)


def test_replay_reports_clipping_and_matches_the_runtime_rule() -> None:
    from anima_ll.neuroarchitecture.plasticity import PlasticState, balanced_pair_window
    spec = W.plasticity(PROTOCOL)
    rnd = random.Random(21299)
    sp = {"s1": sorted(rnd.sample(range(1, 400), 60)), "s2": sorted(rnd.sample(range(1, 400), 70))}
    r = A.replay([0.005, 0.0, 0.0], "s1", "s2", sp, 0, 400, (0, 200))
    st = PlasticState(0.005)
    for p in range(1, 401):
        st = balanced_pair_window(st, pre_fired=p in sp["s1"], post_fired=p in sp["s2"], delta_time=1.0, spec=spec)
    assert r["end"] == [st.weight, st.pre_trace, st.post_trace] and r["clipped"] == [] and r["at"][0] == [0.005, 0.0, 0.0]
    big = A.replay([0.0099, 500.0, 0.0], "s1", "s2", {"s2": [1]}, 0, 1)
    assert big["clipped"] == [1] and big["end"][0] == spec.w_max


def test_structure_checks_detect_wrong_plan_seed_and_shape(syn) -> None:
    data = copy.deepcopy(syn)
    assert set(_checks(data, SYN[1])) == {"revalidate_from_raw"}
    assert A.check_seed(syn, "synthetic", SYN[0], W.make_plan(PROTOCOL, 3, 31))["revalidate_from_raw"]
    for edit in (lambda r: r["designs"]["C0"].pop("W19"), lambda r: r["designs"].pop("V1"),
                 lambda r: r["designs"]["V1"]["O"]["states"].pop(str(SMALL.early[1])),
                 lambda r: r["designs"]["C0"]["M"]["first_stimulus"].pop("2"),
                 lambda r: r["designs"]["V1"]["W2"].update(design="C0"),
                 lambda r: r["designs"]["C0"]["O"]["states"][str(SMALL.body_end)].update(extra=1)):
        data = copy.deepcopy(syn)
        edit(data["run"])
        assert "revalidate_from_raw" in _checks(data)
    data = copy.deepcopy(syn)
    data["meta"]["manifests"]["V1"] = data["meta"]["manifests"]["C0"]
    assert set(_checks(data)) == {"revalidate_from_raw"}


# ---- 4. 時間差 1 の発火の組の数（README §3.1。2 通りの算術）------------------------------------------------------------

def test_lag1_counts_follow_the_definition_by_hand() -> None:
    """N_{X→Y} ＝ #{t : S ≤ t ≤ E − 1, X が t、Y が t ＋ 1 に発火}。同じ Pulse（時間差 0）・時間差 2 以上・区間の外の発火は数えない。"""
    units = {"A": "s1", "B": "s2", "C": "s3"}
    sp = {"s1": [9, 10, 12, 15, 20], "s2": [10, 11, 13, 16, 21], "s3": [12, 13, 21]}
    want = {"N": {"A->B": 3, "B->A": 1, "A->C": 1, "C->A": 0, "B->C": 1, "C->B": 1}, "spikes": {"A": 4, "B": 4, "C": 2}}
    assert A._counts_route1(sp, units, 10, 20) == want == A._counts_route2(sp, units, 10, 20)
    q = A.body_quantities(want)
    assert (q["Delta_AB"], q["Delta_AC"], q["Delta_BC"], q["D"]) == (2, 1, 0, 1)
    silent = {"s1": [10, 12]}                         # B・C が沈黙：その Unit を含む組は 0
    zero = A._counts_route1(silent, units, 10, 20)
    assert zero == A._counts_route2(silent, units, 10, 20) and set(zero["N"].values()) == {0}
    assert zero["spikes"] == {"A": 2, "B": 0, "C": 0}


def test_count_table_routes_agree_on_the_real_runtime_and_detect_inconsistent_spikes(syn) -> None:
    table, problems = A.count_table(syn["run"], SYN[0], SMALL)
    assert problems == []
    units = syn["run"]["roles"]["units"]
    for d in W.DESIGNS:
        for b, rec in syn["run"]["designs"][d].items():
            for w in W.WINDOWS:
                lo, hi = SMALL.window(w)
                assert table[d][b][w]["spikes"] == {r: len([p for p in rec["spikes"].get(units[r], []) if lo <= p <= hi])
                                                    for r in W.ROLES}
    data = copy.deepcopy(syn)
    lo, hi = SMALL.main
    data["run"]["designs"]["V1"]["W7"]["spikes"][units["A"]] = [hi + 5, lo + 1]   # 並びが崩れた発火の列
    _, problems = A.count_table(data["run"], SYN[0], SMALL)
    assert problems


# ---- 5. 判定の量と主の判定（README §4。J_Ca は正式な主の判定）-------------------------------------------------------

def _q(ab: int, ac: int, spikes: int = 1) -> dict:
    return {"Delta_AB": ab, "Delta_AC": ac, "D": ab - ac, "spike_counts": {r: spikes for r in W.ROLES}}


def _window(o, m, w) -> dict:
    """{本体: 量}。o・m は (Δ_AB, Δ_AC)、w は W1〜W19 の (Δ_AB, Δ_AC) の列。"""
    return {"O": _q(*o), "M": _q(*m)} | {f"W{i}": _q(*x) for i, x in enumerate(w, 1)}


W_REF = [(k - 9, 0) for k in range(19)]              # W の Δ_AB は −9〜9、Δ_AC は 0（D は −9〜9）


def test_four_events_are_strict_and_one_sided() -> None:
    ev = A.four_events(_window((10, 0), (0, 10), W_REF))
    assert ev == {"O_Delta_AB_above": True, "O_above": True, "M_below": True, "O_and_M_split": True}
    tie = A.four_events(_window((9, 0), (0, 9), W_REF))                          # 最大・最小と等しい：外にない
    assert tie == {"O_Delta_AB_above": False, "O_above": False, "M_below": False, "O_and_M_split": False}
    opposite = A.four_events(_window((-10, 0), (10, 0), W_REF))                  # 予測と逆の向き：外にない（記録だけ）
    assert not any(opposite.values())
    only_o = A.four_events(_window((10, 0), (0, 0), W_REF))
    assert only_o["O_above"] and not only_o["M_below"] and not only_o["O_and_M_split"]
    with pytest.raises(ValueError):
        A.four_events({"O": _q(0, 0)})


def test_J_Ca_and_J_O_are_different_events() -> None:
    """README §3.2：Δ_AB（C-a）と D（C-b）は同じ事象ではない。どちらか一方だけが起きる個体がありうる。"""
    ca_only = A.four_events(_window((10, 10), (0, 0), W_REF))   # Δ_AB は上、Δ_AC も同じだけ大きく D は 0
    assert ca_only["O_Delta_AB_above"] and not ca_only["O_above"]
    o_only = A.four_events(_window((0, -20), (0, 0), W_REF))    # Δ_AB は W の中、Δ_AC が小さく D は上
    assert o_only["O_above"] and not o_only["O_Delta_AB_above"]


def test_design_eval_records_auxiliary_frozen_and_silence() -> None:
    per = {b: {"main": q, "early": q} for b, q in _window((-10, 0), (10, 0), W_REF).items()}
    ev = A.design_eval(per)
    aux = ev["auxiliary"]
    assert not any(ev["main"].values())
    assert aux["opposite_direction"] == {"Delta_AB_O_below_min": True, "D_O_below_min": True, "D_M_above_max": True}
    assert aux["ranks"]["rank_of_Delta_AB_O_among_W"] == {"W_below": 0, "W_equal": 0, "W_above": 19}
    assert not aux["C_a_form_for_M"] and not any(aux["frozen"].values()) and aux["early_window_events"] == ev["main"]
    m_ca = A.design_eval({b: {"main": q, "early": q} for b, q in _window((0, 0), (0, 5), [(0, k - 9) for k in range(19)]).items()})
    assert m_ca["auxiliary"]["C_a_form_for_M"] is False
    m_ca = A.design_eval({b: {"main": q, "early": q} for b, q in _window((0, 0), (0, 10), [(0, k - 9) for k in range(19)]).items()})
    assert m_ca["auxiliary"]["C_a_form_for_M"] is True and not m_ca["main"]["O_Delta_AB_above"]   # M の C-a の形は判定しない


def test_an_all_silent_individual_is_frozen_and_not_outside() -> None:
    """D3：主の区間でどの Unit も発火しない個体でも、主の式が値を返し、凍結として「外にない」に数える。"""
    zero = {"N": {k: 0 for k in A.PAIR_KEYS}, "spikes": {r: 0 for r in W.ROLES}}
    table = {d: {b: {w: zero for w in W.WINDOWS} for b in W.BODIES} for d in W.DESIGNS}
    weights = {b: {str(p): {k: 0.005 for k in A.PAIR_KEYS} for p in SMALL.snapshots} for b in W.BODIES}
    q = A.quantities_for_seed(table, weights)
    for d in W.DESIGNS:
        ev = q["designs"][d]["individual"]
        assert not any(ev["main"].values()) and all(ev["auxiliary"]["frozen"].values())
        assert all(v == list(W.ROLES) for v in ev["auxiliary"]["silent_units_main_window"].values())
        assert all(v["main"]["D"] == 0 for v in q["designs"][d]["bodies"].values())
    assert q["C0_weight_ranks"][str(SMALL.experience_end)]["O"]["A->B"] == {"W_below": 0, "W_equal": 19, "W_above": 0}


def _ind(**events) -> dict:
    main = {e: events.get(e, False) for e in ALIGN.EVENT.values()}
    return {"main": main, "auxiliary": {"C_a_form_for_M": False,
                                        "opposite_direction": {"Delta_AB_O_below_min": False, "D_O_below_min": False,
                                                               "D_M_above_max": False},
                                        "frozen": {J: False for J in ALIGN.JUDGMENTS},
                                        "early_window_events": {e: False for e in ALIGN.EVENT.values()},
                                        "silent_units_main_window": {b: [] for b in W.BODIES}}}


def test_J_Ca_is_a_formal_main_judgment_in_both_families() -> None:
    """J_Ca は C-a の正式な主の判定：protocol の per_family・道具の判定の一覧・家族ごとの判定の量のどれにもあり、
    割り当てた水準 0.016・閾値 h_Ca ≥ 4 で、O_Delta_AB_above の個体の数だけから決まる（D の事象とは独立に数える）。"""
    pf = PROTOCOL["judgment"]["per_family"]
    assert "J_Ca" in pf and pf["alpha_split"]["J_Ca"] == 0.016 and pf["J_Ca"]["corresponds_to"] == "C-a"
    assert ALIGN.JUDGMENTS == ("J_Ca", "J_O", "J_M", "J_OM") and ALIGN.EVENT["J_Ca"] == "O_Delta_AB_above"
    assert PROTOCOL["quantities"]["primary"]["across_individuals_per_design"]["h_Ca"] == "count(O_Delta_AB_above)"
    for h_ca, h_o in ((4, 0), (3, 20), (0, 4)):
        ind = {str(s): _ind(O_Delta_AB_above=k < h_ca, O_above=k < h_o) for k, s in enumerate(SYN)}
        fam = A.family_judgment(ind, "C0", 0.05)
        assert fam["main_judgments"] == ["J_Ca", "J_O", "J_M", "J_OM"]
        assert (fam["J_Ca"]["h_Ca"], fam["J_Ca"]["holds"]) == (h_ca, h_ca >= 4)
        assert (fam["J_O"]["h_O"], fam["J_O"]["holds"]) == (h_o, h_o >= 4)
        assert fam["J_Ca"]["alpha"] == 0.016 and fam["J_Ca"]["holds_if"] == "h_Ca >= 4"
    per_seed = {str(s): {"designs": {d: {"individual": _ind(O_Delta_AB_above=k < 5)} for d in W.DESIGNS}}
                for k, s in enumerate(SYN)}
    j = A.judgment(per_seed)
    assert all(j["families"][f]["J_Ca"]["holds"] and j["families"][f]["J_Ca"]["h_Ca"] == 5 for f in ("C0", "V1"))
    protocol = copy.deepcopy(PROTOCOL)
    protocol["judgment"]["per_family"].pop("J_Ca")
    with pytest.raises(SystemExit):                    # J_Ca を外した protocol では、道具は動かない
        ALIGN.check(protocol)


def test_thresholds_and_family_alpha_are_the_registered_values() -> None:
    """閾値 4・4・4・2 は、割り当てた水準（0.016・0.016・0.016・0.002。和は家族の水準 0.05）と K ＝ 19 から決まる最小の整数。"""
    p, q = Fraction(1, 20), Fraction(1, 420)
    assert A.binom_tail(20, p, 4) <= Fraction(16, 1000) < A.binom_tail(20, p, 3)
    assert A.binom_tail(20, q, 2) <= Fraction(2, 1000) < A.binom_tail(20, q, 1)
    assert abs(float(A.binom_tail(20, p, 4)) - 0.015902) < 1e-6 and abs(float(A.binom_tail(20, q, 2)) - 0.001047) < 1e-6
    assert sum(Fraction(str(v)) for v in PROTOCOL["judgment"]["per_family"]["alpha_split"].values()) == Fraction(1, 20)
    assert ALIGN.HOLDS_MIN == {"J_Ca": 4, "J_O": 4, "J_M": 4, "J_OM": 2}
    assert ALIGN.per_individual_null("J_OM", 19) == q and ALIGN.per_individual_null("J_Ca", 19) == p


def test_family_judgment_boundaries_and_no_combined_quantities() -> None:
    for ev, J, stat, thr in (("M_below", "J_M", "h_M", 4), ("O_and_M_split", "J_OM", "h_OM", 2)):
        for h in (thr - 1, thr):
            ind = {str(s): _ind(**{ev: k < h}) for k, s in enumerate(SYN)}
            fam = A.family_judgment(ind, "V1", 0.05)
            assert (fam[J][stat], fam[J]["holds"]) == (h, h >= thr)
    per_seed = {str(s): {"designs": {d: {"individual": _ind()} for d in W.DESIGNS}} for s in SYN}
    j = A.judgment(per_seed)
    assert set(j) == {"families", "experiment_wide_error_rate_claimed", "scope", "content_claimed", "not_judged", "note"}
    assert j["experiment_wide_error_rate_claimed"] == "none" and set(j["families"]) == {"C0", "V1"}
    for fam in j["families"].values():
        assert set(fam) == {"design", "alpha", "n", "main_judgments", "auxiliary", *ALIGN.JUDGMENTS}
        assert fam["alpha"] == 0.05 and fam["n"] == 20
    text = json.dumps(j)
    assert not any(k in text for k in ('"total', '"sum', '"combined', '"difference', '"ratio', '"C0_minus', '"both_families'))


def test_clopper_pearson_reference_values() -> None:
    lo, hi = A.clopper_pearson(5, 20)
    assert abs(lo - 0.0866) < 1e-4 and abs(hi - 0.4910) < 1e-4


# ---- 6. seed を単位にした一度限りの実行（README §9、protocol execution.per_seed）------------------------------------

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
    seed2 = GUARD_SEEDS[1]                            # 同時に 16 個が同じ seed の開始の記録を作ろうとしても、成功は 1 つだけ
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
    stray = G.seed_dir(out, GUARD_SEEDS[2])           # 開始の記録がないまま何かがある seed は始めない
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
        assert raw["run"]["seed"] == s and set(raw["meta"]["manifests"]) == {"C0", "V1"}
        assert G.seed_status(out, s) == ("completed", [])
    for again in (seeds[:1], [seeds[2], GUARD_SEEDS[3]]):                    # 開始済みの seed は再実行しない
        with pytest.raises(ERR, match="既に開始"):
            _exec(repo, out, again)
    assert not G.seed_dir(out, GUARD_SEEDS[3]).exists()
    assert _exec(repo, out, [GUARD_SEEDS[3]])["completed"] == [GUARD_SEEDS[3]]   # 未着手の seed は後から実行できる


def test_a_started_seed_without_finish_is_never_rerun_and_blocks_new_seeds(repo, tmp_path) -> None:
    out = tmp_path / "out"
    s = GUARD_SEEDS[0]
    G.begin_seed(out, s, {"seed": s, "measurement_commit": _git(repo, "rev-parse", "HEAD"), "protocol_sha256": "x",
                          "started_at": "t", "experiment": "0028", "kind": PROTOCOL["kind"], "mode": "synthetic"})
    assert G.seed_status(out, s) == ("started", [])                          # 中断（終了の記録がない）
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
    assert not G.seed_dir(out, seeds[2]).exists() and not G.seed_dir(out, seeds[3]).exists()   # 後の seed は始めない
    for again in ([seeds[1]], [seeds[2]], [GUARD_SEEDS[10]]):               # 失敗した seed も、ほかの seed も始めない
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
    assert fin["status"] == "failed" and fin["raw_file_sha256"] is not None      # raw は開示のために残る

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
    for mode, seeds in (("synthetic", [21001]), ("synthetic", [21300]), ("synthetic", [21101]), ("smoke", [21201]),
                        ("formal", [21021]), ("formal", [20001]), ("synthetic", [GUARD_SEEDS[0], GUARD_SEEDS[0]]),
                        ("synthetic", [])):
        with pytest.raises(ERR):
            R.execute(mode, seeds, out, repo, head, runner=_dummy, executor_factory=SerialExecutor)
    with pytest.raises(ERR, match="measurement-commit"):
        R.execute("formal", [21001], out, repo, None, runner=_dummy, executor_factory=SerialExecutor)
    with pytest.raises(ERR, match="指定した commit"):
        R.execute("formal", [21001], out, repo, "1" * 40, runner=_dummy, executor_factory=SerialExecutor)
    assert not (out / G.SEEDS_DIR).exists() or not any((out / G.SEEDS_DIR).iterdir())      # どの seed も始めていない
    (G.seed_dir(out, 21300)).mkdir(parents=True)     # 出力先に範囲の外の seed（穴埋め）があれば始めない
    (G.seed_dir(out, 21300) / G.START).write_text("{}", encoding="utf-8")
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
    (d[0] / G.RAW).write_bytes((d[0] / G.RAW).read_bytes() + b"\0")             # raw の改ざん
    (d[1] / G.START).unlink()                                                    # 開始の記録のない終了の記録
    (d[2] / (G.RAW + ".tmp")).write_bytes(b"")                                   # 置き忘れの一時ファイル
    fin = json.loads((d[3] / G.FINISH).read_text())
    (d[3] / G.FINISH).write_text(json.dumps(fin | {"status": "done"}))           # 想定外の status
    (d[4] / G.RAW).unlink()                                                      # completed なのに raw がない
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
    path = Path(os.environ["ANIMA_0028_TIMING_DIR"]) / f"{seed}.json"
    path.write_text(json.dumps({"seed": seed, "pid": os.getpid(), "t0": t0, "t1": t1}), encoding="utf-8")
    return {"seed": seed}


@pytest.mark.skipif(__import__("multiprocessing").get_start_method(allow_none=False) != "fork",
                    reason="テスト関数を子プロセスへ渡すのに fork が要る（本番の run.py は既定の runner を使う）")
def test_real_processes_never_exceed_two_at_once(repo, tmp_path, monkeypatch) -> None:
    timing = tmp_path / "timing"
    timing.mkdir()
    monkeypatch.setenv("ANIMA_0028_TIMING_DIR", str(timing))
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


# ---- 7. 解析：20 個体の完全性・invalid なら判定しない・一度だけ（README §4・§7・§9）---------------------------------------

@pytest.fixture(scope="module")
def full_folder(tmp_path_factory) -> tuple[Path, Path]:
    """合成の 20 個体（SMALL の Plan で実物の runtime を通す）を、本番と同じ execute の手順で保存したフォルダ。"""
    base = tmp_path_factory.mktemp("syn20")
    repo = _make_repo(base)
    out = base / "out"
    runner = functools.partial(W.measure_seed, PROTOCOL, plan=SMALL)
    R.execute("synthetic", SYN, out, repo, _git(repo, "rev-parse", "HEAD"), runner=runner,
              executor_factory=SerialExecutor)
    return repo, out


def _copy(full_folder, tmp_path) -> Path:
    out = tmp_path / "copy"
    shutil.copytree(full_folder[1], out, ignore=shutil.ignore_patterns(G.LOCK))
    return out


def _forbidden_keys(report: dict) -> set:
    """判定の量・現象に関する数値の鍵。invalid・smoke の report には出ない。"""
    text = json.dumps(report)
    return {k for k in ('"N"', '"Delta_AB"', '"Delta_AC"', '"D"', '"h_Ca"', '"h_O"', '"h_M"', '"h_OM"', '"per_seed"',
                        '"spike_counts"', '"silent_units_main_window"', '"C0_weights"', '"C0_weight_ranks"', '"families"',
                        '"O_Delta_AB_above"', '"frozen"') if k in text}


def test_complete_valid_records_give_one_judgment_per_family(full_folder, tmp_path) -> None:
    out = _copy(full_folder, tmp_path)
    report = A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
    assert report["records"]["state"] == "complete" and report["valid"] and report["invalid_seeds"] == []
    assert report["count_arithmetic"] == "evaluated"
    assert report["analysis_commit"] == report["records"]["measurement_commit"] == _git(full_folder[0], "rev-parse", "HEAD")
    j = report["judgment"]
    assert set(j["families"]) == {"C0", "V1"} and j["experiment_wide_error_rate_claimed"] == "none"
    for name, fam in j["families"].items():
        assert fam["design"] == name and fam["n"] == 20 and fam["main_judgments"] == list(ALIGN.JUDGMENTS)
        # J_Ca は主の判定の側にだけあり、補助の数え上げには入らない（補助の「C-a の形」は M についてのもの）
        assert "J_Ca" in fam and fam["J_Ca"]["alpha"] == 0.016 and fam["J_Ca"]["holds_if"] == "h_Ca >= 4"
        assert set(fam["auxiliary"]) == {"C_a_form_for_M", "opposite_direction", "frozen", "early_window_events",
                                         "individuals_with_a_silent_unit_in_some_body"}
        assert "O_Delta_AB_above" not in json.dumps(fam["auxiliary"]["opposite_direction"])
        for J in ALIGN.JUDGMENTS:
            stat = ALIGN.STATISTIC[J]
            h = sum(v["designs"][name]["individual"]["main"][ALIGN.EVENT[J]] for v in report["per_seed"].values())
            assert fam[J][stat] == h and fam[J]["holds"] == (h >= ALIGN.HOLDS_MIN[J])
    assert len(report["per_seed"]) == 20
    for v in report["per_seed"].values():
        assert set(v) == {"designs", "C0_weights", "C0_weight_ranks"}
        assert all(tuple(v["designs"][d]["bodies"]) == W.BODIES for d in W.DESIGNS)
        assert set(v["C0_weight_ranks"]) == {str(p) for p in SMALL.snapshots}
    assert json.loads((out / A.REPORT).read_text())["judgment"] == j
    with pytest.raises(ERR, match="既にある"):                     # 集計は一度だけ
        A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
    assert [json.loads(x)["event"] for x in (out / A.LOG).read_text().splitlines()] == ["started", "completed"]


def test_incomplete_records_are_not_analyzed_and_nothing_is_written(full_folder, tmp_path) -> None:
    out = _copy(full_folder, tmp_path)
    shutil.rmtree(G.seed_dir(out, SYN[-1]))                                  # 19 個体だけ
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

    def tamper(run):                                 # V1 の 1 本体の終わりの全状態に接続の状態を足す
        run["designs"]["V1"]["W11"]["states"][str(SMALL.body_end)]["connections"] = {"s1.main->s2": [0.005, 0.0, 0.0]}
    _rewrite_raw(out, bad, tamper)
    report = A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
    assert report["records"]["state"] == "complete" and not report["valid"]
    assert report["invalid_seeds"] == [bad] and report["judgment"] is None
    assert set(report["checks"][str(bad)]) == {"V1_connections_empty_all_recorded_states"}
    assert report["count_arithmetic"] == "not_evaluated"
    assert _forbidden_keys(report) == set()                                  # invalid を「外にない」に数えず、量を出さない


def test_count_arithmetic_failure_makes_the_experiment_invalid(full_folder, tmp_path, monkeypatch) -> None:
    out = _copy(full_folder, tmp_path)
    real = A._counts_route2

    def off_by_one(sp, units, lo, hi):               # 経路 2 だけがずれる（2 通りの算術の確認が働くこと）
        r = real(sp, units, lo, hi)
        r["N"]["A->B"] += 1
        return r
    monkeypatch.setattr(A, "_counts_route2", off_by_one)
    report = A.analyze(out, "synthetic", SMALL, SYN, repo=full_folder[0])
    assert not report["valid"] and report["count_arithmetic"] == "evaluated" and report["judgment"] is None
    assert report["invalid_seeds"] == SYN and all(set(c) == {"lag1_counts_two_ways"} for c in report["checks"].values())
    assert _forbidden_keys(report) == set()


def test_record_problems_block_the_judgment(full_folder, tmp_path) -> None:
    cases = {}
    out = _copy(full_folder, tmp_path / "a")                                # raw のハッシュの不一致
    p = G.seed_dir(out, SYN[3]) / G.RAW
    b = bytearray(p.read_bytes())
    b[len(b) // 2] ^= 0xFF
    p.write_bytes(bytes(b))
    cases["hash"] = out
    out = _copy(full_folder, tmp_path / "b")                                # failed の seed
    fin = G.seed_dir(out, SYN[4]) / G.FINISH
    fin.write_text(json.dumps(json.loads(fin.read_text()) | {"status": "failed"}))
    cases["failed"] = out
    out = _copy(full_folder, tmp_path / "c")                                # 中断（終了の記録がない）
    (G.seed_dir(out, SYN[5]) / G.FINISH).unlink()
    (G.seed_dir(out, SYN[5]) / G.RAW).unlink()
    cases["interrupted"] = out
    out = _copy(full_folder, tmp_path / "d")                                # 穴埋め・余分な seed
    shutil.copytree(G.seed_dir(out, SYN[0]), G.seed_dir(out, GUARD_SEEDS[0]))
    cases["extra"] = out
    for name, out in cases.items():
        report = A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
        assert report["records"]["state"] == "failed", name
        assert not report["valid"] and report["judgment"] is None and _forbidden_keys(report) == set(), name


def test_analysis_refuses_mismatched_raw_and_records(full_folder, tmp_path) -> None:
    out = _copy(full_folder, tmp_path)

    def other_plan(run):
        run["plan"]["delay"] = 31
    _rewrite_raw(out, SYN[2], other_plan)
    report = A.analyze(out, "synthetic", SMALL, SYN, repo=full_folder[0])
    assert report["invalid_seeds"] == [SYN[2]] and "revalidate_from_raw" in report["checks"][str(SYN[2])]
    assert report["judgment"] is None


def test_smoke_analysis_never_computes_quantities(full_folder, tmp_path, monkeypatch) -> None:
    """smoke（操作の確認だけ）：判定の量・重みの材料を計算する関数は一度も呼ばれず、report に判定の量も現象に関する数値もない。
    （smoke の seed は使わず、合成の 20 個体を smoke の形に読み替えて確かめる）"""
    out = _copy(full_folder, tmp_path)
    for s in SYN:
        d = G.seed_dir(out, s)
        for name in (G.START, G.FINISH):
            rec = json.loads((d / name).read_text())
            (d / name).write_text(json.dumps(rec | {"mode": "smoke"}))
        data = json.loads(gzip.decompress((d / G.RAW).read_bytes()))
        data["meta"]["mode"] = "smoke"
        payload = gzip.compress(json.dumps(data).encode("utf-8"), mtime=0)
        (d / G.RAW).write_bytes(payload)
        fin = json.loads((d / G.FINISH).read_text())
        (d / G.FINISH).write_text(json.dumps(fin | {"raw_file_sha256": G.sha256_bytes(payload), "raw_file_bytes": len(payload)}))

    def boom(*a, **k):
        raise AssertionError("smoke で判定の量・重みの材料を計算した")
    for name in ("body_quantities", "quantities_for_seed", "design_eval", "four_events", "family_judgment", "judgment",
                 "weight_table", "weight_ranks", "rank"):
        monkeypatch.setattr(A, name, boom)
    monkeypatch.setattr(A, "expected_seeds", lambda mode: list(SYN))
    monkeypatch.setattr(A.W, "plan_from", lambda protocol: SMALL)
    report = A.analyze(out, "smoke", repo=full_folder[0])
    assert report["valid"] and report["judgment"] is None and report["count_arithmetic"] == "evaluated"
    assert _forbidden_keys(report) == set()
    assert set(report) == {"experiment", "kind", "mode", "seeds", "plan", "records", "analysis_commit", "valid",
                           "invalid_seeds", "count_arithmetic", "checks", "checks_evaluated", "judgment", "note"}


def test_report_destination_isolation(tmp_path, monkeypatch) -> None:
    root = tmp_path / "data" / "experiments"
    own = root / "0028"
    own.mkdir(parents=True)
    monkeypatch.setattr(A, "DATA_ROOT", root)
    monkeypatch.setattr(A, "OWN_DIR", own)
    assert A.report_destination(own, "formal") == own.resolve() / A.REPORT
    for folder, mode in ((root / "0027", "formal"), (tmp_path / "x", "formal"), (own, "smoke"), (root / "0027", "smoke"),
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
    for args in (("formal", SMALL, SYN), ("smoke", SMALL, None), ("synthetic", None, None), ("synthetic", SMALL, [21001]),
                 ("other", SMALL, SYN)):
        with pytest.raises(ERR):
            A.analyze(tmp_path, *args)
    with pytest.raises(ERR, match="未完了"):                                 # 何もない出力先は未完了（集計しない）
        A.analyze(tmp_path, "formal")


# ---- 8. 解析の道具の commit ＝ 測定の commit（protocol の execution.analysis_commit_must_equal_measurement_commit）--------

def _repo_copy(full_folder, where: Path) -> Path:
    """測定に使ったリポジトリの写し（full_folder のリポジトリそのものは変えない）。"""
    r = where / "repo"
    shutil.copytree(full_folder[0], r)
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
    for name in ("read_raw", "check_seed", "count_table", "body_quantities", "quantities_for_seed", "design_eval", "judgment"):
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
