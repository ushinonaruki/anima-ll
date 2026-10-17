"""実験 0024 の道具の契約テスト（確定した事前登録 v0.2 の README §1〜§9、protocol.yaml、neuroarchitecture-v1.yaml）。

本番の seed（17001〜17020）・smoke の seed（17101〜17106）は使わない（実行もしない）。合成の契約テスト専用の範囲
（17201〜17299）だけを使う。合成の個体は、本番と同じ道具（world.measure_seed）・同じ式で、値だけを小さくした Plan
（SMALL：試行 3、試し 5 回、T_w ＝ 15）で実物の runtime を通して作る。結果を見て Plan・seed を選んでいない
（Plan の値は 0023 の契約テストと同じ。seed は範囲の最初から順に使う）。

使った合成の seed（PR に開示）：
- 17201〜17220：SMALL の Plan で、V1 の設計図・実物の runtime を通した 20 個体（確認の再検証・改ざんの検出・合成の集計の通し）
- 17221〜17240：一度限りの実行の契約（dummy の計算。runtime を使わない）
- 17241〜17250：並列数の契約（実際のプロセス。dummy の計算）
- 17251：V1 の確認の検出力（**C0 の設計図**（0014〜0023 の設計図）で作った 1 個体を、V1 の記録として確かめる）
"""

import copy
import functools
import gzip
import importlib.util
import json
import math
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
EXP = ROOT / "experiments" / "0024_learning_free_order_readout"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))
PREREGISTRATION_MERGE = "6d8dd310a8a26ed80db6c0f381a44241ccae22d9"   # PR #107 のマージ（README・protocol・V1 の設計図の確定）
C0_MANIFEST = "experiments/0012_passive_world/neuroarchitecture.yaml"  # V1 の元の設計図（検出力の確認にだけ使う）
SYN = list(range(17201, 17221))
GUARD_SEEDS = list(range(17221, 17241))
POOL_SEEDS = list(range(17241, 17251))
C0_SEED = 17251
TOOLS = ("world.py", "run.py", "analyze.py", "alignment.py", "guard.py")
V1_CHECKS = {"no_plastic_connection_state", "fixed_transmission_weights"}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


W = _load("world_0024_test", EXP / "world.py")
G = _load("guard_0024_test", EXP / "guard.py")
A = _load("analyze_0024_test", EXP / "analyze.py")
R = _load("run_0024_test", EXP / "run.py")
sys.modules[R.__name__] = R          # 実際のプロセスへ compute_and_write を渡すため（本番では run.py が __main__）
ALIGN = _load("alignment_0024_test", EXP / "alignment.py")
SMALL = W.make_plan(PROTOCOL, 3, 5, 15)
UNITS = tuple(PROTOCOL["brain"]["sensory_units"])
RECEPTORS = dict(PROTOCOL["brain"]["receptors"])
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
    """run.py が書くのと同じ形の生の記録（JSON を通して、保存したものと同じ値の型にする）。設計図は V1（protocol のもの）。"""
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
    """protocol.yaml と V1 の設計図は事前登録の確定（PR #107 のマージ）からバイト単位で変わっていない。README は確定した
    §0〜§14 がそのまま先頭に残っている（結果は後ろの節に追記する：README §14 の 4）。"""
    rel = f"experiments/{EXP.name}"
    for name in ("protocol.yaml", "neuroarchitecture-v1.yaml"):
        assert (EXP / name).read_bytes() == _git_show(PREREGISTRATION_MERGE, f"{rel}/{name}"), name
    assert (EXP / "README.md").read_bytes().startswith(_git_show(PREREGISTRATION_MERGE, f"{rel}/README.md"))


def test_runtime_core_and_other_experiments_are_unchanged_from_main() -> None:
    """0024 の道具を変える branch では、本体（src/）・設計（config/）・ほかの実験・0024 の事前登録の文書を同時に変えない
    （main との差分）。0024 の道具を変えない branch（後の PR）では確かめない（この PR の範囲の確認なので、後の作業を止めない）。"""
    try:
        base = subprocess.run(["git", "-C", str(ROOT), "merge-base", "HEAD", "origin/main"], capture_output=True,
                              text=True, check=True).stdout.strip()
        diff = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", base, "--", "src", "config", "experiments"],
                              capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git の履歴がない環境")
    tools = {f"experiments/{EXP.name}/{n}" for n in TOOLS}
    if not set(diff) & tools:
        pytest.skip("この branch は 0024 の道具を変えていない")
    assert set(diff) <= tools, sorted(set(diff) - tools)


FORBIDDEN = [r'"00(0\d|1\d|2[0-3])"', r"'00(0\d|1\d|2[0-3])'", r"data/experiments/00(0\d|1\d|2[0-3])",
             r"00(0\d|1\d|2[0-3])-shuffle", r"experiments/00(1[3-9]|2[0-3])_",
             r"experiments/0012_passive_world/(?!neuroarchitecture\.yaml)",
             r"(world|guard|run|analyze|alignment)_00(0\d|1\d|2[0-3])"]
SEED_NUMBERS = r"\b1[3456][0-2]\d\d\b"     # 0020〜0023 の seed の範囲（13001〜16299）の数


def _code(name: str) -> str:
    """道具のコード（説明の文字列・コメントは除く。alignment.py の使用済みの seed の一覧 SEEN は重なりの確認の記録なので除く）。"""
    src = (EXP / name).read_text(encoding="utf-8")
    src = re.sub(r"SEEN = \(.*?\)\)\)\n", "", src, flags=re.DOTALL)
    src = re.sub(r'""".*?"""', "", src, flags=re.DOTALL)
    return "\n".join(line.split("#")[0] for line in src.splitlines())


def test_tools_hold_no_earlier_experiment_references() -> None:
    """道具は、ほかの実験の ID・出力先・乱数の流れの名前・道具（world.py など）を参照しない。0023 の道具も読み込まない。
    0012 の設計図は、alignment.py が V1 の設計図との照合のためだけに YAML として読む（protocol の brain.derived_from）。"""
    for name in TOOLS:
        code = _code(name)
        for pat in FORBIDDEN:
            assert not re.search(pat, code), (name, pat)
        assert "_load(" not in code or all("experiments/" not in line for line in code.splitlines() if "_load(" in line), name
        assert not re.search(SEED_NUMBERS, code), (name, "0020〜0023 の seed の範囲の数")
    code = {n: _code(n) for n in TOOLS}
    assert all("0012_passive_world" not in c for n, c in code.items() if n != "alignment.py")


def test_the_reference_scan_detects_leftovers() -> None:
    for leftover in ('EXPERIMENT = "0023"', 'OUT = "data/experiments/0023"', 'RNG = "0023-shuffle-{i}:{seed}"',
                     '_load("w", ROOT / "experiments/0023_natural_order_readout/world.py")',
                     '"experiments/0012_passive_world/world.py"', "world_0023_for_x", "guard_0023"):
        assert any(re.search(p, leftover) for p in FORBIDDEN), leftover
    for leftover in ("SEEDS = range(16001, 16021)", "SYN = range(16201, 16251)", "seed = 15001"):
        assert re.search(SEED_NUMBERS, leftover), leftover
    src = (EXP / "alignment.py").read_text(encoding="utf-8")
    assert "range(16001" in src and "range(16001" not in _code("alignment.py") and {16001, 16299, 15001} <= ALIGN.SEEN


def test_tools_read_identity_from_this_protocol() -> None:
    ex = PROTOCOL["execution"]
    assert R.EXPERIMENT == A.EXPERIMENT == W.EXPERIMENT == PROTOCOL["experiment"] == ex["experiment_id"] == "0024"
    assert str(R.OUT_DIR) == str(A.DEFAULT_DIR) == ex["output_dir"]
    assert str(R.PROTOCOL_PATH) == str(A.PROTOCOL_PATH) == str(W.PROTOCOL_PATH) == ex["protocol_path"]
    assert W.RNG_SHUFFLE == PROTOCOL["conditions"]["shuffles"]["rng"] == "0024-shuffle-{i}:{seed}"
    assert PROTOCOL["brain"]["manifest"] == f"experiments/{EXP.name}/neuroarchitecture-v1.yaml"
    for mode, key in (("formal", "seeds"), ("smoke", "smoke_seeds"), ("synthetic", "synthetic_seeds")):
        assert list(R.allowed_seeds(mode)) == A.expected_seeds(mode) == list(
            range(PROTOCOL[key]["first"], PROTOCOL[key]["last"] + 1))


# ---- 2. V1 の設計図（README §1.1）------------------------------------------------------------------------------

def test_v1_manifest_text_differs_from_c0_only_in_the_six_plastic_flags() -> None:
    """ファイルとしては冒頭の注釈が違う。本文（version: 3 から後）は、s のあいだの 6 行の `, plastic: true` だけが違う。"""
    def body(p: Path) -> list[str]:
        lines = p.read_text(encoding="utf-8").splitlines()
        return lines[next(i for i, x in enumerate(lines) if x.startswith("version: 3")):]
    v1, c0 = body(EXP / "neuroarchitecture-v1.yaml"), body(ROOT / C0_MANIFEST)
    assert len(v1) == len(c0)
    changed = [(a, b) for a, b in zip(c0, v1) if a != b]
    assert len(changed) == 6 and all(a.replace(", plastic: true", "") == b for a, b in changed)
    assert all(re.match(r"\s+- \{ from: s[123]\.main, to: s[123], weight: 0\.005 \}$", b) for _, b in changed)


def test_the_v1_connection_store_exports_nothing_and_never_changes_weights() -> None:
    """Core の接続の状態（ConnectionStore）は、V1 の設計図では書き出すものがなく（{}）、発火を与えても重みが変わらない。"""
    from anima_ll.adapter.config.yaml_config_source import parse_neuroarchitecture
    from anima_ll.neuroarchitecture.connections import ConnectionStore
    store = ConnectionStore(parse_neuroarchitecture(W.manifest_raw(PROTOCOL)))
    before = dict(store.weights())
    rnd = random.Random(f"0024-contract-store:{SYN[0]}")
    for _ in range(500):
        store.apply_activity([u for u in UNITS if rnd.random() < 0.5], 1.0)
    assert store.export_state() == {}
    assert dict(store.weights()) == before
    assert {k: v for k, v in before.items() if k[0] in UNITS} == {
        (i, "main", j): PROTOCOL["brain"]["fixed_weights"]["s_to_s"] for i in UNITS for j in UNITS if i != j}
    c0 = ConnectionStore(parse_neuroarchitecture(yaml.safe_load((ROOT / C0_MANIFEST).read_text(encoding="utf-8"))))
    assert len(c0.export_state()) == 6                               # 対照：C0 では 6 本を書き出す


def _alignment_problems(tmp_path: Path, edit_manifest=None, edit_protocol=None) -> str:
    """V1 の設計図・protocol を写しの上で変え、alignment.check が止めることと、その理由の文を返す。"""
    protocol = copy.deepcopy(PROTOCOL)
    if edit_manifest is not None:
        text = edit_manifest((EXP / "neuroarchitecture-v1.yaml").read_text(encoding="utf-8"))
        path = tmp_path / "neuroarchitecture-v1.yaml"
        path.write_text(text, encoding="utf-8")
        protocol["brain"]["manifest"] = str(path)
    if edit_protocol is not None:
        edit_protocol(protocol)
    with pytest.raises(SystemExit) as e:
        ALIGN.check(protocol)
    return str(e.value)


def test_alignment_refuses_a_manifest_that_is_not_v1(tmp_path) -> None:
    msg = _alignment_problems(tmp_path, lambda t: t.replace("{ from: s2.main, to: s3, weight: 0.005 }",
                                                           "{ from: s2.main, to: s3, weight: 0.005, plastic: true }"))
    assert "可塑性の対象の接続がある" in msg and "plastic: true だけを除いたものと違う" in msg
    msg = _alignment_problems(tmp_path, lambda t: t.replace("{ from: s3.main, to: s1, weight: 0.005 }",
                                                           "{ from: s3.main, to: s1, weight: 0.0051 }"))
    assert "plastic: true だけを除いたものと違う" in msg and "brain.fixed_weights.s_to_s ではない" in msg
    msg = _alignment_problems(tmp_path, lambda t: t.replace("decay: 0.85", "decay: 0.86"))
    assert "plastic: true だけを除いたものと違う" in msg and "minimal-v3 と違う" in msg
    assert "このフォルダの V1 ではない" in msg                         # 写しを指した protocol は、そもそも通らない


def test_alignment_refuses_protocol_drift_in_the_v1_items(tmp_path) -> None:
    cases = {
        "固定した伝達の重み": lambda p: p["brain"]["fixed_weights"].update(s_to_s=0.006),
        "操作の確認の項目": lambda p: p["checks"]["exact"].append("no_clipping"),
        "記録の項目": lambda p: p["records"].update(connections_field_in_V1="omitted"),
        "主・補助の量の定義": lambda p: p["quantities"]["auxiliary"]["per_individual"].pop("silence_counts"),
        "判定の決まり": lambda p: p["judgment"].update(scope="V1_and_C0"),
        "試しの手順": lambda p: p["probe"]["A_copy"].update(plasticity=True),
    }
    for what, edit in cases.items():
        assert what in _alignment_problems(tmp_path, edit_protocol=edit), what


# ---- 3. Plan と刺激（README §2・§3）-------------------------------------------------------------------------------

def test_plan_from_protocol_is_the_registered_timeline() -> None:
    p = W.plan_from(PROTOCOL)
    assert (p.trials, p.experience_end, p.probes[0], p.probes[-1], len(p.probes), p.window, p.body_end, p.states_from) \
        == (200, 12000, 12001, 12300, 300, 300, 12601, 11999)
    assert list(p.probes) == list(range(12001, 12301))
    assert W.plan_of(p.as_dict()) == p
    assert (SMALL.experience_end, SMALL.probes, SMALL.body_end) == (180, (181, 182, 183, 184, 185), 201)


def test_schedules_follow_the_protocol() -> None:
    plan, seed = W.plan_from(PROTOCOL), SYN[0]
    o, m = W.ordered_labels(PROTOCOL, plan), W.mirrored_labels(PROTOCOL, plan)
    assert len(o) == 600 and [x for _, x in o].count("A") == [x for _, x in o].count("B") == 200
    assert o[:3] == [(1, "A"), (3, "B"), (31, "C")] and m[:3] == [(1, "A"), (3, "C"), (31, "B")]
    assert o[-3:] == [(11941, "A"), (11943, "B"), (11971, "C")]
    seen = set()
    for i in range(1, 20):
        s = W.labels_of(PROTOCOL, plan, seed, f"S{i}")
        labels = [x for _, x in o]
        random.Random(f"0024-shuffle-{i}:{seed}").shuffle(labels)
        assert s == [(t, x) for (t, _), x in zip(o, labels)]
        assert [t for t, _ in s] == [t for t, _ in o] and sorted(x for _, x in s) == sorted(x for _, x in o)
        seen.add(tuple(x for _, x in s))
    assert len(seen) == 19                                    # 19 本は互いに違う流れ
    assert W.BODIES == ("O", "M") + tuple(f"S{i}" for i in range(1, 20))


def test_roles_cycle_through_the_six_orders() -> None:
    orders = {tuple(W.role_receptors(PROTOCOL, s).values()) for s in SYN[:6]}
    assert len(orders) == 6
    assert W.role_receptors(PROTOCOL, SYN[0]) == dict(zip("ABC", PROTOCOL["stimulus"]["role_orders"][(SYN[0] - 1) % 6]))


# ---- 4. 実物の runtime を通した合成の個体での操作の確認（README §7）---------------------------------------------------

def test_all_checks_pass_on_a_real_runtime_individual(syn) -> None:
    assert _checks(syn) == {}
    assert set(A.check_seed(syn, "synthetic", SYN[0], SMALL)) == (
        set(PROTOCOL["checks"]["exact"]) - {"censor_arithmetic_recomputed"}) | {"revalidate_from_raw"}
    table, problems = A.probe_table(syn["run"], SYN[0], SMALL)
    assert problems == [] and set(table) == set(W.BODIES) and all(len(r) == 5 for r in table.values())


def test_raw_holds_the_preregistered_items(syn) -> None:
    run = syn["run"]
    o = run["bodies"]["O"]
    assert {"birth", "labels", "spikes", "states", "probes", "empty_side", "before_divergence", "rng"} <= set(o)
    assert o["states_from"] == SMALL.experience_end - 1 and len(o["states"]) == SMALL.body_end - SMALL.states_from + 1
    c = o["probes"][0]
    assert set(c["states"]) == {"t0-1", "t0", "t0+1", "end"}
    assert [e["t0"] for e in o["empty_side"]] == [SMALL.probes[0], SMALL.probes[-1]]
    assert {"state_experience_end", "state_end", "spikes", "birth"} <= set(run["O_twin"])
    assert "probes" not in run["O_twin"]


def test_every_recorded_full_state_has_the_five_fields_and_empty_connections(syn) -> None:
    """README §8：全状態の欄は 0023 と同じ 5 つで、V1 では connections を省かず、中身は常に空の辞書。"""
    states = list(A.recorded_states(syn["run"]))
    per_body = 1 + (SMALL.body_end - SMALL.states_from + 1) + 4 * len(SMALL.probes) + 2 * (SMALL.window + 3)
    assert len(states) >= 21 * per_body + 4
    for where, st in states:
        assert list(st) == list(PROTOCOL["records"]["full_state_fields"]) == list(W.FULL_STATE_FIELDS), where
        assert st["connections"] == {} and isinstance(st["connections"], dict), where
        assert all(len(v) == 4 for v in st["units"].values()) and set(st["units"]) == set(UNITS), where


def test_recorded_drives_carry_the_fixed_weights(syn) -> None:
    """伝達の重みは駆動にだけ現れる。記録した Unit → Unit の駆動はどれも 0.005 ちょうど、Receptor → s は 1.0 ちょうど。
    確認が空振りでないこと（どちらの駆動も記録の中にあること）も確かめる。"""
    unit_drives, receptor_drives = [], []
    for _, st in A.recorded_states(syn["run"]):
        for src, dst, w, _ in st["drives"]:
            (unit_drives if src in UNITS else receptor_drives).append((src, dst, w))
    assert unit_drives and receptor_drives
    assert {w for _, _, w in unit_drives} == {PROTOCOL["brain"]["fixed_weights"]["s_to_s"]} == {0.005}
    assert {(s, d) for s, d, _ in unit_drives} <= {(i, j) for i in UNITS for j in UNITS if i != j}
    assert {w for _, _, w in receptor_drives} == {1.0} and all(RECEPTORS[s] == d for s, d, _ in receptor_drives)


def test_probe_copy_equals_body_through_t0_plus_1_except_the_input_drive(syn) -> None:
    run = syn["run"]
    u = run["roles"]["units"]
    a_rec = run["roles"]["receptors"]["A"]
    for b, rec in run["bodies"].items():
        for c in rec["probes"]:
            t0 = c["t0"]
            body = A.state_at(rec, t0)
            assert c["states"]["t0-1"] == A.state_at(rec, t0 - 1)
            assert c["states"]["t0"]["units"] == body["units"] and c["states"]["t0"]["connections"] == body["connections"] == {}
            extra = [d for d in c["states"]["t0"]["drives"] if d not in body["drives"]]
            assert extra == [[a_rec, u["A"], 1.0, t0]]
            for role in "BC":
                assert c["states"]["t0+1"]["units"][u[role]] == A.state_at(rec, t0 + 1)["units"][u[role]]


def test_without_the_input_the_copy_is_the_body_itself() -> None:
    """空の側に本体を使う根拠（状態の十分性）：入力を入れない複製は、窓の終わりまで本体と全く同じ。"""
    log = W.ExperimentLog()
    labels = W.labels_of(PROTOCOL, SMALL, SYN[1], "O")
    app = W.build(PROTOCOL, labels, SYN[1], "O", log)
    t0 = SMALL.probes[0]
    W.advance_to(app, t0 - 1)
    c = W.a_copy(PROTOCOL, SMALL, SYN[1], app, log, t0, deliver=False)
    W.advance_to(app, t0 + 1 + SMALL.window)
    assert c["sensory"] == []
    assert c["states"]["end"] == W.full_state(app)
    assert c["spikes"] == {u: [p for p in ps if p >= t0] for u, ps in log.spikes().items() if any(p >= t0 for p in ps)}


def test_cloning_does_not_change_the_body() -> None:
    """複製を作っても本体の軌道は変わらない（O の双子の確認の根拠を、短い区間で直接確かめる）。"""
    labels = W.labels_of(PROTOCOL, SMALL, SYN[2], "O")
    a = W.run_body(PROTOCOL, SMALL, SYN[2], "O", labels, ())
    b = W.run_body(PROTOCOL, SMALL, SYN[2], "O_twin", labels, (), probes=False)
    assert a["spikes"] == b["spikes"] and A.state_at(a, SMALL.body_end) == b["state_end"]


def _tampered(syn, f) -> dict:
    data = copy.deepcopy(syn)
    f(data["run"])
    return _checks(data)


def test_v1_checks_detect_connection_state(syn) -> None:
    """no_plastic_connection_state：欄がない・中身がある・辞書でない、のどれも不成立（README §7・§8）。
    比べる相手のない全状態（A の複製の窓の終わり）を変えるので、ほかの確認は成り立ったまま。"""
    def missing(run):
        del run["bodies"]["S6"]["probes"][1]["states"]["end"]["connections"]
    assert set(_tampered(syn, missing)) == {"no_plastic_connection_state"}

    def filled(run):
        run["bodies"]["O"]["probes"][4]["states"]["end"]["connections"] = {"s1.main->s2": [0.005, 0.0, 0.0]}
    assert set(_tampered(syn, filled)) == {"no_plastic_connection_state"}

    def not_a_mapping(run):
        run["bodies"]["M"]["probes"][0]["states"]["end"]["connections"] = []
    assert set(_tampered(syn, not_a_mapping)) == {"no_plastic_connection_state"}

    def at_t0(run):                                  # t0 の終わり：本体と比べる時点でも、V1 の確認が拾う
        run["bodies"]["S8"]["probes"][2]["states"]["t0"]["connections"] = {"x": [1.0, 0.0, 0.0]}
    assert set(_tampered(syn, at_t0)) == {"no_plastic_connection_state"}

    def birth(run):
        run["O_twin"]["birth"]["connections"] = {"s2.main->s3": [0.005, 0.0, 0.0]}
    assert "no_plastic_connection_state" in _tampered(syn, birth)


def test_v1_checks_detect_transmission_weights(syn) -> None:
    """fixed_transmission_weights：Unit → Unit の重みが 0.005 から浮動小数で 1 つずれても、配線にない駆動・Receptor の重みの
    違いも不成立。"""
    u = syn["run"]["roles"]["units"]
    end = SMALL.probes[3] + 1 + SMALL.window

    def drift(run):
        st = run["bodies"]["S10"]["probes"][3]["states"]["end"]
        st["drives"] = sorted(st["drives"] + [[u["B"], u["C"], math.nextafter(0.005, 1.0), end]])
    assert set(_tampered(syn, drift)) == {"fixed_transmission_weights"}

    def self_loop(run):
        st = run["bodies"]["O"]["probes"][3]["states"]["end"]
        st["drives"] = sorted(st["drives"] + [["s1", "s1", 0.005, end]])
    assert set(_tampered(syn, self_loop)) == {"fixed_transmission_weights"}

    def receptor(run):
        st = run["bodies"]["S1"]["probes"][3]["states"]["end"]
        st["drives"] = sorted(st["drives"] + [["receptor.x1", "s1", 0.5, end]])
    assert set(_tampered(syn, receptor)) == {"fixed_transmission_weights"}

    def wrong_target(run):
        st = run["bodies"]["S2"]["probes"][3]["states"]["end"]
        st["drives"] = sorted(st["drives"] + [["receptor.x1", "s2", 1.0, end]])
    assert set(_tampered(syn, wrong_target)) == {"fixed_transmission_weights"}

    def existing(run):                                # 本体に記録した実際の Unit → Unit の駆動の重みを変える
        for rec in run["bodies"].values():
            for st in rec["states"]:
                for d in st["drives"]:
                    if d[0] in UNITS:
                        d[2] = math.nextafter(d[2], 0.0)
                        return
        raise AssertionError("Unit → Unit の駆動が記録にない")
    assert "fixed_transmission_weights" in _tampered(syn, existing)


def test_v1_checks_detect_a_c0_brain() -> None:
    """検出力：C0 の設計図（可塑性あり）で作った個体を V1 の記録として確かめると、V1 の 2 つの確認だけが成り立たない
    （ほかの確認は、可塑性の有無によらない手順の確認なので成り立つ）。"""
    c0 = copy.deepcopy(PROTOCOL)
    c0["brain"]["manifest"] = C0_MANIFEST
    data = _raw(W.measure_seed(c0, C0_SEED, SMALL))
    assert set(_checks(data, C0_SEED)) == V1_CHECKS


def test_clone_and_t0_plus_1_checks_detect_tampering(syn) -> None:
    u = syn["run"]["roles"]["units"]

    def clone_state(run):
        run["bodies"]["S3"]["probes"][2]["states"]["t0-1"]["units"][u["B"]][0] += 1e-15
    assert set(_tampered(syn, clone_state)) == {"probe_clone_equals_body_t0_minus_1"}

    def t1_state(run):
        run["bodies"]["M"]["probes"][1]["states"]["t0+1"]["units"][u["C"]][1] += 1e-15
    assert set(_tampered(syn, t1_state)) == {"identical_through_t0_plus_1"}

    def drive(run):
        run["bodies"]["O"]["probes"][0]["states"]["t0"]["drives"] = []
    assert set(_tampered(syn, drive)) == {"identical_through_t0_plus_1"}


def test_proposition_3_is_checked_on_every_probe(syn) -> None:
    run = syn["run"]
    u = run["roles"]["units"]
    for b, rec in run["bodies"].items():
        for c in rec["probes"]:
            for role in "BC":
                assert A.fired_at(c["spikes"], u[role], c["t0"] + 2) >= A.fired_at(rec["spikes"], u[role], c["t0"] + 2)

    def body_fires_alone(run):                       # 本体だけが t0 ＋ 2 に B で発火し、A の複製は発火しない
        rec = run["bodies"]["S5"]
        c = rec["probes"][3]
        t = c["t0"] + 2
        ub = u["B"]
        rec["spikes"][ub] = sorted(set(rec["spikes"].get(ub, [])) | {t})
        c["spikes"][ub] = [p for p in c["spikes"].get(ub, []) if p != t]
    assert "proposition_3" in _tampered(syn, body_fires_alone)


def test_empty_side_and_twin_checks_detect_tampering(syn) -> None:
    def empty_state(run):
        run["bodies"]["S7"]["empty_side"][1]["states"][4]["units"]["s2"][0] += 1e-15
    assert set(_tampered(syn, empty_state)) == {"empty_side_identity"}

    def empty_spike(run):
        c = run["bodies"]["O"]["empty_side"][0]
        c["spikes"]["s3"] = sorted(set(c["spikes"].get("s3", [])) ^ {c["t0"] + 5})
    assert set(_tampered(syn, empty_spike)) == {"empty_side_identity"}

    def twin(run):
        run["O_twin"]["state_end"]["units"]["s1"][0] += 1e-15
    assert set(_tampered(syn, twin)) == {"O_twin_identity"}

    def twin_spike(run):
        run["O_twin"]["spikes"]["s1"] = run["O_twin"]["spikes"]["s1"][:-1]
    assert "O_twin_identity" in _tampered(syn, twin_spike)


def test_label_and_input_checks_detect_tampering(syn) -> None:
    def rng(run):
        run["bodies"]["S2"]["rng"] = f"0024-shuffle-2:{SYN[1]}"
    assert set(_tampered(syn, rng)) == {"stimulus_labels"}

    def swap(run):
        run["bodies"]["M"]["labels"] = copy.deepcopy(run["bodies"]["O"]["labels"])
    assert "stimulus_labels" in _tampered(syn, swap)

    def late_input(run):
        run["bodies"]["S9"]["sensory"].append([SMALL.experience_end + 3, "receptor.x1"])
    assert "input_free_after_experience" in _tampered(syn, late_input)

    def double_probe(run):
        c = run["bodies"]["O"]["probes"][0]
        c["sensory"] = c["sensory"] + [[c["t0"], "receptor.x2"]]
    assert set(_tampered(syn, double_probe)) == {"input_free_after_experience"}

    def empty_input(run):
        run["bodies"]["O"]["empty_side"][0]["sensory"] = [[SMALL.probes[0], "receptor.x1"]]
    assert set(_tampered(syn, empty_input)) == {"input_free_after_experience"}


def test_divergence_check_detects_tampering(syn) -> None:
    def birth(run):
        run["bodies"]["S4"]["birth"]["units"]["s1"][0] += 1e-15
    assert "identical_before_label_divergence" in _tampered(syn, birth)

    def before(run):
        rec = run["bodies"]["M"]
        k = next(iter(rec["before_divergence"]))
        rec["before_divergence"][k]["units"]["s2"][1] += 1e-15
    assert set(_tampered(syn, before)) == {"identical_before_label_divergence"}


def test_structure_checks_detect_wrong_plan_seed_manifest_and_shape(syn) -> None:
    data = copy.deepcopy(syn)
    assert set(_checks(data, SYN[1])) == {"revalidate_from_raw"}               # フォルダの seed と違う
    bad = A.check_seed(syn, "synthetic", SYN[0], W.make_plan(PROTOCOL, 3, 5, 16))
    assert bad["revalidate_from_raw"]
    data["meta"]["manifest"] = yaml.safe_load((ROOT / C0_MANIFEST).read_text(encoding="utf-8"))   # raw の設計図が V1 でない
    assert set(_checks(data)) == {"revalidate_from_raw"}
    data = copy.deepcopy(syn)
    data["run"]["bodies"].pop("S19")
    assert set(_checks(data)) == {"revalidate_from_raw"}
    data = copy.deepcopy(syn)
    data["run"]["bodies"]["O"]["spikes"]["s1"].reverse()
    assert "revalidate_from_raw" in _checks(data)
    data = copy.deepcopy(syn)
    del data["run"]["bodies"]["O"]["probes"][0]["states"]["t0+1"]
    assert "revalidate_from_raw" in _checks(data)


# ---- 5. 打ち切りの算術と判定の量（README §3・§4・§5・§6）------------------------------------------------------------------

def test_censor_arithmetic_and_ell() -> None:
    """両側打ち切りで ℓ ＝ 0、片側だけ打ち切りなら打ち切りの値との差、ℓ は −T_w〜＋T_w。"""
    plan = W.make_plan(PROTOCOL, 3, 2, 10)
    t0a, t0b = plan.probes
    ca, cb = t0a + 12, t0b + 12
    rows = [(ca, ca, t0a + 2, ca, 0, 0, 1, 0, 0, 0, 1, 0),            # B 両側打ち切り（ℓ_B ＝ 0）、C は A の側だけ発火
            (t0b + 5, t0b + 11, cb, t0b + 2, 1, 1, 0, 1, 0, 0, 0, 1)]
    q = A.body_quantities(rows, plan)
    lB = [0, 6]
    lC = [ca - (t0a + 2), (t0b + 2) - cb]
    assert all(-plan.window <= x <= plan.window for x in lB + lC)
    assert q["L"] == Fraction(sum(b - c for b, c in zip(lB, lC)), 2)
    assert (q["L_B"], q["L_C"]) == (Fraction(sum(lB), 2), Fraction(sum(lC), 2))
    assert q["censor_counts"] == {"B_A": 1, "B_null": 1, "C_A": 1, "C_null": 1}
    assert q["R1_prime"] == Fraction((0 - 0) - (1 - 0) + (0 - 0) - (0 - 1), 2)
    assert q["R1"] == Fraction((0 - 1) + (0 - 0), 2)
    assert q["R3"] == Fraction(((0 - 0) - (1 - 0)) + ((1 - 1) - (0 - 1)), 2)


def test_probe_table_routes_agree_and_detect_inconsistent_spikes(syn) -> None:
    table, problems = A.probe_table(syn["run"], SYN[0], SMALL)
    assert problems == []
    for b, rows in table.items():
        for t0, r in zip(SMALL.probes, rows):
            c = t0 + 2 + SMALL.window
            for n, N in zip(r[:4], r[4:8]):
                assert (n == c) == (N == 0) and (t0 + 2 <= n <= t0 + 1 + SMALL.window or n == c)
    data = copy.deepcopy(syn)
    c = data["run"]["bodies"]["O"]["probes"][0]
    ub = data["run"]["roles"]["units"]["B"]
    c["spikes"][ub] = [c["t0"] + 9, c["t0"] + 4]                    # 並んでいない列：2 通りの計算が食い違う
    _, problems = A.probe_table(data["run"], SYN[0], SMALL)
    assert problems


def _per(o, s, m=Fraction(0), aux=Fraction(0), censor=None) -> dict:
    censor = censor or {}
    zero = {"B_A": 0, "B_null": 0, "C_A": 0, "C_null": 0}

    def q(name, L):
        return {"L": L, "R1_prime": aux, "R1": aux, "R3": aux, "censor_counts": censor.get(name, zero)}
    per = {"O": q("O", o), "M": q("M", m)}
    for i, x in enumerate(s, 1):
        per[f"S{i}"] = q(f"S{i}", x)
    return per


def test_frozen_individual_counts_as_not_outside() -> None:
    ind = A.individual(_per(Fraction(0), [Fraction(0)] * 19), 300)
    assert ind["frozen"] and not ind["outside"] and ind["direction"] is None
    assert ind["rank_of_L_O_among_20"] == {"shuffles_below": 0, "shuffles_equal": 19, "shuffles_above": 0}


def test_ties_with_the_extremes_are_not_outside() -> None:
    s = [Fraction(k, 300) for k in range(-9, 10)]
    assert not A.individual(_per(Fraction(9, 300), s), 300)["outside"]              # 最大と等しい
    assert not A.individual(_per(Fraction(-9, 300), s), 300)["outside"]             # 最小と等しい
    up = A.individual(_per(Fraction(10, 300), s), 300)
    down = A.individual(_per(Fraction(-10, 300), s), 300)
    assert up["outside"] and up["direction"] == "above_max" and down["outside"] and down["direction"] == "below_min"
    assert not A.outside(Fraction(1, 3), [Fraction(1, 3)] * 19)


def test_silence_counts_count_bodies_silent_on_both_sides_on_every_probe() -> None:
    """README §6・protocol の silence_counts：両方の側で、すべての試しで打ち切りになった本体だけを数える
    （片側だけ・1 回でも発火した本体は数えない）。補助の記録で、外にあるか・凍結の判定を変えない。"""
    P = 300
    censor = {"O": {"B_A": P, "B_null": P, "C_A": 0, "C_null": 0},           # B は沈黙、C は発火
              "M": {"B_A": P, "B_null": P, "C_A": P, "C_null": P},           # 両方とも沈黙
              "S1": {"B_A": P, "B_null": P - 1, "C_A": P, "C_null": P},      # B は空の側で 1 回発火（数えない）、C は沈黙
              "S2": {"B_A": P - 1, "B_null": P, "C_A": 3, "C_null": P},      # どちらも数えない
              "S3": {"B_A": P, "B_null": P, "C_A": P, "C_null": P}}
    s = [Fraction(k, 300) for k in range(19)]
    ind = A.individual(_per(Fraction(-1, 300), s, censor=censor), P)
    assert ind["silence_counts"] == {"B": 3, "C": 3}
    assert ind["outside"] and ind["direction"] == "below_min"               # 沈黙の多さは外にあるかを変えない
    assert A.silence_counts(_per(Fraction(0), [Fraction(0)] * 19, censor=censor), P + 1) == {"B": 0, "C": 0}


def test_threshold_is_the_smallest_h_at_level_005() -> None:
    p = Fraction(1, 10)
    assert A.binom_tail(20, p, 5) <= Fraction(1, 20) < A.binom_tail(20, p, 4)
    assert abs(float(A.binom_tail(20, p, 5)) - 0.04317) < 5e-6 and abs(float(A.binom_tail(20, p, 4)) - 0.13295) < 5e-6
    ind = {"outside": True, "direction": "above_max", "frozen": False,
           "mirror": {"M_outside_shuffles": False}, "aux_outside": {"R1_prime": False, "R1": False, "R3": False}}
    no = ind | {"outside": False, "direction": None}
    for h, holds in ((4, False), (5, True)):
        per = {str(s): {"individual": ind if k < h else no} for k, s in enumerate(SYN)}
        j = A.judgment(per)
        assert (j["h"], j["n"], j["holds"], j["scope"]) == (h, 20, holds, "V1_only")


def test_clopper_pearson_reference_values() -> None:
    lo, hi = A.clopper_pearson(5, 20)
    assert abs(lo - 0.0866) < 1e-4 and abs(hi - 0.4910) < 1e-4
    assert A.clopper_pearson(0, 20)[0] == 0.0 and abs(A.clopper_pearson(0, 20)[1] - 0.1684) < 1e-4
    assert A.clopper_pearson(20, 20)[1] == 1.0 and abs(A.clopper_pearson(20, 20)[0] - 0.8316) < 1e-4


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
        raw = json.loads(gzip.decompress((G.seed_dir(out, s) / G.RAW).read_bytes()))
        assert raw["run"]["seed"] == s and raw["meta"]["manifest"] == W.manifest_raw(PROTOCOL)   # 設計図は V1
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
                          "started_at": "t", "experiment": "0024", "kind": PROTOCOL["kind"], "mode": "synthetic"})
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
    for mode, seeds in (("synthetic", [17001]), ("synthetic", [17300]), ("synthetic", [17101]), ("smoke", [17201]),
                        ("formal", [17021]), ("formal", [16001]), ("synthetic", [GUARD_SEEDS[0], GUARD_SEEDS[0]]),
                        ("synthetic", [])):
        with pytest.raises(ERR):
            R.execute(mode, seeds, out, repo, head, runner=_dummy, executor_factory=SerialExecutor)
    with pytest.raises(ERR, match="measurement-commit"):
        R.execute("formal", [17001], out, repo, None, runner=_dummy, executor_factory=SerialExecutor)
    with pytest.raises(ERR, match="指定した commit"):
        R.execute("formal", [17001], out, repo, "1" * 40, runner=_dummy, executor_factory=SerialExecutor)
    assert not (out / G.SEEDS_DIR).exists() or not any((out / G.SEEDS_DIR).iterdir())      # どの seed も始めていない
    # 出力先に範囲の外の seed（穴埋め）があれば始めない
    (G.seed_dir(out, 17300)).mkdir(parents=True)
    (G.seed_dir(out, 17300) / G.START).write_text("{}", encoding="utf-8")
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
    path = Path(os.environ["ANIMA_0024_TIMING_DIR"]) / f"{seed}.json"
    path.write_text(json.dumps({"seed": seed, "pid": os.getpid(), "t0": t0, "t1": t1}), encoding="utf-8")
    return {"seed": seed}


@pytest.mark.skipif(__import__("multiprocessing").get_start_method(allow_none=False) != "fork",
                    reason="テスト関数を子プロセスへ渡すのに fork が要る（本番の run.py は既定の runner を使う）")
def test_real_processes_never_exceed_two_at_once(repo, tmp_path, monkeypatch) -> None:
    timing = tmp_path / "timing"
    timing.mkdir()
    monkeypatch.setenv("ANIMA_0024_TIMING_DIR", str(timing))
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


# ---- 7. 解析：20 個体の完全性・invalid なら判定しない・一度だけ（README §5〜§7・§9）---------------------------------------

@pytest.fixture(scope="module")
def full_folder(tmp_path_factory) -> tuple[Path, Path]:
    """合成の 20 個体（SMALL の Plan で、V1 の設計図・実物の runtime を通す）を、本番と同じ execute の手順で保存したフォルダ。"""
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
    text = json.dumps(report)
    return {k for k in ('"L"', '"L_B"', '"h"', '"outside"', '"per_seed"', '"R3"', '"silence_counts"', '"censor_counts"')
            if k in text}


def test_complete_valid_records_give_one_judgment(full_folder, tmp_path) -> None:
    out = _copy(full_folder, tmp_path)
    report = A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
    assert report["records"]["state"] == "complete" and report["valid"] and report["invalid_seeds"] == []
    assert report["analysis_commit"] == report["records"]["measurement_commit"] == _git(full_folder[0], "rev-parse", "HEAD")
    assert all(set(c) >= V1_CHECKS for c in report["checks_evaluated"].values())
    j = report["judgment"]
    assert j["n"] == 20 and j["holds"] == (j["h"] >= 5) and len(report["per_seed"]) == 20 and j["scope"] == "V1_only"
    assert all(set(v["bodies"]) == set(W.BODIES) for v in report["per_seed"].values())
    for v in report["per_seed"].values():
        sc = v["individual"]["silence_counts"]
        assert set(sc) == {"B", "C"} and all(isinstance(x, int) and 0 <= x <= 21 for x in sc.values())
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
        run["bodies"]["S11"]["probes"][2]["states"]["t0-1"]["units"]["s1"][0] += 1e-15
    _rewrite_raw(out, bad, tamper)
    report = A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
    assert report["records"]["state"] == "complete" and not report["valid"]
    assert report["invalid_seeds"] == [bad] and report["judgment"] is None
    assert set(report["checks"][str(bad)]) == {"probe_clone_equals_body_t0_minus_1"}
    assert report["censor_arithmetic"] == "not_evaluated"
    assert _forbidden_keys(report) == set()                                  # invalid を「外にない」に数えず、量を出さない


def test_a_non_empty_connection_state_in_one_individual_blocks_the_judgment(full_folder, tmp_path) -> None:
    """V1 の確認が 1 個体の 1 つの全状態で成り立たないだけで、実験全体が invalid（判定の量を計算も表示もしない）。"""
    out = _copy(full_folder, tmp_path)
    bad = SYN[12]

    def tamper(run):
        run["bodies"]["S17"]["probes"][4]["states"]["end"]["connections"] = {"s3.main->s1": [0.005, 0.0, 0.0]}
    _rewrite_raw(out, bad, tamper)
    report = A.publish(out, "synthetic", plan=SMALL, seeds=SYN, repo=full_folder[0])
    assert not report["valid"] and report["invalid_seeds"] == [bad] and report["judgment"] is None
    assert set(report["checks"][str(bad)]) == {"no_plastic_connection_state"}
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
        run["plan"]["window"] = 16
    _rewrite_raw(out, SYN[2], other_plan)
    report = A.analyze(out, "synthetic", SMALL, SYN, repo=full_folder[0])
    assert report["invalid_seeds"] == [SYN[2]] and "revalidate_from_raw" in report["checks"][str(SYN[2])]
    assert report["judgment"] is None


def test_smoke_analysis_never_computes_quantities(full_folder, tmp_path, monkeypatch) -> None:
    """smoke（操作の確認だけ）：判定の量・補助の量（silence_counts を含む）を計算する関数は一度も呼ばれず、report に量がない。
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
    for name in ("body_quantities", "quantities_for_seed", "individual", "judgment", "silence_counts"):
        monkeypatch.setattr(A, name, boom)
    monkeypatch.setattr(A, "expected_seeds", lambda mode: list(SYN))
    monkeypatch.setattr(A.W, "plan_from", lambda protocol: SMALL)
    report = A.analyze(out, "smoke", repo=full_folder[0])
    assert report["valid"] and report["judgment"] is None and report["censor_arithmetic"] == "evaluated"
    assert _forbidden_keys(report) == set()


def test_report_destination_isolation(tmp_path, monkeypatch) -> None:
    root = tmp_path / "data" / "experiments"
    own = root / "0024"
    own.mkdir(parents=True)
    monkeypatch.setattr(A, "DATA_ROOT", root)
    monkeypatch.setattr(A, "OWN_DIR", own)
    assert A.report_destination(own, "formal") == own.resolve() / A.REPORT
    for folder, mode in ((root / "0023", "formal"), (tmp_path / "x", "formal"), (own, "smoke"), (root / "0023", "smoke"),
                         (own, "synthetic")):
        with pytest.raises(ERR):
            A.report_destination(folder, mode)
    (own / A.REPORT).write_text("{}")
    with pytest.raises(ERR, match="既にある"):
        A.report_destination(own, "formal", resume=True)


def test_resume_only_with_identical_inputs(full_folder, tmp_path) -> None:
    out = _copy(full_folder, tmp_path)
    A._append(out, {"event": "started", "context": A.analysis_context(out, "synthetic")}, create=True)
    with pytest.raises(ERR, match="既にある"):                     # 再開の指定なしでは止まる
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


def test_an_all_censored_individual_is_frozen_and_not_outside() -> None:
    """D3：窓の中でどの Unit も発火しない（打ち切りだけの）個体でも、主の式が値を返し、凍結として「外にない」に数える。
    沈黙した本体の数は B・C とも 21。"""
    plan = W.make_plan(PROTOCOL, 3, 3, 10)
    rows = [(t0 + 2 + plan.window,) * 4 + (0,) * 8 for t0 in plan.probes]
    q = A.quantities_for_seed({b: rows for b in W.BODIES}, plan)
    assert all(v["L"]["exact"] == "0/1" for v in q["bodies"].values())
    assert q["bodies"]["O"]["censor_counts"] == {"B_A": 3, "B_null": 3, "C_A": 3, "C_null": 3}
    ind = q["individual"]
    assert ind["frozen"] and not ind["outside"] and not any(ind["aux_outside"].values())
    assert ind["silence_counts"] == {"B": 21, "C": 21}


def test_formal_and_smoke_use_only_the_protocol_plan_and_seeds(tmp_path) -> None:
    for args in (("formal", SMALL, SYN), ("smoke", SMALL, None), ("synthetic", None, None), ("synthetic", SMALL, [17001]),
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
    """解析の道具の HEAD が測定の commit と違う（後の commit）、追跡しているファイルに未 commit の変更がある、未追跡のファイルがある
    ときは、生の記録を読まず、判定の量を計算・表示せず、解析の記録も report も書かずに止まる。"""
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
