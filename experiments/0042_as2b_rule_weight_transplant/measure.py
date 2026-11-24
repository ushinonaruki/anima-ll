"""実験 0042 の測定（確定した事前登録 v0.2：README §2・§8・§9、protocol.yaml。#195 merge `49d99e4`）。

seed ごとに measure_seed（1 個体で 17 系。README §2.2）：
1. 本体 B^{A1}・B^{A2}：関門の `run_body` と同じ組み立て（`build(seed, schedule=…, delay=L, rule_c=c, respond=True)`）。
   予定・o・W・L・本体の長さは、関門の宣言 v0.2 から取る（SHA-256 を確かめる。値をここに書き込まない：O2）
2. **S0**：B^{A1}・B^{A2} を P_E まで進める。組み立てた直後の Σ（Σ_0）と、E の共通の部分の最初の決まった窓 k* の意図の Pulse
   （決定の翌 Pulse）の処理の後の Σ を書き出す（SE-T2・O4。k* が E の中にあるときだけ。k* は B^{A1} の層 A の記録から見つけ、
   B^{A2} は同じ Pulse で書き出す）
3. **S1〜S4**（README §2.4。このあいだに Pulse を進めない）
   - S1：B^{A1}・B^{A2} の 6 本の重み W^{A1}・W^{A2} と、P_E の Σ（値の全体）を読む（本体は介入を持たない）
   - S2：B^c から 7 つずつ、14 の複製の系の元を丸ごと複製する（`clone`）
   - S3：移植する（`transplant`。6 本を一度に）。G^c[W^d]・N^c[W^d] ← W^d、G^c[W^c]^{tr} ← W^c、G^c[X1] ← X1、
     G^c[X2] ← X2。G^c[W^c]・N^c[W^c] は移植しない
   - S3′：N^c[W^c]・N^c[W^d] で `switch_world(respond=False)` を一度だけ呼ぶ。14 系の Σ の書き出し (a)
   - S4：14 系で、U の介入（6 本の FREEZE、advance）を一度の宣言で置く。Σ の書き出し (b)
4. **S5**：B^{A1}・B^{A2} と 14 系を、終わり（b_K ＋ L）まで進める。14 系は U の Pulse ごとの 6 本の重みと、Pulse P_E ＋ 1 の
   処理の後の Σ（O9）を記録する。17 系とも、終わりの Σ（値の全体）と SHA-256 を書き出す
5. B′^{A1}：関門の `run_body` と同じ組み立てと既定の来歴のログで、この実験で足す記録をしない。P_E まで一度に進めて Σ を書き出し、
   終わりまで一度に進めて Σ を書き出す。その二点のほかは、走らせている間に状態を読まない（README §2.2 の観測の区分）。
   終わりに着いた後に、層 A・層 B・発火・感覚の出来事の記録を書き出す（O13）

生の記録だけを返す。s・T とその成分・符号・k*・札・δ・判定と推定の量は計算しない（analyze.py）。
Core・設計図・Unit の力学・可塑性の規則・確定したパラメータ・AS2b の道具・関門の宣言は変えない。
"""

import hashlib
import importlib.util
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A = _load("as2b_tools_for_0042", REPO / "experiments" / "as2b_choice" / "as2b.py")
AS1 = A.AS1
EVENT = A.RuntimeEventType


@dataclass(frozen=True)
class Plan:
    """測定の区間。本番の値は、関門の宣言と protocol から（formal_plan）。契約テストだけが小さい Plan を使う。"""

    first: int                # 手がかりの予定：c_k ＝ first ＋ spacing (k − 1)
    spacing: int
    count: int                # 窓の数 K
    offset: int               # o
    length: int               # W
    delay: int                # L
    e_windows: int            # 経験の区間 E の窓の数（E ＝ 窓 1〜e_windows、U ＝ 残り）

    def schedule(self) -> "A.TrialSchedule":
        return A.TrialSchedule.periodic(first=self.first, spacing=self.spacing, count=self.count,
                                        offset=self.offset, length=self.length)

    @property
    def p_e(self) -> int:
        """境界 P_E：U の最初の窓の手がかりの直前（c_(E+1) − 1）。"""
        return self.first + self.spacing * self.e_windows - 1

    @property
    def end(self) -> int:
        """本体の長さ：b_K ＋ L。"""
        return self.first + self.spacing * (self.count - 1) + self.offset + self.length - 1 + self.delay


# ---- 系（README §2.2。protocol の systems.per_individual と同じ順） -------------------------------------------

BODIES = ("B_A1", "B_A2")                                       # 本体（R-7 の二つの本体）。観測する
RERUN = "B_A1_rerun"                                            # B′^{A1}。観測しない
G_MAIN = ("G_A1_WA1", "G_A1_WA2", "G_A1_WA1_tr", "G_A2_WA2", "G_A2_WA1", "G_A2_WA2_tr")
G_EXTREMES = ("G_A1_X1", "G_A1_X2", "G_A2_X1", "G_A2_X2")
N_SYSTEMS = ("N_A1_WA1", "N_A1_WA2", "N_A2_WA2", "N_A2_WA1")
CLONES = G_MAIN + G_EXTREMES + N_SYSTEMS                        # P_E から走らせる 14 系
SYSTEMS = BODIES + (RERUN,) + CLONES
RULE_OF = {"B_A1": "A1", "B_A2": "A2", RERUN: "A1"} | {n: n.split("_")[1] for n in CLONES}
BACKGROUND = {n: f"B_{RULE_OF[n]}" for n in CLONES}             # 複製の元の本体
WEIGHTS_OF = {n: (n.split("_")[2][1:] if n.split("_")[2].startswith("W") else n.split("_")[2]) for n in CLONES}
# 各複製の系の U の 6 本の重み：A1 → W^{A1}、A2 → W^{A2}、X1・X2 → 端の値（S4 の FREEZE の値。O7）
TRANSPLANTS = {n: WEIGHTS_OF[n] for n in CLONES if WEIGHTS_OF[n] != RULE_OF[n] or n.endswith("_tr")}
# S3：移植する系 → 移植の先。G^c[W^c]・N^c[W^c] は移植しない
NO_RESPONSE = N_SYSTEMS                                          # S3′ で世界の応答を切る系
SAME_BACKGROUND_PAIRS = (("G_A1_WA1", "G_A1_WA2"), ("G_A2_WA2", "G_A2_WA1"),
                         ("G_A1_WA1", "G_A1_X1"), ("G_A1_WA1", "G_A1_X2"), ("G_A2_WA2", "G_A2_X1"), ("G_A2_WA2", "G_A2_X2"),
                         ("N_A1_WA1", "N_A1_WA2"), ("N_A2_WA2", "N_A2_WA1"))     # SE-T5・O9：重みだけが違う対
FEEDBACK_PAIRS = (("G_A1_WA1", "N_A1_WA1"), ("G_A2_WA2", "N_A2_WA2"))            # SE-T6・O10：世界の応答だけが違う対
IDENTITIES = (("G_A1_WA1", "G_A1_WA1_tr"), ("G_A2_WA2", "G_A2_WA2_tr"))          # SE-T4・O8：自分の値の移植
STRUCTURAL_PAIRS = (("G_A1_WA1", "G_A1_WA2"), ("G_A2_WA2", "G_A2_WA1"),
                    ("N_A1_WA1", "N_A1_WA2"), ("N_A2_WA2", "N_A2_WA1"))          # SE-T7：W^{A1} ＝ W^{A2} なら同じ系
R6_PAIRS = (("G_A1_WA1", "G_A1_WA2"), ("G_A2_WA2", "G_A2_WA1"), ("G_A1_X1", "G_A1_X2"), ("G_A2_X1", "G_A2_X2"),
            ("N_A1_WA1", "N_A1_WA2"), ("N_A2_WA2", "N_A2_WA1"), ("G_A1_WA1", "N_A1_WA1"), ("G_A2_WA2", "N_A2_WA2"))
LOG_KEEP = frozenset({EVENT.SENSORY, EVENT.ACTIVITY, EVENT.DELTA})        # 来歴のログは感覚・発火・Delta（意図）だけ
S3P_LABEL, S4_LABEL = "S3'", "S4"
ROLES6 = ("C_to_source1", "source1_to_C", "C_to_source2", "source2_to_C", "source1_to_source2", "source2_to_source1")


# ---- 関門の宣言（README §1.1・O2） -----------------------------------------------------------------

def gate_declaration(protocol: dict) -> tuple[dict, str]:
    """関門の宣言を読み、SHA-256 が protocol の値（v0.2）と同じことを確かめる。(宣言, SHA-256) を返す。"""
    gate = protocol["inherited_gate_set"]
    raw = (REPO / gate["declaration"]).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != gate["sha256"]:
        raise ValueError(f"関門の宣言の SHA-256 が {digest}（protocol は {gate['sha256']}）。走らせない")
    return json.loads(raw), digest


def plan_from_declaration(decl: dict, e_windows: int) -> Plan:
    """宣言の予定・o・W・L から Plan を作る。この道具が実現する形（同時は引き分け、結果は手がかりの Receptor に 1 予約 1 出来事、
    LC3 なし、本体は可塑性あり・出口あり・世界が応じる・介入なし）だけを受け、それ以外は止める（読み替えない）。
    本体の長さ（bodies.pulses）が b_K ＋ L と同じことも確かめる（この実験は宣言の本体の長さまで走らせる）。"""
    w, b, cp = decl["world"], decl["bodies"], decl["schedule"]["cue_pulses"]
    problems = []
    if decl["exit"]["tie_rule"] != "close_window_without_intent":
        problems.append("tie_rule")
    if w["consequence_receptor"] != "cue_receptor" or w["multiplicity"] != AS1.PER_RESERVATION or w["lc3"] is not None:
        problems.append("world")
    if w["rule_c_assignment"] != "both_values_as_separate_bodies" \
            or [x["rule_c"] for x in b["per_individual"]] != list(A.ACTION_IDS):
        problems.append("rule_c")
    if (b["plasticity"], b["outlet"], b["respond"], b["interventions"]) != ("on", True, True, "none"):
        problems.append("bodies")
    if decl["roles"] != {"stream": "as2b-roles-{seed}", "action_ids": {"source1": "A1", "source2": "A2"}}:
        problems.append("roles")
    if problems:
        raise ValueError(f"この道具が実現しない宣言の欄: {problems}")
    plan = Plan(cp["first"], cp["spacing"], cp["count"], decl["schedule"]["window_offset_o"],
                decl["schedule"]["window_length_W"], w["delay_L"], e_windows)
    if plan.end != b["pulses"]:
        raise ValueError(f"本体の長さ {b['pulses']} が b_K ＋ L ＝ {plan.end} と違う")
    return plan


def formal_plan(protocol: dict) -> Plan:
    decl, _ = gate_declaration(protocol)
    tl = protocol["timeline"]
    plan = plan_from_declaration(decl, int(tl["experience_E"]["windows"][1]))
    if (plan.p_e, plan.end) != (tl["boundary_P_E"], tl["body_pulses"]):
        raise ValueError(f"区間（P_E ＝ {plan.p_e}、終わり ＝ {plan.end}）が protocol の timeline と違う")
    return plan


def check_plan(plan: Plan) -> None:
    plan.schedule().check(plan.delay)
    if not 1 <= plan.e_windows < plan.count:
        raise ValueError("E と U の両方に窓が要る")


def manifest_raw() -> dict:
    return AS1.as1_manifest_raw()


def extremes(protocol: dict) -> dict[str, dict[str, float]]:
    """人工の端 X1・X2 の 6 本（役の名前 → 値。protocol の extremes。README §1.2）。"""
    ex = protocol["extremes"]
    return {"X1": {r: float(ex["X1"][r]) for r in ROLES6}, "X2": {r: float(ex["X2"][r]) for r in ROLES6}}


def role_cids(roles) -> dict[str, str]:
    """役の名前（C_to_source1 など）→ 接続の ID（"<送り手>.main-><受け手>"）。C は手がかりの Unit。"""
    c, s1, s2 = roles["cue"], roles["source1"], roles["source2"]
    return {"C_to_source1": f"{c}.main->{s1}", "source1_to_C": f"{s1}.main->{c}",
            "C_to_source2": f"{c}.main->{s2}", "source2_to_C": f"{s2}.main->{c}",
            "source1_to_source2": f"{s1}.main->{s2}", "source2_to_source1": f"{s2}.main->{s1}"}


# ---- 記録の形 --------------------------------------------------------------------------------

def _jsonable(x):
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    return x


def sigma_sha256(sigma_json) -> str:
    """Σ（JSON の形）の正規の書き出しの SHA-256（0035〜0041 と同じ）。"""
    canonical = json.dumps(json.loads(json.dumps(sigma_json)), separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _sigma(system) -> dict:
    return _jsonable(A.sigma(system))


def _weights(system) -> dict[str, float]:
    return {cid: v["weight"] for cid, v in sorted(system.app.connections.export_state().items())}


def _row(system, order) -> list[float]:
    state = system.app.connections.export_state()
    return [state[cid]["weight"] for cid in order]


def _history(system) -> list:
    return [[b, label, [[iv.kind, sorted(iv.targets), iv.trace_policy] for iv in active]]
            for b, label, active in system.connections.history]


def _intent_log(system) -> list:
    """来歴のログの Delta の出来事のうち、意図のもの：[Pulse, Delta の識別子, 出どころ, 行動 ID]（層 B と同じ形）。"""
    return [[e.data["created_pulse"], e.data["delta_id"], e.data["source_id"], e.data["payload"]]
            for e in system.log.of(EVENT.DELTA) if e.data["kind"] == A.DeltaKind.INTENT]


CLONE_AUDIT_DROPS = ("ok", "log_matches_world")


def _end_record(system, *, clone: bool = False) -> dict:
    """終わりの記録（どの系も同じ形）。層 A・層 B・世界は出生からのすべて。終わりの Σ は値の全体と SHA-256。

    複製の系の来歴のログは、複製の後（U）だけを持つ。そのため道具の突合（audit）の「来歴のログ ＝ 世界」は、出生からの
    世界の記録とは構成上合わない。複製の系では、その欄と、それを含む ok を記録から外す（analyze.py が、保存した層 A・層 B・
    U の来歴のログから CT-E10 を計算し直す：O3。0039 と同じ）。
    """
    audit = _jsonable(A.audit(system))
    if clone:
        audit = {k: v for k, v in audit.items() if k not in CLONE_AUDIT_DROPS}
    at_end = _sigma(system)
    return {
        "activity": [list(x) for x in system.log.activity()],
        "sensory": [list(x) for x in system.log.sensory()],
        "delta_log": _intent_log(system),
        "layer_a": [dict(r) for r in system.decider.records],
        "layer_b": [list(x) for x in system.world.intents],
        "audit": audit,
        "world_end": _jsonable(system.world.export_state()),
        "world_switches": _jsonable(system.meta.get("world_switches", [])),
        "sigma_end": at_end,
        "sigma_end_sha256": sigma_sha256(at_end),
        "history": _history(system),
        "pulse_end": system.pulse,
    }


def build_body(plan: Plan, seed: int, rule_c: str, *, log=None) -> "A.AS2bSystem":
    """関門の `run_body` と同じ組み立て（予定・L・規則 c・世界が応じる）。log を渡さなければ、関門と同じ既定の来歴のログ。"""
    kwargs = {} if log is None else {"log": log}
    return A.build(seed, schedule=plan.schedule(), delay=plan.delay, rule_c=rule_c, respond=True, **kwargs)


def _freeze_six(six: frozenset[str]) -> list:
    return [AS1.Intervention(AS1.FREEZE, six, AS1.ADVANCE)]


def _first_decided(system) -> dict | None:
    return next((r for r in system.decider.records if r["outcome"] in A.ACTION_IDS), None)


class _Probe:
    """E の共通の部分の k* の意図の Pulse（決定の翌 Pulse）の処理の後の Σ を、一度だけ書き出すための目印（0039・0041 と同じ形）。

    detect が真の本体（B^{A1}）は、E の窓の中を 1 Pulse ずつ進めて、最初の決定を道具の層 A の記録から見つける（E の窓だけ）。
    もう一方の本体（B^{A2}）は、同じ Pulse（dump_at）で書き出す。読むのは記録だけで、状態を変えない。
    """

    def __init__(self, detect: bool, e_windows: int, dump_at: int | None = None) -> None:
        self.detect, self.e_windows, self.dump_at, self.done = detect, e_windows, dump_at, False

    def after(self, system, rec: dict) -> None:
        if self.detect and self.dump_at is None:
            first = _first_decided(system)
            if first is not None and first["window"] <= self.e_windows:
                self.dump_at = first["decision_pulse"] + 1
        if self.dump_at is not None and self.dump_at == system.pulse and not self.done:
            rec["first_intent"] = {"pulse": system.pulse, "sigma": _sigma(system)}
            self.done = True


def _advance_body(system, until: int, plan: Plan, rec: dict, probe: _Probe) -> None:
    """本体を until まで進める。最初の決定が見つかるまでは、E の窓の中を 1 Pulse ずつ進める（記録は読むだけ）。"""
    windows = [w for w in plan.schedule().windows if w[0] <= plan.e_windows]
    while system.pulse < until:
        p = system.pulse
        stops = [until]
        if probe.dump_at is not None and not probe.done and probe.dump_at > p:
            stops.append(probe.dump_at)
        if probe.detect and probe.dump_at is None:
            if any(a <= p + 1 <= b for _k, a, b in windows):
                stops.append(p + 1)
            else:
                nxt = min((a for _k, a, _b in windows if a > p + 1), default=None)
                if nxt is not None:
                    stops.append(nxt - 1)
        q = min(s for s in stops if s > p)
        A.advance_to(system.app, min(q, until))
        probe.after(system, rec)


def _advance_each_pulse(system, until: int, order, rec: dict) -> None:
    """1 Pulse ずつ until まで進め、各 Pulse の処理の後の 6 本の重みを [Pulse, 重みの列] で実測して記録する（O7 の証拠）。"""
    for pulse in range(system.pulse + 1, until + 1):
        A.advance_to(system.app, pulse)
        rec["pulse_weights"].append([pulse, _row(system, order)])


def measure_seed(protocol: dict, seed: int, plan: Plan | None = None) -> dict:
    plan = plan or formal_plan(protocol)
    check_plan(plan)
    p_e, end = plan.p_e, plan.end
    x_by_role = extremes(protocol)

    # ---- S0：本体 B^{A1}・B^{A2} を P_E まで ----
    bodies = {name: build_body(plan, seed, RULE_OF[name], log=AS1.AS1Log(keep=LOG_KEEP)) for name in BODIES}
    first = bodies["B_A1"]
    roles = first.roles
    birth_units = {u.unit_id: u.export_state() for u in first.app.units.all()}
    w_0 = _weights(first)                                   # 出生時の値
    order = sorted(w_0)
    six = frozenset(order)
    cids = role_cids(roles.as_dict())
    if set(cids.values()) != six:
        raise ValueError("役の名前と接続の ID の対応が、6 本の可塑的な接続と合わない")
    x_values = {key: {cids[r]: v for r, v in vals.items()} for key, vals in x_by_role.items()}
    records: dict[str, dict] = {name: {"sigma_0": _sigma(bodies[name]), "first_intent": None} for name in BODIES}
    probes = {"B_A1": _Probe(True, plan.e_windows)}
    steps: list[list] = []
    for name in BODIES:
        if name == "B_A2":
            probes[name] = _Probe(False, plan.e_windows, probes["B_A1"].dump_at)
        _advance_body(bodies[name], p_e, plan, records[name], probes[name])
        steps.append(["S0", name, bodies[name].pulse, "advance_to", {"from": 0}])

    # ---- S1〜S4（このあいだに Pulse を進めない） ----
    weights, sigma_p_e = {}, {}
    for name in BODIES:                                                       # S1
        weights[RULE_OF[name]] = _weights(bodies[name])
        sigma_p_e[name] = _sigma(bodies[name])
        steps.append(["S1", name, bodies[name].pulse, "read_weights_and_sigma", None])
    targets = {"A1": weights["A1"], "A2": weights["A2"]} | x_values
    clones: dict[str, A.AS2bSystem] = {}
    for name in CLONES:                                                       # S2
        clones[name] = A.clone(bodies[BACKGROUND[name]])
        steps.append(["S2", name, clones[name].pulse, "clone", {"from": BACKGROUND[name]}])
    for name, key in TRANSPLANTS.items():                                     # S3
        state_before = _jsonable(clones[name].connections.export_intervention_state())
        clones[name].transplant(targets[key])
        steps.append(["S3", name, clones[name].pulse, "transplant",
                      {"to": f"W_{key}" if key in A.ACTION_IDS else key, "intervention_state_at_transplant": state_before}])
    for name in NO_RESPONSE:                                                  # S3′
        clones[name].switch_world(False, label=S3P_LABEL)
        steps.append(["S3'", name, clones[name].pulse, "switch_world", {"respond": False}])
    sigma_a = {name: _sigma(clones[name]) for name in CLONES}
    for name in CLONES:                                                       # S4
        clones[name].declare(_freeze_six(six), label=S4_LABEL)
        steps.append(["S4", name, clones[name].pulse, "declare", {"FREEZE": sorted(six), "trace_policy": AS1.ADVANCE}])
    sigma_b = {name: _sigma(clones[name]) for name in CLONES}

    # ---- S5：本体と 14 系を終わりまで ----
    for name in BODIES:
        A.advance_to(bodies[name].app, end)
        records[name] |= _end_record(bodies[name])
        steps.append(["S5", name, bodies[name].pulse, "advance_to", {"from": p_e}])
    clone_records = {}
    for name in CLONES:
        s = clones[name]
        rec: dict = {"pulse_weights": []}
        _advance_each_pulse(s, p_e + 1, order, rec)
        rec["sigma_after_first"] = _sigma(s)                                  # Pulse P_E ＋ 1 の処理の後（O9）
        _advance_each_pulse(s, end, order, rec)
        clone_records[name] = rec | _end_record(s, clone=True)
        steps.append(["S5", name, s.pulse, "advance_to", {"from": p_e}])

    # ---- B′^{A1}：関門と同じ組み立てと既定のログで、足した記録をしない（P_E と終わりの二点のほかは状態を読まない） ----
    rerun = build_body(plan, seed, RULE_OF[RERUN])
    A.advance_to(rerun.app, p_e)
    rerun_p_e = _sigma(rerun)
    A.advance_to(rerun.app, end)
    records[RERUN] = {"sigma_p_e": rerun_p_e, "sigma_p_e_sha256": sigma_sha256(rerun_p_e)} | _end_record(rerun)

    return {
        "seed": seed,
        "plan": asdict(plan),
        "roles": roles.as_dict(),
        "birth_units": _jsonable(birth_units),
        "connection_order": order,
        "W_0": w_0,
        "X": x_values,
        "bodies": records,
        "boundary": {"steps": steps, "W": weights, "sigma_p_e": sigma_p_e,
                     "sigma_p_e_sha256": {n: sigma_sha256(sigma_p_e[n]) for n in BODIES},
                     "sigma_a": sigma_a, "sigma_b": sigma_b},
        "clones": clone_records,
    }


def protocol_from_file() -> dict:
    return yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
