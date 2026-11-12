"""実験 0039 の道具の契約テスト（確定した事前登録 v0.2 の README・protocol.yaml、#179 merge `ba7ffba`）。

本番の seed（32001〜32200）・smoke の seed（32201〜32206）・関門の seed（31001〜31040）は使わない（実行もしない）。0034〜0037 の
seed・raw も、関門の記録も使わない。合成の契約テスト専用の範囲（32301〜32399）だけを使う。合成の個体は、本番と同じ道具
（measure.measure_seed）・同じ式で、区間だけを小さくした Plan（SMALL：8 窓、E ＝ 窓 1〜4、P_E ＝ 204、終わり 350。E1 は E ＝ 窓 1）か、
本番の Plan で、実物の runtime を通して作る。結果を見て Plan・seed を選んでいない（seed は範囲の最初から順に、構成の条件だけで
決定的に選ぶ）。テストは操作の確認・記録の形・介入の部品の決まり方・Runtime の順序・判定の算術だけを確かめ、合成の個体の
判定の量（A1 の割合・差・符号・J_7・J_W・区間・対照の数）の値を表示も判定もしない。

構成（README §14 の契約テストの要件）：
- 適格（E に決まった窓がある）・適格外（E に決まった窓がない）：SMALL の本体 B^{A1} の層 A の、決まった窓の有無だけで選ぶ
- 構造上の恒等（W^{A1} ＝ W^{A2}）：E1 で、最初の決まった窓が E の後の最初の個体（二つの本体が P_E まで同じ）
- SE-6 の Runtime の順序：AS2b の道具を直接使い、境界で 1 本の重みだけを大きく替えた複製（契約テストだけの値）
- 命題 S-1・補題 L1・L2：Unit の θ・c を出生時の範囲の角に置き、6 本の重みを w_max で止めた合成の系（契約テストだけの値）

使った合成の seed（PR に開示）：32301〜32310（SMALL）、32321〜32326（一度限りの実行・盲検の契約。dummy の計算と SMALL）、
32390〜32392（S-1・L1・L2 の角の系と SE-5）、32399（本番の Plan で実物の runtime を通す確かめと、関門の本体との同一）、
構成の条件で選んだ個体（32301〜32399 の最初から順。どれになったかはテストの中で決まる）。
"""

import ast
import copy
import dataclasses
import functools
import gzip
import importlib.util
import inspect
import itertools
import json
import re
import subprocess
from concurrent.futures import Future
from fractions import Fraction
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments" / "0039_as2b_rule_dependence"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = _load("measure_0039_test", EXP / "measure.py")
AN = _load("analyze_0039_test", EXP / "analyze.py")
AL = _load("alignment_0039_test", EXP / "alignment.py")
R = _load("run_0039_test", EXP / "run.py")
RC = _load("recheck_0039_test", EXP / "recheck.py")
GATE = _load("gate_0038_for_0039_test", ROOT / "experiments" / "0038_as2b_forward_gate" / "gate.py")
A, AS1 = M.A, M.AS1
SMALL = M.Plan(41, 41, 8, 2, 19, 2, 4)
E1 = M.Plan(41, 41, 8, 2, 19, 2, 1)
FORMAL = M.formal_plan(PROTOCOL)
SYN = list(range(32301, 32311))
SYN_ALL = list(range(32301, 32400))
GUARD_SEEDS = list(range(32321, 32327))
CORNER_SEEDS = (32390, 32391, 32392)
FORMAL_SEED = 32399
W_MAX = PROTOCOL["brain"]["w_max"]


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)


def _meta(seed: int, mode: str = "synthetic") -> dict:
    return {"experiment": "0039", "kind": PROTOCOL["kind"], "mode": mode, "seed": seed, "manifest": M.manifest_raw(),
            "gate": {"sha256": AN.GATE_SHA256, "declaration": AN.GATE_DECLARATION}, "blind": mode == "smoke"}


def _raw(run: dict, mode: str = "synthetic") -> dict:
    return {"meta": _meta(run["seed"], mode), "run": run}


@functools.cache
def _measured(seed: int, plan: M.Plan) -> str:
    return json.dumps(_raw(M.measure_seed(PROTOCOL, seed, plan)))


def measured(seed: int, plan: M.Plan = SMALL) -> dict:
    """実物の runtime を通した合成の個体の生の記録（JSON を通した形。返すのは複製）。"""
    return json.loads(_measured(seed, plan))


def failures(data: dict, seed: int, plan: M.Plan = SMALL) -> dict:
    return {k: v for k, v in AN.check_seed(data, "synthetic", seed, plan).items() if v}


def _log():
    return AS1.AS1Log(keep=M.LOG_KEEP)


@functools.cache
def k_star(seed: int, plan: M.Plan = SMALL) -> int | None:
    """本体 B^{A1} の最初の決まった窓（構成の条件にだけ使う。値は表示しない）。"""
    s = M.build_body(plan, seed, "A1", log=_log())
    A.advance_to(s.app, plan.end)
    first = AN.first_decided([dict(r) for r in s.decider.records])
    return None if first is None else first["window"]


@functools.cache
def eligible_seed() -> int:
    """SMALL の E に決まった窓がある最初の合成の個体。"""
    return next(s for s in SYN_ALL if k_star(s) is not None and k_star(s) <= SMALL.e_windows)


@functools.cache
def ineligible_seed() -> int:
    """SMALL の E に決まった窓がない最初の合成の個体（適格外 (a)）。"""
    return next(s for s in SYN_ALL if k_star(s) is None or k_star(s) > SMALL.e_windows)


@functools.cache
def identity_seed() -> int:
    """E1 で、最初の決まった窓が E の後にある最初の合成の個体（二つの本体が P_E まで同じ ⇒ W^{A1} ＝ W^{A2}）。"""
    return next(s for s in SYN_ALL if k_star(s, E1) is not None and k_star(s, E1) > E1.e_windows)


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
                   lambda d: d["bodies"].update(interventions="freeze"),
                   lambda d: d["bodies"].update(pulses=2073),
                   lambda d: d["roles"].update(stream="other-{seed}")):
        changed = copy.deepcopy(decl)
        tamper(changed)
        with pytest.raises(ValueError):
            M.plan_from_declaration(changed, 25)


def test_the_boundary_has_no_open_window_and_no_reservation_by_arithmetic() -> None:
    """P_E ＝ c_(E+1) − 1。E の最後の窓の結果は遅くとも b_E ＋ L で、P_E より前（README §1.2）。"""
    for plan in (FORMAL, SMALL, E1):
        windows = plan.schedule().windows
        assert windows[plan.e_windows - 1][2] + plan.delay < plan.p_e < plan.schedule().cues[plan.e_windows]
        assert plan.end == windows[-1][2] + plan.delay


def test_the_run_entry_point_uses_only_the_protocol_plan() -> None:
    assert "W.measure_seed(PROTOCOL, seed)" in inspect.getsource(R.measure)
    assert "plan" not in inspect.signature(R.measure).parameters


def test_seen_seeds_include_0037_and_the_gate_and_exclude_0039() -> None:
    assert {30001, 30100, 30101, 30201, 30299, 31001, 31040, 9101} <= AL.SEEN
    assert not ({32001, 32200, 32201, 32206, 32301, 32399} & AL.SEEN)


def test_contract_tests_of_o1_are_the_tool_tests_and_this_file() -> None:
    assert AN.CONTRACT_TESTS == (*PROTOCOL["tools"]["contract_tests"], "tests/integration/test_as2b_rule_dependence_0039.py")
    assert R.CONTRACT_TESTS == AN.CONTRACT_TESTS and (ROOT / AN.CONTRACT_TESTS[-1]) == Path(__file__).resolve()


def test_the_analysis_contrasts_and_controls_follow_the_protocol() -> None:
    q = PROTOCOL["quantities"]["contrasts"]
    assert {k: list(v) for k, v in AN.CONTRASTS.items()} == q and list(AN.CONTRASTS) == list(q)
    assert list(AN.MUST_REPORT) == PROTOCOL["must_report"]["contrasts"]
    assert list(AN.DESCRIPTIVE) == PROTOCOL["must_report"]["descriptive"]
    assert set(AN.WITHIN_RULE) == set(AN.DESCRIPTIVE) and all(AN.WITHIN_RULE[n] == n.split("_")[1] for n in AN.WITHIN_RULE)
    assert AN.CHECK_NAMES[1:] == tuple(PROTOCOL["operation_checks"][1:])


# ---- 合成の個体が、すべての操作の確認を通る ------------------------------------------------------------

@pytest.mark.parametrize("seed", SYN)
def test_synthetic_individuals_pass_every_operation_check(seed) -> None:
    assert failures(measured(seed), seed) == {}


def test_the_formal_plan_through_the_runtime_passes_every_operation_check() -> None:
    data = measured(FORMAL_SEED, FORMAL)
    assert AN.check_seed(data, "synthetic", FORMAL_SEED, None) == {k: [] for k in AN.CHECK_NAMES}
    run = data["run"]
    assert [len(run["bodies"][n]["layer_a"]) for n in M.BODIES] == [50, 50]
    assert len(run["G"]["G_A1_WA2"]["pulse_weights"]) == 1007 and len(run["bodies"]["F_A1"]["pulse_weights"]) == 2072


@pytest.mark.parametrize("which", ["eligible", "ineligible", "identity"])
def test_the_constructed_individuals_pass_every_operation_check(which) -> None:
    seed, plan = _constructed(which)
    assert failures(measured(seed, plan), seed, plan) == {}


def _constructed(which: str) -> tuple[int, M.Plan]:
    return {"eligible": (eligible_seed(), SMALL), "ineligible": (ineligible_seed(), SMALL),
            "identity": (identity_seed(), E1)}[which]


JUDGMENT_KEYS = {"share", "s_U", "s_E", "sign", "difference", "contrasts", "in_population", "ineligible_a", "k_star", "prefix",
                 "structural_identity", "J_7", "J_W", "judgment", "individuals", "auxiliary", "descriptive_controls",
                 "interval", "counts_U", "counts_E", "S1", "first_divergence", "undefined_kind", "eligible"}


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


# ---- CT-39-1 本体の同一（関門の run_body と同じ組み立て） -------------------------------------------------

def test_ct39_1_the_bodies_are_the_gate_run_body() -> None:
    """本番の Plan の B^{A1}・B^{A2}・B′^{A1} が、関門の run_body（宣言 v0.2）と、層 A・層 B・終わりの Σ で一致する。"""
    decl = AN.GATE_DECLARATION
    run = measured(FORMAL_SEED, FORMAL)["run"]
    for name in (*M.BODIES, M.RERUN):
        c = M.RULE_OF[name]
        _row, audit = GATE.run_body(A, decl, FORMAL_SEED, c)
        rec = run["bodies"][name]
        assert json.loads(json.dumps(audit["layer_a"])) == rec["layer_a"] and audit["audit"]["ok"] is True
        assert json.loads(json.dumps(audit["layer_b"])) == rec["layer_b"]
        gate_like = A.build(FORMAL_SEED, schedule=GATE.schedule_of(decl, A), delay=decl["world"]["delay_L"], rule_c=c,
                            respond=True)
        A.advance_to(gate_like.app, decl["bodies"]["pulses"])
        assert M.sigma_sha256(M._sigma(gate_like)) == rec["sigma_end_sha256"]


def test_ct39_1_build_body_uses_the_declared_values_only() -> None:
    src = inspect.getsource(M.build_body)
    assert "A.build(seed, schedule=plan.schedule(), delay=plan.delay, rule_c=rule_c, respond=True" in src
    body = M.build_body(SMALL, SYN[0], "A2")
    assert body.meta == {"delay": 2, "rule_c": "A2", "respond": True, "outlet": True, "world_cues": True}
    assert body.log.keep == AS1.AS1Log.DEFAULT_KEEP and body.connections.history == []


def test_the_gate_seeds_and_the_formal_seeds_are_never_run_by_the_tests(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    commit = _git(repo, "rev-parse", "HEAD")
    for seed in (31001, 31040, 32001, 32201, 30201):
        with pytest.raises(R.G.GuardError):
            R.execute("synthetic", [seed], tmp_path / f"o{seed}", repo, commit, runner=_dummy, executor_factory=SerialExecutor)
        assert not (tmp_path / f"o{seed}").exists()
    for mode in ("formal", "smoke"):
        with pytest.raises(R.G.GuardError):
            R.execute(mode, [31001], tmp_path / f"g{mode}", repo, commit, runner=_dummy, executor_factory=SerialExecutor)


# ---- CT-39-2 共通の部分（SE-1） ------------------------------------------------------------------------

def test_ct39_2_the_two_bodies_share_the_prefix_up_to_the_first_intent() -> None:
    s = eligible_seed()
    run = measured(s)["run"]
    for a, b in AN.PREFIX_PAIRS:
        ra, rb = run["bodies"][a], run["bodies"][b]
        assert AS1.sigma_diff(ra["sigma_0"], rb["sigma_0"]) == [("world", "rule", "rule_c")]
        first = AN.first_decided(ra["layer_a"])
        k, t = first["window"], first["decision_pulse"] + 1
        assert ra["layer_a"][:k] == rb["layer_a"][:k] and ra["first_intent"]["pulse"] == rb["first_intent"]["pulse"] == t
        sa, sb = ra["first_intent"]["sigma"], rb["first_intent"]["sigma"]
        for key in ("units", "connections", "drives", "deltas", "issuer", "runtime", "exit", "interventions", "pulse"):
            assert sa[key] == sb[key], key
        assert sa["world"]["intents"] == sb["world"]["intents"] and len(sa["world"]["intents"]) == 1
        # 結果の予約は、最初の決まった窓の行動を規則 c が指す本体にだけある
        cons = {n: [r for r in sig["world"]["pending"] if r[1] == A.CONSEQUENCE] for n, sig in ((a, sa), (b, sb))}
        owner = a if first["action"] == M.RULE_OF[a] else b
        other = b if owner == a else a
        assert len(cons[owner]) == 1 and cons[other] == [] and cons[owner][0][3] == t + SMALL.delay - 1
    assert AN.prefix_label(run["bodies"]["B_A1"]["layer_a"], SMALL.e_windows) == \
        AN.prefix_label(run["bodies"]["B_A2"]["layer_a"], SMALL.e_windows)


def test_ct39_2_without_a_decided_window_in_e_the_bodies_are_identical_through_p_e() -> None:
    s = ineligible_seed()
    run = measured(s)["run"]
    b = run["boundary"]
    assert [tuple(p) for p in AS1.sigma_diff(b["sigma_p_e"]["B_A1"], b["sigma_p_e"]["B_A2"])] == [("world", "rule", "rule_c")]
    assert b["W"]["A1"] == b["W"]["A2"]
    label = AN.prefix_label(run["bodies"]["B_A1"]["layer_a"], SMALL.e_windows)
    assert label["ineligible_a"] is True and label["ineligible_kind"] in ("a1_all_none", "a2_ties_only")


def test_o4_detects_tampering() -> None:
    s = eligible_seed()
    data = measured(s)
    k = AN.first_decided(data["run"]["bodies"]["B_A1"]["layer_a"])["window"]
    for tamper in (lambda r: r["bodies"]["B_A2"]["layer_a"][k - 1].update(decision_pulse=0),
                   lambda r: r["bodies"]["B_A2"]["first_intent"]["sigma"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["bodies"]["B_A2"]["first_intent"].update(pulse=r["bodies"]["B_A2"]["first_intent"]["pulse"] + 1),
                   lambda r: r["bodies"]["B_A2"].update(first_intent=None),
                   lambda r: r["bodies"]["F_A2"]["sigma_0"]["world"]["rule"].update(delay=3),
                   lambda r: r["bodies"]["B_A2"]["first_intent"]["sigma"]["world"]["intents"].append([1, "x", "s1", "A1"])):
        changed = measured(s)
        tamper(changed["run"])
        assert "O4" in failures(changed, s)


# ---- CT-39-3 境界の順序と差の目録（README §2.4） ---------------------------------------------------------

def test_ct39_3_the_boundary_log_lists_s0_to_s5_in_order() -> None:
    run = measured(SYN[0])["run"]
    steps = run["boundary"]["steps"]
    assert steps == AN.expected_steps(run)
    assert [x[0] for x in steps] == ["S0"] * 2 + ["S1"] * 2 + ["S2"] * 6 + ["S3"] * 4 + ["S4"] * 6 + ["S5"] * 8
    assert all(x[2] == SMALL.p_e for x in steps if x[0] != "S5") and all(x[2] == SMALL.end for x in steps if x[0] == "S5")
    assert all(x[4]["intervention_state_at_transplant"] == AN.EMPTY_INTERVENTIONS for x in steps if x[0] == "S3")


def test_ct39_3_at_s0_nothing_is_open_or_reserved() -> None:
    for seed in SYN[:4]:
        for n in M.BODIES:
            s = measured(seed)["run"]["boundary"]["sigma_p_e"][n]
            assert s["pulse"] == SMALL.p_e and s["exit"]["pending"] is None and s["exit"]["reports"] == {}
            assert s["exit"]["cursor"] == SMALL.e_windows and all(r[1] == A.CUE for r in s["world"]["pending"])


def test_ct39_3_transplant_under_freeze_fails_and_without_it_succeeds() -> None:
    base = M.build_body(SMALL, SYN[0], "A1", log=_log())
    A.advance_to(base.app, SMALL.p_e)
    six = frozenset(M._weights(base))
    frozen = A.clone(base)
    frozen.declare(M._freeze_six(six), label="x")
    with pytest.raises(ValueError, match="FREEZE 中の接続"):
        frozen.transplant({min(six): 0.001})
    free = A.clone(base)
    free.transplant({min(six): 0.001})
    assert M._weights(free)[min(six)] == 0.001
    assert "frozen_targets" in inspect.getsource(AS1.transplant)


def test_ct39_3_the_difference_inventory_at_a_and_b() -> None:
    s = eligible_seed()
    run = measured(s)["run"]
    b, w = run["boundary"], run["boundary"]["W"]
    assert w["A1"] != w["A2"]
    for c, d in (("A1", "A2"), ("A2", "A1")):
        own, other, tr = f"G_{c}_W{c}", f"G_{c}_W{d}", f"G_{c}_W{c}_tr"
        assert AS1.sigma_diff(b["sigma_p_e"][f"B_{c}"], b["sigma_a"][own]) == []
        assert AS1.sigma_diff(b["sigma_a"][own], b["sigma_a"][tr]) == []
        diff = {tuple(p) for p in AS1.sigma_diff(b["sigma_a"][own], b["sigma_a"][other])}
        assert diff == {("connections", cid, "weight") for cid in w[c] if w[c][cid] != w[d][cid]} and diff
        assert AN._weights_of(b["sigma_a"][other]) == w[d]
        for n in (own, other, tr):
            assert {p[0] for p in AS1.sigma_diff(b["sigma_a"][n], b["sigma_b"][n])} == {"interventions"}
            assert b["sigma_b"][n]["world"] == b["sigma_b"][own]["world"]


def test_o7_detects_tampering() -> None:
    s = eligible_seed()
    for tamper in (lambda r: r["boundary"]["steps"].__setitem__(4, r["boundary"]["steps"][5]),
                   lambda r: r["boundary"]["steps"][10][4].update(intervention_state_at_transplant={"active": [1], "frozen": {}}),
                   lambda r: r["boundary"]["sigma_a"]["G_A1_WA2"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["boundary"]["sigma_a"]["G_A1_WA1_tr"]["connections"][min(r["W_0"])].update(weight=0.0),
                   lambda r: r["boundary"]["sigma_b"]["G_A2_WA1"]["interventions"]["frozen"][min(r["W_0"])].update(weight=0.0),
                   lambda r: r["boundary"]["sigma_b"]["G_A1_WA2"].update(pulse=SMALL.p_e + 1),
                   lambda r: r["boundary"]["sigma_p_e"]["B_A1"]["world"]["pending"].append(
                       [99, "consequence", r["roles"]["cue_receptor"], SMALL.p_e + 1, "x"]),
                   lambda r: r["boundary"]["sigma_p_e"]["B_A2"]["exit"].update(pending={"unit": "s1"}),
                   lambda r: r["boundary"]["sigma_p_e"]["B_A2"]["exit"].update(cursor=SMALL.e_windows - 1),
                   lambda r: r["G"]["G_A1_WA1"]["history"].append(r["G"]["G_A1_WA1"]["history"][0]),
                   lambda r: r["bodies"]["B_A1"]["history"].append([0, "x", []]),
                   lambda r: r["boundary"]["sigma_b"]["G_A1_WA2"]["world"]["rule"].update(rule_c="A2")):
        changed = measured(s)
        tamper(changed["run"])
        assert "O7" in failures(changed, s)


# ---- CT-39-4 恒等（SE-4・SE-8） -------------------------------------------------------------------------

def test_ct39_4_the_own_weight_transplant_reproduces_the_untransplanted_clone() -> None:
    run = measured(eligible_seed())["run"]
    for a, b in M.IDENTITIES:
        for key in ("activity", "sensory", "layer_a", "layer_b", "delta_log", "sigma_end_sha256", "pulse_weights"):
            assert run["G"][a][key] == run["G"][b][key], (a, b, key)


def test_ct39_4_a_structural_identity_is_identical_to_the_untransplanted_clone() -> None:
    s = identity_seed()
    run = measured(s, E1)["run"]
    assert run["boundary"]["W"]["A1"] == run["boundary"]["W"]["A2"]
    for a, b in M.PAIRS:
        for key in ("activity", "layer_a", "layer_b", "sigma_end_sha256"):
            assert run["G"][a][key] == run["G"][b][key], (a, b, key)
    assert AN.individual(run)["structural_identity"] is True


def test_o9_detects_a_broken_identity() -> None:
    s = eligible_seed()
    data = measured(s)
    data["run"]["G"]["G_A1_WA1_tr"]["sigma_end_sha256"] = "0" * 64
    assert "O9" in failures(data, s)
    s2 = identity_seed()
    data = measured(s2, E1)
    data["run"]["G"]["G_A2_WA1"]["activity"].append([E1.end, data["run"]["roles"]["cue"]])
    assert "O9" in failures(data, s2, E1)


# ---- CT-39-5 Pulse P_E ＋ 1 の一致（SE-6） ---------------------------------------------------------------

def _se6_setup(seed: int, b: int):
    base = M.build_body(SMALL, seed, "A1", log=_log())
    A.advance_to(base.app, b)
    six = frozenset(M._weights(base))
    look = A.clone(base)
    look.declare(M._freeze_six(six), label="look")
    A.advance_to(look.app, b + 2)
    fired = {p: {u for q, u in look.log.activity() if q == p} for p in (b + 1, b + 2)}
    return base, six, fired


def _se6_pair(base, six, cid: str, weight: float):
    orig, test = A.clone(base), A.clone(base)
    test.transplant({cid: weight})                                     # 契約テストだけの値（重みの差を大きくする）
    for s in (orig, test):
        s.declare(M._freeze_six(six), label="S4")
    return orig, test


@functools.cache
def _find_se6_boundary(want_sender_fires: bool) -> tuple[int, int, str]:
    for seed in SYN_ALL:
        for b in range(40, 200):
            _base, six, fired = _se6_setup(seed, b)
            for cid in sorted(six):
                u, v = AN._ends(cid)
                if want_sender_fires and u in fired[b + 1] and v not in fired[b + 2]:
                    return seed, b, cid
                if not want_sender_fires and u not in fired[b + 1]:
                    return seed, b, cid
    raise AssertionError("構成が見つからない")


def test_ct39_5_a_weight_difference_can_first_change_firing_at_the_second_pulse() -> None:
    seed, b, cid = _find_se6_boundary(True)
    base, six, _ = _se6_setup(seed, b)
    orig, test = _se6_pair(base, six, cid, 10.0)
    for s in (orig, test):
        A.advance_to(s.app, b + 1)
    so, st = M._sigma(orig), M._sigma(test)
    assert so["units"] == st["units"] and so["exit"] == st["exit"] and orig.log.activity() == test.log.activity()
    differs = [(x, y) for x, y in zip(so["drives"], st["drives"]) if x != y]
    u, v = AN._ends(cid)
    assert differs and all(x[0] == u and x[1] == v and x[3] == b + 1 for x, _ in differs)  # その接続の分だけ違う
    for s in (orig, test):
        A.advance_to(s.app, b + 2)
    assert AN.first_divergence([list(x) for x in orig.log.activity()], [list(x) for x in test.log.activity()],
                               b + 1, b + 2) == b + 2


def test_ct39_5_no_difference_reaches_the_second_pulse_when_the_sender_does_not_fire() -> None:
    seed, b, cid = _find_se6_boundary(False)
    base, six, _ = _se6_setup(seed, b)
    orig, test = _se6_pair(base, six, cid, 10.0)
    for s in (orig, test):
        A.advance_to(s.app, b + 1)
    so, st = M._sigma(orig), M._sigma(test)
    assert so["units"] == st["units"] and so["drives"] == st["drives"]                    # 駆動に差はない
    for s in (orig, test):
        A.advance_to(s.app, b + 2)
    assert orig.log.activity() == test.log.activity()


def test_o10_holds_on_the_records_and_detects_tampering() -> None:
    s = eligible_seed()
    run = measured(s)["run"]
    for a, b in M.PAIRS:
        fd = AN.first_divergence(run["G"][a]["activity"], run["G"][b]["activity"], SMALL.p_e + 1, SMALL.end)
        assert fd is None or fd >= SMALL.p_e + 2
    cue = run["roles"]["cue"]
    for tamper in (lambda r: r["G"]["G_A1_WA2"]["sigma_after_first"]["units"][cue].update(activity=9.0),
                   lambda r: r["G"]["G_A1_WA2"]["sigma_after_first"].update(pulse=SMALL.p_e + 2),
                   lambda r: r["G"]["G_A2_WA1"]["activity"].insert(0, [SMALL.p_e + 1, "zz"]),
                   lambda r: r["G"]["G_A1_WA2"]["sigma_after_first"]["drives"].append(["s1", "s2", 0.5, SMALL.p_e + 1]),
                   lambda r: r["G"]["G_A1_WA2"]["sigma_after_first"]["exit"].update(cursor=7)):
        changed = measured(s)
        tamper(changed["run"])
        assert "O10" in failures(changed, s)


def test_o10_accepts_only_the_drive_difference_of_a_weight_differing_connection_whose_sender_fired() -> None:
    s = eligible_seed()
    data = measured(s)
    run = data["run"]
    a, b = M.PAIRS[0]
    first = SMALL.p_e + 1
    wa, wb = (AN._weights_of(run["boundary"]["sigma_b"][n]) for n in (a, b))
    cid = next(c for c in sorted(wa) if wa[c] != wb[c])
    u, v = AN._ends(cid)
    for n, w in ((a, wa), (b, wb)):                                    # 送り手が Pulse P_E ＋ 1 に発火した、と記録を書き換える
        run["G"][n]["activity"].insert(0, [first, u])
        run["G"][n]["sigma_after_first"]["drives"] = [[u, v, w[cid], first]]
    assert "O10" not in failures(data, s)
    run["G"][b]["sigma_after_first"]["drives"] = [[u, v, wa[cid] + 1.0, first]]            # 重みと合わない駆動
    assert "O10" in failures(data, s)


# ---- CT-39-6 FREEZE（SE-3・SE-5） ------------------------------------------------------------------------

def test_ct39_6_the_frozen_weights_stay_at_the_declared_values() -> None:
    s = eligible_seed()
    run = measured(s)["run"]
    w0 = [run["W_0"][c] for c in run["connection_order"]]
    for n in M.FROZEN_BODIES:
        rows = run["bodies"][n]["pulse_weights"]
        assert [p for p, _ in rows] == list(range(1, SMALL.end + 1)) and all(w == w0 for _, w in rows)
    for n in M.G_SYSTEMS:
        want = [run["boundary"]["W"][M.FROZEN_VALUE[n]][c] for c in run["connection_order"]]
        rows = run["G"][n]["pulse_weights"]
        assert [p for p, _ in rows] == list(range(SMALL.p_e + 1, SMALL.end + 1)) and all(w == want for _, w in rows)
    moved = [w for _, w in run["bodies"]["B_A1"]["window_weights"]]
    assert moved[-1] != w0                                           # 本体は可塑性あり（重みが動く）


def test_o6_and_o8_detect_a_moving_weight() -> None:
    s = eligible_seed()
    data = measured(s)
    data["run"]["bodies"]["F_A2"]["pulse_weights"][5][1][0] = 0.0
    assert "O6" in failures(data, s)
    data = measured(s)
    data["run"]["G"]["G_A2_WA1"]["pulse_weights"][7][1][2] = 0.0
    assert "O8" in failures(data, s)
    data = measured(s)
    data["run"]["G"]["G_A1_WA1"]["pulse_weights"].pop()
    assert "O8" in failures(data, s)


def test_ct39_6_traces_do_not_matter_when_all_six_are_frozen() -> None:
    """SE-5：全 6 本を止めている系では、痕跡の扱い（advance・hold）を替えても、発火・層 A・Unit の状態が同じ。"""
    seed = CORNER_SEEDS[2]
    ends = []
    for policy in (AS1.ADVANCE, AS1.HOLD):
        s = M.build_body(SMALL, seed, "A1", log=_log())
        A.advance_to(s.app, 100)                                     # 痕跡が 0 でない状態から止める
        s.declare([AS1.Intervention(AS1.FREEZE, frozenset(M._weights(s)), policy)], label=policy)
        A.advance_to(s.app, SMALL.end)
        sig = M._sigma(s)
        ends.append((s.log.activity(), sig["units"], sig["exit"], M._weights(s)))
    assert ends[0] == ends[1]


# ---- CT-39-7 F1（SE-7） ---------------------------------------------------------------------------------

def test_ct39_7_pair_sums_of_the_bodies_and_the_transplanted_systems() -> None:
    s = eligible_seed()
    run = measured(s)["run"]
    for c in ("A1", "A2"):
        sums = AN.pair_sums(run["boundary"]["W"][c])
        assert len(sums) == 3 and all(abs(x - W_MAX) <= AN.F1_TOLERANCE for x in sums.values())
    for n in M.G_SYSTEMS:
        assert AN.pair_sums(AN._weights_of(run["boundary"]["sigma_a"][n])) == AN.pair_sums(run["boundary"]["W"][M.FROZEN_VALUE[n]])
    data = measured(s)
    cid = min(data["run"]["W_0"])
    data["run"]["boundary"]["W"]["A1"][cid] += 1e-6
    assert "O14" in failures(data, s)


# ---- CT-39-8 命題 S-1・補題 L1・L2（README §7.2） ----------------------------------------------------------

THETA = (0.45, 0.55)                                                 # 出生時の θ の範囲（0.5 ± 10%）
DRIVE = (0.072, 0.088)                                               # 出生時の c の範囲（0.08 ± 10%）
LAMBDA = 0.85


def _inner(system, unit_id):
    u = system.app.units.get(unit_id)
    return u._inner if isinstance(u, A.CompetitionTap) else u


def _corner_system(seed: int, rule_c: str, values: dict, *, freeze_at_w_max: bool):
    """Unit の θ・c・初期の activity を決めた値に置いた合成の系（契約テストだけ。Core も道具も変えない）。

    values：役（cue・source1・source2）→ (θ, c)。初期の activity は上限 θ/2。freeze_at_w_max なら 6 本を w_max にして止める。
    """
    s = M.build_body(FORMAL, seed, rule_c, log=_log())
    roles = s.roles.as_dict()
    for role, (theta, c) in values.items():
        inner = _inner(s, roles[role])
        inner._dynamics = dataclasses.replace(inner._dynamics, threshold=theta, intrinsic_drive_per_second=c)
        inner.import_state(inner.export_state() | {"activity": theta / 2})
    if freeze_at_w_max:
        six = frozenset(M._weights(s))
        s.transplant(dict.fromkeys(six, W_MAX))
        s.declare(M._freeze_six(six), label="corner")
    return s


def _run_recording_adaptation(system, unit_id) -> float:
    top = 0.0
    for pulse in range(1, FORMAL.end + 1):
        A.advance_to(system.app, pulse)
        top = max(top, _inner(system, unit_id).export_state()["adaptation"])
    return top


def _gaps(pulses: list[int]) -> list[int]:
    return [b - a for a, b in itertools.pairwise(pulses)]


def test_ct39_8_the_bound_e_s_matches_the_preregistered_analysis() -> None:
    lam, w = LAMBDA, W_MAX
    e_s = w * ((1 + lam ** 4) / (1 - lam ** 23) + 2 / (1 - lam ** 7))
    assert AN.E_S == pytest.approx(e_s, abs=1e-15) and AN.E_S == pytest.approx(PROTOCOL["proposition_S1"]["E_S_value"], abs=5e-6)
    assert AN.margin({"dynamics": {"intrinsic_drive_per_second": 0.08, "decay_per_second": 0.85, "threshold": 0.5}}) \
        == pytest.approx(0.08 / 0.15 - 0.5)


@pytest.mark.parametrize("rule_c", ["A1", "A2"])
@pytest.mark.parametrize("freeze", [True, False])
def test_ct39_8_a_source_below_the_bound_never_fires_even_at_the_corners(rule_c, freeze) -> None:
    """命題 S-1：g ＜ −E_S の源（θ を上限、c を g がちょうど境の下になる値）は、ほかの二つの Unit を最も発火しやすい値に置き、
    6 本を w_max で止めても（または可塑性のままでも）、本番の長さのあいだ一度も発火しない。"""
    theta = THETA[1]
    c = (theta - AN.E_S - 1e-9) * (1 - LAMBDA)
    assert DRIVE[0] <= c <= DRIVE[1]
    easy = (THETA[0], DRIVE[1])
    s = _corner_system(CORNER_SEEDS[0], rule_c, {"source1": (theta, c), "cue": easy, "source2": easy}, freeze_at_w_max=freeze)
    assert AN.margin(_inner(s, s.roles.source1).export_state()) < -AN.E_S
    A.advance_to(s.app, FORMAL.end)
    fired = {u for _, u in s.log.activity()}
    assert s.roles.source1 not in fired and _inner(s, s.roles.source1).export_state()["fire_count"] == 0
    assert {s.roles.cue, s.roles.source2} <= fired                   # ほかの二つは発火している（確かめが空でない）
    assert all(r["outcome"] in ("A2", A.NONE) for r in s.decider.records)      # その源の行動 A1 は一度も勝たない（SE-9）


@pytest.mark.parametrize("rule_c", ["A1", "A2"])
def test_ct39_8_lemma_l1_and_l2_hold_at_the_corners(rule_c) -> None:
    """補題 L1：手がかりの Unit は、Receptor の入力の入る Pulse（感覚の出来事の翌 Pulse）に必ず発火し、順応は 0.441 未満。そのほかの
    発火は、直前の発火から 7 Pulse 以上後。補題 L2：源の連続する発火は 7 Pulse 以上離れる。"""
    easy = (THETA[0], DRIVE[1])
    for cue_values in (easy, (THETA[1], DRIVE[0])):                  # 手がかりの Unit：最も発火しやすい角と、最も発火しにくい角
        s = _corner_system(CORNER_SEEDS[1], rule_c, {"cue": cue_values, "source1": easy, "source2": easy}, freeze_at_w_max=True)
        top = _run_recording_adaptation(s, s.roles.cue)
        act = s.log.activity()
        cue_fires = [p for p, u in act if u == s.roles.cue]
        r_pulses = {p + 1 for p, _ in s.log.sensory()}
        assert r_pulses and r_pulses <= set(cue_fires)               # L1：R の Pulse では必ず発火する
        assert top < 0.441
        for prev, cur in itertools.pairwise(cue_fires):
            assert cur in r_pulses or cur - prev >= 7                # L1：R でない発火は、直前の発火から 7 以上後
        for src in (s.roles.source1, s.roles.source2):
            fires = [p for p, u in act if u == src]
            assert len(fires) > 10 and min(_gaps(fires)) >= 7        # L2
        cons = sorted(r[3] for r in s.world.export_state()["reserved"] if r[1] == A.CONSEQUENCE)
        cues = list(FORMAL.schedule().cues)
        for x in cons:                                               # 手がかり → 結果は 4 以上、結果 → 次の手がかりは 19 以上
            k = max(i for i, c in enumerate(cues) if c <= x)
            assert x - cues[k] >= 4 and (k + 1 == len(cues) or cues[k + 1] - x >= 19)


def test_ct39_8_the_s1_label_and_a_violation_are_reported_without_changing_the_judgment() -> None:
    s = eligible_seed()
    run = measured(s)["run"]
    src = run["roles"]["source1"]
    d = run["birth_units"][src]["dynamics"]
    d["threshold"], d["intrinsic_drive_per_second"] = 0.55, 0.072    # 記録の上だけ、構造的に沈黙する源の値にする
    ind = AN.individual(run)
    assert ind["S1"]["silent_source"] == {"source1": True, "source2": False}
    fired = any(u == src for n in M.SYSTEMS for _, u in AN.record_of(run, n)["activity"])
    assert ind["S1"]["violations"] == (["source1"] if fired else [])
    aux = AN.auxiliary({"1": ind})
    assert aux["R1"]["S1"]["labels_withdrawn"] is fired
    assert aux["R1"]["S1"]["individuals_with_silent_source"] == (None if fired else 1)
    assert "S1" not in json.dumps(AN.judge({"1": ind}))               # 判定は S-1 に依らない


# ---- CT-39-9 量と判定の算術（README §3〜§5） ---------------------------------------------------------------

def _layer(outcomes: list[str]) -> list[dict]:
    return [{"window": k + 1, "outcome": o} for k, o in enumerate(outcomes)]


def test_window_counts_and_shares() -> None:
    la = _layer(["A1", "tie", "none", "A2", "A1", "A1", "none", "A2"])
    assert AN.window_counts(la, 1, 4) == {"windows": 4, "decided": 2, "A1": 1, "A2": 1, "tie": 1, "none": 1}
    u = AN.window_counts(la, 5, 8)
    assert u == {"windows": 4, "decided": 3, "A1": 2, "A2": 1, "tie": 0, "none": 1}
    assert AN.share(u) == Fraction(2, 3) and AN.share_of(u, "A2") == Fraction(1, 3)
    empty = AN.window_counts(_layer(["tie", "none"]), 1, 2)
    assert AN.share(empty) is None and AN.share_of(empty, "A2") is None
    assert [AN.sign(x) for x in (Fraction(1, 7), Fraction(-1, 7), Fraction(0))] == ["+", "-", "0"]


def test_prefix_label_kinds() -> None:
    assert AN.prefix_label(_layer(["none", "tie", "A2", "A1"]), 3) == {"k_star": 3, "ineligible_a": False, "ineligible_kind": None}
    assert AN.prefix_label(_layer(["none", "none", "A2"]), 2) == {"k_star": 3, "ineligible_a": True, "ineligible_kind": "a1_all_none"}
    assert AN.prefix_label(_layer(["none", "tie", "none"]), 2) == {"k_star": None, "ineligible_a": True,
                                                                   "ineligible_kind": "a2_ties_only"}


def _with_outcomes(run: dict, outcomes: dict[str, list[str]]) -> dict:
    """実物の合成の個体の記録の、層 A の結末だけを差し替える（判定の算術の確かめにだけ使う。操作の確認には通さない）。"""
    for name, outs in outcomes.items():
        la = AN.record_of(run, name)["layer_a"]
        assert len(outs) == len(la)
        for r, o in zip(la, outs):
            r["outcome"] = o
    return run


E_PART = ["A1", "none", "none", "none"]


def test_the_individual_quantities_follow_the_definitions() -> None:
    run = measured(eligible_seed())["run"]
    u = {"B_A1": ["A1", "A1", "A1", "A2"], "B_A2": ["A1", "A2", "tie", "none"],                # s ＝ 3/4 と 1/2 → D ＞ 0
         "G_A1_WA1": ["A1", "A2", "none", "none"], "G_A1_WA2": ["A1", "A1", "A2", "A2"],        # 1/2 と 1/2 → D_W ＝ 0
         "G_A2_WA1": ["A2", "none", "none", "none"], "G_A2_WA2": ["A1", "A2", "A2", "A2"],      # 0 と 1/4 → D_W_rev ＜ 0
         "F_A1": ["none", "tie", "none", "none"], "F_A2": ["A1", "A1", "none", "none"]}         # F_A1 は定まらない
    ind = AN.individual(_with_outcomes(run, {n: E_PART + o for n, o in u.items()}))
    c = ind["contrasts"]
    assert ind["prefix"]["B"] == {"k_star": 1, "ineligible_a": False, "ineligible_kind": None}
    assert (c["D"]["sign"], c["D"]["difference"]["num"], c["D"]["difference"]["den"]) == ("+", 1, 4) and c["D"]["in_population"]
    assert c["D_W"]["sign"] == "0" and c["D_W"]["in_population"] and c["D_W_rev"]["sign"] == "-"
    assert c["D_F"]["defined"] is False and c["D_F"]["undefined_kind"] == "one_system" and c["D_F"]["sign"] is None
    assert c["D_F"]["in_population"] is False
    # Z・P は、規則 c が指す行動の割合 s_c の差：Z_A2 は A2 の割合（B_A2：1/2、G_A2_WA2：3/4）
    assert c["Z_A2"]["share_of"] == "A2" and (c["Z_A2"]["a"]["num"], c["Z_A2"]["a"]["den"]) == (1, 2)
    assert (c["Z_A2"]["b"]["num"], c["Z_A2"]["b"]["den"]) == (3, 4) and c["Z_A2"]["sign"] == "-"
    assert c["Z_A1"]["share_of"] == "A1" and c["Z_A1"]["sign"] == "+"
    assert c["D"]["n_U_diff"] == 2 and c["D"]["A1_U_diff"] == 2
    assert ind["counts_U"]["B_A2"] == {"windows": 4, "decided": 2, "A1": 1, "A2": 1, "tie": 1, "none": 1}


def test_swapping_the_labels_keeps_d_and_exchanges_the_two_transplant_contrasts() -> None:
    """README §3.2：A1・A2 の札を入れ替えると、D・D^F は同じ値、D^W と D^{W′} は互いに入れ替わる。"""
    run = measured(eligible_seed())["run"]
    u = {"B_A1": ["A1", "A1", "A1", "A2"], "B_A2": ["A1", "A2", "tie", "none"],
         "G_A1_WA1": ["A1", "A2", "A2", "none"], "G_A1_WA2": ["A1", "A1", "A2", "A2"],
         "G_A2_WA1": ["A2", "A1", "none", "none"], "G_A2_WA2": ["A1", "A2", "A2", "A2"],
         "F_A1": ["A1", "A1", "none", "none"], "F_A2": ["A2", "A1", "A2", "none"]}
    swap = {"A1": "A2", "A2": "A1", "tie": "tie", "none": "none"}
    partner = {"B_A1": "B_A2", "B_A2": "B_A1", "F_A1": "F_A2", "F_A2": "F_A1", "G_A1_WA1": "G_A2_WA2", "G_A2_WA2": "G_A1_WA1",
               "G_A1_WA2": "G_A2_WA1", "G_A2_WA1": "G_A1_WA2"}
    before = AN.individual(_with_outcomes(copy.deepcopy(run), {n: E_PART + o for n, o in u.items()}))["contrasts"]
    after = AN.individual(_with_outcomes(copy.deepcopy(run), {partner[n]: [swap[x] for x in E_PART + o] for n, o in u.items()}))["contrasts"]
    for name in ("D", "D_F"):
        assert before[name]["difference"] == after[name]["difference"], name
    assert before["D_W"]["difference"] == after["D_W_rev"]["difference"]
    assert before["D_W_rev"]["difference"] == after["D_W"]["difference"]


def test_an_individual_without_a_decided_window_in_e_is_ineligible_for_every_contrast_of_the_bodies() -> None:
    s = ineligible_seed()
    ind = AN.individual(measured(s)["run"])
    assert ind["prefix"]["B"]["ineligible_a"] is True
    assert all(ind["contrasts"][n]["in_population"] is False for n in ("D", "D_W", "D_W_rev", "Z_A1", "Z_A2", "P_A1", "P_A2"))
    assert ind["structural_identity"] is True


def _fake(**signs) -> dict:
    """判定の算術の確かめ用の個体：対比 → 符号（None なら分母の外）。"""
    out = {}
    for name in AN.CONTRASTS:
        s = signs.get(name)
        out[name] = {"in_population": s is not None, "sign": s, "ineligible_a": False, "defined": s is not None,
                     "undefined_kind": None if s is not None else "one_system"}
    return {"contrasts": out}


def _group(**counts) -> dict:
    """counts：対比 → (＋の数, −の数, 0 の数)。個体は対比ごとに独立に並べる。"""
    n = max(sum(v) for v in counts.values())
    rows = []
    for i in range(n):
        signs = {}
        for name, (p, m, z) in counts.items():
            signs[name] = "+" if i < p else ("-" if i < p + m else ("0" if i < p + m + z else None))
        rows.append(_fake(**signs))
    return {str(i): r for i, r in enumerate(rows)}


def test_k2_of_m_matches_the_protocol_table_and_the_binomial_tail() -> None:
    table = PROTOCOL["judgment"]["k2_of_m"]
    assert sorted(table) == list(range(10, 201))
    for m, k in table.items():
        assert AN.k2_of_m(m) == k
        assert AN.binom_upper_tail(m, k) <= Fraction(1, 40) < AN.binom_upper_tail(m, k - 1)
    assert (table[10], table[50], table[100], table[200]) == (9, 33, 61, 115)


def test_j7_at_the_boundaries_in_both_directions_and_zeros_stay_in_the_denominator() -> None:
    assert AN.judge(_group(D=(9, 0, 0)))["J_7"]["status"] == "inconclusive"               # m ＝ 9
    assert AN.judge(_group(D=(9, 0, 0)))["outcome"] == "inconclusive"
    for plus in (True, False):
        def d(k, rest, plus=plus):
            return (k, rest, 0) if plus else (rest, k, 0)
        j = AN.judge(_group(D=d(9, 1)))["J_7"]                                             # m ＝ 10、k₂ ＝ 9
        assert (j["m"], j["k2"], j["status"], j["direction"]) == (10, 9, "established", "+" if plus else "-")
        j = AN.judge(_group(D=d(8, 2)))["J_7"]
        assert (j["status"], j["direction"]) == ("not_established", None)
    zeros = AN.judge(_group(D=(9, 0, 3)))["J_7"]                                           # 0 を分母に残す：m ＝ 12、k₂ ＝ 10
    assert (zeros["m"], zeros["k2"], zeros["status"], zeros["counts"]) == (12, 10, "not_established", {"+": 9, "-": 0, "0": 3})
    assert zeros["interval"]["+"]["computed"] and zeros["interval"]["-"]["denominator"] == 12


def test_the_fixed_sequence_j_w_is_tested_only_if_j7_is_established() -> None:
    not_tested = AN.judge(_group(D=(8, 2, 0), D_W=(10, 0, 0)))
    assert not_tested["outcome"] == "J_7_not_established" and not_tested["J_W"]["status"] == "not_tested"
    assert not_tested["J_W"]["counts"] == {"+": 10, "-": 0, "0": 0} and not_tested["J_W"]["interval"]["+"]["computed"]
    same = AN.judge(_group(D=(9, 1, 0), D_W=(10, 0, 0)))
    assert same["outcome"] == "both_same_direction" and same["J_W"]["status"] == "established"
    opposite = AN.judge(_group(D=(9, 1, 0), D_W=(0, 10, 0)))
    assert opposite["outcome"] == "both_opposite_direction" and opposite["J_W"]["direction"] == "-"
    only = AN.judge(_group(D=(9, 1, 0), D_W=(5, 5, 0)))
    assert only["outcome"] == "J_7_only" and only["J_W"]["status"] == "not_established"
    few = AN.judge(_group(D=(9, 1, 0), D_W=(9, 0, 0)))
    assert few["outcome"] == "J_7_only" and few["J_W"]["status"] == "inconclusive"
    assert set(PROTOCOL["judgment"]["outcomes"]) - {"invalid"} == {
        "inconclusive", "J_7_not_established", "J_7_only", "both_same_direction", "both_opposite_direction"}


def test_the_same_direction_does_not_show_a_same_individual_mediation() -> None:
    """レビュー 5837398414 の反例：J_7 の分母の 50 個体で 35 個体が＋、J_W の分母の別の 50 個体で 35 個体が＋。どちらも k₂(50) ＝ 33 を
    越えて成立するが、両方の分母に入る個体は 0。report は、二つの条件付きの結果の並立として出し、同じ個体の表は記述だけ。"""
    rows = [_fake(D="+") for _ in range(35)] + [_fake(D="-") for _ in range(15)] \
        + [_fake(D_W="+") for _ in range(35)] + [_fake(D_W="-") for _ in range(15)]
    individuals = {str(i): r for i, r in enumerate(rows)}
    j = AN.judge(individuals)
    assert j["outcome"] == "both_same_direction" and j["J_7"]["k2"] == j["J_W"]["k2"] == 33
    assert "no same-individual mediation" in j["combined_claim"]
    table = AN.cross_table(list(individuals.values()), "D", "D_W")
    assert table["in_both"] == 0 and table["only_D"] == 50 and table["only_D_W"] == 50 and sum(table["cells"].values()) == 0


def test_cross_table_counts_the_nine_cells() -> None:
    rows = [_fake(D="+", D_W="+"), _fake(D="+", D_W="-"), _fake(D="0", D_W="0"), _fake(D="-"), _fake(D_W="+")]
    t = AN.cross_table(rows, "D", "D_W")
    assert t["in_both"] == 3 and t["cells"]["++"] == 1 and t["cells"]["+-"] == 1 and t["cells"]["00"] == 1
    assert t["only_D"] == 1 and t["only_D_W"] == 1 and len(t["cells"]) == 9


def test_clopper_pearson_known_values() -> None:
    lo, hi = AN.clopper_pearson(0, 10)
    assert lo == 0.0 and hi == pytest.approx(1 - 0.025 ** 0.1, abs=1e-9)
    lo, hi = AN.clopper_pearson(10, 10)
    assert hi == 1.0 and lo == pytest.approx(0.025 ** 0.1, abs=1e-9)
    lo, hi = AN.clopper_pearson(5, 10)
    assert lo == pytest.approx(0.187086, abs=1e-5) and hi == pytest.approx(0.812914, abs=1e-5)
    assert AN.interval(0, 0) == {"computed": False, "interval": None, "numerator": 0, "denominator": 0, "reason": "m = 0"}


def test_descriptive_controls_report_the_required_contrasts_and_the_separate_tables() -> None:
    rows = {"1": _fake(D="+", D_W="+", D_W_rev="-", D_F="0", Z_A1="+"), "2": _fake(D="-", D_W_rev="+")}
    rows["3"] = _fake()
    for name in AN.CONTRASTS:
        rows["3"]["contrasts"][name] |= {"ineligible_a": True, "defined": True, "sign": "+", "undefined_kind": None}
    dc = AN.descriptive_controls(rows)
    assert set(dc["contrasts"]) == set(AN.MUST_REPORT + AN.DESCRIPTIVE)
    assert dc["contrasts"]["D_W_rev"]["required"] and dc["contrasts"]["D_F"]["required"] and not dc["contrasts"]["Z_A1"]["required"]
    assert dc["contrasts"]["D_W_rev"]["m"] == 2 and dc["contrasts"]["D_W_rev"]["counts"] == {"+": 1, "-": 1, "0": 0}
    assert set(dc["cross_tables"]) == {"D_W|D_W_rev", "D|D_W"}
    assert dc["ineligible_a"]["D"] == {"individuals": ["3"], "defined": 1, "counts": {"+": 1, "-": 0, "0": 0},
                                       "interval": dc["ineligible_a"]["D"]["interval"]}
    assert dc["undefined_b"]["D_W"]["one_system"] == ["2"] and dc["undefined_b"]["D"]["one_system"] == []


def test_five_numbers() -> None:
    assert AN.five_numbers([]) is None and AN.five_numbers([3])["median"] == 3
    assert AN.five_numbers([1, 2, 3, 4, 5]) == {"count": 5, "min": 1, "q1": 2.0, "median": 3.0, "q3": 4.0, "max": 5}


def test_the_analysis_of_the_synthetic_individuals_runs_through_and_the_recheck_agrees() -> None:
    """合成の個体の解析が最後まで通る。標準のライブラリだけの独立の検算（recheck.py）が、report と一つずつ一致する。値は表示しない。"""
    runs = {s: measured(s) for s in SYN}
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=[])
    assert report["valid"] is True and set(report) == {"mode", "valid", "O1", "gate_declaration_sha256", "judgment",
                                                       "descriptive_controls", "individuals", "auxiliary"}
    j = report["judgment"]
    assert j["J_7"]["status"] in ("inconclusive", "established", "not_established") and j["outcome"] in PROTOCOL["judgment"]["outcomes"]
    assert j["J_7"]["interval"]["+"]["computed"] is (j["J_7"]["m"] >= 1)
    assert set(report["auxiliary"]) == {"R1", "R2", "R3", "R4", "R5", "R6", "R7", "R9"}
    assert all(report["auxiliary"]["R5"][n]["equals_decided_windows_of_c"] for n in M.BODIES + M.FROZEN_BODIES)
    for s in SYN:
        runs[s]["meta"]["protocol"] = PROTOCOL
    result = RC.recheck(runs, json.loads(json.dumps(report)))
    assert result["mismatches"] == [] and result["checks"] > 500


def test_the_recheck_is_independent_and_detects_a_changed_report_or_raw() -> None:
    src = (EXP / "recheck.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    modules = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names} \
        | {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert modules <= {"argparse", "gzip", "hashlib", "json", "math", "sys", "collections", "fractions", "pathlib"}
    assert "spec_from_file_location" not in src and "__import__" not in src and "exec(" not in src
    runs = {s: measured(s) for s in SYN[:4]}
    for s in runs:
        runs[s]["meta"]["protocol"] = PROTOCOL
    report = json.loads(json.dumps(AN.analyze_runs({s: measured(s) for s in SYN[:4]}, "synthetic", SMALL, o1=[])))
    assert RC.recheck(runs, report)["mismatches"] == []
    for tamper in (lambda rep, raw: rep["judgment"]["J_7"]["counts"].update({"+": rep["judgment"]["J_7"]["counts"]["+"] + 1}),
                   lambda rep, raw: rep["judgment"].update(outcome="both_same_direction" if rep["judgment"]["outcome"] != "both_same_direction" else "J_7_only"),
                   lambda rep, raw: rep["individuals"][str(SYN[0])]["contrasts"]["D_F"].update(sign="?"),
                   lambda rep, raw: rep["individuals"][str(SYN[0])]["prefix"]["B"].update(k_star=99),
                   lambda rep, raw: raw[SYN[1]]["run"]["bodies"]["F_A1"]["pulse_weights"][3][1].__setitem__(0, 0.0),
                   lambda rep, raw: raw[SYN[1]]["run"]["G"]["G_A1_WA1_tr"]["layer_b"].append([9, "d", "s1", "A1"])):
        rep, raw = copy.deepcopy(report), copy.deepcopy(runs)
        tamper(rep, raw)
        assert RC.recheck(raw, rep)["mismatches"]


def test_an_invalid_individual_or_a_failed_o1_blocks_the_judgment() -> None:
    runs = {s: measured(s) for s in SYN[:2]}
    runs[SYN[1]]["run"]["bodies"]["F_A1"]["pulse_weights"][0][1][0] = 0.0
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=[])
    assert report["valid"] is False and report["judgment"] is None and "individuals" not in report
    assert list(report["failed_checks"]) == [str(SYN[1])] and "O6" in report["failed_checks"][str(SYN[1])]
    report = AN.analyze_runs({SYN[0]: measured(SYN[0])}, "synthetic", SMALL, o1=["x"])
    assert report["valid"] is False and report["judgment"] is None and report["O1"]["status"] == "fail"


# ---- 操作の確認が、記録の食い違いを見つける（O2・O3・O5・O11・O12・O13・structure） ---------------------------------

def test_structure_detects_extra_fields_and_wrong_roles() -> None:
    s = SYN[0]
    for tamper in (lambda d: d["run"].update(judgment={}), lambda d: d.update(extra=1),
                   lambda d: d["run"]["bodies"]["B_A1"].update(s_U=0.5), lambda d: d["run"]["G"].pop("G_A2_WA2_tr"),
                   lambda d: d["run"]["roles"].update(cue=d["run"]["roles"]["source1"]),
                   lambda d: d["run"]["W_0"].update({min(d["run"]["W_0"]): 0.004}),
                   lambda d: d["run"].update(seed=s + 1), lambda d: d["meta"].update(manifest={}),
                   lambda d: d["run"]["plan"].update(e_windows=3),
                   lambda d: d["run"]["G"]["G_A1_WA1"]["audit"].update(ok=True)):
        data = measured(s)
        tamper(data)
        assert "structure" in failures(data, s)


def test_o2_detects_a_different_gate_set() -> None:
    s = SYN[0]
    for tamper in (lambda d: d["meta"]["gate"].update(sha256="0" * 64),
                   lambda d: d["meta"]["gate"]["declaration"]["schedule"].update(window_length_W=18),
                   lambda d: d["meta"].pop("gate"),
                   lambda d: d["run"]["bodies"]["B_A2"]["world_end"]["rule"].update(delay=3),
                   lambda d: d["run"]["G"]["G_A2_WA1"]["world_end"]["rule"].update(rule_c="A1"),
                   lambda d: d["run"]["bodies"]["F_A1"]["world_end"]["rule"].update(respond=False),
                   lambda d: d["run"]["bodies"]["B_A1"]["layer_a"][2].update(close=d["run"]["bodies"]["B_A1"]["layer_a"][2]["close"] + 1),
                   lambda d: d["run"]["bodies"]["B_A1"]["world_end"]["reserved"][0].__setitem__(3, 40),
                   lambda d: d["run"]["G"]["G_A1_WA1"].update(pulse_end=SMALL.end - 1),
                   lambda d: d["run"]["boundary"]["sigma_p_e"]["B_A1"]["exit"]["windows"][0].__setitem__(2, 60)):
        data = measured(s)
        tamper(data)
        assert "O2" in failures(data, s)
    formal = measured(s)
    formal["meta"]["mode"] = "formal"
    assert AN.check_seed(formal, "formal", s, SMALL)["structure"]            # 本番では小さい Plan を使えない


def test_o3_detects_a_broken_audit() -> None:
    s = eligible_seed()
    for tamper in (lambda r: r["bodies"]["B_A1"]["layer_b"].append([9, "d-x", r["roles"]["source1"], "A1"]),
                   lambda r: r["bodies"]["B_A2"]["layer_b"].pop(),
                   lambda r: r["G"]["G_A1_WA2"]["layer_a"].pop(),
                   lambda r: r["bodies"]["F_A1"]["delta_log"].pop(),
                   lambda r: r["G"]["G_A2_WA2"]["delta_log"].insert(0, r["G"]["G_A2_WA2"]["layer_b"][0]),
                   lambda r: r["bodies"]["B_A1"]["audit"].update(ok=False),
                   lambda r: r["G"]["G_A1_WA1"]["audit"].update(carried_over_windows=[8]),
                   lambda r: next(x for x in r["bodies"]["B_A1"]["layer_a"] if x["emitted"]).update(emitted=False)):
        data = measured(s)
        tamper(data["run"])
        assert "O3" in failures(data, s)
    data = measured(s)
    lb = data["run"]["bodies"]["B_A1"]["layer_b"]
    if len(lb) >= 2:
        lb[1][1] = lb[0][1]                                                    # Delta の識別子の重複
        assert "O3" in failures(data, s)


def test_o5_detects_a_wrong_consequence_or_a_source_receptor_event() -> None:
    s = eligible_seed()
    run = measured(s)["run"]
    src_r = AS1.RECEPTOR_OF[run["roles"]["source1"]]
    name = next(n for n in M.BODIES if any(r[1] == A.CONSEQUENCE for r in run["bodies"][n]["world_end"]["reserved"]))

    def cons(r):
        return next(x for x in r["bodies"][name]["world_end"]["reserved"] if x[1] == A.CONSEQUENCE)
    for tamper in (lambda r: r["bodies"]["B_A1"]["sensory"].append([5, src_r]),
                   lambda r: cons(r).__setitem__(3, cons(r)[3] + 1),
                   lambda r: r["bodies"][name]["world_end"]["reserved"].remove(cons(r)),
                   lambda r: r["bodies"]["B_A1"]["world_end"]["pending"].append([99, "consequence", r["roles"]["cue_receptor"], 9, "x"]),
                   lambda r: r["G"]["G_A1_WA1"]["sensory"].pop(),
                   lambda r: r["G"]["G_A2_WA2"]["world_end"]["realized"].pop(0)):
        data = measured(s)
        tamper(data["run"])
        assert "O5" in failures(data, s)


def test_o11_detects_inconsistent_layer_a_fields() -> None:
    s = eligible_seed()

    def decided(r, n="B_A1"):
        return next(x for x in AN.record_of(r, n)["layer_a"] if x["outcome"] in A.ACTION_IDS)
    for tamper in (lambda r: decided(r).update(outcome="A2" if decided(r)["outcome"] == "A1" else "A1"),
                   lambda r: decided(r).update(emit_pulse=decided(r)["emit_pulse"] + 1),
                   lambda r: decided(r).update(decision_pulse=decided(r)["open"] - 1),
                   lambda r: decided(r, "G_A1_WA2").update(winner_unit=r["roles"]["cue"]),
                   lambda r: r["bodies"]["F_A2"]["layer_a"][0].update(outcome="other"),
                   lambda r: r["bodies"]["B_A2"]["layer_a"][1].update(open=1)):
        data = measured(s)
        tamper(data["run"])
        assert "O11" in failures(data, s)
    problems = AN.layer_a_problems([{"window": 1, "open": 3, "close": 5, "outcome": "tie", "decision_pulse": 4, "winner_unit": "s1",
                                     "action": None, "emit_pulse": None, "emitted": False}], [(1, 3, 5)],
                                   {"source1": "s1", "source2": "s2"})
    assert problems == ["窓 1：結末と記録の欄が合わない"]


def test_o12_rejects_seeds_outside_the_range_or_seen() -> None:
    assert AN.check_seed(measured(SYN[0]), "synthetic", SYN[0], SMALL)["O12"] == []
    for seed in (31001, 32001, 30201):
        out: list[str] = []
        AN._o12(seed, "synthetic", out)
        assert out
    out = []
    AN._o12(31001, "formal", out)
    assert len(out) == 2                                                       # 範囲の外で、かつ関門で走らせた seed


def test_o13_detects_a_different_rerun() -> None:
    s = eligible_seed()
    for tamper in (lambda r: r["bodies"]["B_A1_rerun"]["activity"].pop(),
                   lambda r: r["bodies"]["B_A1_rerun"]["sigma_p_e"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["bodies"]["B_A1_rerun"].update(sigma_end_sha256="0" * 64),
                   lambda r: r["bodies"]["B_A1_rerun"]["sigma_end"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["bodies"]["B_A1"].update(sigma_end_sha256="0" * 64)):
        data = measured(s)
        tamper(data["run"])
        assert "O13" in failures(data, s)


def test_the_rerun_keeps_no_added_records_and_uses_the_gate_log() -> None:
    rec = measured(SYN[0])["run"]["bodies"][M.RERUN]
    assert set(rec) == AN.BODY_KEYS[M.RERUN] and "window_weights" not in rec and "first_intent" not in rec
    src = inspect.getsource(M.measure_seed)
    assert "rerun = build_body(plan, seed, RULE_OF[RERUN])" in src       # log を渡さない ＝ 関門と同じ既定のログ


def test_meta_blind_must_match_the_mode() -> None:
    s = SYN[0]
    data = measured(s)
    data["meta"]["blind"] = "no"
    assert "structure" in failures(data, s)
    assert AN.check_seed(dict(measured(s), meta=dict(measured(s)["meta"], blind=True)), "formal", s, SMALL)["structure"]


# ---- CT-39-10 一度限りの実行（guard と run.execute。dummy の計算。0037 と同じ） ------------------------------------

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


@pytest.fixture
def repo(tmp_path) -> Path:
    r = tmp_path / "repo"
    (r / EXP.relative_to(ROOT)).mkdir(parents=True)
    (r / EXP.relative_to(ROOT) / "protocol.yaml").write_bytes((EXP / "protocol.yaml").read_bytes())
    _git(r, "init", "-q")
    for k, v in (("user.email", "t@example.invalid"), ("user.name", "t"), ("commit.gpgsign", "false")):
        _git(r, "config", k, v)
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "init")
    return r


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
        R.execute("formal", [32001], tmp_path / "o", repo, None, runner=_dummy, executor_factory=SerialExecutor)
    assert not (tmp_path / "o").exists()
    assert R.OUT_DIR == Path("data/experiments/0039") and R.MAX_WORKERS == 2
    assert list(R.allowed_seeds("formal")) == list(range(32001, 32201))
    assert list(R.allowed_seeds("smoke")) == list(range(32201, 32207))


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


def test_the_raw_meta_carries_the_gate_declaration_and_its_hash(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    _exec(repo, out, GUARD_SEEDS[:1], runner=functools.partial(M.measure_seed, PROTOCOL, plan=SMALL))
    raw = AN.read_raw(R.G.seed_dir(out, GUARD_SEEDS[0]) / R.G.RAW)
    assert raw["meta"]["gate"] == {"sha256": AN.GATE_SHA256, "declaration": AN.GATE_DECLARATION}
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
    assert report["valid"] is True and report["judgment"]["J_7"]["status"] == "inconclusive"   # 3 個体なので m ＜ 10
    assert report["judgment"]["J_W"]["status"] == "not_tested" and report["judgment"]["outcome"] == "inconclusive"
    (out / AN.REPORT).write_text(json.dumps(report), encoding="utf-8")
    assert RC.recheck_directory(out)["mismatches"] == []                       # 保存したファイルからの独立の検算


# ---- smoke の盲検：現象の数値を保存しない（0037 と同じ） -------------------------------------------------

FORBIDDEN_KEYS = ((AN.RUN_KEYS - {"seed", "plan", "roles"}) | AN.END_KEYS | AN.G_KEYS | AN.BOUNDARY_KEYS
                  | set().union(*AN.BODY_KEYS.values()) | JUDGMENT_KEYS
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
    s = eligible_seed()
    for tamper, check in ((lambda r: r["bodies"]["F_A1"]["pulse_weights"][3][1].__setitem__(0, 0.0), "O6"),
                          (lambda r: r["G"]["G_A1_WA1_tr"].update(sigma_end_sha256="0" * 64), "O9"),
                          (lambda r: r["G"]["G_A1_WA2"]["sigma_after_first"]["units"][r["roles"]["cue"]].update(activity=9.0),
                           "O10")):
        data = measured(s)
        data["meta"]["blind"] = True
        tamper(data["run"])
        rec = R.blinded(data, "synthetic", s, SMALL)
        assert set(rec) == {"meta", "blind"} and rec["blind"]["checks"][check] == "fail"
        assert set(rec["blind"]) == AN.BLIND_KEYS and all(v in ("ok", "fail") for v in rec["blind"]["checks"].values())


def test_smoke_report_reads_blinded_records_and_rechecks_o12() -> None:
    s = SYN[0]
    data = measured(s)
    data["meta"]["blind"] = True
    rec = R.blinded(data, "synthetic", s, SMALL)
    rec["meta"]["mode"] = "smoke"
    report = AN.analyze_runs({s: rec}, "smoke", o1=[])
    assert set(report) == {"mode", "O1", "checks", "valid"} and report["checks"][str(s)]["O12"] == "fail"
    assert report["valid"] is False
    missing = copy.deepcopy(rec)
    missing["blind"]["checks"].pop("O14")
    assert AN.check_blinded(missing, s, "smoke") == {k: "fail" for k in AN.CHECK_NAMES}
    no_gate = copy.deepcopy(rec)
    no_gate["meta"]["gate"]["sha256"] = "0" * 64
    assert AN.check_blinded(no_gate, s, "smoke") == {k: "fail" for k in AN.CHECK_NAMES}


def test_smoke_must_be_blind_and_formal_must_not(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    commit = _git(repo, "rev-parse", "HEAD")
    for mode, seeds, kw in (("smoke", [32201], {"blind": False}), ("formal", [32001], {"blind": True}),
                            ("smoke", [32201], {"check_plan": SMALL})):
        out = tmp_path / f"o_{mode}_{min(kw)}"
        with pytest.raises(R.G.GuardError):
            R.execute(mode, seeds, out, repo, commit, runner=_dummy, executor_factory=SerialExecutor, **kw)
        assert not out.exists()


# ---- O1 の証拠（0037 と同じ） ---------------------------------------------------------------------------

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
        return _Proc(0, "....\n300 passed in 90.0s\n")
    out = tmp_path / "out"
    rec = R.record_contract_tests(repo, out, commit, run=ok)
    assert rec["exit_code"] == 0 and calls[0][0][1:] == ["-m", "pytest", "-q", *AN.CONTRACT_TESTS]
    assert len(AN.CONTRACT_TESTS) == 3 and AN.o1_check(out, commit) == []
    R.record_contract_tests(repo, out, commit, run=lambda *a, **k: pytest.fail("走らせ直さない"))


def _never(*a, **k):
    raise AssertionError("O1 が成り立たないのに、契約テストの実行か seed の計算に進んだ")


@pytest.mark.parametrize("name,tamper", [
    ("終了コード", lambda r: r.update(exit_code=1)),
    ("結果の行", lambda r: r.update(summary="1 failed, 298 passed in 50.0s")),
    ("テストのファイルの SHA-256", lambda r: r["test_files_sha256"].update({AN.CONTRACT_TESTS[2]: "0" * 64})),
    ("走らせたコマンド", lambda r: r.update(command=["python", "-m", "pytest", "-q", *AN.CONTRACT_TESTS[:2]])),
    ("測定の commit", lambda r: r.update(measurement_commit="0" * 40)),
])
def test_a_broken_o1_record_stops_before_any_seed_is_started(repo, tmp_path, monkeypatch, name, tamper) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    commit = _o1_repo(repo)
    R.record_contract_tests(repo, out, commit, run=lambda *a, **k: _Proc(0, "299 passed in 50.0s\n"))
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
        R.start("synthetic", GUARD_SEEDS[:2], out, repo, commit, run=lambda *a, **k: _Proc(1, "1 failed, 298 passed\n"),
                runner=_never, executor_factory=SerialExecutor)
    assert not (out / R.G.SEEDS_DIR).exists() and (out / AN.O1_FILE).exists()


def test_a_valid_o1_record_lets_start_run_the_seeds(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    commit = _o1_repo(repo)
    R.record_contract_tests(repo, out, commit, run=lambda *a, **k: _Proc(0, "299 passed in 50.0s\n"))
    done = R.start("synthetic", GUARD_SEEDS[:2], out, repo, commit, run=_never, runner=_dummy, executor_factory=SerialExecutor)
    assert done["completed"] == GUARD_SEEDS[:2]


def test_main_goes_through_start() -> None:
    src = inspect.getsource(R.main)
    assert "start(mode, seeds, out, REPO, args.measurement_commit)" in src and "execute(" not in src


def test_results_copy_is_verified_byte_for_byte(repo, tmp_path, monkeypatch) -> None:
    import shutil
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
