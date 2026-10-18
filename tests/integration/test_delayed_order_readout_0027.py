"""実験 0027 の道具の契約テスト（確定した事前登録 v0.1 の README §1〜§9、protocol.yaml）。

本番の seed（20001〜20020）・smoke の seed（20101〜20106）は使わない（実行もしない）。合成の契約テスト専用の範囲
（20201〜20299）だけを使う。合成の個体は、本番と同じ道具（world.measure_seed）・同じ式で、値だけを小さくした Plan
（SMALL：試行 3、試し 5 回、T_w ＝ 15、遅れ 30。試行・試し・窓は 0023〜0026 の契約テストと同じ値。遅れは二つの全状態の範囲が
重ならない値）で実物の runtime を通して作る。結果を見て Plan・seed を選んでいない（seed は範囲の最初から順に使う）。

使った合成の seed（PR に開示）：
- 20201〜20220：SMALL の Plan で実物の runtime を通した 20 個体（確認の再検証・改ざんの検出・合成の集計の通し）
- 20221〜20240：一度限りの実行の契約（dummy の計算。runtime を使わない）
- 20241〜20250：並列数の契約（実際のプロセス。dummy の計算）
- 20299：可塑性の再生の照合に使う乱数の流れの名前だけ（runtime の個体は作らない）
- 本番の Plan（試行 200）での W の札の列の作り方の確認には 20201〜20206 の名前を使う（札の列を作るだけで、runtime の個体は作らない）
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
EXP = ROOT / "experiments" / "0027_delayed_order_readout"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))
PREREGISTRATION_MERGE = "7f4f28b4685334cf80a0a9b39c139b61291e640a"   # PR #117 のマージ（README・protocol の確定）
SYN = list(range(20201, 20221))
GUARD_SEEDS = list(range(20221, 20241))
POOL_SEEDS = list(range(20241, 20251))
TOOLS = ("world.py", "run.py", "analyze.py", "alignment.py", "guard.py")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W = _load("world_0027_test", EXP / "world.py")
G = _load("guard_0027_test", EXP / "guard.py")
A = _load("analyze_0027_test", EXP / "analyze.py")
R = _load("run_0027_test", EXP / "run.py")
sys.modules[R.__name__] = R          # 実際のプロセスへ compute_and_write を渡すため（本番では run.py が __main__）
ALIGN = _load("alignment_0027_test", EXP / "alignment.py")
SMALL = W.make_plan(PROTOCOL, 3, 5, 15, 30)
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
    """protocol.yaml は事前登録の確定（PR #117 のマージ）からバイト単位で変わっていない。README は確定した §0〜§14 が
    そのまま先頭に残っている（結果は後ろの節に追記する：README §14 の 4）。"""
    rel = f"experiments/{EXP.name}"
    assert (EXP / "protocol.yaml").read_bytes() == _git_show(PREREGISTRATION_MERGE, f"{rel}/protocol.yaml")
    assert (EXP / "README.md").read_bytes().startswith(_git_show(PREREGISTRATION_MERGE, f"{rel}/README.md"))


def test_runtime_core_and_other_experiments_are_unchanged_from_main() -> None:
    """0027 の道具を変える branch では、本体（src/）・設計（config/）・ほかの実験・0027 の事前登録の文書を同時に変えない
    （main との差分）。0027 の道具を変えない branch（後の PR）では確かめない（この PR の範囲の確認なので、後の作業を止めない）。"""
    try:
        base = subprocess.run(["git", "-C", str(ROOT), "merge-base", "HEAD", "origin/main"], capture_output=True,
                              text=True, check=True).stdout.strip()
        diff = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", base, "--", "src", "config", "experiments"],
                              capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git の履歴がない環境")
    tools = {f"experiments/{EXP.name}/{n}" for n in TOOLS}
    if not set(diff) & tools:
        pytest.skip("この branch は 0027 の道具を変えていない")
    assert set(diff) <= tools, sorted(set(diff) - tools)


FORBIDDEN = [r'"00(0\d|1\d|2[0-6])"', r"'00(0\d|1\d|2[0-6])'", r"data/experiments/00(0\d|1\d|2[0-6])",
             r"00(0\d|1\d|2[0-6])-(shuffle|within)", r"experiments/00(1[3-9]|2[0-6])_",
             r"experiments/0012_passive_world/(?!neuroarchitecture\.yaml)",
             r"(world|guard|run|analyze|alignment)_00(0\d|1\d|2[0-6])"]
SEED_NUMBERS = r"\b1[3456789][0-2]\d\d\b"   # 0020〜0026 の seed の範囲（13001〜19299）の数


def _code(name: str) -> str:
    """道具のコード（説明の文字列・コメントは除く。alignment.py の使用済みの seed の一覧 SEEN は重なりの確認の記録なので除く）。"""
    src = (EXP / name).read_text(encoding="utf-8")
    src = re.sub(r"SEEN = \(.*?\)\)\)\n", "", src, flags=re.DOTALL)
    src = re.sub(r'""".*?"""', "", src, flags=re.DOTALL)
    return "\n".join(line.split("#")[0] for line in src.splitlines())


def test_tools_hold_no_earlier_experiment_references() -> None:
    """道具は、ほかの実験の ID・出力先・乱数の流れの名前・道具（world.py など）を参照しない。0023〜0026 の道具も読み込まない。
    脳の設計図だけは protocol の brain.manifest（0014〜0026 と同じ共有の設計図）を読み、alignment.py がその名前を確かめる。"""
    for name in TOOLS:
        code = _code(name)
        for pat in FORBIDDEN:
            assert not re.search(pat, code), (name, pat)
        assert "_load(" not in code or all("experiments/" not in line for line in code.splitlines() if "_load(" in line), name
        plan_values = re.sub(r"\b14101\b", "", code)        # 本体の終わり 14101（Plan の値で、seed ではない）
        assert not re.search(SEED_NUMBERS, plan_values), (name, "0020〜0026 の seed の範囲の数")


def test_the_reference_scan_detects_leftovers() -> None:
    for leftover in ('EXPERIMENT = "0026"', 'OUT = "data/experiments/0025"', 'RNG = "0026-within-trial-{i}:{seed}"',
                     '_load("w", ROOT / "experiments/0026_state_block_swap/world.py")',
                     '"experiments/0012_passive_world/world.py"', "world_0026_for_x", "guard_0025"):
        assert any(re.search(p, leftover) for p in FORBIDDEN), leftover
    for leftover in ("SEEDS = range(19001, 19021)", "SYN = range(18201, 18251)", "seed = 19101"):
        assert re.search(SEED_NUMBERS, leftover), leftover
    src = (EXP / "alignment.py").read_text(encoding="utf-8")
    assert "range(19001" in src and "range(19001" not in _code("alignment.py") and {19001, 19299, 18299, 16299} <= ALIGN.SEEN


def test_tools_read_identity_from_this_protocol() -> None:
    ex = PROTOCOL["execution"]
    assert R.EXPERIMENT == A.EXPERIMENT == W.EXPERIMENT == PROTOCOL["experiment"] == ex["experiment_id"] == "0027"
    assert str(R.OUT_DIR) == str(A.DEFAULT_DIR) == ex["output_dir"]
    assert str(R.PROTOCOL_PATH) == str(A.PROTOCOL_PATH) == str(W.PROTOCOL_PATH) == ex["protocol_path"]
    assert W.RNG_SHUFFLE == PROTOCOL["conditions"]["within_trial_shuffles"]["rng"] == "0027-within-trial-{i}:{seed}"
    assert PROTOCOL["brain"]["manifest"] == "experiments/0012_passive_world/neuroarchitecture.yaml"
    for mode, key in (("formal", "seeds"), ("smoke", "smoke_seeds"), ("synthetic", "synthetic_seeds")):
        assert list(R.allowed_seeds(mode)) == A.expected_seeds(mode) == list(
            range(PROTOCOL[key]["first"], PROTOCOL[key]["last"] + 1))


# ---- 2. Plan・試しの時刻・刺激（README §2・§3）---------------------------------------------------------------------

def test_plan_from_protocol_is_the_registered_timeline() -> None:
    """本番の Plan：経験の終わり 12000、遅れ 1500（＝ 5 × τ_a）、早い時点 12001〜12300、遅い時点 13501〜13800、T_w 300、
    本体の終わり 14101。全状態の範囲は 11999〜12601 と 13500〜14101 で重ならない。"""
    p = W.plan_from(PROTOCOL)
    assert (p.trials, p.experience_end, p.delay, p.window, p.body_end) == (200, 12000, 1500, 300, 14101)
    assert list(p.probes_early) == list(range(12001, 12301)) and list(p.probes_late) == list(range(13501, 13801))
    assert (p.state_range("early"), p.state_range("late")) == ((11999, 12601), (13500, 14101))
    assert p.delay == W.DELAY_MULTIPLE * 300 and W.DELAY_MULTIPLE == 5
    assert p.probes_late[0] - 1 - p.experience_end == p.delay                       # 遅い時点の最初の複製の元は 12000 ＋ D
    assert W.plan_of(p.as_dict()) == p
    assert (SMALL.experience_end, SMALL.probes_early, SMALL.probes_late, SMALL.body_end) \
        == (180, (181, 182, 183, 184, 185), (211, 212, 213, 214, 215), 231)


def test_make_plan_refuses_overlapping_ranges_and_wrong_formulas() -> None:
    with pytest.raises(ValueError, match="重なる"):
        W.make_plan(PROTOCOL, 3, 5, 15, 10)                                       # 遅れが短すぎる
    for edit in (lambda p: p["timeline"]["probes_late"].update(first="experience_end + 1"),
                 lambda p: p["timeline"].update(body_runs_to="probes_early.first + 1"),
                 lambda p: p["timeline"].update(delay="3 * adaptation_tau / pulse_interval_seconds")):
        protocol = copy.deepcopy(PROTOCOL)
        edit(protocol)
        with pytest.raises(ValueError):
            W.plan_from(protocol)


def _balanced(labels, plan) -> bool:
    at = dict(labels)
    return all(sorted(at.get(t, "") for t in slots) == ["A", "B", "C"] for slots in W.trial_slots(PROTOCOL, plan))


def test_schedules_follow_the_protocol() -> None:
    """W_i は 0025 と同じ作り方（1 本の乱数の流れで、試行の順に [A, B, C] を 1 回ずつ並べ替えて 3 つの枠に置く）。19 本、M はない。"""
    plan = W.plan_from(PROTOCOL)
    o = W.ordered_labels(PROTOCOL, plan)
    assert len(o) == 600 and o[:3] == [(1, "A"), (3, "B"), (31, "C")] and o[-1] == (11971, "C") and _balanced(o, plan)
    for seed in SYN[:6]:
        seen = set()
        for i in range(1, 20):
            w = W.labels_of(PROTOCOL, plan, seed, f"W{i}")
            rnd, expected = random.Random(f"0027-within-trial-{i}:{seed}"), []
            for k in range(200):
                roles = ["A", "B", "C"]
                rnd.shuffle(roles)
                t = 1 + 60 * k
                expected += [(t, roles[0]), (t + 2, roles[1]), (t + 30, roles[2])]
            assert w == expected and [t for t, _ in w] == [t for t, _ in o] and _balanced(w, plan) and w != o
            seen.add(tuple(x for _, x in w))
        assert len(seen) == 19
    assert W.BODIES == ("O",) + tuple(f"W{i}" for i in range(1, 20)) and "M" not in W.BODIES


def test_alignment_refuses_drift_in_the_timeline_conditions_and_scope() -> None:
    cases = {
        "時間の流れ": [lambda p: p["timeline"].update(delay="10 * adaptation_tau / pulse_interval_seconds"),
                      lambda p: p["timeline"]["probes_late"].update(role="auxiliary"),
                      lambda p: p["timeline"]["probes_early"].update(first="experience_end + 2")],
        "条件": [lambda p: p["conditions"].update(M={"schedule": "mirrored"}),
                 lambda p: p["conditions"]["within_trial_shuffles"].update(count=20),
                 lambda p: p["conditions"]["within_trial_shuffles"].update(rng="0027-shuffle-{i}:{seed}")],
        "試しの手順": [lambda p: p["probe"].update(early_probes_do_not_change_body=False)],
        "判定の決まり": [lambda p: p["judgment"].update(statistic="h_early"),
                         lambda p: p["judgment"].update(holds_if="h >= 6"),
                         lambda p: p["judgment"]["not_judged"].pop()],
        "主・補助の量": [lambda p: p["quantities"]["not_used"].remove("decay_tests")],
        "記録の項目": [lambda p: p["records"].update(late_range="probes_late.first .. body_runs_to")],
        "操作の確認": [lambda p: p["checks"]["numeric"].pop("replay_history_late_start")],
        "seed": [lambda p: p.update(seeds={"first": 19001, "last": 19020})],
    }
    for what, edits in cases.items():
        for edit in edits:
            protocol = copy.deepcopy(PROTOCOL)
            edit(protocol)
            with pytest.raises((SystemExit, ValueError)) as e:
                ALIGN.check(protocol)
            assert e.type is ValueError or what in str(e.value), (what, str(e.value))


def test_roles_cycle_through_the_six_orders() -> None:
    orders = {tuple(W.role_receptors(PROTOCOL, s).values()) for s in SYN[:6]}
    assert len(orders) == 6


# ---- 3. 実物の runtime を通した合成の個体での操作の確認（README §2.3・§7）-------------------------------------------------

def test_all_checks_pass_on_a_real_runtime_individual(syn) -> None:
    assert _checks(syn) == {}
    table, problems = A.probe_table(syn["run"], SYN[0], SMALL)
    assert problems == [] and set(table) == {"early", "late"}
    assert all(tuple(table[w]) == W.BODIES and all(len(r) == 5 for r in table[w].values()) for w in W.WINDOWS)


def test_raw_holds_the_preregistered_items(syn) -> None:
    run = syn["run"]
    o = run["bodies"]["O"]
    assert {"birth", "labels", "spikes", "early", "late", "before_divergence", "rng"} <= set(o)
    for w in W.WINDOWS:
        lo, hi = SMALL.state_range(w)
        part = o[w]
        assert part["states_from"] == lo and len(part["states"]) == hi - lo + 1
        assert set(part["states"][0]) == set(W.FULL_STATE_FIELDS) and len(part["states"][0]["connections"]) == 6
        assert [e["t0"] for e in part["empty_side"]] == [SMALL.probes(w)[0], SMALL.probes(w)[-1]]
    assert [("states" in c) for c in o["late"]["probes"]] == [True] * 5            # 遅い時点：すべての試しで 4 時点
    assert [("states" in c) for c in o["early"]["probes"]] == [True, False, False, False, True]   # 早い時点：最初と最後
    tw = run["O_twin"]
    assert {"state_experience_end", "state_late_start", "state_end", "spikes", "birth"} <= set(tw)
    assert "early" not in tw and "late" not in tw
    assert tw["state_late_start"]["pulse"] == SMALL.state_range("late")[0]


def test_late_probes_are_at_the_registered_times(syn) -> None:
    """遅い時点の試しの t0 は experience_end ＋ delay ＋ 1 から、A の複製の入力は t0 の A の 1 つだけ。"""
    run = syn["run"]
    a_rec = run["roles"]["receptors"]["A"]
    for rec in run["bodies"].values():
        assert [c["t0"] for c in rec["late"]["probes"]] == list(SMALL.probes_late)
        assert rec["late"]["probes"][0]["t0"] == SMALL.experience_end + SMALL.delay + 1
        assert all(c["sensory"] == [[c["t0"], a_rec]] for w in W.WINDOWS for c in rec[w]["probes"])
        assert all(min((p for ps in c["spikes"].values() for p in ps), default=c["t0"]) >= c["t0"]
                   for c in rec["late"]["probes"])


def test_early_probes_do_not_change_the_body() -> None:
    """命題 0（README §2.3）：試しの複製を作った本体と、一度も作らない双子は、終わりまで発火も全状態も同じ。
    早い時点の試しだけを作った本体（遅い時点の試しも作る本体）でも、遅い時点の範囲の全状態は双子と同じ。"""
    labels = W.labels_of(PROTOCOL, SMALL, SYN[2], "O")
    a = W.run_body(PROTOCOL, SMALL, SYN[2], "O", labels, ())
    b = W.run_body(PROTOCOL, SMALL, SYN[2], "O_twin", labels, (), probes=False)
    assert a["spikes"] == b["spikes"]
    assert A.state_at(a, SMALL.experience_end) == b["state_experience_end"]
    assert A.state_at(a, SMALL.state_range("late")[0]) == b["state_late_start"]
    assert A.state_at(a, SMALL.body_end) == b["state_end"]
    w = W.labels_of(PROTOCOL, SMALL, SYN[2], "W3")
    c = W.run_body(PROTOCOL, SMALL, SYN[2], "W3", w, ())
    d = W.run_body(PROTOCOL, SMALL, SYN[2], "W3", w, (), deliver=False)          # 入力を入れない複製でも、本体は同じ
    assert c["spikes"] == d["spikes"] and c["late"]["states"] == d["late"]["states"]


def test_without_the_input_the_copy_is_the_body_itself() -> None:
    log = W.ExperimentLog()
    labels = W.labels_of(PROTOCOL, SMALL, SYN[1], "O")
    app = W.build(PROTOCOL, labels, SYN[1], "O", log)
    t0 = SMALL.probes_late[0]
    W.advance_to(app, t0 - 1)
    c = W.a_copy(PROTOCOL, SMALL, SYN[1], app, log, t0, deliver=False)
    W.advance_to(app, t0 + 1 + SMALL.window)
    assert c["sensory"] == [] and c["states"]["end"] == W.full_state(app)
    assert c["spikes"] == {u: [p for p in ps if p >= t0] for u, ps in log.spikes().items() if any(p >= t0 for p in ps)}


def test_probe_copy_equals_body_through_t0_plus_1_except_the_input_drive(syn) -> None:
    run = syn["run"]
    u = run["roles"]["units"]
    a_rec = run["roles"]["receptors"]["A"]
    for rec in run["bodies"].values():
        for w in W.WINDOWS:
            for c in rec[w]["probes"]:
                if "states" not in c:
                    continue
                t0 = c["t0"]
                body = A.state_at(rec, t0)
                assert c["states"]["t0-1"] == A.state_at(rec, t0 - 1)
                assert c["states"]["t0"]["units"] == body["units"] and c["states"]["t0"]["connections"] == body["connections"]
                assert [d for d in c["states"]["t0"]["drives"] if d not in body["drives"]] == [[a_rec, u["A"], 1.0, t0]]


def _tampered(syn, f) -> dict:
    data = copy.deepcopy(syn)
    f(data["run"])
    return _checks(data)


def test_late_and_early_probe_checks_detect_tampering(syn) -> None:
    u = syn["run"]["roles"]["units"]

    def late_clone(run):
        run["bodies"]["W3"]["late"]["probes"][2]["states"]["t0-1"]["units"][u["B"]][0] += 1e-15
    assert set(_tampered(syn, late_clone)) == {"probe_clone_equals_body_t0_minus_1"}

    def early_clone(run):
        run["bodies"]["W4"]["early"]["probes"][-1]["states"]["t0-1"]["units"][u["C"]][1] += 1e-15
    assert set(_tampered(syn, early_clone)) == {"probe_clone_equals_body_t0_minus_1"}

    def late_t1(run):
        run["bodies"]["W14"]["late"]["probes"][1]["states"]["t0+1"]["units"][u["C"]][1] += 1e-15
    assert set(_tampered(syn, late_t1)) == {"identical_through_t0_plus_1"}

    def late_drive(run):
        run["bodies"]["O"]["late"]["probes"][3]["states"]["t0"]["drives"] = []
    assert set(_tampered(syn, late_drive)) == {"identical_through_t0_plus_1"}

    def middle_states(run):                          # 早い時点の真ん中の試しに全状態がある（記録の項目と違う）
        p = run["bodies"]["W2"]["early"]["probes"]
        p[2]["states"] = p[0]["states"]
    assert set(_tampered(syn, middle_states)) == {"revalidate_from_raw"}

    def missing_late_states(run):
        del run["bodies"]["W2"]["late"]["probes"][2]["states"]
    assert set(_tampered(syn, missing_late_states)) == {"revalidate_from_raw"}

    def late_missing_probe(run):
        run["bodies"]["W9"]["late"]["probes"].pop()
    assert "revalidate_from_raw" in _tampered(syn, late_missing_probe)

    def body_fires_alone(run):                       # 早い時点の真ん中の試し（全状態のない試し）でも命題 3 を確かめる
        rec = run["bodies"]["W5"]
        c = rec["early"]["probes"][2]
        t = c["t0"] + 2
        rec["spikes"][u["B"]] = sorted(set(rec["spikes"].get(u["B"], [])) | {t})
        c["spikes"][u["B"]] = [p for p in c["spikes"].get(u["B"], []) if p != t]
    assert "proposition_3" in _tampered(syn, body_fires_alone)


def test_twin_empty_side_and_replay_checks_detect_tampering(syn) -> None:
    def twin_late_start(run):
        run["O_twin"]["state_late_start"]["units"]["s2"][1] += 1e-15
    assert set(_tampered(syn, twin_late_start)) == {"O_twin_identity"}

    def twin_end(run):
        run["O_twin"]["state_end"]["connections"]["s1.main->s2"][0] += 1e-15
    assert set(_tampered(syn, twin_end)) == {"O_twin_identity"}

    def twin_spike(run):
        sp = run["O_twin"]["spikes"]
        sp["s1"] = sorted(set(sp.get("s1", [])) ^ {SMALL.probes_late[2]})
    assert "O_twin_identity" in _tampered(syn, twin_spike)

    for w in W.WINDOWS:
        def empty_state(run, w=w):
            run["bodies"]["W7"][w]["empty_side"][1]["states"][4]["units"]["s2"][0] += 1e-15
        assert set(_tampered(syn, empty_state)) == {"empty_side_identity"}, w

    def late_start(run):                             # 遅い時点の始まりの重み（組の和は保つ）
        st = A.state_at(run["bodies"]["W1"], SMALL.state_range("late")[0])
        st["connections"]["s1.main->s2"][0] += 1e-9
        st["connections"]["s2.main->s1"][0] -= 1e-9
    assert "replay_history_late_start" in _tampered(syn, late_start)

    def w12000(run):
        st = A.state_at(run["bodies"]["W1"], SMALL.experience_end)
        st["connections"]["s1.main->s3"][0] += 1e-9
        st["connections"]["s3.main->s1"][0] -= 1e-9
    assert "replay_history_12000" in _tampered(syn, w12000)

    def pair(run):
        A.state_at(run["bodies"]["W1"], SMALL.body_end)["connections"]["s1.main->s3"][0] += 1e-9
    assert {"pair_sum", "no_clipping"} <= set(_tampered(syn, pair))


def test_label_input_and_divergence_checks_detect_tampering(syn) -> None:
    def rng(run):
        run["bodies"]["W2"]["rng"] = f"0027-within-trial-2:{SYN[1]}"
    assert set(_tampered(syn, rng)) == {"stimulus_labels"}

    def late_input(run):
        run["bodies"]["W9"]["sensory"].append([SMALL.probes_late[0], "receptor.x1"])
    assert "input_free_after_experience" in _tampered(syn, late_input)

    def late_double(run):
        c = run["bodies"]["O"]["late"]["probes"][0]
        c["sensory"] = c["sensory"] + [[c["t0"], "receptor.x2"]]
    assert set(_tampered(syn, late_double)) == {"input_free_after_experience"}

    def birth(run):
        run["bodies"]["W4"]["birth"]["units"]["s1"][0] += 1e-15
    assert "identical_before_label_divergence" in _tampered(syn, birth)


def test_replay_reports_clipping_and_matches_the_runtime_rule() -> None:
    from anima_ll.neuroarchitecture.plasticity import PlasticState, balanced_pair_window
    spec = W.plasticity(PROTOCOL)
    rnd = random.Random(20299)
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
    assert A.check_seed(syn, "synthetic", SYN[0], W.make_plan(PROTOCOL, 3, 5, 15, 31))["revalidate_from_raw"]
    data["run"]["bodies"].pop("W19")
    assert set(_checks(data)) == {"revalidate_from_raw"}
    data = copy.deepcopy(syn)
    data["run"]["bodies"]["O"]["late"]["states"].pop()
    assert "revalidate_from_raw" in _checks(data)
    data = copy.deepcopy(syn)
    data["run"]["O_twin"]["late"] = {}
    assert "revalidate_from_raw" in _checks(data)


# ---- 4. 打ち切りの算術と判定の量（README §4〜§6）--------------------------------------------------------------------

def test_censor_arithmetic_and_ell() -> None:
    plan = W.make_plan(PROTOCOL, 3, 2, 10, 30)
    t0a, t0b = plan.probes_late
    ca, cb = t0a + 12, t0b + 12
    rows = [(ca, ca, t0a + 2, ca, 0, 0, 1, 0), (t0b + 5, t0b + 11, cb, t0b + 2, 1, 1, 0, 1)]
    q = A.body_quantities(rows, plan.probes_late, plan.window)
    lB, lC = [0, 6], [ca - (t0a + 2), (t0b + 2) - cb]
    assert q["L"] == Fraction(sum(b - c for b, c in zip(lB, lC)), 2)
    assert (q["L_B"], q["L_C"]) == (Fraction(sum(lB), 2), Fraction(sum(lC), 2))
    assert q["censor_counts"] == {"B_A": 1, "B_null": 1, "C_A": 1, "C_null": 1}


def test_probe_table_routes_agree_and_detect_inconsistent_spikes(syn) -> None:
    table, problems = A.probe_table(syn["run"], SYN[0], SMALL)
    assert problems == []
    for w in W.WINDOWS:
        for rows in table[w].values():
            for t0, r in zip(SMALL.probes(w), rows):
                c = t0 + 2 + SMALL.window
                for n, N in zip(r[:4], r[4:8]):
                    assert (n == c) == (N == 0) and (t0 + 2 <= n <= t0 + 1 + SMALL.window or n == c)
    data = copy.deepcopy(syn)
    c = data["run"]["bodies"]["O"]["late"]["probes"][0]
    c["spikes"][data["run"]["roles"]["units"]["B"]] = [c["t0"] + 9, c["t0"] + 4]
    _, problems = A.probe_table(data["run"], SYN[0], SMALL)
    assert problems


def _q(L, censor=None) -> dict:
    return {"L": L, "censor_counts": censor or {"B_A": 0, "B_null": 0, "C_A": 0, "C_null": 0}}


def _bodies(o, s) -> dict:
    return {"O": _q(o)} | {f"W{i}": _q(x) for i, x in enumerate(s, 1)}


def test_window_eval_ties_frozen_and_direction() -> None:
    s = [Fraction(k, 300) for k in range(-9, 10)]
    assert not A.window_eval(_bodies(Fraction(9, 300), s), 300)["outside"]             # 最大と等しい
    up, down = A.window_eval(_bodies(Fraction(10, 300), s), 300), A.window_eval(_bodies(Fraction(-10, 300), s), 300)
    assert up["outside"] and up["direction"] == "above_max" and down["outside"] and down["direction"] == "below_min"
    fr = A.window_eval(_bodies(Fraction(0), [Fraction(0)] * 19), 300)
    assert fr["frozen"] and not fr["outside"] and fr["rank_of_L_O_among_20"] == {"shuffles_below": 0, "shuffles_equal": 19,
                                                                                 "shuffles_above": 0}
    with pytest.raises(ValueError):
        A.window_eval({"O": _q(Fraction(0))}, 300)


def test_silence_counts_per_window() -> None:
    P = 300
    per = _bodies(Fraction(1), [Fraction(0)] * 19)
    per["W3"]["censor_counts"] = {"B_A": P, "B_null": P, "C_A": 0, "C_null": 0}
    per["W4"]["censor_counts"] = {"B_A": P, "B_null": P - 1, "C_A": P, "C_null": P}
    ev = A.window_eval(per, P)
    assert ev["silence_counts"] == {"B": 1, "C": 1} and ev["outside"]


def test_judgment_uses_only_h_late_with_threshold_5() -> None:
    p = Fraction(1, 10)
    assert A.binom_tail(20, p, 5) <= Fraction(1, 20) < A.binom_tail(20, p, 4)

    def ind(e, l):
        f = lambda o: {"outside": o, "direction": "above_max" if o else None, "frozen": False}   # noqa: E731
        return {"early": f(e), "late": f(l)}
    for h_late, h_early in ((4, 20), (5, 0), (5, 5), (0, 0)):
        per = {str(s): {"individual": ind(k < h_early, k < h_late)} for k, s in enumerate(SYN)}
        j = A.judgment(per)
        assert (j["h_late"], j["h_early"], j["holds"], j["n"]) == (h_late, h_early, h_late >= 5, 20)
        assert sum(j["early_late_table"].values()) == 20
        assert j["early_late_table"]["early_outside__late_outside"] == min(h_late, h_early)
        assert j["scope"] == PROTOCOL["judgment"]["scope"] and j["not_judged"] == PROTOCOL["judgment"]["not_judged"]
    assert not any(k for k in j if "ratio" in k or "decay" in k or "difference" in k)


def test_clopper_pearson_reference_values() -> None:
    lo, hi = A.clopper_pearson(5, 20)
    assert abs(lo - 0.0866) < 1e-4 and abs(hi - 0.4910) < 1e-4


def test_an_all_censored_individual_is_frozen_and_not_outside() -> None:
    """D3：窓の中でどの Unit も発火しない（打ち切りだけの）個体でも、主の式が値を返し、凍結として「外にない」に数える。"""
    plan = W.make_plan(PROTOCOL, 3, 3, 10, 30)
    table = {w: {b: [(t0 + 2 + plan.window,) * 4 + (0,) * 4 for t0 in plan.probes(w)] for b in W.BODIES} for w in W.WINDOWS}
    q = A.quantities_for_seed(table, plan)
    assert all(v["L"]["exact"] == "0/1" for w in W.WINDOWS for v in q["bodies"][w].values())
    for w in W.WINDOWS:
        ev = q["individual"][w]
        assert ev["frozen"] and not ev["outside"] and ev["silence_counts"] == {"B": 20, "C": 20}


# ---- 5. seed を単位にした一度限りの実行（README §9、protocol execution.per_seed）------------------------------------

def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout.strip()


def _make_repo(base: Path) -> Path:
    r = base / "repo"
    (r / EXP.relative_to(ROOT)).mkdir(parents=True)
    (r / EXP.relative_to(ROOT) / "protocol.yaml").write_bytes((EXP / "protocol.yaml").read_bytes())
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@example.invalid")
    _git(r, "config", "user.name", "t")
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
    # 同時に 16 個が同じ seed の開始の記録を作ろうとしても、成功は 1 つだけ
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
    # 開始の記録がないまま何かがある seed は始めない
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
        assert json.loads(gzip.decompress((G.seed_dir(out, s) / G.RAW).read_bytes()))["run"]["seed"] == s
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
                          "started_at": "t", "experiment": "0027", "kind": PROTOCOL["kind"], "mode": "synthetic"})
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
    for mode, seeds in (("synthetic", [20001]), ("synthetic", [20300]), ("synthetic", [20101]), ("smoke", [20201]),
                        ("formal", [20021]), ("formal", [19001]), ("synthetic", [GUARD_SEEDS[0], GUARD_SEEDS[0]]),
                        ("synthetic", [])):
        with pytest.raises(ERR):
            R.execute(mode, seeds, out, repo, head, runner=_dummy, executor_factory=SerialExecutor)
    with pytest.raises(ERR, match="measurement-commit"):
        R.execute("formal", [20001], out, repo, None, runner=_dummy, executor_factory=SerialExecutor)
    with pytest.raises(ERR, match="指定した commit"):
        R.execute("formal", [20001], out, repo, "1" * 40, runner=_dummy, executor_factory=SerialExecutor)
    assert not (out / G.SEEDS_DIR).exists() or not any((out / G.SEEDS_DIR).iterdir())      # どの seed も始めていない
    # 出力先に範囲の外の seed（穴埋め）があれば始めない
    (G.seed_dir(out, 20300)).mkdir(parents=True)
    (G.seed_dir(out, 20300) / G.START).write_text("{}", encoding="utf-8")
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
    path = Path(os.environ["ANIMA_0027_TIMING_DIR"]) / f"{seed}.json"
    path.write_text(json.dumps({"seed": seed, "pid": os.getpid(), "t0": t0, "t1": t1}), encoding="utf-8")
    return {"seed": seed}


@pytest.mark.skipif(__import__("multiprocessing").get_start_method(allow_none=False) != "fork",
                    reason="テスト関数を子プロセスへ渡すのに fork が要る（本番の run.py は既定の runner を使う）")
def test_real_processes_never_exceed_two_at_once(repo, tmp_path, monkeypatch) -> None:
    timing = tmp_path / "timing"
    timing.mkdir()
    monkeypatch.setenv("ANIMA_0027_TIMING_DIR", str(timing))
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




# ---- 6. 解析：20 個体の完全性・invalid なら判定しない・一度だけ（README §5・§7・§9）---------------------------------------

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
    return {k for k in ('"L"', '"L_B"', '"h_late"', '"h_early"', '"outside"', '"per_seed"', '"silence_counts"',
                        '"censor_counts"', '"early_late_table"', '"direction"') if k in text}


def test_complete_valid_records_give_one_judgment(full_folder, tmp_path) -> None:
    out = _copy(full_folder, tmp_path)
    report = A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
    assert report["records"]["state"] == "complete" and report["valid"] and report["invalid_seeds"] == []
    assert report["analysis_commit"] == report["records"]["measurement_commit"] == _git(full_folder[0], "rev-parse", "HEAD")
    j = report["judgment"]
    assert j["n"] == 20 and j["holds"] == (j["h_late"] >= 5) and len(report["per_seed"]) == 20
    assert j["scope"] == PROTOCOL["judgment"]["scope"] and "h" not in j
    assert set(j["clopper_pearson_95_of_h_over_n"]) == {"late", "early"} and sum(j["early_late_table"].values()) == 20
    for v in report["per_seed"].values():
        assert set(v["bodies"]) == {"early", "late"} and all(tuple(v["bodies"][w]) == W.BODIES for w in W.WINDOWS)
        assert all(set(v["individual"][w]["silence_counts"]) == {"B", "C"} for w in W.WINDOWS)
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

    def tamper(run):                                 # O の双子の遅い時点の始まりの全状態だけを変える（命題 0 の確認）
        run["O_twin"]["state_late_start"]["units"]["s1"][0] += 1e-15
    _rewrite_raw(out, bad, tamper)
    report = A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
    assert report["records"]["state"] == "complete" and not report["valid"]
    assert report["invalid_seeds"] == [bad] and report["judgment"] is None
    assert set(report["checks"][str(bad)]) == {"O_twin_identity"}
    assert report["censor_arithmetic"] == "not_evaluated"
    assert _forbidden_keys(report) == set()                                  # invalid を「外にない」に数えず、量を出さない


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
    """smoke（操作の確認だけ）：判定の量を計算する関数は一度も呼ばれず、report に判定の量も現象に関する数値もない。
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
        raise AssertionError("smoke で判定の量を計算した")
    for name in ("body_quantities", "quantities_for_seed", "individual", "window_eval", "judgment", "silence_counts"):
        monkeypatch.setattr(A, name, boom)
    monkeypatch.setattr(A, "expected_seeds", lambda mode: list(SYN))
    monkeypatch.setattr(A.W, "plan_from", lambda protocol: SMALL)
    report = A.analyze(out, "smoke", repo=full_folder[0])
    assert report["valid"] and report["judgment"] is None and report["censor_arithmetic"] == "evaluated"
    assert _forbidden_keys(report) == set()
    assert set(report) == {"experiment", "kind", "mode", "seeds", "plan", "records", "analysis_commit", "valid",
                           "invalid_seeds", "censor_arithmetic", "checks", "checks_evaluated", "judgment", "note"}


def test_report_destination_isolation(tmp_path, monkeypatch) -> None:
    root = tmp_path / "data" / "experiments"
    own = root / "0027"
    own.mkdir(parents=True)
    monkeypatch.setattr(A, "DATA_ROOT", root)
    monkeypatch.setattr(A, "OWN_DIR", own)
    assert A.report_destination(own, "formal") == own.resolve() / A.REPORT
    for folder, mode in ((root / "0026", "formal"), (tmp_path / "x", "formal"), (own, "smoke"), (root / "0026", "smoke"),
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
    for args in (("formal", SMALL, SYN), ("smoke", SMALL, None), ("synthetic", None, None), ("synthetic", SMALL, [20001]),
                 ("other", SMALL, SYN)):
        with pytest.raises(ERR):
            A.analyze(tmp_path, *args)
    with pytest.raises(ERR, match="未完了"):                                 # 何もない出力先は未完了（集計しない）
        A.analyze(tmp_path, "formal")


# ---- 7. 解析の道具の commit ＝ 測定の commit（protocol の execution.analysis_commit_must_equal_measurement_commit）--------

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
    for name in ("read_raw", "check_seed", "probe_table", "body_quantities", "quantities_for_seed", "individual", "judgment"):
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
