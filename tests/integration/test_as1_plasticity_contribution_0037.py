"""実験 0037 の道具の契約テスト（確定した事前登録 v0.2 の README・protocol.yaml、#168 merge `1c71f3c`）。

本番の seed（30001〜30100）・smoke の seed（30101〜30106）は使わない（実行もしない）。0034〜0036 の seed・raw（27001〜29299）も
使わない。合成の契約テスト専用の範囲（30201〜30299）だけを使う。合成の個体は、本番と同じ道具（measure.measure_seed）・同じ式で、
区間だけを小さくした Plan（SMALL：E ＝ [1, 180]、U ＝ [181, 240]、M の記録の Pulse 60・120・180）か、構成の条件
（下の「構成」）から決まる Plan で、実物の runtime を通して作る。結果を見て Plan・seed を選んでいない（seed は範囲の最初から順に、
構成の条件だけで決定的に選ぶ）。テストは操作の確認・記録の形・介入の部品の決まり方・Runtime の順序・判定の算術だけを確かめ、
合成の個体の判定の量（I_U の一致・P_i・J_C・区間・対照の数）の値を表示も判定もしない。

構成（README §14 の契約テストの要件）：
- 持ち越し・適格外 (b)：M の最初の意図の Pulse を P_E にする（その結果は P_E ＋ 1 に届く）
- n_E(M) ＝ 1：M の最初の意図の Pulse ＋ 1 を P_E にする
- 適格外 (a)・命題 Q2-4：SMALL の E で源が一度も発火しない最初の個体
- 構造上の恒等（適格）：源の最初の意図の Pulse が、6 本の重みが最初に変わる Pulse より 2 以上前の最初の個体で、重みが最初に
  変わる Pulse の一つ前を P_E にする（源の結果を E の中で 1 度以上受け取り、W_M ＝ W_0 のまま）
- SE-6 の Runtime の順序：AS1 の道具を直接使い、境界で 1 本の重みだけを大きく替えた複製（契約テストだけの値）

使った合成の seed（PR に開示）：30201〜30210（SMALL）、30221〜30226（一度限りの実行・盲検の契約。dummy の計算と SMALL）、
30299（本番の Plan で実物の runtime を通す確かめ）、構成の条件で選んだ個体（30201〜30299 の最初から順。どれになったかは
テストの中で決まり、PR に記す）。
"""

import copy
import functools
import gzip
import importlib.util
import inspect
import json
import re
import subprocess
from concurrent.futures import Future
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments" / "0037_as1_plasticity_contribution"
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = _load("measure_0037_test", EXP / "measure.py")
AN = _load("analyze_0037_test", EXP / "analyze.py")
AL = _load("alignment_0037_test", EXP / "alignment.py")
R = _load("run_0037_test", EXP / "run.py")
A = M.A
SMALL = M.Plan(p_e=180, u_length=60, checkpoints=(60, 120, 180))
SYN = list(range(30201, 30211))
SYN_ALL = list(range(30201, 30300))
GUARD_SEEDS = list(range(30221, 30227))


@pytest.fixture(autouse=True)
def _repo_root(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)


def _raw(run: dict, mode: str = "synthetic") -> dict:
    return {"meta": {"experiment": "0037", "kind": PROTOCOL["kind"], "mode": mode, "seed": run["seed"],
                     "manifest": M.manifest_raw(), "blind": mode == "smoke"}, "run": run}


@functools.lru_cache(maxsize=None)
def _measured(seed: int, plan: M.Plan) -> str:
    return json.dumps(_raw(M.measure_seed(PROTOCOL, seed, plan)))


def measured(seed: int, plan: M.Plan = SMALL) -> dict:
    """実物の runtime を通した合成の個体の生の記録（JSON を通した形。返すのは複製）。"""
    return json.loads(_measured(seed, plan))


def failures(data: dict, seed: int, plan: M.Plan = SMALL) -> dict:
    return {k: v for k, v in AN.check_seed(data, "synthetic", seed, plan).items() if v}


def _probe(seed: int, until: int):
    s = M.build_system(PROTOCOL, seed)
    A.advance_to(s.app, until)
    return s


@functools.lru_cache(maxsize=None)
def first_intent(seed: int) -> int | None:
    s = _probe(seed, SMALL.p_e)
    return min((p for p, _ in s.world.intents), default=None)


@functools.lru_cache(maxsize=None)
def silent_seed() -> int:
    """SMALL の E で源が一度も発火しない最初の合成の個体（構成の条件だけで選ぶ）。"""
    return next(s for s in SYN_ALL if first_intent(s) is None)


@functools.lru_cache(maxsize=None)
def acting_seed() -> int:
    """SMALL の E の中ほどまでに源が発火する最初の合成の個体（持ち越しの構成に使う）。"""
    return next(s for s in SYN_ALL if first_intent(s) is not None and first_intent(s) < SMALL.p_e - 2)


@functools.lru_cache(maxsize=None)
def identity_seed() -> int:
    """源の結果を E の中で受け取ってから 6 本の重みが変わる最初の合成の個体（構造上の恒等を適格の個体で作る）。"""
    return next(s for s in SYN_ALL if first_intent(s) is not None and first_intent(s) <= first_weight_change(s) - 2)


@functools.lru_cache(maxsize=None)
def first_weight_change(seed: int) -> int:
    s = M.build_system(PROTOCOL, seed)
    w0 = M._weights(s)
    for pulse in range(1, SMALL.p_e + 1):
        A.advance_to(s.app, pulse)
        if M._weights(s) != w0:
            return pulse
    raise AssertionError("SMALL の E で重みが変わらない")


def plan_at(p_e: int) -> M.Plan:
    return M.Plan(p_e=p_e, u_length=SMALL.u_length, checkpoints=())


# ---- protocol と道具の一致 ----------------------------------------------------------------------

def test_protocol_and_tools_are_aligned() -> None:
    AL.check(PROTOCOL)


def test_formal_plan_follows_the_protocol_formulas() -> None:
    plan = M.formal_plan(PROTOCOL)
    assert (plan.p_e, plan.u_length) == (1800, 300) and plan.checkpoints == (300, 600, 900, 1200, 1500, 1800)


def test_the_run_entry_point_uses_only_the_protocol_plan() -> None:
    assert inspect.signature(R.measure).parameters.keys() == {"seed"}
    assert "measure_seed(PROTOCOL, seed)" in inspect.getsource(R.measure)
    assert R.OUT_DIR == Path("data/experiments/0037") and R.MAX_WORKERS == 2 and AN.OUT_DIR == R.OUT_DIR


def test_seen_seeds_include_0036_and_exclude_0037() -> None:
    assert set(range(27001, 27300)) <= AL.SEEN and set(range(28001, 28300)) <= AL.SEEN \
        and set(range(29001, 29300)) <= AL.SEEN
    assert not (set(range(30001, 30300)) & AL.SEEN)


def test_contract_tests_of_o1_are_the_as1_tests_and_this_file() -> None:
    assert AN.CONTRACT_TESTS == (PROTOCOL["tools"]["contract_tests"], str(Path(__file__).relative_to(ROOT)))


def test_the_analysis_contrasts_and_controls_follow_the_protocol() -> None:
    assert {k: list(v) for k, v in AN.CONTRASTS.items()} == PROTOCOL["quantities"]["contrasts"] == AL.CONTRASTS
    dc = PROTOCOL["descriptive_controls"]
    assert list(AN.REQUIRED_CONTROLS) == dc["required"] and list(AN.ALSO_CONTROLS) == dc["also"]
    assert list(AN.HORIZONTAL_PATTERNS) == dc["horizontal_pattern"]
    assert AN.CHECK_NAMES == ("structure", *(f"O{i}" for i in range(2, 16)))
    assert AN.M_E == PROTOCOL["judgment"]["per_individual"]["m_E"] == 1


# ---- 実物の runtime を通した合成の個体 --------------------------------------------------------------

@pytest.mark.parametrize("seed", SYN)
def test_synthetic_individuals_pass_every_operation_check(seed) -> None:
    assert failures(measured(seed), seed) == {}


def test_the_formal_plan_through_the_runtime_passes_every_operation_check() -> None:
    seed = 30299
    data = _raw(json.loads(json.dumps(M.measure_seed(PROTOCOL, seed))))
    assert {k: v for k, v in AN.check_seed(data, "synthetic", seed).items() if v} == {}
    assert data["run"]["plan"] == {"p_e": 1800, "u_length": 300, "checkpoints": [300, 600, 900, 1200, 1500, 1800]}


@pytest.mark.parametrize("which", ["carry", "n_e_one", "silent", "identity"])
def test_the_constructed_individuals_pass_every_operation_check(which) -> None:
    seed, plan = _constructed(which)
    assert failures(measured(seed, plan), seed, plan) == {}


def _constructed(which: str) -> tuple[int, M.Plan]:
    if which == "carry":
        s = acting_seed()
        return s, plan_at(first_intent(s))
    if which == "n_e_one":
        s = acting_seed()
        return s, plan_at(first_intent(s) + 1)
    if which == "silent":
        return silent_seed(), SMALL
    s = identity_seed()
    return s, plan_at(first_weight_change(s) - 1)


JUDGMENT_KEYS = {"eligible", "ineligible_kind", "n_E_M", "structural_identity", "I_U", "T", "T1", "T2", "T3", "contrasts",
                 "exists", "P_i", "J_C", "judgment", "individuals", "auxiliary", "descriptive_controls", "interval",
                 "delta_w", "M_checkpoints", "first_divergence_firing", "first_divergence_intent"}


def _keys(x, path=()):
    if isinstance(x, dict):
        for k, v in x.items():
            yield path, k
            if path == ("meta",) and k in ("protocol", "manifest"):
                continue
            yield from _keys(v, path + (k,))
    elif isinstance(x, list):
        for v in x:
            yield from _keys(v, path)


def test_raw_has_no_judgment_quantities() -> None:
    data = measured(SYN[0])
    assert not ({k for _, k in _keys(data)} & JUDGMENT_KEYS)
    assert set(data["run"]) == AN.RUN_KEYS


# ---- CT-PC1 再生の忠実さ ---------------------------------------------------------------------------

def test_ct_pc1_replay_gives_y_the_sensory_of_m_and_y_creates_no_reservation() -> None:
    seed, plan = _constructed("carry")
    run = measured(seed, plan)["run"]
    assert run["E"]["Y"]["sensory"] == run["M_E"]["sensory"] == run["E"]["Y_on"]["sensory"]
    w = run["boundary"]["sigma_a"]["Y"]["world"]
    assert w["next_rid"] == len(run["M_E"]["schedule"]) and {row[1] for row in w["pending"]} <= {"exogenous"}
    assert run["M_E"]["pending_at_p_e"]                                          # 持ち越しがある構成


def test_ct_pc1_y_without_freeze_is_m_through_p_e() -> None:
    run = measured(SYN[1])["run"]
    sm, sy = run["boundary"]["sigma_a"]["M"], run["E"]["Y_on"]["sigma_p_e"]
    assert (sy["units"], sy["connections"], sy["drives"]) == (sm["units"], sm["connections"], sm["drives"])
    assert run["E"]["Y_on"]["activity"] == run["M_E"]["activity"]


def test_o3_and_o4_detect_tampering() -> None:
    s = SYN[1]
    data = measured(s)
    data["run"]["E"]["Y"]["sensory"].append([5, data["run"]["roles"]["consequence_receptor"]])
    assert "O3" in failures(data, s)
    data = measured(s)
    data["run"]["boundary"]["sigma_a"]["Y"]["world"]["next_rid"] += 1
    assert "O3" in failures(data, s)
    data = measured(s)
    data["run"]["E"]["Y_on"]["sigma_p_e"]["units"][data["run"]["roles"]["other"]]["activity"] += 1e-9
    assert "O4" in failures(data, s)


# ---- CT-PC2 持ち越しと規則の切り替え ------------------------------------------------------------------

def test_ct_pc2_the_carry_over_arrives_identically_although_its_origin_differs() -> None:
    seed, plan = _constructed("carry")
    run = measured(seed, plan)["run"]
    p_e = plan.p_e
    carry = [[row[3], row[2]] for row in run["M_E"]["pending_at_p_e"]]
    assert carry == [[p_e + 1, run["roles"]["consequence_receptor"]]]
    for name in ("M", "M_W0", "M_WM", "Y", "Y_WM"):                       # P_E ＋ 1 には持ち越しだけが届く（U の結果と重ならない）
        assert [x for x in run["U"][name]["sensory"] if x[0] == p_e + 1] == carry, name
    kinds = {n: {row[1] for row in run["boundary"]["sigma_b"][n]["world"]["pending"]} for n in ("M", "Y")}
    assert kinds == {"M": {"consequence"}, "Y": {"exogenous"}}                       # 由来・種類は違う
    assert AN._pending_pr(run["boundary"]["sigma_b"]["M"]["world"]) == AN._pending_pr(run["boundary"]["sigma_b"]["Y"]["world"])


def test_ct_pc2_the_s4_switch_changes_only_respond_in_the_rule_dict() -> None:
    run = measured(*_constructed("carry"))["run"]
    sa, sb = run["boundary"]["sigma_a"], run["boundary"]["sigma_b"]
    for name in M.SWITCHED:
        before, after = sa[name]["world"]["rule"], sb[name]["world"]["rule"]
        assert isinstance(after, dict) and before["respond"] is False and after["respond"] is True
        assert {k: v for k, v in before.items() if k != "respond"} == {k: v for k, v in after.items() if k != "respond"}
        for key in ("intents", "realized", "pending", "next_rid"):           # 履歴・既存の予約の来歴は変えない
            assert sa[name]["world"][key] == sb[name]["world"][key], (name, key)
    assert all(sb[n]["world"]["rule"] == sb["M"]["world"]["rule"] for n in M.U_SYSTEMS)


def test_ct_pc2_y_answers_only_intents_after_the_switch() -> None:
    seed = acting_seed()
    run = measured(seed)["run"]
    cons, p_e, end = run["roles"]["consequence_receptor"], SMALL.p_e, SMALL.p_e + SMALL.u_length
    for name in ("Y", "Y_WM"):
        u = run["U"][name]
        carry = AN._pending_pr({"pending": run["M_E"]["pending_at_p_e"]})
        assert sorted(u["sensory"]) == sorted(carry + [[t + 1, cons] for t, _ in u["intents"] if t + 1 <= end])
        assert u["world_switches"] == [[p_e, "S4", True]]


def test_o8_detects_a_missing_or_extra_consequence() -> None:
    seed, plan = _constructed("carry")
    data = measured(seed, plan)
    data["run"]["U"]["Y"]["sensory"] = [x for x in data["run"]["U"]["Y"]["sensory"] if x[0] != plan.p_e + 1]
    assert "O8" in failures(data, seed, plan)
    data = measured(seed, plan)
    data["run"]["U"]["M_W0"]["sensory"].append([plan.p_e + 7, data["run"]["roles"]["consequence_receptor"]])
    assert "O8" in failures(data, seed, plan)


# ---- CT-PC3 E の FREEZE ---------------------------------------------------------------------------

def test_ct_pc3_y_and_k_keep_w0_at_every_pulse_of_e() -> None:
    run = measured(SYN[2])["run"]
    for name in ("Y", "K"):
        rows = run["E"][name]["pulse_weights"]
        assert [p for p, _ in rows] == list(range(1, SMALL.p_e + 1)) and all(w == run["W_0"] for _, w in rows)
    assert set(run["W_0"].values()) == {AN.W0}
    six = sorted(run["W_0"])
    for name in ("Y", "K"):                                               # 宣言の境界 0 が Pulse 1 から効く
        assert run["U"][name]["history"][0] == [0, "E", [["FREEZE", six, "advance"]]]


def test_o5_detects_a_moving_e_weight() -> None:
    s = SYN[2]
    data = measured(s)
    cid = sorted(data["run"]["W_0"])[0]
    data["run"]["E"]["K"]["pulse_weights"][10][1][cid] += 1e-12
    assert "O5" in failures(data, s)


# ---- CT-PC4 移植 ---------------------------------------------------------------------------------

def test_ct_pc4_transplant_under_freeze_fails_and_after_clear_succeeds() -> None:
    seed = SYN[3]
    m = _probe(seed, 120)
    w_m = M._weights(m)
    y = M.build_system(PROTOCOL, seed, respond=False, exogenous=A.replay_schedule(m))
    six = frozenset(w_m)
    y.declare(M._freeze_six(six), label="E")                          # 出生から 6 本を止めた系
    A.advance_to(y.app, 120)
    with pytest.raises(ValueError):
        y.transplant(w_m)                                              # FREEZE 中の接続へは移植できない
    assert M._weights(y) != w_m
    y.clear(label="S1")
    twin = A.clone(y)
    assert M._jsonable(twin.connections.export_intervention_state()) == AN.EMPTY_INTERVENTIONS
    twin.transplant(w_m)
    assert M._weights(twin) == w_m and twin.pulse == y.pulse == 120      # Pulse を進めていない
    twin.declare(M._freeze_six(six), label="S5")
    frozen = twin.connections.export_intervention_state()["frozen"]
    assert {cid: v["weight"] for cid, v in frozen.items()} == w_m       # 宣言の時点の重みは移植の値のまま
    A.advance_to(twin.app, 150)
    assert M._weights(twin) == w_m


def test_ct_pc4_only_the_declared_weights_are_replaced_and_the_pairs_share_the_intervention_state() -> None:
    run = measured(SYN[3])["run"]
    sa, sb = run["boundary"]["sigma_a"], run["boundary"]["sigma_b"]
    for a, b in M.HORIZONTAL:
        paths = A.sigma_diff(sa[a], sa[b])
        assert all(len(x) == 3 and x[0] == "connections" and x[2] == "weight" for x in paths), paths
        assert {x[1] for x in paths} == {c for c in run["W_0"] if run["W_0"][c] != run["boundary"]["W_M"][c]}
        assert sa[a]["interventions"] == sa[b]["interventions"] == AN.EMPTY_INTERVENTIONS
        assert sb[a]["interventions"]["active"] == sb[b]["interventions"]["active"]


def test_the_boundary_log_lists_s0_to_s6_in_order() -> None:
    run = measured(SYN[3])["run"]
    steps = run["boundary"]["steps"]
    assert [x[0] for x in steps] == sorted(x[0] for x in steps)                 # S0 → S6 の順
    assert [x[1] for x in steps if x[0] == "S0"] == list(M.S0_ORDER)
    assert all(x[2] == SMALL.p_e for x in steps if x[0] in ("S0", "S1", "S2", "S3", "S4", "S5"))
    assert [(x[1], x[2]) for x in steps if x[0] == "S6"] == [(n, SMALL.p_e + SMALL.u_length) for n in M.U_SYSTEMS]


def test_ct_pc4_pair_sums_and_the_transplanted_values() -> None:
    run = measured(SYN[3])["run"]
    sa = run["boundary"]["sigma_a"]
    assert AN._weights_of(sa["M_W0"]) == run["W_0"] and AN._weights_of(sa["Y_WM"]) == run["boundary"]["W_M"]
    assert AN._weights_of(sa["M_WM"]) == AN._weights_of(sa["M"]) == run["boundary"]["W_M"]
    assert all(v == 2 * AN.W0 for v in AN.pair_sums(AN._weights_of(sa["M_W0"])).values())


def test_o6_detects_a_wrong_order_or_history() -> None:
    s = SYN[3]
    data = measured(s)
    steps = data["run"]["boundary"]["steps"]
    steps[0], steps[2] = steps[2], steps[0]
    assert "O6" in failures(data, s)
    data = measured(s)
    s3 = next(x for x in data["run"]["boundary"]["steps"] if x[0] == "S3")
    s3[4]["intervention_state_at_transplant"] = {"active": [["FREEZE", sorted(data["run"]["W_0"]), "advance"]], "frozen": {}}
    assert "O6" in failures(data, s)
    data = measured(s)
    s6 = next(x for x in data["run"]["boundary"]["steps"] if x[0] == "S6")
    s6[2] -= 1                                                              # U を最後まで走らせていない
    assert "O6" in failures(data, s)
    data = measured(s)
    data["run"]["U"]["K"]["history"].append([SMALL.p_e, "S5", data["run"]["U"]["K"]["history"][-1][2]])
    assert "O6" in failures(data, s)
    data = measured(s)
    data["run"]["boundary"]["sigma_a"]["Y"]["pulse"] += 1
    assert "O6" in failures(data, s)


def test_o14_detects_a_broken_pair_sum() -> None:
    s = SYN[3]
    data = measured(s)
    cid = sorted(data["run"]["W_0"])[0]
    data["run"]["boundary"]["sigma_a"]["M_W0"]["connections"][cid]["weight"] += 1e-6
    assert "O14" in failures(data, s)


# ---- CT-PC5 差の目録 --------------------------------------------------------------------------------

def test_ct_pc5_the_difference_inventory_at_a_and_b() -> None:
    run = measured(SYN[4])["run"]
    sa = run["boundary"]["sigma_a"]
    assert A.sigma_diff(sa["M"], sa["M_WM"]) == []
    assert {p[0] for p in A.sigma_diff(sa["M"], sa["M_W0"])} <= {"connections"}
    assert {p[0] for p in A.sigma_diff(sa["M"], sa["Y"])} <= AN.ALLOWED_TOP_M_Y
    sb = run["boundary"]["sigma_b"]
    for name in M.U_SYSTEMS:
        assert sb[name]["interventions"]["active"] == [["FREEZE", sorted(run["W_0"]), "advance"]]


def test_o7_detects_tampering() -> None:
    s = SYN[4]
    data = measured(s)
    data["run"]["boundary"]["sigma_a"]["M_W0"]["units"][data["run"]["roles"]["source"]]["adaptation"] += 1e-9
    assert "O7" in failures(data, s)
    data = measured(s)
    data["run"]["boundary"]["sigma_a"]["Y"]["clock"] += 1
    assert "O7" in failures(data, s)
    data = measured(s)
    data["run"]["boundary"]["sigma_b"]["Y"]["world"]["pending"].append([999, "exogenous", "receptor.x1", 9999, None])
    assert "O7" in failures(data, s)
    data = measured(s)
    cid = sorted(data["run"]["W_0"])[0]
    data["run"]["boundary"]["sigma_b"]["M"]["interventions"]["frozen"][cid]["weight"] += 1e-9
    assert "O7" in failures(data, s)


def test_ct_pc5_bookkeeping_fields_do_not_affect_the_trajectory() -> None:
    seed = SYN[4]
    base = _probe(seed, 150)
    twin = A.clone(base)
    twin.world.intents.append((1, "fake-delta"))                       # 世界の帳簿の欄
    twin.world.realized.append((2, "receptor.x1", (999,), 1))
    twin.world._next_rid += 7
    unit = twin.app.units.get(twin.roles.other)
    st = unit.export_state()
    unit.import_state({**st, "fire_count": st["fire_count"] + 5})        # 発火の数
    A.advance_to(base.app, 210)
    A.advance_to(twin.app, 210)
    assert [x for x in twin.log.activity()] == [x for x in base.log.activity() if x[0] > 150]
    assert M._weights(twin) == M._weights(base)
    for u in base.app.units.all():
        a, b = u.export_state(), twin.app.units.get(u.unit_id).export_state()
        assert {k: v for k, v in a.items() if k != "fire_count"} == {k: v for k, v in b.items() if k != "fire_count"}


# ---- CT-PC6 恒等の検出 ------------------------------------------------------------------------------

def test_ct_pc6_the_own_weight_transplant_reproduces_m() -> None:
    run = measured(SYN[5])["run"]
    for key in ("activity", "intents", "sensory", "sigma_end_sha256"):
        assert run["U"]["M_WM"][key] == run["U"]["M"][key]


def test_ct_pc6_a_structural_identity_is_labelled_and_identical() -> None:
    seed, plan = _constructed("identity")
    run = measured(seed, plan)["run"]
    assert run["boundary"]["W_M"] == run["W_0"]
    ind = AN.individual(run)
    assert ind["eligible"] is True and ind["n_E_M"] >= 1                       # 分母に残る
    assert ind["structural_identity"] is True and ind["P_i"] is False
    for a, b in (("M", "M_W0"), ("Y", "Y_WM")):
        assert run["U"][a]["sigma_end_sha256"] == run["U"][b]["sigma_end_sha256"]


def test_o10_detects_a_broken_identity() -> None:
    s = SYN[5]
    data = measured(s)
    data["run"]["U"]["M_WM"]["sigma_end_sha256"] = "0" * 64
    assert "O10" in failures(data, s)
    seed, plan = _constructed("identity")
    data = measured(seed, plan)
    data["run"]["U"]["M_W0"]["intents"].append([plan.p_e + 3, "fake"])
    assert "O10" in failures(data, seed, plan)


# ---- CT-PC7 試しの区間の同じ条件 -----------------------------------------------------------------------

def test_ct_pc7_the_u_weights_stay_at_the_declared_values() -> None:
    run = measured(SYN[6])["run"]
    targets = {"W_0": run["W_0"], "W_M": run["boundary"]["W_M"]}
    for name in M.U_SYSTEMS:
        rows = run["U"][name]["pulse_weights"]
        assert [p for p, _ in rows] == list(range(SMALL.p_e + 1, SMALL.p_e + SMALL.u_length + 1))
        assert all(w == targets[M.FROZEN_VALUE[name]] for _, w in rows)
    assert len({json.dumps(run["U"][n]["world_end"]["rule"], sort_keys=True) for n in M.U_SYSTEMS}) == 1
    assert {run["U"][n]["pulse_end"] for n in M.U_SYSTEMS} == {SMALL.p_e + SMALL.u_length}       # 同じ |U|


def test_o9_detects_a_moving_u_weight_or_a_different_rule() -> None:
    s = SYN[6]
    data = measured(s)
    cid = sorted(data["run"]["W_0"])[1]
    data["run"]["U"]["Y"]["pulse_weights"][5][1][cid] += 1e-12
    assert "O9" in failures(data, s)
    data = measured(s)
    data["run"]["U"]["K"]["world_end"]["rule"]["respond"] = False
    assert "O9" in failures(data, s)


# ---- CT-PC9 命題 Q2-4・Q2-5 ----------------------------------------------------------------------------

def test_ct_pc9_a_silent_source_keeps_its_four_weights_bitwise() -> None:
    seed = silent_seed()
    run = measured(seed)["run"]
    src = run["roles"]["source"]
    assert not any(u == src for _, u in run["M_E"]["activity"])
    incident = [cid for cid in run["W_0"] if src in AN._ends(cid)]
    assert len(incident) == 4 and all(run["boundary"]["W_M"][c] == run["W_0"][c] for c in incident)
    ind = AN.individual(run)
    assert ind["eligible"] is False and ind["ineligible_kind"] == "a"


def test_ct_pc9_traces_do_not_matter_when_all_six_are_frozen() -> None:
    seed = SYN[6]
    base = _probe(seed, 120)
    six = frozenset(M._weights(base))
    a, b = A.clone(base), A.clone(base)
    for s in (a, b):
        s.declare(M._freeze_six(six), label="S5")
    state = b.app.connections.export_state()
    b.app.connections.import_state({cid: {**v, "pre_trace": v["pre_trace"] + 3.0, "post_trace": v["post_trace"] * 0.5}
                                    for cid, v in state.items()})
    A.advance_to(a.app, 180)
    A.advance_to(b.app, 180)
    assert a.log.activity() == b.log.activity() and M._weights(a) == M._weights(b)
    assert {u.unit_id: u.export_state() for u in a.app.units.all()} == {u.unit_id: u.export_state() for u in b.app.units.all()}


# ---- 適格・適格外の分け方（README §4.1） ------------------------------------------------------------------

def test_ineligible_kind_b_the_source_fired_only_at_p_e() -> None:
    seed, plan = _constructed("carry")
    ind = AN.individual(measured(seed, plan)["run"])
    assert ind["n_E_M"] == 0 and ind["source_firings_E"]["M"] == 1
    assert ind["eligible"] is False and ind["ineligible_kind"] == "b"


def test_n_e_one_is_eligible() -> None:
    seed, plan = _constructed("n_e_one")
    ind = AN.individual(measured(seed, plan)["run"])
    assert ind["n_E_M"] == 1 and ind["eligible"] is True and ind["ineligible_kind"] is None


# ---- CT-PC10 T の計算 -------------------------------------------------------------------------------

def test_ct_pc10_the_intents_follow_the_source_firings_in_the_world_record() -> None:
    run = measured(acting_seed())["run"]
    src = run["roles"]["source"]
    assert [p for p, _ in run["M_E"]["intents"]] == [p for p, u in run["M_E"]["activity"] if u == src]
    assert run["M_E"]["intents"]                                          # 空の一致ではない
    for name in M.U_SYSTEMS:
        u = run["U"][name]
        assert [p for p, _ in u["intents"]] == [p for p, x in u["activity"] if x == src], name
    ind = AN.individual(run)
    for name in M.U_SYSTEMS:                                                # I_U は源の発火と同じ（O11 で照合）
        assert ind["I_U"][name] == [p for p, x in run["U"][name]["activity"] if x == src]


def test_t_values_and_the_t2_sign_rule() -> None:
    assert AN.t_values([], 100) == {"T1": 0, "T2": None, "T3": None}
    assert AN.t_values([105], 100) == {"T1": 1, "T2": 5, "T3": None}
    assert AN.t_values([130, 105, 110], 100) == {"T1": 3, "T2": 5, "T3": 12.5}
    assert [AN.t2_sign(*x) for x in ((5, 3), (3, 5), (4, 4), (None, 3), (3, None), (None, None))] == \
        ["+", "-", "0", "+", "-", "?"]


def test_first_divergence_helpers() -> None:
    a, b = [[11, "s1"], [12, "s2"]], [[11, "s1"], [13, "s2"]]
    assert AN.first_divergence(a, a, 11, 20) is None and AN.first_divergence(a, b, 11, 20) == 12
    assert AN.first_intent_divergence([11, 15], [11, 16], 11, 20) == 15


@functools.lru_cache(maxsize=None)
def u_event_seed() -> int:
    """U に世界の成立の出来事がある最初の合成の個体（SYN の中、構成の条件だけで選ぶ）。"""
    return next(s for s in SYN if measured(s)["run"]["U"]["M"]["sensory"])


def test_o2_matches_the_world_realized_record_with_the_saved_sensory() -> None:
    s = u_event_seed()
    p_e = SMALL.p_e
    assert failures(measured(s), s) == {}
    for name in M.U_SYSTEMS:
        data = measured(s)
        rows = data["run"]["U"][name]["world_end"]["realized"]
        i = next(i for i, row in enumerate(rows) if row[0] > p_e)               # U の中の出来事（予約の識別子 1 つ・n ＝ 1）
        assert len(rows[i][2]) == 1 and rows[i][3] == 1
        rows[i][0] += 1                                                          # Pulse だけを替える
        assert _world_failure(failures(data, s)), name
        data = measured(s)
        row = next(r for r in data["run"]["U"][name]["world_end"]["realized"] if r[0] > p_e)
        row[1] = data["run"]["roles"]["source_receptor"]                         # Receptor だけを替える
        assert _world_failure(failures(data, s)), name


def _world_failure(f: dict) -> bool:
    return any("世界の成立の記録" in msg or "世界の意図の記録" in msg or "P_E の世界" in msg for msg in f.get("O2", []))


def test_o2_matches_the_world_records_in_e_and_the_intents() -> None:
    s = u_event_seed()
    data = measured(s)
    rows = data["run"]["U"]["Y"]["world_end"]["realized"]
    rows[0][0] += 1                                                              # E の側（再生された S^ext）
    assert _world_failure(failures(data, s))
    data = measured(s)
    data["run"]["U"]["K"]["world_end"]["intents"][-1][0] += 1                     # 世界の意図の記録
    assert _world_failure(failures(data, s))
    for name in ("Y_on", "M_rerun"):
        data = measured(s)
        data["run"]["E"][name]["sigma_p_e"]["world"]["realized"][0][0] += 1
        assert _world_failure(failures(data, s)), name


def test_o11_and_o2_detect_tampering() -> None:
    s = SYN[7]
    data = measured(s)
    data["run"]["U"]["Y_WM"]["intents"].append([SMALL.p_e + 2, "fake"])
    f = failures(data, s)
    assert "O11" in f and "O2" in f
    data = measured(s)
    data["run"]["M_E"]["sensory"].append([7, data["run"]["roles"]["source_receptor"]])
    assert "O2" in failures(data, s)


# ---- SE-6：Pulse P_E ＋ 1 の一致と、最短の分岐（Runtime の順序） ---------------------------------------------

def _se6_setup(seed: int, b: int):
    base = _probe(seed, b)
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
        s.declare(M._freeze_six(six), label="S5")
    return orig, test


def _find_se6_boundary(want_sender_fires: bool) -> tuple[int, int, str]:
    for seed in SYN_ALL:
        for b in range(40, 170):
            base, six, fired = _se6_setup(seed, b)
            for cid in sorted(six):
                u, v = AN._ends(cid)
                if want_sender_fires and u in fired[b + 1] and v not in fired[b + 2]:
                    return seed, b, cid
                if not want_sender_fires and u not in fired[b + 1]:
                    return seed, b, cid
    raise AssertionError("構成が見つからない")


def test_se6_a_weight_difference_can_first_change_firing_at_p_e_plus_2() -> None:
    seed, b, cid = _find_se6_boundary(want_sender_fires=True)
    base, six, _ = _se6_setup(seed, b)
    orig, test = _se6_pair(base, six, cid, 10.0)
    A.advance_to(orig.app, b + 1)
    A.advance_to(test.app, b + 1)
    so, st = M._sigma(orig), M._sigma(test)
    assert so["units"] == st["units"] and orig.log.activity() == test.log.activity()      # 1 歩目は同じ
    differs = [(x, y) for x, y in zip(so["drives"], st["drives"]) if x != y]
    u, v = AN._ends(cid)
    assert differs and all(x[0] == u and x[1] == v and x[3] == b + 1 for x, _ in differs)  # その接続の分だけ違う
    A.advance_to(orig.app, b + 2)
    A.advance_to(test.app, b + 2)
    assert AN.first_divergence([list(x) for x in orig.log.activity()], [list(x) for x in test.log.activity()],
                               b + 1, b + 2) == b + 2


def test_se6_no_difference_reaches_p_e_plus_2_when_the_sender_does_not_fire() -> None:
    seed, b, cid = _find_se6_boundary(want_sender_fires=False)
    base, six, _ = _se6_setup(seed, b)
    orig, test = _se6_pair(base, six, cid, 10.0)
    A.advance_to(orig.app, b + 1)
    A.advance_to(test.app, b + 1)
    so, st = M._sigma(orig), M._sigma(test)
    assert so["units"] == st["units"] and so["drives"] == st["drives"]                    # 駆動に差はない
    A.advance_to(orig.app, b + 2)
    A.advance_to(test.app, b + 2)
    assert orig.log.activity() == test.log.activity()


def _seed_with_first_drives() -> int:
    """Pulse P_E ＋ 1 の処理の後に届く途中の駆動がある最初の合成の個体（SYN の中、構成の条件だけで選ぶ）。"""
    return next(s for s in SYN if measured(s)["run"]["U"]["Y_WM"]["sigma_after_first"]["drives"])


@functools.lru_cache(maxsize=None)
def weight_drive_seed() -> tuple[int, str, str]:
    """横の対で、Pulse P_E ＋ 1 の後の届く途中の駆動の値が違う最初の合成の個体（重みの差がある接続の送り手が P_E ＋ 1 に
    発火した構成。SMALL、30201〜30299 の最初から順に、構成の条件だけで選ぶ）。"""
    for s in SYN_ALL:
        run = measured(s)["run"]
        for a, b in M.HORIZONTAL:
            da, db = run["U"][a]["sigma_after_first"]["drives"], run["U"][b]["sigma_after_first"]["drives"]
            if len(da) == len(db) and any(x[2] != y[2] for x, y in zip(da, db)):
                return s, a, b
    raise AssertionError("構成が見つからない")


def test_o15_holds_on_the_records_and_detects_tampering() -> None:
    s = SYN[8]
    data = measured(s)
    assert "O15" not in failures(data, s)
    sigma = data["run"]["U"]["M_W0"]["sigma_after_first"]
    sigma["units"][data["run"]["roles"]["receiver"]]["activity"] += 1e-9
    assert "O15" in failures(data, s)
    s = _seed_with_first_drives()
    data = measured(s)
    assert "O15" not in failures(data, s)
    data["run"]["U"]["Y_WM"]["sigma_after_first"]["drives"].pop()
    assert "O15" in failures(data, s)
    s = SYN[8]
    data = measured(s)
    data["run"]["U"]["M_W0"]["activity"].append([SMALL.p_e + 1, "s1"])
    data["run"]["U"]["M_W0"]["activity"].sort()
    assert "O15" in failures(data, s)


def test_o15_receptor_drives_are_in_sigma_and_must_match_without_a_lookup_error() -> None:
    # Receptor の感覚から作られた駆動も sigma の drives に入る（connections は Unit 間の可塑的な 6 本だけ）。
    # 横の対では一致を求め、違えば無効にする（接続の鍵で引いて KeyError にしない）
    for seed, plan in (_constructed("carry"), (_seed_with_first_drives(), SMALL)):
        data = measured(seed, plan)
        run = data["run"]
        cons = run["roles"]["consequence_receptor"]
        drives = run["U"]["Y_WM"]["sigma_after_first"]["drives"]
        i = next(i for i, x in enumerate(drives) if x[0] == cons)            # 持ち越しの感覚から作られた駆動
        assert f"{cons}.main->{drives[i][1]}" not in run["boundary"]["sigma_b"]["Y_WM"]["connections"]
        assert "O15" not in failures(data, seed, plan)
        drives[i][2] += 0.5
        assert "O15" in failures(data, seed, plan)


def test_o15_without_carry_over_has_no_receptor_drive_at_the_first_pulse() -> None:
    s = SYN[8]
    run = measured(s)["run"]
    assert not run["M_E"]["pending_at_p_e"]                                  # 持ち越しのない構成
    for name in M.U_SYSTEMS:
        assert all(not x[0].startswith("receptor.") for x in run["U"][name]["sigma_after_first"]["drives"])


def test_o15_accepts_only_the_drive_difference_of_a_weight_differing_connection_whose_sender_fired() -> None:
    s, a, b = weight_drive_seed()
    data = measured(s)
    assert failures(data, s) == {}
    run = data["run"]
    da, db = run["U"][a]["sigma_after_first"]["drives"], run["U"][b]["sigma_after_first"]["drives"]
    wa, wb = AN._weights_of(run["boundary"]["sigma_b"][a]), AN._weights_of(run["boundary"]["sigma_b"][b])
    fired = {u for p, u in run["U"][a]["activity"] if p == SMALL.p_e + 1}
    for x, y in zip(da, db):
        if x[2] != y[2]:
            cid = f"{x[0]}.main->{x[1]}"
            assert wa[cid] != wb[cid] and x[0] in fired and (x[2], y[2]) == (wa[cid], wb[cid])
    i = next(i for i, (x, y) in enumerate(zip(da, db)) if x[2] != y[2])
    db[i][2] = da[i][2] + 1e-6                                                  # 重みの差の分の外の違い
    assert "O15" in failures(data, s)


# ---- 判定の算術（README §4・§5） ----------------------------------------------------------------------------

def _fake(eligible: bool, p: bool, identity: bool = False, kind: str | None = None) -> dict:
    contrasts = {name: {"exists": p, "T1_diff": 0, "T1_sign": "0", "T2_sign": "?", "T2_diff": None, "T3_diff": None,
                        "first_divergence_firing": None, "first_divergence_intent": None} for name in AN.CONTRASTS}
    return {"eligible": eligible, "ineligible_kind": None if eligible else (kind or "a"), "structural_identity": identity,
            "P_i": eligible and p, "contrasts": contrasts}


def test_judge_counts_only_the_eligible_and_keeps_identities_in_the_denominator() -> None:
    k10 = PROTOCOL["judgment"]["J_C"]["k_of_m"][10]
    inds = {str(i): _fake(True, i < k10 - 1) for i in range(9)}
    inds["id"] = _fake(True, False, identity=True)                       # 構造上の恒等：分母に残り、P_i ＝ 0
    inds.update({f"x{i}": _fake(False, True) for i in range(5)})          # 適格外は数えない
    j = AN.judge(inds)
    assert j["J_C"]["m"] == 10 and j["J_C"]["count_P_i"] == k10 - 1 and j["J_C"]["status"] == "not_established"
    assert j["interval"]["computed"] is True and j["interval"]["denominator"] == 10
    inds["9"] = _fake(True, True)
    j = AN.judge(inds)
    assert j["J_C"]["m"] == 11 and j["J_C"]["k"] == PROTOCOL["judgment"]["J_C"]["k_of_m"][11]
    inds = {str(i): _fake(True, True) for i in range(10)}
    assert AN.judge(inds)["J_C"]["status"] == "established"


def test_below_ten_is_inconclusive_but_the_interval_is_still_reported() -> None:
    inds = {str(i): _fake(True, True) for i in range(9)}
    j = AN.judge(inds)
    assert j["J_C"]["status"] == "inconclusive" and j["J_C"]["k"] is None
    assert j["interval"]["computed"] is True and j["interval"]["denominator"] == 9
    assert AN.judge({"a": _fake(False, True)})["interval"]["computed"] is False


def test_k_of_m_matches_the_protocol_table() -> None:
    for m, k in PROTOCOL["judgment"]["J_C"]["k_of_m"].items():
        assert AN.k_of_m(m, 0.05) == k


def test_clopper_pearson_known_values() -> None:
    lo, hi = AN.clopper_pearson(16, 20)
    assert abs(lo - 0.5634) < 1e-4 and abs(hi - 0.9427) < 1e-4
    assert AN.clopper_pearson(0, 10)[0] == 0.0 and AN.clopper_pearson(10, 10)[1] == 1.0


def test_descriptive_controls_and_the_horizontal_patterns() -> None:
    inds = {"a": _fake(True, False), "b": _fake(True, True), "c": _fake(False, True, kind="a"), "d": _fake(False, False, kind="b")}
    inds["e"] = _fake(True, False)
    inds["e"]["contrasts"]["C_tr"]["exists"] = True
    inds["f"] = _fake(True, False)
    inds["f"]["contrasts"]["C_tr_rev"]["exists"] = True
    dc = AN.descriptive_controls(inds)
    assert dc["m"] == 4 and set(dc["contrasts"]) == set(AN.REQUIRED_CONTROLS + AN.ALSO_CONTROLS)
    assert dc["horizontal_pattern"] == {"equal under both states": 1, "differs only under M's state": 1,
                                        "differs only under Y's state": 1, "differs under both states": 1}
    assert dc["ineligible"]["a"]["denominator"] == 1 and dc["ineligible"]["b"]["denominator"] == 1
    assert dc["ineligible"]["a"]["individuals"] == ["c"] and dc["ineligible"]["b"]["individuals"] == ["d"]
    assert all(v["interval"]["computed"] for v in dc["contrasts"].values())


def test_the_ineligible_tables_carry_the_same_quantities_as_the_eligible_table() -> None:
    inds = {"e": _fake(True, True), "a1": _fake(False, True, kind="a"), "a2": _fake(False, False, kind="a")}
    dc = AN.descriptive_controls(inds)
    eligible_row = set(dc["contrasts"]["C_rep"])
    a = dc["ineligible"]["a"]
    assert a["denominator"] == 2 and a["individuals"] == ["a1", "a2"]
    assert set(a["contrasts"]) == set(AN.CONTRASTS)                          # 主の比べ C^tr も記述として並べる
    for name, row in a["contrasts"].items():
        assert set(row) >= eligible_row, name
        assert row["count"] == 1 and row["proportion"] == 0.5                  # a1 だけが、どの対比でも違う
        assert row["interval"] == AN.interval(1, 2) and row["interval"]["computed"] is True
    assert "structural_identity_label" in a["contrasts"]["C_tr_rev"]
    assert sum(a["horizontal_pattern"].values()) == 2 and set(a["horizontal_pattern"]) == set(AN.HORIZONTAL_PATTERNS)
    assert "a1" not in [s for s, v in inds.items() if v["eligible"]] and dc["m"] == 1   # 全体の数には入れない
    assert AN.judge(inds)["J_C"]["m"] == 1


def test_an_empty_ineligible_group_has_null_proportions_and_no_interval() -> None:
    dc = AN.descriptive_controls({"e": _fake(True, True)})
    for kind in ("a", "b"):
        t = dc["ineligible"][kind]
        assert t["denominator"] == 0 and t["individuals"] == []
        for row in t["contrasts"].values():
            assert row["count"] == 0 and row["proportion"] is None and row["interval"]["computed"] is False
        assert set(t["horizontal_pattern"].values()) == {0}
    empty = AN.descriptive_controls({})
    assert empty["m"] == 0 and all(r["proportion"] is None for r in empty["contrasts"].values())


def test_the_ineligible_tables_on_synthetic_raw_of_kinds_a_and_b() -> None:
    seed_a, plan_a = _constructed("silent")
    seed_b, plan_b = _constructed("carry")
    inds = {str(seed_a): AN.individual(measured(seed_a, plan_a)["run"]),
            "b" + str(seed_b): AN.individual(measured(seed_b, plan_b)["run"])}
    dc = AN.descriptive_controls(inds)
    assert dc["m"] == 0 and dc["ineligible"]["a"]["individuals"] == [str(seed_a)]
    assert dc["ineligible"]["b"]["individuals"] == ["b" + str(seed_b)]
    for kind in ("a", "b"):
        t = dc["ineligible"][kind]
        assert t["denominator"] == 1 and set(t["contrasts"]) == set(AN.CONTRASTS)
        assert all(r["interval"]["computed"] and r["proportion"] is not None for r in t["contrasts"].values())


def test_r2_reports_the_m_checkpoints_by_role() -> None:
    run = measured(SYN[1])["run"]
    ind = AN.individual(run)
    assert list(ind["M_checkpoints"]) == [str(p) for p in SMALL.checkpoints]
    last = ind["M_checkpoints"][str(SMALL.p_e)]
    assert last["weights"] == ind["W_M"] and set(last["traces"]) == set(ind["W_M"])
    assert last["pair_sums"] == ind["pair_sums_W_M"]


def _with_activity(run: dict, other: str, extra: list) -> dict:
    """解析の算術を確かめるための、記録の書き換え（有効な raw ではない）：other の系の U の発火を M のものにそろえ、extra を足す。"""
    run = copy.deepcopy(run)
    base = [list(x) for x in run["U"]["M"]["activity"]]
    run["U"][other]["activity"] = sorted(base + extra)
    return run


def test_r6_reports_the_delay_from_p_e_plus_2_only_for_the_horizontal_pairs() -> None:
    run = measured(SYN[2])["run"]
    lower = SMALL.p_e + 2
    for extra, want in (([[lower, "s9"]], 0), ([[lower + 1, "s9"]], 1), ([], None)):
        row = AN.individual(_with_activity(run, "M_W0", extra))["contrasts"]["C_tr"]
        assert row["horizontal"] is True and row["lower_bound_pulse"] == lower
        assert row["first_divergence_firing"] == (None if want is None else lower + want)       # 絶対の Pulse も残す
        assert row["first_divergence_firing_delay"] == want
    ind = AN.individual(run)
    assert set(AN.HORIZONTAL_CONTRASTS) == {"C_tr", "C_tr_rev"}
    assert ind["contrasts"]["C_tr_rev"]["lower_bound_pulse"] == lower
    for name in set(AN.CONTRASTS) - set(AN.HORIZONTAL_CONTRASTS):            # ほかの対に下限を当てない
        row = ind["contrasts"][name]
        assert row["horizontal"] is False
        assert not {"lower_bound_pulse", "first_divergence_firing_delay", "first_divergence_intent_delay"} & set(row)


def test_r6_summary_has_the_delays_for_the_horizontal_pairs() -> None:
    run = measured(SYN[2])["run"]
    lower = SMALL.p_e + 2
    inds = {}
    for i, extra in enumerate(([[lower, "s9"]], [[lower + 3, "s9"]], [])):
        inds[str(i)] = AN.individual(_with_activity(run, "M_W0", extra))
        inds[str(i)]["eligible"] = True                                        # 算術の確かめのための書き換え
    r6 = AN.auxiliary(inds)["R6"]
    c = r6["C_tr"]
    assert c["horizontal"] is True and c["lower_bound_pulse"] == lower
    assert c["first_divergence_firing"]["none"] == 1
    assert c["first_divergence_firing"]["pulses"]["min"] == lower and c["first_divergence_firing"]["delays"]["max"] == 3
    assert c["first_divergence_firing"]["delays"]["count"] == 2 and c["first_divergence_firing"]["delays"]["min"] == 0
    for name in set(AN.CONTRASTS) - set(AN.HORIZONTAL_CONTRASTS):
        assert r6[name]["horizontal"] is False and "lower_bound_pulse" not in r6[name]
        assert "delays" not in r6[name]["first_divergence_firing"] and "delays" not in r6[name]["first_divergence_intent"]


def test_five_numbers() -> None:
    assert AN.five_numbers([]) is None
    assert AN.five_numbers([3]) == {"count": 1, "min": 3, "q1": 3, "median": 3, "q3": 3, "max": 3}


def test_the_analysis_of_the_synthetic_individuals_runs_through() -> None:
    runs = {s: measured(s) for s in SYN[:4]}
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=[])
    assert report["valid"] is True
    assert set(report) == {"mode", "valid", "O1", "judgment", "interval", "descriptive_controls", "individuals", "auxiliary"}
    assert report["judgment"]["J_C"]["status"] == "inconclusive"                  # 4 個体なので m ＜ 10
    assert set(report["auxiliary"]) == {"R1", "R2", "R4", "R5", "R6", "R7"}


def test_an_invalid_individual_or_a_failed_o1_blocks_the_judgment() -> None:
    runs = {s: measured(s) for s in SYN[:2]}
    runs[SYN[0]]["run"]["U"]["M_WM"]["sigma_end_sha256"] = "0" * 64
    report = AN.analyze_runs(runs, "synthetic", SMALL, o1=[])
    assert report["valid"] is False and report["judgment"] is None and "individuals" not in report
    report = AN.analyze_runs({SYN[1]: measured(SYN[1])}, "synthetic", SMALL, o1=["x"])
    assert report["valid"] is False and report["judgment"] is None


# ---- 記録の形・seed・meta ---------------------------------------------------------------------------

def test_structure_detects_extra_fields_and_wrong_roles() -> None:
    s = SYN[9]
    data = measured(s)
    data["run"]["P_i"] = True
    assert "structure" in failures(data, s)
    data = measured(s)
    data["run"]["roles"]["source"], data["run"]["roles"]["other"] = data["run"]["roles"]["other"], data["run"]["roles"]["source"]
    assert "structure" in failures(data, s)
    data = measured(s)
    data["run"]["U"]["K"]["extra"] = 1
    assert "structure" in failures(data, s)


def test_o12_rejects_seeds_outside_the_range_or_seen() -> None:
    out: list[str] = []
    AN._o12(30001, "synthetic", out)
    assert out
    out = []
    AN._o12(29299, "synthetic", out)
    assert out


def test_o13_detects_a_different_rerun() -> None:
    s = SYN[9]
    data = measured(s)
    data["run"]["E"]["M_rerun"]["sigma_p_e_sha256"] = "0" * 64
    assert "O13" in failures(data, s)


def test_o13_compares_the_saved_full_sigma_of_m_rerun_by_value() -> None:
    s = SYN[9]
    data = measured(s)
    r = data["run"]["E"]["M_rerun"]
    assert r["sigma_p_e"] == data["run"]["boundary"]["sigma_a"]["M"]                  # 全体を保存している
    assert r["sigma_p_e_sha256"] == M.sigma_sha256(r["sigma_p_e"])                     # SHA-256 は補助
    roles = data["run"]["roles"]
    cid = sorted(data["run"]["W_0"])[0]
    for tamper in (lambda x: x["units"][roles["other"]].update(activity=x["units"][roles["other"]]["activity"] + 1e-9),
                   lambda x: x["connections"][cid].update(pre_trace=x["connections"][cid]["pre_trace"] + 1e-9),
                   lambda x: x["world"].update(next_rid=x["world"]["next_rid"] + 1)):
        data = measured(s)
        sig = data["run"]["E"]["M_rerun"]["sigma_p_e"]
        tamper(sig)
        data["run"]["E"]["M_rerun"]["sigma_p_e_sha256"] = M.sigma_sha256(sig)          # SHA-256 も合わせた改ざん
        assert "O13" in failures(data, s)


def test_meta_blind_must_match_the_mode() -> None:
    s = SYN[0]
    data = measured(s)
    data["meta"]["blind"] = "no"
    assert "structure" in failures(data, s)
    assert AN.check_seed(dict(measured(s), meta=dict(measured(s)["meta"], blind=True)), "formal", s, SMALL)["structure"]


# ---- 一度限りの実行（guard と run.execute。dummy の計算。0036 と同じ） ------------------------------------------

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
        R.execute("formal", [30001], tmp_path / "o", repo, None, runner=_dummy, executor_factory=SerialExecutor)
    for seed in (30001, 30101, 29201):
        with pytest.raises(R.G.GuardError):
            R.execute("synthetic", [seed], tmp_path / f"o{seed}", repo, _git(repo, "rev-parse", "HEAD"), runner=_dummy,
                      executor_factory=SerialExecutor)
        assert not (tmp_path / f"o{seed}").exists()


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
    assert report["valid"] is True and report["judgment"]["J_C"]["status"] == "inconclusive"   # 3 個体なので m ＜ 10
    assert report["interval"]["computed"] is (report["judgment"]["J_C"]["m"] >= 1)


# ---- smoke の盲検：現象の数値を保存しない（0036 と同じ） -------------------------------------------------

FORBIDDEN_KEYS = ((AN.RUN_KEYS - {"seed", "plan", "roles"}) | AN.M_E_KEYS | AN.U_KEYS | AN.BOUNDARY_KEYS
                  | set().union(*AN.E_KEYS.values()) | JUDGMENT_KEYS | {"run"})
META_KEYS = {"experiment", "kind", "mode", "seed", "measurement_commit", "protocol_sha256", "protocol", "manifest", "blind"}
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
    s = SYN[0]
    for tamper, check in ((lambda r: r["E"]["Y"]["pulse_weights"][3][1].update({sorted(r["W_0"])[0]: 0.0}), "O5"),
                          (lambda r: r["U"]["M_WM"].update(sigma_end_sha256="0" * 64), "O10"),
                          (lambda r: r["U"]["M_W0"]["sigma_after_first"]["units"][r["roles"]["other"]].update(activity=9.0),
                           "O15")):
        data = measured(s)
        data["meta"]["blind"] = True
        tamper(data["run"])
        rec = R.blinded(data, "synthetic", s, SMALL)
        assert set(rec) == {"meta", "blind"} and rec["blind"]["checks"][check] == "fail"


def test_smoke_report_reads_blinded_records_and_rechecks_o12() -> None:
    s = SYN[0]
    data = measured(s)
    data["meta"]["blind"] = True
    rec = R.blinded(data, "synthetic", s, SMALL)
    rec["meta"]["mode"] = "smoke"
    report = AN.analyze_runs({s: rec}, "smoke", o1=[])
    assert set(report) == {"mode", "O1", "checks", "valid"} and report["checks"][str(s)]["O12"] == "fail"
    missing = copy.deepcopy(rec)
    missing["blind"]["checks"].pop("O15")
    assert AN.check_blinded(missing, s, "smoke") == {k: "fail" for k in AN.CHECK_NAMES}


def test_smoke_must_be_blind_and_formal_must_not(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    commit = _git(repo, "rev-parse", "HEAD")
    for mode, kw in (("smoke", {"blind": False}), ("formal", {"blind": True}), ("smoke", {"check_plan": SMALL})):
        out = tmp_path / f"o_{mode}_{sorted(kw)[0]}"
        with pytest.raises(R.G.GuardError):
            R.execute(mode, GUARD_SEEDS[:1], out, repo, commit, runner=_dummy, executor_factory=SerialExecutor, **kw)
        assert not out.exists()


# ---- O1 の証拠（0036 と同じ） ---------------------------------------------------------------------------

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
        return _Proc(0, "....\n150 passed in 9.0s\n")
    out = tmp_path / "out"
    rec = R.record_contract_tests(repo, out, commit, run=ok)
    assert rec["exit_code"] == 0 and calls[0][0][1:] == ["-m", "pytest", "-q", *AN.CONTRACT_TESTS]
    assert AN.o1_check(out, commit) == []
    R.record_contract_tests(repo, out, commit, run=lambda *a, **k: pytest.fail("走らせ直さない"))


def _never(*a, **k):
    raise AssertionError("O1 が成り立たないのに、契約テストの実行か seed の計算に進んだ")


@pytest.mark.parametrize("name,tamper", [
    ("終了コード", lambda r: r.update(exit_code=1)),
    ("結果の行", lambda r: r.update(summary="1 failed, 198 passed in 50.0s")),
    ("テストのファイルの SHA-256", lambda r: r["test_files_sha256"].update({AN.CONTRACT_TESTS[1]: "0" * 64})),
    ("走らせたコマンド", lambda r: r.update(command=["python", "-m", "pytest", "-q", AN.CONTRACT_TESTS[0]])),
    ("測定の commit", lambda r: r.update(measurement_commit="0" * 40)),
])
def test_a_broken_o1_record_stops_before_any_seed_is_started(repo, tmp_path, monkeypatch, name, tamper) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    commit = _o1_repo(repo)
    R.record_contract_tests(repo, out, commit, run=lambda *a, **k: _Proc(0, "199 passed in 50.0s\n"))
    path = out / AN.O1_FILE
    rec = json.loads(path.read_text(encoding="utf-8"))
    tamper(rec)
    path.write_text(json.dumps(rec), encoding="utf-8")
    with pytest.raises(R.G.GuardError):
        R.start("synthetic", GUARD_SEEDS[:2], out, repo, commit, run=_never, runner=_never, executor_factory=SerialExecutor)
    assert not (out / R.G.SEEDS_DIR).exists()


def test_a_valid_o1_record_lets_start_run_the_seeds(repo, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(R, "REPO", repo)
    out = tmp_path / "out"
    commit = _o1_repo(repo)
    R.record_contract_tests(repo, out, commit, run=lambda *a, **k: _Proc(0, "199 passed in 50.0s\n"))
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
