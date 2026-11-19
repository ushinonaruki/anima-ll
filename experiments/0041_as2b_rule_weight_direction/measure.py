"""実験 0041 の測定（確定した事前登録 v0.1：README §2・§8・§9、protocol.yaml。#189 merge `5fba79f`）。

seed ごとに measure_seed（1 個体で 3 本体。README §2.2）：
1. どの本体も関門の `run_body` と同じ組み立て（`build(seed, schedule=…, delay=L, rule_c=c, respond=True)`）。予定・o・W・L は、
   関門の宣言 v0.2 から取る（SHA-256 を確かめる。値をここに書き込まない：O2）。本体は経験の区間 E の終わりの境界 P_E で止める
   （窓 26〜50 は走らせない。README §2.1）。どの本体にも介入（移植・FREEZE・複製・世界の切り替え）をしない
2. 観測する本体 B^{A1}・B^{A2}（README §2.4 の T0〜T2）
   - T0：組み立てた直後の Σ を書き出す（Σ_0）
   - T1：1 Pulse ずつ P_E まで進め、Pulse ごとの 6 本の重みを実測して記録する（O6・O9）。共通の部分の最初の決まった窓 k* の
     意図の Pulse（決定の翌 Pulse）の処理の後の Σ を書き出す（O4。k* があるときだけ）。k* は B^{A1} の層 A の記録から見つけ、
     B^{A2} は同じ Pulse で書き出す。二つの本体がそこまで同じこと（SE-B1）は、analyze.py が O4 で確かめる
   - T2：P_E に着いた後に、P_E の Σ（値の全体）と SHA-256・層 A・層 B・発火・感覚の出来事・世界の記録を書き出す
3. B′^{A1}：B^{A1} と同じ組み立てで、この実験で足す記録（Σ の書き出し・Pulse ごとの重み・来歴のログの絞り込み）をしない。
   AS2b の道具の既定の来歴のログのまま、P_E まで一度に進める。走らせている間は状態を読まない（README §2.2 の観測の区分）。
   P_E に着いた後に、同じ終わりの記録を書き出す（O8）

生の記録だけを返す。δ・q・δ^←・ε・符号・k*・構造的な 0 の札・判定と推定の量は計算しない（analyze.py）。
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


A = _load("as2b_tools_for_0041", REPO / "experiments" / "as2b_choice" / "as2b.py")
AS1 = A.AS1
EVENT = A.RuntimeEventType


@dataclass(frozen=True)
class Plan:
    """測定の区間。本番の値は、関門の宣言と protocol から（formal_plan）。契約テストだけが小さい Plan を使う。"""

    first: int                # 手がかりの予定：c_k ＝ first ＋ spacing (k − 1)
    spacing: int
    count: int                # 予定の窓の数 K（関門の予定のまま。本体は P_E で止めるので、窓 E ＋ 1〜K は走らせない）
    offset: int               # o
    length: int               # W
    delay: int                # L
    e_windows: int            # 経験の区間 E の窓の数（E ＝ 窓 1〜e_windows）

    def schedule(self) -> "A.TrialSchedule":
        return A.TrialSchedule.periodic(first=self.first, spacing=self.spacing, count=self.count,
                                        offset=self.offset, length=self.length)

    @property
    def p_e(self) -> int:
        """境界 P_E：E の最後の窓の次の手がかりの直前（c_(E+1) − 1）。本体はここで止める。"""
        return self.first + self.spacing * self.e_windows - 1

    @property
    def boundaries(self) -> list[int]:
        """窓 k の境界 c_(k+1) − 1（k ＝ 1〜E。最後が P_E）。記述の重みの記録（R4）にだけ使う。"""
        return [self.first + self.spacing * k - 1 for k in range(1, self.e_windows + 1)]


BODIES = ("B_A1", "B_A2")                                       # 観測する本体（R-7 の二つの本体）
RERUN = "B_A1_rerun"                                            # B′^{A1}（観測しない）
SYSTEMS = BODIES + (RERUN,)                                     # protocol の bodies.per_individual と同じ順
RULE_OF = {"B_A1": "A1", "B_A2": "A2", RERUN: "A1"}
LOG_KEEP = frozenset({EVENT.SENSORY, EVENT.ACTIVITY, EVENT.DELTA})        # 観測する本体の来歴のログは感覚・発火・Delta（意図）だけ


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
    LC3 なし、二つの規則の本体、本体は可塑性あり・出口あり・世界が応じる・介入なし、役の乱数の流れ）だけを受け、それ以外は止める
    （読み替えない）。宣言の本体の長さ（bodies.pulses）は取らない（protocol の not_taken。本体は P_E で止める）。"""
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
    check_plan(plan)
    return plan


def check_plan(plan: Plan) -> None:
    """E が予定の中にあり、E の最後の窓の結果の刺激（b_E ＋ L）が P_E より前に成立すること（SE-B7 の算術）。"""
    plan.schedule().check(plan.delay)
    if not 1 <= plan.e_windows < plan.count:
        raise ValueError("E の窓の数は 1 以上で、予定の窓の数より少ない（P_E の次に手がかりがある）")
    _k, _a, b_e = plan.schedule().windows[plan.e_windows - 1]
    if not b_e + plan.delay < plan.p_e:
        raise ValueError("E の最後の窓の結果が P_E より前に成立しない")


def formal_plan(protocol: dict) -> Plan:
    decl, _ = gate_declaration(protocol)
    tl = protocol["timeline"]
    plan = plan_from_declaration(decl, int(tl["experience_E"]["windows"][1]))
    if not plan.p_e == tl["boundary_P_E"] == tl["runs_to"] == tl["experience_E"]["pulses"][1]:
        raise ValueError(f"区間（P_E ＝ {plan.p_e}）が protocol の timeline と違う")
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
    """Σ（JSON の形）の正規の書き出しの SHA-256（0035〜0040 と同じ）。"""
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


def _end_record(system) -> dict:
    """P_E の記録（どの本体も同じ形）。層 A・層 B・世界・来歴のログは出生からのすべて。P_E の Σ は値の全体と SHA-256。"""
    at_p_e = _sigma(system)
    return {
        "activity": [list(x) for x in system.log.activity()],
        "sensory": [list(x) for x in system.log.sensory()],
        "delta_log": _intent_log(system),
        "layer_a": [dict(r) for r in system.decider.records],
        "layer_b": [list(x) for x in system.world.intents],
        "audit": _jsonable(A.audit(system)),
        "world_end": _jsonable(system.world.export_state()),
        "sigma_p_e": at_p_e,
        "sigma_p_e_sha256": sigma_sha256(at_p_e),
        "history": _history(system),
        "pulse_end": system.pulse,
    }


def build_body(plan: Plan, seed: int, rule_c: str, *, log=None) -> "A.AS2bSystem":
    """関門の `run_body` と同じ組み立て（予定・L・規則 c・世界が応じる）。log を渡さなければ、関門と同じ既定の来歴のログ。"""
    kwargs = {} if log is None else {"log": log}
    return A.build(seed, schedule=plan.schedule(), delay=plan.delay, rule_c=rule_c, respond=True, **kwargs)


def _first_decided(system) -> dict | None:
    return next((r for r in system.decider.records if r["outcome"] in A.ACTION_IDS), None)


class _Probe:
    """k* の意図の Pulse（決定の翌 Pulse）の処理の後の Σ を、一度だけ書き出すための目印（0039 と同じ形）。

    detect が真の本体（B^{A1}）は、1 Pulse ごとに道具の層 A の記録から最初の決定を見つける。もう一方の本体（B^{A2}）は、
    同じ Pulse（dump_at）で書き出す。読むのは記録だけで、状態を変えない。
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


def _advance_each_pulse(system, until: int, order, rec: dict, probe: _Probe) -> None:
    """1 Pulse ずつ until まで進め、各 Pulse の処理の後の 6 本の重みを [Pulse, 重みの列] で実測して記録する（観測する本体だけ）。"""
    for pulse in range(system.pulse + 1, until + 1):
        A.advance_to(system.app, pulse)
        rec["pulse_weights"].append([pulse, _row(system, order)])
        probe.after(system, rec)


def measure_seed(protocol: dict, seed: int, plan: Plan | None = None) -> dict:
    plan = plan or formal_plan(protocol)
    check_plan(plan)
    p_e = plan.p_e

    # ---- 観測する本体 B^{A1}・B^{A2}（T0〜T2） ----
    bodies = {name: build_body(plan, seed, RULE_OF[name], log=AS1.AS1Log(keep=LOG_KEEP)) for name in BODIES}
    first = bodies["B_A1"]
    roles = first.roles
    birth_units = {u.unit_id: u.export_state() for u in first.app.units.all()}
    w_0 = _weights(first)                                   # 出生時の値
    order = sorted(w_0)
    steps: list[list] = []
    records: dict[str, dict] = {}
    probe_a1 = _Probe(True)
    for name in BODIES:
        system = bodies[name]
        rec: dict = {"sigma_0": _sigma(system), "pulse_weights": [], "first_intent": None}           # T0
        steps.append(["T0", name, system.pulse, "build", {"rule_c": RULE_OF[name], "respond": True}])
        probe = probe_a1 if name == "B_A1" else _Probe(False, probe_a1.dump_at)
        _advance_each_pulse(system, p_e, order, rec, probe)                                          # T1
        steps.append(["T1", name, system.pulse, "advance_each_pulse", {"from": 0}])
        records[name] = rec | _end_record(system)                                                    # T2
        steps.append(["T2", name, system.pulse, "end_records", None])

    # ---- B′^{A1}：同じ組み立て。足した記録をせず、既定のログのまま一度に進める（走らせている間は状態を読まない） ----
    rerun = build_body(plan, seed, RULE_OF[RERUN])
    steps.append(["T0", RERUN, rerun.pulse, "build", {"rule_c": RULE_OF[RERUN], "respond": True}])
    A.advance_to(rerun.app, p_e)
    steps.append(["T1", RERUN, rerun.pulse, "advance_to", {"from": 0}])
    records[RERUN] = _end_record(rerun)                     # P_E に着いた後に書き出す
    steps.append(["T2", RERUN, rerun.pulse, "end_records", None])

    return {
        "seed": seed,
        "plan": asdict(plan),
        "roles": roles.as_dict(),
        "birth_units": _jsonable(birth_units),
        "connection_order": order,
        "W_0": w_0,
        "steps": steps,
        "bodies": records,
    }


def protocol_from_file() -> dict:
    return yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
