"""実験 0040 の道具の契約テスト（確定した事前登録 v0.2 の README・protocol.yaml、#184 merge `9a8651a`。README §14 の CT-40-1〜10）。

本番の seed（33001〜33200）・smoke の seed（33201〜33206）・関門の seed（31001〜31040）・0039 の seed（32001〜32399）は使わない
（実行もしない）。0034〜0039 の seed・raw も、関門の記録も使わない。合成の契約テスト専用の範囲（33301〜33399）だけを使う。
合成の個体は、本番と同じ道具（measure.measure_seed）・同じ式で、区間だけを小さくした Plan（SMALL：8 窓、E ＝ 窓 1〜4、
終わり 350）か、本番の Plan で、実物の runtime を通して作る。結果を見て Plan・seed を選んでいない（seed は範囲の最初から順に、
構成の条件だけで決定的に選ぶ）。テストは操作の確認・記録の形・介入の部品の決まり方・Runtime の順序・判定と推定の算術だけを
確かめ、合成の個体の判定と推定の量（A1 の割合・差・符号・J_A・E_A・区間・対照の数・最初に分かれた Pulse・窓の直前の発火）の値を
表示も判定もしない（README §9.3）。

構成（README §14 の契約テストの要件）：
- 決まった窓のある個体：SMALL の X1 の層 A に、決まった窓が 1 つ以上ある最初の合成の個体
- X1 と X2 の発火が分かれる個体：SMALL で、X1 と X2 の発火の記録が違う最初の合成の個体（分かれる場合の SE-A2）
- 分かれない場合の SE-A2：重みの違う接続の送り手を構造的に沈黙させた系（契約テストだけの値。AS2b の道具を直接使う）
- 系 S-1′・補題 L1・L2：Unit の θ・c を出生時の範囲の角に置き、端の重み（X1・X2 の値）で止め、結果を返さない世界の合成の系

使った合成の seed（PR に開示）：33301〜33310（SMALL）、33321〜33326（一度限りの実行・盲検の契約。dummy の計算と SMALL）、
33390〜33392（S-1′・L1・L2 の角の系、SE-A2 の分かれない場合、SE-A4・SE-A5）、33399（本番の Plan で実物の runtime を通す確かめ）、
構成の条件で選んだ個体（33301〜33399 の最初から順。どれになったかはテストの中で決まる）。
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
import re
import subprocess
from concurrent.futures import Future
from fractions import Fraction
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments" / "0040_as2b_weight_extremes"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = _load("measure_0040_test", EXP / "measure.py")
AN = _load("analyze_0040_test", EXP / "analyze.py")
AL = _load("alignment_0040_test", EXP / "alignment.py")
AX = _load("analysis_0040_test", EXP / "analysis.py")
R = _load("run_0040_test", EXP / "run.py")
RC = _load("recheck_0040_test", EXP / "recheck.py")
GATE = _load("gate_0038_for_0040_test", ROOT / "experiments" / "0038_as2b_forward_gate" / "gate.py")
A, AS1 = M.A, M.AS1
SMALL = M.Plan(41, 41, 8, 2, 19, 2, 4)
FORMAL = M.formal_plan(PROTOCOL)
SYN = list(range(33301, 33311))
SYN_ALL = list(range(33301, 33400))
GUARD_SEEDS = list(range(33321, 33327))
CORNER_SEEDS = (33390, 33391, 33392)
FORMAL_SEED = 33399
W_MAX, W0 = PROTOCOL["brain"]["w_max"], PROTOCOL["brain"]["initial_weight_w0"]


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)


def _meta(seed: int, mode: str = "synthetic") -> dict:
    """run.py が書く meta と同じ形（protocol の写しと、その SHA-256 を含む）。"""
    return {"experiment": "0040", "kind": PROTOCOL["kind"], "mode": mode, "seed": seed, "manifest": M.manifest_raw(),
            "protocol": json.loads(json.dumps(PROTOCOL)), "protocol_sha256": AN.PROTOCOL_SHA256,
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
def decided_seed() -> int:
    """SMALL の X1 の層 A に、決まった窓が 1 つ以上ある最初の合成の個体（構成の条件だけ。値は表示しない）。"""
    return next(s for s in SYN_ALL if any(r["outcome"] in A.ACTION_IDS for r in measured(s)["run"]["systems"]["X1"]["layer_a"]))


@functools.cache
def diverging_seed() -> int:
    """SMALL で、X1 と X2 の発火の記録が違う最初の合成の個体（SE-A2 の分かれる場合）。"""
    return next(s for s in SYN_ALL if measured(s)["run"]["systems"]["X1"]["activity"] != measured(s)["run"]["systems"]["X2"]["activity"])


# ---- protocol と道具の一致 ----------------------------------------------------------------------

def test_protocol_and_tools_are_aligned() -> None:
    AL.check(PROTOCOL)


def test_the_formal_plan_is_taken_from_the_gate_declaration() -> None:
    assert FORMAL == M.Plan(41, 41, 50, 2, 19, 2, 25) and (FORMAL.last_e_pulse, FORMAL.end) == (1065, 2072)
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
                   lambda d: d["bodies"].update(pulses=2073),
                   lambda d: d["roles"].update(stream="other-{seed}")):
        changed = copy.deepcopy(decl)
        tamper(changed)
        with pytest.raises(ValueError):
            M.plan_from_declaration(changed, 25)
    not_taken = copy.deepcopy(decl)                                    # 本体の欄（respond など）は、この実験では取らない
    not_taken["bodies"].update(respond=False, plasticity="off")
    assert M.plan_from_declaration(not_taken, 25) == FORMAL


def test_the_run_entry_point_uses_only_the_protocol_plan() -> None:
    assert "W.measure_seed(PROTOCOL, seed)" in inspect.getsource(R.measure)
    assert "plan" not in inspect.signature(R.measure).parameters


def test_seen_seeds_include_0039_and_the_gate_and_exclude_0040() -> None:
    assert {30001, 30299, 31001, 31040, 32001, 32200, 32201, 32301, 32399, 9101} <= AL.SEEN
    assert not ({33001, 33200, 33201, 33206, 33301, 33399} & AL.SEEN)


def test_contract_tests_of_o1_are_the_tool_tests_and_this_file() -> None:
    assert AN.CONTRACT_TESTS == (*PROTOCOL["tools"]["contract_tests"], "tests/integration/test_as2b_weight_extremes_0040.py")
    assert R.CONTRACT_TESTS == AN.CONTRACT_TESTS and (ROOT / AN.CONTRACT_TESTS[-1]) == Path(__file__).resolve()


def test_the_analysis_contrasts_and_controls_follow_the_protocol() -> None:
    q = PROTOCOL["quantities"]["contrasts"]
    assert {k: list(v) for k, v in AN.CONTRASTS.items()} == q and list(AN.CONTRASTS) == list(q)
    assert list(AN.MUST_REPORT) == PROTOCOL["must_report"]["contrasts"] and AN.INTERVAL_OF == {"D_X_E": "E"}
    assert AN.CHECK_NAMES[1:] == tuple(PROTOCOL["operation_checks"][1:])
    assert [list(p) for p in AN.CROSS_TABLES] == [["D_X", "D_M"], ["Delta_1", "Delta_2"]]


# ---- 合成の個体が、すべての操作の確認を通る ------------------------------------------------------------

@pytest.mark.parametrize("seed", SYN)
def test_synthetic_individuals_pass_every_operation_check(seed) -> None:
    assert failures(measured(seed), seed) == {}


def test_the_formal_plan_through_the_runtime_passes_every_operation_check() -> None:
    data = measured(FORMAL_SEED, FORMAL)
    assert AN.check_seed(data, "synthetic", FORMAL_SEED, None) == {k: [] for k in AN.CHECK_NAMES}
    run = data["run"]
    assert all(len(run["systems"][n]["layer_a"]) == 50 for n in M.SYSTEMS)
    assert all(len(run["systems"][n]["pulse_weights"]) == 2072 for n in M.RECORDED)


@pytest.mark.parametrize("which", ["decided", "diverging"])
def test_the_constructed_individuals_pass_every_operation_check(which) -> None:
    seed = decided_seed() if which == "decided" else diverging_seed()
    assert failures(measured(seed), seed) == {}


JUDGMENT_KEYS = {"share", "s_U", "s_E", "sign", "difference", "contrasts", "in_population", "judgment", "individuals",
                 "auxiliary", "descriptive_controls", "estimate", "interval", "counts_U", "counts_E", "S1_prime", "flip",
                 "first_divergence", "undefined_kind", "pre_window_firing_U", "never_diverged_X1_X2", "J_A", "E_A"}


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


# ---- CT-40-1 組み立て -------------------------------------------------------------------------------------

def test_ct40_1_every_system_is_built_open_loop_from_the_declared_values() -> None:
    src = inspect.getsource(M.build_system)
    assert "A.build(seed, schedule=plan.schedule(), delay=plan.delay, rule_c=RULE_C, respond=False" in src
    s = M.build_system(SMALL, SYN[0])
    assert s.meta == {"delay": 2, "rule_c": "A1", "respond": False, "outlet": True, "world_cues": True}
    assert s.log.keep == AS1.AS1Log.DEFAULT_KEEP and s.connections.history == [] and s.pulse == 0
    run = measured(SYN[0])["run"]
    assert all(run["systems"][n]["world_end"]["rule"]["respond"] is False for n in M.SYSTEMS)


def test_the_gate_and_0039_and_formal_seeds_are_never_run_by_the_tests(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    commit = _git(repo, "rev-parse", "HEAD")
    for seed in (31001, 31040, 32001, 32301, 33001, 33201, 30201):
        with pytest.raises(R.G.GuardError):
            R.execute("synthetic", [seed], tmp_path / f"o{seed}", repo, commit, runner=_dummy, executor_factory=SerialExecutor)
        assert not (tmp_path / f"o{seed}").exists()
    for mode in ("formal", "smoke"):
        with pytest.raises(R.G.GuardError):
            R.execute(mode, [32001], tmp_path / f"g{mode}", repo, commit, runner=_dummy, executor_factory=SerialExecutor)


# ---- CT-40-2 Pulse 0 の操作（SE-A1） ------------------------------------------------------------------------

def test_ct40_2_the_pulse_0_steps_are_in_order_without_a_pulse_between() -> None:
    run = measured(SYN[0])["run"]
    p0 = run["pulse_0"]
    assert p0["steps"] == AN.expected_steps(run)
    assert [s[0] for s in p0["steps"][:3]] == ["T0", "T1", "T2"] and all(s[2] == 0 for s in p0["steps"] if s[0] != "T3")
    for t in ("T0", "T1", "T2"):
        assert all(p0[f"sigma_{t}"][n]["pulse"] == 0 for n in M.RECORDED)
    assert all(AS1.sigma_diff(p0["sigma_T0"]["X0"], p0["sigma_T0"][n]) == [] for n in M.RECORDED)


def test_ct40_2_the_transplant_changes_only_the_four_weights() -> None:
    run = measured(SYN[0])["run"]
    p0, cids = run["pulse_0"], AN.role_cids(run["roles"])
    four = {cids[k] for k in M.ROLE_KEYS}
    for n in ("X1", "X2", "M1", "M2"):
        diff = {tuple(p) for p in AS1.sigma_diff(p0["sigma_T1"]["X0"], p0["sigma_T1"][n])}
        assert diff == {("connections", c, "weight") for c in four}, n
        w = AN._weights_of(p0["sigma_T1"][n])
        assert w[cids["source1_to_source2"]] == w[cids["source2_to_source1"]] == W0        # 源どうしには触れない
        assert {k: w[cids[k]] for k in M.ROLE_KEYS} == AN.VALUES[n]
    assert AS1.sigma_diff(p0["sigma_T1"]["X0"], p0["sigma_T1"]["X0_tr"]) == []
    assert AS1.sigma_diff(p0["sigma_T0"]["X0"], p0["sigma_T1"]["X0"]) == []
    for n in M.RECORDED:
        assert {p[0] for p in AS1.sigma_diff(p0["sigma_T1"][n], p0["sigma_T2"][n])} == {"interventions"}
        assert p0["sigma_T1"][n]["interventions"] == AN.EMPTY_INTERVENTIONS


def test_ct40_2_a_transplant_after_the_freeze_fails() -> None:
    s = M.build_system(SMALL, SYN[0], log=_log())
    six = frozenset(M._weights(s))
    s.declare(M._freeze_six(six), label="x")
    with pytest.raises(ValueError, match="FREEZE 中の接続"):
        s.transplant({min(six): 0.001})
    free = M.build_system(SMALL, SYN[0], log=_log())
    free.transplant({min(six): 0.001})
    assert M._weights(free)[min(six)] == 0.001 and free.pulse == 0


def test_o4_detects_tampering() -> None:
    s = SYN[0]
    for tamper in (lambda r: r["pulse_0"]["steps"].__setitem__(0, r["pulse_0"]["steps"][1]),
                   lambda r: r["pulse_0"]["steps"][1][4].update(intervention_state_at_transplant={"active": [1], "frozen": {}}),
                   lambda r: r["pulse_0"]["sigma_T1"]["X1"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["pulse_0"]["sigma_T1"]["M1"]["connections"][AN.role_cids(r["roles"])["source1_to_source2"]].update(weight=0.004),
                   lambda r: r["pulse_0"]["sigma_T2"]["X2"]["interventions"]["frozen"][min(r["W_0"])].update(weight=0.0011),
                   lambda r: r["pulse_0"]["sigma_T2"]["X1"].update(pulse=1),
                   lambda r: r["pulse_0"]["sigma_T0"]["M2"]["units"][r["roles"]["cue"]].update(activity=9.0),
                   lambda r: r["systems"]["X1"]["history"].append(r["systems"]["X1"]["history"][0]),
                   lambda r: r["systems"]["X1_rerun"]["history"].append([0, "x", []])):
        changed = measured(s)
        tamper(changed["run"])
        assert "O4" in failures(changed, s)


# ---- CT-40-3 介入の値（SE-A3・SE-A6） --------------------------------------------------------------------

def test_ct40_3_the_values_come_from_c0_and_keep_f1_exactly() -> None:
    w_min, w_max, w0 = M.c0_weights()
    assert (w_min, w_max, w0) == (0.0, W_MAX, W0)
    values = M.intervention_values(w_min, w_max, w0)
    assert values == AN.VALUES
    assert values["X1"] == {"C_to_source1": w_max, "source1_to_C": 0.0, "C_to_source2": 0.0, "source2_to_C": w_max}
    assert values["M1"] == {"C_to_source1": 0.0075, "source1_to_C": 0.0025, "C_to_source2": 0.0025, "source2_to_C": 0.0075}
    for four in values.values():
        assert four["C_to_source1"] + four["source1_to_C"] == w_max and four["C_to_source2"] + four["source2_to_C"] == w_max
        assert all(0.0 <= v <= w_max for v in four.values())
    swap = {"C_to_source1": "C_to_source2", "source1_to_C": "source2_to_C", "C_to_source2": "C_to_source1",
            "source2_to_C": "source1_to_C"}
    for a, b in (("X1", "X2"), ("M1", "M2")):                        # 札の入れ替えで、鏡の系の値がビット単位で入れ替わる
        assert {swap[k]: v for k, v in values[a].items()} == values[b]
    for bad in ((0.001, w_max, w0), (0.0, w_max, 0.004)):
        with pytest.raises(ValueError):
            M.intervention_values(*bad)
    assert "w_max - " not in inspect.getsource(M.intervention_values)    # 相手の値を引き算で作らない


def test_o7_detects_wrong_values_or_pair_sums() -> None:
    s = SYN[0]
    for tamper in (lambda r: r["pulse_0"]["sigma_T2"]["X1"]["connections"][AN.role_cids(r["roles"])["C_to_source1"]].update(weight=0.0099),
                   lambda r: r["pulse_0"]["sigma_T2"]["M2"]["connections"][AN.role_cids(r["roles"])["source1_to_C"]].update(weight=0.0026),
                   lambda r: r["systems"]["X1_rerun"]["sigma_end"]["connections"][AN.role_cids(r["roles"])["source2_to_C"]].update(weight=0.0)):
        changed = measured(s)
        tamper(changed["run"])
        assert "O7" in failures(changed, s)
    changed = measured(s)
    changed["run"]["values"]["X1"]["C_to_source1"] = 0.009
    assert "structure" in failures(changed, s)


# ---- CT-40-4 恒等（O8）と記録の非干渉（O9） -------------------------------------------------------------

def test_ct40_4_the_own_value_transplant_reproduces_x0_and_the_rerun_reproduces_x1() -> None:
    run = measured(decided_seed())["run"]
    for key in ("activity", "sensory", "layer_a", "layer_b", "delta_log", "sigma_end_sha256", "pulse_weights", "history"):
        assert run["systems"]["X0"][key] == run["systems"]["X0_tr"][key], key
    for key in ("activity", "sensory", "layer_a", "layer_b", "delta_log", "sigma_end_sha256", "history"):
        assert run["systems"]["X1"][key] == run["systems"]["X1_rerun"][key], key


def test_ct40_4_the_rerun_keeps_no_added_records_and_uses_the_default_log() -> None:
    rec = measured(SYN[0])["run"]["systems"][M.RERUN]
    assert set(rec) == AN.SYSTEM_KEYS[M.RERUN] and "pulse_weights" not in rec and "first_firing" not in rec
    src = inspect.getsource(M.measure_seed)
    assert "rerun = build_system(plan, seed)" in src                      # log を渡さない ＝ AS2b の道具の既定のログ
    assert "_pulse_0(rerun, RERUN, values, six, steps, None)" in src and "A.advance_to(rerun.app, end)" in src


def test_o8_and_o9_detect_a_broken_identity_or_rerun() -> None:
    s = decided_seed()
    for tamper, check in ((lambda r: r["systems"]["X0_tr"].update(sigma_end_sha256="0" * 64), "O8"),
                          (lambda r: r["systems"]["X0_tr"]["activity"].pop(), "O8"),
                          (lambda r: r["systems"]["X1_rerun"]["activity"].pop(), "O9"),
                          (lambda r: r["systems"]["X1_rerun"]["sigma_end"]["units"][r["roles"]["cue"]].update(activity=9.0), "O9"),
                          (lambda r: r["systems"]["X1"].update(sigma_end_sha256="0" * 64), "O9")):
        data = measured(s)
        tamper(data["run"])
        assert check in failures(data, s)


# ---- CT-40-5 共通の始まり（SE-A2） ----------------------------------------------------------------------

def _first_firing(run) -> int | None:
    return min((p for p, _u in run["systems"]["X0"]["activity"]), default=None)


def test_ct40_5_the_value_systems_share_the_start_up_to_the_first_firing() -> None:
    for seed in (SYN[0], diverging_seed()):
        run = measured(seed)["run"]
        t1 = _first_firing(run)
        assert t1 is not None
        for n in M.VALUE_SYSTEMS:
            assert run["systems"][n]["first_firing"]["pulse"] == t1
            fd = AN.first_divergence(run["systems"][n]["activity"], run["systems"]["X0"]["activity"], 1, SMALL.end)
            assert fd is None or fd >= t1 + 1
    run = measured(diverging_seed())["run"]
    assert AN.first_divergence(run["systems"]["X1"]["activity"], run["systems"]["X2"]["activity"], 1, SMALL.end) is not None


def _silent_sender_pair(seed: int):
    """源 1 を構造的に沈黙させた二つの系で、違いを源 1 → C の 1 本（送り手は沈黙）だけにする（契約テストだけの値）。"""
    out = []
    for weight in (W0, W_MAX):
        s = M.build_system(SMALL, seed, log=_log())
        roles = s.roles.as_dict()
        theta = THETA[1]
        c = (theta - AN.E_S - 1e-9) * (1 - LAMBDA)
        inner = _inner(s, roles["source1"])
        inner._dynamics = dataclasses.replace(inner._dynamics, threshold=theta, intrinsic_drive_per_second=c)
        inner.import_state(inner.export_state() | {"activity": theta / 2})
        s.transplant({f"{roles['source1']}.main->{roles['cue']}": weight, f"{roles['cue']}.main->{roles['source1']}": W_MAX - weight})
        s.declare(M._freeze_six(frozenset(M._weights(s))), label="T2")
        out.append(s)
    return out


def test_ct40_5_no_difference_arises_when_the_differing_senders_never_fire() -> None:
    """分かれない場合：C → 源 1 の重みの違いは、C の発火で源 1 への駆動の違いになるが、源 1 が構造的に沈黙していれば発火に届かず、
    源 1 → C の違い（送り手は沈黙）は駆動にもならない。二つの系の発火・層 A・層 B は終わりまで同じ。"""
    a, b = _silent_sender_pair(CORNER_SEEDS[0])
    for s in (a, b):
        A.advance_to(s.app, SMALL.end)
    assert a.log.activity() == b.log.activity() and a.decider.records == b.decider.records
    assert a.world.intents == b.world.intents
    assert a.roles.source1 not in {u for _, u in a.log.activity()}


def test_ct40_5_a_drive_difference_appears_only_after_its_sender_fires() -> None:
    """分かれる場合の始まり：X1 と X0 の値の系を 1 Pulse ずつ進め、最初に Unit が発火した Pulse t₁ の処理の後、Unit の状態・層 A は同じで、
    届く途中の駆動の違いは、重みの違う接続の、t₁ に発火した送り手の分だけ。t₁ より前の Pulse では駆動に違いがない。"""
    seed = diverging_seed()
    pair = []
    for key in ("X1", None):
        s = M.build_system(SMALL, seed, log=_log())
        if key is not None:
            s.transplant({cid: AN.VALUES[key][role] for role, cid in M.role_connections(s.roles).items()})
        s.declare(M._freeze_six(frozenset(M._weights(s))), label="T2")
        pair.append(s)
    t1 = None
    for p in range(1, SMALL.end + 1):
        for s in pair:
            A.advance_to(s.app, p)
        sa, sb = M._sigma(pair[0]), M._sigma(pair[1])
        assert sa["units"] == sb["units"] and sa["exit"] == sb["exit"]
        if pair[0].log.activity():
            t1 = p
            break
        assert sa["drives"] == sb["drives"]
    fired = {u for q, u in pair[0].log.activity() if q == t1}
    wa, wb = M._weights(pair[0]), M._weights(pair[1])
    differs = [(x, y) for x, y in zip(sa["drives"], sb["drives"]) if x != y]
    assert t1 is not None and differs and len(sa["drives"]) == len(sb["drives"])       # どの Unit の出る接続にも、値の違う 1 本がある
    for x, y in differs:
        cid = f"{x[0]}.main->{x[1]}"
        assert x[0] in fired and wa[cid] != wb[cid] and x[3] == t1 and (x[2], y[2]) == (wa[cid], wb[cid])


def test_o10_detects_tampering() -> None:
    s = diverging_seed()
    run = measured(s)["run"]
    t1 = _first_firing(run)
    cue = run["roles"]["cue"]
    for tamper in (lambda r: r["systems"]["X2"]["first_firing"]["sigma"]["units"][cue].update(activity=9.0),
                   lambda r: r["systems"]["M1"]["first_firing"].update(pulse=t1 + 1),
                   lambda r: r["systems"]["X1"]["activity"].insert(0, [t1, "zz"]),
                   lambda r: r["systems"]["M2"]["first_firing"]["sigma"]["drives"].append(["s1", "s2", 0.5, t1]),
                   lambda r: r["systems"]["X2"]["first_firing"]["sigma"]["exit"].update(cursor=7),
                   lambda r: r["systems"]["X1"]["first_firing"]["sigma"]["world"].update(next_rid=999)):
        changed = measured(s)
        tamper(changed["run"])
        assert "O10" in failures(changed, s)


def test_o10_accepts_only_the_drive_difference_of_a_weight_differing_connection_whose_sender_fired() -> None:
    s = diverging_seed()
    data = measured(s)
    run = data["run"]
    t1 = _first_firing(run)
    cids = AN.role_cids(run["roles"])
    cid = cids["C_to_source1"]
    u, v = AN._ends(cid)
    for n in M.VALUE_SYSTEMS:                                          # 送り手 C が t₁ に発火した、と記録を書き換える
        w = AN._weights_of(run["pulse_0"]["sigma_T2"][n])
        if not any(p == t1 and x == u for p, x in run["systems"][n]["activity"]):
            run["systems"][n]["activity"].insert(0, [t1, u])
        run["systems"][n]["first_firing"]["sigma"]["drives"] = [[u, v, w[cid], t1]]
    assert "O10" not in failures(data, s)
    wx0 = AN._weights_of(run["pulse_0"]["sigma_T2"]["X0"])
    run["systems"]["X1"]["first_firing"]["sigma"]["drives"] = [[u, v, wx0[cid] + 1.0, t1]]   # 重みと合わない駆動
    assert "O10" in failures(data, s)


# ---- CT-40-6 世界（SE-A4） ---------------------------------------------------------------------------------

def test_ct40_6_the_open_world_has_no_consequence_and_rule_c_is_inert() -> None:
    seed = CORNER_SEEDS[2]
    ends = []
    for rule_c in ("A1", "A2"):
        s = A.build(seed, schedule=SMALL.schedule(), delay=SMALL.delay, rule_c=rule_c, respond=False, log=_log())
        s.transplant({cid: AN.VALUES["X1"][role] for role, cid in M.role_connections(s.roles).items()})
        s.declare(M._freeze_six(frozenset(M._weights(s))), label="T2")
        A.advance_to(s.app, SMALL.end)
        ends.append(s)
    a, b = ends
    assert a.log.activity() == b.log.activity() and a.log.sensory() == b.log.sensory()
    assert a.decider.records == b.decider.records and a.world.intents == b.world.intents
    assert [tuple(p) for p in AS1.sigma_diff(M._sigma(a), M._sigma(b))] == [("world", "rule", "rule_c")]
    assert all(r[1] == A.CUE for r in a.world.export_state()["reserved"])
    assert {r for _, r in a.log.sensory()} == {a.roles.cue_receptor}


def test_o5_detects_a_consequence_or_a_source_receptor_event() -> None:
    s = decided_seed()
    run = measured(s)["run"]
    src_r = AS1.RECEPTOR_OF[run["roles"]["source1"]]
    for tamper in (lambda r: r["systems"]["X1"]["sensory"].append([5, src_r]),
                   lambda r: r["systems"]["X2"]["world_end"]["reserved"].append([99, "consequence", r["roles"]["cue_receptor"], 50, "d1"]),
                   lambda r: r["systems"]["M1"]["world_end"]["pending"].append([99, "cue", r["roles"]["cue_receptor"], 9, None]),
                   lambda r: r["systems"]["X0"]["world_end"]["realized"].pop(0),
                   lambda r: r["systems"]["X0_tr"]["sensory"].pop()):
        data = measured(s)
        tamper(data["run"])
        assert "O5" in failures(data, s)


# ---- CT-40-7 FREEZE（SE-A5） --------------------------------------------------------------------------------

def test_ct40_7_the_frozen_weights_stay_at_the_t2_values() -> None:
    run = measured(SYN[0])["run"]
    for n in M.RECORDED:
        want = AN._as_row(run, AN._weights_of(run["pulse_0"]["sigma_T2"][n]))
        rows = run["systems"][n]["pulse_weights"]
        assert [p for p, _ in rows] == list(range(1, SMALL.end + 1)) and all(w == want for _, w in rows)


def test_ct40_7_traces_do_not_matter_when_all_six_are_frozen() -> None:
    """SE-A5：全 6 本を止めた系では、痕跡の扱い（advance・hold）を替えても、発火・層 A・Unit の状態・重みが同じ。"""
    ends = []
    for policy in (AS1.ADVANCE, AS1.HOLD):
        s = M.build_system(SMALL, CORNER_SEEDS[2], log=_log())
        s.transplant({cid: AN.VALUES["X2"][role] for role, cid in M.role_connections(s.roles).items()})
        s.declare([AS1.Intervention(AS1.FREEZE, frozenset(M._weights(s)), policy)], label=policy)
        A.advance_to(s.app, SMALL.end)
        sig = M._sigma(s)
        ends.append((s.log.activity(), sig["units"], sig["exit"], M._weights(s)))
    assert ends[0] == ends[1]


def test_o6_detects_a_moving_weight() -> None:
    s = SYN[0]
    for tamper in (lambda r: r["systems"]["X2"]["pulse_weights"][5][1].__setitem__(0, 0.0011),
                   lambda r: r["systems"]["M1"]["pulse_weights"].pop(),
                   lambda r: r["systems"]["X1_rerun"]["sigma_end"]["connections"][min(r["W_0"])].update(weight=0.004)):
        data = measured(s)
        tamper(data["run"])
        assert "O6" in failures(data, s)


# ---- CT-40-8 系 S-1′・補題 L1・L2（README §7.2） ----------------------------------------------------------

THETA = (0.45, 0.55)                                                 # 出生時の θ の範囲（0.5 ± 10%）
DRIVE = (0.072, 0.088)                                               # 出生時の c の範囲（0.08 ± 10%）
LAMBDA = 0.85


def _inner(system, unit_id):
    u = system.app.units.get(unit_id)
    return u._inner if isinstance(u, A.CompetitionTap) else u


def _corner_system(seed: int, values: dict, key: str):
    """Unit の θ・c・初期の activity を決めた値に置き、4 本を端の値（key：X1 か X2）にして 6 本を止めた、結果を返さない世界の
    合成の系（契約テストだけ。Core も道具も変えない）。values：役 → (θ, c)。初期の activity は上限 θ/2。"""
    s = M.build_system(FORMAL, seed, log=_log())
    roles = s.roles.as_dict()
    for role, (theta, c) in values.items():
        inner = _inner(s, roles[role])
        inner._dynamics = dataclasses.replace(inner._dynamics, threshold=theta, intrinsic_drive_per_second=c)
        inner.import_state(inner.export_state() | {"activity": theta / 2})
    s.transplant({cid: AN.VALUES[key][role] for role, cid in M.role_connections(s.roles).items()})
    s.declare(M._freeze_six(frozenset(M._weights(s))), label="corner")
    return s


def _run_recording_adaptation(system, unit_id) -> float:
    top = 0.0
    for pulse in range(1, FORMAL.end + 1):
        A.advance_to(system.app, pulse)
        top = max(top, _inner(system, unit_id).export_state()["adaptation"])
    return top


def _gaps(pulses: list[int]) -> list[int]:
    return [b - a for a, b in itertools.pairwise(pulses)]


def test_ct40_8_the_bound_e_s_matches_the_preregistered_analysis() -> None:
    lam, w = LAMBDA, W_MAX
    e_s = w * ((1 + lam ** 4) / (1 - lam ** 23) + 2 / (1 - lam ** 7))
    assert AN.E_S == pytest.approx(e_s, abs=1e-15) and AN.E_S == pytest.approx(PROTOCOL["corollary_S1_prime"]["E_S_value"], abs=5e-6)
    bound = AX.silence_bound(AX.c0_values(), AX.gate_set())
    assert bound["phi_R_cues_only"] == pytest.approx(1 / (1 - lam ** 41)) and bound["phi_R_cues_only"] <= bound["phi_R"]
    assert RC.bound_e_s(M.manifest_raw(), dataclasses.asdict(FORMAL)) == pytest.approx(AN.E_S, abs=1e-15)
    assert AN.margin({"dynamics": {"intrinsic_drive_per_second": 0.08, "decay_per_second": 0.85, "threshold": 0.5}}) \
        == pytest.approx(0.08 / 0.15 - 0.5)


@pytest.mark.parametrize("key", ["X1", "X2"])
def test_ct40_8_a_source_below_the_bound_never_fires_even_at_the_corners(key) -> None:
    """系 S-1′：g ＜ −E_S の源は、ほかの二つの Unit を最も発火しやすい値に置き、4 本を端の値で止め（X1 なら C → その源 ＝ w_max）、
    世界が結果を返さなくても、本番の長さのあいだ一度も発火しない。"""
    theta = THETA[1]
    c = (theta - AN.E_S - 1e-9) * (1 - LAMBDA)
    assert DRIVE[0] <= c <= DRIVE[1]
    easy = (THETA[0], DRIVE[1])
    s = _corner_system(CORNER_SEEDS[0], {"source1": (theta, c), "cue": easy, "source2": easy}, key)
    assert AN.margin(_inner(s, s.roles.source1).export_state()) < -AN.E_S
    A.advance_to(s.app, FORMAL.end)
    fired = {u for _, u in s.log.activity()}
    assert s.roles.source1 not in fired and _inner(s, s.roles.source1).export_state()["fire_count"] == 0
    assert {s.roles.cue, s.roles.source2} <= fired                   # ほかの二つは発火している（確かめが空でない）
    assert all(r["outcome"] in ("A2", A.NONE) for r in s.decider.records)      # その源の行動 A1 は一度も勝たない（SE-A7）


@pytest.mark.parametrize("key", ["X1", "X2"])
def test_ct40_8_lemma_l1_and_l2_hold_at_the_corners(key) -> None:
    """補題 L1：手がかりの Unit は、Receptor の入力の入る Pulse（感覚の出来事の翌 Pulse）に必ず発火し、順応は 0.441 未満。そのほかの
    発火は、直前の発火から 7 Pulse 以上後。補題 L2：源の連続する発火は 7 Pulse 以上離れる。結果を返さない世界では、感覚の出来事は手がかりだけ。"""
    easy = (THETA[0], DRIVE[1])
    for cue_values in (easy, (THETA[1], DRIVE[0])):                  # 手がかりの Unit：最も発火しやすい角と、最も発火しにくい角
        s = _corner_system(CORNER_SEEDS[1], {"cue": cue_values, "source1": easy, "source2": easy}, key)
        top = _run_recording_adaptation(s, s.roles.cue)
        act = s.log.activity()
        cue_fires = [p for p, u in act if u == s.roles.cue]
        r_pulses = {p + 1 for p, _ in s.log.sensory()}
        assert sorted(p for p, _ in s.log.sensory()) == list(FORMAL.schedule().cues)      # 手がかりだけ
        assert r_pulses and r_pulses <= set(cue_fires)               # L1：R の Pulse では必ず発火する
        assert top < 0.441
        for prev, cur in itertools.pairwise(cue_fires):
            assert cur in r_pulses or cur - prev >= 7                # L1：R でない発火は、直前の発火から 7 以上後
        for src in (s.roles.source1, s.roles.source2):
            fires = [p for p, u in act if u == src]
            assert len(fires) > 10 and min(_gaps(fires)) >= 7        # L2


def test_ct40_8_the_label_and_a_violation_are_reported_without_changing_the_judgment() -> None:
    s = decided_seed()
    run = measured(s)["run"]
    src = run["roles"]["source1"]
    d = run["birth_units"][src]["dynamics"]
    d["threshold"], d["intrinsic_drive_per_second"] = 0.55, 0.072    # 記録の上だけ、構造的に沈黙する源の値にする
    ind = AN.individual(run)
    assert ind["S1_prime"]["silent_source"] == {"source1": True, "source2": False}
    fired = any(u == src for n in M.SYSTEMS for _, u in run["systems"][n]["activity"])
    assert ind["S1_prime"]["violations"] == (["source1"] if fired else [])
    aux = AN.auxiliary({"1": ind})
    assert aux["R1"]["S1_prime"]["labels_withdrawn"] is fired
    assert aux["R1"]["S1_prime"]["individuals_with_silent_source"] == (None if fired else 1)
    assert "S1" not in json.dumps(AN.judge({"1": ind})) and "S1" not in json.dumps(AN.estimate({"1": ind}))


# ---- CT-40-9 量と判定・推定の算術（README §3〜§5） --------------------------------------------------------

def _layer(outcomes: list[str]) -> list[dict]:
    return [{"window": k + 1, "outcome": o} for k, o in enumerate(outcomes)]


def test_window_counts_and_shares() -> None:
    la = _layer(["A1", "tie", "none", "A2", "A1", "A1", "none", "A2"])
    assert AN.window_counts(la, 1, 4) == {"windows": 4, "decided": 2, "A1": 1, "A2": 1, "tie": 1, "none": 1}
    u = AN.window_counts(la, 5, 8)
    assert u == {"windows": 4, "decided": 3, "A1": 2, "A2": 1, "tie": 0, "none": 1}
    assert AN.share(u) == Fraction(2, 3) and AN.share(AN.window_counts(_layer(["tie", "none"]), 1, 2)) is None
    assert [AN.sign(x) for x in (Fraction(1, 7), Fraction(-1, 7), Fraction(0))] == ["+", "-", "0"]


def _with_outcomes(run: dict, outcomes: dict[str, list[str]]) -> dict:
    """実物の合成の個体の記録の、層 A の結末だけを差し替える（判定の算術の確かめにだけ使う。操作の確認には通さない）。"""
    for name, outs in outcomes.items():
        la = run["systems"][name]["layer_a"]
        assert len(outs) == len(la)
        for r, o in zip(la, outs):
            r["outcome"] = o
    return run


E_PART = ["A1", "none", "A2", "none"]


def test_the_individual_quantities_follow_the_definitions() -> None:
    run = measured(SYN[0])["run"]
    u = {"X1": ["A1", "A1", "A1", "A2"], "X2": ["A1", "A2", "tie", "none"],               # s ＝ 3/4 と 1/2 → D_X ＞ 0、入れ替わりなし
         "M1": ["A1", "A2", "none", "none"], "M2": ["A1", "A1", "A2", "A2"],              # 1/2 と 1/2 → D_M ＝ 0
         "X0": ["none", "tie", "none", "none"], "X0_tr": ["none", "tie", "none", "none"],  # X0 は定まらない → Δ は N/A
         "X1_rerun": ["A1", "A1", "A1", "A2"]}
    ind = AN.individual(_with_outcomes(run, {n: E_PART + o for n, o in u.items()}))
    c = ind["contrasts"]
    assert (c["D_X"]["sign"], c["D_X"]["difference"]["num"], c["D_X"]["difference"]["den"]) == ("+", 1, 4) and c["D_X"]["in_population"]
    assert c["D_M"]["sign"] == "0" and c["D_M"]["in_population"]
    for name in ("Delta_1", "Delta_2"):
        assert c[name]["defined"] is False and c[name]["undefined_kind"] == "one_system" and c[name]["sign"] is None
    assert c["D_X_E"]["interval"] == "E" and c["D_X_E"]["sign"] == "0"                 # E は X1・X2 とも 1/2
    assert c["D_X"]["decided_diff"] == 2 and c["D_X"]["A1_diff"] == 2 and ind["flip"] is False
    assert ind["counts_U"]["X2"] == {"windows": 4, "decided": 2, "A1": 1, "A2": 1, "tie": 1, "none": 1}
    flipped = AN.individual(_with_outcomes(copy.deepcopy(run), {"X1": E_PART + ["A1"] * 4, "X2": E_PART + ["A2", "A2", "A1", "A2"]}))
    assert flipped["flip"] is True
    half = AN.individual(_with_outcomes(copy.deepcopy(run), {"X1": E_PART + ["A1", "A2", "none", "none"],
                                                             "X2": E_PART + ["A2"] * 4}))
    assert half["flip"] is False                                       # s ＝ 1/2 の系は入れ替わりに数えない


def test_swapping_the_labels_keeps_the_mirror_contrasts_and_exchanges_the_two_reference_contrasts() -> None:
    """README §3.2：A1・A2 の札を入れ替えると、X1 と X2、M1 と M2 が入れ替わり、D_X・D_M・D_X_E は同じ値、Δ^1 と Δ^2 は入れ替わる。"""
    run = measured(SYN[0])["run"]
    u = {"X1": ["A1", "A1", "A1", "A2"], "X2": ["A1", "A2", "tie", "none"], "M1": ["A1", "A2", "A2", "none"],
         "M2": ["A1", "A1", "A2", "A2"], "X0": ["A2", "A1", "none", "A1"], "X0_tr": ["A2", "A1", "none", "A1"],
         "X1_rerun": ["A1", "A1", "A1", "A2"]}
    swap = {"A1": "A2", "A2": "A1", "tie": "tie", "none": "none"}
    partner = {"X1": "X2", "X2": "X1", "M1": "M2", "M2": "M1", "X0": "X0", "X0_tr": "X0_tr", "X1_rerun": "X1_rerun"}
    before = AN.individual(_with_outcomes(copy.deepcopy(run), {n: E_PART + o for n, o in u.items() if n != "X1_rerun"}))["contrasts"]
    after = AN.individual(_with_outcomes(copy.deepcopy(run), {partner[n]: [swap[x] for x in E_PART + o]
                                                              for n, o in u.items() if n != "X1_rerun"}))["contrasts"]
    for name in ("D_X", "D_M", "D_X_E"):
        assert before[name]["difference"] == after[name]["difference"], name
    assert before["Delta_1"]["difference"] == after["Delta_2"]["difference"]
    assert before["Delta_2"]["difference"] == after["Delta_1"]["difference"]


def _fake(diff_x=None, **signs) -> dict:
    """判定・推定の算術の確かめ用の個体：対比 → 符号（None なら分母の外）。D_X の差の値と入れ替わりは diff_x で与える。"""
    out = {}
    for name in AN.CONTRASTS:
        s = signs.get(name)
        value = {"+": 0.25, "-": -0.25, "0": 0.0, None: None}[s]
        if name == "D_X" and diff_x is not None:
            value = diff_x
        out[name] = {"in_population": s is not None, "sign": s, "defined": s is not None,
                     "undefined_kind": None if s is not None else "one_system",
                     "difference": None if value is None else {"value": value}}
    return {"contrasts": out, "flip": signs.get("flip", False if signs.get("D_X") else None)}


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
    assert (table[10], table[50], table[100], table[150], table[200]) == (9, 33, 61, 88, 115)


def test_j_a_at_the_boundaries_in_both_directions_and_zeros_stay_in_the_denominator() -> None:
    few = AN.judge(_group(D_X=(9, 0, 0)))
    assert few["J_A"]["status"] == "inconclusive" and few["outcome"] == "inconclusive"     # m ＝ 9
    for plus in (True, False):
        def d(k, rest, plus=plus):
            return (k, rest, 0) if plus else (rest, k, 0)
        j = AN.judge(_group(D_X=d(9, 1)))                                                  # m ＝ 10、k₂ ＝ 9
        assert (j["J_A"]["m"], j["J_A"]["k2"], j["J_A"]["status"], j["J_A"]["direction"]) == \
            (10, 9, "established", "+" if plus else "-")
        assert j["outcome"] == ("plus" if plus else "minus")
        j = AN.judge(_group(D_X=d(8, 2)))
        assert (j["J_A"]["status"], j["J_A"]["direction"], j["outcome"]) == ("not_established", None, "not_established")
    zeros = AN.judge(_group(D_X=(9, 0, 3)))["J_A"]                                         # 0 を分母に残す：m ＝ 12、k₂ ＝ 10
    assert (zeros["m"], zeros["k2"], zeros["status"], zeros["counts"]) == (12, 10, "not_established", {"+": 9, "-": 0, "0": 3})
    assert zeros["interval"]["+"]["computed"] and zeros["interval"]["-"]["denominator"] == 12
    assert set(PROTOCOL["judgment"]["outcomes"]) - {"invalid"} == {"inconclusive", "not_established", "plus", "minus"}


def test_the_estimate_e_a_counts_changes_and_flips_without_a_threshold() -> None:
    rows = {"1": _fake(D_X="+", flip=True), "2": _fake(D_X="-", flip=False), "3": _fake(D_X="0", flip=False),
            "4": _fake(D_X="+", flip=False), "5": _fake()}
    rows["2"]["contrasts"]["D_X"]["difference"]["value"] = -0.5
    e = AN.estimate(rows)
    assert e["m"] == 4 and e["p_change"]["count"] == 3 and e["p_plus"]["count"] == 2 and e["p_minus"]["count"] == 1
    assert e["p_flip"]["count"] == 1 and e["p_flip"]["interval"]["denominator"] == 4
    assert e["abs_D_X"]["all"]["count"] == 4 and e["abs_D_X"]["changed"]["count"] == 3 and e["abs_D_X"]["changed"]["max"] == 0.5
    assert e["p_change"]["interval"]["computed"] and "threshold" not in json.dumps({k: v for k, v in e.items() if k != "note"})
    empty = AN.estimate({"1": _fake()})
    assert empty["m"] == 0 and empty["p_change"]["interval"]["computed"] is False and empty["abs_D_X"]["all"] is None


def test_cross_table_counts_the_nine_cells() -> None:
    rows = [_fake(D_X="+", D_M="+"), _fake(D_X="+", D_M="-"), _fake(D_X="0", D_M="0"), _fake(D_X="-"), _fake(D_M="+")]
    t = AN.cross_table(rows, "D_X", "D_M")
    assert t["in_both"] == 3 and t["cells"]["++"] == 1 and t["cells"]["+-"] == 1 and t["cells"]["00"] == 1
    assert t["only_D_X"] == 1 and t["only_D_M"] == 1 and len(t["cells"]) == 9


def test_clopper_pearson_known_values() -> None:
    lo, hi = AN.clopper_pearson(0, 10)
    assert lo == 0.0 and hi == pytest.approx(1 - 0.025 ** 0.1, abs=1e-9)
    lo, hi = AN.clopper_pearson(10, 10)
    assert hi == 1.0 and lo == pytest.approx(0.025 ** 0.1, abs=1e-9)
    lo, hi = AN.clopper_pearson(5, 10)
    assert lo == pytest.approx(0.187086, abs=1e-5) and hi == pytest.approx(0.812914, abs=1e-5)
    assert AN.interval(0, 0) == {"computed": False, "interval": None, "numerator": 0, "denominator": 0, "reason": "m = 0"}


def test_descriptive_controls_report_the_required_contrasts_and_the_undefined_tables() -> None:
    rows = {"1": _fake(D_X="+", D_M="+", Delta_1="-", Delta_2="0", D_X_E="+"), "2": _fake(D_X="-", Delta_1="+")}
    dc = AN.descriptive_controls(rows)
    assert set(dc["contrasts"]) == set(AN.MUST_REPORT)
    assert dc["contrasts"]["Delta_1"]["m"] == 2 and dc["contrasts"]["Delta_1"]["counts"] == {"+": 1, "-": 1, "0": 0}
    assert dc["contrasts"]["D_M"]["m"] == 1 and dc["contrasts"]["D_M"]["difference"]["count"] == 1
    assert set(dc["cross_tables"]) == {"D_X|D_M", "Delta_1|Delta_2"}
    assert dc["undefined"]["D_M"]["one_system"] == ["2"] and dc["undefined"]["D_X"]["one_system"] == []


def test_five_numbers() -> None:
    assert AN.five_numbers([]) is None and AN.five_numbers([3])["median"] == 3
    assert AN.five_numbers([1, 2, 3, 4, 5]) == {"count": 5, "min": 1, "q1": 2.0, "median": 3.0, "q3": 4.0, "max": 5}


def test_the_analysis_of_the_synthetic_individuals_runs_through_and_the_recheck_agrees() -> None:
    """合成の個体の解析が最後まで通る。標準のライブラリだけの独立の検算（recheck.py）が、report と一つずつ一致する。値は表示しない。"""
    runs = {s: measured(s) for s in SYN}
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=[])
    assert report["valid"] is True and set(report) == {"mode", "valid", "O1", "gate_declaration_sha256", "judgment", "estimate",
                                                       "descriptive_controls", "individuals", "auxiliary"}
    j = report["judgment"]
    assert j["J_A"]["status"] in ("inconclusive", "established", "not_established") and j["outcome"] in PROTOCOL["judgment"]["outcomes"]
    assert j["J_A"]["interval"]["+"]["computed"] is (j["J_A"]["m"] >= 1)
    assert report["estimate"]["m"] == j["J_A"]["m"]
    assert set(report["auxiliary"]) == {"R1", "R2", "R3", "R4", "R5", "R6", "R7", "R9"}
    assert report["auxiliary"]["R4"]["pair_sum_equals_w_max_exactly"] is True
    assert all(report["auxiliary"]["R7"][n]["consequence_reservations_total"] == 0 for n in M.SYSTEMS)
    result = RC.recheck(runs, json.loads(json.dumps(report)))
    assert result["mismatches"] == [] and result["checks"] > 500


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
    for tamper in (lambda rep, raw: rep["judgment"]["J_A"]["counts"].update({"+": rep["judgment"]["J_A"]["counts"]["+"] + 1}),
                   lambda rep, raw: rep["judgment"].update(outcome="plus" if rep["judgment"]["outcome"] != "plus" else "minus"),
                   lambda rep, raw: rep["estimate"]["p_flip"].update(count=rep["estimate"]["p_flip"]["count"] + 1),
                   lambda rep, raw: rep["individuals"][k]["contrasts"]["D_M"].update(sign="?"),
                   lambda rep, raw: rep["individuals"][k].update(flip="?"),
                   lambda rep, raw: raw[SYN[1]]["run"]["systems"]["X2"]["pulse_weights"][3][1].__setitem__(0, 0.0011),
                   lambda rep, raw: raw[SYN[1]]["run"]["systems"]["X0_tr"]["layer_b"].append([9, "d", "s1", "A1"]),
                   lambda rep, raw: raw[SYN[2]]["run"]["pulse_0"]["sigma_T1"]["M1"]["connections"][min(raw[SYN[2]]["run"]["W_0"])]
                   .update(weight=0.001)):
        rep, raw = copy.deepcopy(report), copy.deepcopy(runs)
        tamper(rep, raw)
        assert RC.recheck(raw, rep)["mismatches"]


# ---- CT-40-10 protocol の写しと、確定済みの事前登録の結び付き ------------------------------------------------

def _without(meta: dict, key: str) -> None:
    del meta[key]


def _alter_protocol(path: tuple, value):
    def edit(meta: dict) -> None:
        node = meta["protocol"]
        for k in path[:-1]:
            node = node[k]
        node[path[-1]] = value
    return edit


PROTOCOL_TAMPERS = {
    "no_protocol": lambda m: _without(m, "protocol"),
    "no_sha256": lambda m: _without(m, "protocol_sha256"),
    "sha256_changed": lambda m: m.update(protocol_sha256="0" * 64),
    "alpha_changed": _alter_protocol(("judgment", "J_A", "alpha", "per_direction"), 0.05),
    "min_population_changed": _alter_protocol(("judgment", "J_A", "min_population"), 9),
    "k2_table_changed": _alter_protocol(("judgment", "k2_of_m", "100"), 60),
    "seeds_changed": _alter_protocol(("seeds", "last"), 33250),
    "timeline_changed": _alter_protocol(("timeline", "runs_to"), 2071),
    "respond_changed": _alter_protocol(("world", "respond"), True),
    # 以下は PREREGISTERED で個別に照らさない欄。写しの中身全体のハッシュで見つける
    "J_A_rule_changed": _alter_protocol(("judgment", "J_A", "rule"), "plus if count(plus) > m / 2"),
    "negative_reading_changed": _alter_protocol(("judgment", "negative_reading"), "a configuration limit"),
    "contrast_swapped": _alter_protocol(("quantities", "contrasts", "D_X"), ["X2", "X1"]),
    "intervention_changed": _alter_protocol(("intervention_values", "X1", "C_to_source1"), "w0"),
    "operation_check_dropped": _alter_protocol(("operation_checks",), ["O1", "O2", "O3"]),
}
UNCOMPARED = ("J_A_rule_changed", "negative_reading_changed", "contrast_swapped", "intervention_changed", "operation_check_dropped")


def test_the_preregistered_values_in_the_recheck_are_the_protocol_values() -> None:
    """recheck.py が書き起こした値（PREREGISTERED・TABLE）が、確定済みの protocol.yaml の値と同じ。正本の写しは結び付きを通る。"""
    pr, j, tl, br = RC.PREREGISTERED, PROTOCOL["judgment"], PROTOCOL["timeline"], PROTOCOL["brain"]
    assert pr["experiment"] == PROTOCOL["experiment"]
    assert pr["alpha_per_direction"] == Fraction(str(j["J_A"]["alpha"]["per_direction"])) == Fraction(1, 40)
    assert pr["alpha_two_sided"] == Fraction(str(j["J_A"]["alpha"]["two_sided"]))
    assert pr["min_population"] == j["J_A"]["min_population"]
    assert pr["k2_range"] == (min(j["k2_of_m"]), max(j["k2_of_m"]))
    assert (pr["lead_in_windows"], pr["trial_windows"], pr["lead_in_pulses"], pr["runs_to"]) == \
        (tl["lead_in_E"]["windows"], tl["trial_U"]["windows"], tl["lead_in_E"]["pulses"], tl["runs_to"])
    assert (pr["w_min"], pr["w_max"], pr["w0"]) == (br["w_min"], br["w_max"], br["initial_weight_w0"])
    assert pr["respond"] is PROTOCOL["world"]["respond"] is False
    assert all(pr[k] == PROTOCOL[k] for k in ("seeds", "smoke_seeds", "synthetic_seeds"))
    assert pr["formal_plan"] == dataclasses.asdict(FORMAL)
    for n in ("X1", "X2", "M1", "M2", "X0_tr"):
        assert RC.TABLE[n] == tuple(AN.VALUES[n][k] for k in M.ROLE_KEYS), n
    assert RC.TABLE["X0"] == (W0,) * 4 and RC.TABLE["X1_rerun"] == RC.TABLE["X1"]
    assert RC.PROTOCOL_FILE == EXP / "protocol.yaml"
    assert RC._preregistered_values(json.loads(json.dumps(PROTOCOL))) == []
    assert RC.protocol_problems({s: measured(s) for s in SYN[:2]}) == []


def test_the_recheck_holds_the_fixed_hashes_of_the_preregistered_protocol() -> None:
    """recheck.py の固定のハッシュが、確定済み v0.2 の protocol.yaml（このリポジトリの正本）から計算し直した値と同じ。"""
    stored = json.loads(json.dumps(PROTOCOL))                               # raw の meta と同じ形
    assert RC.canonical_protocol_sha256(stored) == RC.PROTOCOL_JSON_SHA256
    assert hashlib.sha256((EXP / "protocol.yaml").read_bytes()).hexdigest() == RC.PROTOCOL_FILE_SHA256 == AN.PROTOCOL_SHA256
    canonical = json.dumps(stored, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == RC.PROTOCOL_JSON_SHA256   # 正規化の仕方を独立に書き直しても同じ
    assert RC.PROTOCOL_JSON_SHA256 == "d68f7a36b2761435601e4a0f9e1c6d41e4eebe4cf9953768fb9a899d0491826d"
    assert RC.PROTOCOL_FILE_SHA256 == "cfb7deae7764cc748ce9839671bf3ff6d0dd4f398cd942fa64eca93010c7120d"


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
    assert before["structure"] == "ok" and before["O12"] == "fail"           # 形は通る（O12 は合成の seed なので fail）
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
    runs = {s: AN.read_raw(R.G.seed_dir(out, s) / R.G.RAW) for s in SYN[:2]}
    (out / AN.REPORT).write_text(json.dumps(AN.analyze_runs(runs, "synthetic", SMALL, o1=[])), encoding="utf-8")
    assert RC.recheck_directory(out)["mismatches"] == []
    start = R.G.seed_dir(out, SYN[1]) / R.G.START
    start.write_text(json.dumps(json.loads(start.read_text(encoding="utf-8")) | {"protocol_sha256": "1" * 64}), encoding="utf-8")
    assert any("開始の記録" in m for m in RC.recheck_directory(out)["mismatches"])


def test_an_invalid_individual_or_a_failed_o1_blocks_the_judgment_and_the_estimate() -> None:
    runs = {s: measured(s) for s in SYN[:2]}
    runs[SYN[1]]["run"]["systems"]["X1"]["pulse_weights"][0][1][0] = 0.0011
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=[])
    assert report["valid"] is False and report["judgment"] is None and report["estimate"] is None and "individuals" not in report
    assert list(report["failed_checks"]) == [str(SYN[1])] and "O6" in report["failed_checks"][str(SYN[1])]
    report = AN.analyze_runs({SYN[0]: measured(SYN[0])}, "synthetic", SMALL, o1=["x"])
    assert report["valid"] is False and report["judgment"] is None and report["O1"]["status"] == "fail"


# ---- 操作の確認が、記録の食い違いを見つける（structure・O2・O3・O11・O12） ---------------------------------

def test_structure_detects_extra_fields_and_wrong_roles() -> None:
    s = SYN[0]
    for tamper in (lambda d: d["run"].update(judgment={}), lambda d: d.update(extra=1),
                   lambda d: d["run"]["systems"]["X1"].update(s_U=0.5), lambda d: d["run"]["systems"].pop("X0_tr"),
                   lambda d: d["run"]["roles"].update(cue=d["run"]["roles"]["source1"]),
                   lambda d: d["run"]["W_0"].update({min(d["run"]["W_0"]): 0.004}),
                   lambda d: d["run"].update(seed=s + 1), lambda d: d["meta"].update(manifest={}),
                   lambda d: d["run"]["plan"].update(e_windows=3),
                   lambda d: d["run"]["pulse_0"]["sigma_T1"].pop("M2"),
                   lambda d: d["run"]["systems"]["X1_rerun"].update(pulse_weights=[]),
                   lambda d: d["run"]["systems"]["X2"]["audit"].pop("ok")):
        data = measured(s)
        tamper(data)
        assert "structure" in failures(data, s)


def test_o2_detects_a_different_gate_set_or_a_responding_world() -> None:
    s = SYN[0]
    for tamper in (lambda d: d["meta"]["gate"].update(sha256="0" * 64),
                   lambda d: d["meta"]["gate"]["declaration"]["schedule"].update(window_length_W=18),
                   lambda d: d["meta"].pop("gate"),
                   lambda d: d["run"]["systems"]["X2"]["world_end"]["rule"].update(delay=3),
                   lambda d: d["run"]["systems"]["M1"]["world_end"]["rule"].update(rule_c="A2"),
                   lambda d: d["run"]["systems"]["X0"]["world_end"]["rule"].update(respond=True),
                   lambda d: d["run"]["systems"]["X1"]["layer_a"][2].update(close=d["run"]["systems"]["X1"]["layer_a"][2]["close"] + 1),
                   lambda d: d["run"]["systems"]["X1"]["world_end"]["reserved"][0].__setitem__(3, 40),
                   lambda d: d["run"]["systems"]["X1_rerun"].update(pulse_end=SMALL.end - 1),
                   lambda d: d["run"]["pulse_0"]["sigma_T2"]["X1"]["exit"]["windows"][0].__setitem__(2, 60)):
        data = measured(s)
        tamper(data)
        assert "O2" in failures(data, s)
    formal = measured(s)
    formal["meta"]["mode"] = "formal"
    assert AN.check_seed(formal, "formal", s, SMALL)["structure"]            # 本番では小さい Plan を使えない


def test_o3_detects_a_broken_audit() -> None:
    s = decided_seed()
    for tamper in (lambda r: r["systems"]["X1"]["layer_b"].append([9, "d-x", r["roles"]["source1"], "A1"]),
                   lambda r: r["systems"]["X1"]["layer_b"].pop(),
                   lambda r: r["systems"]["X2"]["layer_a"].pop(),
                   lambda r: r["systems"]["X1"]["delta_log"].pop(),
                   lambda r: r["systems"]["X1_rerun"]["audit"].update(ok=False),
                   lambda r: r["systems"]["M1"]["audit"].update(carried_over_windows=[8]),
                   lambda r: next(x for x in r["systems"]["X1"]["layer_a"] if x["emitted"]).update(emitted=False)):
        data = measured(s)
        tamper(data["run"])
        assert "O3" in failures(data, s)
    data = measured(s)
    lb = data["run"]["systems"]["X1"]["layer_b"]
    if len(lb) >= 2:
        lb[1][1] = lb[0][1]                                                    # Delta の識別子の重複
        assert "O3" in failures(data, s)


def test_o11_detects_inconsistent_layer_a_fields() -> None:
    s = decided_seed()

    def decided(r, n="X1"):
        return next(x for x in r["systems"][n]["layer_a"] if x["outcome"] in A.ACTION_IDS)
    for tamper in (lambda r: decided(r).update(outcome="A2" if decided(r)["outcome"] == "A1" else "A1"),
                   lambda r: decided(r).update(emit_pulse=decided(r)["emit_pulse"] + 1),
                   lambda r: decided(r).update(decision_pulse=decided(r)["open"] - 1),
                   lambda r: decided(r).update(winner_unit=r["roles"]["cue"]),
                   lambda r: r["systems"]["X0"]["layer_a"][0].update(outcome="other"),
                   lambda r: r["systems"]["M2"]["layer_a"][1].update(open=1)):
        data = measured(s)
        tamper(data["run"])
        assert "O11" in failures(data, s)
    problems = AN.layer_a_problems([{"window": 1, "open": 3, "close": 5, "outcome": "tie", "decision_pulse": 4, "winner_unit": "s1",
                                     "action": None, "emit_pulse": None, "emitted": False}], [(1, 3, 5)],
                                   {"source1": "s1", "source2": "s2"})
    assert problems == ["窓 1：結末と記録の欄が合わない"]


def test_o12_rejects_seeds_outside_the_range_or_seen() -> None:
    assert AN.check_seed(measured(SYN[0]), "synthetic", SYN[0], SMALL)["O12"] == []
    for seed in (31001, 32001, 32301, 30201, 33001):
        out: list[str] = []
        AN._o12(seed, "synthetic", out)
        assert out
    out = []
    AN._o12(32001, "formal", out)
    assert len(out) == 2                                                       # 範囲の外で、かつ 0039 で走らせた seed


def test_meta_blind_must_match_the_mode() -> None:
    s = SYN[0]
    data = measured(s)
    data["meta"]["blind"] = "no"
    assert "structure" in failures(data, s)
    assert AN.check_seed(dict(measured(s), meta=dict(measured(s)["meta"], blind=True)), "formal", s, SMALL)["structure"]


# ---- 一度限りの実行（guard と run.execute。dummy の計算。0039 と同じ） ------------------------------------

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
        R.execute("formal", [33001], tmp_path / "o", repo, None, runner=_dummy, executor_factory=SerialExecutor)
    assert not (tmp_path / "o").exists()
    assert R.OUT_DIR == Path("data/experiments/0040") and R.MAX_WORKERS == 2
    assert list(R.allowed_seeds("formal")) == list(range(33001, 33201))
    assert list(R.allowed_seeds("smoke")) == list(range(33201, 33207))


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
    assert report["valid"] is True and report["judgment"]["J_A"]["status"] == "inconclusive"   # 3 個体なので m ＜ 10
    assert report["judgment"]["outcome"] == "inconclusive"
    (out / AN.REPORT).write_text(json.dumps(report), encoding="utf-8")
    assert RC.recheck_directory(out)["mismatches"] == []                       # 保存したファイルからの独立の検算


# ---- smoke の盲検：現象の数値を保存しない（0039 と同じ） -------------------------------------------------

FORBIDDEN_KEYS = ((AN.RUN_KEYS - {"seed", "plan", "roles"}) | AN.END_KEYS | AN.PULSE_0_KEYS
                  | set().union(*AN.SYSTEM_KEYS.values()) | JUDGMENT_KEYS
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
    for tamper, check in ((lambda r: r["systems"]["X2"]["pulse_weights"][3][1].__setitem__(0, 0.0011), "O6"),
                          (lambda r: r["systems"]["X0_tr"].update(sigma_end_sha256="0" * 64), "O8"),
                          (lambda r: r["systems"]["M1"]["first_firing"]["sigma"]["units"][r["roles"]["cue"]].update(activity=9.0),
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
    missing["blind"]["checks"].pop("O11")
    assert AN.check_blinded(missing, s, "smoke") == {k: "fail" for k in AN.CHECK_NAMES}
    no_gate = copy.deepcopy(rec)
    no_gate["meta"]["gate"]["sha256"] = "0" * 64
    assert AN.check_blinded(no_gate, s, "smoke") == {k: "fail" for k in AN.CHECK_NAMES}


def test_smoke_must_be_blind_and_formal_must_not(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    commit = _git(repo, "rev-parse", "HEAD")
    for mode, seeds, kw in (("smoke", [33201], {"blind": False}), ("formal", [33001], {"blind": True}),
                            ("smoke", [33201], {"check_plan": SMALL})):
        out = tmp_path / f"o_{mode}_{min(kw)}"
        with pytest.raises(R.G.GuardError):
            R.execute(mode, seeds, out, repo, commit, runner=_dummy, executor_factory=SerialExecutor, **kw)
        assert not out.exists()


# ---- O1 の証拠（0039 と同じ） ---------------------------------------------------------------------------

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
    assert len(AN.CONTRACT_TESTS) == 4 and AN.o1_check(out, commit) == []
    R.record_contract_tests(repo, out, commit, run=lambda *a, **k: pytest.fail("走らせ直さない"))


def _never(*a, **k):
    raise AssertionError("O1 が成り立たないのに、契約テストの実行か seed の計算に進んだ")


@pytest.mark.parametrize("name,tamper", [
    ("終了コード", lambda r: r.update(exit_code=1)),
    ("結果の行", lambda r: r.update(summary="1 failed, 498 passed in 50.0s")),
    ("テストのファイルの SHA-256", lambda r: r["test_files_sha256"].update({AN.CONTRACT_TESTS[3]: "0" * 64})),
    ("走らせたコマンド", lambda r: r.update(command=["python", "-m", "pytest", "-q", *AN.CONTRACT_TESTS[:3]])),
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
