"""実験 0041 の道具の契約テスト（確定した事前登録 v0.1 の README・protocol.yaml。#189 merge `5fba79f`。README §14 の CT-41-1〜10）。

本番の seed（34001〜34200）・smoke の seed（34201〜34206）・関門の seed（31001〜31040）・0039 の seed（32001〜32399）・
0040 の seed（33001〜33399）は使わない（実行もしない）。0034〜0040 の seed・raw も、関門の記録も使わない。合成の契約テスト専用の
範囲（34301〜34399）だけを使う。合成の個体は、本番と同じ道具（measure.measure_seed）・同じ式で、区間だけを小さくした Plan
（SMALL：予定は 8 窓、E ＝ 窓 1〜4、P_E ＝ 204）か、本番の Plan で、実物の runtime を通して作る。結果を見て Plan・seed を選んでいない
（seed は範囲の最初から順に、構成の条件だけで決定的に選ぶ）。テストは操作の確認・記録の形・Runtime の順序・判定と推定の算術だけを
確かめ、合成の個体の判定と推定の量（δ・q・δ^←・ε とその符号、向きごとの数、E_B、区間、k*、構造的な 0 の札、重み、選択と結果の
刺激の数、最初に分かれた Pulse）の値を表示も判定もしない（README §9.3）。実際の軌道から求めた値は、整合の真偽だけを確かめる。

構成（README §14 の契約テストの要件）：
- k* のある個体：SMALL の B^{A1} の層 A の窓 1〜4 に、決まった窓が 1 つ以上ある最初の合成の個体
- 構造的に沈黙する源を持つ個体（SE-B6）と、構造的な 0 の個体（SE-B1。両方の源が沈黙）：本番と同じ measure_seed を通し、
  組み立ての直後（Pulse 0）に源の Unit の θ・c を出生時の範囲の角（g ＜ −E_S）に置いた合成の個体（契約テストだけ。CT-39-8 と同じ
  置き方で、AS2b の道具も Core も変えない）
- 命題 S-1・補題 L1・L2：Unit の θ・c を出生時の範囲の角に置き、世界が結果を返す合成の系（CT-39-8 と同じ形）

使った合成の seed（PR に開示）：34301〜34310（SMALL）、34321〜34326（一度限りの実行・盲検の契約。dummy の計算と SMALL）、
34390〜34392（S-1・L1・L2・SE-B6 の角の系、構造的な 0 の構成）、34399（本番の Plan で実物の runtime を通す確かめと、関門の
run_body との照合）、構成の条件で選んだ個体（34301〜34399 の最初から順。どれになったかはテストの中で決まる）。

失敗の表示に現象の値を出さない（README §9.3）：このモジュールの assert は pytest に書き換えさせない（PYTEST_DONT_REWRITE）。
失敗しても、評価した値を表示せず、行の文と AssertionError だけを出す。assert の文の後ろに付ける文は、本体・欄の名前、report・
ファイルの場所だけにし、合成の軌道から求めた値（Pulse の番号・数・重み・符号など）を入れない。
"""

import ast
import copy
import dataclasses
import functools
import gzip
import hashlib
import importlib.util
import inspect
import itertools
import json
import math
import re
import shutil
import subprocess
from concurrent.futures import Future
from fractions import Fraction
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments" / "0041_as2b_rule_weight_direction"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = _load("measure_0041_test", EXP / "measure.py")
AN = _load("analyze_0041_test", EXP / "analyze.py")
AL = _load("alignment_0041_test", EXP / "alignment.py")
AX = _load("analysis_0041_test", EXP / "analysis.py")
R = _load("run_0041_test", EXP / "run.py")
RC = _load("recheck_0041_test", EXP / "recheck.py")
GATE = _load("gate_0038_for_0041_test", ROOT / "experiments" / "0038_as2b_forward_gate" / "gate.py")
A, AS1 = M.A, M.AS1
SMALL = M.Plan(41, 41, 8, 2, 19, 2, 4)
FORMAL = M.formal_plan(PROTOCOL)
SYN = list(range(34301, 34311))
SYN_ALL = list(range(34301, 34400))
GUARD_SEEDS = list(range(34321, 34327))
CORNER_SEEDS = (34390, 34391, 34392)
FORMAL_SEED = 34399
W_MAX, W0 = PROTOCOL["brain"]["w_max"], PROTOCOL["brain"]["initial_weight_w0"]
THETA = (0.45, 0.55)                                                 # 出生時の θ の範囲（0.5 ± 10%）
DRIVE = (0.072, 0.088)                                               # 出生時の c の範囲（0.08 ± 10%）
LAMBDA = 0.85


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)


def _meta(seed: int, mode: str = "synthetic") -> dict:
    """run.py が書く meta と同じ形（protocol の写しと、その SHA-256 を含む）。"""
    return {"experiment": "0041", "kind": PROTOCOL["kind"], "mode": mode, "seed": seed, "manifest": M.manifest_raw(),
            "protocol": json.loads(json.dumps(PROTOCOL)), "protocol_sha256": AN.PROTOCOL_SHA256,
            "gate": {"sha256": AN.GATE_SHA256, "declaration": AN.GATE_DECLARATION}, "blind": mode == "smoke"}


def _raw(run: dict, mode: str = "synthetic") -> dict:
    return {"meta": _meta(run["seed"], mode), "run": run}


def _inner(system, unit_id):
    u = system.app.units.get(unit_id)
    return u._inner if isinstance(u, A.CompetitionTap) else u


def _place(system, values: dict) -> None:
    """Unit の θ・c と初期の activity（上限 θ/2）を置く（Pulse 0。契約テストだけ。CT-39-8 と同じ置き方）。values：役 → (θ, c)。"""
    roles = system.roles.as_dict()
    for role, (theta, c) in values.items():
        inner = _inner(system, roles[role])
        inner._dynamics = dataclasses.replace(inner._dynamics, threshold=theta, intrinsic_drive_per_second=c)
        inner.import_state(inner.export_state() | {"activity": theta / 2})


def _silent_values() -> tuple[float, float]:
    """g ＝ c／(1 − λ) − θ が −E_S のすぐ下になる (θ, c)（出生時の範囲の中）。"""
    theta = THETA[1]
    c = (theta - AN.E_S - 1e-9) * (1 - LAMBDA)
    assert DRIVE[0] <= c <= DRIVE[1]
    return theta, c


@functools.cache
def _measured(seed: int, plan: M.Plan, silent: tuple[str, ...] = ()) -> str:
    if not silent:
        return json.dumps(_raw(M.measure_seed(PROTOCOL, seed, plan)))
    original = M.build_body

    def build(plan_, seed_, rule_c, *, log=None):                      # 本番と同じ組み立てに、Pulse 0 で源の値を置くだけ
        s = original(plan_, seed_, rule_c, log=log)
        _place(s, dict.fromkeys(silent, _silent_values()))
        return s
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(M, "build_body", build)
        return json.dumps(_raw(M.measure_seed(PROTOCOL, seed, plan)))


def measured(seed: int, plan: M.Plan = SMALL, silent: tuple[str, ...] = ()) -> dict:
    """実物の runtime を通した合成の個体の生の記録（JSON を通した形。返すのは複製）。"""
    return json.loads(_measured(seed, plan, silent))


def failures(data: dict, seed: int, plan: M.Plan = SMALL) -> dict:
    return {k: v for k, v in AN.check_seed(data, "synthetic", seed, plan).items() if v}


def _log():
    return AS1.AS1Log(keep=M.LOG_KEEP)


@functools.cache
def decided_seed() -> int:
    """SMALL の B^{A1} の層 A の窓 1〜E に、決まった窓が 1 つ以上ある最初の合成の個体（構成の条件だけ。値は表示しない）。"""
    return next(s for s in SYN_ALL if AN.k_star(measured(s)["run"]["bodies"]["B_A1"]["layer_a"], SMALL.e_windows) is not None)


def zero_individual() -> dict:
    """構造的な 0 の個体（両方の源を構造的に沈黙させた合成の個体。SE-B1・SE-B6）。"""
    return measured(CORNER_SEEDS[0], SMALL, ("source1", "source2"))


def one_silent_individual() -> dict:
    """源 1 だけを構造的に沈黙させた合成の個体（SE-B6）。"""
    return measured(CORNER_SEEDS[0], SMALL, ("source1",))


# ---- protocol と道具の一致 ----------------------------------------------------------------------

def test_protocol_and_tools_are_aligned() -> None:
    AL.check(PROTOCOL)


def test_the_formal_plan_is_taken_from_the_gate_declaration() -> None:
    assert FORMAL == M.Plan(41, 41, 50, 2, 19, 2, 25) and FORMAL.p_e == 1065
    assert FORMAL.boundaries == [41 * (k + 1) - 1 for k in range(1, 26)] and FORMAL.boundaries[-1] == 1065
    decl, digest = M.gate_declaration(PROTOCOL)
    assert digest == PROTOCOL["inherited_gate_set"]["sha256"] == GATE.DECLARATION_SHA256
    assert FORMAL == M.plan_from_declaration(decl, 25)
    assert FORMAL.schedule().windows == tuple(GATE.declared_windows(decl))
    wrong = copy.deepcopy(PROTOCOL)
    wrong["inherited_gate_set"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="SHA-256"):
        M.formal_plan(wrong)
    for tamper in (lambda d: d["exit"].update(tie_rule="first_listed_wins"),
                   lambda d: d["world"].update(lc3="add"),
                   lambda d: d["world"].update(consequence_receptor="source_receptor"),
                   lambda d: d["world"].update(rule_c_assignment="A1_only"),
                   lambda d: d["bodies"].update(per_individual=[{"rule_c": "A1"}]),
                   lambda d: d["bodies"].update(respond=False),
                   lambda d: d["bodies"].update(plasticity="off"),
                   lambda d: d["bodies"].update(outlet=False),
                   lambda d: d["bodies"].update(interventions="freeze"),
                   lambda d: d["roles"].update(stream="other-{seed}")):
        changed = copy.deepcopy(decl)
        tamper(changed)
        with pytest.raises(ValueError):
            M.plan_from_declaration(changed, 25)
    not_taken = copy.deepcopy(decl)                                    # 本体の長さは取らない（本体は P_E で止める）
    not_taken["bodies"].update(pulses=2073)
    assert M.plan_from_declaration(not_taken, 25) == FORMAL
    other_tl = copy.deepcopy(PROTOCOL)
    other_tl["timeline"]["boundary_P_E"] = 1064
    with pytest.raises(ValueError, match="timeline"):
        M.formal_plan(other_tl)
    for e in (0, 50):
        with pytest.raises(ValueError):
            M.check_plan(dataclasses.replace(FORMAL, e_windows=e))


def test_the_boundary_has_no_open_window_and_no_reservation_by_arithmetic() -> None:
    """SE-B7 の算術（analysis.py と同じ）：窓 25 ＝ [1027, 1045]、意図 1046、結果 1047、次の手がかり 1066 ＝ P_E ＋ 1。"""
    iv = AX.intervals(AX.gate_set())
    k, a, b = FORMAL.schedule().windows[24]
    assert (k, a, b) == (25, 1027, 1045) and b + FORMAL.delay == iv["last_E_outcome_pulse"] == 1047 < FORMAL.p_e
    assert FORMAL.schedule().cues[25] == FORMAL.p_e + 1 == iv["next_cue_after_P_E"] == 1066
    assert iv["window_boundaries"] == FORMAL.boundaries and iv["pulses_per_individual"] == 3 * 1065


def test_the_run_entry_point_uses_only_the_protocol_plan() -> None:
    assert "W.measure_seed(PROTOCOL, seed)" in inspect.getsource(R.measure)
    assert "plan" not in inspect.signature(R.measure).parameters


def test_seen_seeds_include_0040_and_the_gate_and_exclude_0041() -> None:
    assert {30001, 30299, 31001, 31040, 32001, 32399, 33001, 33200, 33201, 33301, 33399, 9101} <= AL.SEEN
    assert not ({34001, 34200, 34201, 34206, 34301, 34399} & AL.SEEN)


def test_contract_tests_of_o1_are_the_tool_tests_and_this_file() -> None:
    assert AN.CONTRACT_TESTS == (*PROTOCOL["tools"]["contract_tests"], "tests/integration/test_as2b_rule_weight_direction_0041.py")
    assert R.CONTRACT_TESTS == AN.CONTRACT_TESTS and (ROOT / AN.CONTRACT_TESTS[-1]) == Path(__file__).resolve()


def test_the_analysis_quantities_and_checks_follow_the_protocol() -> None:
    q = PROTOCOL["quantities"]
    assert list(AN.QUANTITIES) == AL.QUANTITIES and all(name in q for name in AN.QUANTITIES)
    assert AN.CHECK_NAMES[1:] == tuple(PROTOCOL["operation_checks"][1:]) and PROTOCOL["operation_checks"][0] == "O1"
    assert AN.ROLES6 == AX.ROLES6 and AN.F1_TOLERANCE == 1e-12
    assert set(PROTOCOL["judgment"]["outcomes"]) == {"invalid", "not_established", "plus", "minus"}


# ---- 合成の個体が、すべての操作の確認を通る ------------------------------------------------------------

@pytest.mark.parametrize("seed", SYN)
def test_synthetic_individuals_pass_every_operation_check(seed) -> None:
    assert failures(measured(seed), seed) == {}


def test_the_formal_plan_through_the_runtime_passes_every_operation_check() -> None:
    data = measured(FORMAL_SEED, FORMAL)
    assert AN.check_seed(data, "synthetic", FORMAL_SEED, None) == {k: [] for k in AN.CHECK_NAMES}
    run = data["run"]
    assert all(len(run["bodies"][n]["layer_a"]) == 25 and run["bodies"][n]["pulse_end"] == 1065 for n in M.SYSTEMS)
    assert all(len(run["bodies"][n]["pulse_weights"]) == 1065 for n in M.BODIES)


@pytest.mark.parametrize("which", ["decided", "zero", "one_silent"])
def test_the_constructed_individuals_pass_every_operation_check(which) -> None:
    if which == "decided":
        seed = decided_seed()
        assert failures(measured(seed), seed) == {}
    else:
        data = zero_individual() if which == "zero" else one_silent_individual()
        assert failures(data, CORNER_SEEDS[0]) == {}


JUDGMENT_KEYS = {"delta", "q_1", "q_2", "q1", "q2", "delta_back", "epsilon", "sign", "signs", "k_star", "structural_zero",
                 "other_zero", "quantities", "judgment", "individuals", "auxiliary", "descriptive_controls", "estimate",
                 "interval", "counts_E", "S1", "J_B", "E_B", "first_divergence", "never_diverged", "boundaries",
                 "consequences", "weights_P_E", "weight_differences"}


def _keys(x, path=()):
    if isinstance(x, dict):
        for k, v in x.items():
            yield path, k
            if path == ("meta",) and k in ("protocol", "manifest", "gate"):
                continue
            yield from _keys(v, path + (k,))
    elif isinstance(x, list):
        for v in x:
            yield from _keys(v, path)


def test_raw_has_no_judgment_quantities() -> None:
    data = measured(SYN[0])
    assert not ({k for _, k in _keys(data)} & JUDGMENT_KEYS)
    assert set(data["run"]) == AN.RUN_KEYS


def test_failures_in_this_module_show_no_evaluated_values() -> None:
    """README §9.3：このモジュールは pytest の assert の書き換えを受けない（失敗しても評価した値を表示しない）。"""
    assert "PYTEST_DONT_REWRITE" in __doc__
    module = inspect.getmodule(test_failures_in_this_module_show_no_evaluated_values)
    tests = [f for name, f in vars(module).items() if name.startswith("test_") and inspect.isfunction(f)]
    assert len(tests) > 80
    assert not any(v.startswith("@py_assert") for f in tests for v in f.__code__.co_varnames)


# ---- CT-41-1 組み立て --------------------------------------------------------------------------------------

def test_ct41_1_every_body_is_the_gate_body_with_rule_c_and_a_responding_world() -> None:
    src = inspect.getsource(M.build_body)
    assert "A.build(seed, schedule=plan.schedule(), delay=plan.delay, rule_c=rule_c, respond=True" in src
    for c in ("A1", "A2"):
        s = M.build_body(SMALL, SYN[0], c)
        assert s.meta == {"delay": 2, "rule_c": c, "respond": True, "outlet": True, "world_cues": True}
        assert s.log.keep == AS1.AS1Log.DEFAULT_KEEP and s.connections.history == [] and s.pulse == 0
    run = measured(SYN[0])["run"]
    assert [run["bodies"][n]["world_end"]["rule"]["rule_c"] for n in M.SYSTEMS] == ["A1", "A2", "A1"]
    assert all(run["bodies"][n]["world_end"]["rule"]["respond"] is True for n in M.SYSTEMS)
    assert M.RULE_OF == PROTOCOL["world"]["rule_c"] and list(M.SYSTEMS) == PROTOCOL["bodies"]["per_individual"]


def test_ct41_1_the_bodies_equal_the_gate_run_body_up_to_p_e() -> None:
    """本番の Plan の B^{A1}・B^{A2}・B′^{A1} の P_E までの記録と Σ が、関門の宣言 v0.2 の `run_body` の本体（同じ組み立て）を
    Pulse 1,065 まで進めたものと同じ。関門の run_body を終わりまで走らせた層 A の窓 1〜25 とも同じ。"""
    decl, _ = M.gate_declaration(PROTOCOL)
    run = measured(FORMAL_SEED, FORMAL)["run"]
    for n in M.SYSTEMS:
        c = M.RULE_OF[n]
        gate_like = A.build(FORMAL_SEED, schedule=GATE.schedule_of(decl, A), delay=decl["world"]["delay_L"], rule_c=c, respond=True)
        A.advance_to(gate_like.app, FORMAL.p_e)
        rec = run["bodies"][n]
        assert AS1.sigma_diff(M._sigma(gate_like), rec["sigma_p_e"]) == [], n
        assert [dict(r) for r in gate_like.decider.records] == rec["layer_a"]
        assert [list(x) for x in gate_like.world.intents] == rec["layer_b"]
        assert [list(x) for x in gate_like.log.activity()] == rec["activity"]
    for c, n in (("A1", "B_A1"), ("A2", "B_A2")):
        _row, audit = GATE.run_body(A, decl, FORMAL_SEED, c)
        assert audit["layer_a"][:25] == run["bodies"][n]["layer_a"] and audit["reached_windows"] == 50


def test_the_gate_and_earlier_and_formal_seeds_are_never_run_by_the_tests(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    commit = _git(repo, "rev-parse", "HEAD")
    for seed in (31001, 31040, 32001, 32301, 33001, 33301, 33399, 34001, 34201, 30201):
        with pytest.raises(R.G.GuardError):
            R.execute("synthetic", [seed], tmp_path / f"o{seed}", repo, commit, runner=_dummy, executor_factory=SerialExecutor)
        assert not (tmp_path / f"o{seed}").exists()
    for mode in ("formal", "smoke"):
        with pytest.raises(R.G.GuardError):
            R.execute(mode, [33001], tmp_path / f"g{mode}", repo, commit, runner=_dummy, executor_factory=SerialExecutor)


def test_ct41_1_the_steps_and_the_observation_split_follow_the_preregistration() -> None:
    run = measured(SYN[0])["run"]
    assert run["steps"] == AN.expected_steps(run)
    assert [s[:4] for s in run["steps"][:3]] == [["T0", "B_A1", 0, "build"], ["T1", "B_A1", SMALL.p_e, "advance_each_pulse"],
                                                  ["T2", "B_A1", SMALL.p_e, "end_records"]]
    assert set(run["bodies"]["B_A1"]) == AN.BODY_KEYS["B_A1"] and set(run["bodies"][M.RERUN]) == AN.END_KEYS


# ---- CT-41-2 共通の部分（SE-B1） -----------------------------------------------------------------------

def test_ct41_2_the_two_bodies_share_the_prefix_up_to_the_k_star_intent() -> None:
    """k* の意図の Pulse まで、二つの本体の脳の側の Σ と層 A・発火・重みが一致し、その後の結果の予約は、規則 c が k* の行動 ID を
    指す本体にだけある（値は表示しない）。"""
    run = measured(decided_seed())["run"]
    a, b = run["bodies"]["B_A1"], run["bodies"]["B_A2"]
    k = AN.k_star(a["layer_a"], SMALL.e_windows)
    assert k is not None and k == AN.k_star(b["layer_a"], SMALL.e_windows)
    assert a["layer_a"][:k] == b["layer_a"][:k]
    t = a["layer_a"][k - 1]["decision_pulse"] + 1
    assert a["first_intent"]["pulse"] == b["first_intent"]["pulse"] == t
    diff = [tuple(p) for p in AS1.sigma_diff(a["first_intent"]["sigma"], b["first_intent"]["sigma"])]
    assert ("world", "rule", "rule_c") in diff and all(AN._prefix_allowed(p) for p in diff)
    assert not any(p[0] in ("units", "connections", "drives", "exit", "deltas", "issuer") for p in diff)
    action = a["layer_a"][k - 1]["outcome"]
    for name, x in (("B_A1", a), ("B_A2", b)):
        cons = [r for r in x["first_intent"]["sigma"]["world"]["reserved"] if r[1] == A.CONSEQUENCE]
        assert len(cons) == (1 if M.RULE_OF[name] == action else 0)
        if cons:
            assert cons[0][3] == t + SMALL.delay - 1
    assert a["pulse_weights"][:t] == b["pulse_weights"][:t]
    assert sorted(tuple(p) for p in AS1.sigma_diff(a["sigma_0"], b["sigma_0"])) == [("world", "rule", "rule_c")]


def test_ct41_2_without_k_star_the_bodies_are_identical_through_p_e_and_every_quantity_is_zero() -> None:
    """SE-B1：E に決まった窓がない個体では、P_E まで規則 c のほかが同じで、δ・q・δ^←・ε はちょうど 0（構造的な 0。札 Z-1）。"""
    data = zero_individual()
    a, b = data["run"]["bodies"]["B_A1"], data["run"]["bodies"]["B_A2"]
    assert AN.k_star(a["layer_a"], SMALL.e_windows) is None and a["first_intent"] is None and b["first_intent"] is None
    for key in ("activity", "sensory", "layer_a", "layer_b", "delta_log", "pulse_weights"):
        assert a[key] == b[key], key
    assert [tuple(p) for p in AS1.sigma_diff(a["sigma_p_e"], b["sigma_p_e"])] == [("world", "rule", "rule_c")]
    ind = AN.individual(data["run"])
    assert ind["k_star"] is None and ind["structural_zero"] == "Z-1" and ind["other_zero"] is False
    assert all(v["num"] == 0 and v["sign"] == "0" for v in ind["quantities"].values())


def test_ct41_2_k_star_and_the_zero_labels_on_hand_made_layers() -> None:
    assert AN.k_star(_layer(["none", "tie", "A2", "A1"]), 4) == 3 and AN.k_star(_layer(["none", "tie", "none", "A1"]), 3) is None
    assert AN.zero_label(_layer(["none"] * 4), 4) == "Z-1" and AN.zero_label(_layer(["none", "tie", "none", "none"]), 4) == "Z-2"
    assert AN.zero_label(_layer(["tie", "A1"]), 2) is None and AN.zero_label(_layer(["tie", "A1"]), 1) == "Z-2"


def test_o4_detects_tampering() -> None:
    s = decided_seed()
    for tamper in (lambda r: r["bodies"]["B_A2"]["sigma_0"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["bodies"]["B_A2"]["first_intent"]["sigma"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["bodies"]["B_A2"]["first_intent"].update(pulse=r["bodies"]["B_A2"]["first_intent"]["pulse"] + 1),
                   lambda r: r["bodies"]["B_A1"].update(first_intent=None),
                   lambda r: r["bodies"]["B_A2"]["activity"].insert(0, [1, "zz"]),
                   lambda r: r["bodies"]["B_A2"]["pulse_weights"][0][1].__setitem__(0, 0.0049)):
        data = measured(s)
        tamper(data["run"])
        assert "O4" in failures(data, s)
    for tamper in (lambda r: r["bodies"]["B_A2"]["sigma_p_e"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["bodies"]["B_A2"].update(first_intent={"pulse": 1, "sigma": r["bodies"]["B_A2"]["sigma_0"]}),
                   lambda r: r["bodies"]["B_A1"]["activity"].append([SMALL.p_e, r["roles"]["cue"]])):
        data = zero_individual()
        tamper(data["run"])
        assert "O4" in failures(data, CORNER_SEEDS[0])


# ---- CT-41-3 境界（SE-B7） ----------------------------------------------------------------------------------

def test_ct41_3_at_p_e_nothing_is_open_or_reserved_and_every_body_stops_there() -> None:
    for data in (measured(decided_seed()), measured(FORMAL_SEED, FORMAL)):
        run = data["run"]
        plan = M.Plan(**run["plan"])
        for n in M.SYSTEMS:
            rec = run["bodies"][n]
            s = rec["sigma_p_e"]
            assert rec["pulse_end"] == s["pulse"] == plan.p_e
            assert s["exit"]["cursor"] == plan.e_windows and s["exit"]["pending"] is None and s["exit"]["reports"] == {}
            assert all(r[1] == A.CUE and r[3] > plan.p_e for r in rec["world_end"]["pending"])
            assert sorted(r[3] for r in rec["world_end"]["pending"]) == [c for c in plan.schedule().cues if c > plan.p_e]
            assert all(r[3] <= plan.p_e for r in rec["world_end"]["reserved"] if r[1] == A.CONSEQUENCE)
    # Gemini の監査（BLACKBOARD 702dcc9）：組み立てのときに 50 窓分の手がかりを予約するので、本番の Plan の P_E に残る予約は、
    # 窓 26〜50 の手がかり（Pulse 1066〜2050）の 25 件だけ。予約の履歴（reserved）は空ではない。層 A は 25 窓、cursor ＝ 25
    for n in M.SYSTEMS:
        rec = run["bodies"][n]
        pending = sorted(r[3] for r in rec["world_end"]["pending"])
        assert len(pending) == 25 and (pending[0], pending[-1]) == (1066, 2050)
        assert {r[1] for r in rec["world_end"]["pending"]} == {A.CUE} and len(rec["world_end"]["reserved"]) >= 50
        assert len(rec["layer_a"]) == 25 and rec["sigma_p_e"]["exit"]["cursor"] == 25 and rec["sigma_p_e"]["exit"]["pending"] is None


def test_o7_detects_tampering() -> None:
    s = decided_seed()
    cue_r = measured(s)["run"]["roles"]["cue_receptor"]
    for tamper in (lambda r: r["bodies"]["B_A1"]["sigma_p_e"]["exit"].update(cursor=SMALL.e_windows - 1),
                   lambda r: r["bodies"]["B_A2"]["sigma_p_e"]["exit"].update(pending={"unit": "s1"}),
                   lambda r: r["bodies"][M.RERUN]["world_end"]["pending"].append([99, A.CONSEQUENCE, cue_r, SMALL.p_e + 1, "d"]),
                   lambda r: r["bodies"]["B_A1"]["world_end"]["pending"].pop(),
                   lambda r: r["bodies"]["B_A2"]["sigma_p_e"].update(pulse=SMALL.p_e + 1),
                   lambda r: r["bodies"]["B_A1"]["world_end"].update(last_drained={})):
        data = measured(s)
        tamper(data["run"])
        assert "O7" in failures(data, s)


# ---- CT-41-4 記録の非干渉（SE-B4・O8） ---------------------------------------------------------------------

def test_ct41_4_the_rerun_reads_nothing_while_running_and_equals_b_a1() -> None:
    run = measured(decided_seed())["run"]
    for key in ("activity", "sensory", "layer_a", "layer_b", "delta_log", "sigma_p_e", "sigma_p_e_sha256", "history"):
        assert run["bodies"]["B_A1"][key] == run["bodies"][M.RERUN][key], key
    rec = run["bodies"][M.RERUN]
    assert set(rec) == AN.BODY_KEYS[M.RERUN] and not {"pulse_weights", "sigma_0", "first_intent"} & set(rec)
    src = inspect.getsource(M.measure_seed)
    assert "rerun = build_body(plan, seed, RULE_OF[RERUN])" in src          # log を渡さない ＝ AS2b の道具の既定のログ
    assert "A.advance_to(rerun.app, p_e)" in src and "_advance_each_pulse(rerun" not in src
    rerun_part = src[src.index("rerun = build_body"):src.index("return {")]
    assert "_sigma(rerun)" not in rerun_part and "_row(rerun" not in rerun_part and rerun_part.count("A.advance_to") == 1
    assert rerun_part.index("A.advance_to(rerun.app, p_e)") < rerun_part.index("_end_record(rerun)")


def test_ct41_4_the_p_e_sigma_is_kept_whole_and_compared_by_value() -> None:
    """3 本体とも P_E の Σ を値の全体で保存する。O8 は値の完全な一致が主で、SHA-256 は補助。正規化は鍵の順に依らない。"""
    run = measured(decided_seed())["run"]
    for n in M.SYSTEMS:
        end = run["bodies"][n]["sigma_p_e"]
        assert end["pulse"] == SMALL.p_e and M.sigma_sha256(end) == run["bodies"][n]["sigma_p_e_sha256"]
        assert set(end) == {"pulse", "clock", "units", "connections", "drives", "deltas", "issuer", "runtime", "world",
                            "interventions", "exit"}                     # 来歴のログを含まない
        shuffled = json.loads(json.dumps(dict(reversed(list(end.items())))))
        assert M.sigma_sha256(shuffled) == M.sigma_sha256(end) == RC._sha(end)
    assert AS1.sigma_diff(run["bodies"]["B_A1"]["sigma_p_e"], run["bodies"][M.RERUN]["sigma_p_e"]) == []
    assert AS1.sigma_diff(run["bodies"]["B_A1"]["sigma_p_e"], run["bodies"]["B_A2"]["sigma_p_e"])     # 規則 c の違う本体は違う


def _same_sha_value_change(r, name: str) -> None:
    """P_E の Σ の値だけを変え、SHA-256 の欄は元のまま残す（値の照合が主であることの確かめ）。"""
    r["bodies"][name]["sigma_p_e"]["units"][r["roles"]["cue"]]["activity"] = 9.0


def test_o8_detects_a_different_rerun() -> None:
    s = decided_seed()
    for tamper in (lambda r: r["bodies"][M.RERUN]["activity"].pop(),
                   lambda r: r["bodies"][M.RERUN]["layer_b"].pop(),
                   lambda r: _same_sha_value_change(r, M.RERUN),
                   lambda r: _same_sha_value_change(r, "B_A1"),
                   lambda r: r["bodies"][M.RERUN].update(sigma_p_e_sha256="0" * 64),
                   lambda r: r["bodies"]["B_A2"].update(sigma_p_e_sha256="0" * 64),
                   lambda r: r["bodies"][M.RERUN]["history"].append([0, "x", []])):
        data = measured(s)
        tamper(data["run"])
        assert "O8" in failures(data, s)


def test_ct41_4_reading_the_weights_and_sigma_does_not_change_the_state() -> None:
    """重みの読み出しと Σ の書き出しは、状態を変えない：1 Pulse ごとに読んだ本体と、一度に進めた本体の P_E の Σ が同じ。"""
    for c in ("A1", "A2"):
        read = M.build_body(SMALL, SYN[1], c, log=_log())
        order = sorted(M._weights(read))
        for p in range(1, SMALL.p_e + 1):
            A.advance_to(read.app, p)
            M._row(read, order)
            M._sigma(read)
        plain = M.build_body(SMALL, SYN[1], c)
        A.advance_to(plain.app, SMALL.p_e)
        assert AS1.sigma_diff(M._sigma(read), M._sigma(plain)) == []


# ---- CT-41-5 世界（SE-B2・O5） ---------------------------------------------------------------------------

def test_ct41_5_consequences_follow_only_the_rule_c_intents() -> None:
    run = measured(decided_seed())["run"]
    for n in M.SYSTEMS:
        rec = run["bodies"][n]
        w = rec["world_end"]
        cons = sorted((r[3], r[4]) for r in w["reserved"] if r[1] == A.CONSEQUENCE)
        assert cons == sorted((p + SMALL.delay - 1, did) for p, did, _src, act in rec["layer_b"] if act == M.RULE_OF[n])
        assert len(cons) == sum(1 for r in rec["layer_a"] if r["outcome"] == M.RULE_OF[n])         # SE-B2
        assert {r for _, r in rec["sensory"]} <= {run["roles"]["cue_receptor"]}
    ind = AN.individual(run)
    assert all(ind["consequences"][n]["stimuli"] == ind["consequences"][n]["decided_of_rule_c"] for n in M.SYSTEMS)


def test_o5_detects_a_wrong_consequence_or_a_source_receptor_event() -> None:
    s = decided_seed()
    run = measured(s)["run"]
    src_r = AS1.RECEPTOR_OF[run["roles"]["source1"]]
    cue_r = run["roles"]["cue_receptor"]
    for tamper in (lambda r: r["bodies"]["B_A1"]["sensory"].append([5, src_r]),
                   lambda r: r["bodies"]["B_A2"]["world_end"]["reserved"].append([99, A.CONSEQUENCE, cue_r, 50, "d1"]),
                   lambda r: r["bodies"][M.RERUN]["world_end"]["reserved"].append([99, A.EXOGENOUS, cue_r, 51, None]),
                   lambda r: r["bodies"]["B_A1"]["world_end"]["realized"].pop(0),
                   lambda r: r["bodies"]["B_A2"]["world_end"]["cancelled"].append([98, A.CUE, cue_r, 9, None]),
                   lambda r: r["bodies"][M.RERUN]["sensory"].pop()):
        data = measured(s)
        tamper(data["run"])
        assert "O5" in failures(data, s)


def test_ct41_5_rule_c_is_the_only_difference_of_the_world() -> None:
    """二つの規則の世界は、規則 c の指す行動 ID の意図にだけ結果を返す。同じ意図の列を渡すと、結果の予約だけが違う。"""
    worlds = [A.AS2bWorld(cue_receptor="r", delay=2, rule_c=c, cues=[41]) for c in ("A1", "A2")]
    for w in worlds:
        w.receive_intent(60, "d1", "s1", "A1")
        w.receive_intent(70, "d2", "s2", "A2")
    cons = [[(r.pulse, r.origin) for r in w.reserved if r.kind == A.CONSEQUENCE] for w in worlds]
    assert cons == [[(61, "d1")], [(71, "d2")]]


# ---- CT-41-6 F1 と範囲（SE-B5・O6） ------------------------------------------------------------------------

def test_ct41_6_pair_sums_stay_at_w_max_and_delta_back_mirrors_delta() -> None:
    """各組の 2 本の和は、Pulse ごとに w_max から 10⁻¹² 以内。δ^← と −δ の違いは浮動小数の誤差の範囲（値は表示しない）。"""
    for data in (measured(decided_seed()), measured(FORMAL_SEED, FORMAL)):
        run = data["run"]
        pairs = AN._pairs(run["connection_order"])
        assert len(pairs) == 3
        for n in M.BODIES:
            assert all(AN._row_ok(w, pairs) for _p, w in run["bodies"][n]["pulse_weights"])
        ind = AN.individual(run)
        assert all(x <= AN.F1_TOLERANCE for x in ind["pair_sum_max_deviation"].values())
        assert abs(Fraction(ind["delta_plus_delta_back"]["num"], ind["delta_plus_delta_back"]["den"])) <= 4 * Fraction(AN.F1_TOLERANCE)
    w1 = {"C_to_source1": 0.006, "source1_to_C": 0.004, "C_to_source2": 0.005, "source2_to_C": 0.005,
          "source1_to_source2": 0.005, "source2_to_source1": 0.005}
    w2 = dict(w1, C_to_source1=0.0055, source1_to_C=0.0045)
    q = AN.quantities(w1, w2)
    assert q["delta"] == Fraction(0.006) - Fraction(0.0055) and q["delta_back"] == Fraction(0.004) - Fraction(0.0045)
    assert abs(q["delta"] + q["delta_back"]) < Fraction(1, 10 ** 15)


def test_o6_detects_a_weight_out_of_range_or_a_broken_pair_or_an_intervention() -> None:
    s = SYN[0]
    for tamper in (lambda r: r["bodies"]["B_A1"]["pulse_weights"][5][1].__setitem__(0, r["bodies"]["B_A1"]["pulse_weights"][5][1][0]
                                                                                   + 1e-9),
                   lambda r: r["bodies"]["B_A2"]["pulse_weights"][7][1].__setitem__(1, W_MAX + 0.001),
                   lambda r: r["bodies"][M.RERUN]["sigma_p_e"]["connections"][min(r["W_0"])].update(weight=-0.001),
                   lambda r: r["bodies"]["B_A2"]["history"].append([0, "x", []]),
                   lambda r: r["bodies"]["B_A1"]["sigma_p_e"]["interventions"].update(active=[["FREEZE", [], "advance"]])):
        data = measured(s)
        tamper(data["run"])
        assert "O6" in failures(data, s)


def test_o9_detects_inconsistent_weight_records() -> None:
    s = decided_seed()
    for tamper in (lambda r: r["bodies"]["B_A1"]["pulse_weights"].pop(),
                   lambda r: r["bodies"]["B_A2"]["pulse_weights"][-1][1].reverse(),
                   lambda r: r["bodies"]["B_A1"]["sigma_0"]["connections"][min(r["W_0"])].update(weight=0.004),
                   lambda r: r["bodies"]["B_A2"]["sigma_0"].update(pulse=1),
                   lambda r: r["bodies"]["B_A1"]["first_intent"]["sigma"]["connections"][min(r["W_0"])].update(weight=0.0001)):
        data = measured(s)
        tamper(data["run"])
        assert "O9" in failures(data, s)


# ---- CT-41-7 命題 S-1・補題 L1・L2・SE-B6（README §7.2） ---------------------------------------------------------

def _corner_system(seed: int, rule_c: str, values: dict, *, freeze_at_w_max: bool):
    """Unit の θ・c・初期の activity を決めた値に置いた合成の系（契約テストだけ。CT-39-8 と同じ形）。

    values：役（cue・source1・source2）→ (θ, c)。freeze_at_w_max なら 6 本を w_max にして止める（発火しやすさの上限）。
    """
    s = M.build_body(FORMAL, seed, rule_c, log=_log())
    _place(s, values)
    if freeze_at_w_max:
        six = frozenset(M._weights(s))
        s.transplant(dict.fromkeys(six, W_MAX))
        s.declare([AS1.Intervention(AS1.FREEZE, six, AS1.ADVANCE)], label="corner")
    return s


def _run_recording_adaptation(system, unit_id, until: int) -> float:
    top = 0.0
    for pulse in range(1, until + 1):
        A.advance_to(system.app, pulse)
        top = max(top, _inner(system, unit_id).export_state()["adaptation"])
    return top


def _gaps(pulses: list[int]) -> list[int]:
    return [b - a for a, b in itertools.pairwise(pulses)]


def test_ct41_7_the_bound_e_s_matches_the_preregistered_analysis() -> None:
    lam, w = LAMBDA, W_MAX
    e_s = w * ((1 + lam ** 4) / (1 - lam ** 23) + 2 / (1 - lam ** 7))
    assert AN.E_S == pytest.approx(e_s, abs=1e-15) and AN.E_S == pytest.approx(PROTOCOL["proposition_S1"]["E_S_value"], abs=5e-6)
    assert RC.bound_e_s(M.manifest_raw(), dataclasses.asdict(FORMAL)) == pytest.approx(AN.E_S, abs=1e-15)
    assert AN.margin({"dynamics": {"intrinsic_drive_per_second": 0.08, "decay_per_second": 0.85, "threshold": 0.5}}) \
        == pytest.approx(0.08 / 0.15 - 0.5)


@pytest.mark.parametrize("rule_c", ["A1", "A2"])
@pytest.mark.parametrize("freeze", [True, False])
def test_ct41_7_a_source_below_the_bound_never_fires_even_at_the_corners(rule_c, freeze) -> None:
    """命題 S-1：g ＜ −E_S の源は、ほかの二つの Unit を最も発火しやすい値に置き、6 本を w_max で止めても（または可塑性のままでも）、
    世界が結果を返す P_E までのあいだ一度も発火しない。"""
    easy = (THETA[0], DRIVE[1])
    s = _corner_system(CORNER_SEEDS[0], rule_c, {"source1": _silent_values(), "cue": easy, "source2": easy}, freeze_at_w_max=freeze)
    assert AN.margin(_inner(s, s.roles.source1).export_state()) < -AN.E_S
    A.advance_to(s.app, FORMAL.p_e)
    fired = {u for _, u in s.log.activity()}
    assert s.roles.source1 not in fired and _inner(s, s.roles.source1).export_state()["fire_count"] == 0
    assert {s.roles.cue, s.roles.source2} <= fired                   # ほかの二つは発火している（確かめが空でない）
    assert all(r["outcome"] in ("A2", A.NONE) for r in s.decider.records)      # その源の行動 A1 は一度も勝たない


@pytest.mark.parametrize("rule_c", ["A1", "A2"])
def test_ct41_7_the_four_connections_of_a_silent_source_stay_at_w0(rule_c) -> None:
    """SE-B6：構造的に沈黙する源に触れる 4 本（C ↔ 源、源 ↔ もう一方の源）の重みは、可塑性のまま P_E まで w0 のまま。
    痕跡も出生時の 0 のまま。ほかの 2 本（C ↔ もう一方の源）は動きうる（確かめが空でない）。"""
    easy = (THETA[0], DRIVE[1])
    s = _corner_system(CORNER_SEEDS[1], rule_c, {"source1": _silent_values(), "cue": easy, "source2": easy}, freeze_at_w_max=False)
    roles = s.roles.as_dict()
    touching = {cid for cid in M._weights(s) if roles["source1"] in cid.split(".main->")}
    assert len(touching) == 4
    moved = set()
    for p in range(1, FORMAL.p_e + 1):
        A.advance_to(s.app, p)
        state = s.app.connections.export_state()
        assert all(state[cid]["weight"] == W0 for cid in touching)
        moved |= {cid for cid, v in state.items() if v["weight"] != W0}
    for cid in touching:                                              # 沈黙した源の痕跡は出生時の 0 のまま
        src, tgt = cid.split(".main->")
        assert (src != roles["source1"] or state[cid]["pre_trace"] == 0) and (tgt != roles["source1"] or state[cid]["post_trace"] == 0)
    assert moved and not (moved & touching)


def test_ct41_7_a_silent_source_gives_its_q_zero_and_epsilon_zero_through_the_measurement() -> None:
    """SE-B6 を本番と同じ measure_seed の記録で：源 1 が構造的に沈黙する個体では、源 1 に触れる 4 本は観測する両方の本体で
    すべての Pulse で w0、q_1 ＝ 0・ε ＝ 0・δ ＝ q_2（値は表示しない）。札は源 1 だけ。両方が沈黙すれば構造的な 0。"""
    data = one_silent_individual()
    run = data["run"]
    touching = [i for i, cid in enumerate(run["connection_order"]) if run["roles"]["source1"] in cid.split(".main->")]
    assert len(touching) == 4
    for n in M.BODIES:
        assert all(w[i] == W0 for _p, w in run["bodies"][n]["pulse_weights"] for i in touching)
    ind = AN.individual(run)
    assert ind["S1"] == {"silent_source": {"source1": True, "source2": False}, "violations": []}
    q = ind["quantities"]
    assert q["q_1"]["num"] == 0 and q["epsilon"]["num"] == 0 and (q["delta"]["num"], q["delta"]["den"]) == (q["q_2"]["num"], q["q_2"]["den"])
    both = AN.individual(zero_individual()["run"])
    assert both["S1"]["silent_source"] == {"source1": True, "source2": True} and both["structural_zero"] == "Z-1"


@pytest.mark.parametrize("rule_c", ["A1", "A2"])
def test_ct41_7_lemma_l1_and_l2_hold_at_the_corners(rule_c) -> None:
    """補題 L1：手がかりの Unit は、Receptor の入力の入る Pulse（感覚の出来事の翌 Pulse）に必ず発火し、順応は 0.441 未満。そのほかの
    発火は、直前の発火から 7 Pulse 以上後。補題 L2：源の連続する発火は 7 Pulse 以上離れる。結果の刺激は手がかりから 4 以上、
    次の手がかりまで 19 以上離れる。"""
    easy = (THETA[0], DRIVE[1])
    for cue_values in (easy, (THETA[1], DRIVE[0])):                  # 手がかりの Unit：最も発火しやすい角と、最も発火しにくい角
        s = _corner_system(CORNER_SEEDS[2], rule_c, {"cue": cue_values, "source1": easy, "source2": easy}, freeze_at_w_max=True)
        top = _run_recording_adaptation(s, s.roles.cue, FORMAL.p_e)
        act = s.log.activity()
        cue_fires = [p for p, u in act if u == s.roles.cue]
        r_pulses = {p + 1 for p, _ in s.log.sensory() if p + 1 <= FORMAL.p_e}
        assert r_pulses and r_pulses <= set(cue_fires)               # L1：R の Pulse では必ず発火する
        assert top < 0.441
        for prev, cur in itertools.pairwise(cue_fires):
            assert cur in r_pulses or cur - prev >= 7                # L1：R でない発火は、直前の発火から 7 以上後
        for src in (s.roles.source1, s.roles.source2):
            fires = [p for p, u in act if u == src]
            assert len(fires) > 10 and min(_gaps(fires)) >= 7        # L2
        cons = sorted(r[3] for r in s.world.export_state()["reserved"] if r[1] == A.CONSEQUENCE)
        cues = list(FORMAL.schedule().cues)
        for x in cons:
            k = max(i for i, c in enumerate(cues) if c <= x)
            assert x - cues[k] >= 4 and (k + 1 == len(cues) or cues[k + 1] - x >= 19)


def test_ct41_7_the_s1_label_and_a_violation_are_reported_without_changing_the_judgment() -> None:
    s = decided_seed()
    run = measured(s)["run"]
    src = run["roles"]["source1"]
    d = run["birth_units"][src]["dynamics"]
    d["threshold"], d["intrinsic_drive_per_second"] = 0.55, 0.072    # 記録の上だけ、構造的に沈黙する源の値にする
    ind = AN.individual(run)
    assert ind["S1"]["silent_source"] == {"source1": True, "source2": False}
    fired = any(u == src for n in M.SYSTEMS for _, u in run["bodies"][n]["activity"])
    assert ind["S1"]["violations"] == (["source1"] if fired else [])
    aux = AN.auxiliary({"1": ind})
    assert aux["R1"]["S1"]["labels_withdrawn"] is fired
    assert aux["R1"]["S1"]["individuals_with_silent_source"] == (None if fired else 1)
    dc = AN.descriptive_controls({"1": ind})["zero_table"]
    assert dc["S1_labels_withdrawn"] is fired and (dc["silent_source"] is None) is fired
    assert "S1" not in json.dumps(AN.judge({"1": ind})) and "S1" not in json.dumps(AN.estimate({"1": ind}))


# ---- CT-41-8 量と判定・推定の算術（README §3〜§5。手で作った記録） ----------------------------------------------

def _layer(outcomes: list[str]) -> list[dict]:
    return [{"window": k + 1, "outcome": o} for k, o in enumerate(outcomes)]


def _w(c_s1, c_s2, s1_s2) -> dict:
    """F1 を保つ 6 本（役の名前）。"""
    return {"C_to_source1": c_s1, "source1_to_C": W_MAX - c_s1, "C_to_source2": c_s2, "source2_to_C": W_MAX - c_s2,
            "source1_to_source2": s1_s2, "source2_to_source1": W_MAX - s1_s2}


def test_window_counts_and_signs() -> None:
    la = _layer(["A1", "tie", "none", "A2", "A1", "A1", "none", "A2"])
    assert AN.window_counts(la, 1, 4) == {"windows": 4, "decided": 2, "A1": 1, "A2": 1, "tie": 1, "none": 1}
    assert RC.window_count(la, 1, 4) == AN.window_counts(la, 1, 4)
    assert [AN.sign(x) for x in (Fraction(1, 7), Fraction(-1, 7), Fraction(0))] == ["+", "-", "0"]


def test_the_quantities_are_exact_rationals_of_the_stored_binary64_values() -> None:
    w1, w2 = _w(0.0053, 0.0049, 0.00502), _w(0.0047, 0.0051, 0.00497)
    q = AN.quantities(w1, w2)
    f, h = {k: Fraction(v) for k, v in w1.items()}, {k: Fraction(v) for k, v in w2.items()}
    assert q["delta"] == (f["C_to_source1"] - h["C_to_source1"]) - (f["C_to_source2"] - h["C_to_source2"])
    assert q["q_1"] == f["C_to_source1"] - h["C_to_source1"] and q["q_2"] == h["C_to_source2"] - f["C_to_source2"]
    assert q["delta"] == q["q_1"] + q["q_2"] and q["delta"] != Fraction(str(0.0053 - 0.0047 - (0.0049 - 0.0051)))
    assert q["epsilon"] == (f["source1_to_source2"] - h["source1_to_source2"]) - (f["source2_to_source1"] - h["source2_to_source1"])
    assert RC.contrast(w1, w2) == q                                         # 独立に書き起こした定義と同じ
    assert AN.quantities(w1, w1) == dict.fromkeys(AN.QUANTITIES, Fraction(0))
    up = math.nextafter(w1["C_to_source1"], 1.0)                             # 1 ULP の違いも 0 に丸めず、符号に残る
    tiny = dict(w1, C_to_source1=up)
    assert AN.sign(AN.quantities(tiny, w1)["delta"]) == "+" and AN.sign(AN.quantities(w1, tiny)["delta"]) == "-"
    assert AN.quantities(tiny, w1)["delta"] == Fraction(up) - Fraction(w1["C_to_source1"]) == RC.contrast(tiny, w1)["delta"]


def test_the_quantities_use_the_binary64_values_after_the_json_round_trip_not_their_decimal_text() -> None:
    """Gemini の監査（BLACKBOARD 702dcc9）の補助注意 (a)：JSON を往復した倍精度の値を Fraction(float) で正確に扱い、
    Fraction(str(w)) に置き換えない。10 進の表記では同じ差でも、倍精度の正確な差は違うことがある。"""
    a, b = 0.1 + 0.2, 0.3
    assert json.loads(json.dumps(a)) == a                                     # JSON の往復で倍精度の値は変わらない
    w1, w2 = _w(a / 50, W0, W0), _w(b / 50, W0, W0)
    q = AN.quantities(w1, w2)
    assert q["q_1"] == Fraction(a / 50) - Fraction(b / 50) == RC.contrast(w1, w2)["q_1"]
    assert q["q_1"] != Fraction(str(a / 50)) - Fraction(str(b / 50))
    for src in (inspect.getsource(AX.contrasts), inspect.getsource(AN.individual), inspect.getsource(RC.contrast),
                inspect.getsource(RC.max_pair_gap), inspect.getsource(AN.pair_deviation)):
        assert "Fraction(str(" not in src


def test_swapping_the_labels_keeps_delta_delta_back_and_epsilon_and_exchanges_q() -> None:
    """SE-B3：源 1 と源 2 の札を入れ替えると、規則 c ＝ A1 の本体は A2 の本体になる。δ・δ^←・ε は正確に同じ、q_1 と q_2 は入れ替わる。"""
    for w1, w2 in ((_w(0.0053, 0.0049, 0.00502), _w(0.0047, 0.0051, 0.00497)), (_w(0.0061, W0, W0), _w(0.0058, W0, W0)),
                   (_w(W0, W0, W0), _w(W0, W0, W0))):
        before = AN.quantities(w1, w2)
        after = AN.quantities(AX.swap_labels(w2), AX.swap_labels(w1))
        assert (after["delta"], after["delta_back"], after["epsilon"]) == (before["delta"], before["delta_back"], before["epsilon"])
        assert (after["q_1"], after["q_2"]) == (before["q_2"], before["q_1"])
    assert AX.label_swap_check(AX.c0_values())["q1_q2_exchanged"] is True


def _fake(delta: str = "0", *, k_star: int | None = 1, q1: str = "0", q2: str = "0", back: str | None = None, eps: str = "0",
          value: float | None = None, zero: str | None = None) -> dict:
    """判定・推定・記述の算術の確かめ用の個体。"""
    v = {"+": 0.25, "-": -0.25, "0": 0.0}
    back = {"+": "-", "-": "+", "0": "0"}[delta] if back is None else back
    out = {name: {"value": v[s], "sign": s} for name, s in (("delta", delta), ("q_1", q1), ("q_2", q2), ("delta_back", back),
                                                            ("epsilon", eps))}
    if value is not None:
        out["delta"]["value"] = value
    return {"quantities": out, "k_star": k_star, "structural_zero": zero, "other_zero": k_star is not None and delta == "0",
            "S1": {"silent_source": {"source1": False, "source2": False}, "violations": []},
            "delta_plus_delta_back": {"value": out["delta"]["value"] + out["delta_back"]["value"]}}


def _group(plus: int, minus: int, zero: int) -> dict:
    rows = [_fake("+")] * plus + [_fake("-")] * minus + [_fake("0", k_star=None, zero="Z-1")] * zero
    return {str(i): copy.deepcopy(r) for i, r in enumerate(rows)}


def test_k2_of_200_and_the_binomial_tail() -> None:
    assert AN.k2_of_m(200) == PROTOCOL["judgment"]["J_B"]["k2_200"] == 115 == RC.k2(200, Fraction(1, 40)) == AX.k2(200)
    assert AN.binom_upper_tail(200, 115) <= Fraction(1, 40) < AN.binom_upper_tail(200, 114)
    assert float(AN.binom_upper_tail(200, 115)) == pytest.approx(0.0200, abs=5e-5)
    assert float(AN.binom_upper_tail(200, 114)) == pytest.approx(0.0280, abs=5e-5)
    assert AN.k2_of_m(3) == 4 == RC.k2(3, Fraction(1, 40))                  # どの数でも成立しない m
    broken = copy.deepcopy(PROTOCOL)
    broken["judgment"]["J_B"]["k2_200"] = 114
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(AN, "PROTOCOL", broken)
        with pytest.raises(ValueError, match="k₂"):
            AN.k2_of_m(200)


@pytest.mark.parametrize("plus", [True, False])
def test_j_b_at_the_114_115_boundary_in_both_directions_and_zeros_stay_in_the_denominator(plus) -> None:
    def g(k, rest, zero):
        return _group(k, rest, zero) if plus else _group(rest, k, zero)
    j = AN.judge(g(115, 0, 85))                                               # m ＝ 200、0 も分母に残る
    assert (j["J_B"]["m"], j["J_B"]["k2"], j["J_B"]["status"], j["J_B"]["direction"]) == (200, 115, "established",
                                                                                         "+" if plus else "-")
    assert j["outcome"] == ("plus" if plus else "minus")
    j = AN.judge(g(114, 0, 86))
    assert (j["J_B"]["status"], j["J_B"]["direction"], j["outcome"]) == ("not_established", None, "not_established")
    j = AN.judge(g(114, 86, 0))
    assert j["outcome"] == "not_established" and j["J_B"]["counts"] == ({"+": 114, "-": 86, "0": 0} if plus
                                                                       else {"+": 86, "-": 114, "0": 0})
    assert j["J_B"]["interval"]["+"]["denominator"] == 200 and j["J_B"]["tail_probability"] == float(AN.binom_upper_tail(200, 115))
    assert RC.judgment(list(g(115, 0, 85).values()))["outcome"] == ("plus" if plus else "minus")


def test_there_is_no_inconclusive_class_and_m_is_the_number_of_born_individuals() -> None:
    small = AN.judge(_group(3, 0, 0))
    assert small["J_B"]["m"] == 3 and small["J_B"]["status"] == "not_established" and small["outcome"] == "not_established"
    assert "inconclusive" not in json.dumps(AN.judge(_group(0, 0, 5)))


def test_the_estimate_e_b_counts_changes_without_a_threshold() -> None:
    rows = {"1": _fake("+"), "2": _fake("-", value=-0.5), "3": _fake("0"), "4": _fake("+"), "5": _fake("0", k_star=None, zero="Z-2")}
    e = AN.estimate(rows)
    assert e["m"] == 5 and e["p_change"]["count"] == 3 and e["p_plus"]["count"] == 2 and e["p_minus"]["count"] == 1
    assert e["p_change"]["interval"]["denominator"] == 5 and e["p_change"]["proportion"] == 3 / 5
    assert e["abs_delta"]["all"]["count"] == 5 and e["abs_delta"]["changed"]["count"] == 3 and e["abs_delta"]["changed"]["max"] == 0.5
    assert "threshold" not in json.dumps({k: v for k, v in e.items() if k != "note"})
    assert RC.compare(RC.estimate(list(rows.values())), e)[1] == []         # 区間の端点だけ、書き方の違いを 1e-9 まで許す


def test_the_descriptive_controls_report_the_required_tables() -> None:
    rows = {"10": _fake("+", q1="+", q2="0", eps="+"), "11": _fake("-", q1="-", q2="-", back="-"),
            "12": _fake("0", k_star=None, zero="Z-1"), "13": _fake("0", k_star=2), "14": _fake("0", k_star=None, zero="Z-2")}
    rows["11"]["delta_plus_delta_back"]["value"] = -0.5
    dc = AN.descriptive_controls(rows)
    assert dc["diverged"]["count"] == 3 and dc["diverged"]["counts"] == {"+": 1, "-": 1, "0": 1}
    assert dc["diverged"]["interval"]["+"]["denominator"] == 3 and dc["diverged"]["delta"]["count"] == 3
    assert dc["delta_back"]["sign_not_opposite_to_delta"] == 1 and dc["delta_back"]["max_abs_delta_plus_delta_back"] == 0.5
    assert dc["epsilon"]["counts"] == {"+": 1, "-": 0, "0": 4} and dc["epsilon"]["interval"]["+"]["denominator"] == 5
    assert dc["cross_table_q"]["cells"]["+0"] == 1 and dc["cross_table_q"]["cells"]["--"] == 1 and dc["cross_table_q"]["cells"]["00"] == 3
    assert sum(dc["cross_table_q"]["cells"].values()) == 5 and len(dc["cross_table_q"]["cells"]) == 9
    assert dc["zero_table"]["structural"] == {"Z-1": ["12"], "Z-2": ["14"]} and dc["zero_table"]["other_zero"] == ["13"]
    assert dc["zero_table"]["silent_source"] == {"source1": [], "source2": []}
    assert RC.compare(RC.controls(rows), dc)[1] == []
    swapped = {k: copy.deepcopy(v) for k, v in rows.items()}                # 札を入れ替えると 9 つの組の表は転置する
    for v in swapped.values():
        q = v["quantities"]
        q["q_1"], q["q_2"] = q["q_2"], q["q_1"]
    cells = AN.descriptive_controls(swapped)["cross_table_q"]["cells"]
    assert all(cells[a + b] == dc["cross_table_q"]["cells"][b + a] for a in AN.SIGNS for b in AN.SIGNS)


def test_clopper_pearson_known_values() -> None:
    lo, hi = AN.clopper_pearson(0, 10)
    assert lo == 0.0 and hi == pytest.approx(1 - 0.025 ** 0.1, abs=1e-9)
    lo, hi = AN.clopper_pearson(10, 10)
    assert hi == 1.0 and lo == pytest.approx(0.025 ** 0.1, abs=1e-9)
    lo, hi = AN.clopper_pearson(5, 10)
    assert lo == pytest.approx(0.187086, abs=1e-5) and hi == pytest.approx(0.812914, abs=1e-5)
    assert AN.interval(0, 0) == {"computed": False, "interval": None, "numerator": 0, "denominator": 0, "reason": "m = 0"}
    for x, n in ((0, 200), (115, 200), (37, 120)):
        assert RC.exact_interval(x, n) == pytest.approx(AN.clopper_pearson(x, n), abs=1e-9)


def test_five_numbers() -> None:
    assert AN.five_numbers([]) is None and AN.five_numbers([3])["median"] == 3
    assert AN.five_numbers([1, 2, 3, 4, 5]) == {"count": 5, "min": 1, "q1": 2.0, "median": 3.0, "q3": 4.0, "max": 5}
    assert RC.five([1, 2, 3, 4, 5]) == AN.five_numbers([1, 2, 3, 4, 5])


def test_the_first_divergences_on_hand_made_records() -> None:
    assert AN.first_divergence([[3, "a"], [5, "b"]], [[3, "a"], [6, "b"]], 1, 9) == 5
    assert AN.first_divergence([[3, "a"]], [[3, "a"]], 1, 9) is None
    la, lb = _layer(["none", "A1", "tie"]), _layer(["none", "A2", "tie"])
    assert AN.first_window_divergence(la, lb) == 2 and AN.first_window_divergence(la, la) is None
    assert AN.first_weight_divergence([[1, [1.0]], [2, [2.0]]], [[1, [1.0]], [2, [2.5]]]) == 2
    assert RC.first_split([[3, "a"], [5, "b"]], [[3, "a"], [6, "b"]], 9) == 5


def test_the_analysis_of_the_synthetic_individuals_runs_through_and_the_recheck_agrees() -> None:
    """合成の個体の解析が最後まで通る。標準のライブラリだけの独立の検算（recheck.py）が、report と一つずつ一致する。値は表示しない。"""
    runs = {s: measured(s) for s in SYN}
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=[])
    assert report["valid"] is True and set(report) == {"mode", "valid", "O1", "gate_declaration_sha256", "judgment", "estimate",
                                                       "descriptive_controls", "individuals", "auxiliary"}
    j = report["judgment"]
    assert j["J_B"]["m"] == len(SYN) and j["outcome"] in PROTOCOL["judgment"]["outcomes"] and j["J_B"]["interval"]["+"]["computed"]
    assert report["estimate"]["m"] == j["J_B"]["m"] and sum(j["J_B"]["counts"].values()) == len(SYN)
    assert set(report["auxiliary"]) == {f"R{i}" for i in range(1, 9)}
    assert report["auxiliary"]["R4"]["pair_sum_max_deviation"] <= AN.F1_TOLERANCE
    assert all(report["auxiliary"]["R5"][n]["equals_decided_of_rule_c"] is True for n in M.SYSTEMS)
    assert len(report["auxiliary"]["R4"]["boundary_delta_signs"]) == SMALL.e_windows
    result = RC.recheck(runs, json.loads(json.dumps(report)))
    assert result["mismatches"] == [] and result["checks"] > 1000


def test_the_recheck_is_independent_and_detects_a_changed_report_or_raw() -> None:
    src = (EXP / "recheck.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    modules = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} \
        | {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert modules <= {"argparse", "gzip", "hashlib", "json", "math", "statistics", "sys", "collections", "fractions", "pathlib"}
    assert "spec_from_file_location" not in src and "__import__" not in src and "exec(" not in src
    runs = {s: measured(s) for s in SYN[:4]}
    report = json.loads(json.dumps(AN.analyze_runs({s: measured(s) for s in SYN[:4]}, "synthetic", SMALL, o1=[])))
    assert RC.recheck(runs, report)["mismatches"] == []
    k = str(SYN[0])
    for tamper in (lambda rep, raw: rep["judgment"]["J_B"]["counts"].update({"+": rep["judgment"]["J_B"]["counts"]["+"] + 1}),
                   lambda rep, raw: rep["judgment"].update(outcome="plus" if rep["judgment"]["outcome"] != "plus" else "minus"),
                   lambda rep, raw: rep["estimate"]["p_change"].update(count=rep["estimate"]["p_change"]["count"] + 1),
                   lambda rep, raw: rep["individuals"][k]["quantities"]["q_1"].update(sign="?"),
                   lambda rep, raw: rep["individuals"][k].update(k_star="?"),
                   lambda rep, raw: raw[SYN[1]]["run"]["bodies"]["B_A2"]["pulse_weights"][3][1].__setitem__(0, 0.0011),
                   lambda rep, raw: raw[SYN[1]]["run"]["bodies"][M.RERUN]["layer_b"].append([9, "d", "s1", "A1"]),
                   lambda rep, raw: raw[SYN[3]]["run"]["bodies"][M.RERUN]["sigma_p_e"]["units"][
                       raw[SYN[3]]["run"]["roles"]["cue"]].update(activity=9.0),
                   lambda rep, raw: raw[SYN[2]]["run"]["bodies"]["B_A1"]["sigma_p_e"]["connections"][min(raw[SYN[2]]["run"]["W_0"])]
                   .update(weight=0.001)):
        rep, raw = copy.deepcopy(report), copy.deepcopy(runs)
        tamper(rep, raw)
        assert RC.recheck(raw, rep)["mismatches"]


# ---- CT-41-10 独立の検算：report のすべての欄 ------------------------------------------------------------------

COMMIT = "a" * 40                                                    # 照合の形だけを確かめる測定の commit（合成）


def _leaves(x, path=()):
    """report の葉（数・文字列・真偽・null と、空の列・辞書）の場所。"""
    if isinstance(x, dict) and x:
        for k, v in x.items():
            yield from _leaves(v, (*path, k))
    elif isinstance(x, list) and x:
        for i, v in enumerate(x):
            yield from _leaves(v, (*path, i))
    else:
        yield path


def _at(x, path):
    for k in path:
        x = x[k]
    return x


def _changed(v):
    """値を変える（真偽は反転、整数は ＋1、浮動小数は ＋0.25、文字列は文字を足す、null は 0、空の列・辞書は 1 つ足す）。"""
    if isinstance(v, bool):
        return not v
    if isinstance(v, int):
        return v + 1
    if isinstance(v, float):
        return v + 0.25
    if isinstance(v, str):
        return v + "~"
    if v is None:
        return 0
    return ["~"] if isinstance(v, list) else {"~": 0}


def _runs3() -> dict:
    """合成の個体（SMALL の SYN[0]・SYN[1] と k* のある個体〔重なれば 2 個体〕と、構造的な 0 の構成の 1 個体：k* と札の欄に
    値と null の両方が出る）。"""
    return {SYN[0]: measured(SYN[0]), SYN[1]: measured(SYN[1]), decided_seed(): measured(decided_seed()),
            CORNER_SEEDS[0]: zero_individual()}


@functools.cache
def _analyzed() -> str:
    """合成の個体（_runs3）の解析の report（解析の main と同じく measurement_commit を書き足した形。JSON を通す）。"""
    return json.dumps(AN.analyze_runs(_runs3(), "synthetic", SMALL, o1=[]) | {"measurement_commit": COMMIT})


def test_the_recheck_rebuilds_the_whole_report_and_compares_every_field() -> None:
    """raw から report の全体を組み立て直し、すべての葉を照合する。report のどの葉の値を変えても、どの欄を消しても足しても、
    照合が失敗する（合成の個体の値は表示しない。失敗の文は場所だけ）。"""
    runs = _runs3()
    report = json.loads(_analyzed())
    mine = RC.expected_report(runs, COMMIT)
    checks, found = RC.compare(mine, report)
    paths = list(_leaves(report))
    scalars = [p for p in paths if not isinstance(_at(report, p), (dict, list))]
    assert found == [] and checks == len(scalars) > 1000                     # すべての葉を比べている
    assert {p[0] for p in paths} == set(report) == {"mode", "valid", "O1", "gate_declaration_sha256", "judgment", "estimate",
                                                    "descriptive_controls", "individuals", "auxiliary", "measurement_commit"}
    for p in paths:
        parent = _at(report, p[:-1])
        before = parent[p[-1]]
        parent[p[-1]] = _changed(before)
        assert RC.compare(mine, report)[1], p
        parent[p[-1]] = before
    nodes = {q[:i] for q in paths for i in range(len(q)) if isinstance(_at(report, q[:i]), dict)}
    for p in nodes:
        node = _at(report, p)
        for key in list(node):
            value = node.pop(key)
            assert RC.compare(mine, report)[1], (p, key)
            node[key] = value
        node["~"] = 0
        assert RC.compare(mine, report)[1], p
        del node["~"]
    assert RC.compare(mine, report) == (checks, [])


def test_the_comparison_tolerates_only_the_two_independently_written_numbers() -> None:
    """ちょうど同じであることを求めない欄は、Clopper–Pearson の端点と E_S だけ（計算の書き方が解析と違う）。"""
    assert RC._loose("report.judgment.J_B.interval.+.interval[0]") and RC._loose("report.auxiliary.R1.S1.E_S")
    assert not RC._loose("report.estimate.p_change.proportion") and not RC._loose("report.individuals.34301.birth.cue.margin_g")
    assert not RC._loose("report.individuals.34301.quantities.delta.value")
    report = json.loads(_analyzed())
    mine = RC.expected_report(_runs3(), COMMIT)
    margin = report["individuals"][str(SYN[0])]["birth"]["cue"]
    margin["margin_g"] += 1e-12                                              # 書き方の同じ数は、わずかな違いも見つける
    assert RC.compare(mine, report)[1] == [f"report.individuals.{SYN[0]}.birth.cue.margin_g"]
    margin["margin_g"] -= 1e-12
    report["valid"] = 1                                                      # 真偽と数を取り違えない
    assert RC.compare(mine, report)[1] == ["report.valid"]


TARGETS = [("judgment", "J_B", "tail_probability"), ("estimate", "p_change", "proportion"), ("estimate", "abs_delta"),
           ("descriptive_controls", "diverged"), ("descriptive_controls", "delta_back"), ("descriptive_controls", "epsilon"),
           ("descriptive_controls", "cross_table_q"), ("descriptive_controls", "zero_table"),
           ("auxiliary", "R1", "k_star"), ("auxiliary", "R1", "S1", "E_S"), ("auxiliary", "R2"), ("auxiliary", "R3"),
           ("auxiliary", "R4", "P_E_weights"), ("auxiliary", "R4", "differences_B_A1_minus_B_A2"),
           ("auxiliary", "R4", "boundary_delta_signs"), ("auxiliary", "R4", "boundary_weights"), ("auxiliary", "R5"),
           ("auxiliary", "R6"), ("auxiliary", "R7"), ("auxiliary", "R8"),
           ("individuals", None, "quantities"), ("individuals", None, "delta_plus_delta_back"), ("individuals", None, "weights_P_E"),
           ("individuals", None, "weight_differences"), ("individuals", None, "pair_sum_max_deviation"),
           ("individuals", None, "boundaries"), ("individuals", None, "consequences"), ("individuals", None, "first_divergence"),
           ("individuals", None, "firing_E"), ("individuals", None, "birth"), ("individuals", None, "roles"),
           ("individuals", None, "counts_E"), ("individuals", None, "S1"), ("mode",), ("O1",), ("gate_declaration_sha256",),
           ("measurement_commit",)]


@pytest.mark.parametrize("target", TARGETS, ids=lambda t: ".".join(str(x) for x in t if x))
def test_the_recheck_fails_when_any_field_is_changed(target) -> None:
    """report のどの欄（E_B の割合、必ず報告する記述、R1〜R8、個体の量・重み・境界・発火など）を変えても、recheck が失敗する。"""
    runs = _runs3()
    report = json.loads(_analyzed())
    assert RC.recheck(runs, report, COMMIT)["mismatches"] == []
    prefix = tuple(str(decided_seed()) if k is None else k for k in target)
    path = prefix + next(_leaves(_at(report, prefix)))
    parent = _at(report, path[:-1])
    parent[path[-1]] = _changed(parent[path[-1]])
    found = RC.recheck(runs, report, COMMIT)["mismatches"]
    assert found and all(m.startswith("report.") for m in found)


def test_a_raw_change_that_no_operation_check_sees_still_fails_the_report_comparison() -> None:
    runs = _runs3()
    report = json.loads(_analyzed())
    roles = runs[SYN[0]]["run"]["roles"]
    runs[SYN[0]]["run"]["birth_units"][roles["cue"]]["dynamics"]["threshold"] += 0.001
    found = RC.recheck(runs, report, COMMIT)["mismatches"]
    assert f"report.individuals.{SYN[0]}.birth.cue.threshold" in found and all(m.startswith("report.") for m in found)


def test_the_recheck_operation_checks_find_tampering_by_another_writing() -> None:
    s = decided_seed()
    assert RC.operation_problems(measured(s)) == [] and RC.operation_problems(zero_individual()) == []
    for tamper in (lambda r: r["bodies"]["B_A1"]["layer_b"].pop(),
                   lambda r: r["bodies"]["B_A2"]["world_end"]["reserved"].append([99, "consequence", "x", 5, "d"]),
                   lambda r: r["bodies"]["B_A1"]["pulse_weights"][2][1].__setitem__(0, 0.5),
                   lambda r: r["bodies"][M.RERUN]["activity"].pop(),
                   lambda r: r["bodies"]["B_A2"]["sigma_p_e"]["exit"].update(cursor=0),
                   lambda r: r["bodies"]["B_A2"]["first_intent"]["sigma"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["bodies"]["B_A2"]["sigma_0"]["units"][r["roles"]["cue"]].update(activity=9.0)):
        data = measured(s)
        tamper(data["run"])
        assert RC.operation_problems(data)


# ---- CT-41-9 protocol の写しと、確定済みの事前登録の結び付き ------------------------------------------------

def _drop(meta: dict, key: str) -> None:
    del meta[key]


def _alter_protocol(path: tuple, value):
    def edit(meta: dict) -> None:
        node = meta["protocol"]
        for k in path[:-1]:
            node = node[k]
        node[path[-1]] = value
    return edit


PROTOCOL_TAMPERS = {
    "no_protocol": lambda m: _drop(m, "protocol"),
    "no_sha256": lambda m: _drop(m, "protocol_sha256"),
    "sha256_changed": lambda m: m.update(protocol_sha256="0" * 64),
    "alpha_changed": _alter_protocol(("judgment", "J_B", "alpha", "per_direction"), 0.05),
    "m_changed": _alter_protocol(("judgment", "J_B", "m"), 199),
    "k2_changed": _alter_protocol(("judgment", "J_B", "k2_200"), 114),
    "seeds_changed": _alter_protocol(("seeds", "last"), 34250),
    "timeline_changed": _alter_protocol(("timeline", "boundary_P_E"), 1064),
    "respond_changed": _alter_protocol(("world", "respond"), False),
    "rule_c_changed": _alter_protocol(("world", "rule_c", "B_A1_rerun"), "A2"),
    # 以下は PREREGISTERED で個別に照らさない欄。写しの中身全体のハッシュで見つける
    "J_B_rule_changed": _alter_protocol(("judgment", "J_B", "rule"), "plus if count(plus) > m / 2"),
    "negative_reading_changed": _alter_protocol(("judgment", "negative_reading"), "a configuration limit"),
    "delta_redefined": _alter_protocol(("quantities", "delta"), "a_1^A1 - a_1^A2"),
    "population_changed": _alter_protocol(("judgment", "per_individual", "structural_zero"), "excluded"),
    "operation_check_dropped": _alter_protocol(("operation_checks",), ["O1", "O2", "O3"]),
}
UNCOMPARED = ("J_B_rule_changed", "negative_reading_changed", "delta_redefined", "population_changed", "operation_check_dropped")


def test_the_preregistered_values_in_the_recheck_are_the_protocol_values() -> None:
    """recheck.py が書き起こした値（PREREGISTERED）が、確定済みの protocol.yaml の値と同じ。正本の写しは結び付きを通る。"""
    pr, jb, tl, br = RC.PREREGISTERED, PROTOCOL["judgment"]["J_B"], PROTOCOL["timeline"], PROTOCOL["brain"]
    assert pr["experiment"] == PROTOCOL["experiment"] and pr["kind"] == PROTOCOL["kind"]
    assert pr["alpha_per_direction"] == Fraction(str(jb["alpha"]["per_direction"])) == Fraction(1, 40)
    assert pr["alpha_two_sided"] == Fraction(str(jb["alpha"]["two_sided"]))
    assert (pr["m"], pr["k2_200"]) == (jb["m"], jb["k2_200"])
    assert (pr["experience_windows"], pr["experience_pulses"], pr["boundary_P_E"], pr["runs_to"]) == \
        (tl["experience_E"]["windows"], tl["experience_E"]["pulses"], tl["boundary_P_E"], tl["runs_to"])
    assert (pr["w_min"], pr["w_max"], pr["w0"]) == (br["w_min"], br["w_max"], br["initial_weight_w0"])
    assert pr["f1_tolerance"] == AN.F1_TOLERANCE
    assert pr["respond"] is PROTOCOL["world"]["respond"] is True and pr["rule_c"] == PROTOCOL["world"]["rule_c"]
    assert pr["per_individual"] == PROTOCOL["bodies"]["per_individual"]
    assert all(pr[k] == PROTOCOL[k] for k in ("seeds", "smoke_seeds", "synthetic_seeds"))
    assert pr["formal_plan"] == dataclasses.asdict(FORMAL)
    assert RC.PROTOCOL_FILE == EXP / "protocol.yaml"
    assert RC._preregistered_values(json.loads(json.dumps(PROTOCOL))) == []
    assert RC.protocol_problems({s: measured(s) for s in SYN[:2]}) == []
    gate = PROTOCOL["inherited_gate_set"]
    assert (RC.GATE_FILE, RC.GATE_SHA256) == (gate["declaration"], gate["sha256"]) and RC.GATE_SHA256 == AN.GATE_SHA256
    assert RC.gate_problems({s: measured(s) for s in SYN[:2]}) == [] and RC.REPO_ROOT == ROOT
    # 書き起こした名前・組が、道具と同じ（照合の相手を取り違えない）
    assert (RC.START, RC.FINISH, RC.RAW, RC.SEEDS_DIR) == (R.G.START, R.G.FINISH, R.G.RAW, R.G.SEEDS_DIR)
    assert (RC.REPORT, RC.O1_FILE, RC.O1_KEYS, RC.CONTRACT_TESTS) == (AN.REPORT, AN.O1_FILE, AN.O1_KEYS, AN.CONTRACT_TESTS)
    assert (RC.BODIES, RC.OBSERVED, RC.RERUN, RC.RULE_OF) == (list(M.SYSTEMS), list(M.BODIES), M.RERUN, M.RULE_OF)
    assert (RC.ROLES6, list(RC.NAMES), RC.NOTES) == (AN.ROLES6, list(AN.QUANTITIES), AN.NOTES)


def test_the_recheck_holds_the_fixed_hashes_of_the_preregistered_protocol() -> None:
    """recheck.py の固定のハッシュが、事前登録 v0.1 の protocol.yaml（このリポジトリの正本）から計算し直した値と同じ。"""
    stored = json.loads(json.dumps(PROTOCOL))                               # raw の meta と同じ形
    assert RC.canonical_protocol_sha256(stored) == RC.PROTOCOL_JSON_SHA256
    assert hashlib.sha256((EXP / "protocol.yaml").read_bytes()).hexdigest() == RC.PROTOCOL_FILE_SHA256 == AN.PROTOCOL_SHA256
    canonical = json.dumps(stored, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == RC.PROTOCOL_JSON_SHA256   # 正規化の仕方を独立に書き直しても同じ
    assert RC.PROTOCOL_JSON_SHA256 == "dd377cd1700d24f7c4b9f850d1c78907e07b0b712e2e34fc6901cbe697d59fc5"     # v0.1
    assert RC.PROTOCOL_FILE_SHA256 == "cdb09a2b9b90318ceea254c6ebbdcbd1a5404a3736c82d326ac3a9a7d10446c4"


@pytest.mark.parametrize("tamper", UNCOMPARED)
def test_the_value_comparison_alone_misses_these_fields_but_the_content_hash_does_not(tamper) -> None:
    proto = json.loads(json.dumps(PROTOCOL))
    PROTOCOL_TAMPERS[tamper]({"protocol": proto})
    assert RC._preregistered_values(proto) == []
    assert RC.canonical_protocol_sha256(proto) != RC.PROTOCOL_JSON_SHA256


@pytest.mark.parametrize("tamper", sorted(PROTOCOL_TAMPERS))
def test_the_analysis_requires_the_stored_protocol_to_be_the_preregistered_one(tamper) -> None:
    good = measured(SYN[0])
    assert AN.check_seed(good, "synthetic", SYN[0], SMALL)["structure"] == []
    bad = copy.deepcopy(good)
    PROTOCOL_TAMPERS[tamper](bad["meta"])
    assert AN.check_seed(bad, "synthetic", SYN[0], SMALL)["structure"]
    report = AN.analyze_runs({SYN[0]: bad, SYN[1]: measured(SYN[1])}, "synthetic", SMALL, o1=[])
    assert report["valid"] is False and report["judgment"] is None and report["estimate"] is None


@pytest.mark.parametrize("tamper", sorted(PROTOCOL_TAMPERS))
def test_a_blinded_record_with_a_wrong_protocol_fails_every_check(tamper) -> None:
    s = SYN[0]
    data = measured(s)
    data["meta"]["blind"] = True
    record = R.blinded(data, "synthetic", s, SMALL)
    record["meta"]["mode"] = "smoke"
    before = AN.check_blinded(record, s, "smoke")
    assert before["structure"] == "ok" and before["O11"] == "fail"           # 形は通る（O11 は合成の seed なので fail）
    PROTOCOL_TAMPERS[tamper](record["meta"])
    assert AN.check_blinded(record, s, "smoke") == {k: "fail" for k in AN.CHECK_NAMES}


@pytest.mark.parametrize("tamper", sorted(PROTOCOL_TAMPERS))
@pytest.mark.parametrize("everyone", [False, True])
def test_the_recheck_binds_every_stored_protocol_to_the_preregistered_one(tamper, everyone) -> None:
    runs = {s: measured(s) for s in SYN[:3]}
    report = json.loads(json.dumps(AN.analyze_runs(runs, "synthetic", SMALL, o1=[])))
    assert RC.recheck(copy.deepcopy(runs), report)["mismatches"] == []
    bad = copy.deepcopy(runs)
    for s in (SYN[:3] if everyone else SYN[1:2]):
        PROTOCOL_TAMPERS[tamper](bad[s]["meta"])
    found = RC.recheck(bad, report)["mismatches"]
    assert found and any("protocol" in m for m in found)


def test_the_recheck_checks_the_formal_plan_and_the_start_records(repo, tmp_path, monkeypatch) -> None:
    runs = {s: measured(s) for s in SYN[:2]}
    runs[SYN[0]]["meta"]["mode"] = "formal"                                  # 本番なのに Plan が小さい
    assert any("本番の Plan" in m for m in RC.protocol_problems(runs))
    other = tmp_path / "other.yaml"
    other.write_text((EXP / "protocol.yaml").read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    found = RC.protocol_problems({s: measured(s) for s in SYN[:2]}, other)
    assert any("照らす protocol.yaml" in m for m in found) and any("SHA-256" in m for m in found)
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    _exec(repo, out, SYN[:2], runner=functools.partial(M.measure_seed, PROTOCOL, plan=SMALL))
    _complete(out, SYN[:2])
    assert RC.recheck_directory(out)["mismatches"] == []
    start = R.G.seed_dir(out, SYN[1]) / R.G.START
    start.write_text(json.dumps(json.loads(start.read_text(encoding="utf-8")) | {"protocol_sha256": "1" * 64}), encoding="utf-8")
    assert any("開始の記録" in m for m in RC.recheck_directory(out)["mismatches"])


# ---- CT-41-10 独立の検算：測定の来歴と全件性 ------------------------------------------------------------------

DIR_SEEDS = SYN[:3]


def _o1_record(commit: str) -> dict:
    """run.py の record_contract_tests が書く O1 の記録と同じ形（テストのファイルの SHA-256 は、このリポジトリのもの）。"""
    return {"measurement_commit": commit, "command": ["python", "-m", "pytest", "-q", *AN.CONTRACT_TESTS], "exit_code": 0,
            "summary": "801 passed in 250.00s", "test_files_sha256": {f: R.G.sha256_file(ROOT / f) for f in AN.CONTRACT_TESTS},
            "at": "2026-01-01T00:00:00+00:00"}


def _complete(out: Path, seeds: list[int], plan: M.Plan = SMALL) -> dict:
    """解析の main と同じ形の report（measurement_commit を書き足す）と、O1 の記録を出力先に書く。書いた report を返す。"""
    commit = AN.verify_records(out, "synthetic", seeds)["measurement_commit"]
    runs = {s: AN.read_raw(R.G.seed_dir(out, s) / R.G.RAW) for s in seeds}
    report = json.loads(json.dumps(AN.analyze_runs(runs, "synthetic", plan, o1=[]) | {"measurement_commit": commit}))
    (out / AN.REPORT).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / AN.O1_FILE).write_text(json.dumps(_o1_record(commit), ensure_ascii=False, indent=1), encoding="utf-8")
    return report


@pytest.fixture(scope="module")
def finished_out(tmp_path_factory) -> Path:
    """合成の 3 個体を run.py の一度限りの実行で測り、解析の report と O1 の記録を書いた出力先（テストごとに写して使う）。"""
    base = tmp_path_factory.mktemp("finished")
    repo = _make_repo(base / "repo")
    out = base / "out"
    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(ROOT)
        mp.setattr(R, "REPO", repo)
        _exec(repo, out, DIR_SEEDS, runner=functools.partial(M.measure_seed, PROTOCOL, plan=SMALL))
        _complete(out, DIR_SEEDS)
    return out


@pytest.fixture
def done(finished_out, tmp_path) -> Path:
    dst = tmp_path / "out"
    shutil.copytree(finished_out, dst, ignore=shutil.ignore_patterns(R.G.LOCK))
    return dst


def _json_edit(path: Path, edit) -> None:
    rec = json.loads(path.read_text(encoding="utf-8"))
    edit(rec)
    path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")


def _rewrite_raw(out: Path, seed: int, edit=None, data: dict | None = None) -> None:
    """raw を書き換え、終了の記録の SHA-256・バイト数も合わせる（guard の状態の確かめでは見つからない改変）。"""
    d = R.G.seed_dir(out, seed)
    if data is None:
        data = AN.read_raw(d / R.G.RAW)
        edit(data)
    payload = gzip.compress(json.dumps(data, separators=(",", ":")).encode("utf-8"), mtime=0)
    (d / R.G.RAW).write_bytes(payload)
    _json_edit(d / R.G.FINISH, lambda f: f.update(raw_file_sha256=hashlib.sha256(payload).hexdigest(), raw_file_bytes=len(payload)))


def _seed_file(seed: int, name: str):
    return lambda out: R.G.seed_dir(out, seed) / name


def _edit_seed_file(seed: int, name: str, edit):
    return lambda out: _json_edit(R.G.seed_dir(out, seed) / name, edit)


_A, _B, _C = DIR_SEEDS
DIRECTORY_TAMPERS = {
    # 終了の記録と raw
    "finish_raw_sha256": _edit_seed_file(_B, R.G.FINISH, lambda f: f.update(raw_file_sha256="0" * 64)),
    "finish_raw_bytes": _edit_seed_file(_B, R.G.FINISH, lambda f: f.update(raw_file_bytes=f["raw_file_bytes"] + 1)),
    "finish_status_failed": _edit_seed_file(_B, R.G.FINISH, lambda f: f.update(status="failed")),
    "finish_commit_end": _edit_seed_file(_B, R.G.FINISH, lambda f: f.update(measurement_commit_end="0" * 40)),
    "finish_seed": _edit_seed_file(_B, R.G.FINISH, lambda f: f.update(seed=_C)),
    # 開始の記録
    "start_commit": _edit_seed_file(_B, R.G.START, lambda f: f.update(measurement_commit="0" * 40)),
    "start_protocol_sha256": _edit_seed_file(_B, R.G.START, lambda f: f.update(protocol_sha256="1" * 64)),
    "start_mode": _edit_seed_file(_B, R.G.START, lambda f: f.update(mode="formal")),
    "start_seed": _edit_seed_file(_B, R.G.START, lambda f: f.update(seed=_C)),
    # raw の中身（終了の記録の SHA-256・バイト数は合わせる）
    "raw_meta_commit": lambda o: _rewrite_raw(o, _B, lambda d: d["meta"].update(measurement_commit="0" * 40)),
    "raw_meta_protocol_sha256": lambda o: _rewrite_raw(o, _B, lambda d: d["meta"].update(protocol_sha256="1" * 64)),
    "raw_meta_mode": lambda o: _rewrite_raw(o, _B, lambda d: d["meta"].update(mode="formal")),
    "raw_meta_gate_sha256": lambda o: _rewrite_raw(o, _B, lambda d: d["meta"]["gate"].update(sha256="2" * 64)),
    "raw_meta_gate_declaration": lambda o: _rewrite_raw(o, _B, lambda d: d["meta"]["gate"]["declaration"].update({"~": 1})),
    "raw_of_another_seed": lambda o: _rewrite_raw(o, _A, data=AN.read_raw(R.G.seed_dir(o, _B) / R.G.RAW)),
    "raw_weight_changed": lambda o: _rewrite_raw(o, _C, lambda d: d["run"]["bodies"]["B_A1"]["pulse_weights"][0][1].__setitem__(
        0, 0.0049)),
    # フォルダ
    "renamed_folder": lambda o: R.G.seed_dir(o, _B).rename(R.G.seed_dir(o, 34309)),
    "leading_zero_folder": lambda o: R.G.seed_dir(o, _B).rename(o / R.G.SEEDS_DIR / f"0{_B}"),
    "stray_entry": lambda o: (o / R.G.SEEDS_DIR / "notes.txt").write_text("x", encoding="utf-8"),
    "extra_file_in_a_seed": lambda o: (R.G.seed_dir(o, _A) / "raw.json.gz.tmp").write_bytes(b""),
    "missing_start": lambda o: _seed_file(_A, R.G.START)(o).unlink(),
    "missing_finish": lambda o: _seed_file(_A, R.G.FINISH)(o).unlink(),
    "missing_raw": lambda o: _seed_file(_A, R.G.RAW)(o).unlink(),
    "missing_seed": lambda o: shutil.rmtree(R.G.seed_dir(o, _C)),
    # report
    "report_commit": lambda o: _json_edit(o / AN.REPORT, lambda r: r.update(measurement_commit="0" * 40)),
    "report_without_commit": lambda o: _json_edit(o / AN.REPORT, lambda r: r.pop("measurement_commit")),
    "report_mode": lambda o: _json_edit(o / AN.REPORT, lambda r: r.update(mode="formal")),
    "report_missing": lambda o: (o / AN.REPORT).unlink(),
    # O1 の記録
    "o1_missing": lambda o: (o / AN.O1_FILE).unlink(),
    "o1_exit_code": lambda o: _json_edit(o / AN.O1_FILE, lambda r: r.update(exit_code=1)),
    "o1_commit": lambda o: _json_edit(o / AN.O1_FILE, lambda r: r.update(measurement_commit="0" * 40)),
    "o1_summary": lambda o: _json_edit(o / AN.O1_FILE, lambda r: r.update(summary="1 failed, 800 passed in 250.00s")),
    "o1_command": lambda o: _json_edit(o / AN.O1_FILE, lambda r: r.update(command=r["command"][:-1])),
    "o1_test_file": lambda o: _json_edit(o / AN.O1_FILE, lambda r: r["test_files_sha256"].update({AN.CONTRACT_TESTS[4]: "0" * 64})),
    "o1_extra_field": lambda o: _json_edit(o / AN.O1_FILE, lambda r: r.update(note="x")),
}


def test_the_recheck_of_a_finished_output_checks_its_provenance_and_agrees(done) -> None:
    result = RC.recheck_directory(done)
    assert result["mismatches"] == [] and result["individuals"] == len(DIR_SEEDS)
    commit = AN.verify_records(done, "synthetic", DIR_SEEDS)["measurement_commit"]
    assert result["provenance"] == {"mode": "synthetic", "measurement_commit": commit, "seeds": len(DIR_SEEDS)}
    assert set(result["sha256"]) == {f"seeds/{s}/raw.json.gz" for s in DIR_SEEDS} | {"report.json"}


@pytest.mark.parametrize("tamper", sorted(DIRECTORY_TAMPERS))
def test_the_recheck_verifies_the_provenance_and_completeness_itself(done, tamper) -> None:
    """guard・解析の道具の確かめに頼らず、開始・終了の記録・raw・フォルダ・report・O1 の記録の結び付きを、独立の検算が確かめる。"""
    assert RC.recheck_directory(done)["mismatches"] == []
    DIRECTORY_TAMPERS[tamper](done)
    assert RC.recheck_directory(done)["mismatches"]


def test_the_seed_set_of_the_formal_run_is_exactly_the_preregistered_200() -> None:
    formal = list(range(34001, 34201))
    assert RC.seed_set_problems("formal", formal) == []
    assert RC.seed_set_problems("formal", formal[:57] + formal[58:])                 # 欠け
    assert RC.seed_set_problems("formal", formal + [34201])                           # 範囲の外（smoke の seed）
    assert RC.seed_set_problems("formal", formal + [34001])                           # 重複
    assert RC.seed_set_problems("formal", [*formal[:-1], 33200])                       # 0040 の seed（欠けと範囲の外）
    assert RC.seed_set_problems("synthetic", SYN) == []
    assert RC.seed_set_problems("synthetic", [34001]) and RC.seed_set_problems("synthetic", [])
    assert RC.seed_set_problems("smoke", [34201]) and RC.seed_set_problems(None, SYN)
    assert (RC.PREREGISTERED["seeds"], RC.PREREGISTERED["synthetic_seeds"]) == (PROTOCOL["seeds"], PROTOCOL["synthetic_seeds"])


def test_a_formal_output_must_hold_exactly_the_200_preregistered_seeds(done) -> None:
    """mode を本番に揃えて書き換えた 3 個体の出力先は、seed の欠け・範囲の外と Plan で、独立の検算が失敗する。"""
    for s in DIR_SEEDS:
        for name in (R.G.START, R.G.FINISH):
            _json_edit(R.G.seed_dir(done, s) / name, lambda r: r.update(mode="formal"))
        _rewrite_raw(done, s, lambda d: d["meta"].update(mode="formal"))
    _json_edit(done / AN.REPORT, lambda r: r.update(mode="formal"))
    found = RC.recheck_directory(done)["mismatches"]
    assert any("欠け" in m for m in found) and any("範囲の外" in m for m in found) and any("本番の Plan" in m for m in found)


@pytest.mark.parametrize("edit", [lambda d: d["meta"].update(measurement_commit="0" * 40),
                                  lambda d: d["meta"].update(protocol_sha256="1" * 64),
                                  lambda d: d["meta"].update(seed=_C),
                                  lambda d: d["meta"].update(mode="formal")], ids=["commit", "protocol_sha256", "seed", "mode"])
def test_the_analysis_binds_the_raw_meta_to_the_start_and_finish_records(done, edit) -> None:
    """解析側も、raw の meta の測定の commit・protocol の SHA-256・seed・mode を、開始・終了の記録と直接照らす。"""
    def runs() -> dict:
        return {s: AN.read_raw(R.G.seed_dir(done, s) / R.G.RAW) for s in DIR_SEEDS}
    assert AN.provenance_problems(done, runs(), "synthetic") == []
    _rewrite_raw(done, _B, edit)
    assert AN.verify_records(done, "synthetic", DIR_SEEDS)["state"] == "complete"     # 開始・終了の記録だけでは見つからない
    assert AN.provenance_problems(done, runs(), "synthetic")
    assert RC.recheck_directory(done)["mismatches"]


def test_the_analysis_main_checks_the_provenance_before_the_report() -> None:
    src = inspect.getsource(AN.main)
    assert "provenance = provenance_problems(out, runs, mode)" in src
    assert src.index("provenance_problems(out, runs, mode)") < src.index("analyze_runs(runs, mode, o1=o1)")
    assert 'records["state"], records["problems"] = "failed"' in src                # 違えば invalid（判定・推定を出さない）


def test_an_invalid_individual_or_a_failed_o1_blocks_the_judgment_and_the_estimate() -> None:
    runs = {s: measured(s) for s in SYN[:2]}
    runs[SYN[1]]["run"]["bodies"]["B_A1"]["pulse_weights"][0][1][0] = 0.0111
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=[])
    assert report["valid"] is False and report["judgment"] is None and report["estimate"] is None and "individuals" not in report
    assert list(report["failed_checks"]) == [str(SYN[1])] and "O6" in report["failed_checks"][str(SYN[1])]
    report = AN.analyze_runs({SYN[0]: measured(SYN[0])}, "synthetic", SMALL, o1=["x"])
    assert report["valid"] is False and report["judgment"] is None and report["O1"]["status"] == "fail"


# ---- 操作の確認が、記録の食い違いを見つける（structure・O2・O3・O10・O11） ---------------------------------

def test_structure_detects_extra_fields_and_wrong_roles() -> None:
    s = SYN[0]
    for tamper in (lambda d: d["run"].update(judgment={}), lambda d: d.update(extra=1),
                   lambda d: d["run"]["bodies"]["B_A1"].update(delta=0.5), lambda d: d["run"]["bodies"].pop("B_A1_rerun"),
                   lambda d: d["run"]["roles"].update(cue=d["run"]["roles"]["source1"]),
                   lambda d: d["run"]["W_0"].update({min(d["run"]["W_0"]): 0.004}),
                   lambda d: d["run"].update(seed=s + 1), lambda d: d["meta"].update(manifest={}),
                   lambda d: d["run"]["plan"].update(e_windows=3),
                   lambda d: d["run"]["bodies"]["B_A1_rerun"].update(pulse_weights=[]),
                   lambda d: d["run"]["bodies"]["B_A2"].pop("first_intent"),
                   lambda d: d["run"]["bodies"]["B_A2"]["audit"].pop("ok")):
        data = measured(s)
        tamper(data)
        assert "structure" in failures(data, s)


def test_o2_detects_a_different_gate_set_or_world() -> None:
    s = SYN[0]
    for tamper in (lambda d: d["meta"]["gate"].update(sha256="0" * 64),
                   lambda d: d["meta"]["gate"]["declaration"]["schedule"].update(window_length_W=18),
                   lambda d: d["meta"].pop("gate"),
                   lambda d: d["run"]["bodies"]["B_A2"]["world_end"]["rule"].update(delay=3),
                   lambda d: d["run"]["bodies"]["B_A1"]["world_end"]["rule"].update(rule_c="A2"),
                   lambda d: d["run"]["bodies"][M.RERUN]["world_end"]["rule"].update(respond=False),
                   lambda d: d["run"]["bodies"]["B_A1"]["layer_a"][2].update(close=d["run"]["bodies"]["B_A1"]["layer_a"][2]["close"] + 1),
                   lambda d: d["run"]["bodies"]["B_A1"]["world_end"]["reserved"][0].__setitem__(3, 40),
                   lambda d: d["run"]["bodies"][M.RERUN].update(pulse_end=SMALL.p_e - 1),
                   lambda d: d["run"]["bodies"]["B_A2"]["sigma_0"]["exit"]["windows"][0].__setitem__(2, 60),
                   lambda d: d["run"]["bodies"]["B_A1"]["sigma_p_e"].update(exit=None),
                   lambda d: d["run"]["steps"].pop(),
                   lambda d: d["run"]["steps"][4].__setitem__(3, "advance_to")):
        data = measured(s)
        tamper(data)
        assert "O2" in failures(data, s)
    formal = measured(s)
    formal["meta"]["mode"] = "formal"
    assert AN.check_seed(formal, "formal", s, SMALL)["structure"]            # 本番では小さい Plan を使えない


def test_o3_detects_a_broken_audit() -> None:
    s = decided_seed()
    for tamper in (lambda r: r["bodies"]["B_A1"]["layer_b"].append([9, "d-x", r["roles"]["source1"], "A1"]),
                   lambda r: r["bodies"]["B_A1"]["layer_b"].pop(),
                   lambda r: r["bodies"]["B_A2"]["layer_a"].pop(),
                   lambda r: r["bodies"]["B_A1"]["delta_log"].pop(),
                   lambda r: r["bodies"][M.RERUN]["audit"].update(ok=False),
                   lambda r: r["bodies"]["B_A2"]["audit"].update(carried_over_windows=[4]),
                   lambda r: next(x for x in r["bodies"]["B_A1"]["layer_a"] if x["emitted"]).update(emitted=False)):
        data = measured(s)
        tamper(data["run"])
        assert "O3" in failures(data, s)
    data = measured(s)
    lb = data["run"]["bodies"]["B_A1"]["layer_b"]
    if len(lb) >= 2:
        lb[1][1] = lb[0][1]                                                    # Delta の識別子の重複
        assert "O3" in failures(data, s)


def test_o10_detects_inconsistent_layer_a_fields_and_quantities() -> None:
    s = decided_seed()

    def decided(r, n="B_A1"):
        return next(x for x in r["bodies"][n]["layer_a"] if x["outcome"] in A.ACTION_IDS)
    for tamper in (lambda r: decided(r).update(outcome="A2" if decided(r)["outcome"] == "A1" else "A1"),
                   lambda r: decided(r).update(emit_pulse=decided(r)["emit_pulse"] + 1),
                   lambda r: decided(r).update(decision_pulse=decided(r)["open"] - 1),
                   lambda r: decided(r).update(winner_unit=r["roles"]["cue"]),
                   lambda r: r["bodies"][M.RERUN]["layer_a"][0].update(outcome="other"),
                   lambda r: r["bodies"]["B_A2"]["layer_a"][1].update(open=1),
                   lambda r: r["bodies"]["B_A2"]["sigma_p_e"]["connections"][min(r["W_0"])].update(
                       weight=r["bodies"]["B_A2"]["sigma_p_e"]["connections"][min(r["W_0"])]["weight"] + 2 ** -40)):
        data = measured(s)
        tamper(data["run"])
        assert "O10" in failures(data, s)
    zero = zero_individual()
    cid = AN.role_cids(zero["run"]["roles"])["C_to_source1"]
    for n in ("B_A2",):                                                         # 構造的な 0 なのに量が 0 でない
        zero["run"]["bodies"][n]["sigma_p_e"]["connections"][cid]["weight"] += 2 ** -40
    assert "O10" in failures(zero, CORNER_SEEDS[0])
    problems = AN.layer_a_problems([{"window": 1, "open": 3, "close": 5, "outcome": "tie", "decision_pulse": 4, "winner_unit": "s1",
                                     "action": None, "emit_pulse": None, "emitted": False}], [(1, 3, 5)],
                                   {"source1": "s1", "source2": "s2"})
    assert problems == ["窓 1：結末と記録の欄が合わない"]


def test_o11_rejects_seeds_outside_the_range_or_seen() -> None:
    assert AN.check_seed(measured(SYN[0]), "synthetic", SYN[0], SMALL)["O11"] == []
    for seed in (31001, 32001, 32301, 30201, 33001, 33301, 34001):
        out: list[str] = []
        AN._o11(seed, "synthetic", out)
        assert out
    out = []
    AN._o11(33001, "formal", out)
    assert len(out) == 2                                                       # 範囲の外で、かつ 0040 で走らせた seed


def test_meta_blind_must_match_the_mode() -> None:
    s = SYN[0]
    data = measured(s)
    data["meta"]["blind"] = "no"
    assert "structure" in failures(data, s)
    assert AN.check_seed(dict(measured(s), meta=dict(measured(s)["meta"], blind=True)), "formal", s, SMALL)["structure"]


# ---- CT-41-9 一度限りの実行（guard と run.execute。dummy の計算。0040 と同じ） ------------------------------------

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


def _make_repo(r: Path) -> Path:
    (r / EXP.relative_to(ROOT)).mkdir(parents=True)
    (r / EXP.relative_to(ROOT) / "protocol.yaml").write_bytes((EXP / "protocol.yaml").read_bytes())
    _git(r, "init", "-q")
    for k, v in (("user.email", "t@example.invalid"), ("user.name", "t"), ("commit.gpgsign", "false")):
        _git(r, "config", k, v)
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "init")
    return r


@pytest.fixture
def repo(tmp_path) -> Path:
    return _make_repo(tmp_path / "repo")


def _dummy(seed: int) -> dict:
    return {"seed": seed, "dummy": True}


def _exec(repo, out, seeds, runner=_dummy):
    return R.execute("synthetic", seeds, out, repo, _git(repo, "rev-parse", "HEAD"), runner=runner,
                     executor_factory=SerialExecutor)


def test_each_seed_runs_once_and_a_failure_stops_the_rest(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    assert _exec(repo, out, GUARD_SEEDS[:2])["completed"] == GUARD_SEEDS[:2]
    with pytest.raises(R.G.GuardError):
        _exec(repo, out, GUARD_SEEDS[:1])

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
        _exec(repo, out2, GUARD_SEEDS[5:6])


def test_formal_requires_the_measurement_commit_and_the_range(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    with pytest.raises(R.G.GuardError):
        R.execute("formal", [34001], tmp_path / "o", repo, None, runner=_dummy, executor_factory=SerialExecutor)
    assert not (tmp_path / "o").exists()
    assert R.OUT_DIR == Path("data/experiments/0041") and AN.OUT_DIR == R.OUT_DIR and R.MAX_WORKERS == 2
    assert list(R.allowed_seeds("formal")) == list(range(34001, 34201))
    assert list(R.allowed_seeds("smoke")) == list(range(34201, 34207))


def test_a_changed_tree_or_protocol_stops_the_run(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    commit = _git(repo, "rev-parse", "HEAD")
    (repo / "dirty.txt").write_text("x", encoding="utf-8")
    with pytest.raises(R.G.GuardError):
        _exec(repo, tmp_path / "dirty", GUARD_SEEDS[:1])
    assert not (tmp_path / "dirty").exists()
    (repo / "dirty.txt").unlink()

    def edits_protocol(seed: int) -> dict:
        p = repo / R.PROTOCOL_PATH
        p.write_text(p.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
        return _dummy(seed)
    out = tmp_path / "changed"
    with pytest.raises(R.G.GuardError):
        R.execute("synthetic", GUARD_SEEDS[:2], out, repo, commit, runner=edits_protocol, executor_factory=SerialExecutor)
    statuses = {s: st for s, (st, _) in R.G.scan(out)["seeds"].items()}
    assert statuses == {GUARD_SEEDS[0]: "failed"}                              # 2 つ目は始めない


def test_the_raw_meta_carries_the_gate_declaration_and_the_protocol(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    _exec(repo, out, GUARD_SEEDS[:1], runner=functools.partial(M.measure_seed, PROTOCOL, plan=SMALL))
    raw = AN.read_raw(R.G.seed_dir(out, GUARD_SEEDS[0]) / R.G.RAW)
    assert raw["meta"]["gate"] == {"sha256": AN.GATE_SHA256, "declaration": AN.GATE_DECLARATION}
    assert raw["meta"]["protocol"] == AN.PROTOCOL_AS_STORED and raw["meta"]["protocol_sha256"] == AN.PROTOCOL_SHA256
    assert (R.GATE_SHA256, R.GATE_DECLARATION) == (AN.GATE_SHA256, AN.GATE_DECLARATION)
    assert AN.check_seed(raw, "synthetic", GUARD_SEEDS[0], SMALL) == {k: [] for k in AN.CHECK_NAMES}


def test_records_state_and_the_synthetic_pipeline_through_run_and_analyze(repo, tmp_path, monkeypatch) -> None:
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
    assert report["valid"] is True and report["judgment"]["J_B"]["m"] == 3
    assert report["judgment"]["outcome"] == "not_established"                  # 3 個体では k₂(3) ＝ 4 に届かない（算術）
    assert _complete(out, seeds) == report | {"measurement_commit": records["measurement_commit"]}
    assert RC.recheck_directory(out)["mismatches"] == []                       # 保存したファイルからの独立の検算


# ---- CT-41-9 smoke の盲検：現象の数値を保存しない（0040 と同じ） -------------------------------------------------

FORBIDDEN_KEYS = ((AN.RUN_KEYS - {"seed", "plan", "roles"}) | AN.END_KEYS | set().union(*AN.BODY_KEYS.values()) | JUDGMENT_KEYS
                  | {"run", "outcome", "winner_unit", "decision_pulse", "emit_pulse", "window"})
META_KEYS = {"experiment", "kind", "mode", "seed", "measurement_commit", "protocol_sha256", "protocol", "manifest", "gate",
             "blind"}
ISO_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
NUMERIC_OK = {"seed", "raw_file_bytes", "max_workers", "pid"}


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
    for d in [out, *out.rglob("*")]:
        assert d.stat().st_mtime == R.CONCEALED_MTIME, d
    for d in sorted((out / R.G.SEEDS_DIR).iterdir()):
        start = json.loads((d / R.G.START).read_text(encoding="utf-8"))
        finish = json.loads((d / R.G.FINISH).read_text(encoding="utf-8"))
        assert start["started_at"] == R.BLINDED_TIME and finish["finished_at"] == R.BLINDED_TIME
        assert finish["seconds"] is None and start["max_workers"] == 1
        for rec in (start, finish):
            assert not ISO_TIME.search(json.dumps(rec)), rec
            assert _numeric_keys(rec) <= NUMERIC_OK, _numeric_keys(rec)


def test_blind_execution_stores_no_phenomenon_values(repo, tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    seeds = SYN[:2]
    workers: list[int] = []
    done = _blind_exec(repo, out, seeds, workers=workers)
    assert done["completed"] == sorted(seeds) and workers == [1]
    assert capsys.readouterr().out == ""
    _assert_no_timing(out)
    files = sorted(p for p in out.rglob("*") if p.is_file() and p != out / R.G.LOCK)
    assert {p.name for p in files} == {R.G.START, R.G.FINISH, R.G.RAW} and len(files) == 3 * len(seeds)
    for p in files:
        data = json.loads(gzip.decompress(p.read_bytes()) if p.name.endswith(".gz") else p.read_bytes())
        bad = {k for _, k in _keys(data) if k in FORBIDDEN_KEYS}
        assert not bad, (p, bad)
        if p.name == R.G.RAW:
            s = data["meta"]["seed"]
            assert set(data) == {"meta", "blind"} and set(data["meta"]) == META_KEYS
            assert data["blind"]["checks"] == {k: "ok" for k in AN.CHECK_NAMES}
            again = {"meta": data["meta"], "run": M.measure_seed(PROTOCOL, s, SMALL)}
            canonical = json.dumps(json.loads(json.dumps(again)), separators=(",", ":"), sort_keys=True).encode("utf-8")
            assert data["blind"]["raw_sha256"] == R.G.sha256_bytes(canonical)


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
    finish = json.loads((R.G.seed_dir(out, GUARD_SEEDS[1]) / R.G.FINISH).read_text(encoding="utf-8"))
    assert finish["reason"] == "RuntimeError"
    assert all("1234" not in p.read_bytes().decode("utf-8", "replace") for p in out.rglob("*") if p.is_file())
    assert capsys.readouterr().out == ""
    _assert_no_timing(out)


def test_blinded_record_marks_a_failed_check_without_reasons() -> None:
    s = decided_seed()
    for tamper, check in ((lambda r: r["bodies"]["B_A2"]["pulse_weights"][3][1].__setitem__(0, 0.0111), "O6"),
                          (lambda r: r["bodies"][M.RERUN].update(sigma_p_e_sha256="0" * 64), "O8"),
                          (lambda r: r["bodies"]["B_A2"]["sigma_0"]["units"][r["roles"]["cue"]].update(activity=9.0), "O4")):
        data = measured(s)
        data["meta"]["blind"] = True
        tamper(data["run"])
        rec = R.blinded(data, "synthetic", s, SMALL)
        assert set(rec) == {"meta", "blind"} and rec["blind"]["checks"][check] == "fail"
        assert set(rec["blind"]) == AN.BLIND_KEYS and all(v in ("ok", "fail") for v in rec["blind"]["checks"].values())


def test_smoke_report_reads_blinded_records_and_rechecks_o11() -> None:
    s = SYN[0]
    data = measured(s)
    data["meta"]["blind"] = True
    rec = R.blinded(data, "synthetic", s, SMALL)
    rec["meta"]["mode"] = "smoke"
    report = AN.analyze_runs({s: rec}, "smoke", o1=[])
    assert set(report) == {"mode", "O1", "checks", "valid"} and report["checks"][str(s)]["O11"] == "fail"
    assert report["valid"] is False
    missing = copy.deepcopy(rec)
    missing["blind"]["checks"].pop("O10")
    assert AN.check_blinded(missing, s, "smoke") == {k: "fail" for k in AN.CHECK_NAMES}
    no_gate = copy.deepcopy(rec)
    no_gate["meta"]["gate"]["sha256"] = "0" * 64
    assert AN.check_blinded(no_gate, s, "smoke") == {k: "fail" for k in AN.CHECK_NAMES}


def test_smoke_must_be_blind_and_formal_must_not(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    commit = _git(repo, "rev-parse", "HEAD")
    for mode, seeds, kw in (("smoke", [34201], {"blind": False}), ("formal", [34001], {"blind": True}),
                            ("smoke", [34201], {"check_plan": SMALL})):
        out = tmp_path / f"o_{mode}_{min(kw)}"
        with pytest.raises(R.G.GuardError):
            R.execute(mode, seeds, out, repo, commit, runner=_dummy, executor_factory=SerialExecutor, **kw)
        assert not out.exists()


# ---- O1 の証拠（0040 と同じ） ---------------------------------------------------------------------------

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
        return _Proc(0, "....\n500 passed in 90.0s\n")
    out = tmp_path / "out"
    rec = R.record_contract_tests(repo, out, commit, run=ok)
    assert rec["exit_code"] == 0 and calls[0][0][1:] == ["-m", "pytest", "-q", *AN.CONTRACT_TESTS]
    assert len(AN.CONTRACT_TESTS) == 5 and AN.o1_check(out, commit) == []
    R.record_contract_tests(repo, out, commit, run=lambda *a, **k: pytest.fail("走らせ直さない"))


def _never(*a, **k):
    raise AssertionError("O1 が成り立たないのに、契約テストの実行か seed の計算に進んだ")


@pytest.mark.parametrize("name,tamper", [
    ("終了コード", lambda r: r.update(exit_code=1)),
    ("結果の行", lambda r: r.update(summary="1 failed, 498 passed in 50.0s")),
    ("テストのファイルの SHA-256", lambda r: r["test_files_sha256"].update({AN.CONTRACT_TESTS[4]: "0" * 64})),
    ("走らせたコマンド", lambda r: r.update(command=["python", "-m", "pytest", "-q", *AN.CONTRACT_TESTS[:4]])),
    ("測定の commit", lambda r: r.update(measurement_commit="0" * 40)),
])
def test_a_broken_o1_record_stops_before_any_seed_is_started(repo, tmp_path, monkeypatch, name, tamper) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    commit = _o1_repo(repo)
    R.record_contract_tests(repo, out, commit, run=lambda *a, **k: _Proc(0, "499 passed in 50.0s\n"))
    path = out / AN.O1_FILE
    rec = json.loads(path.read_text(encoding="utf-8"))
    tamper(rec)
    path.write_text(json.dumps(rec), encoding="utf-8")
    with pytest.raises(R.G.GuardError):
        R.start("synthetic", GUARD_SEEDS[:2], out, repo, commit, run=_never, runner=_never, executor_factory=SerialExecutor)
    assert not (out / R.G.SEEDS_DIR).exists()


def test_a_failing_contract_test_run_stops_before_any_seed(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    commit = _o1_repo(repo)
    with pytest.raises(R.G.GuardError):
        R.start("synthetic", GUARD_SEEDS[:2], out, repo, commit, run=lambda *a, **k: _Proc(1, "1 failed, 498 passed\n"),
                runner=_never, executor_factory=SerialExecutor)
    assert not (out / R.G.SEEDS_DIR).exists() and (out / AN.O1_FILE).exists()


def test_a_valid_o1_record_lets_start_run_the_seeds(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    commit = _o1_repo(repo)
    R.record_contract_tests(repo, out, commit, run=lambda *a, **k: _Proc(0, "499 passed in 50.0s\n"))
    done = R.start("synthetic", GUARD_SEEDS[:2], out, repo, commit, run=_never, runner=_dummy, executor_factory=SerialExecutor)
    assert done["completed"] == GUARD_SEEDS[:2]


def test_main_goes_through_start() -> None:
    src = inspect.getsource(R.main)
    assert "start(mode, seeds, out, REPO, args.measurement_commit)" in src and "execute(" not in src


def test_results_copy_is_verified_byte_for_byte(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    _exec(repo, out, GUARD_SEEDS[:2])
    (out / AN.REPORT).write_text(json.dumps({"measurement_commit": _git(repo, "rev-parse", "HEAD")}), encoding="utf-8")

    def copy_to(name: str) -> Path:
        dst = tmp_path / name
        shutil.copytree(out, dst, ignore=shutil.ignore_patterns(R.G.LOCK))
        return dst
    assert AN.verify_results_copy(out, copy_to("ok")) == []
    gone = copy_to("gone")
    (R.G.seed_dir(gone, GUARD_SEEDS[1]) / R.G.RAW).unlink()
    assert AN.verify_results_copy(out, gone)
    changed = copy_to("changed")
    (changed / AN.REPORT).write_text(json.dumps({"measurement_commit": "0" * 40}), encoding="utf-8")
    assert AN.verify_results_copy(out, changed)
