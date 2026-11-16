"""実験 0040 の道具の契約テスト（事前登録 v0.3 の README・protocol.yaml。v0.2 は #184 merge `9a8651a`。README §14 の CT-40-1〜10）。

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
import shutil
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
    assert set(rec) == AN.SYSTEM_KEYS[M.RERUN] and "pulse_weights" not in rec
    src = inspect.getsource(M.measure_seed)
    assert "rerun = build_system(plan, seed)" in src                      # log を渡さない ＝ AS2b の道具の既定のログ
    assert "_pulse_0(rerun, RERUN, values, six, steps, None)" in src and "A.advance_to(rerun.app, end)" in src
    assert "_advance_each_pulse(rerun" not in src                         # X1′ は走らせている間に状態を読まない（観測の区分。v0.3）
    p0 = measured(SYN[0])["run"]["pulse_0"]
    assert all(M.RERUN not in p0[f"sigma_{t}"] for t in ("T0", "T1", "T2"))


def test_ct40_4_the_end_sigma_is_kept_whole_and_compared_by_value() -> None:
    """v0.3：7 系とも終わりの Σ を値の全体で保存する。O8・O9 は値の完全な一致が主で、SHA-256 は補助。正規化は鍵の順に依らない。"""
    run = measured(decided_seed())["run"]
    for n in M.SYSTEMS:
        end = run["systems"][n]["sigma_end"]
        assert end["pulse"] == SMALL.end and M.sigma_sha256(end) == run["systems"][n]["sigma_end_sha256"]
        assert set(end) == {"pulse", "clock", "units", "connections", "drives", "deltas", "issuer", "runtime", "world",
                            "interventions", "exit"}                     # 来歴のログを含まない
        shuffled = json.loads(json.dumps(dict(reversed(list(end.items())))))
        assert M.sigma_sha256(shuffled) == M.sigma_sha256(end) == RC.hashlib.sha256(
            json.dumps(end, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()
    for a, b in (("X0", "X0_tr"), ("X1", "X1_rerun")):
        assert AS1.sigma_diff(run["systems"][a]["sigma_end"], run["systems"][b]["sigma_end"]) == []
    assert AS1.sigma_diff(run["systems"]["X1"]["sigma_end"], run["systems"]["X2"]["sigma_end"])     # 値の違う系は違う


def _same_sha_value_change(r, name: str) -> None:
    """終わりの Σ の値だけを変え、SHA-256 の欄は元のまま残す（値の照合が主であることの確かめ）。"""
    r["systems"][name]["sigma_end"]["units"][r["roles"]["cue"]]["activity"] = 9.0


def test_o8_and_o9_detect_a_broken_identity_or_rerun() -> None:
    s = decided_seed()
    for tamper, check in ((lambda r: r["systems"]["X0_tr"].update(sigma_end_sha256="0" * 64), "O8"),
                          (lambda r: r["systems"]["X0_tr"]["activity"].pop(), "O8"),
                          (lambda r: _same_sha_value_change(r, "X0_tr"), "O8"),
                          (lambda r: _same_sha_value_change(r, "X0"), "O8"),
                          (lambda r: r["systems"]["X0_tr"]["history"].append([0, "x", []]), "O8"),
                          (lambda r: r["systems"]["X1_rerun"]["activity"].pop(), "O9"),
                          (lambda r: _same_sha_value_change(r, "X1_rerun"), "O9"),
                          (lambda r: r["systems"]["X1_rerun"]["sigma_end"].update(pulse=SMALL.end - 1), "O9"),
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
            assert min(p for p, _u in run["systems"][n]["activity"]) == t1
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


def test_o10_is_the_limited_check_on_the_saved_records_and_detects_tampering() -> None:
    """O10（v0.3）：保存した記録から、t₁ の一致、t₁ までの発火・層 A の一致、最初に分かれた Pulse が t₁ ＋ 1 以後を確かめる。
    Unit の内部の状態は O10 では確かめない（raw に t₁ の Σ を入れない。CT-40-5 の合成の系で直接確かめる）。"""
    s = diverging_seed()
    run = measured(s)["run"]
    assert all(set(run["systems"][n]) == AN.SYSTEM_KEYS[n] for n in M.SYSTEMS)
    assert "sigma" not in inspect.getsource(AN._o10).replace("sigma_end", "")
    t1 = _first_firing(run)
    other = next(u for u in (run["roles"]["cue"], run["roles"]["source1"], run["roles"]["source2"])
                 if [t1, u] not in run["systems"]["M1"]["activity"])
    for tamper in (lambda r: r["systems"]["X2"]["activity"].insert(0, [t1 - 1, r["roles"]["cue"]]),
                   lambda r: r["systems"]["M1"]["activity"].insert(0, [t1, other]),
                   lambda r: r["systems"]["X1"]["layer_a"][0].update(decision_pulse=t1),
                   lambda r: r["systems"]["M2"]["activity"].__setitem__(0, [t1, "zz"])):
        changed = measured(s)
        tamper(changed["run"])
        assert "O10" in failures(changed, s)


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
                   lambda rep, raw: raw[SYN[3]]["run"]["systems"]["X1_rerun"]["sigma_end"]["units"][
                       raw[SYN[3]]["run"]["roles"]["cue"]].update(activity=9.0),
                   lambda rep, raw: raw[SYN[2]]["run"]["pulse_0"]["sigma_T1"]["M1"]["connections"][min(raw[SYN[2]]["run"]["W_0"])]
                   .update(weight=0.001)):
        rep, raw = copy.deepcopy(report), copy.deepcopy(runs)
        tamper(rep, raw)
        assert RC.recheck(raw, rep)["mismatches"]


# ---- CT-40-9・10 独立の検算：report のすべての欄（PR #185 のレビュー 5924138620 の修正必須 1） -----------------------

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


@functools.cache
def _analyzed() -> str:
    """合成の 3 個体（SMALL）の解析の report（解析の main と同じく measurement_commit を書き足した形。JSON を通す）。"""
    runs = {s: measured(s) for s in SYN[:3]}
    return json.dumps(AN.analyze_runs(runs, "synthetic", SMALL, o1=[]) | {"measurement_commit": COMMIT})


def test_the_recheck_rebuilds_the_whole_report_and_compares_every_field() -> None:
    """raw から report の全体を組み立て直し、すべての葉を照合する。report のどの葉の値を変えても、どの欄を消しても足しても、
    照合が失敗する（合成の個体の値は表示しない。失敗の文は場所だけ）。"""
    runs = {s: measured(s) for s in SYN[:3]}
    report = json.loads(_analyzed())
    mine = RC.expected_report(runs, COMMIT)
    checks, found = RC.compare(mine, report)
    paths = list(_leaves(report))
    scalars = [p for p in paths if not isinstance(_at(report, p), (dict, list))]
    assert found == [] and checks == len(scalars) > 2000                     # すべての葉を比べている
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
    assert RC._loose("report.judgment.J_A.interval.+.interval[0]") and RC._loose("report.auxiliary.R1.S1_prime.E_S")
    assert not RC._loose("report.estimate.p_change.proportion") and not RC._loose("report.individuals.33301.birth.cue.margin_g")
    report = json.loads(_analyzed())
    mine = RC.expected_report({s: measured(s) for s in SYN[:3]}, COMMIT)
    margin = report["individuals"][str(SYN[0])]["birth"]["cue"]
    margin["margin_g"] += 1e-12                                              # 書き方の同じ数は、わずかな違いも見つける
    assert RC.compare(mine, report)[1] == [f"report.individuals.{SYN[0]}.birth.cue.margin_g"]
    margin["margin_g"] -= 1e-12
    report["valid"] = 1                                                      # 真偽と数を取り違えない
    assert RC.compare(mine, report)[1] == ["report.valid"]


TARGETS = [("estimate", "p_change", "proportion"), ("estimate", "p_flip", "proportion"), ("estimate", "abs_D_X"),
           ("descriptive_controls", "contrasts", "D_M", "difference"), ("descriptive_controls", "contrasts", "Delta_1", "proportion"),
           ("descriptive_controls", "contrasts", "Delta_2", "interval"), ("descriptive_controls", "contrasts", "D_X_E", "difference"),
           ("descriptive_controls", "cross_tables"), ("descriptive_controls", "undefined"),
           ("auxiliary", "R1", "never_diverged_X1_X2_in_J_A_population"), ("auxiliary", "R1", "S1_prime", "E_S"),
           ("auxiliary", "R2"), ("auxiliary", "R3"), ("auxiliary", "R4", "T2_values_by_system"),
           ("auxiliary", "R4", "end_values_X1_rerun"), ("auxiliary", "R4", "pulse_weights"), ("auxiliary", "R5"),
           ("auxiliary", "R6"), ("auxiliary", "R7"), ("auxiliary", "R9"),
           ("individuals", None, "firing"), ("individuals", None, "pre_window_firing_U"), ("individuals", None, "world"),
           ("individuals", None, "weights"), ("individuals", None, "pair_sums"), ("individuals", None, "first_divergence"),
           ("individuals", None, "birth"), ("individuals", None, "roles"), ("individuals", None, "counts_U"),
           ("individuals", None, "contrasts", "Delta_2", "a"), ("mode",), ("O1",), ("gate_declaration_sha256",),
           ("measurement_commit",)]


@pytest.mark.parametrize("target", TARGETS, ids=lambda t: ".".join(str(x) for x in t if x))
def test_the_recheck_fails_when_a_field_it_did_not_check_before_is_changed(target) -> None:
    """これまで独立の照合がなかった欄（E_A の割合、記述の対照の差の分布、R2〜R7・R9、個体の発火・世界・重みなど）を変えると、
    recheck が失敗する。"""
    runs = {s: measured(s) for s in SYN[:3]}
    report = json.loads(_analyzed())
    assert RC.recheck(runs, report, COMMIT)["mismatches"] == []
    prefix = tuple(str(SYN[1]) if k is None else k for k in target)
    path = prefix + next(_leaves(_at(report, prefix)))
    parent = _at(report, path[:-1])
    parent[path[-1]] = _changed(parent[path[-1]])
    found = RC.recheck(runs, report, COMMIT)["mismatches"]
    assert found and all(m.startswith("report.") for m in found)


def test_a_raw_change_that_no_operation_check_sees_still_fails_the_report_comparison() -> None:
    runs = {s: measured(s) for s in SYN[:3]}
    report = json.loads(_analyzed())
    roles = runs[SYN[2]]["run"]["roles"]
    runs[SYN[2]]["run"]["birth_units"][roles["cue"]]["dynamics"]["threshold"] += 0.001
    found = RC.recheck(runs, report, COMMIT)["mismatches"]
    assert f"report.individuals.{SYN[2]}.birth.cue.threshold" in found and all(m.startswith("report.") for m in found)


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
    gate = PROTOCOL["inherited_gate_set"]
    assert (RC.GATE_FILE, RC.GATE_SHA256) == (gate["declaration"], gate["sha256"]) and RC.GATE_SHA256 == AN.GATE_SHA256
    assert RC.gate_problems({s: measured(s) for s in SYN[:2]}) == [] and RC.REPO_ROOT == ROOT
    assert RC.PREREGISTERED["kind"] == PROTOCOL["kind"]
    # 書き起こした名前・組が、道具と同じ（照合の相手を取り違えない）
    assert (RC.START, RC.FINISH, RC.RAW, RC.SEEDS_DIR) == (R.G.START, R.G.FINISH, R.G.RAW, R.G.SEEDS_DIR)
    assert (RC.REPORT, RC.O1_FILE, RC.O1_KEYS, RC.CONTRACT_TESTS) == (AN.REPORT, AN.O1_FILE, AN.O1_KEYS, AN.CONTRACT_TESTS)
    assert (RC.SYSTEMS, RC.RECORDED, RC.RERUN, RC.PAIRS) == (list(M.SYSTEMS), list(M.RECORDED), M.RERUN, list(M.PAIRS))
    assert {k: v[:2] for k, v in RC.CONTRASTS.items()} == AN.CONTRASTS and RC.TABLES == list(AN.MUST_REPORT)
    assert RC.CROSS == list(AN.CROSS_TABLES)


def test_the_recheck_holds_the_fixed_hashes_of_the_preregistered_protocol() -> None:
    """recheck.py の固定のハッシュが、事前登録 v0.3 の protocol.yaml（このリポジトリの正本）から計算し直した値と同じ。"""
    stored = json.loads(json.dumps(PROTOCOL))                               # raw の meta と同じ形
    assert RC.canonical_protocol_sha256(stored) == RC.PROTOCOL_JSON_SHA256
    assert hashlib.sha256((EXP / "protocol.yaml").read_bytes()).hexdigest() == RC.PROTOCOL_FILE_SHA256 == AN.PROTOCOL_SHA256
    canonical = json.dumps(stored, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(canonical).hexdigest() == RC.PROTOCOL_JSON_SHA256   # 正規化の仕方を独立に書き直しても同じ
    assert RC.PROTOCOL_JSON_SHA256 == "5e4fa28eb3473748afc392bfd05064c50c1c931218ccae063fc021d74c57af87"     # v0.3
    assert RC.PROTOCOL_FILE_SHA256 == "62c15db4340eac25b78fd4cff31e90983fd13850f914a9dc36ec5616fa787fda"


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
    _complete(out, SYN[:2])
    assert RC.recheck_directory(out)["mismatches"] == []
    start = R.G.seed_dir(out, SYN[1]) / R.G.START
    start.write_text(json.dumps(json.loads(start.read_text(encoding="utf-8")) | {"protocol_sha256": "1" * 64}), encoding="utf-8")
    assert any("開始の記録" in m for m in RC.recheck_directory(out)["mismatches"])


# ---- CT-40-10 独立の検算：測定の来歴と全件性（PR #185 のレビュー 5924138620 の修正必須 2） ------------------------

DIR_SEEDS = SYN[:3]


def _o1_record(commit: str) -> dict:
    """run.py の record_contract_tests が書く O1 の記録と同じ形（テストのファイルの SHA-256 は、このリポジトリのもの）。"""
    return {"measurement_commit": commit, "command": ["python", "-m", "pytest", "-q", *AN.CONTRACT_TESTS], "exit_code": 0,
            "summary": "551 passed in 250.00s", "test_files_sha256": {f: R.G.sha256_file(ROOT / f) for f in AN.CONTRACT_TESTS},
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
    # フォルダ
    "renamed_folder": lambda o: R.G.seed_dir(o, _B).rename(R.G.seed_dir(o, 33309)),
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
    "o1_summary": lambda o: _json_edit(o / AN.O1_FILE, lambda r: r.update(summary="1 failed, 550 passed in 250.00s")),
    "o1_command": lambda o: _json_edit(o / AN.O1_FILE, lambda r: r.update(command=r["command"][:-1])),
    "o1_test_file": lambda o: _json_edit(o / AN.O1_FILE, lambda r: r["test_files_sha256"].update({AN.CONTRACT_TESTS[3]: "0" * 64})),
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
    formal = list(range(33001, 33201))
    assert RC.seed_set_problems("formal", formal) == []
    assert RC.seed_set_problems("formal", formal[:57] + formal[58:])                 # 欠け
    assert RC.seed_set_problems("formal", formal + [33201])                           # 範囲の外（smoke の seed）
    assert RC.seed_set_problems("formal", formal + [33001])                           # 重複
    assert RC.seed_set_problems("formal", [*formal[:-1], 32399])                       # 0039 の seed（欠けと範囲の外）
    assert RC.seed_set_problems("synthetic", SYN) == []
    assert RC.seed_set_problems("synthetic", [33001]) and RC.seed_set_problems("synthetic", [])
    assert RC.seed_set_problems("smoke", [33201]) and RC.seed_set_problems(None, SYN)
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
    assert _complete(out, seeds) == report | {"measurement_commit": records["measurement_commit"]}
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
                          (lambda r: r["systems"]["M1"]["activity"].insert(0, [1, "zz"]), "O10")):
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
