"""実験 0026 の道具の契約テスト（確定した事前登録 v0.2 の README §1〜§9、protocol.yaml）。

本番の seed（19001〜19020）・smoke の seed（19101〜19106）は使わない（実行もしない）。合成の契約テスト専用の範囲
（19201〜19299）だけを使う。合成の個体は、本番と同じ道具（world.measure_seed）・同じ式で、値だけを小さくした Plan
（SMALL：試行 3、試し 5 回、T_w ＝ 15。0023〜0025 の契約テストと同じ値）で実物の runtime を通して作る。結果を見て Plan・seed を
選んでいない（seed は範囲の最初から順に使う）。

使った合成の seed（PR に開示）：
- 19201〜19220：SMALL の Plan で実物の runtime を通した 20 個体（確認の再検証・改ざんの検出・合成の集計の通し）
- 19221〜19240：一度限りの実行の契約（dummy の計算。runtime を使わない）
- 19241〜19250：並列数の契約（実際のプロセス。dummy の計算）
- 19299：可塑性の再生の照合に使う乱数の流れの名前だけ（runtime の個体は作らない）
- 本番の Plan（試行 200）での W の札の列の作り方の確認には 19201〜19206 の名前を使う（札の列を作るだけで、runtime の個体は作らない）
- 入れ替えの関数・T がない場合の確認には 19201〜19203 の個体を、SMALL の Plan で作り直す（同じ seed・同じ道具。新しい seed は使わない）
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
EXP = ROOT / "experiments" / "0026_state_block_swap"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))
PREREGISTRATION_MERGE = "0d9cfb31b0e4b93add741ae92605c152f3bddb5b"   # PR #114 のマージ（README・protocol の確定）
SYN = list(range(19201, 19221))
GUARD_SEEDS = list(range(19221, 19241))
POOL_SEEDS = list(range(19241, 19251))
TOOLS = ("world.py", "run.py", "analyze.py", "alignment.py", "guard.py")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W = _load("world_0026_test", EXP / "world.py")
G = _load("guard_0026_test", EXP / "guard.py")
A = _load("analyze_0026_test", EXP / "analyze.py")
R = _load("run_0026_test", EXP / "run.py")
sys.modules[R.__name__] = R          # 実際のプロセスへ compute_and_write を渡すため（本番では run.py が __main__）
ALIGN = _load("alignment_0026_test", EXP / "alignment.py")
SMALL = W.make_plan(PROTOCOL, 3, 5, 15)
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
    """protocol.yaml は事前登録の確定（PR #114 のマージ）からバイト単位で変わっていない。README は確定した §0〜§14 が
    そのまま先頭に残っている（結果は後ろの節に追記する：README §14 の 4）。"""
    rel = f"experiments/{EXP.name}"
    assert (EXP / "protocol.yaml").read_bytes() == _git_show(PREREGISTRATION_MERGE, f"{rel}/protocol.yaml")
    assert (EXP / "README.md").read_bytes().startswith(_git_show(PREREGISTRATION_MERGE, f"{rel}/README.md"))


def test_runtime_core_and_other_experiments_are_unchanged_from_main() -> None:
    """0026 の道具を変える branch では、本体（src/）・設計（config/）・ほかの実験・0026 の事前登録の文書を同時に変えない
    （main との差分）。0026 の道具を変えない branch（後の PR）では確かめない（この PR の範囲の確認なので、後の作業を止めない）。"""
    try:
        base = subprocess.run(["git", "-C", str(ROOT), "merge-base", "HEAD", "origin/main"], capture_output=True,
                              text=True, check=True).stdout.strip()
        diff = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", base, "--", "src", "config", "experiments"],
                              capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git の履歴がない環境")
    tools = {f"experiments/{EXP.name}/{n}" for n in TOOLS}
    if not set(diff) & tools:
        pytest.skip("この branch は 0026 の道具を変えていない")
    assert set(diff) <= tools, sorted(set(diff) - tools)


FORBIDDEN = [r'"00(0\d|1\d|2[0-5])"', r"'00(0\d|1\d|2[0-5])'", r"data/experiments/00(0\d|1\d|2[0-5])",
             r"00(0\d|1\d|2[0-5])-(shuffle|within)", r"experiments/00(1[3-9]|2[0-5])_",
             r"experiments/0012_passive_world/(?!neuroarchitecture\.yaml)",
             r"(world|guard|run|analyze|alignment)_00(0\d|1\d|2[0-5])"]
SEED_NUMBERS = r"\b1[345678][0-2]\d\d\b"   # 0020〜0025 の seed の範囲（13001〜18299）の数


def _code(name: str) -> str:
    """道具のコード（説明の文字列・コメントは除く。alignment.py の使用済みの seed の一覧 SEEN は重なりの確認の記録なので除く）。"""
    src = (EXP / name).read_text(encoding="utf-8")
    src = re.sub(r"SEEN = \(.*?\)\)\)\n", "", src, flags=re.DOTALL)
    src = re.sub(r'""".*?"""', "", src, flags=re.DOTALL)
    return "\n".join(line.split("#")[0] for line in src.splitlines())


def test_tools_hold_no_earlier_experiment_references() -> None:
    """道具は、ほかの実験の ID・出力先・乱数の流れの名前・道具（world.py など）を参照しない。0023〜0025 の道具も読み込まない。
    脳の設計図だけは protocol の brain.manifest（0014〜0025 と同じ共有の設計図）を読み、alignment.py がその名前を確かめる。"""
    for name in TOOLS:
        code = _code(name)
        for pat in FORBIDDEN:
            assert not re.search(pat, code), (name, pat)
        assert "_load(" not in code or all("experiments/" not in line for line in code.splitlines() if "_load(" in line), name
        assert not re.search(SEED_NUMBERS, code), (name, "0020〜0025 の seed の範囲の数")


def test_the_reference_scan_detects_leftovers() -> None:
    for leftover in ('EXPERIMENT = "0025"', 'OUT = "data/experiments/0025"', 'RNG = "0025-within-trial-{i}:{seed}"',
                     '_load("w", ROOT / "experiments/0025_within_trial_order_reference/world.py")',
                     '"experiments/0012_passive_world/world.py"', "world_0025_for_x", "guard_0024"):
        assert any(re.search(p, leftover) for p in FORBIDDEN), leftover
    for leftover in ("SEEDS = range(18001, 18021)", "SYN = range(17201, 17251)", "seed = 18101"):
        assert re.search(SEED_NUMBERS, leftover), leftover
    src = (EXP / "alignment.py").read_text(encoding="utf-8")
    assert "range(18001" in src and "range(18001" not in _code("alignment.py") and {18001, 18299, 17299, 16299} <= ALIGN.SEEN


def test_tools_read_identity_from_this_protocol() -> None:
    ex = PROTOCOL["execution"]
    assert R.EXPERIMENT == A.EXPERIMENT == W.EXPERIMENT == PROTOCOL["experiment"] == ex["experiment_id"] == "0026"
    assert str(R.OUT_DIR) == str(A.DEFAULT_DIR) == ex["output_dir"]
    assert str(R.PROTOCOL_PATH) == str(A.PROTOCOL_PATH) == str(W.PROTOCOL_PATH) == ex["protocol_path"]
    assert W.RNG_SHUFFLE == PROTOCOL["conditions"]["within_trial_shuffles"]["rng"] == "0026-within-trial-{i}:{seed}"
    assert PROTOCOL["brain"]["manifest"] == "experiments/0012_passive_world/neuroarchitecture.yaml"
    for mode, key in (("formal", "seeds"), ("smoke", "smoke_seeds"), ("synthetic", "synthetic_seeds")):
        assert list(R.allowed_seeds(mode)) == A.expected_seeds(mode) == list(
            range(PROTOCOL[key]["first"], PROTOCOL[key]["last"] + 1))
    assert (A.FAMILIES, A.DONORS, A.RECIPIENT) == (W.BLOCK_NAMES, W.DONORS, W.RECIPIENT)


def test_swap_uses_only_the_public_import_state() -> None:
    """README §2.4：入れ替えは Core の公開の import_state だけで行う。道具のコードは Core の内部の欄（_state・_plastic・_weights
    など）に触れない。"""
    for name in TOOLS:
        code = _code(name)
        assert not re.search(r"\._(state|plastic|weights|keys|spec|rule|dynamics|output|brain_state)\b", code), name
    code = _code("world.py")
    assert "u.import_state(" in code and "app.connections.import_state(" in code


# ---- 2. Plan・刺激・T の窓（README §2）----------------------------------------------------------------------------

def test_plan_window_and_selected_pulses_follow_the_protocol() -> None:
    p = W.plan_from(PROTOCOL)
    assert (p.trials, p.experience_end, p.probes[0], p.probes[-1], len(p.probes), p.window, p.body_end, p.states_from) \
        == (200, 12000, 12001, 12300, 300, 300, 12601, 11999)
    assert W.plan_of(p.as_dict()) == p
    assert W.swap_window(PROTOCOL, p) == (11972, 12000)                    # 最後の刺激 11971 の次から経験の終わりまで
    assert W.ordered_labels(PROTOCOL, p)[-1] == (11971, "C")
    assert W.selected_pulses(p) == (12000, 12001, 12002, 12299, 12300, 12301, 12601)
    assert (SMALL.experience_end, SMALL.probes, SMALL.body_end) == (180, (181, 182, 183, 184, 185), 201)
    assert W.swap_window(PROTOCOL, SMALL) == (152, 180)
    assert W.selected_pulses(SMALL) == (180, 181, 182, 184, 185, 186, 201)


def _balanced(labels, plan) -> bool:
    at = dict(labels)
    return all(sorted(at.get(t, "") for t in slots) == ["A", "B", "C"] for slots in W.trial_slots(PROTOCOL, plan))


def test_schedules_follow_the_protocol() -> None:
    """W_i は README §2.1・protocol の procedure のとおり：1 本の乱数の流れで、試行の順に [A, B, C] を 1 回ずつ並べ替えて 3 つの枠に置く。
    O・W_i のどの試行でも A・B・C が 1 回ずつ（試行の中の釣り合い）で、時刻の集合は O と同じ。W は 20 本で M はない。"""
    plan = W.plan_from(PROTOCOL)
    o = W.ordered_labels(PROTOCOL, plan)
    assert len(o) == 600 and o[:3] == [(1, "A"), (3, "B"), (31, "C")] and _balanced(o, plan)
    for seed in SYN[:6]:
        seen = set()
        for i in range(1, 21):
            w = W.labels_of(PROTOCOL, plan, seed, f"W{i}")
            rnd, expected = random.Random(f"0026-within-trial-{i}:{seed}"), []
            for k in range(200):
                roles = ["A", "B", "C"]
                rnd.shuffle(roles)
                t = 1 + 60 * k
                expected += [(t, roles[0]), (t + 2, roles[1]), (t + 30, roles[2])]
            assert w == expected
            assert [t for t, _ in w] == [t for t, _ in o] and _balanced(w, plan) and w != o
            seen.add(tuple(x for _, x in w))
        assert len(seen) == 20
    assert W.BODIES == ("O",) + tuple(f"W{i}" for i in range(1, 21)) and "M" not in W.BODIES
    assert W.DONORS == ("O",) + tuple(f"W{i}" for i in range(2, 21)) and W.RECIPIENT == "W1"


def test_find_swap_time_is_the_last_quiet_pulse_of_the_window() -> None:
    """README §2.2：T ＝ 窓の中で、どの本体でも、どの Unit も発火していない最後の Pulse。窓の外の発火は見ない。なければ None。"""
    lo, hi = 10, 20
    sp = {"O": {"s1": [5, 12, 20]}, "W1": {"s2": [19, 21]}, "W2": {"s3": [18]}}
    assert W.find_swap_time(sp, lo, hi) == 17
    sp["W3"] = {"s1": [17]}
    assert W.find_swap_time(sp, lo, hi) == 16
    full = {"O": {"s1": list(range(lo, hi + 1))}}
    assert W.find_swap_time(full, lo, hi) is None
    assert W.find_swap_time({"O": {"s1": list(range(lo, hi))}}, lo, hi) == hi
    assert W.find_swap_time({"O": {}}, lo, hi) == hi


def test_blocks_partition_the_dynamical_fields() -> None:
    """2 つの塊は、発火の回数を除く Unit・接続の欄を重ならずに覆う（README §2.3）。発火の回数はどちらにも入らない。"""
    unit_f = set(W.BLOCKS["weights"][0]) | set(W.BLOCKS["units"][0])
    conn_f = set(W.BLOCKS["weights"][1]) | set(W.BLOCKS["units"][1])
    assert unit_f == {"activity", "adaptation", "refractory_remaining"} and conn_f == set(W.CONNECTION_FIELDS)
    assert not set(W.BLOCKS["weights"][1]) & set(W.BLOCKS["units"][1]) and W.KEPT_UNIT_FIELDS == ("fire_count",)
    assert W.BLOCKS["weights"] == ((), ("weight",))


def test_alignment_refuses_drift_in_the_intervention_and_scope() -> None:
    """protocol の介入・参照の作り方・判定の範囲・記録が道具とずれたら、alignment が止める。"""
    cases = {
        "条件": [lambda p: p["conditions"]["within_trial_shuffles"].update(rng="0026-shuffle-{i}:{seed}"),
                 lambda p: p["conditions"]["within_trial_shuffles"].update(count=19),
                 lambda p: p["conditions"].update(M={"schedule": "mirrored"})],
        "介入": [lambda p: p["intervention"].update(recipient="W2"),
                 lambda p: p["intervention"]["donors"].pop(),
                 lambda p: p["intervention"]["blocks"]["weights"]["replace"].append("connections.pre_trace"),
                 lambda p: p["intervention"]["blocks"]["units"]["keep"].clear(),
                 lambda p: p["intervention"]["swap_time"].update(rule="T = 12000"),
                 lambda p: p["intervention"]["swap_time"].update(if_none="exclude_individual"),
                 lambda p: p["intervention"]["invariants_checked_on_swapped_state"].update(I1_pair_sum_tolerance=1e-9)],
        "判定の決まり": [lambda p: p["judgment"].update(scope="C0_C_II"),
                         lambda p: p["judgment"].update(holds_if="h >= 5"),
                         lambda p: p["judgment"]["not_judged"].pop()],
        "記録の項目": [lambda p: p["records"]["swapped_bodies"].update(per_probe_A_copy_states_for=["first"])],
        "操作の確認": [lambda p: p["checks"]["exact"].remove("null_swap_identity")],
        "seed": [lambda p: p.update(seeds={"first": 18001, "last": 18020})],
    }
    for what, edits in cases.items():
        for edit in edits:
            protocol = copy.deepcopy(PROTOCOL)
            edit(protocol)
            with pytest.raises(SystemExit) as e:
                ALIGN.check(protocol)
            assert what in str(e.value), (what, str(e.value))


def test_roles_cycle_through_the_six_orders() -> None:
    orders = {tuple(W.role_receptors(PROTOCOL, s).values()) for s in SYN[:6]}
    assert len(orders) == 6
    assert W.role_receptors(PROTOCOL, SYN[0]) == dict(zip("ABC", PROTOCOL["stimulus"]["role_orders"][(SYN[0] - 1) % 6]))


# ---- 3. 入れ替えの関数（実物の runtime。README §2.3・§2.4）------------------------------------------------------------

def _app_at(seed: int, body: str, pulse: int):
    log = W.ExperimentLog()
    app = W.build(PROTOCOL, W.labels_of(PROTOCOL, SMALL, seed, body), seed, body, log)
    W.advance_to(app, pulse)
    return app, log


def test_apply_swap_replaces_exactly_the_block_fields() -> None:
    """apply_swap は塊の欄だけをドナーの値にし、ほかの欄（発火の回数・駆動・Delta・Pulse）は受け手のまま。
    2 つの塊を順に入れ替えた結果は、両方を一度に入れ替えた結果と同じ。"""
    t = W.swap_window(PROTOCOL, SMALL)[0]
    rec_app, _ = _app_at(SYN[1], "W1", t)
    don_app, _ = _app_at(SYN[1], "O", t)
    r0, d0 = W.full_state(rec_app), W.full_state(don_app)
    assert r0 != d0
    for block in W.BLOCK_NAMES:
        app, log = W.clone(rec_app, W.ExperimentLog())
        W.apply_swap(app, d0, (block,))
        assert W.full_state(app) == A.composed_state(r0, d0, [block])
        assert W.full_state(rec_app) == r0                                # 受け手の元の個体は変わらない
    both, _ = W.clone(rec_app, W.ExperimentLog())
    W.apply_swap(both, d0, W.BLOCK_NAMES)
    seq, _ = W.clone(rec_app, W.ExperimentLog())
    W.apply_swap(seq, d0, ("weights",))
    W.apply_swap(seq, d0, ("units",))
    assert W.full_state(both) == W.full_state(seq) == A.composed_state(r0, d0, W.BLOCK_NAMES)
    assert W.full_state(both)["units"] != d0["units"] or r0["units"] == d0["units"]  # 発火の回数は受け手のまま
    assert all(W.full_state(both)["units"][u][3] == r0["units"][u][3] for u in r0["units"])
    with pytest.raises(ValueError):
        W.apply_swap(both, d0, ("drives",))


def test_a_full_swap_reproduces_the_donor_and_a_null_swap_the_recipient(syn) -> None:
    """README §7 の全部の入れ替え・入れ替えなし：実物の runtime を通した記録で、T より後の発火と終わりの全状態が一致する。"""
    run = syn["run"]
    T = run["swap_time"]
    assert T is not None
    o, w1 = run["bodies"]["O"], run["bodies"]["W1"]
    fs, ns = run["controls"]["full_swap"], run["controls"]["null_swap"]
    for u in A.UNITS:
        assert A.spikes_of(fs["spikes"], u) == A.in_range(o["spikes"], u, T + 1, SMALL.body_end)
        assert A.spikes_of(ns["spikes"], u) == A.in_range(w1["spikes"], u, T + 1, SMALL.body_end)
    assert A.without_fire_count(fs["state_end"]) == A.without_fire_count(A.state_at(o, SMALL.body_end))
    assert ns["state_end"] == A.state_at(w1, SMALL.body_end) and ns["state_T"] == w1["state_T"]


# ---- 4. 実物の runtime を通した合成の個体での操作の確認（README §7）---------------------------------------------------

def test_all_checks_pass_on_a_real_runtime_individual(syn) -> None:
    assert _checks(syn) == {}
    table, problems = A.probe_table(syn["run"], SYN[0], SMALL)
    assert problems == [] and set(table) == {"natural", "weights", "units"}
    assert tuple(table["natural"]) == W.BODIES and all(tuple(table[c]) == W.DONORS for c in W.BLOCK_NAMES)
    assert all(len(r) == 5 for v in table.values() for r in v.values())


def test_raw_holds_the_preregistered_items(syn) -> None:
    run = syn["run"]
    T = run["swap_time"]
    o = run["bodies"]["O"]
    assert run["swap_window"] == list(W.swap_window(PROTOCOL, SMALL)) and set(run) >= {"swapped", "controls", "O_twin"}
    assert {"birth", "labels", "spikes", "states", "probes", "empty_side", "before_divergence", "rng", "state_T"} <= set(o)
    assert "window_states" not in o and o["state_T"]["pulse"] == T
    assert o["states_from"] == SMALL.experience_end - 1 and len(o["states"]) == SMALL.body_end - SMALL.states_from + 1
    assert set(o["states"][0]) == set(W.FULL_STATE_FIELDS) and len(o["states"][0]["connections"]) == 6
    assert tuple(run["swapped"]) == W.BLOCK_NAMES and all(tuple(v) == W.DONORS for v in run["swapped"].values())
    y = run["swapped"]["units"]["W7"]
    assert set(y) == {"swap", "state_T", "sensory", "spikes", "states", "probes"}
    assert y["swap"] == {"T": T, "recipient": "W1", "blocks": ["units"], "donor": "W7"}
    assert sorted(map(int, y["states"])) == sorted(W.selected_pulses(SMALL))
    assert [("states" in c) for c in y["probes"]] == [True, False, False, False, True]
    assert all(p > T for ps in y["spikes"].values() for p in ps)
    assert set(run["controls"]) == {"full_swap", "null_swap"}
    assert set(run["controls"]["full_swap"]) == {"swap", "state_T", "state_experience_end", "state_end", "sensory", "spikes"}
    assert "probes" not in run["controls"]["full_swap"] and "probes" not in run["O_twin"]


def test_swapped_states_are_the_composed_states(syn) -> None:
    """入れ替えた状態は、W1 の T の状態の塊の欄だけをドナーの値にしたもの。重みの家族では痕跡・Unit の状態が W1 のまま、
    Unit の家族では重みと発火の回数が W1 のまま。"""
    run = syn["run"]
    w1 = run["bodies"]["W1"]["state_T"]
    for d in W.DONORS:
        dn = run["bodies"][d]["state_T"]
        yw, yu = run["swapped"]["weights"][d]["state_T"], run["swapped"]["units"][d]["state_T"]
        assert yw["units"] == w1["units"] and yu["drives"] == yw["drives"] == w1["drives"] == []
        assert all(yw["connections"][c] == [dn["connections"][c][0]] + w1["connections"][c][1:] for c in w1["connections"])
        assert all(yu["connections"][c] == [w1["connections"][c][0]] + dn["connections"][c][1:] for c in w1["connections"])
        assert all(yu["units"][u] == dn["units"][u][:3] + [w1["units"][u][3]] for u in w1["units"])
    assert A.invariant_problems(yu, "x") == [] and A.invariant_problems(yw, "x") == []


def _tampered(syn, f) -> dict:
    data = copy.deepcopy(syn)
    f(data["run"])
    return _checks(data)


def test_swap_checks_detect_tampering(syn) -> None:
    def composition(run):                            # 入れ替えた状態の重みを 1 つだけドナーと違う値に
        st = run["swapped"]["weights"]["W4"]["state_T"]["connections"]
        c = next(iter(st))
        st[c][0] += 1e-15
        st[next(k for k in st if A.W.unit_of(k) == tuple(reversed(A.W.unit_of(c))))][0] -= 1e-15
    assert "swap_composition" in _tampered(syn, composition)

    def record(run):
        run["swapped"]["units"]["W9"]["swap"]["donor"] = "W8"
    assert set(_tampered(syn, record)) == {"swap_composition"}

    def fire_count(run):                             # 発火の回数をドナーの値に：組み立てが違う
        st = run["swapped"]["units"]["O"]["state_T"]
        st["units"]["s1"][3] = run["bodies"]["O"]["state_T"]["units"]["s1"][3] + 1
    assert set(_tampered(syn, fire_count)) == {"swap_composition"}

    def full_state(run):
        run["controls"]["full_swap"]["state_end"]["units"]["s2"][0] += 1e-15
    assert set(_tampered(syn, full_state)) == {"full_swap_reproduces_donor"}

    def full_fire_count(run):                        # 全部の入れ替えは発火の回数を比べない
        run["controls"]["full_swap"]["state_end"]["units"]["s2"][3] += 1
    assert set(_tampered(syn, full_fire_count)) == set()

    def full_spike(run):
        sp = run["controls"]["full_swap"]["spikes"]
        sp["s3"] = sorted(set(sp.get("s3", [])) ^ {SMALL.body_end})
    assert "full_swap_reproduces_donor" in _tampered(syn, full_spike)

    def null_fire_count(run):                        # 入れ替えなしは発火の回数も含めて W1 と同じ
        run["controls"]["null_swap"]["state_experience_end"]["units"]["s1"][3] += 1
    assert set(_tampered(syn, null_fire_count)) == {"null_swap_identity"}

    def selected(run):                               # 入れ替えた本体の 12000 の重み（組の和は保つ）
        st = run["swapped"]["units"]["W3"]["states"][str(SMALL.experience_end)]["connections"]
        st["s1.main->s2"][0] += 1e-9
        st["s2.main->s1"][0] -= 1e-9
    assert "replay_history_12000" in _tampered(syn, selected)

    def swapped_probe(run):
        run["swapped"]["weights"]["W5"]["probes"][-1]["states"]["t0-1"]["units"]["s1"][1] += 1e-15
    assert set(_tampered(syn, swapped_probe)) == {"probe_clone_equals_body_t0_minus_1"}

    def swapped_input(run):
        run["swapped"]["weights"]["W6"]["sensory"].append([SMALL.probes[2], "receptor.x1"])
    assert set(_tampered(syn, swapped_input)) == {"input_free_after_experience"}

    def control_input(run):
        run["controls"]["null_swap"]["sensory"].append([SMALL.body_end, "receptor.x2"])
    assert set(_tampered(syn, control_input)) == {"input_free_after_experience"}

    def middle_states(run):                          # 最初と最後以外の試しに全状態がある（記録の項目と違う）
        y = run["swapped"]["units"]["W2"]
        y["probes"][2]["states"] = y["probes"][0]["states"]
    assert set(_tampered(syn, middle_states)) == {"revalidate_from_raw"}

    def missing_family(run):
        run["swapped"]["weights"].pop("W20")
    assert set(_tampered(syn, missing_family)) == {"revalidate_from_raw"}

    def donor_state(run):                            # ドナーの T の状態だけを変えると、組み立てとドナーの再生が食い違う
        run["bodies"]["W11"]["state_T"]["connections"]["s3.main->s1"][1] += 1e-9
    assert {"swap_composition", "replay_history_12000"} <= set(_tampered(syn, donor_state))


def test_invariants_are_checked_on_the_swapped_states() -> None:
    """I1〜I4（README §3）：組の和、痕跡が Unit ごとに一つ、activity が正、駆動・Delta がない。"""
    run = W.measure_seed(PROTOCOL, SYN[2], SMALL)
    st = json.loads(json.dumps(run["swapped"]["weights"]["O"]["state_T"]))
    assert A.invariant_problems(st, "Y") == []
    cases = {"I1": lambda s: s["connections"]["s1.main->s3"].__setitem__(0, s["connections"]["s1.main->s3"][0] + 1e-9),
             "I2": lambda s: s["connections"]["s1.main->s2"].__setitem__(1, s["connections"]["s1.main->s2"][1] + 1e-15),
             "I3": lambda s: s["units"]["s2"].__setitem__(0, 0.0),
             "I4": lambda s: s["drives"].append(["s1", "s2", 0.005, run["swap_time"]])}
    for name, f in cases.items():
        bad = copy.deepcopy(st)
        f(bad)
        problems = A.invariant_problems(bad, "Y")
        assert problems and all(f"（{name}）" in p for p in problems), (name, problems)
    deltas = copy.deepcopy(st) | {"deltas": 1}
    assert any("（I4）" in p for p in A.invariant_problems(deltas, "Y"))


def test_invariant_tampering_in_the_record_is_reported(syn) -> None:
    def i3(run):
        run["swapped"]["units"]["W12"]["state_T"]["units"]["s3"][0] = -1.0
    assert {"swap_invariants", "swap_composition"} <= set(_tampered(syn, i3))

    def i4(run):
        run["controls"]["full_swap"]["state_T"]["drives"] = [["s1", "s2", 0.005, run["swap_time"]]]
    assert {"swap_invariants", "swap_composition"} <= set(_tampered(syn, i4))


def _run_with(syn, f):
    run = copy.deepcopy(syn["run"])
    f(run)
    out = {k: [] for k in A.CHECK_NAMES}
    A._check_swap_time(run, SMALL, out)
    return out["swap_time_rule"]


def test_swap_time_rule_is_recounted_from_the_spikes(syn) -> None:
    """T の規則（README §2.2・§7）：記録の T が、自然な 21 本体の発火の列から数え直した T と同じで、T に発火がなく、
    T より後の窓のどの Pulse にもどこかで発火がある。T がないなら、窓のどの Pulse にも発火がある。"""
    lo, hi = W.swap_window(PROTOCOL, SMALL)
    T = syn["run"]["swap_time"]
    assert _run_with(syn, lambda run: None) == []

    def spike_at_T(run):
        sp = run["bodies"]["W5"]["spikes"]
        sp["s2"] = sorted(set(sp.get("s2", [])) | {T})
    assert any("T に" in p for p in _run_with(syn, spike_at_T))

    def claims_none(run):
        run["swap_time"] = None
    assert _run_with(syn, claims_none)

    def earlier(run):                                # 記録の T を、より早い静かな Pulse にする
        fired = {t for rec in run["bodies"].values() for ps in rec["spikes"].values() for t in ps}
        quiet = [t for t in range(lo, T) if t not in fired]
        run["swap_time"] = quiet[-1] if quiet else lo - 1
    assert _run_with(syn, earlier)

    def all_fired(run):                              # 窓のすべての Pulse に発火があり、T なしと記録した場合は成り立つ
        run["swap_time"] = None
        sp = run["bodies"]["O"]["spikes"]
        sp["s1"] = sorted(set(sp.get("s1", [])) | set(range(lo, hi + 1)))
    assert _run_with(syn, all_fired) == []

    def drive_at_T(run):
        run["bodies"]["W17"]["state_T"]["drives"] = [["s1", "s3", 0.005, T]]
    assert any("駆動" in p for p in _run_with(syn, drive_at_T))


def test_an_individual_without_t_has_no_swaps_and_a_wrong_none_is_caught(monkeypatch) -> None:
    """D3：T がない個体では、入れ替えた本体・確認の本体を作らず、state_T を None にする（除外しない）。
    実物の個体で T を None と偽った記録は、T の規則の確認だけが成り立たない（ほかの確認は T がない形として通る）。"""
    monkeypatch.setattr(W, "find_swap_time", lambda spikes, lo, hi: None)
    run = W.measure_seed(PROTOCOL, SYN[3], SMALL)
    assert run["swap_time"] is None and run["controls"] is None and run["swapped"] == {"weights": {}, "units": {}}
    assert all(rec["state_T"] is None for rec in run["bodies"].values())
    assert set(_checks(_raw(run), SYN[3])) == {"swap_time_rule"}
    table, problems = A.probe_table(_raw(run)["run"], SYN[3], SMALL)
    assert problems == [] and table["weights"] == table["units"] == {}


def test_every_body_received_one_a_b_c_in_every_trial(syn) -> None:
    run = syn["run"]
    to_role = {r: role for role, r in run["roles"]["receptors"].items()}
    for b, rec in run["bodies"].items():
        got = [(p, to_role[r]) for p, r in rec["sensory"] if p <= SMALL.experience_end]
        assert len(got) == 3 * SMALL.trials and _balanced(got, SMALL), b


def test_probe_copy_equals_body_through_t0_plus_1_except_the_input_drive(syn) -> None:
    run = syn["run"]
    u = run["roles"]["units"]
    a_rec = run["roles"]["receptors"]["A"]
    targets = [(rec, lambda p, rec=rec: A.state_at(rec, p), rec["probes"]) for rec in run["bodies"].values()]
    targets += [(rec, lambda p, rec=rec: A.selected_at(rec, p), [c for c in rec["probes"] if "states" in c])
                for _, _, _, rec in A.swapped_bodies(run)]
    for rec, at, probes in targets:
        for c in probes:
            t0 = c["t0"]
            assert c["states"]["t0-1"] == at(t0 - 1)
            body = at(t0)
            assert c["states"]["t0"]["units"] == body["units"] and c["states"]["t0"]["connections"] == body["connections"]
            assert [d for d in c["states"]["t0"]["drives"] if d not in body["drives"]] == [[a_rec, u["A"], 1.0, t0]]


def test_without_the_input_the_copy_is_the_body_itself() -> None:
    log = W.ExperimentLog()
    labels = W.labels_of(PROTOCOL, SMALL, SYN[1], "O")
    app = W.build(PROTOCOL, labels, SYN[1], "O", log)
    t0 = SMALL.probes[0]
    W.advance_to(app, t0 - 1)
    c = W.a_copy(PROTOCOL, SMALL, SYN[1], app, log, t0, deliver=False)
    W.advance_to(app, t0 + 1 + SMALL.window)
    assert c["sensory"] == [] and c["states"]["end"] == W.full_state(app)
    assert c["spikes"] == {u: [p for p in ps if p >= t0] for u, ps in log.spikes().items() if any(p >= t0 for p in ps)}


def test_cloning_does_not_change_the_body() -> None:
    labels = W.labels_of(PROTOCOL, SMALL, SYN[2], "O")
    a, _ = W.run_body(PROTOCOL, SMALL, SYN[2], "O", labels, (), keep_clones=True)
    b, _ = W.run_body(PROTOCOL, SMALL, SYN[2], "O_twin", labels, (), probes=False)
    assert a["spikes"] == b["spikes"] and A.state_at(a, SMALL.body_end) == b["state_end"]


def test_natural_checks_detect_tampering(syn) -> None:
    u = syn["run"]["roles"]["units"]

    def clone_state(run):
        run["bodies"]["W3"]["probes"][2]["states"]["t0-1"]["units"][u["B"]][0] += 1e-15
    assert set(_tampered(syn, clone_state)) == {"probe_clone_equals_body_t0_minus_1"}

    def t1_state(run):
        run["bodies"]["W14"]["probes"][1]["states"]["t0+1"]["units"][u["C"]][1] += 1e-15
    assert set(_tampered(syn, t1_state)) == {"identical_through_t0_plus_1"}

    def empty_state(run):
        run["bodies"]["W7"]["empty_side"][1]["states"][4]["units"]["s2"][0] += 1e-15
    assert set(_tampered(syn, empty_state)) == {"empty_side_identity"}

    def twin(run):
        run["O_twin"]["state_end"]["connections"]["s1.main->s2"][0] += 1e-15
    assert set(_tampered(syn, twin)) == {"O_twin_identity"}

    def rng(run):
        run["bodies"]["W2"]["rng"] = f"0026-within-trial-2:{SYN[1]}"
    assert set(_tampered(syn, rng)) == {"stimulus_labels"}

    def unbalanced(run):
        labels = run["bodies"]["W6"]["labels"]
        j = next(j for j in range(3, len(labels)) if labels[j][1] != labels[0][1])
        labels[0][1], labels[j][1] = labels[j][1], labels[0][1]
    assert "stimulus_labels" in _tampered(syn, unbalanced)

    def late_input(run):
        run["bodies"]["W9"]["sensory"].append([SMALL.experience_end + 3, "receptor.x1"])
    assert "input_free_after_experience" in _tampered(syn, late_input)

    def birth(run):
        run["bodies"]["W4"]["birth"]["units"]["s1"][0] += 1e-15
    assert "identical_before_label_divergence" in _tampered(syn, birth)

    def w12000(run):
        st = A.state_at(run["bodies"]["W1"], SMALL.experience_end)
        st["connections"]["s1.main->s2"][0] += 1e-9
        st["connections"]["s2.main->s1"][0] -= 1e-9
    assert "replay_history_12000" in _tampered(syn, w12000)

    def pair(run):
        A.state_at(run["bodies"]["W1"], SMALL.body_end)["connections"]["s1.main->s3"][0] += 1e-9
    assert {"pair_sum", "no_clipping"} <= set(_tampered(syn, pair))

    def t_state(run):                                # 自然な本体の T の状態の重み（再生と食い違う）
        run["bodies"]["W19"]["state_T"]["connections"]["s2.main->s3"][0] += 1e-9
    assert "replay_history_12000" in _tampered(syn, t_state)


def test_proposition_3_is_checked_on_every_probe_of_every_body(syn) -> None:
    run = syn["run"]
    u = run["roles"]["units"]
    for _, _, _, rec in A.swapped_bodies(run):
        for c in rec["probes"]:
            for role in "BC":
                assert A.fired_at(c["spikes"], u[role], c["t0"] + 2) >= A.fired_at(rec["spikes"], u[role], c["t0"] + 2)

    def body_fires_alone(run):                       # 入れ替えた本体の真ん中の試し（全状態のない試し）でも確かめる
        rec = run["swapped"]["weights"]["W10"]
        c = rec["probes"][2]
        t = c["t0"] + 2
        ub = u["B"]
        rec["spikes"][ub] = sorted(set(rec["spikes"].get(ub, [])) | {t})
        c["spikes"][ub] = [p for p in c["spikes"].get(ub, []) if p != t]
    assert "proposition_3" in _tampered(syn, body_fires_alone)


def test_replay_reports_clipping_and_matches_the_runtime_rule() -> None:
    from anima_ll.neuroarchitecture.plasticity import PlasticState, balanced_pair_window
    spec = W.plasticity(PROTOCOL)
    rnd = random.Random(19299)
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
    assert A.check_seed(syn, "synthetic", SYN[0], W.make_plan(PROTOCOL, 3, 5, 16))["revalidate_from_raw"]
    data["run"]["bodies"].pop("W20")
    assert set(_checks(data)) == {"revalidate_from_raw"}
    data = copy.deepcopy(syn)
    data["run"]["swap_window"] = [151, 180]
    assert "revalidate_from_raw" in _checks(data)
    data = copy.deepcopy(syn)
    data["run"]["controls"] = None
    assert "revalidate_from_raw" in _checks(data)
    data = copy.deepcopy(syn)
    data["run"]["swapped"]["weights"]["W2"]["spikes"]["s1"] = [SMALL.experience_end - 40]
    assert "revalidate_from_raw" in _checks(data)


# ---- 5. 打ち切りの算術と判定の量（README §4〜§6）--------------------------------------------------------------------

def test_censor_arithmetic_and_ell() -> None:
    plan = W.make_plan(PROTOCOL, 3, 2, 10)
    t0a, t0b = plan.probes
    ca, cb = t0a + 12, t0b + 12
    rows = [(ca, ca, t0a + 2, ca, 0, 0, 1, 0), (t0b + 5, t0b + 11, cb, t0b + 2, 1, 1, 0, 1)]
    q = A.body_quantities(rows, plan)
    lB, lC = [0, 6], [ca - (t0a + 2), (t0b + 2) - cb]
    assert q["L"] == Fraction(sum(b - c for b, c in zip(lB, lC)), 2)
    assert (q["L_B"], q["L_C"]) == (Fraction(sum(lB), 2), Fraction(sum(lC), 2))
    assert q["censor_counts"] == {"B_A": 1, "B_null": 1, "C_A": 1, "C_null": 1}
    assert set(q) == {"L", "L_B", "L_C", "censor_counts"}


def test_probe_table_routes_agree_and_detect_inconsistent_spikes(syn) -> None:
    table, problems = A.probe_table(syn["run"], SYN[0], SMALL)
    assert problems == []
    for v in table.values():
        for rows in v.values():
            for t0, r in zip(SMALL.probes, rows):
                c = t0 + 2 + SMALL.window
                for n, N in zip(r[:4], r[4:8]):
                    assert (n == c) == (N == 0) and (t0 + 2 <= n <= t0 + 1 + SMALL.window or n == c)
    data = copy.deepcopy(syn)
    c = data["run"]["swapped"]["units"]["O"]["probes"][0]
    c["spikes"][data["run"]["roles"]["units"]["B"]] = [c["t0"] + 9, c["t0"] + 4]
    _, problems = A.probe_table(data["run"], SYN[0], SMALL)
    assert problems


def _q(L, censor=None) -> dict:
    return {"L": L, "censor_counts": censor or {"B_A": 0, "B_null": 0, "C_A": 0, "C_null": 0}}


def _per(nat_o, nat_w, fam=None) -> dict:
    """自然な本体（O・W1〜W20）と 2 つの家族（ドナー O・W2〜W20）の量。fam：{塊: (O の L, [W2〜W20 の L])}。"""
    per = {"natural": {"O": _q(nat_o)} | {f"W{i}": _q(x) for i, x in enumerate(nat_w, 1)}}
    for c in W.BLOCK_NAMES:
        if fam is None:
            per[c] = {}
        else:
            o, refs = fam[c]
            per[c] = {"O": _q(o)} | {f"W{i}": _q(x) for i, x in enumerate(refs, 2)}
    return per


def test_family_outside_ties_and_frozen() -> None:
    refs = [Fraction(k, 300) for k in range(-9, 10)]
    nat = [Fraction(0)] * 20
    ind = A.individual(_per(Fraction(0), nat, {"weights": (Fraction(9, 300), refs), "units": (Fraction(10, 300), refs)}),
                       300, 175)
    assert not ind["weights"]["outside"] and ind["units"]["outside"] and ind["units"]["direction"] == "above_max"
    assert ind["weights"]["rank_of_donor_O_among_20"] == {"donors_below": 18, "donors_equal": 1, "donors_above": 0}
    frozen = A.individual(_per(Fraction(0), nat, {"weights": (Fraction(0), [Fraction(0)] * 19),
                                                  "units": (Fraction(-10, 300), refs)}), 300, 175)
    assert frozen["weights"]["frozen"] and not frozen["weights"]["outside"]
    assert frozen["units"]["outside"] and frozen["units"]["direction"] == "below_min"
    assert not frozen["natural_outside"] and frozen["swap_time"] == 175 and not frozen["no_swap_time"]


def test_an_individual_without_t_is_not_outside_in_both_families() -> None:
    """D3：T がない個体は、両方の判定で「外にない」（除外しない）。自然な比較は補助として記録する。"""
    nat = [Fraction(k, 300) for k in range(20)]
    ind = A.individual(_per(Fraction(-5, 300), nat), 300, None)
    assert ind["no_swap_time"] and ind["swap_time"] is None
    assert not ind["weights"]["outside"] and not ind["units"]["outside"]
    assert ind["weights"]["not_outside_because"] == "no_swap_time" and ind["natural_outside"]
    assert ind["silence_counts"]["weights"] is None and set(ind["silence_counts"]["natural"]) == {"B", "C"}
    with pytest.raises(ValueError):
        A.individual(_per(Fraction(0), nat, {"weights": (Fraction(0), nat[:19]), "units": (Fraction(0), nat[:19])}), 300, None)


def test_silence_counts_per_set_of_bodies() -> None:
    P = 300
    silent = {"B_A": P, "B_null": P, "C_A": 0, "C_null": 0}
    per = _per(Fraction(0), [Fraction(0)] * 20, {"weights": (Fraction(1), [Fraction(0)] * 19),
                                                 "units": (Fraction(1), [Fraction(0)] * 19)})
    per["natural"]["W3"]["censor_counts"] = silent
    per["weights"]["W3"]["censor_counts"] = silent
    per["weights"]["W4"]["censor_counts"] = {"B_A": P, "B_null": P - 1, "C_A": P, "C_null": P}
    ind = A.individual(per, P, 170)
    assert ind["silence_counts"] == {"natural": {"B": 1, "C": 0}, "weights": {"B": 1, "C": 1}, "units": {"B": 0, "C": 0}}
    assert ind["weights"]["outside"] and ind["units"]["outside"]          # 補助は外にあるかを変えない


def test_two_judgments_each_at_h_6_with_bonferroni() -> None:
    p = Fraction(1, 10)
    assert A.binom_tail(20, p, 6) <= Fraction(1, 40) < A.binom_tail(20, p, 5)
    assert abs(float(A.binom_tail(20, p, 6)) - 0.011253) < 5e-6 and abs(float(A.binom_tail(20, p, 5)) - 0.043174) < 5e-6

    def ind(w, u):
        f = lambda o: {"outside": o, "direction": "above_max" if o else None, "frozen": False}   # noqa: E731
        return {"weights": f(w), "units": f(u), "no_swap_time": False, "natural_outside": False}
    for hw, hu in ((5, 6), (6, 5), (0, 20), (6, 6)):
        per = {str(s): {"individual": ind(k < hw, k < hu)} for k, s in enumerate(SYN)}
        j = A.judgment(per)
        assert (j["h_weights"], j["h_units"], j["holds_weights"], j["holds_units"]) == (hw, hu, hw >= 6, hu >= 6)
        assert j["n"] == 20 and j["holds_if"] == "h >= 6" and (j["alpha_each"], j["alpha_family"]) == (0.025, 0.05)
        assert j["scope"] == PROTOCOL["judgment"]["scope"] and j["not_judged"] == PROTOCOL["judgment"]["not_judged"]
    assert not any(k for k in j if "ratio" in k or "difference" in k or "combined" in k)


def test_clopper_pearson_reference_values() -> None:
    lo, hi = A.clopper_pearson(6, 20)
    assert abs(lo - 0.1189) < 1e-4 and abs(hi - 0.5428) < 1e-4
    assert A.clopper_pearson(0, 20)[0] == 0.0 and A.clopper_pearson(20, 20)[1] == 1.0


def test_an_all_censored_individual_is_frozen_and_not_outside() -> None:
    """D3：窓の中でどの Unit も発火しない（打ち切りだけの）個体でも、主の式が値を返し、凍結として「外にない」に数える。"""
    plan = W.make_plan(PROTOCOL, 3, 3, 10)
    rows = [(t0 + 2 + plan.window,) * 4 + (0,) * 4 for t0 in plan.probes]
    table = {"natural": {b: rows for b in W.BODIES}, "weights": {d: rows for d in W.DONORS},
             "units": {d: rows for d in W.DONORS}}
    q = A.quantities_for_seed(table, plan, 160)
    assert all(v["L"]["exact"] == "0/1" for fam in q["bodies"].values() for v in fam.values())
    ind = q["individual"]
    assert ind["weights"]["frozen"] and ind["units"]["frozen"] and not ind["weights"]["outside"] and not ind["units"]["outside"]
    assert ind["silence_counts"] == {"natural": {"B": 21, "C": 21}, "weights": {"B": 20, "C": 20},
                                     "units": {"B": 20, "C": 20}}


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
                          "started_at": "t", "experiment": "0026", "kind": PROTOCOL["kind"], "mode": "synthetic"})
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
    for mode, seeds in (("synthetic", [19001]), ("synthetic", [19300]), ("synthetic", [19101]), ("smoke", [19201]),
                        ("formal", [19021]), ("formal", [18001]), ("synthetic", [GUARD_SEEDS[0], GUARD_SEEDS[0]]),
                        ("synthetic", [])):
        with pytest.raises(ERR):
            R.execute(mode, seeds, out, repo, head, runner=_dummy, executor_factory=SerialExecutor)
    with pytest.raises(ERR, match="measurement-commit"):
        R.execute("formal", [19001], out, repo, None, runner=_dummy, executor_factory=SerialExecutor)
    with pytest.raises(ERR, match="指定した commit"):
        R.execute("formal", [19001], out, repo, "1" * 40, runner=_dummy, executor_factory=SerialExecutor)
    assert not (out / G.SEEDS_DIR).exists() or not any((out / G.SEEDS_DIR).iterdir())      # どの seed も始めていない
    # 出力先に範囲の外の seed（穴埋め）があれば始めない
    (G.seed_dir(out, 19300)).mkdir(parents=True)
    (G.seed_dir(out, 19300) / G.START).write_text("{}", encoding="utf-8")
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
    path = Path(os.environ["ANIMA_0026_TIMING_DIR"]) / f"{seed}.json"
    path.write_text(json.dumps({"seed": seed, "pid": os.getpid(), "t0": t0, "t1": t1}), encoding="utf-8")
    return {"seed": seed}


@pytest.mark.skipif(__import__("multiprocessing").get_start_method(allow_none=False) != "fork",
                    reason="テスト関数を子プロセスへ渡すのに fork が要る（本番の run.py は既定の runner を使う）")
def test_real_processes_never_exceed_two_at_once(repo, tmp_path, monkeypatch) -> None:
    timing = tmp_path / "timing"
    timing.mkdir()
    monkeypatch.setenv("ANIMA_0026_TIMING_DIR", str(timing))
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



# ---- 7. 解析：20 個体の完全性・invalid なら判定しない・一度だけ（README §5・§7・§9）---------------------------------------

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
    """判定の量・現象に関する数値（T の値を含む）の鍵。invalid・smoke の report には出ない。"""
    text = json.dumps(report)
    return {k for k in ('"L"', '"L_B"', '"h_weights"', '"h_units"', '"outside"', '"per_seed"', '"silence_counts"',
                        '"censor_counts"', '"swap_time"', '"natural_outside"', '"no_swap_time_individuals"')
            if k in text}


def test_complete_valid_records_give_two_judgments(full_folder, tmp_path) -> None:
    out = _copy(full_folder, tmp_path)
    report = A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
    assert report["records"]["state"] == "complete" and report["valid"] and report["invalid_seeds"] == []
    assert report["analysis_commit"] == report["records"]["measurement_commit"] == _git(full_folder[0], "rev-parse", "HEAD")
    j = report["judgment"]
    assert j["n"] == 20 and len(report["per_seed"]) == 20
    for c in W.BLOCK_NAMES:
        assert j[f"holds_{c}"] == (j[f"h_{c}"] >= 6) and 0 <= j[f"h_{c}"] <= 20
    assert j["scope"] == PROTOCOL["judgment"]["scope"] and "h" not in j
    for v in report["per_seed"].values():
        assert set(v["bodies"]) == {"natural", "weights", "units"}
        assert tuple(v["bodies"]["natural"]) == W.BODIES and all(tuple(v["bodies"][c]) == W.DONORS for c in W.BLOCK_NAMES)
        sc = v["individual"]["silence_counts"]
        assert set(sc) == {"natural", "weights", "units"} and 0 <= sc["natural"]["B"] <= 21
    assert json.loads((out / A.REPORT).read_text())["judgment"] == j
    with pytest.raises(ERR, match="既にある"):                     # 集計は一度だけ
        A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
    events = [json.loads(x)["event"] for x in (out / A.LOG).read_text().splitlines()]
    assert events == ["started", "completed"]


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

    def tamper(run):
        run["controls"]["null_swap"]["state_end"]["units"]["s1"][0] += 1e-15
    _rewrite_raw(out, bad, tamper)
    report = A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
    assert report["records"]["state"] == "complete" and not report["valid"]
    assert report["invalid_seeds"] == [bad] and report["judgment"] is None
    assert set(report["checks"][str(bad)]) == {"null_swap_identity"}
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
        run["plan"]["window"] = 16
    _rewrite_raw(out, SYN[2], other_plan)
    report = A.analyze(out, "synthetic", SMALL, SYN, repo=full_folder[0])
    assert report["invalid_seeds"] == [SYN[2]] and "revalidate_from_raw" in report["checks"][str(SYN[2])]
    assert report["judgment"] is None


def test_smoke_analysis_never_computes_quantities_nor_shows_t(full_folder, tmp_path, monkeypatch) -> None:
    """smoke（操作の確認だけ）：判定の量を計算する関数は一度も呼ばれず、report に量も T の値もない。
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
    for name in ("body_quantities", "quantities_for_seed", "individual", "family", "judgment", "silence_counts"):
        monkeypatch.setattr(A, name, boom)
    monkeypatch.setattr(A, "expected_seeds", lambda mode: list(SYN))
    monkeypatch.setattr(A.W, "plan_from", lambda protocol: SMALL)
    report = A.analyze(out, "smoke", repo=full_folder[0])
    assert report["valid"] and report["judgment"] is None and report["censor_arithmetic"] == "evaluated"
    assert _forbidden_keys(report) == set()


def test_report_destination_isolation(tmp_path, monkeypatch) -> None:
    root = tmp_path / "data" / "experiments"
    own = root / "0026"
    own.mkdir(parents=True)
    monkeypatch.setattr(A, "DATA_ROOT", root)
    monkeypatch.setattr(A, "OWN_DIR", own)
    assert A.report_destination(own, "formal") == own.resolve() / A.REPORT
    for folder, mode in ((root / "0025", "formal"), (tmp_path / "x", "formal"), (own, "smoke"), (root / "0025", "smoke"),
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
    for args in (("formal", SMALL, SYN), ("smoke", SMALL, None), ("synthetic", None, None), ("synthetic", SMALL, [19001]),
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
