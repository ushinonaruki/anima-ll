"""実験 0039 の測定（確定した事前登録 v0.2：README §2・§8・§9、protocol.yaml。#179 merge `ba7ffba`）。

seed ごとに measure_seed（1 個体で 11 系。README §2.2）：
1. 本体 B^{A1}・B^{A2}：関門の `run_body` と同じ組み立て（`build(seed, schedule=…, delay=L, rule_c=c, respond=True)`）。
   予定・o・W・L・本体の長さは、関門の宣言 v0.2 から取る（SHA-256 を確かめる。値をここに書き込まない：O2）
2. **S0**：B^{A1}・B^{A2} を P_E まで進める。窓の境界（c_k − 1）ごとに 6 本の重みを記録し、最初の決まった窓の意図の Pulse の
   処理の後の Σ を書き出す（SE-1・O4 の証拠）。P_E の Σ を書き出す
3. **S1〜S4**（README §2.4。このあいだに Pulse を進めない）
   - S1：B^{A1}・B^{A2} の 6 本の重み W^{A1}・W^{A2} を読む（本体は介入を持たない）
   - S2：B^c から G^c[W^c]・G^c[W^d]・G^c[W^c]^{tr} を複製する（M1）
   - S3：複製に移植する（G^c[W^d] ← W^d、G^c[W^c]^{tr} ← W^c。G^c[W^c] は移植しない）。Σ の書き出し (a)
   - S4：6 つの G の系で、U の介入（6 本の FREEZE、advance）を一度だけ宣言する。Σ の書き出し (b)
4. **S5**：B^{A1}・B^{A2} と 6 つの G の系を、終わり（b_K ＋ L）まで進める。G は Pulse ごとの 6 本の重みと、Pulse P_E ＋ 1 の
   処理の後の Σ（O10）を記録する
5. LC1 の本体 F^{A1}・F^{A2}（境界 0 で 6 本の FREEZE）を、Pulse ごとの 6 本の重みを記録しながら終わりまで進める
6. B′^{A1}：関門の `run_body` と同じ組み立てで、この実験で足す記録（窓の境界の重み・最初の意図の Σ・複製）をしない。
   P_E と終わりの Σ だけを取る（O13）

生の記録だけを返す。A1 の割合・差・符号・適格・判定の量は計算しない（analyze.py）。
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


A = _load("as2b_tools_for_0039", REPO / "experiments" / "as2b_choice" / "as2b.py")
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


BODIES = ("B_A1", "B_A2")                                       # 本体（R-7 の二つの本体）
FROZEN_BODIES = ("F_A1", "F_A2")                                # LC1（境界 0 で 6 本の FREEZE）
RERUN = "B_A1_rerun"                                            # B′^{A1}
G_SYSTEMS = ("G_A1_WA1", "G_A1_WA2", "G_A1_WA1_tr", "G_A2_WA2", "G_A2_WA1", "G_A2_WA2_tr")
SYSTEMS = BODIES + (RERUN,) + FROZEN_BODIES + G_SYSTEMS         # protocol の systems.per_individual と同じ順
RULE_OF = {"B_A1": "A1", "B_A2": "A2", "B_A1_rerun": "A1", "F_A1": "A1", "F_A2": "A2",
           "G_A1_WA1": "A1", "G_A1_WA2": "A1", "G_A1_WA1_tr": "A1", "G_A2_WA2": "A2", "G_A2_WA1": "A2", "G_A2_WA2_tr": "A2"}
BACKGROUND = {name: f"B_{RULE_OF[name]}" for name in G_SYSTEMS}                          # 複製の元の本体
TRANSPLANTS = {"G_A1_WA2": "A2", "G_A1_WA1_tr": "A1", "G_A2_WA1": "A1", "G_A2_WA2_tr": "A2"}   # S3：系 → 移植の先 W^d
FROZEN_VALUE = {"G_A1_WA1": "A1", "G_A1_WA2": "A2", "G_A1_WA1_tr": "A1",
                "G_A2_WA2": "A2", "G_A2_WA1": "A1", "G_A2_WA2_tr": "A2"}                  # S4 の FREEZE の値（O8）
PAIRS = (("G_A1_WA1", "G_A1_WA2"), ("G_A2_WA2", "G_A2_WA1"))    # 同じ背景で、重みだけが違う対（SE-6・O10）
IDENTITIES = (("G_A1_WA1", "G_A1_WA1_tr"), ("G_A2_WA2", "G_A2_WA2_tr"))   # 自分の重みの移植（SE-4・O9）
LOG_KEEP = frozenset({EVENT.SENSORY, EVENT.ACTIVITY, EVENT.DELTA})        # 来歴のログは感覚・発火・Delta（意図）だけ
E_LABEL, S4_LABEL = "E", "S4"


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
    LC3 なし、本体は可塑性あり・出口あり・世界が応じる・介入なし）だけを受け、それ以外は止める（読み替えない）。"""
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
    if (plan.p_e, plan.end) != (tl["P_E"], tl["runs_to"]):
        raise ValueError(f"区間（P_E ＝ {plan.p_e}、終わり ＝ {plan.end}）が protocol の timeline と違う")
    return plan


def manifest_raw() -> dict:
    return AS1.as1_manifest_raw()


# ---- 記録の形 --------------------------------------------------------------------------------

def _jsonable(x):
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    return x


def sigma_sha256(sigma_json) -> str:
    """Σ（JSON の形）の正規の書き出しの SHA-256（0035〜0037 と同じ）。"""
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
    """終わりの記録（どの系も同じ形）。層 A・層 B・世界は出生からのすべて。

    複製の系（G）の来歴のログは、複製の後（U）だけを持つ。そのため道具の突合（audit）の「来歴のログ ＝ 世界」は、出生からの
    世界の記録とは構成上合わない。複製の系では、その欄と、それを含む ok を記録から外す（analyze.py が、保存した層 A・層 B・
    U の来歴のログから CT-E10 を計算し直す：O3）。
    """
    audit = _jsonable(A.audit(system))
    if clone:
        audit = {k: v for k, v in audit.items() if k not in CLONE_AUDIT_DROPS}
    return {
        "activity": [list(x) for x in system.log.activity()],
        "sensory": [list(x) for x in system.log.sensory()],
        "delta_log": _intent_log(system),
        "layer_a": [dict(r) for r in system.decider.records],
        "layer_b": [list(x) for x in system.world.intents],
        "audit": audit,
        "world_end": _jsonable(system.world.export_state()),
        "sigma_end_sha256": sigma_sha256(_sigma(system)),
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
    """最初の決まった窓の意図の Pulse（決定の翌 Pulse）の処理の後の Σ を、一度だけ書き出すための目印。

    detect が真の系（各対の A1 の側）は、窓の中を 1 Pulse ずつ進めて、最初の決定を道具の層 A の記録から見つける。
    もう一方の系は、同じ Pulse（dump_at）で書き出す。二つの系がそこまで同じこと（SE-1）は、analyze.py が O4 で確かめる。
    """

    def __init__(self, detect: bool, dump_at: int | None = None) -> None:
        self.detect, self.dump_at, self.done = detect, dump_at, False

    def after(self, system, rec: dict) -> None:
        if self.detect and self.dump_at is None:
            first = _first_decided(system)
            if first is not None:
                self.dump_at = first["decision_pulse"] + 1
        if self.dump_at == system.pulse and not self.done:
            rec["first_intent"] = {"pulse": system.pulse, "sigma": _sigma(system)}
            self.done = True


def _advance_body(system, until: int, plan: Plan, order, rec: dict, probe: _Probe) -> None:
    """本体を until まで進める。窓の境界（c_k − 1）で 6 本の重みを記録する。最初の決定が見つかるまでは、窓の中を 1 Pulse ずつ進める。"""
    windows = plan.schedule().windows
    marks = sorted(c - 1 for c in plan.schedule().cues)
    while system.pulse < until:
        p = system.pulse
        stops = [until] + [m for m in marks if m > p][:1]
        if probe.dump_at is not None and not probe.done and probe.dump_at > p:
            stops.append(probe.dump_at)
        if probe.detect and probe.dump_at is None:
            if any(a <= p + 1 <= b for _k, a, b in windows):
                stops.append(p + 1)
            else:
                nxt = min((a for _k, a, _b in windows if a > p + 1), default=None)
                stops.append(until if nxt is None else nxt - 1)
        q = min(s for s in stops if s > p)
        A.advance_to(system.app, min(q, until))
        if system.pulse in marks:
            rec["window_weights"].append([system.pulse, _row(system, order)])
        probe.after(system, rec)


def _advance_each_pulse(system, until: int, order, rec: dict, probe: _Probe | None = None) -> None:
    """1 Pulse ずつ until まで進め、各 Pulse の処理の後の 6 本の重みを [Pulse, 重みの列] で記録する（O6・O8 の証拠）。"""
    for pulse in range(system.pulse + 1, until + 1):
        A.advance_to(system.app, pulse)
        rec["pulse_weights"].append([pulse, _row(system, order)])
        if probe is not None:
            probe.after(system, rec)


def measure_seed(protocol: dict, seed: int, plan: Plan | None = None) -> dict:
    plan = plan or formal_plan(protocol)
    plan.schedule().check(plan.delay)
    if not 1 <= plan.e_windows < plan.count:
        raise ValueError("E と U の両方に窓が要る")
    p_e, end = plan.p_e, plan.end

    def log():
        return AS1.AS1Log(keep=LOG_KEEP)

    # ---- S0：本体 B^{A1}・B^{A2} を P_E まで ----
    bodies = {name: build_body(plan, seed, RULE_OF[name], log=log()) for name in BODIES}
    roles = bodies["B_A1"].roles
    birth_units = {u.unit_id: u.export_state() for u in bodies["B_A1"].app.units.all()}
    w_0 = _weights(bodies["B_A1"])                         # 出生時の値
    order = sorted(w_0)
    six = frozenset(order)
    records: dict[str, dict] = {name: {"sigma_0": _sigma(bodies[name]), "window_weights": [], "first_intent": None}
                                for name in BODIES}
    probes = {"B_A1": _Probe(True), "B_A2": _Probe(False)}
    steps: list[list] = []
    for name in BODIES:
        if name == "B_A2":
            probes[name].dump_at = probes["B_A1"].dump_at
        _advance_body(bodies[name], p_e, plan, order, records[name], probes[name])
        steps.append(["S0", name, bodies[name].pulse, "advance_to", {"from": 0}])
    sigma_p_e = {name: _sigma(bodies[name]) for name in BODIES}

    # ---- S1〜S4（このあいだに Pulse を進めない） ----
    weights = {}
    for name in BODIES:                                                       # S1
        weights[RULE_OF[name]] = _weights(bodies[name])
        steps.append(["S1", name, bodies[name].pulse, "read_weights", None])
    g: dict[str, A.AS2bSystem] = {}
    for name in G_SYSTEMS:                                                    # S2
        g[name] = A.clone(bodies[BACKGROUND[name]])
        steps.append(["S2", name, g[name].pulse, "clone", {"from": BACKGROUND[name]}])
    for name, key in TRANSPLANTS.items():                                     # S3
        state_before = _jsonable(g[name].connections.export_intervention_state())
        g[name].transplant(weights[key])
        steps.append(["S3", name, g[name].pulse, "transplant",
                      {"to": f"W_{key}", "intervention_state_at_transplant": state_before}])
    sigma_a = {name: _sigma(g[name]) for name in G_SYSTEMS}
    for name in G_SYSTEMS:                                                    # S4
        g[name].declare(_freeze_six(six), label=S4_LABEL)
        steps.append(["S4", name, g[name].pulse, "declare", {"FREEZE": sorted(six), "trace_policy": AS1.ADVANCE}])
    sigma_b = {name: _sigma(g[name]) for name in G_SYSTEMS}

    # ---- S5：本体と G の系を終わりまで ----
    for name in BODIES:
        if name == "B_A2" and probes[name].dump_at is None:
            probes[name].dump_at = probes["B_A1"].dump_at
        _advance_body(bodies[name], end, plan, order, records[name], probes[name])
        records[name] |= _end_record(bodies[name])
        steps.append(["S5", name, bodies[name].pulse, "advance_to", {"from": p_e}])
    g_records = {}
    for name in G_SYSTEMS:
        s = g[name]
        rec: dict = {"pulse_weights": []}
        _advance_each_pulse(s, p_e + 1, order, rec)
        rec["sigma_after_first"] = _sigma(s)                                  # Pulse P_E ＋ 1 の処理の後（O10）
        _advance_each_pulse(s, end, order, rec)
        g_records[name] = rec | _end_record(s, clone=True)
        steps.append(["S5", name, s.pulse, "advance_to", {"from": p_e}])

    # ---- LC1：F^{A1}・F^{A2}（境界 0 で 6 本の FREEZE） ----
    f_probe: dict[str, _Probe] = {}
    for name in FROZEN_BODIES:
        f = build_body(plan, seed, RULE_OF[name], log=log())
        f.declare(_freeze_six(six), label=E_LABEL)
        rec = {"sigma_0": _sigma(f), "pulse_weights": [], "first_intent": None}
        f_probe[name] = _Probe(True) if name == "F_A1" else _Probe(False, f_probe["F_A1"].dump_at)
        _advance_each_pulse(f, end, order, rec, f_probe[name])
        records[name] = rec | _end_record(f)

    # ---- B′^{A1}：関門と同じ組み立てと既定のログで、足した記録をしない ----
    rerun = build_body(plan, seed, RULE_OF[RERUN])
    A.advance_to(rerun.app, p_e)
    rerun_rec = {"sigma_p_e": _sigma(rerun)}
    A.advance_to(rerun.app, end)
    sigma_end = _sigma(rerun)
    records[RERUN] = rerun_rec | {"sigma_end": sigma_end} | _end_record(rerun)

    return {
        "seed": seed,
        "plan": asdict(plan),
        "roles": roles.as_dict(),
        "birth_units": _jsonable(birth_units),
        "connection_order": order,
        "W_0": w_0,
        "bodies": records,
        "boundary": {"steps": steps, "W": weights, "sigma_p_e": sigma_p_e, "sigma_a": sigma_a, "sigma_b": sigma_b},
        "G": g_records,
    }


def protocol_from_file() -> dict:
    return yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
