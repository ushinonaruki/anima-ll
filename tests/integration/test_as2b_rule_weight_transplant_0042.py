"""実験 0042 の道具の契約テスト（確定した事前登録 v0.2 の README・protocol.yaml。#195 merge `49d99e4`。README §14 の CT-42-1〜11）。

本番の seed（35001〜35200）・smoke の seed（35201〜35206）・関門の seed（31001〜31040）・0039 の seed（32001〜32399）・
0040 の seed（33001〜33399）・0041 の seed（34001〜34399）は使わない（実行もしない）。0039〜0041 の raw・report も、関門の記録も
使わない。合成の契約テスト専用の範囲（35301〜35399）だけを使う。合成の個体は、本番と同じ道具（measure.measure_seed）・同じ式で、
区間だけを小さくした Plan（SMALL：予定は 8 窓、E ＝ 窓 1〜4、P_E ＝ 204、終わり ＝ 350）か、本番の Plan で、実物の runtime を通して
作る。結果を見て Plan・seed を選んでいない（seed は範囲の最初から順に、構成の条件だけで決定的に選ぶ）。テストは操作の確認・記録の形・
Runtime の順序・判定と推定の算術だけを確かめ、合成の個体の判定と推定の量（s と n_U、§3.2 のすべての量とその符号、向きごとの数、
m≠・m_def、E_T、区間、k*、§4.1 の札、W^{A1}・W^{A2} と δ、選択と結果の刺激の数、最初に分かれた Pulse）の値を表示も判定もしない
（README §9.3）。実際の軌道から求めた値は、整合の真偽だけを確かめる。

構成（README §14 の契約テストの要件）：
- k* のある個体：SMALL の B^{A1} の層 A の窓 1〜4 に、決まった窓が 1 つ以上ある最初の合成の個体
- U に結果の刺激がある個体：SMALL の G^{A1}[W^{A1}] か G^{A2}[W^{A2}] に、U の結果の刺激の予約が 1 つ以上ある最初の合成の個体
- 構造的な 0（SE-T2・SE-T7）：本番と同じ measure_seed を通し、組み立ての直後（Pulse 0）に両方の源の Unit の θ・c を出生時の範囲の
  角（g ＜ −E_S）に置いた合成の個体。W^{A1} ＝ W^{A2} ＝ 出生時の値になる（CT-42-4 の「W^{A1} ＝ W^{A2} の合成の場合」）
- 非対称な角（CT-42-8）：一方の源を構造的に沈黙させ、もう一方の源と手がかりの Unit を最も発火しやすい角に置いた合成の個体を、本番の
  Plan で measure_seed に通す（17 系：移植・端の値・結果を返さない世界を含む）。結果があること（発火・決まった窓・結果の刺激）を
  真偽で確かめる（0041 の CT-41-7 への監査の教訓）
- Pulse 1,066 の駆動の差（CT-42-5）：SMALL の本体を P_E まで進め、手がかりの Unit の activity を置いて（発火する場合・どの Unit も
  発火しない場合）から二つに複製し、X1・X2 を移植した合成の系
置き方は 0039 の CT-39-8・0041 の CT-41-7 と同じで、AS2b の道具も Core も変えない（契約テストだけ）。

使った合成の seed（PR に開示）：35301〜35310（SMALL）、35321〜35326（一度限りの実行・盲検の契約。dummy の計算と SMALL）、
35390〜35393（角の系と、構造的な 0・Pulse P_E ＋ 1 の駆動・痕跡の扱い・自分の値の移植の構成）、35399（本番の Plan で実物の
runtime を通す確かめと、関門の run_body との照合）、構成の条件で選んだ個体（35301〜35399 の最初から順。どれになったかはテストの中で
決まる）。

失敗の表示に現象の値を出さない（README §9.3）：このモジュールの assert は pytest に書き換えさせない（PYTEST_DONT_REWRITE）。
失敗しても、評価した値を表示せず、行の文と AssertionError だけを出す。assert の文の後ろに付ける文は、系・欄の名前、report・
ファイルの場所だけにし、合成の軌道から求めた値（Pulse の番号・数・重み・符号など）を入れない。この仕組み自体を、別のプロセスで
走らせたテストの出力で確かめる（test_a_failing_assert_under_this_mechanism_prints_no_evaluated_value）。
"""

import ast
import copy
import dataclasses
import functools
import gzip
import hashlib
import importlib.util
import inspect
import json
import re
import shutil
import subprocess
import sys
from concurrent.futures import Future
from fractions import Fraction
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments" / "0042_as2b_rule_weight_transplant"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = _load("measure_0042_test", EXP / "measure.py")
AN = _load("analyze_0042_test", EXP / "analyze.py")
AL = _load("alignment_0042_test", EXP / "alignment.py")
AX = _load("analysis_0042_test", EXP / "analysis.py")
R = _load("run_0042_test", EXP / "run.py")
RC = _load("recheck_0042_test", EXP / "recheck.py")
GATE = _load("gate_0038_for_0042_test", ROOT / "experiments" / "0038_as2b_forward_gate" / "gate.py")
A, AS1 = M.A, M.AS1
SMALL = M.Plan(41, 41, 8, 2, 19, 2, 4)
FORMAL = M.formal_plan(PROTOCOL)
SYN = list(range(35301, 35311))
SYN_ALL = list(range(35301, 35400))
GUARD_SEEDS = list(range(35321, 35327))
CORNER_SEEDS = (35390, 35391, 35392, 35393)
FORMAL_SEED = 35399
W_MAX, W0 = PROTOCOL["brain"]["w_max"], PROTOCOL["brain"]["initial_weight_w0"]
THETA = (0.45, 0.55)                                                 # 出生時の θ の範囲（0.5 ± 10%）
DRIVE = (0.072, 0.088)                                               # 出生時の c の範囲（0.08 ± 10%）
LAMBDA = 0.85
EASY = (THETA[0], DRIVE[1])                                          # 最も発火しやすい角
RESPOND = ("world", "rule", "respond")


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)


def _meta(seed: int, mode: str = "synthetic") -> dict:
    """run.py が書く meta と同じ形（protocol の写しと、その SHA-256 を含む）。"""
    return {"experiment": "0042", "kind": PROTOCOL["kind"], "mode": mode, "seed": seed, "manifest": M.manifest_raw(),
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


CORNERS = {"zero": lambda: {"source1": _silent_values(), "source2": _silent_values()},
           "silent_source1": lambda: {"source1": _silent_values(), "source2": EASY, "cue": EASY},
           "silent_source2": lambda: {"source2": _silent_values(), "source1": EASY, "cue": EASY}}


@functools.cache
def _measured(seed: int, plan: M.Plan, corner: str | None = None) -> str:
    if corner is None:
        return json.dumps(_raw(M.measure_seed(PROTOCOL, seed, plan)))
    original = M.build_body

    def build(plan_, seed_, rule_c, *, log=None):                      # 本番と同じ組み立てに、Pulse 0 で Unit の値を置くだけ
        s = original(plan_, seed_, rule_c, log=log)
        _place(s, CORNERS[corner]())
        return s
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(M, "build_body", build)
        return json.dumps(_raw(M.measure_seed(PROTOCOL, seed, plan)))


def measured(seed: int, plan: M.Plan = SMALL, corner: str | None = None) -> dict:
    """実物の runtime を通した合成の個体の生の記録（JSON を通した形。返すのは複製）。"""
    return json.loads(_measured(seed, plan, corner))


def failures(data: dict, seed: int, plan: M.Plan = SMALL) -> dict:
    return {k: v for k, v in AN.check_seed(data, "synthetic", seed, plan).items() if v}


def _log():
    return AS1.AS1Log(keep=M.LOG_KEEP)


def _rec(run: dict, name: str) -> dict:
    return run["clones"][name] if name in M.CLONES else run["bodies"][name]


@functools.cache
def decided_seed() -> int:
    """SMALL の B^{A1} の層 A の窓 1〜E に、決まった窓が 1 つ以上ある最初の合成の個体（構成の条件だけ。値は表示しない）。"""
    return next(s for s in SYN_ALL if AN.k_star(measured(s)["run"]["bodies"]["B_A1"]["layer_a"], SMALL.e_windows) is not None)


@functools.cache
def consequence_seed() -> int:
    """SMALL の G^{A1}[W^{A1}] か G^{A2}[W^{A2}] に、U の結果の刺激の予約が 1 つ以上ある最初の合成の個体（構成の条件だけ）。"""
    def has(s):
        run = measured(s)["run"]
        return any(AN._first_consequence(run["clones"][n], SMALL.p_e) is not None for n in ("G_A1_WA1", "G_A2_WA2"))
    return next(s for s in SYN_ALL if has(s))


def zero_individual() -> dict:
    """構造的な 0 の個体（両方の源を構造的に沈黙させた合成の個体。SE-T2・SE-T7・SE-T10）。"""
    return measured(CORNER_SEEDS[0], SMALL, "zero")


def corner_individual(silent: str) -> dict:
    """非対称な角の個体（本番の Plan。一方の源が構造的に沈黙し、もう一方の源と手がかりの Unit が最も発火しやすい角）。"""
    return measured(CORNER_SEEDS[1], FORMAL, f"silent_{silent}")


# ---- protocol と道具の一致 ----------------------------------------------------------------------

def test_protocol_and_tools_are_aligned() -> None:
    AL.check(PROTOCOL)


def test_the_formal_plan_is_taken_from_the_gate_declaration() -> None:
    assert FORMAL == M.Plan(41, 41, 50, 2, 19, 2, 25) and (FORMAL.p_e, FORMAL.end) == (1065, 2072)
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
                   lambda d: d["roles"].update(stream="other-{seed}"),
                   lambda d: d["bodies"].update(pulses=2073)):              # この実験は本体の長さ（b_K ＋ L）も宣言から取る
        changed = copy.deepcopy(decl)
        tamper(changed)
        with pytest.raises(ValueError):
            M.plan_from_declaration(changed, 25)
    for key, value in (("boundary_P_E", 1064), ("body_pulses", 2071)):
        other_tl = copy.deepcopy(PROTOCOL)
        other_tl["timeline"][key] = value
        with pytest.raises(ValueError, match="timeline"):
            M.formal_plan(other_tl)
    for e in (0, 50):
        with pytest.raises(ValueError):
            M.check_plan(dataclasses.replace(FORMAL, e_windows=e))


def test_the_intervals_by_arithmetic() -> None:
    """SE-T1・SE-T6 の算術（analysis.py と同じ）：窓 25 ＝ [1027, 1045]、E の最後の結果 1047、P_E ＝ 1065、U の最初の窓
    ＝ [1068, 1086]、U の最初の結果は早くとも 1070、終わり ＝ 2072、1 個体の Pulse ＝ 20,314。"""
    iv = AX.intervals(AX.gate_set())
    assert FORMAL.schedule().windows[24] == (25, 1027, 1045) and iv["last_E_outcome_pulse"] == 1047 < FORMAL.p_e
    assert FORMAL.schedule().windows[25] == (26, 1068, 1086) == tuple(iv["first_U_window"])
    assert iv["earliest_U_consequence_pulse"] == 1070 and FORMAL.schedule().cues[25] == FORMAL.p_e + 1 == 1066
    assert iv["P_E"] == FORMAL.p_e and iv["body_pulses"] == FORMAL.end == 2072
    assert iv["pulses_per_individual"] == 3 * 2072 + 14 * (2072 - 1065) == 20314 == AL.PULSES_PER_INDIVIDUAL


def test_the_run_entry_point_uses_only_the_protocol_plan() -> None:
    assert "W.measure_seed(PROTOCOL, seed)" in inspect.getsource(R.measure)
    assert "plan" not in inspect.signature(R.measure).parameters


def test_seen_seeds_include_0041_and_the_gate_and_exclude_0042() -> None:
    assert {30001, 31001, 31040, 32001, 32399, 33001, 33399, 34001, 34200, 34201, 34301, 34399, 9101} <= AL.SEEN
    assert not ({35001, 35200, 35201, 35206, 35301, 35399} & AL.SEEN)


def test_contract_tests_of_o1_are_the_tool_tests_and_this_file() -> None:
    assert AN.CONTRACT_TESTS == (*PROTOCOL["tools"]["contract_tests"], "tests/integration/test_as2b_rule_weight_transplant_0042.py")
    assert R.CONTRACT_TESTS == AN.CONTRACT_TESTS == RC.CONTRACT_TESTS
    assert (ROOT / AN.CONTRACT_TESTS[-1]) == Path(__file__).resolve()


def test_the_analysis_names_follow_the_protocol() -> None:
    assert AN.CHECK_NAMES[1:] == tuple(PROTOCOL["operation_checks"][1:]) and PROTOCOL["operation_checks"][0] == "O1"
    q = AX.quantities({n: Fraction(1, 2) for n in M.SYSTEMS if n != M.RERUN})
    assert set(AN.QUANTITY_NAMES) | {"T_any"} == set(q) and list(RC.NAMES) == list(AN.QUANTITY_NAMES)
    assert all(set(AN.QUANTITY_SYSTEMS[k]) <= set(M.SYSTEMS) for k in AN.QUANTITY_NAMES)
    assert AN.MAIN_FOUR == ("G_A1_WA1", "G_A1_WA2", "G_A2_WA1", "G_A2_WA2") and RC.T_SYSTEMS == list(AN.MAIN_FOUR)
    assert list(M.SYSTEMS) == PROTOCOL["systems"]["per_individual"] == RC.ALL
    assert PROTOCOL["judgment"]["outcomes"] == ["invalid", "inconclusive", "not_established", "plus", "minus"]
    assert AN.F1_TOLERANCE == 1e-12 and AN.MIN_M == 10 and AN.CLASSES == RC.CLASSES


# ---- 合成の個体が、すべての操作の確認を通る ------------------------------------------------------------

@pytest.mark.parametrize("seed", SYN)
def test_synthetic_individuals_pass_every_operation_check(seed) -> None:
    assert failures(measured(seed), seed) == {}
    assert RC.operation_problems(measured(seed)) == []


def test_the_formal_plan_through_the_runtime_passes_every_operation_check() -> None:
    data = measured(FORMAL_SEED, FORMAL)
    assert AN.check_seed(data, "synthetic", FORMAL_SEED, None) == {k: [] for k in AN.CHECK_NAMES}
    assert RC.operation_problems(data) == []
    run = data["run"]
    assert all(len(_rec(run, n)["layer_a"]) == 50 and _rec(run, n)["pulse_end"] == 2072 for n in M.SYSTEMS)
    assert all(len(run["clones"][n]["pulse_weights"]) == 2072 - 1065 for n in M.CLONES)


@pytest.mark.parametrize("which", ["decided", "consequence", "zero", "silent_source1", "silent_source2"])
def test_the_constructed_individuals_pass_every_operation_check(which) -> None:
    if which in ("decided", "consequence"):
        seed = decided_seed() if which == "decided" else consequence_seed()
        data, plan = measured(seed), SMALL
    elif which == "zero":
        seed, data, plan = CORNER_SEEDS[0], zero_individual(), SMALL
    else:
        seed, data, plan = CORNER_SEEDS[1], corner_individual(which.split("_")[1]), FORMAL
    assert failures(data, seed, plan) == {} and RC.operation_problems(data) == []


JUDGMENT_KEYS = {"s_U", "s_E", "n_U", "T", "T_A1", "T_A2", "T_any", "BE", "TE_F", "D", "S", "TN", "K_A1", "Z_A1", "delta",
                 "sign", "signs", "k_star", "class", "zero_label", "structural_identity", "quantities", "judgment", "individuals",
                 "auxiliary", "descriptive_controls", "estimate", "interval", "counts_E", "counts_U", "S1", "J_T", "E_T",
                 "first_divergence", "consequences", "p_nz", "p_any", "m_def", "m_nonzero"}


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


def test_a_failing_assert_under_this_mechanism_prints_no_evaluated_value(tmp_path) -> None:
    """仕組みそのものの確かめ（README §9.3・0041 の CT-41-7 の教訓）：PYTEST_DONT_REWRITE を置いたモジュールで assert が失敗しても、
    評価した値（式の中で計算した数）は出力に出ない。置かないモジュールでは出る（確かめが空でない）。リポジトリの pytest の設定で走らせる。"""
    body = ("def test_hidden():\n"
            "    secret = sum(range(7)) / 17\n"
            "    assert secret == 1\n")
    shown = repr(sum(range(7)) / 17)
    out = {}
    for name, doc in (("test_hidden_quiet.py", '"""PYTEST_DONT_REWRITE"""\n\n'), ("test_hidden_loud.py", "")):
        f = tmp_path / name
        f.write_text(doc + body, encoding="utf-8")
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--rootdir", str(ROOT),
                               "-c", str(ROOT / "pyproject.toml"), str(f)], capture_output=True, text=True, cwd=ROOT)
        out[name] = (proc.returncode, proc.stdout + proc.stderr)
    quiet, loud = out["test_hidden_quiet.py"], out["test_hidden_loud.py"]
    assert quiet[0] == 1 and "AssertionError" in quiet[1] and shown not in quiet[1]
    assert loud[0] == 1 and shown in loud[1]


# ---- CT-42-1 組み立て --------------------------------------------------------------------------------------

def test_ct42_1_every_system_is_built_from_the_gate_body_with_its_rule_c() -> None:
    src = inspect.getsource(M.build_body)
    assert "A.build(seed, schedule=plan.schedule(), delay=plan.delay, rule_c=rule_c, respond=True" in src
    for c in ("A1", "A2"):
        s = M.build_body(SMALL, SYN[0], c)
        assert s.meta == {"delay": 2, "rule_c": c, "respond": True, "outlet": True, "world_cues": True}
        assert s.log.keep == AS1.AS1Log.DEFAULT_KEEP and s.connections.history == [] and s.pulse == 0
    run = measured(SYN[0])["run"]
    assert all(_rec(run, n)["world_end"]["rule"]["rule_c"] == M.RULE_OF[n] for n in M.SYSTEMS)
    assert all(_rec(run, n)["world_end"]["rule"]["respond"] is (n not in M.NO_RESPONSE) for n in M.SYSTEMS)
    assert {n: M.RULE_OF[n] for n in M.BODIES + (M.RERUN,)} == {k: v for k, v in PROTOCOL["world"]["rule_c"].items()
                                                                 if k != "background"}
    assert all(M.BACKGROUND[n] == f"B_{M.RULE_OF[n]}" for n in M.CLONES)
    assert M.TRANSPLANTS == {"G_A1_WA2": "A2", "G_A1_WA1_tr": "A1", "G_A2_WA1": "A1", "G_A2_WA2_tr": "A2",
                             "G_A1_X1": "X1", "G_A1_X2": "X2", "G_A2_X1": "X1", "G_A2_X2": "X2",
                             "N_A1_WA2": "A2", "N_A2_WA1": "A1"}


def test_ct42_1_the_bodies_equal_the_gate_run_body() -> None:
    """本番の Plan の B^{A1}・B^{A2}・B′^{A1} の P_E と終わりの Σ・層 A・層 B・発火が、関門の宣言 v0.2 の `run_body` の本体
    （同じ組み立て）と同じ。関門の run_body を走らせた層 A の 50 窓とも同じ。"""
    decl, _ = M.gate_declaration(PROTOCOL)
    run = measured(FORMAL_SEED, FORMAL)["run"]
    for n in M.BODIES + (M.RERUN,):
        gate_like = A.build(FORMAL_SEED, schedule=GATE.schedule_of(decl, A), delay=decl["world"]["delay_L"],
                            rule_c=M.RULE_OF[n], respond=True)
        A.advance_to(gate_like.app, FORMAL.p_e)
        at_p_e = run["boundary"]["sigma_p_e"][n] if n in M.BODIES else run["bodies"][n]["sigma_p_e"]
        assert AS1.sigma_diff(M._sigma(gate_like), at_p_e) == [], n
        A.advance_to(gate_like.app, FORMAL.end)
        rec = run["bodies"][n]
        assert AS1.sigma_diff(M._sigma(gate_like), rec["sigma_end"]) == [], n
        assert [dict(r) for r in gate_like.decider.records] == rec["layer_a"]
        assert [list(x) for x in gate_like.world.intents] == rec["layer_b"]
        assert [list(x) for x in gate_like.log.activity()] == rec["activity"]
    for c, n in (("A1", "B_A1"), ("A2", "B_A2")):
        _row, audit = GATE.run_body(A, decl, FORMAL_SEED, c)
        assert audit["layer_a"] == run["bodies"][n]["layer_a"] and audit["reached_windows"] == 50


def test_the_gate_and_earlier_and_formal_seeds_are_never_run_by_the_tests(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    commit = _git(repo, "rev-parse", "HEAD")
    for seed in (31001, 31040, 32001, 32301, 33001, 33301, 34001, 34201, 34301, 34399, 35001, 35201, 30201):
        with pytest.raises(R.G.GuardError):
            R.execute("synthetic", [seed], tmp_path / f"o{seed}", repo, commit, runner=_dummy, executor_factory=SerialExecutor)
        assert not (tmp_path / f"o{seed}").exists()
    for mode in ("formal", "smoke"):
        with pytest.raises(R.G.GuardError):
            R.execute(mode, [34001], tmp_path / f"g{mode}", repo, commit, runner=_dummy, executor_factory=SerialExecutor)


def test_ct42_1_the_observation_split_and_the_record_keys() -> None:
    """B′^{A1} は、関門と同じ組み立てと既定の来歴のログで、P_E と終わりの二点のほかは状態を読まない（README §2.2）。"""
    run = measured(SYN[0])["run"]
    assert {n: set(r) for n, r in run["bodies"].items()} == AN.BODY_KEYS
    assert all(set(run["clones"][n]) == AN.CLONE_KEYS for n in M.CLONES)
    src = inspect.getsource(M.measure_seed)
    assert "rerun = build_body(plan, seed, RULE_OF[RERUN])" in src                # log を渡さない ＝ AS2b の道具の既定のログ
    part = src[src.index("rerun = build_body"):src.index("return {")]
    assert part.count("A.advance_to") == 2 and part.count("_sigma(rerun)") == 1 and "_row(rerun" not in part
    assert part.index("A.advance_to(rerun.app, p_e)") < part.index("_sigma(rerun)") < part.index("A.advance_to(rerun.app, end)") \
        < part.index("_end_record(rerun)")


# ---- CT-42-2 共通の部分（SE-T2） -----------------------------------------------------------------------

def test_ct42_2_the_two_bodies_share_the_prefix_up_to_the_k_star_intent() -> None:
    """k* の意図の Pulse まで、二つの本体の脳の側の Σ と層 A・発火が一致し、その後の結果の予約は、規則 c が k* の行動 ID を
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
    assert [x for x in a["activity"] if x[0] <= t] == [x for x in b["activity"] if x[0] <= t]
    assert sorted(tuple(p) for p in AS1.sigma_diff(a["sigma_0"], b["sigma_0"])) == [("world", "rule", "rule_c")]


def test_ct42_2_without_k_star_the_bodies_are_identical_through_p_e_and_w_is_equal() -> None:
    """SE-T2：E に決まった窓がない個体では、P_E まで規則 c のほかが同じで、W^{A1} ＝ W^{A2}（札 Z-1。T は定まれば 0）。"""
    data = zero_individual()
    run = data["run"]
    a, b = run["bodies"]["B_A1"], run["bodies"]["B_A2"]
    assert AN.k_star(a["layer_a"], SMALL.e_windows) is None and a["first_intent"] is None and b["first_intent"] is None
    for key in ("activity", "sensory", "layer_b", "delta_log"):
        assert [x for x in a[key] if x[0] <= SMALL.p_e] == [x for x in b[key] if x[0] <= SMALL.p_e], key
    assert [tuple(p) for p in AS1.sigma_diff(run["boundary"]["sigma_p_e"]["B_A1"], run["boundary"]["sigma_p_e"]["B_A2"])] \
        == [("world", "rule", "rule_c")]
    assert run["boundary"]["W"]["A1"] == run["boundary"]["W"]["A2"] == run["W_0"]
    ind = AN.individual(run)
    assert ind["k_star"] is None and ind["zero_label"] == "Z-1" and ind["structural_identity"] is False
    assert ind["class"] in ("structural_zero", "undefined") and ind["delta"]["sign"] == "0"


def _layer(outcomes: list[str]) -> list[dict]:
    return [{"window": k + 1, "outcome": o} for k, o in enumerate(outcomes)]


def test_ct42_2_k_star_and_the_zero_labels_on_hand_made_layers() -> None:
    assert AN.k_star(_layer(["none", "tie", "A2", "A1"]), 4) == 3 and AN.k_star(_layer(["none", "tie", "none", "A1"]), 3) is None
    assert AN.zero_label(_layer(["none"] * 4), 4) == "Z-1" and AN.zero_label(_layer(["none", "tie", "none", "none"]), 4) == "Z-2"
    assert AN.zero_label(_layer(["tie", "A1"]), 2) is None and AN.zero_label(_layer(["tie", "A1"]), 1) == "Z-2"


def test_o4_detects_tampering() -> None:
    s = decided_seed()
    for tamper in (lambda r: r["bodies"]["B_A2"]["sigma_0"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["bodies"]["B_A2"]["first_intent"]["sigma"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["bodies"]["B_A2"]["first_intent"].update(pulse=r["bodies"]["B_A2"]["first_intent"]["pulse"] + 1),
                   lambda r: r["bodies"]["B_A1"].update(first_intent=None),
                   lambda r: r["bodies"]["B_A2"]["activity"].insert(0, [1, "zz"])):
        data = measured(s)
        tamper(data["run"])
        assert "O4" in failures(data, s)
    for tamper in (lambda r: r["boundary"]["sigma_p_e"]["B_A2"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["bodies"]["B_A2"].update(first_intent={"pulse": 1, "sigma": r["bodies"]["B_A2"]["sigma_0"]}),
                   lambda r: r["bodies"]["B_A1"]["activity"].append([SMALL.p_e, r["roles"]["cue"]]),
                   lambda r: r["boundary"]["W"]["A2"].update({min(r["W_0"]): 0.004})):
        data = zero_individual()
        tamper(data["run"])
        assert "O4" in failures(data, CORNER_SEEDS[0])


# ---- CT-42-3 境界（SE-T1・§2.4・O6・O12） ----------------------------------------------------------------------

def test_ct42_3_the_steps_follow_s0_to_s5_and_no_pulse_passes_between_s1_and_s4() -> None:
    run = measured(decided_seed())["run"]
    steps = run["boundary"]["steps"]
    assert steps == AN.expected_steps(run)
    assert [s[0] for s in steps] == (["S0"] * 2 + ["S1"] * 2 + ["S2"] * 14 + ["S3"] * 10 + ["S3'"] * 4 + ["S4"] * 14
                                     + ["S5"] * 16)
    assert all(s[2] == SMALL.p_e for s in steps if s[0] in ("S0", "S1", "S2", "S3", "S3'", "S4"))
    assert all(s[2] == SMALL.end for s in steps if s[0] == "S5")
    assert all(s[4]["intervention_state_at_transplant"] == {"active": [], "frozen": {}} for s in steps if s[0] == "S3")
    b = run["boundary"]
    assert all(b["sigma_a"][n]["pulse"] == b["sigma_b"][n]["pulse"] == SMALL.p_e for n in M.CLONES)
    assert all(b["sigma_p_e"][n]["pulse"] == SMALL.p_e for n in M.BODIES)


def _weight_paths(w_from: dict, w_to: dict) -> list[tuple]:
    return sorted(("connections", cid, "weight") for cid in w_from if w_from[cid] != w_to[cid])


@pytest.mark.parametrize("which", ["decided", "zero"])
def test_ct42_3_the_difference_inventory_after_s3_prime(which) -> None:
    """(a) S3′ の直後の差の目録：G^c[W^d]・G^c[X1]・G^c[X2] と G^c[W^c] は移植した重みだけ、G^c[W^c]^{tr} と G^c[W^c] は違いなし、
    N^c[W^c] と G^c[W^c] は `world.respond` だけ、N^c[W^d] と N^c[W^c] は移植した重みだけ、G^c[W^c] と B^c は違いなし。
    (b) S4 の直後は介入の状態だけが変わる。"""
    run = (measured(decided_seed()) if which == "decided" else zero_individual())["run"]
    b = run["boundary"]
    target = {"A1": b["W"]["A1"], "A2": b["W"]["A2"], "X1": run["X"]["X1"], "X2": run["X"]["X2"]}
    for c, d in (("A1", "A2"), ("A2", "A1")):
        base = b["sigma_a"][f"G_{c}_W{c}"]

        def diff(x, y):
            return sorted(tuple(p) for p in AS1.sigma_diff(x, y))
        assert diff(b["sigma_p_e"][f"B_{c}"], base) == []
        assert diff(base, b["sigma_a"][f"G_{c}_W{c}_tr"]) == []
        for n, key in ((f"G_{c}_W{d}", d), (f"G_{c}_X1", "X1"), (f"G_{c}_X2", "X2")):
            assert diff(base, b["sigma_a"][n]) == _weight_paths(target[c], target[key]), n
        assert diff(base, b["sigma_a"][f"N_{c}_W{c}"]) == [RESPOND]
        assert diff(b["sigma_a"][f"N_{c}_W{c}"], b["sigma_a"][f"N_{c}_W{d}"]) == _weight_paths(target[c], target[d])
    for n in M.CLONES:
        assert {p[0] for p in AS1.sigma_diff(b["sigma_a"][n], b["sigma_b"][n])} == {"interventions"}, n
    if which == "zero":                                    # W^{A1} ＝ W^{A2}：入れ替えの系は、移植しない系と違いがない
        assert _weight_paths(b["W"]["A1"], b["W"]["A2"]) == []
        assert AS1.sigma_diff(b["sigma_a"]["G_A1_WA1"], b["sigma_a"]["G_A1_WA2"]) == []
    else:                                                  # 移植した重みの違いが実際にある（目録の確かめが空でない）
        assert _weight_paths(b["W"]["A1"], b["W"]["A2"])


def test_ct42_3_freeze_is_declared_once_with_the_values_of_each_system() -> None:
    run = measured(decided_seed())["run"]
    six = sorted(run["W_0"])
    for n in M.CLONES:
        sb = run["boundary"]["sigma_b"][n]
        assert sb["interventions"]["active"] == [["FREEZE", six, "advance"]]
        assert {cid: v["weight"] for cid, v in sb["interventions"]["frozen"].items()} == AN._target(run, n)
        assert run["clones"][n]["history"] == [[SMALL.p_e, "S4", [["FREEZE", six, "advance"]]]]
    for n in M.BODIES + (M.RERUN,):
        assert run["bodies"][n]["history"] == []


def test_ct42_3_at_p_e_nothing_is_open_or_reserved() -> None:
    """SE-T1：P_E の本体に、未決の窓・出す予定の意図・結果の予約がない。残る予約は、U の手がかりだけ。"""
    for data in (measured(decided_seed()), measured(FORMAL_SEED, FORMAL)):
        run = data["run"]
        plan = M.Plan(**run["plan"])
        for n in M.BODIES:
            s = run["boundary"]["sigma_p_e"][n]
            assert s["pulse"] == plan.p_e and s["exit"]["cursor"] == plan.e_windows and s["exit"]["pending"] is None
            assert s["exit"]["reports"] == {}
            assert sorted(r[3] for r in s["world"]["pending"]) == [c for c in plan.schedule().cues if c > plan.p_e]
            assert {r[1] for r in s["world"]["pending"]} == {A.CUE}


def test_o6_detects_tampering() -> None:
    s = decided_seed()
    for tamper in (lambda r: r["boundary"]["steps"].pop(),
                   lambda r: r["boundary"]["steps"][20].__setitem__(2, SMALL.p_e + 1),
                   lambda r: r["boundary"]["steps"][20][4].update(intervention_state_at_transplant={"active": [["x"]], "frozen": {}}),
                   lambda r: r["boundary"]["sigma_a"]["N_A1_WA1"]["world"]["rule"].update(respond=True),
                   lambda r: r["boundary"]["sigma_a"]["G_A2_WA1"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["boundary"]["sigma_a"]["G_A1_WA1"].update(pulse=SMALL.p_e + 1),
                   lambda r: r["boundary"]["sigma_a"]["G_A1_X1"]["interventions"].update(active=[["FREEZE", [], "advance"]]),
                   lambda r: r["boundary"]["sigma_b"]["G_A2_X2"]["interventions"]["frozen"][min(r["W_0"])].update(weight=0.001),
                   lambda r: r["boundary"]["sigma_b"]["N_A2_WA2"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["clones"]["G_A1_WA2"]["history"].append([SMALL.p_e, "x", []])):
        data = measured(s)
        tamper(data["run"])
        assert "O6" in failures(data, s)


def test_o12_detects_tampering() -> None:
    s = decided_seed()
    cue_r = measured(s)["run"]["roles"]["cue_receptor"]
    for tamper in (lambda r: r["boundary"]["sigma_p_e"]["B_A1"]["exit"].update(cursor=SMALL.e_windows - 1),
                   lambda r: r["boundary"]["sigma_p_e"]["B_A2"]["exit"].update(pending={"unit": "s1"}),
                   lambda r: r["boundary"]["sigma_p_e"]["B_A1"]["world"]["pending"].append(
                       [99, A.CONSEQUENCE, cue_r, SMALL.p_e + 1, "d"]),
                   lambda r: r["boundary"]["W"]["A1"].update({min(r["W_0"]): 0.0049}),
                   lambda r: r["boundary"]["sigma_p_e_sha256"].update(B_A2="0" * 64),
                   lambda r: r["boundary"]["sigma_p_e"]["B_A2"]["interventions"].update(active=[["FREEZE", [], "advance"]])):
        data = measured(s)
        tamper(data["run"])
        assert "O12" in failures(data, s)


# ---- CT-42-4 移植の恒等と構造上の恒等（SE-T4・SE-T7・O8） ------------------------------------------------------------

@pytest.mark.parametrize("rule_c", ["A1", "A2"])
def test_ct42_4_own_value_transplant_is_the_identity_at_runtime(rule_c) -> None:
    """自分の値の移植は、移植しない複製と、移植の直後の Σ が同じで、U で FREEZE して終わりまで進めても、発火・層 A・層 B・
    感覚の出来事・終わりの Σ が同じ（SE-T4。移植は痕跡とほかの Σ を変えない：CT-I4）。"""
    body = M.build_body(SMALL, CORNER_SEEDS[3], rule_c, log=_log())
    A.advance_to(body.app, SMALL.p_e)
    own = M._weights(body)
    plain, tr = A.clone(body), A.clone(body)
    tr.transplant(own)
    assert AS1.sigma_diff(M._sigma(plain), M._sigma(tr)) == [] and AS1.sigma_diff(M._sigma(plain), M._sigma(body)) == []
    for s in (plain, tr):
        s.declare(M._freeze_six(frozenset(own)), label="S4")
        A.advance_to(s.app, SMALL.end)
    assert AS1.sigma_diff(M._sigma(plain), M._sigma(tr)) == []
    assert plain.log.activity() == tr.log.activity() and plain.log.sensory() == tr.log.sensory()
    assert plain.decider.records == tr.decider.records and plain.world.intents == tr.world.intents
    assert any(u for _p, u in tr.log.activity())                         # 確かめが空でない（U に発火がある）


@pytest.mark.parametrize("which", ["decided", "consequence"])
def test_ct42_4_own_value_transplant_equals_the_untransplanted_clone_in_the_records(which) -> None:
    run = measured(decided_seed() if which == "decided" else consequence_seed())["run"]
    for a, b in M.IDENTITIES:
        for key in AN.IDENTITY_KEYS:
            assert run["clones"][a][key] == run["clones"][b][key], (a, key)
    assert run["boundary"]["W"]["A1"] != run["boundary"]["W"]["A2"]       # 移植の先は本当に違う重み（恒等の確かめが空でない）


def test_ct42_4_equal_weights_make_the_swap_systems_identical() -> None:
    """SE-T7：W^{A1} ＝ W^{A2}（構造的な 0 の合成の個体）なら、G^c[W^d] は G^c[W^c] と、N^c[W^d] は N^c[W^c] と同じ。"""
    run = zero_individual()["run"]
    assert run["boundary"]["W"]["A1"] == run["boundary"]["W"]["A2"]
    for a, b in M.STRUCTURAL_PAIRS + M.IDENTITIES:
        for key in AN.IDENTITY_KEYS:
            assert run["clones"][a][key] == run["clones"][b][key], (a, key)
    ind = AN.individual(run)
    assert all(ind["quantities"][k]["sign"] in ("0", None) for k in ("T_A1", "T_A2", "T", "TN_A1", "TN_A2", "TN"))


def test_o8_detects_tampering() -> None:
    s = decided_seed()
    for tamper in (lambda r: r["clones"]["G_A1_WA1_tr"]["activity"].pop(),
                   lambda r: r["clones"]["G_A2_WA2_tr"]["layer_b"].append([SMALL.end, "d", "s1", "A1"]),
                   lambda r: r["clones"]["G_A1_WA1_tr"]["sigma_end"]["units"][r["roles"]["cue"]].update(activity=9.0)):
        data = measured(s)
        tamper(data["run"])
        assert "O8" in failures(data, s)
    for tamper in (lambda r: r["clones"]["N_A2_WA1"]["activity"].append([SMALL.end, r["roles"]["cue"]]),
                   lambda r: r["clones"]["G_A1_WA2"]["sensory"].pop()):
        data = zero_individual()
        tamper(data["run"])
        assert "O8" in failures(data, CORNER_SEEDS[0])


# ---- CT-42-5 Pulse P_E ＋ 1 と帰還の対（SE-T5・SE-T6・O9・O10） -----------------------------------------------------

def _boundary_pair(fire: bool):
    """SMALL の本体を P_E まで進め、手がかりの Unit が P_E ＋ 1 に発火するように（fire）、またはどの Unit も発火しないように
    activity を置いてから二つに複製し、X1・X2 を移植して FREEZE し、P_E ＋ 1 まで進めた合成の系（契約テストだけ）。"""
    body = M.build_body(SMALL, CORNER_SEEDS[3], "A1", log=_log())
    A.advance_to(body.app, SMALL.p_e)
    roles = body.roles.as_dict()
    if fire:
        u = _inner(body, roles["cue"])
        st = u.export_state()
        u.import_state(st | {"activity": 2 * st["dynamics"]["threshold"]})
    else:
        for r in ("cue", "source1", "source2"):
            u = _inner(body, roles[r])
            u.import_state(u.export_state() | {"activity": 0.0})
    cids = M.role_cids(roles)
    pair = []
    for key in ("X1", "X2"):
        s = A.clone(body)
        s.transplant({cids[r]: v for r, v in M.extremes(PROTOCOL)[key].items()})
        s.declare(M._freeze_six(frozenset(cids.values())), label="S4")
        A.advance_to(s.app, SMALL.p_e + 1)
        pair.append(s)
    return pair, roles, cids


@pytest.mark.parametrize("fire", [True, False])
def test_ct42_5_at_p_e_plus_1_drives_differ_only_by_the_weights_of_the_sources_that_fired(fire) -> None:
    """SE-T5：重みだけが違う二つの系は、Pulse P_E ＋ 1 の発火・層 A・Unit の内部の状態が同じ。届く途中の駆動は、重みの差がある接続の
    送り手が P_E ＋ 1 に発火したときだけ、その接続の分が違う（差がある場合と、ない場合の両方）。"""
    (a, b), roles, cids = _boundary_pair(fire)
    first = SMALL.p_e + 1
    fa = sorted(u for p, u in a.log.activity() if p == first)
    assert fa == sorted(u for p, u in b.log.activity() if p == first) and (roles["cue"] in fa) is fire
    sa, sb = M._sigma(a), M._sigma(b)
    assert sa["units"] == sb["units"] and sa["exit"] == sb["exit"]
    da, db = sa["drives"], sb["drives"]
    assert [x[:2] + x[3:] for x in da] == [x[:2] + x[3:] for x in db]
    differ = {f"{x[0]}.main->{x[1]}" for x, y in zip(da, db) if x[2] != y[2]}
    x1, x2 = M.extremes(PROTOCOL)["X1"], M.extremes(PROTOCOL)["X2"]
    weighted = {cids[r] for r in M.ROLES6 if x1[r] != x2[r] and cids[r].split(".main->")[0] in fa}
    assert differ == weighted and bool(differ) is fire
    out: list[str] = []
    run = {"plan": dataclasses.asdict(SMALL), "clones": {"G_A1_X1": {"activity": [list(x) for x in a.log.activity()],
                                                                    "sigma_after_first": json.loads(json.dumps(sa))},
                                                         "G_A1_X2": {"activity": [list(x) for x in b.log.activity()],
                                                                     "sigma_after_first": json.loads(json.dumps(sb))}},
           "boundary": {"sigma_b": {"G_A1_X1": json.loads(json.dumps(M._sigma(a))), "G_A1_X2": json.loads(json.dumps(M._sigma(b)))}}}
    with pytest.MonkeyPatch.context() as mp:                             # 解析の道具が読み込んだ measure の対の組を差し替える
        mp.setattr(AN.M, "SAME_BACKGROUND_PAIRS", (("G_A1_X1", "G_A1_X2"),))
        AN._o9(run, out)
    assert out == []                                                     # 解析の O9 は、この形の差を許す


def test_ct42_5_the_feedback_pair_is_the_same_until_the_first_consequence() -> None:
    """SE-T6：G^c[W^c] と N^c[W^c] は、G^c[W^c] の U の最初の結果の刺激の Pulse の前まで、発火・感覚の出来事・層 A・層 B が同じ。
    U に結果の刺激がなければ、終わりまで同じで、Σ の違いは `world.respond` だけ（両方の場合を確かめる）。"""
    run = measured(consequence_seed())["run"]
    seen = 0
    for g, n in M.FEEDBACK_PAIRS:
        t = AN._first_consequence(run["clones"][g], SMALL.p_e)
        assert AN._first_consequence(run["clones"][n], SMALL.p_e) is None
        if t is None:
            continue
        seen += 1
        assert t >= SMALL.p_e + 1 + SMALL.offset + SMALL.delay - 1
        for key in ("activity", "sensory", "layer_b", "delta_log"):
            assert [x for x in run["clones"][g][key] if x[0] < t] == [x for x in run["clones"][n][key] if x[0] < t], key
    assert seen >= 1                                                     # 差がある場合が実際にある
    zero = zero_individual()["run"]
    for g, n in M.FEEDBACK_PAIRS:
        assert AN._first_consequence(zero["clones"][g], SMALL.p_e) is None
        for key in ("activity", "sensory", "layer_a", "layer_b", "delta_log"):
            assert zero["clones"][g][key] == zero["clones"][n][key], key
        assert [tuple(p) for p in AS1.sigma_diff(zero["clones"][g]["sigma_end"], zero["clones"][n]["sigma_end"])] == [RESPOND]


def test_o9_detects_tampering() -> None:
    s = decided_seed()
    for tamper in (lambda r: r["clones"]["G_A1_WA2"]["sigma_after_first"].update(pulse=SMALL.p_e + 2),
                   lambda r: r["clones"]["G_A2_X1"]["sigma_after_first"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["clones"]["N_A1_WA2"]["sigma_after_first"]["exit"].update(cursor=0),
                   lambda r: r["clones"]["G_A1_X2"]["activity"].insert(0, [SMALL.p_e + 1, "zz"]),
                   lambda r: r["clones"]["G_A2_WA1"]["sigma_after_first"]["drives"].append(["a", "b", 0.001, SMALL.p_e + 1])):
        data = measured(s)
        tamper(data["run"])
        assert "O9" in failures(data, s)


def test_o10_detects_tampering() -> None:
    s = consequence_seed()
    run = measured(s)["run"]
    g = next(g for g, _n in M.FEEDBACK_PAIRS if AN._first_consequence(run["clones"][g], SMALL.p_e) is not None)
    n = dict(M.FEEDBACK_PAIRS)[g]
    cue_r = run["roles"]["cue_receptor"]
    for tamper in (lambda r: r["clones"][n]["activity"].insert(0, [SMALL.p_e + 1, "zz"]),
                   lambda r: r["clones"][n]["world_end"]["reserved"].append([99, A.CONSEQUENCE, cue_r, SMALL.end, "d"])):
        data = measured(s)
        tamper(data["run"])
        assert "O10" in failures(data, s)
    data = zero_individual()
    data["run"]["clones"]["N_A1_WA1"]["layer_a"][-1].update(outcome="tie")
    assert "O10" in failures(data, CORNER_SEEDS[0])


# ---- CT-42-6 世界（SE-T3・O5） ---------------------------------------------------------------------------

def test_ct42_6_consequences_follow_only_rule_c_intents_and_n_systems_get_none_in_u() -> None:
    run = measured(consequence_seed())["run"]
    p_e = SMALL.p_e
    for n in M.SYSTEMS:
        rec = _rec(run, n)
        live = [x for x in rec["layer_b"] if x[3] == M.RULE_OF[n] and (n not in M.NO_RESPONSE or x[0] <= p_e)]
        cons = sorted((r[3], r[4]) for r in rec["world_end"]["reserved"] if r[1] == A.CONSEQUENCE)
        assert cons == sorted((p + SMALL.delay - 1, did) for p, did, _s, _a in live), n
        assert {r for _, r in rec["sensory"]} <= {run["roles"]["cue_receptor"]}
        if n in M.NO_RESPONSE:
            assert all(p <= p_e for p, _did in cons) and rec["world_end"]["rule"]["rule_c"] == M.RULE_OF[n]
    ind = AN.individual(run)
    aux = AN.auxiliary({"1": ind})
    assert all(aux["R5"][n]["as_expected"] is True for n in M.BODIES + M.CLONES)
    assert any(ind["consequences"][n]["U"] for n in ("G_A1_WA1", "G_A2_WA2"))     # 確かめが空でない


def test_ct42_6_switch_world_keeps_rule_c_and_is_recorded_once() -> None:
    """`switch_world(respond=False)`：規則 c は変わらず、切り替えた後に来た規則 c の意図にも結果を返さない。意図は記録する。
    記録は (境界の Pulse, 札, respond) の一つ。"""
    s = M.build_body(SMALL, SYN[0], "A1", log=_log())
    A.advance_to(s.app, SMALL.p_e)
    s.switch_world(False, label="S3'")
    assert s.world.rule_c == "A1" and s.world.respond is False and s.meta["world_switches"] == [(SMALL.p_e, "S3'", False)]
    before = len(s.world.reserved)
    s.world.receive_intent(SMALL.p_e + 5, "d-x", s.roles.source1, "A1")
    assert len(s.world.reserved) == before and s.world.intents[-1][1] == "d-x"
    run = measured(SYN[0])["run"]
    for n in M.CLONES:
        assert run["clones"][n]["world_switches"] == ([[SMALL.p_e, "S3'", False]] if n in M.NO_RESPONSE else [])
    assert all(run["bodies"][n]["world_switches"] == [] for n in M.BODIES + (M.RERUN,))


def test_o5_detects_tampering() -> None:
    s = consequence_seed()
    run = measured(s)["run"]
    src_r = A.RECEPTOR_OF[run["roles"]["source1"]]
    cue_r = run["roles"]["cue_receptor"]
    for tamper in (lambda r: r["bodies"]["B_A1"]["sensory"].append([5, src_r]),
                   lambda r: r["bodies"]["B_A2"]["world_end"]["reserved"].append([99, A.CONSEQUENCE, cue_r, 50, "d1"]),
                   lambda r: r["clones"]["G_A1_WA2"]["world_end"]["reserved"].append([99, A.EXOGENOUS, cue_r, 51, None]),
                   lambda r: r["clones"]["N_A2_WA1"]["world_end"]["reserved"].append([99, A.CONSEQUENCE, cue_r, SMALL.end, "d9"]),
                   lambda r: r["bodies"]["B_A1"]["world_end"]["realized"].pop(0),
                   lambda r: r["clones"]["G_A2_X1"]["world_end"]["cancelled"].append([98, A.CUE, cue_r, 9, None]),
                   lambda r: r["clones"]["N_A1_WA1"].update(world_switches=[]),
                   lambda r: r["clones"]["G_A1_WA1"].update(world_switches=[[SMALL.p_e, "S3'", False]]),
                   lambda r: r["clones"]["G_A2_WA2_tr"]["layer_a"][0].update(decision_pulse=-1),
                   lambda r: r["clones"]["N_A1_WA2"]["sensory"].pop()):
        data = measured(s)
        tamper(data["run"])
        assert "O5" in failures(data, s)


# ---- CT-42-7 F1・範囲・FREEZE（SE-T8・SE-T9・O7・O11） ----------------------------------------------------------

def test_ct42_7_weights_after_transplant_keep_f1_and_the_x_values() -> None:
    for data in (measured(decided_seed()), measured(FORMAL_SEED, FORMAL)):
        run = data["run"]
        cids = AN.role_cids(run["roles"])
        assert run["X"] == {k: {cids[r]: v for r, v in vals.items()} for k, vals in M.extremes(PROTOCOL).items()}
        ax = AX.extremes(AX.c0_values())
        assert M.extremes(PROTOCOL) == {"X1": ax["X1"], "X2": ax["X2"]}
        for n in M.CLONES:
            w = AN._weights_of(run["boundary"]["sigma_a"][n])
            assert w == AN._target(run, n) and all(0.0 <= v <= W_MAX for v in w.values())
            assert AN.pair_deviation(w) <= Fraction(AN.F1_TOLERANCE)
        for c in ("A1", "A2"):
            assert AN.pair_deviation(run["boundary"]["W"][c]) <= Fraction(AN.F1_TOLERANCE)
    cids = AN.role_cids({"cue": "s1", "source1": "s2", "source2": "s3"})
    for key in ("X1", "X2"):                                              # 端の値は組の和をちょうど w_max に保つ
        assert AN.pair_deviation({cids[r]: v for r, v in M.extremes(PROTOCOL)[key].items()}) == 0
    broken = {cids[r]: v for r, v in M.extremes(PROTOCOL)["X1"].items()} | {cids["source1_to_C"]: 1e-9}
    assert AN.pair_deviation(broken) > Fraction(AN.F1_TOLERANCE)


def test_ct42_7_freeze_holds_every_u_pulse() -> None:
    run = measured(consequence_seed())["run"]
    for n in M.CLONES:
        rows = run["clones"][n]["pulse_weights"]
        assert [p for p, _ in rows] == list(range(SMALL.p_e + 1, SMALL.end + 1))
        assert all(w == AN._as_row(run, AN._target(run, n)) for _p, w in rows)
    moved = any(AN._weights_of(run["bodies"][b]["sigma_end"]) != run["boundary"]["W"][M.RULE_OF[b]] for b in M.BODIES)
    assert moved                                                         # 可塑性のままの本体の重みは U で動く（確かめが空でない）


@pytest.mark.parametrize("rule_c", ["A1", "A2"])
def test_ct42_7_traces_do_not_affect_the_trajectory_when_all_six_are_frozen(rule_c) -> None:
    """SE-T9（0037 の命題 Q2-5）：全 6 本を止めた区間では、痕跡を進めても（advance）据え置いても（hold）、発火・層 A・層 B・
    感覚の出来事が同じ。Σ の違いは痕跡と介入の記録だけ。"""
    body = M.build_body(SMALL, CORNER_SEEDS[2], rule_c, log=_log())
    A.advance_to(body.app, SMALL.p_e)
    six = frozenset(M._weights(body))
    systems = []
    for policy in (AS1.ADVANCE, AS1.HOLD):
        s = A.clone(body)
        s.declare([AS1.Intervention(AS1.FREEZE, six, policy)], label="S4")
        A.advance_to(s.app, SMALL.end)
        systems.append(s)
    a, b = systems
    assert a.log.activity() == b.log.activity() and a.log.sensory() == b.log.sensory() and a.log.activity()
    assert a.decider.records == b.decider.records and a.world.intents == b.world.intents
    paths = {tuple(p[:1]) + (p[-1],) if p[0] == "connections" else tuple(p[:1])
             for p in AS1.sigma_diff(M._sigma(a), M._sigma(b))}
    assert paths and paths <= {("connections", "pre_trace"), ("connections", "post_trace"), ("interventions",)}


def test_o7_detects_tampering() -> None:
    s = decided_seed()
    for tamper in (lambda r: r["clones"]["G_A1_WA2"]["pulse_weights"].pop(),
                   lambda r: r["clones"]["N_A2_WA1"]["pulse_weights"][3][1].__setitem__(0, 0.0049),
                   lambda r: r["clones"]["G_A2_X1"]["pulse_weights"][0].__setitem__(0, SMALL.p_e)):
        data = measured(s)
        tamper(data["run"])
        assert "O7" in failures(data, s)


def test_o11_detects_tampering() -> None:
    s = decided_seed()
    for tamper in (lambda r: r["X"]["X1"].update({min(r["W_0"]): 0.006}),
                   lambda r: r["boundary"]["W"]["A2"].update({min(r["W_0"]): W_MAX + 0.001}),
                   lambda r: r["boundary"]["sigma_a"]["G_A1_X2"]["connections"][min(r["W_0"])].update(weight=-0.001),
                   lambda r: r["boundary"]["sigma_a"]["N_A1_WA2"]["connections"][min(r["W_0"])].update(
                       weight=r["boundary"]["sigma_a"]["N_A1_WA2"]["connections"][min(r["W_0"])]["weight"] + 1e-9)):
        data = measured(s)
        tamper(data["run"])
        assert "O11" in failures(data, s)


# ---- CT-42-8 命題 S-1・SE-T10（README §7.2） -------------------------------------------------------------

def test_ct42_8_the_bound_e_s_matches_the_preregistered_analysis() -> None:
    lam, w = LAMBDA, W_MAX
    e_s = w * ((1 + lam ** 4) / (1 - lam ** 23) + 2 / (1 - lam ** 7))
    assert AN.E_S == pytest.approx(e_s, abs=1e-15) and AN.E_S == pytest.approx(PROTOCOL["proposition_S1"]["E_S_value"], abs=5e-6)
    assert RC.bound_e_s(M.manifest_raw(), dataclasses.asdict(FORMAL)) == pytest.approx(AN.E_S, abs=1e-15)
    assert RC.bound_e_s(M.manifest_raw(), dataclasses.asdict(SMALL)) == pytest.approx(AN.E_S, abs=1e-15)
    assert AN.margin({"dynamics": {"intrinsic_drive_per_second": 0.08, "decay_per_second": 0.85, "threshold": 0.5}}) \
        == pytest.approx(0.08 / 0.15 - 0.5)


@pytest.mark.parametrize("silent", ["source1", "source2"])
def test_ct42_8_an_asymmetric_corner_source_never_fires_in_any_system_and_results_exist(silent) -> None:
    """命題 S-1・SE-T10（非対称な角）：一方の源を g ＜ −E_S に、もう一方の源と手がかりの Unit を最も発火しやすい角に置いた個体を、
    本番の Plan で measure_seed に通す。沈黙した源は 17 系（移植・端の値 X1・X2・結果を返さない世界を含む）のどれでも一度も発火しない。
    結果があること：もう一方の源はどの系でも発火し、どの系にも U の決まった窓があり、規則 c がその行動を指す本体では結果の刺激が
    成立している（真偽だけ。数・Pulse は表示しない）。その個体の T・T_N・S は定まり 0（SE-T10）。"""
    data = corner_individual(silent)
    run = data["run"]
    firing = "source2" if silent == "source1" else "source1"
    action = {"source1": "A1", "source2": "A2"}[firing]
    roles = run["roles"]
    for n in M.SYSTEMS:
        fired = {u for _p, u in _rec(run, n)["activity"]}
        assert roles[silent] not in fired and roles[firing] in fired, n
        u_windows = [r for r in _rec(run, n)["layer_a"] if r["window"] > FORMAL.e_windows]
        assert any(r["outcome"] == action for r in u_windows) and all(r["outcome"] in (action, A.NONE) for r in u_windows), n
    body = f"B_{action}"
    assert any(r[1] == A.CONSEQUENCE for r in run["bodies"][body]["world_end"]["reserved"])
    assert any(r[1] == A.CONSEQUENCE and r[3] > FORMAL.p_e for r in run["clones"][f"G_{action}_W{action}"]["world_end"]["reserved"])
    ind = AN.individual(run)
    assert ind["S1"] == {"silent_source": {silent: True, firing: False}, "violations": []}
    for k in ("T_A1", "T_A2", "T", "TN", "S"):
        assert ind["quantities"][k]["sign"] == "0", k                  # 定まり、ちょうど 0
    assert ind["class"] in ("structural_zero", "structural_identity", "both_zero") and ind["T_any"] is False


def test_ct42_8_both_sources_silent_give_a_structural_zero() -> None:
    run = zero_individual()["run"]
    roles = run["roles"]
    assert all(roles["source1"] not in {u for _p, u in _rec(run, n)["activity"]} for n in M.SYSTEMS)
    assert all(roles["source2"] not in {u for _p, u in _rec(run, n)["activity"]} for n in M.SYSTEMS)
    assert any(roles["cue"] in {u for _p, u in _rec(run, n)["activity"]} for n in M.SYSTEMS)
    ind = AN.individual(run)
    assert ind["S1"]["silent_source"] == {"source1": True, "source2": True} and ind["zero_label"] == "Z-1"
    assert ind["undefined_systems"] == list(AN.MAIN_FOUR) and ind["class"] == "undefined"   # 決まった窓がなく、s は定まらない


def test_ct42_8_the_s1_label_and_a_violation_are_reported_without_changing_the_judgment() -> None:
    s = decided_seed()
    run = measured(s)["run"]
    src = run["roles"]["source1"]
    d = run["birth_units"][src]["dynamics"]
    d["threshold"], d["intrinsic_drive_per_second"] = 0.55, 0.072    # 記録の上だけ、構造的に沈黙する源の値にする
    ind = AN.individual(run)
    assert ind["S1"]["silent_source"] == {"source1": True, "source2": False}
    fired = any(u == src for n in M.SYSTEMS for _, u in _rec(run, n)["activity"])
    assert ind["S1"]["violations"] == (["source1"] if fired else [])
    aux = AN.auxiliary({"1": ind})
    assert aux["R1"]["S1"]["labels_withdrawn"] is fired
    assert aux["R1"]["S1"]["individuals_with_silent_source"] == (None if fired else 1)
    dc = AN.descriptive_controls({"1": ind})["zero_table"]
    assert (dc["structurally_silent_source"] is None) is fired
    assert "S1" not in json.dumps(AN.judge({"1": ind})) and "S1" not in json.dumps(AN.estimate({"1": ind}))


# ---- CT-42-9 量と判定・推定の算術（README §3〜§5。手で作った記録） ----------------------------------------------

def _s(**given) -> dict:
    """17 系の s（既定は 1/2）。"""
    s = {n: Fraction(1, 2) for n in M.SYSTEMS}
    s.update(given)
    return s


def _person(s: dict, *, k_star: int | None = 1, identity: bool = False, zero_label: str | None = None,
            delta: Fraction = Fraction(0), silent=(False, False)) -> dict:
    """判定・推定・記述の算術の確かめ用の個体（道具の関数で、s から作る）。"""
    q = AX.quantities({n: s[n] for n in M.SYSTEMS if n != M.RERUN})
    return {"class": AN.classify(q["T"], q["T_A1"], q["T_A2"], k_star, identity), "T_any": q["T_any"],
            "quantities": {k: AN._quantity(q[k]) for k in AN.QUANTITY_NAMES}, "delta": AN._quantity(delta),
            "k_star": k_star, "zero_label": zero_label, "structural_identity": identity,
            "undefined_systems": [n for n in AN.MAIN_FOUR if s[n] is None],
            "S1": {"silent_source": {"source1": silent[0], "source2": silent[1]}, "violations": []},
            "s_U": {n: AN._frac(s[n]) for n in M.SYSTEMS}}


Q = Fraction(1, 4)
PLUS = _s(G_A1_WA1=Fraction(3, 4))                                   # T^(A1) ＝ ＋1/4、T^(A2) ＝ 0
MINUS = _s(G_A1_WA1=Q)
CANCEL = _s(G_A1_WA1=Fraction(3, 4), G_A2_WA1=Q)                     # T^(A1) ＝ ＋1/4、T^(A2) ＝ −1/4、T ＝ 0
EQUAL = _s()
UNDEF = _s(G_A2_WA2=None)


def _group(plus: int, minus: int, zero: int, undefined: int = 0) -> dict:
    rows = [_person(PLUS)] * plus + [_person(MINUS)] * minus + [_person(EQUAL, k_star=None, zero_label="Z-1")] * zero \
        + [_person(UNDEF)] * undefined
    return {str(i): copy.deepcopy(r) for i, r in enumerate(rows)}


def test_window_counts_share_and_undefined() -> None:
    la = _layer(["A1", "tie", "none", "A2", "A1", "A1", "none", "A2"])
    assert AN.window_counts(la, 1, 4) == {"windows": 4, "decided": 2, "A1": 1, "A2": 1, "tie": 1, "none": 1}
    assert RC.window_count(la, 1, 4) == AN.window_counts(la, 1, 4)
    assert AN.share(AN.window_counts(la, 5, 8)) == Fraction(2, 3)
    assert AN.share(AN.window_counts(_layer(["tie", "none"]), 1, 2)) is None        # 決まった窓が 0：定まらない（0 にしない）
    assert RC.a1_share(RC.window_count(_layer(["tie", "none"]), 1, 2)) is None
    assert [AN.sign(x) for x in (Fraction(1, 7), Fraction(-1, 7), Fraction(0))] == ["+", "-", "0"]


def test_every_quantity_is_the_exact_fraction_of_its_definition() -> None:
    f = Fraction
    s = {"B_A1": f(7, 12), "B_A2": f(5, 13), "B_A1_rerun": f(7, 12),
         "G_A1_WA1": f(9, 14), "G_A1_WA2": f(4, 7), "G_A1_WA1_tr": f(9, 14), "G_A2_WA2": f(4, 11), "G_A2_WA1": f(6, 11),
         "G_A2_WA2_tr": f(4, 11), "G_A1_X1": f(12, 13), "G_A1_X2": f(2, 13), "G_A2_X1": f(5, 6), "G_A2_X2": f(1, 12),
         "N_A1_WA1": f(3, 5), "N_A1_WA2": f(3, 5), "N_A2_WA2": f(2, 9), "N_A2_WA1": f(4, 9)}
    want = {"T_A1": f(9, 14) - f(4, 7), "T_A2": f(6, 11) - f(4, 11), "BE_WA1": f(9, 14) - f(6, 11), "BE_WA2": f(4, 7) - f(4, 11),
            "TE_F": f(9, 14) - f(4, 11), "D": f(7, 12) - f(5, 13), "S_A1": f(10, 13), "S_A2": f(5, 6) - f(1, 12),
            "TN_A1": f(0), "TN_A2": f(4, 9) - f(2, 9), "K_A1": f(9, 14) - f(3, 5), "K_A2": (1 - f(4, 11)) - (1 - f(2, 9)),
            "Z_A1": f(7, 12) - f(9, 14), "Z_A2": (1 - f(5, 13)) - (1 - f(4, 11))}
    want |= {"T": want["T_A1"] + want["T_A2"], "BE": want["BE_WA1"] + want["BE_WA2"], "S": want["S_A1"] + want["S_A2"],
             "TN": want["TN_A1"] + want["TN_A2"], "T_any": True}
    q = AX.quantities({n: v for n, v in s.items() if n != M.RERUN})
    assert q == want == AN.written_out_quantities(s) == RC.definitions(s)
    assert q["TE_F"] == (q["T"] + q["BE"]) / 2                              # 算術の恒等（本当の内訳とは呼ばない）
    assert AN._quantity(q["T"]) == {"value": {"num": q["T"].numerator, "den": q["T"].denominator, "value": float(q["T"])},
                                    "sign": "+"}


def test_the_quantities_are_undefined_when_any_s_they_use_is_undefined() -> None:
    for name, systems in AN.QUANTITY_SYSTEMS.items():
        for n in systems:
            q = AX.quantities({k: v for k, v in _s(**{n: None}).items() if k != M.RERUN})
            assert q[name] is None, (name, n)
            assert RC.definitions(_s(**{n: None}))[name] is None
    q = AX.quantities({k: v for k, v in UNDEF.items() if k != M.RERUN})
    assert q["T"] is None and q["T_any"] is None and q["T_A1"] == 0 and q["D"] == 0


def _hand_run() -> dict:
    """系ごとの窓の結末の列（手で置く）。U は窓 5〜8（SMALL の E ＝ 窓 1〜4）。"""
    u = {"B_A1": ["A1", "A1", "A2", "tie"], "B_A2": ["A2", "none", "A1", "A2"], "B_A1_rerun": ["A1", "A1", "A2", "tie"],
         "G_A1_WA1": ["A1", "A1", "A1", "A2"], "G_A1_WA2": ["A1", "A2", "tie", "none"], "G_A1_WA1_tr": ["A1", "A1", "A1", "A2"],
         "G_A2_WA2": ["A2", "A2", "A1", "none"], "G_A2_WA1": ["A1", "A1", "A2", "A2"], "G_A2_WA2_tr": ["A2", "A2", "A1", "none"],
         "G_A1_X1": ["A1", "A1", "A1", "A1"], "G_A1_X2": ["A2", "tie", "A2", "A1"], "G_A2_X1": ["A1", "A2", "A1", "none"],
         "G_A2_X2": ["A2", "A2", "A2", "A2"], "N_A1_WA1": ["A1", "A2", "none", "none"], "N_A1_WA2": ["A2", "A2", "A1", "tie"],
         "N_A2_WA2": ["A2", "A1", "A2", "A2"], "N_A2_WA1": ["none", "A1", "A1", "A2"]}
    return {n: _layer(["none", "tie", "A1", "A2"] + outs) for n, outs in u.items()}


def _s_from_layers(layers: dict) -> dict:
    return {n: AN.share(AN.window_counts(la, SMALL.e_windows + 1, SMALL.count)) for n, la in layers.items()}


def test_the_quantities_from_hand_made_layers() -> None:
    s = _s_from_layers(_hand_run())
    assert (s["G_A1_WA1"], s["G_A1_WA2"], s["G_A2_WA2"], s["G_A2_WA1"]) == (Fraction(3, 4), Fraction(1, 2), Fraction(1, 3),
                                                                            Fraction(1, 2))
    q = AX.quantities({n: v for n, v in s.items() if n != M.RERUN})
    assert q["T_A1"] == Fraction(1, 4) and q["T_A2"] == Fraction(1, 2) - Fraction(1, 3) and q["T"] == Fraction(5, 12)
    assert q["TE_F"] == (q["T"] + q["BE"]) / 2 and q["S_A1"] == 1 - Fraction(1, 3) and q["S_A2"] == Fraction(2, 3)
    assert q == RC.definitions(s) == AN.written_out_quantities(s)


def _flip(outcome):
    return {"A1": "A2", "A2": "A1"}.get(outcome, outcome)


def test_the_label_swap_on_hand_made_records() -> None:
    """SE-T11：記録の札を入れ替える（系の名前を SWAP で写し、窓の結末の A1・A2 を入れ替える）と、道具が記録から計算する
    T・BE・TE_F・D・S・T_N と T_any は正確に同じ、背景ごとの量の組は入れ替わる。T を −T に移さない（符号の対称の根拠ではない）。"""
    layers = _hand_run()
    swapped = {AX.SWAP[n]: [dict(r, outcome=_flip(r["outcome"])) for r in la] for n, la in layers.items() if n != M.RERUN}
    q = AX.quantities({n: v for n, v in _s_from_layers(layers).items() if n != M.RERUN})
    r = AX.quantities(_s_from_layers(swapped))
    assert all(r[k] == q[k] for k in AX.INVARIANT) and all((r[a], r[b]) == (q[b], q[a]) for a, b in AX.EXCHANGED)
    assert q["T"] != 0 and r["T"] == q["T"] != -q["T"]


def _swap_run(run: dict) -> dict:
    """生の記録の札を入れ替える：源 1 と源 2 の役、系の名前（AX.SWAP。B′^{A1} はそのまま）、窓の結末と行動 ID、W^{A1} と W^{A2}。"""
    r = copy.deepcopy(run)
    sw = {k: v for k, v in AX.SWAP.items() if k != M.RERUN}
    r["bodies"] = {sw.get(n, n): v for n, v in r["bodies"].items()}
    r["clones"] = {sw[n]: v for n, v in r["clones"].items()}
    for rec in list(r["bodies"].values()) + list(r["clones"].values()):
        for x in rec["layer_a"]:
            x["outcome"], x["action"] = _flip(x["outcome"]), _flip(x["action"])
    r["roles"] = dict(r["roles"], source1=run["roles"]["source2"], source2=run["roles"]["source1"])
    r["boundary"]["W"] = {"A1": run["boundary"]["W"]["A2"], "A2": run["boundary"]["W"]["A1"]}
    return r


@pytest.mark.parametrize("seed_of", ["decided", "consequence", "formal"])
def test_ct42_9_the_label_swap_on_the_records_of_synthetic_individuals(seed_of) -> None:
    """CT-42-9（SE-T11）：合成の個体の生の記録の札を入れ替えて、道具（analyze.individual）が計算し直した量：T・BE・TE_F・D・S・T_N・δ
    と T_any は正確に同じ、背景ごとの量の組は入れ替わる。独立の検算（recheck.individual）も同じ（値は表示しない）。"""
    run = (measured(decided_seed()) if seed_of == "decided" else measured(consequence_seed()) if seed_of == "consequence"
           else measured(FORMAL_SEED, FORMAL))["run"]
    before, after = AN.individual(run), AN.individual(_swap_run(run))
    for k in AX.INVARIANT:
        if k != "T_any":
            assert after["quantities"][k] == before["quantities"][k], k
    for a, b in AX.EXCHANGED:
        assert (after["quantities"][a], after["quantities"][b]) == (before["quantities"][b], before["quantities"][a]), a
    assert after["T_any"] == before["T_any"] and after["delta"] == before["delta"]
    data = {"meta": _meta(run["seed"]), "run": _swap_run(run)}
    mine = RC.individual(data)
    assert mine["quantities"] == after["quantities"] and mine["delta"] == after["delta"]


def test_delta_uses_the_binary64_values_and_is_label_invariant() -> None:
    a, b = 0.1 + 0.2, 0.3
    roles = {"cue": "s1", "source1": "s2", "source2": "s3"}
    cids = AN.role_cids(roles)
    w1 = {cid: W0 for cid in cids.values()} | {cids["C_to_source1"]: a / 50}
    w2 = {cid: W0 for cid in cids.values()} | {cids["C_to_source1"]: b / 50}
    assert AN.delta_of(roles, w1, w2) == Fraction(a / 50) - Fraction(b / 50) != Fraction(str(a / 50)) - Fraction(str(b / 50))
    swapped_roles = dict(roles, source1="s3", source2="s2")
    assert AN.delta_of(swapped_roles, w2, w1) == AN.delta_of(roles, w1, w2)
    assert AX.delta_label_swap_check()["delta_invariant_under_label_swap"] is True
    for src in (inspect.getsource(AN.individual), inspect.getsource(AN.delta_of), inspect.getsource(AN.pair_deviation),
                inspect.getsource(RC.individual), inspect.getsource(RC.max_pair_gap)):
        assert "Fraction(str(" not in src


def test_the_classification_of_readme_section_4_1() -> None:
    f = Fraction
    assert AN.classify(None, None, None, 1, False) == "undefined"
    assert AN.classify(f(1, 4), f(1, 4), f(0), 1, False) == "plus" and AN.classify(f(-1, 4), f(0), f(-1, 4), 1, False) == "minus"
    assert AN.classify(f(0), f(0), f(0), None, True) == "structural_zero"
    assert AN.classify(f(0), f(0), f(0), 3, True) == "structural_identity"
    assert AN.classify(f(0), f(0), f(0), 3, False) == "both_zero"
    assert AN.classify(f(0), f(1, 4), f(-1, 4), 3, False) == "cancellation"
    assert [_person(x)["class"] for x in (PLUS, MINUS, CANCEL, EQUAL, UNDEF)] == ["plus", "minus", "cancellation", "both_zero",
                                                                                   "undefined"]


def test_a_cancellation_is_t_zero_and_counts_in_p_any_not_in_p_nz() -> None:
    p = _person(CANCEL)
    assert p["quantities"]["T"]["sign"] == "0" and p["T_any"] is True and p["class"] == "cancellation"
    e = AN.estimate({"1": p, "2": _person(EQUAL)})
    assert (e["m_def"], e["m_nonzero"], e["p_nz"]["count"], e["p_any"]["count"], e["cancellations"]) == (2, 0, 0, 1, 1)
    assert e["p_dir"]["interval"]["computed"] is False                       # 0 でない個体がなければ p_dir は計算できない


@pytest.mark.parametrize("plus", [True, False])
@pytest.mark.parametrize("m", [10, 200])
def test_j_t_at_the_k2_boundary_in_both_directions(plus, m) -> None:
    k = PROTOCOL["judgment"]["k2_of_m"][m]
    assert k == AN.k2_of_m(m) == AX.k2(m) == RC.k2(m, Fraction(1, 40)) and (m, k) in ((10, 9), (200, 115))

    def g(x, rest, zero=3, undefined=2):
        return _group(x, rest, zero, undefined) if plus else _group(rest, x, zero, undefined)
    j = AN.judge(g(k, m - k))
    assert (j["J_T"]["m_nonzero"], j["J_T"]["m_def"], j["J_T"]["k2"], j["J_T"]["status"]) == (m, m + 3, k, "established")
    assert j["J_T"]["direction"] == ("+" if plus else "-") and j["outcome"] == ("plus" if plus else "minus")
    assert j["J_T"]["counts"]["0"] == 3 and j["J_T"]["counts"]["undefined"] == 2
    assert j["J_T"]["tail_probability"] == float(AN.binom_upper_tail(m, k)) <= 0.025
    j = AN.judge(g(k - 1, m - k + 1))
    assert (j["J_T"]["status"], j["J_T"]["direction"], j["outcome"]) == ("not_established", None, "not_established")
    assert RC.judgment(list(g(k, m - k).values()))["outcome"] == ("plus" if plus else "minus")
    assert RC.compare(RC.judgment(list(g(k - 1, m - k + 1).values())), AN.judge(g(k - 1, m - k + 1)))[1] == []


def test_j_t_is_inconclusive_below_10_and_zeros_and_undefined_never_count() -> None:
    j = AN.judge(_group(9, 0, 50, 20))
    assert (j["J_T"]["m_nonzero"], j["J_T"]["status"], j["outcome"], j["J_T"]["k2"]) == (9, "inconclusive", "inconclusive", None)
    assert j["J_T"]["m_def"] == 59 and "prominence" in j
    assert AN.judge(_group(10, 0, 0))["outcome"] == "plus" and AN.judge(_group(0, 0, 200))["outcome"] == "inconclusive"
    assert RC.compare(RC.judgment(list(_group(9, 0, 50, 20).values())), j)[1] == []


def test_k2_table_matches_the_protocol_and_the_binomial() -> None:
    table = PROTOCOL["judgment"]["k2_of_m"]
    assert sorted(table) == list(range(10, 201))
    assert all(table[m] == AN.k2_of_m(m) == RC.k2(m, Fraction(1, 40)) for m in table)
    assert AN.binom_upper_tail(200, 115) <= Fraction(1, 40) < AN.binom_upper_tail(200, 114)
    broken = copy.deepcopy(PROTOCOL)
    broken["judgment"]["k2_of_m"][200] = 114
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(AN, "PROTOCOL", broken)
        with pytest.raises(ValueError, match="k₂"):
            AN.judge(_group(115, 85, 0))


def test_the_estimate_e_t_fields() -> None:
    rows = {"1": _person(PLUS), "2": _person(PLUS), "3": _person(MINUS), "4": _person(CANCEL), "5": _person(EQUAL),
            "6": _person(EQUAL, k_star=None, zero_label="Z-2"), "7": _person(UNDEF)}
    e = AN.estimate(rows)
    assert (e["m_def"], e["m_nonzero"], e["cancellations"]) == (6, 3, 1)
    assert (e["p_nz"]["count"], e["p_nz"]["denominator"], e["p_any"]["count"], e["p_any"]["denominator"]) == (3, 6, 4, 6)
    assert (e["p_plus"]["count"], e["p_minus"]["count"], e["p_dir"]["count"], e["p_dir"]["denominator"]) == (2, 1, 2, 3)
    assert e["p_nz"]["proportion"] == 3 / 6 and e["p_nz"]["interval"]["computed"] and e["p_any"]["interval"]["denominator"] == 6
    assert e["cancellations"] == e["p_any"]["count"] - e["p_nz"]["count"]
    assert e["abs_T"]["defined"]["count"] == 6 and e["abs_T"]["nonzero"]["count"] == 3 and e["abs_T"]["nonzero"]["max"] == 0.25
    assert e["undefined"] == {"count": 1, "by_number_of_undefined_systems": {"1": 1, "2": 0, "3": 0, "4": 0},
                              "by_background": {"A1": 0, "A2": 1}}
    assert "threshold" not in json.dumps({k: v for k, v in e.items() if k != "notes"})
    assert RC.compare(RC.estimate(list(rows.values())), e)[1] == []         # 区間の端点だけ、書き方の違いを 1e-9 まで許す


def test_the_descriptive_controls_report_the_required_tables() -> None:
    rows = {"10": _person(PLUS, delta=Fraction(1, 100)), "11": _person(MINUS, delta=Fraction(-1, 100)), "12": _person(CANCEL),
            "13": _person(EQUAL, k_star=None, zero_label="Z-1"), "14": _person(EQUAL, k_star=3, identity=True),
            "15": _person(UNDEF), "16": _person(EQUAL, silent=(True, False))}
    dc = AN.descriptive_controls(rows)
    pb = dc["per_background"]
    assert pb["order"] == ["T_A1", "T_A2"] and pb["in_both"] == 6 and pb["only_T_A1"] == 1 and pb["only_T_A2"] == 0
    assert pb["cells"]["+0"] == 1 and pb["cells"]["-0"] == 1 and pb["cells"]["+-"] == 1 and pb["cells"]["00"] == 3
    assert pb["opposite_cells_by_sign_of_T"] == {"+": 0, "-": 0, "0": 1}
    assert dc["quantities"]["T"]["defined"] == 6 and dc["quantities"]["T"]["counts"] == {"+": 1, "-": 1, "0": 4}
    assert dc["quantities"]["T"]["proportion"]["+"]["denominator"] == 6 and dc["quantities"]["T"]["plus_among_nonzero"]["count"] == 1
    assert dc["quantities"]["delta"]["counts"] == {"+": 1, "-": 1, "0": 5}
    assert dc["cross_with_T"]["delta"]["cells"]["++"] == 1 and dc["cross_with_T"]["delta"]["cells"]["--"] == 1
    assert set(dc["cross_with_T"]) == {"D", "S", "TN", "delta"} and all(len(t["cells"]) == 9 for t in dc["cross_with_T"].values())
    assert dc["two_by_two"]["s_U"]["G_A1_WA1"]["count"] == 7 and dc["two_by_two"]["identity_note"] == AN.NOTES["identity"]
    assert dc["diverged_subpopulation"]["m_def"] == 5 and dc["diverged_subpopulation"]["p_any"]["count"] == 3
    zt = dc["zero_table"]
    assert zt["structural_zero"] == {"Z-1": ["13"], "Z-2": []} and zt["structural_identity"] == ["14"]
    assert zt["both_zero"] == ["16"] and zt["cancellation"] == ["12"] and zt["undefined"] == {"15": ["G_A2_WA2"]}
    assert zt["structurally_silent_source"] == ["16"]
    assert RC.compare(RC.controls(rows), dc)[1] == []
    swapped = {k: copy.deepcopy(v) for k, v in rows.items()}               # 札を入れ替えると、背景ごとの 9 つの組は転置する
    for v in swapped.values():
        q = v["quantities"]
        q["T_A1"], q["T_A2"] = q["T_A2"], q["T_A1"]
    cells = AN.descriptive_controls(swapped)["per_background"]["cells"]
    assert all(cells[a + b] == pb["cells"][b + a] for a in AN.SIGNS for b in AN.SIGNS)


def test_clopper_pearson_known_values() -> None:
    lo, hi = AN.clopper_pearson(0, 10)
    assert lo == 0.0 and hi == pytest.approx(1 - 0.025 ** 0.1, abs=1e-9)
    lo, hi = AN.clopper_pearson(10, 10)
    assert hi == 1.0 and lo == pytest.approx(0.025 ** 0.1, abs=1e-9)
    lo, hi = AN.clopper_pearson(5, 10)
    assert lo == pytest.approx(0.187086, abs=1e-5) and hi == pytest.approx(0.812914, abs=1e-5)
    assert AN.interval(0, 0) == {"computed": False, "interval": None, "numerator": 0, "denominator": 0,
                                 "reason": "denominator = 0"} == RC.interval_of(0, 0)
    for x, n in ((0, 200), (115, 200), (37, 120)):
        assert RC.exact_interval(x, n) == pytest.approx(AN.clopper_pearson(x, n), abs=1e-9)


def test_five_numbers() -> None:
    assert AN.five_numbers([]) is None and AN.five_numbers([3])["median"] == 3
    assert AN.five_numbers([1, 2, 3, 4, 5]) == {"count": 5, "min": 1, "q1": 2.0, "median": 3.0, "q3": 4.0, "max": 5}
    assert RC.five([1, 2, 3, 4, 5]) == AN.five_numbers([1, 2, 3, 4, 5])


def test_the_first_divergences_on_hand_made_records() -> None:
    assert AN.first_divergence([[3, "a"], [5, "b"]], [[3, "a"], [6, "b"]], 1, 9) == 5
    assert AN.first_divergence([[3, "a"]], [[3, "a"]], 1, 9) is None and AN.first_divergence([[3, "a"]], [[3, "b"]], 4, 9) is None
    la, lb = _layer(["none", "A1", "tie"]), _layer(["none", "A2", "tie"])
    assert AN.first_window_divergence(la, lb) == 2 and AN.first_window_divergence(la, la) is None
    assert RC.first_split([[3, "a"], [5, "b"]], [[3, "a"], [6, "b"]], 1, 9) == 5 and RC.first_outcome_split(la, lb) == 2


def test_t_p_nz_and_p_any_are_recomputed_from_the_records() -> None:
    """審査の重点：実際の記録（合成の個体の生の記録）から、ここで独立に数え直した s と T・T_any・p_nz・p_any の数が、解析の report
    と独立の検算に一致する（値は表示しない。一致の真偽だけ）。"""
    runs = {s: measured(s) for s in SYN[:5]} | {decided_seed(): measured(decided_seed()), consequence_seed(): measured(consequence_seed())}
    report = json.loads(json.dumps(AN.analyze_runs(runs, "synthetic", SMALL, o1=[])))
    assert report["valid"] is True
    defined = nonzero = any_bg = 0
    for seed, data in runs.items():
        run = data["run"]
        s = {}
        for n in AN.MAIN_FOUR:
            outs = [r["outcome"] for r in run["clones"][n]["layer_a"] if r["window"] > SMALL.e_windows]
            a1, a2 = outs.count("A1"), outs.count("A2")
            s[n] = Fraction(a1, a1 + a2) if a1 + a2 else None
        ind = report["individuals"][str(seed)]
        if None in s.values():
            assert ind["quantities"]["T"]["value"] is None and ind["class"] == "undefined"
            continue
        t1, t2 = s["G_A1_WA1"] - s["G_A1_WA2"], s["G_A2_WA1"] - s["G_A2_WA2"]
        got = ind["quantities"]["T"]["value"]
        assert Fraction(got["num"], got["den"]) == t1 + t2 and ind["T_any"] is (t1 != 0 or t2 != 0)
        defined += 1
        nonzero += t1 + t2 != 0
        any_bg += t1 != 0 or t2 != 0
    est = report["estimate"]
    assert (est["m_def"], est["p_nz"]["count"], est["p_any"]["count"]) == (defined, nonzero, any_bg)
    assert est["cancellations"] == any_bg - nonzero and defined >= 1
    assert RC.recheck(runs, report)["mismatches"] == []


# ---- CT-42-11 独立の検算：合成の個体の解析と report のすべての欄 ---------------------------------------------------

def test_the_analysis_of_the_synthetic_individuals_runs_through_and_the_recheck_agrees() -> None:
    """合成の個体の解析が最後まで通る。標準のライブラリだけの独立の検算（recheck.py）が、report と一つずつ一致する。値は表示しない。"""
    runs = {s: measured(s) for s in SYN}
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=[])
    assert report["valid"] is True and set(report) == {"mode", "valid", "O1", "gate_declaration_sha256", "judgment", "estimate",
                                                       "descriptive_controls", "individuals", "auxiliary"}
    j = report["judgment"]
    assert j["outcome"] in PROTOCOL["judgment"]["outcomes"] and j["J_T"]["m_def"] == report["estimate"]["m_def"]
    assert sum(j["J_T"]["counts"].values()) == len(SYN)
    assert set(report["auxiliary"]) == {f"R{i}" for i in range(1, 10)}
    assert report["auxiliary"]["R4"]["pair_sum_max_abs_deviation"] <= AN.F1_TOLERANCE
    assert report["auxiliary"]["R4"]["clones_after_transplant"]["pair_sum_max_abs_deviation"] <= AN.F1_TOLERANCE
    assert all(report["auxiliary"]["R5"][n]["as_expected"] is True for n in M.BODIES + M.CLONES)
    assert set(report["descriptive_controls"]) == {"quantities", "per_background", "two_by_two", "cross_with_T",
                                                   "diverged_subpopulation", "zero_table"}
    result = RC.recheck(runs, json.loads(json.dumps(report)))
    assert result["mismatches"] == [] and result["checks"] > 1000


def test_the_recheck_is_independent_and_detects_a_changed_report_or_raw() -> None:
    src = (EXP / "recheck.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    modules = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} \
        | {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert modules <= {"argparse", "copy", "gzip", "hashlib", "json", "math", "statistics", "sys", "collections", "fractions",
                       "pathlib"}
    assert "spec_from_file_location" not in src and "__import__" not in src and "exec(" not in src
    runs = {s: measured(s) for s in SYN[:4]}
    report = json.loads(json.dumps(AN.analyze_runs({s: measured(s) for s in SYN[:4]}, "synthetic", SMALL, o1=[])))
    assert RC.recheck(runs, report)["mismatches"] == []
    k = str(SYN[0])
    for tamper in (lambda rep, raw: rep["judgment"]["J_T"]["counts"].update({"+": rep["judgment"]["J_T"]["counts"]["+"] + 1}),
                   lambda rep, raw: rep["judgment"].update(outcome="plus" if rep["judgment"]["outcome"] != "plus" else "minus"),
                   lambda rep, raw: rep["estimate"]["p_nz"].update(count=rep["estimate"]["p_nz"]["count"] + 1),
                   lambda rep, raw: rep["estimate"]["p_any"].update(count=rep["estimate"]["p_any"]["count"] + 1),
                   lambda rep, raw: rep["individuals"][k]["quantities"]["T"].update(sign="?"),
                   lambda rep, raw: rep["individuals"][k].update(k_star="?"),
                   lambda rep, raw: raw[SYN[1]]["run"]["clones"]["G_A1_WA2"]["pulse_weights"][3][1].__setitem__(0, 0.0011),
                   lambda rep, raw: raw[SYN[1]]["run"]["bodies"][M.RERUN]["layer_b"].append([9, "d", "s1", "A1"]),
                   lambda rep, raw: raw[SYN[3]]["run"]["bodies"][M.RERUN]["sigma_p_e"]["units"][
                       raw[SYN[3]]["run"]["roles"]["cue"]].update(activity=9.0),
                   lambda rep, raw: raw[SYN[2]]["run"]["clones"]["G_A2_WA1"]["layer_a"][-1].update(outcome="tie")):
        rep, raw = copy.deepcopy(report), copy.deepcopy(runs)
        tamper(rep, raw)
        assert RC.recheck(raw, rep)["mismatches"]


COMMIT = "a" * 40                                                    # 照合の形だけを確かめる測定の commit（合成）
GENERIC = (set(M.SYSTEMS) | set(M.ROLES6) | {"A1", "A2", "X1", "X2", "+", "-", "0", "cue", "source1", "source2", "E", "U"}
           | {f"{a}|{b}" for a, b in M.R6_PAIRS} | {"B_A1|B_A2"} | set(AN.QUANTITY_NAMES) | {"delta"})


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


def _pattern(path) -> tuple:
    """欄の場所の形（seed・系・役・量の名前・列の位置を * にする）。同じ形の欄は、同じ書き方で照合される。"""
    return tuple("*" if isinstance(k, int) or k in GENERIC or (isinstance(k, str) and k.isdigit()) else k for k in path)


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
    """合成の個体（SYN[0]・k* のある個体・U に結果の刺激がある個体〔重なれば 2 個体〕と、構造的な 0 の構成の 1 個体：k* と札と
    s の欄に、値と null の両方が出る）。"""
    return {SYN[0]: measured(SYN[0]), decided_seed(): measured(decided_seed()), consequence_seed(): measured(consequence_seed()),
            CORNER_SEEDS[0]: zero_individual()}


@functools.cache
def _analyzed() -> str:
    """合成の個体（_runs3）の解析の report（解析の main と同じく measurement_commit を書き足した形。JSON を通す）。"""
    return json.dumps(AN.analyze_runs(_runs3(), "synthetic", SMALL, o1=[]) | {"measurement_commit": COMMIT})


def test_the_recheck_rebuilds_the_whole_report_and_compares_every_field() -> None:
    """raw から report の全体を組み立て直し、すべての葉を照合する（比べた葉の数 ＝ report の葉の数）。欄の形ごとに、その形の最初の葉の
    値を変えても、どの欄を消しても足しても、照合が失敗する（合成の個体の値は表示しない。失敗の文は場所だけ）。"""
    runs = _runs3()
    report = json.loads(_analyzed())
    mine = RC.expected_report(runs, COMMIT)
    checks, found = RC.compare(mine, report)
    paths = list(_leaves(report))
    scalars = [p for p in paths if not isinstance(_at(report, p), (dict, list))]
    assert found == [] and checks == len(scalars) > 3000                     # すべての葉を比べている
    assert {p[0] for p in paths} == set(report) == {"mode", "valid", "O1", "gate_declaration_sha256", "judgment", "estimate",
                                                    "descriptive_controls", "individuals", "auxiliary", "measurement_commit"}
    seen: set = set()
    for p in paths:
        if _pattern(p) in seen:
            continue
        seen.add(_pattern(p))
        parent = _at(report, p[:-1])
        before = parent[p[-1]]
        parent[p[-1]] = _changed(before)
        assert RC.compare(mine, report)[1], p
        parent[p[-1]] = before
    assert len(seen) > 300
    nodes = {q[:i] for q in paths for i in range(len(q)) if isinstance(_at(report, q[:i]), dict)}
    seen_nodes: set = set()
    for p in sorted(nodes, key=len):
        if _pattern(p) in seen_nodes:
            continue
        seen_nodes.add(_pattern(p))
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
    assert RC._loose("report.judgment.J_T.x.interval.interval[0]") and RC._loose("report.auxiliary.R1.S1.E_S")
    assert not RC._loose("report.estimate.p_nz.proportion") and not RC._loose("report.individuals.35301.birth.cue.margin_g")
    assert not RC._loose("report.individuals.35301.quantities.T.value.value")
    report = json.loads(_analyzed())
    mine = RC.expected_report(_runs3(), COMMIT)
    margin = report["individuals"][str(SYN[0])]["birth"]["cue"]
    margin["margin_g"] += 1e-12                                              # 書き方の同じ数は、わずかな違いも見つける
    assert RC.compare(mine, report)[1] == [f"report.individuals.{SYN[0]}.birth.cue.margin_g"]
    margin["margin_g"] -= 1e-12
    report["valid"] = 1                                                      # 真偽と数を取り違えない
    assert RC.compare(mine, report)[1] == ["report.valid"]


TARGETS = [("judgment", "J_T", "m_nonzero"), ("judgment", "J_T", "m_def"), ("judgment", "J_T", "counts"), ("judgment", "outcome"),
           ("judgment", "prominence"), ("estimate", "p_nz", "count"), ("estimate", "p_nz", "interval"),
           ("estimate", "p_any", "count"), ("estimate", "p_any", "interval"), ("estimate", "cancellations"),
           ("estimate", "p_dir"), ("estimate", "abs_T"), ("estimate", "undefined"), ("estimate", "notes"),
           ("descriptive_controls", "quantities", "T"), ("descriptive_controls", "quantities", "delta"),
           ("descriptive_controls", "per_background"), ("descriptive_controls", "two_by_two"),
           ("descriptive_controls", "cross_with_T", "D"), ("descriptive_controls", "cross_with_T", "S"),
           ("descriptive_controls", "cross_with_T", "TN"), ("descriptive_controls", "cross_with_T", "delta"),
           ("descriptive_controls", "diverged_subpopulation"), ("descriptive_controls", "zero_table"),
           ("auxiliary", "R1"), ("auxiliary", "R1", "S1", "E_S"), ("auxiliary", "R2", "N_A2_WA1"), ("auxiliary", "R3", "K_A2"),
           ("auxiliary", "R4", "W_A1"), ("auxiliary", "R4", "abs_W_diff"), ("auxiliary", "R4", "clones_after_transplant"),
           ("auxiliary", "R5", "N_A1_WA2"), ("auxiliary", "R6"), ("auxiliary", "R7", "G_A2_X1"), ("auxiliary", "R8"),
           ("auxiliary", "R9"),
           ("individuals", None, "quantities"), ("individuals", None, "delta"), ("individuals", None, "T_any"),
           ("individuals", None, "class"), ("individuals", None, "s_U"), ("individuals", None, "s_E"),
           ("individuals", None, "counts_U"), ("individuals", None, "counts_E"), ("individuals", None, "W"),
           ("individuals", None, "W_abs_diff"), ("individuals", None, "pair_deviation"),
           ("individuals", None, "clone_pair_deviation"), ("individuals", None, "consequences"),
           ("individuals", None, "first_divergence"), ("individuals", None, "firing"), ("individuals", None, "birth"),
           ("individuals", None, "roles"), ("individuals", None, "S1"), ("individuals", None, "k_star"),
           ("individuals", None, "structural_identity"), ("individuals", None, "undefined_systems"), ("mode",), ("O1",),
           ("gate_declaration_sha256",), ("measurement_commit",)]


@pytest.mark.parametrize("target", TARGETS, ids=lambda t: ".".join(str(x) for x in t if x))
def test_the_recheck_fails_when_any_field_is_changed(target) -> None:
    """report のどの欄（J_T の数、E_T の p_nz・p_any・打ち消し、必ず報告する記述、R1〜R9、個体の量・s・重み・発火など）を変えても、
    recheck が失敗する。"""
    runs = _runs3()
    report = json.loads(_analyzed())
    assert RC.recheck(runs, report, COMMIT)["mismatches"] == []
    prefix = tuple(str(consequence_seed()) if k is None else k for k in target)
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
    s = consequence_seed()
    assert RC.operation_problems(measured(s)) == [] and RC.operation_problems(zero_individual()) == []
    for tamper in (lambda r: r["bodies"]["B_A1"]["layer_b"].pop(),
                   lambda r: r["bodies"]["B_A2"]["world_end"]["reserved"].append([99, "consequence", "x", 5, "d"]),
                   lambda r: r["clones"]["G_A1_WA2"]["pulse_weights"][2][1].__setitem__(0, 0.5),
                   lambda r: r["bodies"][M.RERUN]["activity"].pop(),
                   lambda r: r["boundary"]["sigma_p_e"]["B_A2"]["exit"].update(cursor=0),
                   lambda r: r["bodies"]["B_A2"]["sigma_0"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["boundary"]["sigma_a"]["N_A2_WA2"]["world"]["rule"].update(respond=True),
                   lambda r: r["boundary"]["sigma_b"]["G_A1_X1"]["interventions"]["frozen"][min(r["W_0"])].update(weight=0.0123),
                   lambda r: r["clones"]["G_A2_WA2_tr"]["activity"].pop(),
                   lambda r: r["clones"]["N_A1_WA2"]["sigma_after_first"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["clones"]["N_A2_WA1"].update(world_switches=[]),
                   lambda r: r["X"]["X2"].update({min(r["W_0"]): 0.003}),
                   lambda r: r["boundary"]["steps"].pop(),
                   lambda r: r["clones"]["G_A1_WA1"]["sigma_end"].update(pulse=0)):
        data = measured(s)
        tamper(data["run"])
        assert RC.operation_problems(data)


# ---- CT-42-10 protocol の写しと、確定済みの事前登録の結び付き ------------------------------------------------

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
    "alpha_changed": _alter_protocol(("judgment", "J_T", "alpha", "per_direction"), 0.05),
    "min_population_changed": _alter_protocol(("judgment", "J_T", "min_population"), 5),
    "k2_changed": _alter_protocol(("judgment", "k2_of_m", "200"), 114),
    "outcomes_changed": _alter_protocol(("judgment", "outcomes"), ["invalid", "not_established", "plus", "minus"]),
    "seeds_changed": _alter_protocol(("seeds", "last"), 35250),
    "timeline_changed": _alter_protocol(("timeline", "boundary_P_E"), 1064),
    "rule_c_changed": _alter_protocol(("world", "rule_c", "B_A1_rerun"), "A2"),
    "systems_changed": _alter_protocol(("systems", "per_individual"), list(M.SYSTEMS[:-1])),
    "extremes_changed": _alter_protocol(("extremes", "X1", "C_to_source1"), 0.009),
    "f1_changed": _alter_protocol(("f1_tolerance",), 1e-6),
    # 以下は PREREGISTERED で個別に照らさない欄。写しの中身全体のハッシュで見つける
    "J_T_rule_changed": _alter_protocol(("judgment", "J_T", "rule"), "plus if count(plus) > m_def / 2"),
    "negative_reading_changed": _alter_protocol(("judgment", "negative_reading"), "weights do not affect choice"),
    "T_redefined": _alter_protocol(("quantities", "T"), "T_A1 only"),
    "null_changed": _alter_protocol(("judgment", "null_hypothesis", "H0_T"), "P(T > 0) = 1/2 among all individuals"),
    "population_changed": _alter_protocol(("judgment", "per_individual", "structural_zero_z"), "excluded"),
    "p_nz_redefined": _alter_protocol(("estimate_E_T", "p_nz"), "share whose choice changed"),
    "operation_check_dropped": _alter_protocol(("operation_checks",), ["O1", "O2", "O3"]),
}
UNCOMPARED = ("J_T_rule_changed", "negative_reading_changed", "T_redefined", "null_changed", "population_changed",
              "p_nz_redefined", "operation_check_dropped")


def test_the_preregistered_values_in_the_recheck_are_the_protocol_values() -> None:
    """recheck.py が書き起こした値（PREREGISTERED）が、確定済みの protocol.yaml の値と同じ。正本の写しは結び付きを通る。"""
    pr, jt, tl, br = RC.PREREGISTERED, PROTOCOL["judgment"]["J_T"], PROTOCOL["timeline"], PROTOCOL["brain"]
    assert pr["experiment"] == PROTOCOL["experiment"] and pr["kind"] == PROTOCOL["kind"]
    assert pr["alpha_per_direction"] == Fraction(str(jt["alpha"]["per_direction"])) == Fraction(1, 40)
    assert pr["alpha_two_sided"] == Fraction(str(jt["alpha"]["two_sided"])) and pr["min_population"] == jt["min_population"]
    assert pr["k2_200"] == PROTOCOL["judgment"]["k2_of_m"][200] and pr["outcomes"] == PROTOCOL["judgment"]["outcomes"]
    assert (pr["experience_windows"], pr["experience_pulses"], pr["boundary_P_E"]) == \
        (tl["experience_E"]["windows"], tl["experience_E"]["pulses"], tl["boundary_P_E"])
    assert (pr["test_windows"], pr["test_pulses"], pr["body_pulses"]) == (tl["test_U"]["windows"], tl["test_U"]["pulses"],
                                                                          tl["body_pulses"])
    assert (pr["w_min"], pr["w_max"], pr["w0"]) == (br["w_min"], br["w_max"], br["initial_weight_w0"])
    assert pr["f1_tolerance"] == AN.F1_TOLERANCE == PROTOCOL["f1_tolerance"]
    assert pr["rule_c"] == {k: v for k, v in PROTOCOL["world"]["rule_c"].items() if k != "background"}
    assert pr["per_individual"] == PROTOCOL["systems"]["per_individual"] and pr["extremes"] == M.extremes(PROTOCOL)
    assert all(pr[k] == PROTOCOL[k] for k in ("seeds", "smoke_seeds", "synthetic_seeds"))
    assert pr["formal_plan"] == dataclasses.asdict(FORMAL) and pr["individuals"] == AX.INDIVIDUALS
    assert RC.PROTOCOL_FILE == EXP / "protocol.yaml"
    assert RC._preregistered_values(json.loads(json.dumps(PROTOCOL))) == []
    assert RC.protocol_problems({s: measured(s) for s in SYN[:2]}) == []
    gate = PROTOCOL["inherited_gate_set"]
    assert (RC.GATE_FILE, RC.GATE_SHA256) == (gate["declaration"], gate["sha256"]) and RC.GATE_SHA256 == AN.GATE_SHA256
    assert RC.gate_problems({s: measured(s) for s in SYN[:2]}) == [] and RC.REPO_ROOT == ROOT
    # 書き起こした名前・組が、道具と同じ（照合の相手を取り違えない）
    assert (RC.START, RC.FINISH, RC.RAW, RC.SEEDS_DIR) == (R.G.START, R.G.FINISH, R.G.RAW, R.G.SEEDS_DIR)
    assert (RC.REPORT, RC.O1_FILE, RC.O1_KEYS, RC.CONTRACT_TESTS) == (AN.REPORT, AN.O1_FILE, AN.O1_KEYS, AN.CONTRACT_TESTS)
    assert (RC.BODIES, RC.RERUN, RC.CLONES, RC.RULE) == (list(M.BODIES), M.RERUN, list(M.CLONES), M.RULE_OF)
    assert RC.U_WEIGHTS == M.WEIGHTS_OF and RC.NO_FEEDBACK == set(M.NO_RESPONSE)
    assert RC.NOT_TRANSPLANTED == set(M.CLONES) - set(M.TRANSPLANTS)
    assert (RC.PAIRS_R6, RC.PAIRS_SE_T5, RC.PAIRS_SE_T6, RC.PAIRS_SE_T4, RC.PAIRS_SE_T7) == \
        tuple(list(x) for x in (M.R6_PAIRS, M.SAME_BACKGROUND_PAIRS, M.FEEDBACK_PAIRS, M.IDENTITIES, M.STRUCTURAL_PAIRS))
    assert RC.ROLES6 == M.ROLES6 and {k: RC.NOTES[k] for k in AN.NOTES} == AN.NOTES


def test_the_recheck_holds_the_fixed_hashes_of_the_preregistered_protocol() -> None:
    """recheck.py の固定のハッシュが、事前登録 v0.2 の protocol.yaml（このリポジトリの正本）から計算し直した値と同じ。"""
    stored = json.loads(json.dumps(PROTOCOL))                               # raw の meta と同じ形
    assert RC.canonical_protocol_sha256(stored) == RC.PROTOCOL_JSON_SHA256
    assert hashlib.sha256((EXP / "protocol.yaml").read_bytes()).hexdigest() == RC.PROTOCOL_FILE_SHA256 == AN.PROTOCOL_SHA256
    canonical = json.dumps(stored, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == RC.PROTOCOL_JSON_SHA256   # 正規化の仕方を独立に書き直しても同じ
    assert RC.PROTOCOL_JSON_SHA256 == "32ddbd1ddf30081caf15c779ed9d04ad0d34c306d8116992244e0675896a2180"     # v0.2
    assert RC.PROTOCOL_FILE_SHA256 == "709010ef964d945f09522ab279b1c725e0042bcf51a526a0a67cda0ff506b170"
    frozen = subprocess.run(["git", "-C", str(ROOT), "show", "49d99e4b57253f9a767cdcee56c03d11d42f148e:"
                             "experiments/0042_as2b_rule_weight_transplant/protocol.yaml"], capture_output=True)
    if frozen.returncode == 0:                                              # merge の commit の正本（取り出せるときだけ）
        assert hashlib.sha256(frozen.stdout).hexdigest() == RC.PROTOCOL_FILE_SHA256


@pytest.mark.parametrize("tamper", UNCOMPARED)
def test_the_value_comparison_alone_misses_these_fields_but_the_content_hash_does_not(tamper) -> None:
    proto = json.loads(json.dumps(PROTOCOL))
    PROTOCOL_TAMPERS[tamper]({"protocol": proto})
    assert RC._preregistered_values(proto) == []
    assert RC.canonical_protocol_sha256(proto) != RC.PROTOCOL_JSON_SHA256


@pytest.mark.parametrize("tamper", sorted(set(PROTOCOL_TAMPERS) - set(UNCOMPARED) - {"no_protocol", "no_sha256", "sha256_changed"}))
def test_the_value_comparison_finds_these_fields_by_itself(tamper) -> None:
    proto = json.loads(json.dumps(PROTOCOL))
    PROTOCOL_TAMPERS[tamper]({"protocol": proto})
    assert RC._preregistered_values(proto)


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
    assert before["structure"] == "ok" and before["O15"] == "fail"           # 形は通る（O15 は合成の seed なので fail）
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


# ---- CT-42-11 独立の検算：測定の来歴と全件性 ------------------------------------------------------------------

DIR_SEEDS = SYN[:3]


def _o1_record(commit: str) -> dict:
    """run.py の record_contract_tests が書く O1 の記録と同じ形（テストのファイルの SHA-256 は、このリポジトリのもの）。"""
    return {"measurement_commit": commit, "command": ["python", "-m", "pytest", "-q", *AN.CONTRACT_TESTS], "exit_code": 0,
            "summary": "901 passed in 300.00s", "test_files_sha256": {f: R.G.sha256_file(ROOT / f) for f in AN.CONTRACT_TESTS},
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
    "raw_weight_changed": lambda o: _rewrite_raw(o, _C, lambda d: d["run"]["clones"]["G_A1_WA2"]["pulse_weights"][0][1].__setitem__(
        0, 0.0049)),
    "raw_outcome_changed": lambda o: _rewrite_raw(o, _C, lambda d: d["run"]["clones"]["G_A2_WA1"]["layer_a"][-1].update(
        outcome="tie")),
    # フォルダ
    "renamed_folder": lambda o: R.G.seed_dir(o, _B).rename(R.G.seed_dir(o, 35309)),
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
    "report_p_any": lambda o: _json_edit(o / AN.REPORT, lambda r: r["estimate"]["p_any"].update(count=r["estimate"]["p_any"]["count"] + 1)),
    "report_missing": lambda o: (o / AN.REPORT).unlink(),
    # O1 の記録
    "o1_missing": lambda o: (o / AN.O1_FILE).unlink(),
    "o1_exit_code": lambda o: _json_edit(o / AN.O1_FILE, lambda r: r.update(exit_code=1)),
    "o1_commit": lambda o: _json_edit(o / AN.O1_FILE, lambda r: r.update(measurement_commit="0" * 40)),
    "o1_summary": lambda o: _json_edit(o / AN.O1_FILE, lambda r: r.update(summary="1 failed, 900 passed in 300.00s")),
    "o1_command": lambda o: _json_edit(o / AN.O1_FILE, lambda r: r.update(command=r["command"][:-1])),
    "o1_test_file": lambda o: _json_edit(o / AN.O1_FILE, lambda r: r["test_files_sha256"].update({AN.CONTRACT_TESTS[5]: "0" * 64})),
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
    formal = list(range(35001, 35201))
    assert RC.seed_set_problems("formal", formal) == []
    assert RC.seed_set_problems("formal", formal[:57] + formal[58:])                 # 欠け
    assert RC.seed_set_problems("formal", formal + [35201])                           # 範囲の外（smoke の seed）
    assert RC.seed_set_problems("formal", formal + [35001])                           # 重複
    assert RC.seed_set_problems("formal", [*formal[:-1], 34200])                       # 0041 の seed（欠けと範囲の外）
    assert RC.seed_set_problems("synthetic", SYN) == []
    assert RC.seed_set_problems("synthetic", [35001]) and RC.seed_set_problems("synthetic", [])
    assert RC.seed_set_problems("smoke", [35201]) and RC.seed_set_problems(None, SYN)
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
    assert src.index("verify_clean_commit") < src.index("analyze_runs(runs, mode, o1=o1)")


def test_an_invalid_individual_or_a_failed_o1_blocks_the_judgment_and_the_estimate() -> None:
    runs = {s: measured(s) for s in SYN[:2]}
    runs[SYN[1]]["run"]["clones"]["G_A1_WA2"]["pulse_weights"][0][1][0] = 0.0111
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=[])
    assert report["valid"] is False and report["judgment"] is None and report["estimate"] is None and "individuals" not in report
    assert list(report["failed_checks"]) == [str(SYN[1])] and "O7" in report["failed_checks"][str(SYN[1])]
    report = AN.analyze_runs({SYN[0]: measured(SYN[0])}, "synthetic", SMALL, o1=["x"])
    assert report["valid"] is False and report["judgment"] is None and report["O1"]["status"] == "fail"


# ---- 操作の確認が、記録の食い違いを見つける（structure・O2・O3・O13・O14・O15） ---------------------------------

def test_structure_detects_extra_fields_and_wrong_roles() -> None:
    s = SYN[0]
    for tamper in (lambda d: d["run"].update(judgment={}), lambda d: d.update(extra=1),
                   lambda d: d["run"]["bodies"]["B_A1"].update(T=0.5), lambda d: d["run"]["bodies"].pop("B_A1_rerun"),
                   lambda d: d["run"]["clones"].pop("N_A2_WA1"), lambda d: d["run"]["clones"]["G_A1_X1"].update(s=0.5),
                   lambda d: d["run"]["roles"].update(cue=d["run"]["roles"]["source1"]),
                   lambda d: d["run"]["W_0"].update({min(d["run"]["W_0"]): 0.004}),
                   lambda d: d["run"].update(seed=s + 1), lambda d: d["meta"].update(manifest={}),
                   lambda d: d["run"]["plan"].update(e_windows=3),
                   lambda d: d["run"]["bodies"]["B_A1_rerun"].update(pulse_weights=[]),
                   lambda d: d["run"]["bodies"]["B_A2"].pop("first_intent"),
                   lambda d: d["run"]["bodies"]["B_A2"]["audit"].pop("ok"),
                   lambda d: d["run"]["clones"]["G_A2_WA1"]["audit"].update(ok=True),
                   lambda d: d["run"]["boundary"].update(T={}),
                   lambda d: d["run"]["X"].pop("X2")):
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
                   lambda d: d["run"]["clones"]["N_A2_WA2"]["world_end"]["rule"].update(rule_c="A1"),
                   lambda d: d["run"]["clones"]["G_A1_X2"]["world_end"]["rule"].update(respond=False),
                   lambda d: d["run"]["bodies"]["B_A1"]["layer_a"][2].update(close=d["run"]["bodies"]["B_A1"]["layer_a"][2]["close"] + 1),
                   lambda d: d["run"]["bodies"]["B_A1"]["world_end"]["reserved"][0].__setitem__(3, 40),
                   lambda d: d["run"]["clones"]["G_A2_WA1"].update(pulse_end=SMALL.end - 1),
                   lambda d: d["run"]["bodies"]["B_A2"]["sigma_end"]["exit"]["windows"][0].__setitem__(2, 60),
                   lambda d: d["run"]["bodies"]["B_A1"]["history"].append([0, "x", []])):
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
                   lambda r: r["clones"]["G_A1_WA2"]["layer_a"].pop(),
                   lambda r: r["bodies"]["B_A1"]["delta_log"].pop(),
                   lambda r: r["clones"]["N_A2_WA1"]["delta_log"].append([1, "d", "s1", "A1"]),
                   lambda r: r["bodies"][M.RERUN]["audit"].update(ok=False),
                   lambda r: r["clones"]["G_A2_X2"]["audit"].update(issued=r["clones"]["G_A2_X2"]["audit"]["issued"] + 1),
                   lambda r: r["bodies"]["B_A2"]["audit"].update(carried_over_windows=[4]),
                   lambda r: next(x for x in r["bodies"]["B_A1"]["layer_a"] if x["emitted"]).update(emitted=False)):
        data = measured(s)
        tamper(data["run"])
        assert "O3" in failures(data, s)
    data = measured(s)
    lb = data["run"]["bodies"]["B_A1"]["layer_b"]
    assert len(lb) >= 2
    lb[1][1] = lb[0][1]                                                        # Delta の識別子の重複
    assert "O3" in failures(data, s)


def test_o13_detects_a_different_rerun() -> None:
    s = decided_seed()
    for tamper in (lambda r: r["bodies"][M.RERUN]["activity"].pop(),
                   lambda r: r["bodies"][M.RERUN]["layer_b"].pop(),
                   lambda r: r["bodies"][M.RERUN]["sigma_p_e"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["bodies"][M.RERUN]["sigma_end"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["bodies"][M.RERUN].update(sigma_p_e_sha256="0" * 64),
                   lambda r: r["bodies"][M.RERUN]["sigma_p_e"].update(pulse=SMALL.p_e - 1)):
        data = measured(s)
        tamper(data["run"])
        assert "O13" in failures(data, s)


def test_o14_detects_inconsistent_layer_a_fields_and_quantities() -> None:
    s = decided_seed()

    def decided(r, n="G_A1_WA1"):
        return next(x for x in _rec(r, n)["layer_a"] if x["outcome"] in A.ACTION_IDS)
    for tamper in (lambda r: decided(r).update(outcome="A2" if decided(r)["outcome"] == "A1" else "A1"),
                   lambda r: decided(r, "B_A2").update(emit_pulse=decided(r, "B_A2")["emit_pulse"] + 1),
                   lambda r: decided(r, "N_A1_WA2").update(winner_unit=r["roles"]["cue"]),
                   lambda r: r["bodies"][M.RERUN]["layer_a"][0].update(outcome="other"),
                   lambda r: r["clones"]["G_A2_X1"].update(sigma_end_sha256="0" * 64),
                   lambda r: r["boundary"]["W"]["A1"].update({AN.role_cids(r["roles"])["C_to_source1"]:
                                                              r["boundary"]["W"]["A1"][AN.role_cids(r["roles"])["C_to_source1"]]
                                                              + 2 ** -40})):
        data = measured(s)
        tamper(data["run"])
        assert "O14" in failures(data, s)
    problems = AN.layer_a_problems([{"window": 1, "open": 3, "close": 5, "outcome": "tie", "decision_pulse": 4, "winner_unit": "s1",
                                     "action": None, "emit_pulse": None, "emitted": False}], [(1, 3, 5)],
                                   {"source1": "s1", "source2": "s2"})
    assert problems == ["窓 1：結末と記録の欄が合わない"]
    data = measured(s)
    with pytest.MonkeyPatch.context() as mp:                                 # analysis.py の量と、定義の書き下しが違えば O14
        mp.setattr(AN.AX, "quantities", lambda s_: dict(AN.written_out_quantities({**s_, M.RERUN: None}), T=Fraction(7)))
        assert "O14" in failures(data, s)


def test_o15_rejects_seeds_outside_the_range_or_seen() -> None:
    assert AN.check_seed(measured(SYN[0]), "synthetic", SYN[0], SMALL)["O15"] == []
    for seed in (31001, 32001, 32301, 30201, 33001, 33301, 34001, 34301, 34399):
        out: list[str] = []
        AN._o15(seed, "synthetic", out)
        assert out
    out = []
    AN._o15(34001, "formal", out)
    assert len(out) == 2                                                       # 範囲の外で、かつ 0041 で走らせた seed


def test_meta_blind_must_match_the_mode() -> None:
    s = SYN[0]
    data = measured(s)
    data["meta"]["blind"] = "no"
    assert "structure" in failures(data, s)
    assert AN.check_seed(dict(measured(s), meta=dict(measured(s)["meta"], blind=True)), "formal", s, SMALL)["structure"]


# ---- CT-42-10 一度限りの実行（guard と run.execute。dummy の計算。0040・0041 と同じ） ------------------------------------

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
        R.execute("formal", [35001], tmp_path / "o", repo, None, runner=_dummy, executor_factory=SerialExecutor)
    assert not (tmp_path / "o").exists()
    assert R.OUT_DIR == Path("data/experiments/0042") and AN.OUT_DIR == R.OUT_DIR and R.MAX_WORKERS == 2
    assert list(R.allowed_seeds("formal")) == list(range(35001, 35201))
    assert list(R.allowed_seeds("smoke")) == list(range(35201, 35207))


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
    assert report["valid"] is True and sum(report["judgment"]["J_T"]["counts"].values()) == 3
    assert report["judgment"]["outcome"] == "inconclusive"                    # 3 個体では m≠ ＜ 10（算術）
    assert _complete(out, seeds) == report | {"measurement_commit": records["measurement_commit"]}
    assert RC.recheck_directory(out)["mismatches"] == []                       # 保存したファイルからの独立の検算


# ---- CT-42-10 smoke の盲検：現象の数値を保存しない（0040・0041 と同じ） -------------------------------------------------

FORBIDDEN_KEYS = ((AN.RUN_KEYS - {"seed", "plan", "roles"}) | AN.END_KEYS | set().union(*AN.BODY_KEYS.values()) | AN.CLONE_KEYS
                  | JUDGMENT_KEYS | {"run", "outcome", "winner_unit", "decision_pulse", "emit_pulse", "window"})
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
        assert not bad, p
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
    for tamper, check in ((lambda r: r["clones"]["G_A2_WA1"]["pulse_weights"][3][1].__setitem__(0, 0.0111), "O7"),
                          (lambda r: r["bodies"][M.RERUN].update(sigma_p_e_sha256="0" * 64), "O13"),
                          (lambda r: r["bodies"]["B_A2"]["sigma_0"]["units"][r["roles"]["cue"]].update(activity=9.0), "O4"),
                          (lambda r: r["clones"]["G_A1_WA1_tr"]["activity"].pop(), "O8")):
        data = measured(s)
        data["meta"]["blind"] = True
        tamper(data["run"])
        rec = R.blinded(data, "synthetic", s, SMALL)
        assert set(rec) == {"meta", "blind"} and rec["blind"]["checks"][check] == "fail"
        assert set(rec["blind"]) == AN.BLIND_KEYS and all(v in ("ok", "fail") for v in rec["blind"]["checks"].values())


def test_smoke_report_reads_blinded_records_and_rechecks_o15() -> None:
    s = SYN[0]
    data = measured(s)
    data["meta"]["blind"] = True
    rec = R.blinded(data, "synthetic", s, SMALL)
    rec["meta"]["mode"] = "smoke"
    report = AN.analyze_runs({s: rec}, "smoke", o1=[])
    assert set(report) == {"mode", "O1", "checks", "valid"} and report["checks"][str(s)]["O15"] == "fail"
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
    for mode, seeds, kw in (("smoke", [35201], {"blind": False}), ("formal", [35001], {"blind": True}),
                            ("smoke", [35201], {"check_plan": SMALL})):
        out = tmp_path / f"o_{mode}_{min(kw)}"
        with pytest.raises(R.G.GuardError):
            R.execute(mode, seeds, out, repo, commit, runner=_dummy, executor_factory=SerialExecutor, **kw)
        assert not out.exists()


# ---- O1 の証拠（0040・0041 と同じ） ---------------------------------------------------------------------------

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
    assert len(AN.CONTRACT_TESTS) == 6 and AN.o1_check(out, commit) == []
    R.record_contract_tests(repo, out, commit, run=lambda *a, **k: pytest.fail("走らせ直さない"))


def _never(*a, **k):
    raise AssertionError("O1 が成り立たないのに、契約テストの実行か seed の計算に進んだ")


@pytest.mark.parametrize("name,tamper", [
    ("終了コード", lambda r: r.update(exit_code=1)),
    ("結果の行", lambda r: r.update(summary="1 failed, 498 passed in 50.0s")),
    ("テストのファイルの SHA-256", lambda r: r["test_files_sha256"].update({AN.CONTRACT_TESTS[5]: "0" * 64})),
    ("走らせたコマンド", lambda r: r.update(command=["python", "-m", "pytest", "-q", *AN.CONTRACT_TESTS[:5]])),
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
