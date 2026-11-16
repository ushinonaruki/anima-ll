"""実験 0040 の測定（確定した事前登録 v0.2：README §2・§8・§9、protocol.yaml。#184 merge `9a8651a`）。

seed ごとに measure_seed（1 個体で 7 系。README §2.2）：
1. どの系も `build(seed, schedule=…, delay=L, rule_c="A1", respond=False)` で組み立てる。予定・o・W・L・本体の長さは、
   関門の宣言 v0.2 から取る（SHA-256 を確かめる。値をここに書き込まない：O2）。世界は意図を記録するだけで結果を返さない（WB-9）
2. Pulse 0 の操作（README §2.4。T0〜T2 のあいだに Pulse を進めない）
   - T0：組み立てた直後の Σ を書き出す
   - T1：X1・X2・M1・M2 は C ↔ 源 1・C ↔ 源 2 の 4 本をそれぞれの値に、X0^tr は 4 本を w0 に移植する（`transplant`）。X0 は移植しない。
     源 1 ↔ 源 2 の 2 本には触れない。移植の時の介入の状態（空のはず）を記録する。Σ を書き出す
   - T2：6 本の FREEZE（advance）を、各系で一度の宣言で置く（境界 0）。Σ を書き出す
3. T3：6 つの系（X1′ を除く）を 1 Pulse ずつ終わり（b_K ＋ L）まで進め、Pulse ごとの 6 本の重み（O6）と、3 つの Unit のどれかが
   最初に発火した Pulse t₁ の処理の後の Σ（O10）を記録する
4. X1′：X1 と同じ組み立て・同じ移植と FREEZE で、この実験で足す記録（Σ の書き出し・Pulse ごとの重み・t₁ の Σ・来歴のログの絞り込み）を
   しない。AS2b の道具の既定の来歴のログのまま、終わりまで一度に進め、終わりの Σ だけを取る（O9）

介入の値（README §2.3）は、C0 の設計図の w_min・w_max・w0 だけから作る（`intervention_values`。相手の値は引き算で作らず定数のまま置く）。
生の記録だけを返す。A1 の割合・差・符号・定まる・判定の量は計算しない（analyze.py）。
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


A = _load("as2b_tools_for_0040", REPO / "experiments" / "as2b_choice" / "as2b.py")
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
    e_windows: int            # 立ち上がりの区間 E の窓の数（E ＝ 窓 1〜e_windows、記述だけ。U ＝ 残り）

    def schedule(self) -> "A.TrialSchedule":
        return A.TrialSchedule.periodic(first=self.first, spacing=self.spacing, count=self.count,
                                        offset=self.offset, length=self.length)

    @property
    def last_e_pulse(self) -> int:
        """E の最後の Pulse：U の最初の窓の手がかりの直前（c_(E+1) − 1）。区間を分けるだけで、ここで操作はしない。"""
        return self.first + self.spacing * self.e_windows - 1

    @property
    def end(self) -> int:
        """本体の長さ：b_K ＋ L。"""
        return self.first + self.spacing * (self.count - 1) + self.offset + self.length - 1 + self.delay


RULE_C = "A1"                                                   # build に渡す値。結果を返さない世界では軌道に効かない（SE-A4）
VALUE_SYSTEMS = ("X1", "X2", "M1", "M2", "X0")                  # 値の系（SE-A2・O10）
IDENTITY = "X0_tr"                                              # 自分の値の移植（O8）
RERUN = "X1_rerun"                                              # X1′（O9）
SYSTEMS = (*VALUE_SYSTEMS, IDENTITY, RERUN)                     # protocol の systems.per_individual と同じ順
RECORDED = (*VALUE_SYSTEMS, IDENTITY)                           # Σ の書き出し・Pulse ごとの重みを記録する系
TRANSPLANTED = {"X1": "X1", "X2": "X2", "M1": "M1", "M2": "M2", IDENTITY: "X0_tr", RERUN: "X1"}   # 系 → 移植する値の組
PAIRS = (("X1", "X2"), ("M1", "M2"), ("X1", "X0"), ("X2", "X0"))                                  # R5 の対
ROLE_KEYS = ("C_to_source1", "source1_to_C", "C_to_source2", "source2_to_C")
LOG_KEEP = frozenset({EVENT.SENSORY, EVENT.ACTIVITY, EVENT.DELTA})        # 来歴のログは感覚・発火・Delta（意図）だけ
T2_LABEL = "T2"


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
    """宣言の予定・o・W・L から Plan を作る。この道具が引き継ぐ欄（同時は引き分け、結果の規則は手がかりの Receptor に 1 予約 1 出来事、
    LC3 なし、役の乱数の流れ）が宣言のとおりであることを確かめ、それ以外は止める（読み替えない）。宣言の本体の欄（二つの規則の本体・
    可塑性・世界が応じる）は、この実験では取らない（protocol の not_taken。すべての系で respond は偽、6 本は FREEZE）。"""
    w, b, cp = decl["world"], decl["bodies"], decl["schedule"]["cue_pulses"]
    problems = []
    if decl["exit"]["tie_rule"] != "close_window_without_intent":
        problems.append("tie_rule")
    if w["consequence_receptor"] != "cue_receptor" or w["multiplicity"] != AS1.PER_RESERVATION or w["lc3"] is not None:
        problems.append("world")
    if decl["roles"] != {"stream": "as2b-roles-{seed}", "action_ids": {"source1": "A1", "source2": "A2"}}:
        problems.append("roles")
    if problems:
        raise ValueError(f"この道具が引き継がない宣言の欄: {problems}")
    plan = Plan(cp["first"], cp["spacing"], cp["count"], decl["schedule"]["window_offset_o"],
                decl["schedule"]["window_length_W"], w["delay_L"], e_windows)
    if plan.end != b["pulses"]:
        raise ValueError(f"本体の長さ {b['pulses']} が b_K ＋ L ＝ {plan.end} と違う")
    return plan


def formal_plan(protocol: dict) -> Plan:
    decl, _ = gate_declaration(protocol)
    tl = protocol["timeline"]
    plan = plan_from_declaration(decl, int(tl["lead_in_E"]["windows"][1]))
    if (plan.last_e_pulse, plan.end) != (tl["lead_in_E"]["pulses"][1], tl["runs_to"]):
        raise ValueError(f"区間（E の終わり ＝ {plan.last_e_pulse}、終わり ＝ {plan.end}）が protocol の timeline と違う")
    return plan


def manifest_raw() -> dict:
    return AS1.as1_manifest_raw()


# ---- 介入の値（README §2.3） ---------------------------------------------------------------------------

def c0_weights() -> tuple[float, float, float]:
    """C0 の設計図（AS2b の設計図の可塑性の欄と、可塑的な接続の出生時の値）から (w_min, w_max, w0)。"""
    parsed = A.parse_neuroarchitecture(manifest_raw())
    plastic = {p.weight for p in parsed.projections if p.plastic}
    if len(plastic) != 1:
        raise ValueError("可塑的な接続の出生時の値が一つではない")
    return float(parsed.plasticity.w_min), float(parsed.plasticity.w_max), float(plastic.pop())


def intervention_values(w_min: float, w_max: float, w0: float) -> dict[str, dict[str, float]]:
    """系 → 役の名前の 4 本の値（README §2.3 の表）。端は [w_min, w_max] の両端、中間は 3 w_max/4 と w_max/4、参照は w0。
    相手の値は定数のまま置き、引き算で作らない。どの組も、和が二進の浮動小数でちょうど w_max になることを確かめる。"""
    if w_min != 0.0 or w0 != w_max / 2:
        raise ValueError("C0 の w_min ＝ 0、w0 ＝ w_max/2 を前提にしている")
    hi, lo = w_max * 3 / 4, w_max / 4

    def four(c_s1: float, s1_c: float, c_s2: float, s2_c: float) -> dict[str, float]:
        out = dict(zip(ROLE_KEYS, (c_s1, s1_c, c_s2, s2_c), strict=True))
        for a, b in (("C_to_source1", "source1_to_C"), ("C_to_source2", "source2_to_C")):
            if out[a] + out[b] != w_max or not (w_min <= out[a] <= w_max and w_min <= out[b] <= w_max):
                raise ValueError(f"組 {a}・{b} が F1 か範囲を満たさない")
        return out

    return {"X1": four(w_max, w_min, w_min, w_max), "X2": four(w_min, w_max, w_max, w_min),
            "M1": four(hi, lo, lo, hi), "M2": four(lo, hi, hi, lo), "X0_tr": four(w0, w0, w0, w0)}


def role_connections(roles) -> dict[str, str]:
    """役の名前 → 接続の識別子（送り手.main->受け手）。"""
    c, s1, s2 = roles.cue, roles.source1, roles.source2
    return {"C_to_source1": f"{c}.main->{s1}", "source1_to_C": f"{s1}.main->{c}",
            "C_to_source2": f"{c}.main->{s2}", "source2_to_C": f"{s2}.main->{c}"}


# ---- 記録の形 --------------------------------------------------------------------------------

def _jsonable(x):
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    return x


def sigma_sha256(sigma_json) -> str:
    """Σ（JSON の形）の正規の書き出しの SHA-256（0035〜0039 と同じ）。"""
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
    """終わりの記録（どの系も同じ形）。層 A・層 B・世界・来歴のログは出生からのすべて。"""
    return {
        "activity": [list(x) for x in system.log.activity()],
        "sensory": [list(x) for x in system.log.sensory()],
        "delta_log": _intent_log(system),
        "layer_a": [dict(r) for r in system.decider.records],
        "layer_b": [list(x) for x in system.world.intents],
        "audit": _jsonable(A.audit(system)),
        "world_end": _jsonable(system.world.export_state()),
        "sigma_end_sha256": sigma_sha256(_sigma(system)),
        "history": _history(system),
        "pulse_end": system.pulse,
    }


def build_system(plan: Plan, seed: int, *, log=None) -> "A.AS2bSystem":
    """どの系も同じ組み立て（予定・L・rule_c ＝ A1・世界は結果を返さない）。log を渡さなければ、AS2b の道具の既定の来歴のログ。"""
    kwargs = {} if log is None else {"log": log}
    return A.build(seed, schedule=plan.schedule(), delay=plan.delay, rule_c=RULE_C, respond=False, **kwargs)


def _freeze_six(six: frozenset[str]) -> list:
    return [AS1.Intervention(AS1.FREEZE, six, AS1.ADVANCE)]


def _pulse_0(system, name: str, values: dict[str, dict[str, float]], six: frozenset[str], steps: list,
             sigmas: dict | None) -> None:
    """README §2.4 の T0〜T2（Pulse を進めない）。sigmas が None なら Σ を書き出さない（X1′）。"""
    if sigmas is not None:
        sigmas["T0"][name] = _sigma(system)
    steps.append(["T0", name, system.pulse, "build", {"rule_c": RULE_C, "respond": False}])
    key = TRANSPLANTED.get(name)
    if key is not None:
        by_cid = {cid: values[key][role] for role, cid in role_connections(system.roles).items()}
        state_before = _jsonable(system.connections.export_intervention_state())
        system.transplant(by_cid)
        steps.append(["T1", name, system.pulse, "transplant",
                      {"values": key, "intervention_state_at_transplant": state_before}])
    else:
        steps.append(["T1", name, system.pulse, "none", None])
    if sigmas is not None:
        sigmas["T1"][name] = _sigma(system)
    system.declare(_freeze_six(six), label=T2_LABEL)
    steps.append(["T2", name, system.pulse, "declare", {"FREEZE": sorted(six), "trace_policy": AS1.ADVANCE}])
    if sigmas is not None:
        sigmas["T2"][name] = _sigma(system)


def _advance_each_pulse(system, until: int, order, rec: dict) -> None:
    """1 Pulse ずつ until まで進め、各 Pulse の処理の後の 6 本の重みを [Pulse, 重みの列] で記録する（O6）。3 つの Unit のどれかが
    最初に発火した Pulse t₁ の処理の後の Σ を一度だけ記録する（O10）。"""
    for pulse in range(system.pulse + 1, until + 1):
        A.advance_to(system.app, pulse)
        rec["pulse_weights"].append([pulse, _row(system, order)])
        if rec["first_firing"] is None and system.log.activity() and system.log.activity()[-1][0] == pulse:
            rec["first_firing"] = {"pulse": pulse, "sigma": _sigma(system)}


def measure_seed(protocol: dict, seed: int, plan: Plan | None = None) -> dict:
    plan = plan or formal_plan(protocol)
    plan.schedule().check(plan.delay)
    if not 1 <= plan.e_windows < plan.count:
        raise ValueError("E と U の両方に窓が要る")
    end = plan.end
    values = intervention_values(*c0_weights())

    def log():
        return AS1.AS1Log(keep=LOG_KEEP)

    systems = {name: build_system(plan, seed, log=log()) for name in RECORDED}
    first = systems["X1"]
    roles = first.roles
    birth_units = {u.unit_id: u.export_state() for u in first.app.units.all()}
    w_0 = _weights(first)                                   # 出生時の値
    order = sorted(w_0)
    six = frozenset(order)
    steps: list[list] = []
    sigmas: dict[str, dict] = {"T0": {}, "T1": {}, "T2": {}}
    for name in RECORDED:                                   # T0〜T2（Pulse を進めない）
        _pulse_0(systems[name], name, values, six, steps, sigmas)
    records = {}
    for name in RECORDED:                                   # T3
        rec: dict = {"pulse_weights": [], "first_firing": None}
        _advance_each_pulse(systems[name], end, order, rec)
        records[name] = rec | _end_record(systems[name])
        steps.append(["T3", name, systems[name].pulse, "advance_to", {"from": 0}])

    # ---- X1′：同じ組み立て・移植・FREEZE。足した記録をせず、既定のログのまま一度に進める ----
    rerun = build_system(plan, seed)
    _pulse_0(rerun, RERUN, values, six, steps, None)
    A.advance_to(rerun.app, end)
    steps.append(["T3", RERUN, rerun.pulse, "advance_to", {"from": 0}])
    records[RERUN] = {"sigma_end": _sigma(rerun)} | _end_record(rerun)

    return {
        "seed": seed,
        "plan": asdict(plan),
        "roles": roles.as_dict(),
        "birth_units": _jsonable(birth_units),
        "connection_order": order,
        "W_0": w_0,
        "values": values,
        "pulse_0": {"steps": steps, "sigma_T0": sigmas["T0"], "sigma_T1": sigmas["T1"], "sigma_T2": sigmas["T2"]},
        "systems": records,
    }


def protocol_from_file() -> dict:
    return yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
