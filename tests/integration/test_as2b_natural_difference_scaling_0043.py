"""実験 0043 の道具の契約テスト（確定した事前登録 v0.2 の README・protocol.yaml。#200 merge `8fee59e`。README §14 の CT-43-1〜12）。

本番の seed（36001〜36200）・smoke の seed（36201〜36206）・関門の seed（31001〜31040）・0037 の seed（30001〜30299）・
0039〜0042 の seed（32001〜32399、33001〜33399、34001〜34399、35001〜35399）は使わない（実行もしない）。0039〜0042 の raw・report も、
関門の記録も使わない。合成の契約テスト専用の範囲（36301〜36399）だけを使う。合成の個体は、本番と同じ道具（measure.measure_seed）・
同じ式で、区間だけを小さくした Plan（SMALL：予定は 6 窓、E ＝ 窓 1〜3、P_E ＝ 163、終わり ＝ 268）か、本番の Plan で、実物の runtime を
通して作る。結果を見て Plan・seed を選んでいない（seed は範囲の最初から順に、構成の条件だけで決定的に選ぶ）。テストは操作の確認・記録の形・
Runtime の順序・重みの算術・判定と推定の算術だけを確かめ、合成の個体の判定と推定の量（README §9.3：s と n_U、§3.2 のすべての量とその符号、
向きごとの数、m≠・m_def、E_C、区間、k*、§4.1・§4.3 の区分と札、W^{A1}・W^{A2}・e・δ(e)・m_k、範囲の外の系の数と名前、比べへの適格の数、
選択と結果の刺激の数、最初に分かれた Pulse）の値を表示も判定もしない。実際の軌道から求めた値は、整合の真偽だけを確かめる。
算術の値は、手で作った記録（手で置いた重み・窓の結末）で確かめる。

構成（README §14 の契約テストの要件）：
- k* のある個体：SMALL の B^{A1} の層 A の窓 1〜3 に、決まった窓が 1 つ以上ある最初の合成の個体
- U に結果の刺激がある個体：SMALL の G^{A1}_base か G^{A2}_base に、U の結果の刺激の予約が 1 つ以上ある最初の合成の個体
- 構造的な 0（SE-C2・SE-C6・SE-C13）：本番と同じ measure_seed を通し、組み立ての直後（Pulse 0）に両方の源の Unit の θ・c を出生時の範囲の
  角（g ＜ −E_S）に置いた合成の個体。W^{A1} ＝ W^{A2} ＝ 出生時の値（e ＝ 0）になり、端の系はすべて基の系と同じ重みになる
- 非対称な角（CT-43-10）：一方の源を構造的に沈黙させ、もう一方の源と手がかりの Unit を最も発火しやすい角に置いた合成の個体を、本番の
  Plan で measure_seed に通す（作ったすべての系）。結果があること（発火・決まった窓・結果の刺激）を真偽で確かめる
- 作らない系（範囲の外）の道筋：(a) protocol の写しの w_max だけを 0.0049（＜ w0）にした測定（組の和が w_max の 2 倍を超えるので、
  32 の端はすべて範囲の外。測定の記録の形と個体の量の区分だけを確かめる）、(b) 手で作った記録、(c) 段の組 (1, 2, 2^1100)：
  2^1100 の段の自然な差の端は e ≠ 0 なら必ず範囲の外、対称な介入の端は δ(e) ≠ 0 なら必ず範囲の外（浮動小数の差は 2^−1074 の整数倍）。
  この関係だけを確かめる（10^6 などは保証にならない）
- Pulse 1,066 の駆動の差（CT-43-6）：SMALL の本体を P_E まで進め、手がかりの Unit の activity を置いて（発火する場合・どの Unit も
  発火しない場合）から二つに複製し、X1・X2 を移植した合成の系
置き方は 0039 の CT-39-8・0041 の CT-41-7・0042 の CT-42-8 と同じで、AS2b の道具も Core も変えない（契約テストだけ）。

使った合成の seed（PR に開示）：36301〜36310（SMALL）、36321〜36326（一度限りの実行・盲検の契約。dummy の計算と SMALL）、
36390〜36393（角の系と、構造的な 0・Pulse P_E ＋ 1 の駆動・痕跡の扱い・自分の値の移植の構成）、36398・36399（本番の Plan で実物の
runtime を通す確かめと、関門の run_body を一度の advance_to で走らせた本体との照合）、構成の条件で選んだ個体（36301〜36399 の最初から
順。どれになったかはテストの中で決まる）。

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
from collections import Counter
from concurrent.futures import Future
from fractions import Fraction
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments" / "0043_as2b_natural_difference_scaling"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = _load("measure_0043_test", EXP / "measure.py")
AN = _load("analyze_0043_test", EXP / "analyze.py")
AL = _load("alignment_0043_test", EXP / "alignment.py")
AX = _load("analysis_0043_test", EXP / "analysis.py")
R = _load("run_0043_test", EXP / "run.py")
RC = _load("recheck_0043_test", EXP / "recheck.py")
GATE = _load("gate_0038_for_0043_test", ROOT / "experiments" / "0038_as2b_forward_gate" / "gate.py")
A, AS1 = M.A, M.AS1
SMALL = M.Plan(41, 41, 6, 2, 19, 2, 3)
FORMAL = M.formal_plan(PROTOCOL)
LEVELS = M.protocol_levels(PROTOCOL)
HUGE = 2 ** 1100                                                     # e ≠ 0・δ(e) ≠ 0 なら、端は必ず範囲の外
FAR = (1, 2, HUGE)
SYN = list(range(36301, 36311))
SYN_ALL = list(range(36301, 36400))
GUARD_SEEDS = list(range(36321, 36327))
CORNER_SEEDS = (36390, 36391, 36392, 36393)
FORMAL_SEED = 36399
ONE_SHOT_SEEDS = (36399, 36398)                                      # 関門の run_body を一度の advance_to で走らせる照合（O13）
W_MAX, W0 = PROTOCOL["brain"]["w_max"], PROTOCOL["brain"]["initial_weight_w0"]
THETA = (0.45, 0.55)                                                 # 出生時の θ の範囲（0.5 ± 10%）
DRIVE = (0.072, 0.088)                                               # 出生時の c の範囲（0.08 ± 10%）
LAMBDA = 0.85
EASY = (THETA[0], DRIVE[1])                                          # 最も発火しやすい角
NARROW = copy.deepcopy(PROTOCOL)                                     # 作らない系の道筋 (a)：範囲の判定の w_max だけを w0 より下に
NARROW["brain"]["w_max"] = 0.0049
PROTOCOLS = {"formal": PROTOCOL, "narrow": NARROW}
ALWAYS = tuple(n for n in M.clone_names(LEVELS) if M.parse_clone(n)["kind"] in ("base", "X1", "X2", "tr"))


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)


def _meta(seed: int, mode: str = "synthetic") -> dict:
    """run.py が書く meta と同じ形（protocol の写しと、その SHA-256 を含む）。"""
    return {"experiment": "0043", "kind": PROTOCOL["kind"], "mode": mode, "seed": seed, "manifest": M.manifest_raw(),
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
def _measured(seed: int, plan: M.Plan, corner: str | None = None, levels: tuple | None = None, protocol: str = "formal") -> str:
    proto = PROTOCOLS[protocol]
    if corner is None:
        return json.dumps(_raw(M.measure_seed(proto, seed, plan, levels)))
    original = M.build_body

    def build(plan_, seed_, rule_c, *, log=None):                      # 本番と同じ組み立てに、Pulse 0 で Unit の値を置くだけ
        s = original(plan_, seed_, rule_c, log=log)
        _place(s, CORNERS[corner]())
        return s
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(M, "build_body", build)
        return json.dumps(_raw(M.measure_seed(proto, seed, plan, levels)))


def measured(seed: int, plan: M.Plan = SMALL, corner: str | None = None, levels: tuple | None = None,
             protocol: str = "formal") -> dict:
    """実物の runtime を通した合成の個体の生の記録（JSON を通した形。返すのは複製）。"""
    return json.loads(_measured(seed, plan, corner, levels, protocol))


def failures(data: dict, seed: int, plan: M.Plan = SMALL, levels=None) -> dict:
    return {k: v for k, v in AN.check_seed(data, "synthetic", seed, plan, levels).items() if v}


def _log():
    return AS1.AS1Log(keep=M.LOG_KEEP)


def _rec(run: dict, name: str) -> dict:
    return run["clones"][name] if name in run["clones"] else run["bodies"][name]


def _built(run: dict) -> list[str]:
    return [n for n in M.clone_names(tuple(run["levels"])) if n in run["clones"]]


def _u_consequence(rec: dict, p_e: int) -> bool:
    return any(r[1] == A.CONSEQUENCE and r[3] > p_e for r in rec["world_end"]["reserved"])


@functools.cache
def decided_seed() -> int:
    """SMALL の B^{A1} の層 A の窓 1〜E に、決まった窓が 1 つ以上ある最初の合成の個体（構成の条件だけ。値は表示しない）。"""
    return next(s for s in SYN_ALL if AN.k_star(measured(s)["run"]["bodies"]["B_A1"]["layer_a"], SMALL.e_windows) is not None)


@functools.cache
def consequence_seed() -> int:
    """SMALL の G^{A1}_base か G^{A2}_base に、U の結果の刺激の予約が 1 つ以上ある最初の合成の個体（構成の条件だけ）。"""
    def has(s):
        run = measured(s)["run"]
        return any(_u_consequence(run["clones"][n], SMALL.p_e) for n in ("G_A1_base", "G_A2_base"))
    return next(s for s in SYN_ALL if has(s))


def zero_individual(levels: tuple | None = None) -> dict:
    """構造的な 0 の個体（両方の源を構造的に沈黙させた合成の個体。e ＝ 0）。"""
    return measured(CORNER_SEEDS[0], SMALL, "zero", levels)


def corner_individual(silent: str) -> dict:
    """非対称な角の個体（本番の Plan。一方の源が構造的に沈黙し、もう一方の源と手がかりの Unit が最も発火しやすい角）。"""
    return measured(CORNER_SEEDS[1], FORMAL, f"silent_{silent}")


def far_individual(seed: int) -> dict:
    """段の組 (1, 2, 2^1100) の合成の個体（作らない系の道筋 (c)）。"""
    return measured(seed, SMALL, None, FAR)


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
                   lambda d: d["bodies"].update(pulses=2073)):
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
    """SE-C1 の算術（analysis.py と同じ）：窓 25 ＝ [1027, 1045]、E の最後の結果 1047、P_E ＝ 1065、U の最初の窓 ＝ [1068, 1086]、
    U の最初の結果は早くとも 1070、終わり ＝ 2072、1 個体の Pulse は多くとも 3 × 2072 ＋ 40 × 1007 ＝ 46,496。"""
    iv = AX.intervals(AX.gate_set())
    assert FORMAL.schedule().windows[24] == (25, 1027, 1045) and iv["last_E_outcome_pulse"] == 1047 < FORMAL.p_e
    assert FORMAL.schedule().windows[25] == (26, 1068, 1086) == tuple(iv["first_U_window"])
    assert iv["earliest_U_consequence_pulse"] == 1070 and FORMAL.schedule().cues[25] == FORMAL.p_e + 1 == 1066
    assert iv["P_E"] == FORMAL.p_e and iv["body_pulses"] == FORMAL.end == 2072
    assert iv["pulses_per_individual_max"] == 3 * 2072 + 40 * (2072 - 1065) == 46496 == AL.PULSES_PER_INDIVIDUAL_MAX
    assert iv["clones_per_individual_max"] == 40 == AL.CLONES_PER_INDIVIDUAL_MAX == len(M.clone_names(LEVELS))
    assert PROTOCOL["systems"]["pulses_per_individual_max"] == 46496


def test_the_run_entry_point_uses_only_the_protocol_plan_and_levels() -> None:
    assert "W.measure_seed(PROTOCOL, seed)" in inspect.getsource(R.measure)
    assert set(inspect.signature(R.measure).parameters) == {"seed"}
    assert LEVELS == (1, 2, 4, 8) == AX.LEVELS and M.protocol_levels(PROTOCOL) == tuple(PROTOCOL["weights"]["levels"])


def test_seen_seeds_include_0042_and_the_gate_and_exclude_0043() -> None:
    assert {30001, 31001, 31040, 32001, 32399, 33001, 33399, 34001, 34399, 35001, 35200, 35201, 35206, 35301, 35399,
            9101} <= AL.SEEN
    assert not ({36001, 36200, 36201, 36206, 36301, 36399} & AL.SEEN)


def test_contract_tests_of_o1_are_the_tool_tests_and_this_file() -> None:
    assert AN.CONTRACT_TESTS == (*PROTOCOL["tools"]["contract_tests"],
                                 "tests/integration/test_as2b_natural_difference_scaling_0043.py")
    assert R.CONTRACT_TESTS == AN.CONTRACT_TESTS == RC.CONTRACT_TESTS and len(AN.CONTRACT_TESTS) == 7
    assert (ROOT / AN.CONTRACT_TESTS[-1]) == Path(__file__).resolve()
    assert list(AN.CONTRACT_TESTS[:-1]) == AL.CONTRACT_TESTS


def test_the_analysis_names_follow_the_protocol() -> None:
    assert AN.CHECK_NAMES[1:] == tuple(PROTOCOL["operation_checks"][1:]) and PROTOCOL["operation_checks"][0] == "O1"
    assert M.clone_names(LEVELS) == AX.U_SYSTEMS and RC.clone_list(list(LEVELS)) == list(M.clone_names(LEVELS))
    assert RC.endpoint_list(list(LEVELS)) == list(M.endpoint_names(LEVELS)) and len(M.endpoint_names(LEVELS)) == 32
    assert PROTOCOL["systems"]["k_values"] == list(LEVELS) and PROTOCOL["systems"]["clones_per_individual_max"] == 40
    for n in M.clone_names(LEVELS) + M.clone_names(FAR):
        p = M.parse_clone(n)
        assert RC.split_name(n) == (p["background"], p["kind"], p["level"], p["side"]), n
    assert PROTOCOL["judgment"]["outcomes"] == ["invalid", "inconclusive", "not_established", "plus", "minus"] == AL.OUTCOMES
    assert AN.F1_TOLERANCE == 1e-12 == AX.F1_TOLERANCE and AN.MIN_M == 10 == AX.MIN_M and AN.K0 == 2 == AX.K0 == RC.K0
    assert AX.VALUE_CLASSES == RC.CLASS_ORDER == tuple(AL.VALUE_CLASS_ORDER) and AN.DEFINED == RC.DEFINED
    assert AN.INDIVIDUAL_CLASSES == RC.PEOPLE_CLASSES and AN.STRUCTURAL_LABELS_C == RC.C_LABELS
    assert AN.STRUCTURAL_LABELS_DU == RC.DU_LABELS and AN.INELIGIBLE_REASONS == RC.REASONS
    assert AN.OTHER_QUANTITIES == RC.OTHERS
    assert RC.U_SIGN == M.U_DIRECTION == AX.U_DIRECTION == PROTOCOL["weights"]["u"]
    assert RC.ROLES6 == M.ROLES6 == AX.ROLES6 == tuple(PROTOCOL["weights"]["order"])
    assert [list(p) for p in M.PAIRS6] == [list(p) for p in AX.PAIRS] == PROTOCOL["weights"]["pairs"]
    s = {n: Fraction(1, 2) for n in AX.FULL_BODIES + AX.U_SYSTEMS}
    assert set(AX.quantities(s)) == set(AN.written_out_quantities(LEVELS, s)) == set(RC.definitions(list(LEVELS), s))
    assert {k: RC.NOTES[k] for k in AN.NOTES} == AN.NOTES


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
    built = _built(run)
    assert set(ALWAYS) <= set(built) and built == list(M.built_clones(LEVELS, run["endpoints"]))
    assert all(len(_rec(run, n)["layer_a"]) == 50 and _rec(run, n)["pulse_end"] == 2072
               for n in M.BODIES + (M.RERUN,) + tuple(built))
    assert all(len(run["clones"][n]["pulse_weights"]) == 2072 - 1065 for n in built)


@pytest.mark.parametrize("which", ["decided", "consequence", "zero", "silent_source1", "silent_source2", "far", "far_zero"])
def test_the_constructed_individuals_pass_every_operation_check(which) -> None:
    levels = None
    if which in ("decided", "consequence"):
        seed = decided_seed() if which == "decided" else consequence_seed()
        data, plan = measured(seed), SMALL
    elif which == "zero":
        seed, data, plan = CORNER_SEEDS[0], zero_individual(), SMALL
    elif which == "far":
        seed, data, plan, levels = decided_seed(), far_individual(decided_seed()), SMALL, FAR
    elif which == "far_zero":
        seed, data, plan, levels = CORNER_SEEDS[0], zero_individual(FAR), SMALL, FAR
    else:
        seed, data, plan = CORNER_SEEDS[1], corner_individual(which.split("_")[1]), FORMAL
    assert failures(data, seed, plan, levels) == {} and RC.operation_problems(data) == []


JUDGMENT_KEYS = {"s_U", "s_E", "n_U", "C2", "C2_A1", "Du2", "T", "T_A1", "T_A2", "S", "D", "Z_A1", "k_star", "class",
                 "zero_label", "quantities", "judgment", "individuals", "auxiliary", "descriptive", "estimate", "interval",
                 "counts_E", "counts_U", "S1", "J_C", "E_C", "first_divergence", "consequences", "p_nz", "p_any", "m_def",
                 "m_nonzero", "built", "not_built", "eligible", "ineligible_reasons", "base_class", "e_zero", "label"}


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
    for data in (measured(SYN[0]), far_individual(decided_seed())):
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


# ---- CT-43-1 組み立てと参照系 --------------------------------------------------------------------------------

def test_ct43_1_every_system_is_built_from_the_gate_body_with_its_rule_c() -> None:
    src = inspect.getsource(M.build_body)
    assert "A.build(seed, schedule=plan.schedule(), delay=plan.delay, rule_c=rule_c, respond=True" in src
    for c in ("A1", "A2"):
        s = M.build_body(SMALL, SYN[0], c)
        assert s.meta == {"delay": 2, "rule_c": c, "respond": True, "outlet": True, "world_cues": True}
        assert s.log.keep == AS1.AS1Log.DEFAULT_KEEP and s.connections.history == [] and s.pulse == 0
    run = measured(SYN[0])["run"]
    for n in M.BODIES + (M.RERUN,) + tuple(_built(run)):
        assert _rec(run, n)["world_end"]["rule"]["rule_c"] == M.rule_of(n) and _rec(run, n)["world_end"]["rule"]["respond"] is True
    assert {n: M.rule_of(n) for n in M.BODIES + (M.RERUN,)} == {k: v for k, v in PROTOCOL["world"]["rule_c"].items()
                                                                 if k != "background"}
    assert all(M.background_of(n) == f"B_{M.rule_of(n)}" for n in M.clone_names(LEVELS))
    assert {M.target_label(n) for n in M.clone_names(LEVELS) if M.parse_clone(n)["kind"] == "base"} == {None}
    assert [M.target_label(n) for n in ("G_A1_tr", "G_A2_tr", "G_A1_X1", "G_A2_X2", "G_A1_P2", "G_A2_UM8")] == \
        ["W_A1", "W_A2", "X1", "X2", "G_A1_P2", "G_A2_UM8"]


def test_ct43_1_the_bodies_equal_the_gate_run_body() -> None:
    """本番の Plan の B^{A1}・B^{A2}・B′^{A1} の P_E と終わりの Σ・層 A・層 B・発火が、関門の宣言 v0.2 の `run_body` の本体
    （同じ組み立て）と同じ。関門の run_body を走らせた層 A の 50 窓とも同じ。"""
    decl, _ = M.gate_declaration(PROTOCOL)
    run = measured(FORMAL_SEED, FORMAL)["run"]
    for n in M.BODIES + (M.RERUN,):
        gate_like = A.build(FORMAL_SEED, schedule=GATE.schedule_of(decl, A), delay=decl["world"]["delay_L"],
                            rule_c=M.rule_of(n), respond=True)
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


class _GateSpy:
    """関門の `run_body` に渡す AS2b の道具の代わり（契約テストだけ）。build が作った系を残し、advance_to と sigma の呼び出しを
    記録する。ほかの名前は、すべて AS2b の道具そのもの（__getattr__）。"""

    def __init__(self) -> None:
        self.systems, self.advances, self.sigma_reads = [], [], 0

    def __getattr__(self, name):
        return getattr(A, name)

    def build(self, *args, **kwargs):
        system = A.build(*args, **kwargs)
        self.systems.append(system)
        return system

    def advance_to(self, app, pulse):
        self.advances.append(pulse)
        return A.advance_to(app, pulse)

    def sigma(self, *args, **kwargs):
        self.sigma_reads += 1
        return A.sigma(*args, **kwargs)


def _j(x):
    """記録と同じ JSON の形。"""
    return json.loads(json.dumps(M._jsonable(x)))


@pytest.mark.parametrize("seed", ONE_SHOT_SEEDS)
def test_ct43_1_every_full_length_body_equals_an_uninterrupted_gate_run_body(seed) -> None:
    """O13・SE-C15（0042 の CT-42-1 v0.2 と同じ）：関門の宣言 v0.2 の `run_body` そのもので、新たに組み立てた本体を、P_E で止めず、
    途中の状態も Σ も読まずに、一度の advance_to(終わり) で走らせる（spy で、組み立てが一つ・advance_to が終わりへの一度だけ・途中の
    sigma の読み出しが 0 回であることを確かめる）。その本体の終わりの Σ の値の全体・層 A・層 B・発火・感覚の出来事・来歴のログ・世界の
    記録が、P_E で止めて Σ を読んだ B′^{A1}（と B^{A1}・B^{A2}）の記録と同じ。真偽だけ。"""
    decl, _ = M.gate_declaration(PROTOCOL)
    run = measured(seed, FORMAL)["run"]
    for n in (M.RERUN,) + M.BODIES:
        spy = _GateSpy()
        _row, gate_audit = GATE.run_body(spy, decl, seed, M.rule_of(n))
        assert len(spy.systems) == 1 and spy.advances == [FORMAL.end] and spy.sigma_reads == 0, n
        ref, rec = spy.systems[0], run["bodies"][n]
        assert ref.pulse == FORMAL.end and ref.meta["rule_c"] == M.rule_of(n) and ref.meta["respond"] is True
        at_end = _j(A.sigma(ref))                                       # 終わりの後で、はじめて読む
        assert at_end == rec["sigma_end"], n
        assert AS1.sigma_diff(at_end, rec["sigma_end"]) == [] and M.sigma_sha256(at_end) == rec["sigma_end_sha256"]
        assert _j(ref.decider.records) == rec["layer_a"] == _j(gate_audit["layer_a"]), n
        assert _j(ref.world.intents) == rec["layer_b"] == _j(gate_audit["layer_b"]), n
        assert _j(ref.log.activity()) == rec["activity"] and _j(ref.log.sensory()) == rec["sensory"], n
        assert _j(M._intent_log(ref)) == rec["delta_log"] and _j(ref.world.export_state()) == rec["world_end"], n
        assert _j(gate_audit["audit"]) == rec["audit"] and _j(gate_audit["roles"]) == run["roles"], n
        assert rec["layer_a"] and rec["activity"] and rec["sensory"] and rec["layer_b"]       # 確かめが空でない
    rerun = run["bodies"][M.RERUN]
    assert rerun["sigma_end"] == run["bodies"]["B_A1"]["sigma_end"]
    assert failures(measured(seed, FORMAL), seed, FORMAL) == {}


def test_the_gate_and_earlier_and_formal_seeds_are_never_run_by_the_tests(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    commit = _git(repo, "rev-parse", "HEAD")
    for seed in (31001, 31040, 32001, 32301, 33001, 33301, 34001, 34301, 35001, 35201, 35301, 35399, 30201, 36001, 36200,
                 36201, 36206):
        with pytest.raises(R.G.GuardError):
            R.execute("synthetic", [seed], tmp_path / f"o{seed}", repo, commit, runner=_dummy, executor_factory=SerialExecutor)
        assert not (tmp_path / f"o{seed}").exists()
    for mode in ("formal", "smoke"):
        with pytest.raises(R.G.GuardError):
            R.execute(mode, [35001], tmp_path / f"g{mode}", repo, commit, runner=_dummy, executor_factory=SerialExecutor)


def test_ct43_1_the_observation_split_and_the_record_keys() -> None:
    """B′^{A1} は、関門と同じ組み立てと既定の来歴のログで、P_E と終わりの二点のほかは状態を読まない（README §2.3）。"""
    run = measured(SYN[0])["run"]
    assert {n: set(r) for n, r in run["bodies"].items()} == AN.BODY_KEYS
    assert all(set(run["clones"][n]) == AN.CLONE_KEYS for n in _built(run))
    src = inspect.getsource(M.measure_seed)
    assert "rerun = build_body(plan, seed, rule_of(RERUN))" in src                # log を渡さない ＝ AS2b の道具の既定のログ
    part = src[src.index("rerun = build_body"):src.index("return {")]
    assert part.count("A.advance_to") == 2 and part.count("_sigma(rerun)") == 1 and "_row(rerun" not in part
    assert part.index("A.advance_to(rerun.app, p_e)") < part.index("_sigma(rerun)") < part.index("A.advance_to(rerun.app, end)") \
        < part.index("_end_record(rerun)")


# ---- CT-43-2 共通の部分（SE-C2） -----------------------------------------------------------------------

def test_ct43_2_the_two_bodies_share_the_prefix_up_to_the_k_star_intent() -> None:
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
        assert len(cons) == (1 if M.rule_of(name) == action else 0)
    assert [x for x in a["activity"] if x[0] <= t] == [x for x in b["activity"] if x[0] <= t]
    assert sorted(tuple(p) for p in AS1.sigma_diff(a["sigma_0"], b["sigma_0"])) == [("world", "rule", "rule_c")]


def test_ct43_2_without_k_star_the_bodies_are_identical_through_p_e_and_e_is_zero() -> None:
    """SE-C2：E に決まった窓がない個体では、P_E まで規則 c のほかが同じで、W^{A1} ＝ W^{A2}（e ＝ 0、札 Z-1）。"""
    run = zero_individual()["run"]
    a, b = run["bodies"]["B_A1"], run["bodies"]["B_A2"]
    assert AN.k_star(a["layer_a"], SMALL.e_windows) is None and a["first_intent"] is None and b["first_intent"] is None
    for key in ("activity", "sensory", "layer_b", "delta_log"):
        assert [x for x in a[key] if x[0] <= SMALL.p_e] == [x for x in b[key] if x[0] <= SMALL.p_e], key
    assert [tuple(p) for p in AS1.sigma_diff(run["boundary"]["sigma_p_e"]["B_A1"], run["boundary"]["sigma_p_e"]["B_A2"])] \
        == [("world", "rule", "rule_c")]
    assert run["boundary"]["W"]["A1"] == run["boundary"]["W"]["A2"] == run["W_0"]
    assert set(run["difference"]["e"].values()) == {"0/1"} and run["difference"]["delta_e"] == "0/1"
    ind = AN.individual(run)
    assert ind["k_star"] is None and ind["zero_label"] == "Z-1" and ind["e_zero"] is True
    assert ind["delta_e"]["sign"] == "0" and ind["class"] == "undefined"            # 決まった窓がなく、s は定まらない


def _layer(outcomes: list[str]) -> list[dict]:
    return [{"window": k + 1, "outcome": o} for k, o in enumerate(outcomes)]


def test_ct43_2_k_star_and_the_zero_labels_on_hand_made_layers() -> None:
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


# ---- CT-43-3 境界（SE-C1・§2.5・O6・O12） ----------------------------------------------------------------------

@pytest.mark.parametrize("which", ["decided", "far"])
def test_ct43_3_the_steps_follow_s0_to_s5_and_no_pulse_passes_between_s1_and_s4(which) -> None:
    data = measured(decided_seed()) if which == "decided" else far_individual(decided_seed())
    run = data["run"]
    steps = run["boundary"]["steps"]
    built = _built(run)
    n = len(built)
    assert steps == AN.expected_steps(run)
    assert [s[0] for s in steps] == ["S0"] * 2 + ["S1"] * 2 + ["S2"] * n + ["S3"] * (n - 2) + ["S4"] * n + ["S5"] * (2 + n)
    assert all(s[2] == SMALL.p_e for s in steps if s[0] in ("S0", "S1", "S2", "S3", "S4"))
    assert all(s[2] == SMALL.end for s in steps if s[0] == "S5")
    assert all(s[4]["intervention_state_at_transplant"] == {"active": [], "frozen": {}} for s in steps if s[0] == "S3")
    assert [s[1] for s in steps if s[0] == "S3"] == [x for x in built if M.parse_clone(x)["kind"] != "base"]
    b = run["boundary"]
    assert all(b["sigma_a"][x]["pulse"] == b["sigma_b"][x]["pulse"] == SMALL.p_e for x in built)
    assert all(b["sigma_p_e"][x]["pulse"] == SMALL.p_e for x in M.BODIES)
    not_built = [x for x in M.endpoint_names(tuple(run["levels"])) if x not in run["clones"]]
    assert set(b["sigma_a"]) == set(b["sigma_b"]) == set(built) and not ({s[1] for s in steps} & set(not_built))
    assert all(run["endpoints"][x]["in_range"] is False and run["endpoints"][x]["weights"] is None for x in not_built)
    if which == "far":                                                    # e ≠ 0 なので、2^1100 の自然な差の端は作らない
        assert run["boundary"]["W"]["A1"] != run["boundary"]["W"]["A2"]
        assert {f"G_{c}_{h}{HUGE}" for c in ("A1", "A2") for h in ("P", "M")} <= set(not_built)


def _weight_paths(w_from: dict, w_to: dict) -> list[tuple]:
    return sorted(("connections", cid, "weight") for cid in w_from if w_from[cid] != w_to[cid])


@pytest.mark.parametrize("which", ["decided", "zero"])
def test_ct43_3_the_difference_inventory_after_s3_and_s4(which) -> None:
    """(a) S3 の直後の差の目録：作った複製の系と G^c_base は移植した重みだけ、G^c_tr と G^c_base は違いなし、G^c_base と B^c は
    違いなし。(b) S4 の直後は介入の状態だけが変わる。"""
    run = (measured(decided_seed()) if which == "decided" else zero_individual())["run"]
    b = run["boundary"]

    def diff(x, y):
        return sorted(tuple(p) for p in AS1.sigma_diff(x, y))
    for c in ("A1", "A2"):
        base = b["sigma_a"][f"G_{c}_base"]
        assert diff(b["sigma_p_e"][f"B_{c}"], base) == []
        assert diff(base, b["sigma_a"][f"G_{c}_tr"]) == []
        for n in _built(run):
            if M.parse_clone(n)["background"] == c:
                assert diff(base, b["sigma_a"][n]) == _weight_paths(b["W"][c], AN.target_of(run, n)), n
        assert diff(base, b["sigma_a"][f"G_{c}_X1"])                     # 移植した重みの違いが実際にある（目録の確かめが空でない）
    for n in _built(run):
        assert {p[0] for p in AS1.sigma_diff(b["sigma_a"][n], b["sigma_b"][n])} == {"interventions"}, n
    if which == "zero":                                                   # e ＝ 0：端の系はすべて基の系と違いがない
        ends = [n for n in _built(run) if M.parse_clone(n)["kind"] in ("natural", "symmetric")]
        assert len(ends) == 32
        assert all(AS1.sigma_diff(b["sigma_a"][f"G_{n[2:4]}_base"], b["sigma_a"][n]) == [] for n in ends)


def test_ct43_3_freeze_is_declared_once_with_the_values_of_each_system() -> None:
    run = measured(decided_seed())["run"]
    six = sorted(run["W_0"])
    for n in _built(run):
        sb = run["boundary"]["sigma_b"][n]
        assert sb["interventions"]["active"] == [["FREEZE", six, "advance"]]
        assert {cid: v["weight"] for cid, v in sb["interventions"]["frozen"].items()} == AN.target_of(run, n)
        assert run["clones"][n]["history"] == [[SMALL.p_e, "S4", [["FREEZE", six, "advance"]]]]
    for n in M.BODIES + (M.RERUN,):
        assert run["bodies"][n]["history"] == []


def test_ct43_3_at_p_e_nothing_is_open_or_reserved() -> None:
    """SE-C1：P_E の本体に、未決の窓・出す予定の意図・結果の予約がない。残る予約は、U の手がかりだけ（全件）。"""
    for data in (measured(decided_seed()), measured(FORMAL_SEED, FORMAL)):
        run = data["run"]
        plan = M.Plan(**run["plan"])
        for n in M.BODIES:
            s = run["boundary"]["sigma_p_e"][n]
            assert s["pulse"] == plan.p_e and s["exit"]["cursor"] == plan.e_windows and s["exit"]["pending"] is None
            assert s["exit"]["reports"] == {}
            assert sorted(r[3] for r in s["world"]["pending"]) == [c for c in plan.schedule().cues if c > plan.p_e]
            assert {r[1] for r in s["world"]["pending"]} == {A.CUE}
            cue_r = run["roles"]["cue_receptor"]
            want = Counter((A.CUE, cue_r, c, None) for c in plan.schedule().cues if c > plan.p_e)
            assert Counter(tuple(r[1:]) for r in s["world"]["pending"]) == want == AN.future_cue_rows(run)
            assert sum(want.values()) == plan.count - plan.e_windows and AN.pending_problems(run, s) == []


def _same_row_in_reserved(sigma: dict, row: list) -> list:
    return next(r for r in sigma["world"]["reserved"] if r[0] == row[0])


def _cue_edit(index: int, field: int, value):
    """残る予約の index 番目の欄 field を value にし、予約の記録の同じ識別子の行も同じに変える（記録の中では辻褄が合う改変）。"""
    def edit(sigma, run, plan):
        row = sigma["world"]["pending"][index]
        target = _same_row_in_reserved(sigma, row)
        v = value(plan, run) if callable(value) else value
        row[field] = target[field] = v
    return edit


def _cue_add(kind: str, pulse, origin=None, *, in_reserved: bool = True):
    def edit(sigma, run, plan):
        w = sigma["world"]
        row = [w["next_rid"], kind, run["roles"]["cue_receptor"], pulse(plan) if callable(pulse) else pulse, origin]
        w["pending"].append(row)
        if in_reserved:
            w["reserved"].append(list(row))
        w["next_rid"] += 1
    return edit


def _cue_drop(*, from_reserved: bool):
    def edit(sigma, run, plan):
        row = sigma["world"]["pending"].pop()
        if from_reserved:
            sigma["world"]["reserved"].remove(row)
    return edit


FUTURE_CUE_TAMPERS = {
    "missing_cue": _cue_drop(from_reserved=False),
    "missing_cue_and_its_reservation": _cue_drop(from_reserved=True),
    "duplicated_cue_same_id": lambda s, r, p: s["world"]["pending"].append(list(s["world"]["pending"][0])),
    "duplicated_cue_new_id": lambda s, r, p: _cue_add(A.CUE, s["world"]["pending"][0][3])(s, r, p),
    "cue_pulse_shifted": _cue_edit(1, 3, lambda plan, run: plan.schedule().cues[plan.e_windows + 1] + 1),
    "cue_moved_into_E": _cue_edit(0, 3, lambda plan, run: plan.p_e),
    "cue_receptor_changed": _cue_edit(0, 2, "r-other"),
    "cue_origin_changed": _cue_edit(2, 4, "d-x"),
    "extra_cue_off_schedule": _cue_add(A.CUE, lambda plan: plan.end),
    "consequence_reservation_mixed_in": _cue_add(A.CONSEQUENCE, lambda plan: plan.p_e + plan.delay, "d-x"),
}


@pytest.mark.parametrize("case", ["small", "formal"])
@pytest.mark.parametrize("tamper", sorted(FUTURE_CUE_TAMPERS))
def test_o12_finds_any_change_of_the_future_cue_reservations_at_p_e(case, tamper) -> None:
    """0042 の #196 の修正必須 2 と同じ：保存した P_E の Σ の世界に残る予約が、宣言の予定の U の手がかりちょうど（多重集合）でなければ、
    解析の O12 と独立の検算の O12 が、それぞれ見つける。改変の後に Σ の SHA-256 を計算し直すので、SHA-256 の照合では見つからない。"""
    seed, plan = (decided_seed(), SMALL) if case == "small" else (FORMAL_SEED, FORMAL)
    name = "B_A1" if case == "small" else "B_A2"
    data = measured(seed, plan)
    assert failures(data, seed, plan) == {} and RC.operation_problems(data) == []
    run = data["run"]
    sigma = run["boundary"]["sigma_p_e"][name]
    FUTURE_CUE_TAMPERS[tamper](sigma, run, plan)
    run["boundary"]["sigma_p_e_sha256"][name] = M.sigma_sha256(sigma)
    o12 = AN.check_seed(data, "synthetic", seed, plan)["O12"]
    assert any(m.startswith(f"S0：{name} の P_E の世界の") for m in o12), tamper
    assert not any("SHA-256" in m for m in o12)
    assert f"O12 {name}: 残る予約" in RC.operation_problems(data), tamper
    if tamper != "consequence_reservation_mixed_in":
        assert all(r[1] == A.CUE for r in sigma["world"]["pending"])
        assert not any("手がかりのほかの予約" in m for m in o12)


def test_o6_detects_tampering() -> None:
    s = decided_seed()
    for tamper in (lambda r: r["boundary"]["steps"].pop(),
                   lambda r: r["boundary"]["steps"][20].__setitem__(2, SMALL.p_e + 1),
                   lambda r: next(x for x in r["boundary"]["steps"] if x[0] == "S3")[4].update(
                       intervention_state_at_transplant={"active": [["x"]], "frozen": {}}),
                   lambda r: next(x for x in r["boundary"]["steps"] if x[0] == "S3")[4].update(to="W_A2"),
                   lambda r: r["boundary"]["steps"].insert(4, ["S2", "G_A1_base", SMALL.p_e, "clone", {"from": "B_A1"}]),
                   lambda r: r["boundary"]["sigma_a"]["G_A2_X1"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["boundary"]["sigma_a"]["G_A1_base"].update(pulse=SMALL.p_e + 1),
                   lambda r: r["boundary"]["sigma_a"]["G_A1_X1"]["interventions"].update(active=[["FREEZE", [], "advance"]]),
                   lambda r: r["boundary"]["sigma_b"]["G_A2_X2"]["interventions"]["frozen"][min(r["W_0"])].update(weight=0.001),
                   lambda r: r["boundary"]["sigma_b"]["G_A2_tr"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["clones"]["G_A1_X2"]["history"].append([SMALL.p_e, "x", []])):
        data = measured(s)
        tamper(data["run"])
        assert "O6" in failures(data, s)


@pytest.mark.parametrize("which", ["decided", "formal", "zero"])
def test_ct43_3_the_inventory_is_exactly_the_weights_that_changed(which) -> None:
    """#200 の Gemini 監査への ChatGPT の要件：O6(a) の Σ の差の目録は、移植した 6 本のうち、実際に値が変わった重みの経路にちょうど一致する
    （FREEZE の宣言の前の Σ (a) で比べる）。対称な介入の端では源どうしの 2 本は変わらない（部分の一致）。tr・基の系・e ＝ 0 の端は空の目録
    （全部の一致）。部分の一致と空の目録が実際にあることも確かめる（真偽だけ）。"""
    data = {"decided": lambda: measured(decided_seed()), "formal": lambda: measured(FORMAL_SEED, FORMAL),
            "zero": zero_individual}[which]()
    run = data["run"]
    b = run["boundary"]
    cids = AN.role_cids(run["roles"])
    between = {cids["source1_to_source2"], cids["source2_to_source1"]}
    seen = {"partial": False, "empty": False}
    for n in _built(run):
        c, kind = n[2:4], M.parse_clone(n)["kind"]
        paths = sorted(tuple(p) for p in AS1.sigma_diff(b["sigma_a"][f"G_{c}_base"], b["sigma_a"][n]))
        changed = [cid for cid in run["connection_order"] if b["W"][c][cid] != AN.target_of(run, n)[cid]]
        assert paths == sorted(("connections", cid, "weight") for cid in changed), n
        if kind == "symmetric":
            assert not (set(changed) & between), n
        if kind in ("base", "tr") or which == "zero" and kind in ("natural", "symmetric"):
            assert changed == [], n
        seen["partial"] |= 0 < len(changed) < 6
        seen["empty"] |= changed == []
    assert seen["empty"] and (seen["partial"] or which == "zero")


def _changed_cid(run: dict, name: str) -> str:
    c = name[2:4]
    return next(cid for cid in run["connection_order"] if run["boundary"]["W"][c][cid] != AN.target_of(run, name)[cid])


def _first_built(run: dict, kind: str) -> str:
    return next(n for n in _built(run) if M.parse_clone(n)["kind"] == kind)


def _drop_a_needed_difference(r: dict) -> None:
    cid = _changed_cid(r, "G_A1_X1")
    r["boundary"]["sigma_a"]["G_A1_X1"]["connections"][cid]["weight"] = r["boundary"]["W"]["A1"][cid]


def _add_a_weight_difference(r: dict) -> None:
    n = _first_built(r, "symmetric")
    r["boundary"]["sigma_a"][n]["connections"][AN.role_cids(r["roles"])["source1_to_source2"]]["weight"] = 0.0051


def _add_a_trace_difference(r: dict) -> None:
    conn = r["boundary"]["sigma_a"]["G_A2_tr"]["connections"][min(r["W_0"])]
    conn["pre_trace"] += 1.0


def _add_a_unit_difference(r: dict) -> None:
    n = _first_built(r, "natural")
    r["boundary"]["sigma_a"][n]["units"][r["roles"]["source2"]]["activity"] = 9.0


@pytest.mark.parametrize("tamper", [_drop_a_needed_difference, _add_a_weight_difference, _add_a_trace_difference,
                                    _add_a_unit_difference], ids=lambda f: f.__name__.strip("_"))
def test_o6_a_finds_a_missing_or_an_extra_difference_in_the_inventory(tamper) -> None:
    """O6(a)：必要な重みの差の欠け、予定にない重み（源どうし）の差、重みのほかの欄（痕跡・Unit）の差を、解析の O6 と独立の検算の O6 が
    それぞれ見つける。"""
    s = decided_seed()
    data = measured(s)
    assert failures(data, s) == {} and RC.operation_problems(data) == []
    tamper(data["run"])
    assert "O6" in failures(data, s) and any(p.startswith("O6") for p in RC.operation_problems(data))


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


# ---- CT-43-4 重みの算術（README §2.2・SE-C6〜SE-C11・O10。手で置いた重み） ---------------------------------------------

HAND_ROLES = {"cue": "s1", "source1": "s2", "source2": "s3"}
HAND_CIDS = M.role_cids(HAND_ROLES)


def _by_cid(w: dict) -> dict:
    return {HAND_CIDS[r]: w[r] for r in M.ROLES6}


def _flat(**given) -> dict:
    w = {r: W0 for r in M.ROLES6}
    w.update(given)
    return w


def _hand_cases() -> dict:
    """手で置いた 6 本の重みの組（役の名前 → 値。analysis.py の weight_arithmetic_check と同じ組と、範囲の境の組）。"""
    p = AX.c0_values()
    hw = functools.partial(AX._hand_weights, w_max=p["w_max"])
    g1, _ = hw(0.0047, 0.0051, 0.0044, 0.00512, 0.00497, 0.0046)
    cases = {"generic": hw(0.0047, 0.0051, 0.0044, 0.00512, 0.00497, 0.0046),
             "large_e": hw(0.0062, 0.0049, 0.0050, 0.0049, 0.0052, 0.0050),
             "fine": hw(0.004812345678, 0.005003, 0.005, 0.005231, 0.004801999, 0.005000123),
             "e_zero": (dict(g1), dict(g1)),
             "delta_zero": hw(0.0050, 0.0050, 0.0050, 0.0047, 0.0047, 0.0049),
             "anti_u": ({"C_to_source1": 0.0049, "source1_to_C": 0.0051, "C_to_source2": 0.0051, "source2_to_C": 0.0049,
                         "source1_to_source2": 0.005, "source2_to_source1": 0.005},
                        {"C_to_source1": 0.0051, "source1_to_C": 0.0049, "C_to_source2": 0.0049, "source2_to_C": 0.0051,
                         "source1_to_source2": 0.005, "source2_to_source1": 0.005})}
    # 範囲の境：V^{A1}_{+2}(C → 源 1) がちょうど 0（下の境）・ちょうど w_max（上の境）。V^{A1}_{+4} は外（片方の端だけ）
    lo = 2 ** -9
    cases["lower_edge"] = (_flat(C_to_source1=lo), _flat(C_to_source1=1.5 * lo))
    cases["upper_edge"] = (_flat(C_to_source1=W_MAX - 2 ** -12), _flat(C_to_source1=W_MAX - 1.5 * 2 ** -12))
    return cases


def _ax_endpoint(w1: dict, w2: dict, name: str) -> dict:
    p = M.parse_clone(name)
    return AX.endpoints(w1, w2, p["background"], p["level"], W_MAX, p["kind"])["plus" if p["side"] == 1 else "minus"]


@pytest.mark.parametrize("case", sorted(_hand_cases()))
def test_ct43_4_the_tool_arithmetic_equals_the_preregistered_analysis(case) -> None:
    """道具（measure.endpoints）の e・δ(e)・m_k、端の正確な値・範囲・範囲の外の名前と側・一度だけ丸めた値が、事前登録の analysis.py の
    算術と同じ。独立の検算の有理数の書き直し（recheck.rational_endpoints）も同じ。"""
    w1, w2 = _hand_cases()[case]
    got = M.endpoints(HAND_ROLES, _by_cid(w1), _by_cid(w2), LEVELS, W_MAX)
    e = AX.natural_difference(w1, w2)
    assert got["difference"] == {"e": {r: M.frac_str(e[r]) for r in M.ROLES6}, "delta_e": M.frac_str(AX.delta_of(e)),
                                 "m": {str(k): M.frac_str(AX.m_of(e, k)) for k in LEVELS}}
    mine = RC.rational_endpoints(HAND_ROLES, _by_cid(w1), _by_cid(w2), list(LEVELS))
    assert {r: RC.fstr(mine["e"][r]) for r in M.ROLES6} == got["difference"]["e"]
    assert RC.fstr(mine["delta_e"]) == got["difference"]["delta_e"]
    assert set(got["endpoints"]) == set(M.endpoint_names(LEVELS)) == set(mine["endpoints"])
    for name, rec in got["endpoints"].items():
        ax = _ax_endpoint(w1, w2, name)
        bad = [[r, "below" if ax["exact"][r] < 0 else "above"] for r in M.ROLES6 if not 0 <= ax["exact"][r] <= Fraction(W_MAX)]
        assert rec == {"in_range": ax["in_range"], "out_of_range": bad,
                       "weights": None if not ax["in_range"] else _by_cid(ax["weights"])}, name
        exact, inside, outside, rounded = mine["endpoints"][name]
        assert exact == ax["exact"] and (inside, outside, rounded) == (rec["in_range"], rec["out_of_range"], rec["weights"]), name
        if inside:                                                       # 正確な値を一度だけ丸めた値（float(Fraction)）
            assert all(rounded[HAND_CIDS[r]] == float(exact[r]) for r in M.ROLES6)
    assert set(M.built_clones(LEVELS, got["endpoints"])) == set(ALWAYS) | {n for n, r in got["endpoints"].items() if r["in_range"]}


def test_ct43_4_the_preregistered_hand_checks_hold() -> None:
    p = AX.c0_values()
    w = AX.weight_arithmetic_check(p)
    assert all(w[k] is True for k in ("k1_natural_side_equals_other_body_bitwise", "symmetric_pair_sums_exact_before_rounding",
                                      "delta_magnitudes_match", "label_swap_maps_to_opposite_endpoint_of_other_background_bitwise",
                                      "e_zero_gives_identical_endpoints", "delta_zero_gives_identical_symmetric_endpoints",
                                      "anti_u_gives_coinciding_endpoint_pairs", "outer_points_and_nesting"))
    assert AX.classification_check()["order"] == list(AX.VALUE_CLASSES)
    assert AX.label_swap_and_identity_check()["C_defined_without_base"] is True
    assert AX.range_guide(p)["k0"] == 2 and AX.f1_residual_example(p)["exceeds_tolerance"] is True


def test_ct43_4_exact_range_edges_and_one_sided_out_of_range() -> None:
    """範囲の境ちょうどの値は範囲の中、外の値は下・上の名前と側を記録し、丸めず、系を作らない。片方の端だけが外になる場合も。"""
    cases = _hand_cases()
    for case, side in (("lower_edge", "below"), ("upper_edge", "above")):
        w1, w2 = cases[case]
        exact2 = Fraction(w1["C_to_source1"]) + 2 * (Fraction(w1["C_to_source1"]) - Fraction(w2["C_to_source1"]))
        assert exact2 == (0 if side == "below" else Fraction(W_MAX))      # 境ちょうど（有理数で）
        got = M.endpoints(HAND_ROLES, _by_cid(w1), _by_cid(w2), LEVELS, W_MAX)["endpoints"]
        assert got["G_A1_P2"]["in_range"] is True and got["G_A1_P2"]["weights"][HAND_CIDS["C_to_source1"]] == float(exact2)
        for k in (4, 8):
            assert got[f"G_A1_P{k}"] == {"in_range": False, "out_of_range": [["C_to_source1", side]], "weights": None}
            assert got[f"G_A1_M{k}"]["in_range"] is True                 # 片方の端だけが外
        built = M.built_clones(LEVELS, got)
        assert "G_A1_P4" not in built and "G_A1_M4" in built and "G_A1_P2" in built
        assert RC.rational_endpoints(HAND_ROLES, _by_cid(w1), _by_cid(w2), list(LEVELS))["endpoints"]["G_A1_P4"][1:] == \
            (False, [["C_to_source1", side]], None)


@pytest.mark.parametrize("case", sorted(_hand_cases()))
def test_ct43_4_nesting_and_the_outer_two_points(case) -> None:
    """SE-C10：背景・種類・側ごとに、範囲の中の段は入れ子。二つの背景の自然な差の端がすべて範囲の中 ⟺ W^{A1} ＋ k e と W^{A2} − k e が
    範囲の中（外側の二点）。"""
    w1, w2 = _hand_cases()[case]
    got = M.endpoints(HAND_ROLES, _by_cid(w1), _by_cid(w2), LEVELS, W_MAX)["endpoints"]
    built = list(M.built_clones(LEVELS, got))
    assert AN.nesting_ok({"built": built}, LEVELS) and RC.nested(set(built), list(LEVELS))
    e = AX.natural_difference(w1, w2)
    for k in LEVELS:
        both = all(got[f"G_{c}_{h}{k}"]["in_range"] for c in ("A1", "A2") for h in ("P", "M"))
        outer = AX.in_range({r: Fraction(w1[r]) + k * e[r] for r in M.ROLES6}, W_MAX) and \
            AX.in_range({r: Fraction(w2[r]) - k * e[r] for r in M.ROLES6}, W_MAX)
        assert both == outer, k


def test_ct43_4_a_broken_nesting_is_found() -> None:
    ok = list(ALWAYS) + ["G_A1_P1", "G_A1_P2"]
    assert AN.nesting_ok({"built": ok}, LEVELS) and RC.nested(set(ok), list(LEVELS))
    broken = list(ALWAYS) + ["G_A1_P1", "G_A1_P4"]                       # 段 2 がないのに段 4 がある
    assert not AN.nesting_ok({"built": broken}, LEVELS) and not RC.nested(set(broken), list(LEVELS))


def test_ct43_4_e_zero_delta_zero_and_anti_u() -> None:
    """SE-C6：e ＝ 0 なら、どの段のどの端も W^c にビット単位で同じ（構造上の 0）。SE-C7：δ(e) ＝ 0・e ≠ 0 なら、対称な介入の端だけが W^c。
    SE-C11：e ＝ −b u なら、V^c_{±k} ＝ Y^c_{∓k}（有理数で正確に）。SE-C8：k ＝ 1 の自然な側は、もう一方の本体の重みとビット単位で同じ。"""
    cases = _hand_cases()
    for case, (w1, w2) in cases.items():
        got = M.endpoints(HAND_ROLES, _by_cid(w1), _by_cid(w2), LEVELS, W_MAX)["endpoints"]
        assert got["G_A1_M1"]["weights"] == _by_cid(w2) and got["G_A2_P1"]["weights"] == _by_cid(w1), case
        for k in LEVELS:
            for c, w in (("A1", w1), ("A2", w2)):
                if case == "e_zero":
                    assert all(got[f"G_{c}_{h}{k}"]["weights"] == _by_cid(w) for h in ("P", "M", "UP", "UM"))
                if case == "delta_zero":
                    assert got[f"G_{c}_UP{k}"]["weights"] == got[f"G_{c}_UM{k}"]["weights"] == _by_cid(w)
                    if got[f"G_{c}_P{k}"]["in_range"] and got[f"G_{c}_M{k}"]["in_range"]:
                        assert got[f"G_{c}_P{k}"]["weights"] != got[f"G_{c}_M{k}"]["weights"]
                if case == "anti_u":
                    for h, g in (("P", "UM"), ("M", "UP")):
                        assert _ax_endpoint(w1, w2, f"G_{c}_{h}{k}")["exact"] == _ax_endpoint(w1, w2, f"G_{c}_{g}{k}")["exact"]


@pytest.mark.parametrize("which", ["decided", "far", "formal"])
def test_ct43_4_the_recorded_arithmetic_is_recomputed_from_the_p_e_sigma(which) -> None:
    """保存した P_E の Σ の重みから、道具・analysis.py・独立の検算のそれぞれで端を計算し直すと、記録（difference・endpoints）と
    ビット単位で同じ。k ＝ 1 の自然な側は、もう一方の本体の重みと同じ（値は表示しない）。"""
    data = {"decided": lambda: measured(decided_seed()), "far": lambda: far_individual(decided_seed()),
            "formal": lambda: measured(FORMAL_SEED, FORMAL)}[which]()
    run = data["run"]
    levels = tuple(run["levels"])
    sp = run["boundary"]["sigma_p_e"]
    w1, w2 = AN._weights_of(sp["B_A1"]), AN._weights_of(sp["B_A2"])
    again = M.endpoints(run["roles"], w1, w2, levels, W_MAX)
    assert again == {"difference": run["difference"], "endpoints": run["endpoints"]}
    mine = RC.rational_endpoints(run["roles"], w1, w2, list(levels))
    assert all(mine["endpoints"][n][1:] == (r["in_range"], r["out_of_range"], r["weights"]) for n, r in run["endpoints"].items())
    assert run["endpoints"]["G_A1_M1"]["weights"] == run["boundary"]["W"]["A2"]
    assert run["endpoints"]["G_A2_P1"]["weights"] == run["boundary"]["W"]["A1"]


def test_ct43_4_a_narrow_range_builds_no_endpoint_system() -> None:
    """作らない系の道筋 (a)：範囲の判定の w_max を w0 より下にした protocol の写しで測ると、組の和が w_max の 2 倍を超えるので、32 の端は
    すべて範囲の外になり、端の系を作らず（S2〜S5・Σ・記録のどこにもない）、範囲の外の重みの名前と側を記録する。個体の量は、すべての段の
    C・D^u が範囲の外で、個体の C_2 は定まらない。独立の検算の個体の量も同じ（値は表示しない）。"""
    data = measured(SYN[0], SMALL, protocol="narrow")
    run = data["run"]
    assert set(run["clones"]) == set(ALWAYS) and all(r["in_range"] is False for r in run["endpoints"].values())
    assert all(r["weights"] is None and r["out_of_range"] for r in run["endpoints"].values())
    assert all(side in ("below", "above") and role in M.ROLES6 for r in run["endpoints"].values() for role, side in r["out_of_range"])
    assert all([role for role, _ in r["out_of_range"]] == [x for x in M.ROLES6 if x in {role for role, _ in r["out_of_range"]}]
               for r in run["endpoints"].values())
    assert {s[1] for s in run["boundary"]["steps"] if s[0] in ("S2", "S3", "S4")} == set(ALWAYS)
    assert set(run["boundary"]["sigma_a"]) == set(run["boundary"]["sigma_b"]) == set(ALWAYS)
    ind = AN.individual(run)
    assert ind["class"] == "undefined" and len(ind["not_built"]) == 32 and set(ind["built"]) == set(ALWAYS)
    for k in LEVELS:
        lv = ind["levels"][str(k)]
        assert all(lv["C"][c]["class"] == lv["Du"][c]["class"] == "out_of_range" for c in ("A1", "A2"))
        assert lv["C"]["value"]["value"] is None and lv["eligible"] == {"A1": False, "A2": False, "individual": False}
        assert all(lv["ineligible_reasons"][c][:2] == ["C_out_of_range", "Du_out_of_range"] for c in ("A1", "A2"))
    assert RC.compare(RC.individual(data), json.loads(json.dumps(ind)))[1] == []


@pytest.mark.parametrize("which", ["decided", "zero"])
def test_ct43_4_a_huge_level_is_built_exactly_when_the_difference_is_zero(which) -> None:
    """作らない系の道筋 (c)：段 2^1100 の自然な差の端は e ＝ 0 のときだけ、対称な介入の端は δ(e) ＝ 0 のときだけ範囲の中（浮動小数の差は
    2^−1074 の整数倍なので、0 でなければ必ず外）。解析の操作の確認と独立の検算を通る。その関係の真偽だけを確かめる。"""
    seed = decided_seed() if which == "decided" else CORNER_SEEDS[0]
    data = zero_individual(FAR) if which == "zero" else far_individual(seed)
    run = data["run"]
    assert failures(data, seed, SMALL, FAR) == {} and RC.operation_problems(data) == []
    w = run["boundary"]["W"]
    e_zero = w["A1"] == w["A2"]
    delta_zero = AN.delta_of(run["roles"], w["A1"], w["A2"]) == 0
    for c in ("A1", "A2"):
        assert all((f"G_{c}_{h}{HUGE}" in run["clones"]) is e_zero for h in ("P", "M"))
        assert all((f"G_{c}_{h}{HUGE}" in run["clones"]) is delta_zero for h in ("UP", "UM"))
    assert e_zero is (which == "zero")                                     # 両方の道筋が実際にある（e ＝ 0 と e ≠ 0）
    assert AN.nesting_ok({"built": list(run["clones"])}, FAR)


def test_ct43_4_the_report_of_far_individuals_runs_through_and_the_recheck_agrees() -> None:
    runs = {s: far_individual(s) for s in SYN[:3]} | {CORNER_SEEDS[0]: zero_individual(FAR)}
    report = json.loads(json.dumps(AN.analyze_runs(runs, "synthetic", SMALL, FAR, o1=[])))
    assert report["valid"] is True and report["outcome"] in PROTOCOL["judgment"]["outcomes"]
    assert set(report["descriptive"]["levels"]) == {"1", "2", str(HUGE)}
    assert report["auxiliary"]["R4"]["not_built"]["systems"] > 0                   # 作らない系がある（数は表示しない）
    assert report["descriptive"]["out_of_range"]["nesting_holds"] is True
    result = RC.recheck(runs, report)
    assert result["mismatches"] == [] and result["checks"] > 1000


def test_o10_detects_tampering() -> None:
    s = decided_seed()

    def first_in(r, kinds=("natural",)):
        return next(n for n in _built(r) if M.parse_clone(n)["kind"] in kinds)
    for tamper in (lambda r: r["difference"]["e"].update(C_to_source1="1/7"),
                   lambda r: r["difference"].update(delta_e="1/9"),
                   lambda r: r["difference"]["m"].update({"2": "1/11"}),
                   lambda r: r["endpoints"][first_in(r)]["weights"].update(
                       {min(r["W_0"]): r["endpoints"][first_in(r)]["weights"][min(r["W_0"])] + 2 ** -60}),
                   lambda r: r["boundary"]["sigma_p_e"]["B_A1"]["connections"][min(r["W_0"])].update(weight=0.0047)):
        data = measured(s)
        tamper(data["run"])
        assert "O10" in failures(data, s)
        assert any(p.startswith("O10") for p in RC.operation_problems(data))
    data = far_individual(s)                                              # 範囲の外の側の取り違え
    run = data["run"]
    out = next(n for n, r in run["endpoints"].items() if not r["in_range"])
    side = run["endpoints"][out]["out_of_range"][0]
    side[1] = "below" if side[1] == "above" else "above"
    assert "O10" in failures(data, s, SMALL, FAR) and any(p.startswith("O10") for p in RC.operation_problems(data))


# ---- CT-43-5 移植の恒等と構造上の 0（SE-C4・SE-C6・SE-C7・O8） ------------------------------------------------------------

@pytest.mark.parametrize("rule_c", ["A1", "A2"])
def test_ct43_5_own_value_transplant_is_the_identity_at_runtime(rule_c) -> None:
    """自分の値の移植は、移植しない複製と、移植の直後の Σ が同じで、U で FREEZE して終わりまで進めても、発火・層 A・層 B・
    感覚の出来事・終わりの Σ が同じ（SE-C4。移植は痕跡とほかの Σ を変えない）。"""
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
def test_ct43_5_the_own_value_transplant_equals_the_base_in_the_records(which) -> None:
    run = measured(decided_seed() if which == "decided" else consequence_seed())["run"]
    for c in ("A1", "A2"):
        for key in AN.IDENTITY_KEYS:
            assert run["clones"][f"G_{c}_tr"][key] == run["clones"][f"G_{c}_base"][key], (c, key)
    if which == "decided":                                                 # 移植の先は本当に違う重み（恒等の確かめが空でない）
        assert run["boundary"]["W"]["A1"] != run["boundary"]["W"]["A2"]
    assert any({f"G_{c}_base", f"G_{c}_tr"} <= set(g) for g in AN.identity_groups(run) for c in ("A1", "A2"))


def test_ct43_5_e_zero_makes_every_endpoint_system_identical_to_the_base() -> None:
    """SE-C6・SE-C7：e ＝ 0（構造的な 0 の合成の個体）なら、どの段の自然な差の端の系も、δ をそろえた対称な介入の端の系も、基の系と
    U で同じ（発火・層 A・層 B・感覚・終わりの Σ）。端の s は定まらない（源が発火しない）ので、区分は構造上の 0 ではなく s が定まらない。"""
    run = zero_individual()["run"]
    assert run["boundary"]["W"]["A1"] == run["boundary"]["W"]["A2"]
    for n in _built(run):
        if M.parse_clone(n)["kind"] in ("natural", "symmetric", "tr"):
            for key in AN.IDENTITY_KEYS:
                assert run["clones"][n][key] == run["clones"][f"G_{n[2:4]}_base"][key], (n, key)
    groups = AN.identity_groups(run)
    for c in ("A1", "A2"):
        same = {n for n in _built(run) if n[2:4] == c and M.parse_clone(n)["kind"] not in ("X1", "X2")}
        assert any(set(g) == same for g in groups) and len(same) == 18
    ind = AN.individual(run)
    for k in LEVELS:
        lv = ind["levels"][str(k)]
        assert all(lv[x][c]["class"] == "s_undefined" and lv[x][c]["label"] is None for x in ("C", "Du") for c in ("A1", "A2"))


def test_o8_detects_tampering() -> None:
    s = decided_seed()
    for tamper in (lambda r: r["clones"]["G_A1_tr"]["activity"].pop(),
                   lambda r: r["clones"]["G_A2_tr"]["layer_b"].append([SMALL.end, "d", "s1", "A1"]),
                   lambda r: r["clones"]["G_A1_tr"]["sigma_end"]["units"][r["roles"]["cue"]].update(activity=9.0)):
        data = measured(s)
        tamper(data["run"])
        assert "O8" in failures(data, s)
    for tamper in (lambda r: r["clones"]["G_A2_P2"]["activity"].append([SMALL.end, r["roles"]["cue"]]),
                   lambda r: r["clones"]["G_A1_UM4"]["sensory"].pop()):
        data = zero_individual()
        tamper(data["run"])
        assert "O8" in failures(data, CORNER_SEEDS[0])


# ---- CT-43-6 Pulse P_E ＋ 1（SE-C5・O9） -----------------------------------------------------

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
def test_ct43_6_at_p_e_plus_1_drives_differ_only_by_the_weights_of_the_sources_that_fired(fire) -> None:
    """SE-C5：重みだけが違う二つの系は、Pulse P_E ＋ 1 の発火・層 A・Unit の内部の状態が同じ。届く途中の駆動は、重みの差がある接続の
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
    run = {"plan": dataclasses.asdict(SMALL), "levels": [1],
           "clones": {"G_A1_base": {"activity": [list(x) for x in a.log.activity()], "sigma_after_first": json.loads(json.dumps(sa))},
                      "G_A1_X1": {"activity": [list(x) for x in b.log.activity()], "sigma_after_first": json.loads(json.dumps(sb))}},
           "boundary": {"sigma_b": {"G_A1_base": json.loads(json.dumps(M._sigma(a))), "G_A1_X1": json.loads(json.dumps(M._sigma(b)))}}}
    AN._o9(run, out)
    assert out == []                                                     # 解析の O9 は、この形の差を許す


def test_o9_detects_tampering() -> None:
    s = decided_seed()
    for tamper in (lambda r: r["clones"]["G_A1_X1"]["sigma_after_first"].update(pulse=SMALL.p_e + 2),
                   lambda r: r["clones"]["G_A2_X1"]["sigma_after_first"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["clones"]["G_A1_tr"]["sigma_after_first"]["exit"].update(cursor=0),
                   lambda r: r["clones"]["G_A1_X2"]["activity"].insert(0, [SMALL.p_e + 1, "zz"]),
                   lambda r: r["clones"]["G_A2_X2"]["sigma_after_first"]["drives"].append(["a", "b", 0.001, SMALL.p_e + 1])):
        data = measured(s)
        tamper(data["run"])
        assert "O9" in failures(data, s)


# ---- CT-43-7 世界（SE-C3・O5） ---------------------------------------------------------------------------

def test_ct43_7_consequences_follow_only_rule_c_intents_and_count_the_decided_windows() -> None:
    run = measured(consequence_seed())["run"]
    for n in M.BODIES + (M.RERUN,) + tuple(_built(run)):
        rec = _rec(run, n)
        live = [x for x in rec["layer_b"] if x[3] == M.rule_of(n)]
        cons = sorted((r[3], r[4]) for r in rec["world_end"]["reserved"] if r[1] == A.CONSEQUENCE)
        assert cons == sorted((p + SMALL.delay - 1, did) for p, did, _s, _a in live), n
        assert len(cons) == sum(1 for r in rec["layer_a"] if r["outcome"] == M.rule_of(n)), n
        assert {r for _, r in rec["sensory"]} <= {run["roles"]["cue_receptor"]} and rec["world_switches"] == []
    ind = AN.individual(run)
    aux = AN.auxiliary({"1": ind})
    assert all(aux["R5"][n]["as_expected"] is True for n in M.BODIES + tuple(_built(run)))
    assert any(ind["consequences"][n]["U"] for n in ("G_A1_base", "G_A2_base"))     # 確かめが空でない
    assert "switch_world" not in inspect.getsource(M.measure_seed)


def test_o5_detects_tampering() -> None:
    s = consequence_seed()
    run = measured(s)["run"]
    src_r = A.RECEPTOR_OF[run["roles"]["source1"]]
    cue_r = run["roles"]["cue_receptor"]
    for tamper in (lambda r: r["bodies"]["B_A1"]["sensory"].append([5, src_r]),
                   lambda r: r["bodies"]["B_A2"]["world_end"]["reserved"].append([99, A.CONSEQUENCE, cue_r, 50, "d1"]),
                   lambda r: r["clones"]["G_A1_X1"]["world_end"]["reserved"].append([99, A.EXOGENOUS, cue_r, 51, None]),
                   lambda r: r["clones"]["G_A2_base"]["world_end"]["reserved"].append([99, A.CONSEQUENCE, cue_r, SMALL.end, "d9"]),
                   lambda r: r["bodies"]["B_A1"]["world_end"]["realized"].pop(0),
                   lambda r: r["clones"]["G_A2_X1"]["world_end"]["cancelled"].append([98, A.CUE, cue_r, 9, None]),
                   lambda r: r["clones"]["G_A1_base"].update(world_switches=[[SMALL.p_e, "S3'", False]]),
                   lambda r: r["clones"]["G_A2_tr"]["layer_a"][0].update(decision_pulse=-1),
                   lambda r: r["clones"]["G_A1_X2"]["sensory"].pop()):
        data = measured(s)
        tamper(data["run"])
        assert "O5" in failures(data, s)


# ---- CT-43-8 F1・範囲・FREEZE（SE-C9・SE-C12・O7・O11） ----------------------------------------------------------

def test_ct43_8_weights_after_transplant_keep_f1_and_the_x_values() -> None:
    for data in (measured(decided_seed()), measured(FORMAL_SEED, FORMAL)):
        run = data["run"]
        cids = AN.role_cids(run["roles"])
        assert run["X"] == {k: {cids[r]: v for r, v in vals.items()} for k, vals in M.extremes(PROTOCOL).items()}
        ax = AX.extremes(AX.c0_values())
        assert M.extremes(PROTOCOL) == {"X1": ax["X1"], "X2": ax["X2"]}
        for n in _built(run):
            w = AN._weights_of(run["boundary"]["sigma_a"][n])
            assert w == AN.target_of(run, n) and all(0.0 <= v <= W_MAX for v in w.values())
            assert AN.pair_deviation(w) <= Fraction(AN.F1_TOLERANCE)
        for c in ("A1", "A2"):
            assert AN.pair_deviation(run["boundary"]["W"][c]) <= Fraction(AN.F1_TOLERANCE)
    cids = AN.role_cids({"cue": "s1", "source1": "s2", "source2": "s3"})
    for key in ("X1", "X2"):                                              # 端の値は組の和をちょうど w_max に保つ
        assert AN.pair_deviation({cids[r]: v for r, v in M.extremes(PROTOCOL)[key].items()}) == 0


def test_ct43_8_a_rounded_pair_sum_beyond_the_tolerance_makes_the_run_invalid() -> None:
    """SE-C9・O11：F1 は実数の保存則で、丸めた後の組の和には残差がある。残差の大きい手製の重み（analysis.py の f1_residual_example：
    ±4e-13 の残差の本体から k ＝ 2 の端で約 2e-12）は、固定の許容 1e-12 を超える。作った系の移植の後の重みの組の和が許容を超えれば、
    解析の O11 と独立の検算の O11 が無効にする。"""
    p = AX.c0_values()
    ex = AX.f1_residual_example(p)
    assert ex["exceeds_tolerance"] is True and ex["endpoint_A1_plus_2_deviation_rounded"] > AN.F1_TOLERANCE
    w1 = {r: 0.005 for r in M.ROLES6} | {"source1_to_C": 0.005 + 4e-13}
    w2 = {r: 0.005 for r in M.ROLES6} | {"source1_to_C": 0.005 - 4e-13}
    end = M.endpoints(HAND_ROLES, _by_cid(w1), _by_cid(w2), LEVELS, W_MAX)["endpoints"]["G_A1_P2"]
    assert end["in_range"] and AN.pair_deviation(end["weights"]) > Fraction(AN.F1_TOLERANCE)
    assert RC.max_pair_gap(end["weights"]) > Fraction(PROTOCOL["f1_tolerance"])
    s = decided_seed()
    for name in ("G_A1_X1", "G_A2_tr"):
        data = measured(s)
        conn = data["run"]["boundary"]["sigma_a"][name]["connections"][min(data["run"]["W_0"])]
        conn["weight"] += 1e-9
        assert "O11" in failures(data, s) and "O11: 範囲・F1" in RC.operation_problems(data)


def test_ct43_8_freeze_holds_every_u_pulse() -> None:
    run = measured(consequence_seed())["run"]
    for n in _built(run):
        rows = run["clones"][n]["pulse_weights"]
        assert [p for p, _ in rows] == list(range(SMALL.p_e + 1, SMALL.end + 1))
        assert all(w == AN._as_row(run, AN.target_of(run, n)) for _p, w in rows)
    moved = any(AN._weights_of(run["bodies"][b]["sigma_end"]) != run["boundary"]["W"][M.rule_of(b)] for b in M.BODIES)
    assert moved                                                         # 可塑性のままの本体の重みは U で動く（確かめが空でない）


@pytest.mark.parametrize("rule_c", ["A1", "A2"])
def test_ct43_8_traces_do_not_affect_the_trajectory_when_all_six_are_frozen(rule_c) -> None:
    """SE-C12（0037 の命題 Q2-5）：全 6 本を止めた区間では、痕跡を進めても（advance）据え置いても（hold）、発火・層 A・層 B・
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
    for tamper in (lambda r: r["clones"]["G_A1_X1"]["pulse_weights"].pop(),
                   lambda r: r["clones"]["G_A2_base"]["pulse_weights"][3][1].__setitem__(0, 0.0049),
                   lambda r: r["clones"]["G_A2_X1"]["pulse_weights"][0].__setitem__(0, SMALL.p_e)):
        data = measured(s)
        tamper(data["run"])
        assert "O7" in failures(data, s)


def test_o11_detects_tampering() -> None:
    s = decided_seed()
    for tamper in (lambda r: r["X"]["X1"].update({min(r["W_0"]): 0.006}),
                   lambda r: r["boundary"]["W"]["A2"].update({min(r["W_0"]): W_MAX + 0.001}),
                   lambda r: r["boundary"]["sigma_a"]["G_A1_X2"]["connections"][min(r["W_0"])].update(weight=-0.001),
                   lambda r: r["boundary"]["sigma_a"]["G_A1_tr"]["connections"][min(r["W_0"])].update(
                       weight=r["boundary"]["sigma_a"]["G_A1_tr"]["connections"][min(r["W_0"])]["weight"] + 1e-9)):
        data = measured(s)
        tamper(data["run"])
        assert "O11" in failures(data, s)


def _unbuild(run: dict, name: str) -> None:
    """作った端の系を、記録の上だけ「範囲の外で作らない系」に書き換える（S2〜S5・Σ・記録から消す。構造の確かめは通る形）。"""
    run["endpoints"][name] = {"in_range": False, "out_of_range": [["C_to_source1", "above"]], "weights": None}
    del run["clones"][name]
    for key in ("sigma_a", "sigma_b"):
        del run["boundary"][key][name]
    run["boundary"]["steps"] = [st for st in run["boundary"]["steps"] if st[1] != name]


@pytest.mark.parametrize("kind", ["natural", "symmetric"])
def test_o11_finds_a_broken_nesting_of_the_built_endpoint_systems(kind) -> None:
    """#200 の Gemini 監査への ChatGPT の要件：O11 は、背景・端ごとの範囲の入れ子を、自然な差の端 V と対称な介入の端 Y で、それぞれ独立に
    確かめる（analysis.py の事前の算術が V だけを確かめていることは、道具の確かめを省く理由にしない）。小さい段の系だけを作らない記録に
    書き換えると、解析の O11 と独立の検算の O11 が見つける。"""
    s = decided_seed()
    data = measured(s)
    run = data["run"]
    heads = ("P", "M") if kind == "natural" else ("UP", "UM")
    pair = next(((f"G_{c}_{h}{a}", f"G_{c}_{h}{b}") for c in ("A1", "A2") for h in heads for a, b in zip(LEVELS, LEVELS[1:])
                 if f"G_{c}_{h}{a}" in run["clones"] and f"G_{c}_{h}{b}" in run["clones"]), None)
    assert pair is not None                                                # 二つの段で作った系がある（真偽だけ）
    _unbuild(run, pair[0])
    found = failures(data, s)
    assert "structure" not in found and "O6" not in found
    assert any("入れ子" in m for m in found["O11"]) and "O11: 入れ子" in RC.operation_problems(data)


# ---- CT-43-9 量と区分と判定の算術（README §3〜§6。手で作った記録） ----------------------------------------------

def test_window_counts_share_and_undefined() -> None:
    la = _layer(["A1", "tie", "none", "A2", "A1", "A1", "none", "A2"])
    assert AN.window_counts(la, 1, 4) == {"windows": 4, "decided": 2, "A1": 1, "A2": 1, "tie": 1, "none": 1}
    assert RC.window_count(la, 1, 4) == AN.window_counts(la, 1, 4)
    assert AN.share(AN.window_counts(la, 5, 8)) == Fraction(2, 3)
    assert AN.share(AN.window_counts(_layer(["tie", "none"]), 1, 2)) is None        # 決まった窓が 0：定まらない（0 にしない）
    assert RC.a1_share(RC.window_count(_layer(["tie", "none"]), 1, 2)) is None
    assert [AN.sign(x) for x in (Fraction(1, 7), Fraction(-1, 7), Fraction(0))] == ["+", "-", "0"]


def _shares(levels=LEVELS) -> dict:
    """手で置いた割合（乱数を使わない決まった式。すべての系で違う値）。"""
    names = list(M.BODIES) + [M.RERUN] + list(M.clone_names(levels))
    return {x: Fraction((7 * i + 3) % 29 + 1, 31) for i, x in enumerate(names)}


def test_every_quantity_is_the_exact_fraction_of_its_definition() -> None:
    s = _shares()
    q = AX.quantities({n: v for n, v in s.items() if n != M.RERUN})
    assert q == AN.written_out_quantities(LEVELS, s) == RC.definitions(list(LEVELS), s)
    for k in LEVELS:
        for c in ("A1", "A2"):
            assert q[f"C{k}_{c}"] == s[f"G_{c}_P{k}"] - s[f"G_{c}_M{k}"]
            assert q[f"up{k}_{c}"] == s[f"G_{c}_P{k}"] - s[f"G_{c}_base"] and q[f"dn{k}_{c}"] == s[f"G_{c}_base"] - s[f"G_{c}_M{k}"]
            assert q[f"C{k}_{c}"] == q[f"up{k}_{c}"] + q[f"dn{k}_{c}"]
            assert q[f"Du{k}_{c}"] == s[f"G_{c}_UP{k}"] - s[f"G_{c}_UM{k}"]
        assert q[f"C{k}"] == q[f"C{k}_A1"] + q[f"C{k}_A2"] and q[f"Du{k}"] == q[f"Du{k}_A1"] + q[f"Du{k}_A2"]
        assert q[f"C{k}_any"] is (q[f"C{k}_A1"] != 0 or q[f"C{k}_A2"] != 0)
    assert q["T_A1"] == s["G_A1_base"] - s["G_A1_M1"] and q["T_A2"] == s["G_A2_P1"] - s["G_A2_base"]
    assert q["S_A1"] == s["G_A1_X1"] - s["G_A1_X2"] and q["S"] == q["S_A1"] + s["G_A2_X1"] - s["G_A2_X2"]
    assert q["D"] == s["B_A1"] - s["B_A2"] and q["Z_A1"] == s["B_A1"] - s["G_A1_base"]
    assert q["Z_A2"] == (1 - s["B_A2"]) - (1 - s["G_A2_base"])
    assert AN._quantity(q["C2"]) == {"value": {"num": q["C2"].numerator, "den": q["C2"].denominator, "value": float(q["C2"])},
                                     "sign": AN.sign(q["C2"])}
    other = _shares((1, 3))                                                # 本番でない段の組でも、書き下しと独立の検算が同じ
    assert AN.written_out_quantities((1, 3), other) == RC.definitions([1, 3], other)


def _users(name: str) -> set[str]:
    """README §3.2 の定義から、系 name の s を使う量（ここで独立に書き起こす）。"""
    if name == "B_A1":
        return {"D", "Z_A1"}
    if name == "B_A2":
        return {"D", "Z_A2"}
    p = M.parse_clone(name)
    c, k = p["background"], p["level"]
    if p["kind"] == "base":
        out = {f"{x}{j}_{c}" for j in LEVELS for x in ("up", "dn")} | {f"Z_{c}", f"T_{c}", "T"}
    elif p["kind"] == "natural":
        out = {f"C{k}_{c}", f"C{k}", f"C{k}_any", f"{'up' if p['side'] == 1 else 'dn'}{k}_{c}"}
        if k == 1 and (c, p["side"]) in (("A1", -1), ("A2", 1)):
            out |= {f"T_{c}", "T"}
    elif p["kind"] == "symmetric":
        out = {f"Du{k}_{c}", f"Du{k}"}
    elif p["kind"] in ("X1", "X2"):
        out = {f"S_{c}", "S"}
    else:
        out = set()
    return out


@pytest.mark.parametrize("name", list(M.BODIES) + list(M.clone_names(LEVELS)))
def test_the_quantities_are_undefined_exactly_when_an_s_they_use_is_undefined(name) -> None:
    """系 name の s だけが定まらない（作らない系・決まった窓がない系）とき、定まらない量は、その s を使う量ちょうど。"""
    s = _shares() | {name: None}
    q = AX.quantities({n: v for n, v in s.items() if n != M.RERUN})
    assert q == AN.written_out_quantities(LEVELS, s) == RC.definitions(list(LEVELS), s)
    assert {k for k, v in q.items() if v is None} == _users(name)


def test_the_label_swap_on_hand_made_shares() -> None:
    """SE-C14：札を入れ替えた割合（analysis.py の swapped）で、道具の書き下しと独立の検算が計算した量は、不変の量が正確に同じ、
    入れ替わる量の組が入れ替わる。C_k を −C_k に移さない（符号の対称の根拠ではない）。"""
    inv, exc = AX.invariant_and_exchanged()
    s = {n: v for n, v in _shares().items() if n != M.RERUN}
    t = AX.swapped(s)
    for f in (lambda x: AN.written_out_quantities(LEVELS, x), lambda x: RC.definitions(list(LEVELS), x)):
        q, r = f(s), f(t)
        assert all(r[k] == q[k] for k in inv) and all((r[a], r[b]) == (q[b], q[a]) for a, b in exc)
    q = AX.quantities(s)
    assert q["C2"] != 0 and AX.quantities(t)["C2"] == q["C2"] != -q["C2"]


def _flip(outcome):
    return {"A1": "A2", "A2": "A1"}.get(outcome, outcome)


def _swap_rows(rows: list) -> list:
    """範囲の外の重みの名前を、源の札の入れ替えで写す（ROLES6 の順に並べ直す）。"""
    mapped = {AX.SOURCE_SWAP[r]: side for r, side in rows}
    return [[r, mapped[r]] for r in M.ROLES6 if r in mapped]


def _swap_run(run: dict) -> dict:
    """生の記録の札を入れ替える（README §3.3：e′ ＝ −P e、P u ＝ −u）：源 1 と源 2 の役、系の名前（analysis.py の swap_map。
    B′^{A1} はそのまま）、窓の結末と行動 ID、W^{A1} と W^{A2}、X1 と X2、端の記録。"""
    sw = AX.swap_map()                                                    # 新しい札の系 → 元の札の系
    r = copy.deepcopy(run)
    r["bodies"] = {"B_A1": copy.deepcopy(run["bodies"]["B_A2"]), "B_A2": copy.deepcopy(run["bodies"]["B_A1"]),
                   M.RERUN: copy.deepcopy(run["bodies"][M.RERUN])}
    r["clones"] = {new: copy.deepcopy(run["clones"][old]) for new, old in sw.items() if new.startswith("G_") and old in run["clones"]}
    r["endpoints"] = {}
    for new in M.endpoint_names(LEVELS):
        rec = copy.deepcopy(run["endpoints"][sw[new]])
        rec["out_of_range"] = _swap_rows(rec["out_of_range"])
        r["endpoints"][new] = rec
    b = r["boundary"]
    for key in ("sigma_a", "sigma_b"):
        b[key] = {new: copy.deepcopy(run["boundary"][key][old]) for new, old in sw.items() if old in run["boundary"][key]}
    b["sigma_p_e"] = {"B_A1": run["boundary"]["sigma_p_e"]["B_A2"], "B_A2": run["boundary"]["sigma_p_e"]["B_A1"]}
    b["W"] = {"A1": run["boundary"]["W"]["A2"], "A2": run["boundary"]["W"]["A1"]}
    r["X"] = {"X1": run["X"]["X2"], "X2": run["X"]["X1"]}
    for rec in list(r["bodies"].values()) + list(r["clones"].values()):
        for x in rec["layer_a"]:
            x["outcome"], x["action"] = _flip(x["outcome"]), _flip(x["action"])
    r["roles"] = dict(r["roles"], source1=run["roles"]["source2"], source2=run["roles"]["source1"])
    return r


def _swap_holds(before: dict, after: dict) -> None:
    for k in ("T", "S", "D"):
        assert after["quantities"][k] == before["quantities"][k], k
    for a, b in (("T_A1", "T_A2"), ("S_A1", "S_A2"), ("Z_A1", "Z_A2")):
        assert (after["quantities"][a], after["quantities"][b]) == (before["quantities"][b], before["quantities"][a]), a
    assert after["delta_e"] == before["delta_e"] and after["e_zero"] == before["e_zero"] and after["class"] == before["class"]
    for k in before["levels"]:
        x, y = before["levels"][k], after["levels"][k]
        for kind in ("C", "Du"):
            assert y[kind]["value"] == x[kind]["value"] and (y[kind]["A1"], y[kind]["A2"]) == (x[kind]["A2"], x[kind]["A1"]), (k, kind)
        assert y["C"]["class"] == x["C"]["class"] and y["C"]["any"] == x["C"]["any"]
        assert (y["up"]["A1"], y["dn"]["A1"]) == (x["dn"]["A2"], x["up"]["A2"]) and (y["eligible"]["A1"], y["eligible"]["A2"]) == \
            (x["eligible"]["A2"], x["eligible"]["A1"])


@pytest.mark.parametrize("seed_of", ["decided", "consequence", "formal"])
def test_ct43_9_the_label_swap_on_the_records_of_synthetic_individuals(seed_of) -> None:
    """CT-43-9（SE-C14）：合成の個体の生の記録の札を入れ替えて、道具（analyze.individual）が計算し直した量：T・S・D・各段の C_k・D^u_k・
    δ(e)・区分は正確に同じ、背景ごとの量の組は入れ替わる。独立の検算（recheck.individual）も同じ（値は表示しない）。"""
    run = (measured(decided_seed()) if seed_of == "decided" else measured(consequence_seed()) if seed_of == "consequence"
           else measured(FORMAL_SEED, FORMAL))["run"]
    before, after = AN.individual(run), AN.individual(_swap_run(run))
    _swap_holds(before, after)
    mine = RC.individual({"meta": _meta(run["seed"]), "run": _swap_run(run)})
    assert RC.compare({k: mine[k] for k in ("quantities", "delta_e", "levels", "class")},
                      json.loads(json.dumps({k: after[k] for k in ("quantities", "delta_e", "levels", "class")})))[1] == []


def test_delta_uses_the_binary64_values_and_is_label_invariant() -> None:
    a, b = 0.1 + 0.2, 0.3
    roles = {"cue": "s1", "source1": "s2", "source2": "s3"}
    cids = AN.role_cids(roles)
    w1 = {cid: W0 for cid in cids.values()} | {cids["C_to_source1"]: a / 50}
    w2 = {cid: W0 for cid in cids.values()} | {cids["C_to_source1"]: b / 50}
    assert AN.delta_of(roles, w1, w2) == Fraction(a / 50) - Fraction(b / 50) != Fraction(str(a / 50)) - Fraction(str(b / 50))
    swapped_roles = dict(roles, source1="s3", source2="s2")
    assert AN.delta_of(swapped_roles, w2, w1) == AN.delta_of(roles, w1, w2)
    for src in (inspect.getsource(AN.individual), inspect.getsource(AN.delta_of), inspect.getsource(AN.pair_deviation),
                inspect.getsource(M.endpoints), inspect.getsource(RC.individual), inspect.getsource(RC.max_pair_gap),
                inspect.getsource(RC.rational_endpoints)):
        assert "Fraction(str(" not in src


def _ep(inside: bool, weights) -> dict:
    return {"in_range": inside, "out_of_range": [] if inside else [["C_to_source1", "above"]], "weights": weights if inside else None}


def test_the_value_classes_follow_the_order_of_readme_section_4_1() -> None:
    """範囲の外 → s が定まらない → 構造上の 0 → 測った 0 → 0 でない（手で置いた端の記録と s）。e ＝ 0 でも端の s が定まらなければ、
    構造上の 0 ではなく s が定まらない。"""
    wa, wb = {"x": 0.004}, {"x": 0.006}
    h = Fraction(1, 2)
    cases = {  # (P の端, M の端, s(P), s(M)) → 区分・値
        "out_of_range": ((_ep(False, wa), _ep(True, wb), h, h), ("out_of_range", None)),
        "out_of_range_before_s": ((_ep(True, wa), _ep(False, wb), None, None), ("out_of_range", None)),
        "s_undefined": ((_ep(True, wa), _ep(True, wb), None, h), ("s_undefined", None)),
        "identical_but_s_undefined": ((_ep(True, wa), _ep(True, dict(wa)), None, None), ("s_undefined", None)),
        "structural_zero": ((_ep(True, wa), _ep(True, dict(wa)), h, h), ("structural_zero", Fraction(0))),
        "measured_zero": ((_ep(True, wa), _ep(True, wb), h, h), ("measured_zero", Fraction(0))),
        "nonzero": ((_ep(True, wa), _ep(True, wb), Fraction(3, 4), Fraction(1, 4)), ("nonzero", Fraction(1, 2))),
    }
    for name, ((ep, em, sp, sm), want) in cases.items():
        run = {"endpoints": {"G_A1_P2": ep, "G_A1_M2": em}}
        s = {"G_A1_P2": sp, "G_A1_M2": sm}
        assert AN.classes_for(run, s, "A1", 2, "C") == want == RC.value_class(run, s, "G_A1_P2", "G_A1_M2"), name
    assert AX.individual_value(("nonzero", Fraction(1, 2)), ("out_of_range", None)) is None
    assert AX.individual_value(("structural_zero", Fraction(0)), ("measured_zero", Fraction(0))) == 0
    assert AX.comparison_eligible("measured_zero", "nonzero") and not AX.comparison_eligible("nonzero", "structural_zero")


# 手で作った個体の記録：SMALL の合成の個体の記録（構成だけを借りる。値は使わない）を元に、すべての端の系を作り（重みは端ごとに違う手の値）、
# U の窓（4〜6）の結末を手で置く。s は 1・0・2/3・1/3・1/2（既定）・定まらない（u）。W と E の窓も手で置く
OUTS = {"1": ["A1", "A1", "A1"], "0": ["A2", "A2", "A2"], "2/3": ["A1", "A1", "A2"], "1/3": ["A1", "A2", "A2"],
        "1/2": ["A1", "A2", "none"], "u": ["none", "tie", "none"]}
X0, STEP = 2 ** -8, 2 ** -20                                           # どちらも 2 の冪（和が正確）


@functools.cache
def _template() -> str:
    run = measured(SYN[0])["run"]
    order = run["connection_order"]
    for u in run["birth_units"].values():                               # 出生時の値も手で置く（どの源も構造的に沈黙しない）
        u["dynamics"].update(threshold=0.5, intrinsic_drive_per_second=0.08)
    for i, n in enumerate(M.endpoint_names(LEVELS)):
        base = f"G_{n[2:4]}_base"
        if n not in run["clones"]:
            run["clones"][n] = copy.deepcopy(run["clones"][base])
            for key in ("sigma_a", "sigma_b"):
                run["boundary"][key][n] = copy.deepcopy(run["boundary"][key][base])
        run["endpoints"][n] = _ep(True, {cid: (X0 + (i + 1) * STEP if j == 0 else W0) for j, cid in enumerate(order)})
    return json.dumps(run)


def _set_u(run: dict, name: str, key: str) -> None:
    rows = [r for r in _rec(run, name)["layer_a"] if r["window"] > SMALL.e_windows]
    for r, o in zip(rows, OUTS[key]):
        r["outcome"] = o


def _hand(spec=(), *, e="k", delta="-", identical=(), drop=()) -> dict:
    """手で作った個体の生の記録。spec：(系, s の札) の組。e：k*（"k"：窓 1 が A1）・"Z-1"・"Z-2"。delta：δ(e) の符号（"+"・"-"）、
    δ(e) ＝ 0 で e ≠ 0（"0"）、e ＝ 0（"e0"）。identical：両端の重みをビット単位で同じにする端の対（s も同じにする）。drop：作らない端の系。"""
    run = json.loads(_template())
    for n in M.BODIES + (M.RERUN,) + M.clone_names(LEVELS):
        _set_u(run, n, "1/2")
    for n, key in spec:
        _set_u(run, n, key)
    first = {"k": ["A1", "none", "none"], "Z-1": ["none", "none", "none"], "Z-2": ["none", "tie", "none"]}[e]
    for n in M.BODIES:
        for r, o in zip(run["bodies"][n]["layer_a"][:SMALL.e_windows], first):
            r["outcome"] = o
    cids = M.role_cids(run["roles"])
    w1 = {cid: W0 for cid in run["connection_order"]}
    w2 = dict(w1)
    a, b = cids["C_to_source1"], cids["C_to_source2"]
    if delta == "0":
        w1[a] = w1[b] = X0
        w2[a] = w2[b] = X0 + STEP
    elif delta in ("+", "-"):
        w1[a], w2[a] = (X0 + STEP, X0) if delta == "+" else (X0, X0 + STEP)
    run["boundary"]["W"] = {"A1": w1, "A2": w2}
    for p, m in identical:
        run["endpoints"][m]["weights"] = dict(run["endpoints"][p]["weights"])
        _rec(run, m)["layer_a"] = copy.deepcopy(_rec(run, p)["layer_a"])
    for n in drop:
        run["endpoints"][n] = _ep(False, None)
        del run["clones"][n]
        for key in ("sigma_a", "sigma_b"):
            del run["boundary"][key][n]
    return run


PEOPLE = {
    "plus": {"spec": (("G_A1_P2", "1"), ("G_A1_M2", "0"))},
    "minus": {"spec": (("G_A1_P2", "0"), ("G_A1_M2", "1"))},
    "both_zero": {},
    "cancel": {"spec": (("G_A1_P2", "1"), ("G_A1_M2", "1/2"), ("G_A2_P2", "1/2"), ("G_A2_M2", "1"))},
    "out_of_range": {"drop": ("G_A2_P2",)},
    "s_undefined": {"spec": (("G_A1_M2", "u"),)},
    "identity": {"identical": (("G_A1_P2", "G_A1_M2"), ("G_A2_P2", "G_A2_M2")), "delta": "e0"},
    "z1": {"identical": (("G_A1_P2", "G_A1_M2"), ("G_A2_P2", "G_A2_M2")), "delta": "e0", "e": "Z-1"},
    "z2": {"identical": (("G_A1_P2", "G_A1_M2"), ("G_A2_P2", "G_A2_M2")), "delta": "e0", "e": "Z-2"},
    "rounding": {"identical": (("G_A1_P2", "G_A1_M2"), ("G_A2_P2", "G_A2_M2")), "delta": "+"},
    "e0_s_undefined": {"spec": (("G_A1_P2", "u"), ("G_A2_P2", "u")), "delta": "e0",
                       "identical": (("G_A1_P2", "G_A1_M2"), ("G_A2_P2", "G_A2_M2"))},
    "du_delta_zero": {"identical": (("G_A1_UP2", "G_A1_UM2"),), "delta": "0"},
    "du_rounding": {"identical": (("G_A1_UP2", "G_A1_UM2"),), "delta": "-"},
    "du_one_nonzero": {"identical": (("G_A1_UP2", "G_A1_UM2"),), "delta": "-", "spec": (("G_A2_UP2", "1"), ("G_A2_UM2", "0"))},
    "du_both": {"identical": (("G_A1_UP2", "G_A1_UM2"), ("G_A2_UP2", "G_A2_UM2")), "delta": "0"},
    "du_s_undefined_first": {"identical": (("G_A1_UP2", "G_A1_UM2"),), "delta": "0", "spec": (("G_A1_UP2", "u"),)},
    "base_undefined": {"spec": (("G_A1_base", "u"), ("G_A1_P2", "1"), ("G_A1_M2", "0"))},
}


@functools.cache
def _person_json(name: str) -> str:
    return json.dumps(AN.individual(_hand(**PEOPLE[name])))


def person(name: str) -> dict:
    return json.loads(_person_json(name))


def _value(x: Fraction | None) -> dict:
    return json.loads(json.dumps(AN._quantity(x)))


@pytest.mark.parametrize("name", sorted(PEOPLE))
def test_the_hand_made_individuals_are_classified_and_the_recheck_agrees(name) -> None:
    """§4.1〜§4.3・§6.2 の区分・合算・札・比べへの適格を、手で作った記録で確かめる。独立の検算の個体の量の全体が同じ。"""
    run = _hand(**PEOPLE[name])
    p = AN.individual(run)
    lv = p["levels"]["2"]
    want_class = {"plus": "plus", "minus": "minus", "both_zero": "both_zero", "cancel": "cancellation", "out_of_range": "undefined",
                  "s_undefined": "undefined", "identity": "structural_zero", "z1": "structural_zero", "z2": "structural_zero",
                  "rounding": "structural_zero", "e0_s_undefined": "undefined", "du_delta_zero": "both_zero",
                  "du_rounding": "both_zero", "du_one_nonzero": "both_zero", "du_both": "both_zero",
                  "du_s_undefined_first": "both_zero", "base_undefined": "plus"}[name]
    assert p["class"] == want_class == lv["C"]["class"]
    want_value = {"plus": Fraction(1), "minus": Fraction(-1), "cancel": Fraction(0), "base_undefined": Fraction(1)}
    if want_class == "undefined":
        assert lv["C"]["value"] == _value(None) and lv["C"]["any"] is None
    else:
        assert lv["C"]["value"] == _value(want_value.get(name, Fraction(0)))
        assert lv["C"]["any"] is (name in ("plus", "minus", "cancel", "base_undefined"))
    labels = {"identity": "identity", "z1": "Z-1", "z2": "Z-2", "rounding": "rounding_coincidence"}
    if name in labels:
        assert lv["C"]["A1"]["label"] == lv["C"]["A2"]["label"] == labels[name] and lv["C"]["A1"]["class"] == "structural_zero"
        assert lv["ineligible_reasons"]["A1"] == ["C_structural_zero"] and lv["eligible"]["individual"] is False
    if name == "cancel":
        assert lv["C"]["A1"]["value"] == _value(Fraction(1, 2)) and lv["C"]["A2"]["value"] == _value(Fraction(-1, 2))
    if name == "out_of_range":
        assert lv["C"]["A2"]["class"] == "out_of_range" and lv["C"]["A1"]["class"] == "measured_zero"
        assert p["not_built"] == {"G_A2_P2": [["C_to_source1", "above"]]} and "G_A2_P2" not in p["built"]
        assert lv["ineligible_reasons"]["A2"] == ["C_out_of_range"] and lv["eligible"] == {"A1": True, "A2": False, "individual": False}
        assert p["levels"]["4"]["C"]["class"] == "both_zero"                         # ほかの段は定まる
    if name in ("s_undefined", "e0_s_undefined"):
        assert lv["C"]["A1"]["class"] == "s_undefined" and lv["C"]["A1"]["label"] is None
        assert lv["ineligible_reasons"]["A1"] == ["s_undefined"]
    if name in ("du_delta_zero", "du_rounding"):
        assert lv["Du"]["A1"]["class"] == "structural_zero" and lv["Du"]["structural"] is True
        assert lv["Du"]["A1"]["label"] == ("delta_zero" if name == "du_delta_zero" else "rounding_coincidence")
        assert lv["Du"]["value"] == _value(Fraction(0)) and lv["eligible"] == {"A1": False, "A2": True, "individual": False}
        assert lv["ineligible_reasons"]["A1"] == ["Du_structural_zero"]
    if name == "du_one_nonzero":                                              # 一方の背景だけが構造上の 0：合算の値は定まり、保つ
        assert lv["Du"]["A1"]["class"] == "structural_zero" and lv["Du"]["A1"]["label"] == "rounding_coincidence"
        assert lv["Du"]["A2"] == {"class": "nonzero", "value": _value(Fraction(1)), "label": None}
        assert lv["Du"]["value"] == _value(Fraction(1)) and lv["Du"]["structural"] is True
        assert lv["eligible"] == {"A1": False, "A2": True, "individual": False}
    if name == "du_both":
        assert all(lv["Du"][c]["class"] == "structural_zero" and lv["Du"][c]["label"] == "delta_zero" for c in ("A1", "A2"))
        assert lv["Du"]["value"] == _value(Fraction(0)) and lv["eligible"]["individual"] is False
    if name == "du_s_undefined_first":                                       # 両端が同じ重みでも、s が定まらなければ s が定まらない
        assert lv["Du"]["A1"] == {"class": "s_undefined", "value": _value(None), "label": None}
        assert lv["Du"]["value"] == _value(None) and lv["Du"]["structural"] is False
        assert lv["ineligible_reasons"]["A1"] == ["s_undefined"]
    if name == "base_undefined":                                              # 中心の差は定まり、片側の差・T^(A1)・Z^{A1} は定まらない
        assert lv["C"]["A1"]["value"] == _value(Fraction(1)) and lv["up"]["A1"] == lv["dn"]["A1"] == _value(None)
        assert p["quantities"]["T_A1"] == p["quantities"]["T"] == p["quantities"]["Z_A1"] == _value(None)
        assert p["base_class"]["A1"] == "undefined" and lv["eligible"]["individual"] is True
    if name == "plus":
        assert lv["eligible"] == {"A1": True, "A2": True, "individual": True} and p["k_star"] == 1 and p["zero_label"] is None
        assert p["delta_e"] == _value(Fraction(-STEP)) and p["e_zero"] is False and lv["up"]["A1"] == _value(Fraction(1, 2))
    if name in ("z1", "z2"):
        assert p["k_star"] is None and p["zero_label"] == labels[name] and p["e_zero"] is True
    assert RC.compare(RC.individual({"meta": _meta(SYN[0]), "run": run}), json.loads(json.dumps(p)))[1] == []


def _group(plus: int, minus: int, zero: int, undefined: int = 0) -> dict:
    rows = [person("plus")] * plus + [person("minus")] * minus + [person("both_zero")] * zero + [person("out_of_range")] * undefined
    return {str(i): copy.deepcopy(r) for i, r in enumerate(rows)}


@pytest.mark.parametrize("plus", [True, False])
@pytest.mark.parametrize("m", [10, 200])
def test_j_c_at_the_k2_boundary_in_both_directions(plus, m) -> None:
    k = PROTOCOL["judgment"]["k2_of_m"][m]
    assert k == AN.k2_of_m(m) == AX.k2(m) == RC.k2(m, Fraction(1, 40)) and (m, k) in ((10, 9), (200, 115))

    def g(x, rest, zero=3, undefined=2):
        return _group(x, rest, zero, undefined) if plus else _group(rest, x, zero, undefined)
    j = AN.judge(g(k, m - k))
    assert (j["J_C"]["m_nonzero"], j["J_C"]["m_def"], j["J_C"]["k2"], j["J_C"]["status"]) == (m, m + 3, k, "established")
    assert j["J_C"]["direction"] == ("+" if plus else "-") and j["outcome"] == ("plus" if plus else "minus")
    assert j["J_C"]["counts"] == ({"+": k, "-": m - k, "0": 3, "undefined": 2} if plus else {"+": m - k, "-": k, "0": 3, "undefined": 2})
    assert j["J_C"]["tail_probability"] == float(AN.binom_upper_tail(m, k)) <= 0.025 and j["J_C"]["level"] == 2
    j = AN.judge(g(k - 1, m - k + 1))
    assert (j["J_C"]["status"], j["J_C"]["direction"], j["outcome"]) == ("not_established", None, "not_established")
    assert RC.judgment(list(g(k, m - k).values()))["outcome"] == ("plus" if plus else "minus")
    assert RC.compare(RC.judgment(list(g(k - 1, m - k + 1).values())), AN.judge(g(k - 1, m - k + 1)))[1] == []


def test_j_c_is_inconclusive_below_10_and_zeros_and_undefined_never_count() -> None:
    """m≠ ＝ 9 で 9 体すべてが＋でも判定不能（閾値と比べない）。m≠ ＝ 10 で 9 体が＋なら成立、8 体なら不成立。"""
    j = AN.judge(_group(9, 0, 50, 20))
    assert (j["J_C"]["m_nonzero"], j["J_C"]["status"], j["outcome"], j["J_C"]["k2"]) == (9, "inconclusive", "inconclusive", None)
    assert j["J_C"]["m_def"] == 59 and j["J_C"]["tail_probability"] is None and "prominence" in j and "artificial" in j
    assert AN.judge(_group(9, 1, 0))["outcome"] == "plus" and AN.judge(_group(8, 2, 0))["outcome"] == "not_established"
    assert AN.judge(_group(10, 0, 0))["outcome"] == "plus" and AN.judge(_group(0, 0, 200))["outcome"] == "inconclusive"
    assert AN.judge(_group(0, 0, 0, 30))["J_C"]["m_def"] == 0
    assert RC.compare(RC.judgment(list(_group(9, 0, 50, 20).values())), j)[1] == []
    assert AX.judgment_status(True, 9, 0) == "inconclusive" and AX.judgment_status(False, 50, 0) == "invalid"


def test_k2_table_matches_the_protocol_and_the_binomial() -> None:
    table = PROTOCOL["judgment"]["k2_of_m"]
    assert sorted(table) == list(range(10, 201))
    assert all(table[m] == AN.k2_of_m(m) == RC.k2(m, Fraction(1, 40)) == AX.k2(m) for m in table)
    assert AN.binom_upper_tail(200, 115) <= Fraction(1, 40) < AN.binom_upper_tail(200, 114)
    broken = copy.deepcopy(PROTOCOL)
    broken["judgment"]["k2_of_m"][200] = 114
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(AN, "PROTOCOL", broken)
        with pytest.raises(ValueError, match="k₂"):
            AN.judge(_group(115, 85, 0))


ESTIMATE_ROWS = ("plus", "plus", "minus", "cancel", "both_zero", "z2", "out_of_range", "s_undefined")


def test_the_estimate_e_c_fields() -> None:
    rows = {str(i + 1): person(n) for i, n in enumerate(ESTIMATE_ROWS)}
    e = AN.estimate(rows)
    assert (e["m_def"], e["m_nonzero"], e["cancellations"], e["level"]) == (6, 3, 1, 2)
    assert (e["p_nz"]["count"], e["p_nz"]["denominator"], e["p_any"]["count"], e["p_any"]["denominator"]) == (3, 6, 4, 6)
    assert (e["p_plus"]["count"], e["p_minus"]["count"], e["p_dir"]["count"], e["p_dir"]["denominator"]) == (2, 1, 2, 3)
    assert e["p_nz"]["proportion"] == 3 / 6 and e["p_nz"]["interval"]["computed"] and e["p_any"]["interval"]["denominator"] == 6
    assert e["cancellations"] == e["p_any"]["count"] - e["p_nz"]["count"]
    assert e["abs_C2"]["defined"]["count"] == 6 and e["abs_C2"]["nonzero"]["count"] == 3 and e["abs_C2"]["nonzero"]["max"] == 1.0
    assert e["classes"] == {"plus": 2, "minus": 1, "structural_zero": 1, "both_zero": 1, "cancellation": 1, "undefined": 2}
    assert e["undefined"] == {"count": 2, "by_reason_and_background": {"A1:out_of_range": 0, "A1:s_undefined": 1,
                                                                        "A2:out_of_range": 1, "A2:s_undefined": 0}}
    assert "threshold" not in json.dumps({k: v for k, v in e.items() if k != "notes"})
    assert RC.compare(RC.estimate(list(rows.values())), e)[1] == []         # 区間の端点だけ、書き方の違いを 1e-9 まで許す


def test_a_zero_denominator_gives_no_ratio_and_no_interval() -> None:
    rows = {str(i): person("out_of_range") for i in range(3)}
    e = AN.estimate(rows)
    assert e["m_def"] == 0 and e["p_nz"]["proportion"] is None and e["p_nz"]["interval"]["computed"] is False
    assert e["p_dir"]["interval"] == {"computed": False, "interval": None, "numerator": 0, "denominator": 0, "reason": "denominator = 0"}
    assert e["abs_C2"] == {"defined": None, "nonzero": None} and AN.judge(rows)["outcome"] == "inconclusive"
    d = AN.descriptive(rows)
    assert d["levels"]["2"]["p_nz"]["proportion"] is None and d["common_all_levels"]["count"] == 0
    assert RC.compare(RC.estimate(list(rows.values())), e)[1] == [] and RC.compare(RC.describe(rows), d)[1] == []


DESCRIBE_ROWS = ("plus", "plus", "minus", "cancel", "both_zero", "z2", "out_of_range", "s_undefined", "base_undefined",
                 "du_delta_zero", "identity", "e0_s_undefined")


def test_the_descriptive_tables_report_the_required_rows() -> None:
    rows = {str(i + 1): person(n) for i, n in enumerate(DESCRIBE_ROWS)}
    key = {n: str(i + 1) for i, n in reversed(list(enumerate(DESCRIBE_ROWS)))}
    d = AN.descriptive(rows)
    assert set(d) == AL.MUST_REPORT_KEYS | {"notes"}
    zt = d["zero_table"]
    assert zt["structural_zero"] == {"Z-1": [], "Z-2": [key["z2"]], "identity": [key["identity"]], "rounding_coincidence": []}
    assert zt["both_zero"] == sorted([key["both_zero"], key["du_delta_zero"]]) and zt["cancellation"] == [key["cancel"]]
    assert zt["undefined"] == {key["out_of_range"]: {"A2": "out_of_range", "not_built": ["G_A2_P2"]},
                               key["s_undefined"]: {"A1": "s_undefined", "not_built": []},
                               key["e0_s_undefined"]: {"A1": "s_undefined", "A2": "s_undefined", "not_built": []}}
    assert zt["structurally_silent_source"] == []
    assert d["symmetric_control"]["2"]["Du_partition"] == {
        "undefined": 0, "neither_structural": 11, "one_structural": {"A1": {"delta_zero": 1, "rounding_coincidence": 0},
                                                                     "A2": {"delta_zero": 0, "rounding_coincidence": 0}},
        "both_structural": {"delta_zero": 0, "rounding_coincidence": 0}}
    pb = d["per_background"]["2"]
    assert pb["in_both"] == 9 and pb["only_one_background"]["A1"]["defined"] == 1 and pb["only_one_background"]["A2"]["defined"] == 1
    assert pb["cells_A1_A2"]["+0"] == 3 and pb["cells_A1_A2"]["-0"] == 1 and pb["cells_A1_A2"]["+-"] == 1
    assert d["levels"]["2"]["classes"]["undefined"] == 3 and d["levels"]["4"]["classes"]["undefined"] == 0
    assert d["common_all_levels"]["count"] == 9 and key["out_of_range"] not in d["common_all_levels"]["seeds"]
    assert d["out_of_range"]["systems"]["2|A2|natural|plus"] == 1 and sum(d["out_of_range"]["systems"].values()) == 1
    assert d["out_of_range"]["by_weight_name"] == {"natural|plus|C_to_source1|above": 1} and d["out_of_range"]["nesting_holds"] is False
    sc = d["symmetric_control"]["2"]
    assert sc["Du_structural_labels"] == {"delta_zero": 1, "rounding_coincidence": 0} and sc["Du_defined_with_structural_zero"] == 1
    assert sc["ineligible"]["A1"] == {"C_out_of_range": 0, "Du_out_of_range": 0, "s_undefined": 2, "C_structural_zero": 2,
                                      "Du_structural_zero": 1, "ineligible": 5}
    assert sc["ineligible"]["A2"]["C_out_of_range"] == 1 and sc["eligible_individuals"] == 6
    assert sc["comparison"]["delta_minus"]["count"] == 6 and sc["comparison"]["delta_plus"]["count"] == 0
    assert d["delta_e"]["counts"] == {"+": 0, "-": 8, "0": 4} and d["delta_e"]["delta_zero_with_e_nonzero"] == 1
    assert d["base_strata"]["A1"]["undefined"] == {"+": 1, "-": 0, "0": 0, "C_undefined": 0}
    assert d["T"]["T"]["undefined"] == 1 and d["sensitivity"]["S"]["defined"] == 12
    assert RC.compare(RC.describe(rows), d)[1] == []
    aux = AN.auxiliary(rows)
    assert aux["R1"]["classes_at_k0"]["undefined"] == 3 and aux["R4"]["not_built"] == {"systems": 1, "individuals_with_any": 1}
    assert RC.compare(RC.auxiliary(rows, AN.E_S), aux)[1] == []


PARTITION_ROWS = ("plus", "both_zero", "du_delta_zero", "du_rounding", "du_one_nonzero", "du_both", "du_s_undefined_first",
                  "out_of_range")


def test_ct43_9_the_du_partition_is_exclusive_and_matches_the_denominators() -> None:
    """#200 の Gemini 監査への ChatGPT の要件（README §4.1〜§4.3・§6.2、protocol の must_report.symmetric_control）：両方の背景の端の s が
    定まれば、一方の背景だけが構造上の 0 でも D^u_k の合算の値は定まり、割合の分母と比べの適格からは外す。個体を、定まらない・どちらも
    構造上の 0 でない・一方の背景だけが構造上の 0（背景・札ごと）・両方の背景が構造上の 0 に排他的に分け、分母と内訳を照らす。
    一方の背景の構造上の 0 と、もう一方の背景の測った 0・0 でないの組を含む。端の s が定まらないことは、構造上の 0 より先に効く。"""
    rows = {str(i + 1): person(n) for i, n in enumerate(PARTITION_ROWS)}
    sc = AN.descriptive(rows)["symmetric_control"]
    part = sc["2"]["Du_partition"]
    assert part == {"undefined": 1, "neither_structural": 3,
                    "one_structural": {"A1": {"delta_zero": 1, "rounding_coincidence": 2}, "A2": {"delta_zero": 0, "rounding_coincidence": 0}},
                    "both_structural": {"delta_zero": 1, "rounding_coincidence": 0}}
    one = sum(v for c in ("A1", "A2") for v in part["one_structural"][c].values())
    both = sum(part["both_structural"].values())
    assert part["undefined"] + part["neither_structural"] + one + both == len(rows)                 # 排他で、全員を分ける
    assert sc["2"]["Du"]["defined"] == part["neither_structural"]                                   # 割合の分母
    assert sc["2"]["Du_defined_with_structural_zero"] == one + both                                  # 別に示す数
    assert sc["2"]["Du"]["counts"] == {"+": 0, "-": 0, "0": 3}                                      # 合算の値 1 の個体は分母の外
    assert person("du_one_nonzero")["levels"]["2"]["Du"]["value"] == _value(Fraction(1))             # 値は保つ
    assert sc["2"]["eligible_individuals"] == 2 and sc["2"]["ineligible"]["A1"]["Du_structural_zero"] == 4
    assert sc["4"]["Du_partition"]["neither_structural"] == len(rows)                                # ほかの段は分母に入る
    assert RC.compare(RC.describe(rows), AN.descriptive(rows))[1] == []


def _one_background_rounding_example() -> tuple[dict, dict]:
    """ChatGPT の手製の binary64 の例（seed なし）：t ＝ 2^−61、b ＝ 2^−8。A1 の C → 源の 2 本は 0.005 ＋ 2t、逆向きは 0.005 − 2t、
    A2 の C → 源 1 は b − t、C → 源 2 は b、逆向きは w_max からの差、源どうしは 0.005。δ(e) ＝ t、k ＝ 2 で m ＝ t。"""
    t, b = 2.0 ** -61, 2.0 ** -8
    w1 = {"C_to_source1": 0.005 + 2 * t, "source1_to_C": 0.005 - 2 * t, "C_to_source2": 0.005 + 2 * t,
          "source2_to_C": 0.005 - 2 * t, "source1_to_source2": 0.005, "source2_to_source1": 0.005}
    w2 = {"C_to_source1": b - t, "source1_to_C": W_MAX - (b - t), "C_to_source2": b, "source2_to_C": W_MAX - b,
          "source1_to_source2": 0.005, "source2_to_source1": 0.005}
    return w1, w2


def test_ct43_9_a_one_background_rounding_coincidence_of_the_symmetric_endpoints() -> None:
    """手製の binary64 の例：A1 の対称な介入の端は、変わる 4 本が偶数の仮数への丸めで両端とも基の値に戻り（k ＝ 1・2）、A2 の端は戻らない。
    道具・analysis.py・独立の検算の算術が同じで、その端の記録の個体では、D^u の A1 が構造上の 0（札は丸めの一致）、A2 は測った 0。
    自然な差の端は、e ≠ 0 なら k ≥ 1 で両端が一致しない（他方の本体の重みが、中心の反対側にある）。防御の分類（札 rounding_coincidence）
    は残す。"""
    w1, w2 = _one_background_rounding_example()
    e = AX.natural_difference(w1, w2)
    assert AX.delta_of(e) == Fraction(2 ** -61) and AX.m_of(e, 2) == Fraction(2 ** -61)
    got = M.endpoints(HAND_ROLES, _by_cid(w1), _by_cid(w2), LEVELS, W_MAX)
    ends = got["endpoints"]
    mine = RC.rational_endpoints(HAND_ROLES, _by_cid(w1), _by_cid(w2), list(LEVELS))["endpoints"]
    for k in (1, 2):
        assert ends[f"G_A1_UP{k}"]["weights"] == ends[f"G_A1_UM{k}"]["weights"] == _by_cid(w1)
        assert ends[f"G_A2_UP{k}"]["weights"] != ends[f"G_A2_UM{k}"]["weights"]
        assert mine[f"G_A1_UP{k}"][3] == mine[f"G_A1_UM{k}"][3] == _by_cid(w1)
        assert mine[f"G_A1_UP{k}"][0] != mine[f"G_A1_UM{k}"][0]                       # 正確な値は違う（丸めで一致する）
    for name, rec in ends.items():
        ax = _ax_endpoint(w1, w2, name)
        assert rec["weights"] == (None if not ax["in_range"] else _by_cid(ax["weights"])), name
    for c in ("A1", "A2"):
        for k in LEVELS:
            p, m = ends[f"G_{c}_P{k}"], ends[f"G_{c}_M{k}"]
            assert not (p["in_range"] and m["in_range"] and p["weights"] == m["weights"]), (c, k)
    run = _hand(delta="+")                                                    # 手で作った個体に、この例の重みと端の記録を置く
    cids = M.role_cids(run["roles"])
    run["boundary"]["W"] = {"A1": {cids[r]: w1[r] for r in M.ROLES6}, "A2": {cids[r]: w2[r] for r in M.ROLES6}}
    real = M.endpoints(run["roles"], run["boundary"]["W"]["A1"], run["boundary"]["W"]["A2"], LEVELS, W_MAX)["endpoints"]
    for n in M.endpoint_names(LEVELS):
        if M.parse_clone(n)["kind"] == "symmetric":
            run["endpoints"][n] = real[n]
    p = AN.individual(run)
    for k in ("1", "2"):
        du = p["levels"][k]["Du"]
        assert (du["A1"]["class"], du["A1"]["label"], du["A2"]["class"]) == ("structural_zero", "rounding_coincidence", "measured_zero")
        assert du["value"] == _value(Fraction(0)) and du["structural"] is True and p["levels"][k]["eligible"]["A1"] is False
    assert p["levels"]["4"]["Du"]["A1"]["class"] == "measured_zero" and p["delta_e"]["sign"] == "+"
    part = AN.descriptive({"1": p})["symmetric_control"]["2"]["Du_partition"]
    assert part["one_structural"]["A1"]["rounding_coincidence"] == 1 and part["neither_structural"] == 0
    assert RC.compare(RC.individual({"meta": _meta(SYN[0]), "run": run}), json.loads(json.dumps(p)))[1] == []


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


def test_c2_p_nz_and_p_any_are_recomputed_from_the_records() -> None:
    """審査の重点：実際の記録（合成の個体の生の記録）から、ここで独立に数え直した s と C_2・any・p_nz・p_any の数が、解析の report と
    独立の検算に一致する（値は表示しない。一致の真偽だけ）。"""
    runs = {s: measured(s) for s in SYN[:5]} | {decided_seed(): measured(decided_seed()), consequence_seed(): measured(consequence_seed())}
    report = json.loads(json.dumps(AN.analyze_runs(runs, "synthetic", SMALL, o1=[])))
    assert report["valid"] is True
    defined = nonzero = any_bg = 0
    for seed, data in runs.items():
        run = data["run"]
        parts = {}
        for c in ("A1", "A2"):
            s = {}
            for n in (f"G_{c}_P2", f"G_{c}_M2"):
                if n not in run["clones"]:
                    s[n] = None
                    continue
                outs = [r["outcome"] for r in run["clones"][n]["layer_a"] if r["window"] > SMALL.e_windows]
                a1, a2 = outs.count("A1"), outs.count("A2")
                s[n] = Fraction(a1, a1 + a2) if a1 + a2 else None
            parts[c] = None if None in s.values() else s[f"G_{c}_P2"] - s[f"G_{c}_M2"]
        ind = report["individuals"][str(seed)]
        if None in parts.values():
            assert ind["levels"]["2"]["C"]["value"]["value"] is None and ind["class"] == "undefined"
            continue
        got = ind["levels"]["2"]["C"]["value"]["value"]
        assert Fraction(got["num"], got["den"]) == parts["A1"] + parts["A2"]
        assert ind["levels"]["2"]["C"]["any"] is (parts["A1"] != 0 or parts["A2"] != 0)
        defined += 1
        nonzero += parts["A1"] + parts["A2"] != 0
        any_bg += parts["A1"] != 0 or parts["A2"] != 0
    est = report["estimate"]
    assert (est["m_def"], est["p_nz"]["count"], est["p_any"]["count"]) == (defined, nonzero, any_bg)
    assert est["cancellations"] == any_bg - nonzero and defined >= 1
    assert RC.recheck(runs, report)["mismatches"] == []


def test_an_invalid_individual_or_a_failed_o1_blocks_the_judgment_and_the_estimate() -> None:
    runs = {s: measured(s) for s in SYN[:2]}
    runs[SYN[1]]["run"]["clones"]["G_A1_X1"]["pulse_weights"][0][1][0] = 0.0111
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=[])
    assert report["valid"] is False and report["outcome"] == "invalid" and report["judgment"] is None
    assert report["estimate"] is None and report["descriptive"] is None and "individuals" not in report
    assert list(report["failed_checks"]) == [str(SYN[1])] and "O7" in report["failed_checks"][str(SYN[1])]
    report = AN.analyze_runs({SYN[0]: measured(SYN[0])}, "synthetic", SMALL, o1=["x"])
    assert report["valid"] is False and report["judgment"] is None and report["O1"]["status"] == "fail"


# ---- CT-43-10 命題 S-1・SE-C13（README §7.2） -------------------------------------------------------------

def test_ct43_10_the_bound_e_s_matches_the_preregistered_analysis() -> None:
    lam, w = LAMBDA, W_MAX
    e_s = w * ((1 + lam ** 4) / (1 - lam ** 23) + 2 / (1 - lam ** 7))
    assert AN.E_S == pytest.approx(e_s, abs=1e-15) and AN.E_S == pytest.approx(PROTOCOL["proposition_S1"]["E_S_value"], abs=5e-6)
    assert RC.bound_e_s(M.manifest_raw(), dataclasses.asdict(FORMAL)) == pytest.approx(AN.E_S, abs=1e-15)
    assert RC.bound_e_s(M.manifest_raw(), dataclasses.asdict(SMALL)) == pytest.approx(AN.E_S, abs=1e-15)
    assert AN.margin({"dynamics": {"intrinsic_drive_per_second": 0.08, "decay_per_second": 0.85, "threshold": 0.5}}) \
        == pytest.approx(0.08 / 0.15 - 0.5)


@pytest.mark.parametrize("silent", ["source1", "source2"])
def test_ct43_10_an_asymmetric_corner_source_never_fires_in_any_system_and_results_exist(silent) -> None:
    """命題 S-1・SE-C13（非対称な角）：一方の源を g ＜ −E_S に、もう一方の源と手がかりの Unit を最も発火しやすい角に置いた個体を、
    本番の Plan で measure_seed に通す。沈黙した源は作ったどの系（端の系・X1・X2・tr を含む）でも一度も発火しない。結果があること：
    もう一方の源はどの系でも発火し、どの系にも U の決まった窓があり、規則 c がその行動を指す本体と基の系では結果の刺激が成立している
    （真偽だけ。数・Pulse は表示しない）。その個体の T・S・D と、定まる段の C_k は 0 で、any は偽。"""
    data = corner_individual(silent)
    run = data["run"]
    firing = "source2" if silent == "source1" else "source1"
    action = {"source1": "A1", "source2": "A2"}[firing]
    roles = run["roles"]
    for n in M.BODIES + (M.RERUN,) + tuple(_built(run)):
        fired = {u for _p, u in _rec(run, n)["activity"]}
        assert roles[silent] not in fired and roles[firing] in fired, n
        u_windows = [r for r in _rec(run, n)["layer_a"] if r["window"] > FORMAL.e_windows]
        assert any(r["outcome"] == action for r in u_windows) and all(r["outcome"] in (action, A.NONE) for r in u_windows), n
    assert any(r[1] == A.CONSEQUENCE for r in run["bodies"][f"B_{action}"]["world_end"]["reserved"])
    assert _u_consequence(run["clones"][f"G_{action}_base"], FORMAL.p_e)
    ind = AN.individual(run)
    assert ind["S1"] == {"silent_source": {silent: True, firing: False}, "violations": []}
    for k in ("T_A1", "T_A2", "T", "S", "D"):
        assert ind["quantities"][k]["sign"] == "0", k                  # 定まり、ちょうど 0
    for k in LEVELS:
        c = ind["levels"][str(k)]["C"]
        assert c["class"] in ("structural_zero", "both_zero", "undefined") and c["any"] in (False, None), k
        assert c["value"]["sign"] in ("0", None)


def test_ct43_10_both_sources_silent_leave_every_share_undefined() -> None:
    run = zero_individual()["run"]
    roles = run["roles"]
    systems = M.BODIES + (M.RERUN,) + tuple(_built(run))
    assert all(roles["source1"] not in {u for _p, u in _rec(run, n)["activity"]} for n in systems)
    assert all(roles["source2"] not in {u for _p, u in _rec(run, n)["activity"]} for n in systems)
    assert any(roles["cue"] in {u for _p, u in _rec(run, n)["activity"]} for n in systems)
    ind = AN.individual(run)
    assert ind["S1"]["silent_source"] == {"source1": True, "source2": True} and ind["zero_label"] == "Z-1"
    assert all(v is None for v in ind["s_U"].values()) and ind["class"] == "undefined"   # 決まった窓がなく、s は定まらない


def test_ct43_10_the_s1_label_and_a_violation_are_reported_without_changing_the_judgment() -> None:
    s = decided_seed()
    run = measured(s)["run"]
    src = run["roles"]["source1"]
    d = run["birth_units"][src]["dynamics"]
    d["threshold"], d["intrinsic_drive_per_second"] = 0.55, 0.072    # 記録の上だけ、構造的に沈黙する源の値にする
    ind = AN.individual(run)
    assert ind["S1"]["silent_source"] == {"source1": True, "source2": False}
    fired = any(u == src for n in M.BODIES + (M.RERUN,) + tuple(_built(run)) for _, u in _rec(run, n)["activity"])
    assert ind["S1"]["violations"] == (["source1"] if fired else [])
    aux = AN.auxiliary({"1": ind})
    assert aux["R1"]["S1"]["labels_withdrawn"] is fired
    assert aux["R1"]["S1"]["individuals_with_silent_source"] == (None if fired else 1)
    zt = AN.descriptive({"1": ind})["zero_table"]
    assert (zt["structurally_silent_source"] is None) is fired
    assert "S1" not in json.dumps(AN.judge({"1": ind})) and "S1" not in json.dumps(AN.estimate({"1": ind}))


# ---- CT-43-12 独立の検算：合成の個体の解析と report のすべての欄 ---------------------------------------------------

REPORT_KEYS = {"mode", "valid", "outcome", "O1", "gate_declaration_sha256", "judgment", "estimate", "descriptive", "individuals",
               "auxiliary"}


def test_the_analysis_of_the_synthetic_individuals_runs_through_and_the_recheck_agrees() -> None:
    """合成の個体の解析が最後まで通る。標準のライブラリだけの独立の検算（recheck.py）が、report と一つずつ一致する。値は表示しない。"""
    runs = {s: measured(s) for s in SYN}
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=[])
    assert report["valid"] is True and set(report) == REPORT_KEYS
    j = report["judgment"]
    assert j["outcome"] == report["outcome"] in PROTOCOL["judgment"]["outcomes"] and j["J_C"]["m_def"] == report["estimate"]["m_def"]
    assert sum(j["J_C"]["counts"].values()) == len(SYN) and j["J_C"]["level"] == 2
    assert set(report["auxiliary"]) == {f"R{i}" for i in range(1, 10)}
    assert report["auxiliary"]["R4"]["pair_sum_max_abs_deviation"] <= AN.F1_TOLERANCE
    assert report["auxiliary"]["R4"]["clones_after_transplant"]["pair_sum_max_abs_deviation"] <= AN.F1_TOLERANCE
    assert all(v["as_expected"] is True for v in report["auxiliary"]["R5"].values())
    assert set(report["descriptive"]) == AL.MUST_REPORT_KEYS | {"notes"}
    assert set(report["descriptive"]["levels"]) == {str(k) for k in LEVELS}
    result = RC.recheck(runs, json.loads(json.dumps(report)))
    assert result["mismatches"] == [] and result["checks"] > 1000


def test_the_recheck_is_independent_and_detects_a_changed_report_or_raw() -> None:
    src = (EXP / "recheck.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    modules = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} \
        | {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert modules <= {"argparse", "copy", "gzip", "hashlib", "json", "math", "statistics", "sys", "collections", "fractions",
                       "pathlib"}
    assert "spec_from_file_location" not in src and "__import__" not in src and "exec(" not in src and "import yaml" not in src
    runs = {s: measured(s) for s in SYN[:4]}
    report = json.loads(json.dumps(AN.analyze_runs({s: measured(s) for s in SYN[:4]}, "synthetic", SMALL, o1=[])))
    assert RC.recheck(runs, report)["mismatches"] == []
    k = str(SYN[0])
    for tamper in (lambda rep, raw: rep["judgment"]["J_C"]["counts"].update({"+": rep["judgment"]["J_C"]["counts"]["+"] + 1}),
                   lambda rep, raw: rep.update(outcome="plus" if rep["outcome"] != "plus" else "minus"),
                   lambda rep, raw: rep["estimate"]["p_nz"].update(count=rep["estimate"]["p_nz"]["count"] + 1),
                   lambda rep, raw: rep["estimate"]["p_any"].update(count=rep["estimate"]["p_any"]["count"] + 1),
                   lambda rep, raw: rep["individuals"][k]["levels"]["2"]["C"].update(class_="?"),
                   lambda rep, raw: rep["individuals"][k].update(k_star="?"),
                   lambda rep, raw: raw[SYN[1]]["run"]["clones"]["G_A1_X1"]["pulse_weights"][3][1].__setitem__(0, 0.0011),
                   lambda rep, raw: raw[SYN[1]]["run"]["bodies"][M.RERUN]["layer_b"].append([9, "d", "s1", "A1"]),
                   lambda rep, raw: raw[SYN[3]]["run"]["bodies"][M.RERUN]["sigma_p_e"]["units"][
                       raw[SYN[3]]["run"]["roles"]["cue"]].update(activity=9.0),
                   lambda rep, raw: raw[SYN[2]]["run"]["clones"]["G_A2_base"]["layer_a"][-1].update(outcome="tie"),
                   lambda rep, raw: raw[SYN[2]]["run"]["difference"].update(delta_e="1/3")):
        rep, raw = copy.deepcopy(report), copy.deepcopy(runs)
        tamper(rep, raw)
        assert RC.recheck(raw, rep)["mismatches"]


COMMIT = "a" * 40                                                    # 照合の形だけを確かめる測定の commit（合成）


def _r6_keys() -> set[str]:
    out = {"B_A1|B_A2"}
    for c in ("A1", "A2"):
        names = [n for n in M.clone_names(LEVELS) if n[2:4] == c]
        out |= {f"G_{c}_base|{n}" for n in names if n != f"G_{c}_base"}
        out |= {f"G_{c}_{a}{k}|G_{c}_{b}{k}" for k in LEVELS for a, b in (("P", "M"), ("UP", "UM"))} | {f"G_{c}_X1|G_{c}_X2"}
    return out


SIGN_CELLS = {a + b for a in AN.SIGNS for b in AN.SIGNS}
GENERIC = (set(M.BODIES) | {M.RERUN} | set(M.clone_names(LEVELS)) | set(M.ROLES6) | _r6_keys() | SIGN_CELLS
           | {"A1", "A2", "X1", "X2", "+", "-", "0", "cue", "source1", "source2", "E", "U"} | set(AN.OTHER_QUANTITIES)
           | {f"{x}{k}" for x in ("C", "Du") for k in LEVELS} | {"delta_e"}
           | {f"{k}|{c}|{kind}|{side}" for k in LEVELS for c in ("A1", "A2") for kind in ("natural", "symmetric")
              for side in ("plus", "minus")}
           | {f"{kind}|{side}|{r}|{w}" for kind in ("natural", "symmetric") for side in ("plus", "minus") for r in M.ROLES6
              for w in ("below", "above")}
           | {f"{c}:{r}" for c in ("A1", "A2") for r in ("out_of_range", "s_undefined")})


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
    """欄の場所の形（seed・系・役・量の名前・段・列の位置を * にする）。同じ形の欄は、同じ書き方で照合される。"""
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
    """合成の個体（SYN[0]・k* のある個体・U に結果の刺激がある個体〔重なれば少なくなる〕と、構造的な 0 の構成の 1 個体：k* と札と
    s の欄に、値と null の両方が出る）。"""
    return {SYN[0]: measured(SYN[0]), decided_seed(): measured(decided_seed()), consequence_seed(): measured(consequence_seed()),
            CORNER_SEEDS[0]: zero_individual()}


@functools.cache
def _analyzed() -> str:
    """合成の個体（_runs3）の解析の report（解析の main と同じく measurement_commit を書き足した形。JSON を通す）。"""
    return json.dumps(AN.analyze_runs(_runs3(), "synthetic", SMALL, o1=[]) | {"measurement_commit": COMMIT})


@functools.cache
def _expected() -> str:
    return json.dumps(RC.expected_report(_runs3(), COMMIT))


def test_the_recheck_rebuilds_the_whole_report_and_compares_every_field() -> None:
    """raw から report の全体を組み立て直し、すべての葉を照合する（比べた葉の数 ＝ report の葉の数）。欄の形ごとに、その形の最初の葉の
    値を変えても、どの欄を消しても足しても、照合が失敗する（合成の個体の値は表示しない。失敗の文は場所だけ）。"""
    report = json.loads(_analyzed())
    mine = json.loads(_expected())
    checks, found = RC.compare(mine, report)
    paths = list(_leaves(report))
    scalars = [p for p in paths if not isinstance(_at(report, p), (dict, list))]
    assert found == [] and checks == len(scalars) > 3000                     # すべての葉を比べている
    assert {p[0] for p in paths} == set(report) == REPORT_KEYS | {"measurement_commit"}
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
    assert RC._loose("report.judgment.J_C.x.interval.interval[0]") and RC._loose("report.auxiliary.R1.S1.E_S")
    assert not RC._loose("report.estimate.p_nz.proportion") and not RC._loose("report.individuals.36301.birth.cue.margin_g")
    assert not RC._loose("report.individuals.36301.levels.2.C.value.value.value")
    report = json.loads(_analyzed())
    mine = json.loads(_expected())
    margin = report["individuals"][str(SYN[0])]["birth"]["cue"]
    margin["margin_g"] += 1e-12                                              # 書き方の同じ数は、わずかな違いも見つける
    assert RC.compare(mine, report)[1] == [f"report.individuals.{SYN[0]}.birth.cue.margin_g"]
    margin["margin_g"] -= 1e-12
    report["valid"] = 1                                                      # 真偽と数を取り違えない
    assert RC.compare(mine, report)[1] == ["report.valid"]


TARGETS = [("outcome",), ("judgment", "J_C", "m_nonzero"), ("judgment", "J_C", "m_def"), ("judgment", "J_C", "counts"),
           ("judgment", "J_C", "level"), ("judgment", "outcome"), ("judgment", "prominence"), ("judgment", "artificial"),
           ("estimate", "p_nz", "count"), ("estimate", "p_nz", "interval"), ("estimate", "p_any", "count"),
           ("estimate", "p_any", "interval"), ("estimate", "cancellations"), ("estimate", "p_dir"), ("estimate", "abs_C2"),
           ("estimate", "undefined"), ("estimate", "classes"), ("estimate", "notes"),
           ("descriptive", "notes"), ("descriptive", "levels"), ("descriptive", "common_all_levels"),
           ("descriptive", "out_of_range"), ("descriptive", "per_background"), ("descriptive", "one_sided"),
           ("descriptive", "base_strata"), ("descriptive", "symmetric_control"), ("descriptive", "T"),
           ("descriptive", "sensitivity"), ("descriptive", "natural_pair"), ("descriptive", "plasticity_contrast"),
           ("descriptive", "delta_e"), ("descriptive", "zero_table"), ("descriptive", "not_made"),
           ("auxiliary", "R1"), ("auxiliary", "R1", "S1", "E_S"), ("auxiliary", "R2", "G_A2_X1"), ("auxiliary", "R3", "C2"),
           ("auxiliary", "R3", "Du8"), ("auxiliary", "R3", "Z_A2"), ("auxiliary", "R3", "delta_e"), ("auxiliary", "R4", "W_A1"),
           ("auxiliary", "R4", "abs_W_diff"), ("auxiliary", "R4", "clones_after_transplant"), ("auxiliary", "R4", "not_built"),
           ("auxiliary", "R5", "G_A1_X2"), ("auxiliary", "R6"), ("auxiliary", "R7", "G_A2_X1"), ("auxiliary", "R8"),
           ("auxiliary", "R9"),
           ("individuals", None, "levels"), ("individuals", None, "quantities"), ("individuals", None, "delta_e"),
           ("individuals", None, "class"), ("individuals", None, "s_U"), ("individuals", None, "s_E"),
           ("individuals", None, "counts_U"), ("individuals", None, "counts_E"), ("individuals", None, "W"),
           ("individuals", None, "W_abs_diff"), ("individuals", None, "pair_deviation"), ("individuals", None, "built"),
           ("individuals", None, "not_built"), ("individuals", None, "base_class"), ("individuals", None, "e_zero"),
           ("individuals", None, "clone_pair_deviation"), ("individuals", None, "consequences"),
           ("individuals", None, "first_divergence"), ("individuals", None, "firing"), ("individuals", None, "birth"),
           ("individuals", None, "roles"), ("individuals", None, "S1"), ("individuals", None, "k_star"),
           ("individuals", None, "zero_label"), ("mode",), ("O1",), ("gate_declaration_sha256",), ("measurement_commit",)]


@pytest.mark.parametrize("target", TARGETS, ids=lambda t: ".".join(str(x) for x in t if x))
def test_the_recheck_fails_when_any_field_is_changed(target) -> None:
    """report のどの欄（J_C の数、E_C の p_nz・p_any・打ち消し、必ず報告する記述、R1〜R9、個体の量・区分・s・重み・作らない系・発火など）
    を変えても、recheck が失敗する。"""
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
                   lambda r: r["clones"]["G_A1_X1"]["pulse_weights"][2][1].__setitem__(0, 0.5),
                   lambda r: r["bodies"][M.RERUN]["activity"].pop(),
                   lambda r: r["boundary"]["sigma_p_e"]["B_A2"]["exit"].update(cursor=0),
                   lambda r: r["bodies"]["B_A2"]["sigma_0"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["boundary"]["sigma_a"]["G_A2_base"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["boundary"]["sigma_b"]["G_A1_X1"]["interventions"]["frozen"][min(r["W_0"])].update(weight=0.0123),
                   lambda r: r["clones"]["G_A2_tr"]["activity"].pop(),
                   lambda r: r["clones"]["G_A1_X2"]["sigma_after_first"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["clones"]["G_A2_X1"].update(world_switches=[[1, "x", False]]),
                   lambda r: r["X"]["X2"].update({min(r["W_0"]): 0.003}),
                   lambda r: r["boundary"]["steps"].pop(),
                   lambda r: r["difference"]["m"].update({"4": "1/5"}),
                   lambda r: r["clones"]["G_A1_base"]["sigma_end"].update(pulse=0)):
        data = measured(s)
        tamper(data["run"])
        assert RC.operation_problems(data)


# ---- CT-43-11 protocol の写しと、確定済みの事前登録の結び付き ------------------------------------------------

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
    "alpha_changed": _alter_protocol(("judgment", "J_C", "alpha", "per_direction"), 0.05),
    "min_population_changed": _alter_protocol(("judgment", "J_C", "min_population"), 5),
    "level_of_j_c_changed": _alter_protocol(("judgment", "J_C", "level"), 4),
    "k2_changed": _alter_protocol(("judgment", "k2_of_m", "200"), 114),
    "outcomes_changed": _alter_protocol(("judgment", "outcomes"), ["invalid", "not_established", "plus", "minus"]),
    "seeds_changed": _alter_protocol(("seeds", "last"), 36250),
    "timeline_changed": _alter_protocol(("timeline", "boundary_P_E"), 1064),
    "rule_c_changed": _alter_protocol(("world", "rule_c", "B_A1_rerun"), "A2"),
    "levels_changed": _alter_protocol(("weights", "levels"), [1, 2, 4]),
    "k0_changed": _alter_protocol(("weights", "k0"), 4),
    "u_changed": _alter_protocol(("weights", "u", "source1_to_source2"), 1),
    "scheme_changed": _alter_protocol(("weights", "scheme"), "absolute"),
    "extremes_changed": _alter_protocol(("extremes", "X1", "C_to_source1"), 0.009),
    "f1_changed": _alter_protocol(("f1_tolerance",), 1e-6),
    "gate_changed": _alter_protocol(("inherited_gate_set", "sha256"), "0" * 64),
    # 以下は PREREGISTERED で個別に照らさない欄。写しの中身全体のハッシュで見つける
    "J_C_rule_changed": _alter_protocol(("judgment", "J_C", "rule"), "plus if count(plus) > m_def / 2"),
    "inconclusive_reading_changed": _alter_protocol(("judgment", "inconclusive_reading"), "stretched weights do not reach choice"),
    "arithmetic_changed": _alter_protocol(("weights", "arithmetic"), "clip every endpoint to [0, w_max]"),
    "null_changed": _alter_protocol(("judgment", "null_hypothesis", "H0_C"), "P(C_2 > 0) = 1/2 among all individuals"),
    "population_changed": _alter_protocol(("judgment", "per_individual", "structural_zero"), "excluded"),
    "m_def_redefined": _alter_protocol(("estimate_E_C", "m_def"), "all 200 individuals"),
    "operation_check_dropped": _alter_protocol(("operation_checks",), ["O1", "O2", "O3"]),
}
UNCOMPARED = ("J_C_rule_changed", "inconclusive_reading_changed", "arithmetic_changed", "null_changed", "population_changed",
              "m_def_redefined", "operation_check_dropped")


def test_the_preregistered_values_in_the_recheck_are_the_protocol_values() -> None:
    """recheck.py が書き起こした値（PREREGISTERED）が、確定済みの protocol.yaml の値と同じ。正本の写しは結び付きを通る。"""
    pr, jc, tl, br, wt = RC.PREREGISTERED, PROTOCOL["judgment"]["J_C"], PROTOCOL["timeline"], PROTOCOL["brain"], PROTOCOL["weights"]
    assert pr["experiment"] == PROTOCOL["experiment"] and pr["kind"] == PROTOCOL["kind"]
    assert pr["alpha_per_direction"] == Fraction(str(jc["alpha"]["per_direction"])) == Fraction(1, 40)
    assert pr["alpha_two_sided"] == Fraction(str(jc["alpha"]["two_sided"])) and pr["min_population"] == jc["min_population"]
    assert pr["k2_200"] == PROTOCOL["judgment"]["k2_of_m"][200] and pr["outcomes"] == PROTOCOL["judgment"]["outcomes"]
    assert (pr["experience_windows"], pr["experience_pulses"], pr["boundary_P_E"]) == \
        (tl["experience_E"]["windows"], tl["experience_E"]["pulses"], tl["boundary_P_E"])
    assert (pr["test_windows"], pr["test_pulses"], pr["body_pulses"]) == (tl["test_U"]["windows"], tl["test_U"]["pulses"],
                                                                          tl["body_pulses"])
    assert (pr["w_min"], pr["w_max"], pr["w0"]) == (br["w_min"], br["w_max"], br["initial_weight_w0"])
    assert pr["f1_tolerance"] == AN.F1_TOLERANCE == PROTOCOL["f1_tolerance"]
    assert (pr["levels"], pr["k0"], pr["scheme"]) == (wt["levels"], wt["k0"], wt["scheme"]) and pr["k0"] == jc["level"]
    assert pr["rule_c"] == {k: v for k, v in PROTOCOL["world"]["rule_c"].items() if k != "background"}
    assert pr["extremes"] == M.extremes(PROTOCOL)
    assert all(pr[k] == PROTOCOL[k] for k in ("seeds", "smoke_seeds", "synthetic_seeds"))
    assert pr["formal_plan"] == dataclasses.asdict(FORMAL) and pr["individuals"] == AX.INDIVIDUALS
    assert RC.PROTOCOL_FILE == EXP / "protocol.yaml"
    assert RC._preregistered_values(json.loads(json.dumps(PROTOCOL))) == []
    assert RC.protocol_problems({s: measured(s) for s in SYN[:2]}) == []
    gate = PROTOCOL["inherited_gate_set"]
    assert (RC.GATE_FILE, RC.GATE_SHA256) == (gate["declaration"], gate["sha256"]) and RC.GATE_SHA256 == AN.GATE_SHA256
    assert RC.gate_problems({s: measured(s) for s in SYN[:2]}) == [] and RC.REPO_ROOT == ROOT
    assert (RC.START, RC.FINISH, RC.RAW, RC.SEEDS_DIR) == (R.G.START, R.G.FINISH, R.G.RAW, R.G.SEEDS_DIR)
    assert (RC.REPORT, RC.O1_FILE, RC.O1_KEYS, RC.CONTRACT_TESTS) == (AN.REPORT, AN.O1_FILE, AN.O1_KEYS, AN.CONTRACT_TESTS)
    assert (RC.BODIES, RC.RERUN, RC.ACTIONS) == (list(M.BODIES), M.RERUN, M.BACKGROUNDS)


def test_the_recheck_holds_the_fixed_hashes_of_the_preregistered_protocol() -> None:
    """recheck.py の固定のハッシュが、事前登録 v0.2 の protocol.yaml（このリポジトリの正本）から計算し直した値と同じ。"""
    stored = json.loads(json.dumps(PROTOCOL))                               # raw の meta と同じ形
    assert RC.canonical_protocol_sha256(stored) == RC.PROTOCOL_JSON_SHA256
    assert hashlib.sha256((EXP / "protocol.yaml").read_bytes()).hexdigest() == RC.PROTOCOL_FILE_SHA256 == AN.PROTOCOL_SHA256
    canonical = json.dumps(stored, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == RC.PROTOCOL_JSON_SHA256   # 正規化の仕方を独立に書き直しても同じ
    assert RC.PROTOCOL_JSON_SHA256 == "ccb945bf6535eceec1de09dffe81022260898dbb4826fbccc0fb3de8c4205e0d"     # v0.2
    assert RC.PROTOCOL_FILE_SHA256 == "aad8053fd56e7b69e3cb6fef2c325514800ea4dccc1033125259aaff826cfcad"
    frozen = subprocess.run(["git", "-C", str(ROOT), "show", "8fee59e817e96918de4125ee66d4d8de3effc450:"
                             "experiments/0043_as2b_natural_difference_scaling/protocol.yaml"], capture_output=True)
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
    far = {s: far_individual(s) for s in SYN[:1]}
    far[SYN[0]]["run"]["plan"] = dataclasses.asdict(FORMAL)                  # 本番の Plan でも、段の組が違えば
    far[SYN[0]]["meta"]["mode"] = "formal"
    assert any("段の組" in m for m in RC.protocol_problems(far))
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


# ---- CT-43-12 独立の検算：測定の来歴と全件性 ------------------------------------------------------------------

DIR_SEEDS = SYN[:3]


def _o1_record(commit: str) -> dict:
    """run.py の record_contract_tests が書く O1 の記録と同じ形（テストのファイルの SHA-256 は、このリポジトリのもの）。"""
    return {"measurement_commit": commit, "command": ["python", "-m", "pytest", "-q", *AN.CONTRACT_TESTS], "exit_code": 0,
            "summary": "999 passed in 300.00s", "test_files_sha256": {f: R.G.sha256_file(ROOT / f) for f in AN.CONTRACT_TESTS},
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
    "raw_weight_changed": lambda o: _rewrite_raw(o, _C, lambda d: d["run"]["clones"]["G_A1_X1"]["pulse_weights"][0][1].__setitem__(
        0, 0.0049)),
    "raw_outcome_changed": lambda o: _rewrite_raw(o, _C, lambda d: d["run"]["clones"]["G_A2_base"]["layer_a"][-1].update(
        outcome="tie")),
    "raw_endpoint_changed": lambda o: _rewrite_raw(o, _C, lambda d: d["run"]["difference"].update(delta_e="1/3")),
    # フォルダ
    "renamed_folder": lambda o: R.G.seed_dir(o, _B).rename(R.G.seed_dir(o, 36309)),
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
    "o1_test_file": lambda o: _json_edit(o / AN.O1_FILE, lambda r: r["test_files_sha256"].update({AN.CONTRACT_TESTS[6]: "0" * 64})),
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


def test_the_recheck_main_writes_the_result_and_shows_only_counts(done, tmp_path) -> None:
    out = tmp_path / "recheck.json"
    proc = subprocess.run([sys.executable, str(EXP / "recheck.py"), str(done), "--write", str(out)], capture_output=True,
                          text=True, cwd=ROOT)
    assert proc.returncode == 0 and set(json.loads(proc.stdout)) == {"individuals", "checks", "mismatches"}
    assert json.loads(proc.stdout)["mismatches"] == 0 and json.loads(out.read_text(encoding="utf-8"))["mismatches"] == []


def test_the_seed_set_of_the_formal_run_is_exactly_the_preregistered_200() -> None:
    formal = list(range(36001, 36201))
    assert RC.seed_set_problems("formal", formal) == []
    assert RC.seed_set_problems("formal", formal[:57] + formal[58:])                 # 欠け
    assert RC.seed_set_problems("formal", formal + [36201])                           # 範囲の外（smoke の seed）
    assert RC.seed_set_problems("formal", formal + [36001])                           # 重複
    assert RC.seed_set_problems("formal", [*formal[:-1], 35200])                       # 0042 の seed（欠けと範囲の外）
    assert RC.seed_set_problems("synthetic", SYN) == []
    assert RC.seed_set_problems("synthetic", [36001]) and RC.seed_set_problems("synthetic", [])
    assert RC.seed_set_problems("smoke", [36201]) and RC.seed_set_problems(None, SYN)
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
    assert 'records["state"], records["problems"] = "failed"' in src
    assert src.index("verify_clean_commit") < src.index("analyze_runs(runs, mode, o1=o1)")
    assert "analyze_runs(runs, mode, o1=o1)" in src and "levels" not in src[src.index("analyze_runs(runs, mode"):][:40]


# ---- 操作の確認が、記録の食い違いを見つける（structure・O2・O3・O13・O14・O15） ---------------------------------

def test_structure_detects_extra_fields_and_wrong_records() -> None:
    s = SYN[0]

    def first_end(d, inside=True):
        return next(n for n in M.endpoint_names(LEVELS) if d["run"]["endpoints"][n]["in_range"] is inside)
    for tamper in (lambda d: d["run"].update(judgment={}), lambda d: d.update(extra=1),
                   lambda d: d["run"]["bodies"]["B_A1"].update(T=0.5), lambda d: d["run"]["bodies"].pop("B_A1_rerun"),
                   lambda d: d["run"]["clones"].pop("G_A2_X1"), lambda d: d["run"]["clones"]["G_A1_X1"].update(s=0.5),
                   lambda d: d["run"]["clones"].pop(first_end(d)),
                   lambda d: d["run"]["endpoints"][first_end(d)].update(weights=None),
                   lambda d: d["run"]["endpoints"][first_end(d)].update(note=1),
                   lambda d: d["run"]["endpoints"].pop("G_A2_UM8"),
                   lambda d: d["run"]["difference"].pop("m"),
                   lambda d: d["run"]["difference"]["m"].pop("8"),
                   lambda d: d["run"].update(levels=[2, 1, 4, 8]),
                   lambda d: d["run"].update(levels=[1, 2, 4]),
                   lambda d: d["run"]["roles"].update(cue=d["run"]["roles"]["source1"]),
                   lambda d: d["run"]["W_0"].update({min(d["run"]["W_0"]): 0.004}),
                   lambda d: d["run"].update(seed=s + 1), lambda d: d["meta"].update(manifest={}),
                   lambda d: d["run"]["plan"].update(e_windows=2),
                   lambda d: d["run"]["bodies"]["B_A1_rerun"].update(pulse_weights=[]),
                   lambda d: d["run"]["bodies"]["B_A2"].pop("first_intent"),
                   lambda d: d["run"]["bodies"]["B_A2"]["audit"].pop("ok"),
                   lambda d: d["run"]["clones"]["G_A2_base"]["audit"].update(ok=True),
                   lambda d: d["run"]["boundary"].update(T={}),
                   lambda d: d["run"]["boundary"]["sigma_a"].pop("G_A1_tr"),
                   lambda d: d["run"]["X"].pop("X2")):
        data = measured(s)
        tamper(data)
        assert "structure" in failures(data, s)
    data = far_individual(decided_seed())                                 # 範囲の外の端の系を作った記録
    out = next(n for n in M.endpoint_names(FAR) if not data["run"]["endpoints"][n]["in_range"])
    data["run"]["clones"][out] = copy.deepcopy(data["run"]["clones"][f"G_{out[2:4]}_base"])
    assert "structure" in failures(data, decided_seed(), SMALL, FAR)
    assert "structure" in failures(far_individual(decided_seed()), decided_seed(), SMALL, LEVELS)   # 使う段の組と違う


def test_o2_detects_a_different_gate_set_or_world() -> None:
    s = SYN[0]
    for tamper in (lambda d: d["meta"]["gate"].update(sha256="0" * 64),
                   lambda d: d["meta"]["gate"]["declaration"]["schedule"].update(window_length_W=18),
                   lambda d: d["meta"].pop("gate"),
                   lambda d: d["run"]["bodies"]["B_A2"]["world_end"]["rule"].update(delay=3),
                   lambda d: d["run"]["bodies"]["B_A1"]["world_end"]["rule"].update(rule_c="A2"),
                   lambda d: d["run"]["clones"]["G_A2_base"]["world_end"]["rule"].update(rule_c="A1"),
                   lambda d: d["run"]["clones"]["G_A1_X2"]["world_end"]["rule"].update(respond=False),
                   lambda d: d["run"]["bodies"]["B_A1"]["layer_a"][2].update(close=d["run"]["bodies"]["B_A1"]["layer_a"][2]["close"] + 1),
                   lambda d: d["run"]["bodies"]["B_A1"]["world_end"]["reserved"][0].__setitem__(3, 40),
                   lambda d: d["run"]["clones"]["G_A2_X1"].update(pulse_end=SMALL.end - 1),
                   lambda d: d["run"]["bodies"]["B_A2"]["sigma_end"]["exit"]["windows"][0].__setitem__(2, 60),
                   lambda d: d["run"]["bodies"]["B_A1"]["history"].append([0, "x", []])):
        data = measured(s)
        tamper(data)
        assert "O2" in failures(data, s)
    formal = measured(s)
    formal["meta"]["mode"] = "formal"
    assert AN.check_seed(formal, "formal", s, SMALL)["structure"]            # 本番では小さい Plan を使えない
    assert AN.check_seed(formal, "formal", s, None, FAR)["structure"]        # 本番では protocol の段の組だけ


def test_o3_detects_a_broken_audit() -> None:
    s = decided_seed()
    for tamper in (lambda r: r["bodies"]["B_A1"]["layer_b"].append([9, "d-x", r["roles"]["source1"], "A1"]),
                   lambda r: r["bodies"]["B_A1"]["layer_b"].pop(),
                   lambda r: r["clones"]["G_A1_X1"]["layer_a"].pop(),
                   lambda r: r["bodies"]["B_A1"]["delta_log"].pop(),
                   lambda r: r["clones"]["G_A2_base"]["delta_log"].append([1, "d", "s1", "A1"]),
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

    def decided(r, n="G_A1_base"):
        return next(x for x in _rec(r, n)["layer_a"] if x["outcome"] in A.ACTION_IDS)
    for tamper in (lambda r: decided(r).update(outcome="A2" if decided(r)["outcome"] == "A1" else "A1"),
                   lambda r: decided(r, "B_A2").update(emit_pulse=decided(r, "B_A2")["emit_pulse"] + 1),
                   lambda r: decided(r, "G_A1_X1").update(winner_unit=r["roles"]["cue"]),
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
        mp.setattr(AN.AX, "quantities", lambda s_: dict(AN.written_out_quantities(AN.AX.LEVELS, s_), T=Fraction(7)))
        assert "O14" in failures(data, s)


def test_o15_rejects_seeds_outside_the_range_or_seen() -> None:
    assert AN.check_seed(measured(SYN[0]), "synthetic", SYN[0], SMALL)["O15"] == []
    for seed in (31001, 32001, 32301, 30201, 33001, 33301, 34001, 34301, 35001, 35301, 35399, 36001, 36201):
        out: list[str] = []
        AN._o15(seed, "synthetic", out)
        assert out
    out = []
    AN._o15(35001, "formal", out)
    assert len(out) == 2                                                       # 範囲の外で、かつ 0042 で走らせた seed


def test_meta_blind_must_match_the_mode() -> None:
    s = SYN[0]
    data = measured(s)
    data["meta"]["blind"] = "no"
    assert "structure" in failures(data, s)
    assert AN.check_seed(dict(measured(s), meta=dict(measured(s)["meta"], blind=True)), "formal", s, SMALL)["structure"]


# ---- CT-43-11 一度限りの実行（guard と run.execute。dummy の計算。0040〜0042 と同じ） ------------------------------------

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
        R.execute("formal", [36001], tmp_path / "o", repo, None, runner=_dummy, executor_factory=SerialExecutor)
    assert not (tmp_path / "o").exists()
    assert R.OUT_DIR == Path("data/experiments/0043") and AN.OUT_DIR == R.OUT_DIR and R.MAX_WORKERS == 2
    assert list(R.allowed_seeds("formal")) == list(range(36001, 36201)) == AN.expected_seeds("formal")
    assert list(R.allowed_seeds("smoke")) == list(range(36201, 36207))
    assert list(R.allowed_seeds("synthetic")) == SYN_ALL


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
    assert report["valid"] is True and sum(report["judgment"]["J_C"]["counts"].values()) == 3
    assert report["judgment"]["outcome"] == "inconclusive"                    # 3 個体では m≠ ＜ 10（算術）
    assert _complete(out, seeds) == json.loads(json.dumps(report | {"measurement_commit": records["measurement_commit"]}))
    assert RC.recheck_directory(out)["mismatches"] == []                       # 保存したファイルからの独立の検算


# ---- CT-43-11 smoke の盲検：現象の数値を保存しない（0040〜0042 と同じ） -------------------------------------------------

FORBIDDEN_KEYS = ((AN.RUN_KEYS - {"seed", "plan", "roles"}) | AN.END_KEYS | set().union(*AN.BODY_KEYS.values()) | AN.CLONE_KEYS
                  | AN.BOUNDARY_KEYS | AN.ENDPOINT_KEYS | JUDGMENT_KEYS
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
            assert not ISO_TIME.search(json.dumps(rec)), d
            assert _numeric_keys(rec) <= NUMERIC_OK, d


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
    for tamper, check in ((lambda r: r["clones"]["G_A2_X1"]["pulse_weights"][3][1].__setitem__(0, 0.0111), "O7"),
                          (lambda r: r["bodies"][M.RERUN].update(sigma_p_e_sha256="0" * 64), "O13"),
                          (lambda r: r["bodies"]["B_A2"]["sigma_0"]["units"][r["roles"]["cue"]].update(activity=9.0), "O4"),
                          (lambda r: r["clones"]["G_A1_tr"]["activity"].pop(), "O8"),
                          (lambda r: r["difference"].update(delta_e="1/3"), "O10")):
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
    for mode, seeds, kw in (("smoke", [36201], {"blind": False}), ("formal", [36001], {"blind": True}),
                            ("smoke", [36201], {"check_plan": SMALL})):
        out = tmp_path / f"o_{mode}_{min(kw)}"
        with pytest.raises(R.G.GuardError):
            R.execute(mode, seeds, out, repo, commit, runner=_dummy, executor_factory=SerialExecutor, **kw)
        assert not out.exists()


# ---- O1 の証拠（0040〜0042 と同じ） ---------------------------------------------------------------------------

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
    assert len(AN.CONTRACT_TESTS) == 7 and AN.o1_check(out, commit) == []
    R.record_contract_tests(repo, out, commit, run=lambda *a, **k: pytest.fail("走らせ直さない"))


def _never(*a, **k):
    raise AssertionError("O1 が成り立たないのに、契約テストの実行か seed の計算に進んだ")


@pytest.mark.parametrize("name,tamper", [
    ("終了コード", lambda r: r.update(exit_code=1)),
    ("結果の行", lambda r: r.update(summary="1 failed, 498 passed in 50.0s")),
    ("テストのファイルの SHA-256", lambda r: r["test_files_sha256"].update({AN.CONTRACT_TESTS[6]: "0" * 64})),
    ("走らせたコマンド", lambda r: r.update(command=["python", "-m", "pytest", "-q", *AN.CONTRACT_TESTS[:6]])),
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
