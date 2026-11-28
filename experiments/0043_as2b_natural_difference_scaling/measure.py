"""実験 0043 の測定（確定した事前登録 v0.2：README §2・§8・§9、protocol.yaml。#200 merge `8fee59e`）。

seed ごとに measure_seed（1 個体で、本体 3 と、P_E から走らせる最大 40 の複製の系。README §2.3）：
1. 本体 B^{A1}・B^{A2}：関門の `run_body` と同じ組み立て（`build(seed, schedule=…, delay=L, rule_c=c, respond=True)`）。
   予定・o・W・L・本体の長さは、関門の宣言 v0.2 から取る（SHA-256 を確かめる。値をここに書き込まない：O2）
2. **S0**：B^{A1}・B^{A2} を P_E まで進める。組み立てた直後の Σ（Σ_0）と、E の共通の部分の最初の決まった窓 k* の意図の Pulse
   （決定の翌 Pulse）の処理の後の Σ を書き出す（SE-C2・O4。0042 と同じ）
3. **S1〜S4**（README §2.5。このあいだに Pulse を進めない）
   - S1：B^{A1}・B^{A2} の 6 本の重み W^{A1}・W^{A2} と、P_E の Σ（値の全体）を読む。e・δ(e)・m_k と、すべての端の正確な値と範囲を
     計算する（README §2.2：浮動小数の値を有理数として正確に扱い、端の重みごとに一度だけ最近接の浮動小数に丸める）
   - S2：B^c から、基の系、範囲の中の端の系、G^c[X1]・G^c[X2]・G^c[W^c]^{tr} の元を、丸ごと複製する（`clone`）。
     範囲の外の端の系は作らない（切り詰めない）
   - S3：移植する（`transplant`。6 本を一度に）。端の系 ← その端の値、G^c[X1]・G^c[X2] ← X1・X2、G^c[W^c]^{tr} ← W^c。
     基の系は移植しない。作った系の Σ の書き出し (a)
   - S4：作ったすべての複製の系で、U の介入（6 本の FREEZE、advance）を一度の宣言で置く。Σ の書き出し (b)
4. **S5**：B^{A1}・B^{A2} と、作った複製の系を、終わり（b_K ＋ L）まで進める。複製の系は U の Pulse ごとの 6 本の重みと、Pulse P_E ＋ 1 の
   処理の後の Σ（O9）を記録する。どの系も、終わりの Σ（値の全体）と SHA-256 を書き出す
5. B′^{A1}：0042 と同じ（関門の `run_body` と同じ組み立てと既定の来歴のログで、P_E と終わりの二点のほかは状態を読まない。O13）

生の記録だけを返す。s・C_k・D^u_k とその成分・符号・k*・区分・札・判定と推定の量は計算しない（analyze.py）。
端の正確な値・範囲・e・δ(e)・m_k は、移植のために計算して記録する（analyze.py の O10 が、保存した P_E の Σ から計算し直して照らす）。
Core・設計図・Unit の力学・可塑性の規則・確定したパラメータ・AS2b の道具・関門の宣言は変えない。
"""

import hashlib
import importlib.util
import json
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A = _load("as2b_tools_for_0043", REPO / "experiments" / "as2b_choice" / "as2b.py")
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


# ---- 系（README §2.3。protocol の systems と、analysis.py の U_SYSTEMS と同じ順） ---------------------------------------

BACKGROUNDS = ("A1", "A2")
BODIES = ("B_A1", "B_A2")                                       # 本体（R-7 の二つの本体）。観測する
RERUN = "B_A1_rerun"                                            # B′^{A1}。観測しない
ROLES6 = ("C_to_source1", "source1_to_C", "C_to_source2", "source2_to_C", "source1_to_source2", "source2_to_source1")
PAIRS6 = (("C_to_source1", "source1_to_C"), ("C_to_source2", "source2_to_C"), ("source1_to_source2", "source2_to_source1"))
# 対称な介入の向き u ＝ (X1 − X2)／w_max（README §2.2）
U_DIRECTION = {"C_to_source1": 1, "source1_to_C": -1, "C_to_source2": -1, "source2_to_C": 1,
               "source1_to_source2": 0, "source2_to_source1": 0}
ENDPOINT_PREFIX = {"P": ("natural", 1), "M": ("natural", -1), "UP": ("symmetric", 1), "UM": ("symmetric", -1)}
LOG_KEEP = frozenset({EVENT.SENSORY, EVENT.ACTIVITY, EVENT.DELTA})        # 来歴のログは感覚・発火・Delta（意図）だけ
S4_LABEL = "S4"


def clone_names(levels) -> tuple[str, ...]:
    """複製の系の名前（作るかどうかに依らない、すべての名前。背景 A1 の 20、A2 の 20 の順）。"""
    names = []
    for c in BACKGROUNDS:
        names.append(f"G_{c}_base")
        for k in levels:
            names += [f"G_{c}_P{k}", f"G_{c}_M{k}"]
        for k in levels:
            names += [f"G_{c}_UP{k}", f"G_{c}_UM{k}"]
        names += [f"G_{c}_X1", f"G_{c}_X2", f"G_{c}_tr"]
    return tuple(names)


def parse_clone(name: str) -> dict:
    """複製の系の名前 → {background, kind（base・natural・symmetric・X1・X2・tr）, level, side（+1・−1）}。"""
    _g, c, part = name.split("_", 2)
    if part in ("base", "tr", "X1", "X2"):
        return {"background": c, "kind": part, "level": None, "side": None}
    for prefix in ("UP", "UM", "P", "M"):
        if part.startswith(prefix) and part[len(prefix):].isdigit():
            kind, side = ENDPOINT_PREFIX[prefix]
            return {"background": c, "kind": kind, "level": int(part[len(prefix):]), "side": side}
    raise ValueError(f"複製の系の名前ではない：{name}")


def endpoint_names(levels) -> tuple[str, ...]:
    return tuple(n for n in clone_names(levels) if parse_clone(n)["kind"] in ("natural", "symmetric"))


def background_of(name: str) -> str:
    return f"B_{parse_clone(name)['background']}"


def rule_of(name: str) -> str:
    if name in BODIES or name == RERUN:
        return {"B_A1": "A1", "B_A2": "A2", RERUN: "A1"}[name]
    return parse_clone(name)["background"]


def protocol_levels(protocol: dict) -> tuple[int, ...]:
    return tuple(int(k) for k in protocol["weights"]["levels"])


# ---- 関門の宣言（README §1.1・O2）：0042 と同じ -----------------------------------------------------------------

def gate_declaration(protocol: dict) -> tuple[dict, str]:
    """関門の宣言を読み、SHA-256 が protocol の値（v0.2）と同じことを確かめる。(宣言, SHA-256) を返す。"""
    gate = protocol["inherited_gate_set"]
    raw = (REPO / gate["declaration"]).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != gate["sha256"]:
        raise ValueError(f"関門の宣言の SHA-256 が {digest}（protocol は {gate['sha256']}）。走らせない")
    return json.loads(raw), digest


def plan_from_declaration(decl: dict, e_windows: int) -> Plan:
    """宣言の予定・o・W・L から Plan を作る（0042 と同じ。この道具が実現しない形は止める）。"""
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


def check_levels(levels) -> tuple[int, ...]:
    levels = tuple(levels)
    if not levels or any(not isinstance(k, int) or isinstance(k, bool) or k < 1 for k in levels) \
            or list(levels) != sorted(set(levels)):
        raise ValueError("段は 1 以上の整数の、重複のない昇順の列")
    return levels


def manifest_raw() -> dict:
    return AS1.as1_manifest_raw()


def extremes(protocol: dict) -> dict[str, dict[str, float]]:
    """人工の端 X1・X2 の 6 本（役の名前 → 値。protocol の extremes）。"""
    ex = protocol["extremes"]
    return {"X1": {r: float(ex["X1"][r]) for r in ROLES6}, "X2": {r: float(ex["X2"][r]) for r in ROLES6}}


def role_cids(roles) -> dict[str, str]:
    """役の名前（C_to_source1 など）→ 接続の ID（"<送り手>.main-><受け手>"）。C は手がかりの Unit。"""
    c, s1, s2 = roles["cue"], roles["source1"], roles["source2"]
    return {"C_to_source1": f"{c}.main->{s1}", "source1_to_C": f"{s1}.main->{c}",
            "C_to_source2": f"{c}.main->{s2}", "source2_to_C": f"{s2}.main->{c}",
            "source1_to_source2": f"{s1}.main->{s2}", "source2_to_source1": f"{s2}.main->{s1}"}


# ---- 重みの算術（README §2.2） -----------------------------------------------------------------------------

def frac_str(x: Fraction) -> str:
    return f"{x.numerator}/{x.denominator}"


def endpoints(roles, w_a1: dict[str, float], w_a2: dict[str, float], levels, w_max: float) -> dict:
    """すべての端の、正確な値・範囲・丸めた値（README §2.2）。重みは接続の ID → 浮動小数。

    返す値：{"difference": {e（役ごと）・delta_e・m（段ごと）を "分子/分母" の文字列で}, "endpoints": {系の名前: 端の記録}}。
    端の記録：{in_range, out_of_range（範囲の外の [役の名前, below・above] の列。ROLES6 の順）, weights（範囲の中なら
    接続の ID → 丸めた浮動小数、外なら None）}。
    """
    cids = role_cids(roles)
    top = Fraction(w_max)
    exact = {c: {r: Fraction(w[cids[r]]) for r in ROLES6} for c, w in (("A1", w_a1), ("A2", w_a2))}
    e = {r: exact["A1"][r] - exact["A2"][r] for r in ROLES6}
    delta_e = e["C_to_source1"] - e["C_to_source2"]
    m = {k: Fraction(k) * abs(delta_e) / 2 for k in levels}
    out = {}
    for name in endpoint_names(levels):
        p = parse_clone(name)
        k, side, base = p["level"], p["side"], exact[p["background"]]
        if p["kind"] == "natural":
            v = {r: base[r] + side * k * e[r] for r in ROLES6}
        else:
            v = {r: base[r] + side * m[k] * U_DIRECTION[r] for r in ROLES6}
        bad = [[r, "below" if v[r] < 0 else "above"] for r in ROLES6 if not 0 <= v[r] <= top]
        out[name] = {"in_range": not bad, "out_of_range": bad,
                     "weights": None if bad else {cids[r]: float(v[r]) for r in ROLES6}}
    return {"difference": {"e": {r: frac_str(e[r]) for r in ROLES6}, "delta_e": frac_str(delta_e),
                           "m": {str(k): frac_str(m[k]) for k in levels}},
            "endpoints": out}


def built_clones(levels, endpoint_records: dict) -> tuple[str, ...]:
    """作る複製の系：基の系・X1・X2・tr と、範囲の中の端の系（clone_names の順）。"""
    return tuple(n for n in clone_names(levels)
                 if parse_clone(n)["kind"] in ("base", "X1", "X2", "tr") or endpoint_records[n]["in_range"])


def target_label(name: str) -> str | None:
    """S3 の移植の先の札（基の系は移植しない：None）。"""
    p = parse_clone(name)
    if p["kind"] == "base":
        return None
    if p["kind"] == "tr":
        return f"W_{p['background']}"
    if p["kind"] in ("X1", "X2"):
        return p["kind"]
    return name


# ---- 記録の形（0042 と同じ） --------------------------------------------------------------------------------

def _jsonable(x):
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    return x


def sigma_sha256(sigma_json) -> str:
    """Σ（JSON の形）の正規の書き出しの SHA-256（0035〜0042 と同じ）。"""
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
    """終わりの記録（どの系も同じ形。0042 と同じ）。複製の系では、道具の突合の「来歴のログ ＝ 世界」と、それを含む ok を外す
    （複製の系の来歴のログは複製の後だけを持つため。analyze.py が O3 で計算し直す）。"""
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
    """E の共通の部分の k* の意図の Pulse（決定の翌 Pulse）の処理の後の Σ を、一度だけ書き出すための目印（0039〜0042 と同じ形）。"""

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
    """本体を until まで進める。最初の決定が見つかるまでは、E の窓の中を 1 Pulse ずつ進める（記録は読むだけ。0042 と同じ）。"""
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


def measure_seed(protocol: dict, seed: int, plan: Plan | None = None, levels=None) -> dict:
    """1 個体の測定。plan・levels は契約テストだけが渡す（本番・smoke は protocol の値。analyze.py の structure が確かめる）。"""
    plan = plan or formal_plan(protocol)
    check_plan(plan)
    levels = check_levels(protocol_levels(protocol) if levels is None else levels)
    p_e, end = plan.p_e, plan.end
    w_max = float(protocol["brain"]["w_max"])
    x_by_role = extremes(protocol)

    # ---- S0：本体 B^{A1}・B^{A2} を P_E まで ----
    bodies = {name: build_body(plan, seed, rule_of(name), log=AS1.AS1Log(keep=LOG_KEEP)) for name in BODIES}
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
        weights[rule_of(name)] = _weights(bodies[name])
        sigma_p_e[name] = _sigma(bodies[name])
        steps.append(["S1", name, bodies[name].pulse, "read_weights_and_sigma", None])
    ends = endpoints(roles.as_dict(), weights["A1"], weights["A2"], levels, w_max)
    built = built_clones(levels, ends["endpoints"])
    targets = {n: (ends["endpoints"][n]["weights"] if parse_clone(n)["kind"] in ("natural", "symmetric")
                   else x_values[parse_clone(n)["kind"]] if parse_clone(n)["kind"] in ("X1", "X2")
                   else weights[parse_clone(n)["background"]]) for n in built}
    clones: dict[str, A.AS2bSystem] = {}
    for name in built:                                                        # S2
        clones[name] = A.clone(bodies[background_of(name)])
        steps.append(["S2", name, clones[name].pulse, "clone", {"from": background_of(name)}])
    for name in built:                                                        # S3
        label = target_label(name)
        if label is None:
            continue
        state_before = _jsonable(clones[name].connections.export_intervention_state())
        clones[name].transplant(targets[name])
        steps.append(["S3", name, clones[name].pulse, "transplant",
                      {"to": label, "intervention_state_at_transplant": state_before}])
    sigma_a = {name: _sigma(clones[name]) for name in built}
    for name in built:                                                        # S4
        clones[name].declare(_freeze_six(six), label=S4_LABEL)
        steps.append(["S4", name, clones[name].pulse, "declare", {"FREEZE": sorted(six), "trace_policy": AS1.ADVANCE}])
    sigma_b = {name: _sigma(clones[name]) for name in built}

    # ---- S5：本体と作った複製の系を終わりまで ----
    for name in BODIES:
        A.advance_to(bodies[name].app, end)
        records[name] |= _end_record(bodies[name])
        steps.append(["S5", name, bodies[name].pulse, "advance_to", {"from": p_e}])
    clone_records = {}
    for name in built:
        s = clones[name]
        rec: dict = {"pulse_weights": []}
        _advance_each_pulse(s, p_e + 1, order, rec)
        rec["sigma_after_first"] = _sigma(s)                                  # Pulse P_E ＋ 1 の処理の後（O9）
        _advance_each_pulse(s, end, order, rec)
        clone_records[name] = rec | _end_record(s, clone=True)
        steps.append(["S5", name, s.pulse, "advance_to", {"from": p_e}])

    # ---- B′^{A1}：関門と同じ組み立てと既定のログで、足した記録をしない（P_E と終わりの二点のほかは状態を読まない） ----
    rerun = build_body(plan, seed, rule_of(RERUN))
    A.advance_to(rerun.app, p_e)
    rerun_p_e = _sigma(rerun)
    A.advance_to(rerun.app, end)
    records[RERUN] = {"sigma_p_e": rerun_p_e, "sigma_p_e_sha256": sigma_sha256(rerun_p_e)} | _end_record(rerun)

    return {
        "seed": seed,
        "plan": asdict(plan),
        "levels": list(levels),
        "roles": roles.as_dict(),
        "birth_units": _jsonable(birth_units),
        "connection_order": order,
        "W_0": w_0,
        "X": x_values,
        "bodies": records,
        "boundary": {"steps": steps, "W": weights, "sigma_p_e": sigma_p_e,
                     "sigma_p_e_sha256": {n: sigma_sha256(sigma_p_e[n]) for n in BODIES},
                     "sigma_a": sigma_a, "sigma_b": sigma_b},
        "difference": ends["difference"],
        "endpoints": ends["endpoints"],
        "clones": clone_records,
    }


def protocol_from_file() -> dict:
    return yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
