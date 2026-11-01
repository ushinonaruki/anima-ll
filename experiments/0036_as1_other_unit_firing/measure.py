"""実験 0036 の測定（確定した事前登録 v0.2：README §2・§3・§6〜§8、protocol.yaml。#162 merge `dd2973f`）。

seed ごとに measure_seed：
1. AS1 の本体を、AS1 の道具（experiments/as1_closed_loop/as1.py）の build で、protocol の値（L ＝ 2・1 予約に 1 出来事・
   外の刺激なし・respond）で組み立てる。**他の Unit は OtherFiringControl で包む**（build の unit_wrappers。README §2.3）。
   本体では列を置かないので、包みは中の Unit の tick をそのまま渡す（本体には介入をしない）。Pulse を 1 つずつ進める
2. 本体で意図が Pulse t に生まれ、その結果の予約 e の Pulse t ＋ 1 が区間 W に入れば（出来事）、Pulse t の処理の後で：
   - **Σ_t**：本体の `sigma` の書き出しを保存する（読み出すだけ。0035 と同じ）
   - **系**（README §2.2。すべて本体の複製から。介入は Pulse t の境界で一度だけ宣言し、解除しない）：
     F′・N・N′・F^{o:=N}・N^{o:=F}・F^{o:=F}・F^{blk}・N^{blk}・F^{o:=∅}・N^{o:=∅}・F^{cf}・N^{cf}・F^{blk,cf}・N^{blk,cf}・
     F^{∅,cf}・N^{∅,cf}。O7 の (c) のために、F^{o:=N}・F^{blk}・F^{cf} を、Pulse ごとの記録をしない形でもう一度走らせる
   - 参照の列：F^{o:=N} の列は N の、N^{o:=F}・F^{o:=F} の列は F′（介入なしの複製。O10 で本体と一致を確かめる）の、他の Unit の
     発火の列（区間 (t, 参照の止まった Pulse]）。∅ は空の列
3. 本体を最後（body_runs_to）まで進める。O3 の介入なしの複製は 0035 と同じ
4. **O7 の (a)**：0035 と同じ二つの走り直し。途中で Σ を読まない走り直し（rerun_plain）は、**他の Unit を包まない** AS1 の build
   （unit_wrappers を渡さない、#148 と同じ組み立て）で行う。包みが本体を変えないことの、seed ごとの確かめを兼ねる

生の記録だけを返す。符号・判定の量（s_e・s_fix・P_i・J_P）と補助の量は計算しない（analyze.py）。
"""

import copy
import dataclasses
import hashlib
import importlib.util
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from anima_ll.unit.dynamics.activity_dynamics import ActivityState
from anima_ll.unit.dynamics.simple_activity_dynamics import SimpleActivityDynamics

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A = _load("as1_tools_for_0036", REPO / "experiments" / "as1_closed_loop" / "as1.py")


@dataclass(frozen=True)
class Plan:
    """測定の区間。本番の値は protocol の式から（formal_plan）。契約テストだけが小さい Plan を使う（0035 と同じ形）。"""

    window_first: int
    window_last: int
    horizon: int
    body_runs_to: int
    checkpoints: tuple[int, ...]
    clone_check_at: int
    clone_check_until: int


# protocol.yaml の式の文字列（alignment.py が protocol と同じか確かめる）
WINDOW_FIRST = "adaptation_tau_pulses + 1"
WINDOW_LAST = "6 * adaptation_tau_pulses"
BRANCH_PULSE = "e.pulse - (delay_L - 1)"
HORIZON = "adaptation_tau_pulses"
BODY_RUNS_TO = "event_window.last - (delay_L - 1) + horizon_H"

# 系の名前（protocol の systems の鍵と同じ。F は本体なので系の記録を持たない）
SYSTEMS = ("F_prime", "N", "N_prime", "F_fixN", "N_fixF", "F_fixF", "F_blk", "N_blk", "F_none", "N_none",
           "F_cf", "N_cf", "F_blk_cf", "N_blk_cf", "F_none_cf", "N_none_cf")
E_CANCELLED = frozenset({"N", "N_prime", "N_fixF", "N_blk", "N_none", "N_cf", "N_blk_cf", "N_none_cf"})
FORCED = {"F_fixN": "N", "N_fixF": "F_prime", "F_fixF": "F_prime", "F_none": None, "N_none": None,
          "F_none_cf": None, "N_none_cf": None}            # 固定した系 → 列の参照の系（None は空の列）
BLOCKED = frozenset({"F_blk", "N_blk", "F_blk_cf", "N_blk_cf"})
FROZEN = frozenset({"F_cf", "N_cf", "F_blk_cf", "N_blk_cf", "F_none_cf", "N_none_cf"})
PLAIN = ("F_fixN", "F_blk", "F_cf")                         # O7 の (c)：介入の種類ごとに 1 つ
REFERENCE_SYSTEMS = ("F_prime", "N")                        # 列の参照。最初に走らせる


def formal_plan(protocol: dict) -> Plan:
    tau = int(protocol["brain"]["adaptation_tau_pulses"])
    delay = int(protocol["world"]["delay_L"])
    first, last, horizon = tau + 1, 6 * tau, tau
    body = last - (delay - 1) + horizon
    checkpoints = tuple(protocol["auxiliary"]["R10_weights"]["pulses"])
    return Plan(first, last, horizon, body, checkpoints, clone_check_at=300, clone_check_until=600)


def body_log_keep(protocol: dict) -> frozenset[str]:
    return frozenset(getattr(A.RuntimeEventType, name) for name in protocol["records"]["body_log_keep"])


# 系 N′ の来歴のログ：感覚の出来事だけ（0035 と同じ。τ は源の発火の数で検知するのでログに依らない）
N_PRIME_LOG_KEEP = frozenset({A.RuntimeEventType.SENSORY})


def manifest_raw() -> dict:
    return A.as1_manifest_raw()


def block_targets(roles) -> tuple[str, str]:
    """伝達の遮断の対象（protocol の transmission_block.targets）：他 → 源・他 → 受。"""
    return (f"{roles.other}.main->{roles.source}", f"{roles.other}.main->{roles.receiver}")


def block_keys(roles) -> tuple[tuple[str, str, str], tuple[str, str, str]]:
    """遮断の対象の、伝達の重みの鍵（ConnectionKey ＝ (送り手, 出力路, 受け手)）。block_targets と同じ順。"""
    return ((roles.other, "main", roles.source), (roles.other, "main", roles.receiver))


def _key_text(key) -> str:
    src, port, tgt = key
    return f"{src}.{port}->{tgt}"


# ---- 他の Unit の発火の時刻の固定（README §2.3） ------------------------------------------------

def _dynamics(described: dict) -> SimpleActivityDynamics:
    if described.get("kind") != "simple_activity":
        raise ValueError(f"未知の力学：{described.get('kind')}")
    return SimpleActivityDynamics(decay_per_second=described["decay_per_second"], threshold=described["threshold"],
                                  refractory_pulses=described["refractory_pulses"],
                                  intrinsic_drive_per_second=described["intrinsic_drive_per_second"],
                                  adaptation_increment=described["adaptation_increment"],
                                  adaptation_tau_seconds=described["adaptation_tau_seconds"])


def _state_of(exported: dict) -> ActivityState:
    return ActivityState(float(exported["activity"]), int(exported["refractory_remaining"]),
                         float(exported["adaptation"]), int(exported["fire_count"]))


def _as_export(state: ActivityState, exported: dict) -> dict:
    return {**exported, "activity": state.activity, "refractory_remaining": state.refractory_remaining,
            "adaptation": state.adaptation, "fire_count": state.fire_count}


class OtherFiringControl:
    """他の Unit を包む研究用の部品（README §2.3。Core は変えない）。

    - 列を置かない間（本体・固定しない系）は、中の Unit の tick・状態の口をそのまま渡す（恒等）
    - force(schedule, after, until) で列を一度だけ置くと、区間 (after, until] の各 Pulse で：
      1. 中の Unit の状態と、その Pulse に届いた駆動の重みの合計（Unit の刺激。GenericCognitiveUnit と同じ）から、
         Core の SimpleActivityDynamics.advance で自然な結果（状態と、発火するか）を求める
      2. 自然な発火の有無が列と同じなら、中の Unit の tick をそのまま呼ぶ（自然な系と同じ）
      3. 列が「発火」で自然には発火しないなら、中の Unit の活動を +inf として tick を呼ぶ。中の Unit は Core の経路のまま
         発火し（出力の部品の on_fire と ActivityEvent）、状態は advance の発火の枝の更新（活動 0・不応・順応の増分・発火の数）になる
      4. 列が「発火しない」で自然には発火するなら、中の Unit の活動を −inf として tick を呼び（発火しない）、そのあと状態を、
         advance の発火しない枝の更新（閾値を越えていても発火の更新をしない）に置き直す
      どの場合も、中の Unit の tick の後の状態が、advance（閾値を ±inf にした同じ力学を含む）で求めた状態と同じことを確かめ、
      違えば止まる。不応の途中（refractory_remaining ＞ 0）の Pulse が区間に入れば止まる（C0 では起きない。O8）
    - 区間の外の Pulse を固定した系で進めようとしたら止まる（固定した系は until までに止まる）
    - 列が自然な決まり方と違った Pulse を overrides に [Pulse, "fire" | "hold"] で残す（記録だけ）
    """

    def __init__(self, inner) -> None:
        self._inner = inner
        self.schedule: tuple[int, ...] | None = None
        self.after: int | None = None
        self.until: int | None = None
        self.overrides: list[list] = []

    @property
    def unit_id(self):
        return self._inner.unit_id

    def force(self, schedule, *, after: int, until: int) -> None:
        if self.schedule is not None:
            raise RuntimeError("発火の時刻の列は一度だけ置く")
        pulses = tuple(sorted(int(p) for p in schedule))
        if len(set(pulses)) != len(pulses) or any(not (after < p <= until) for p in pulses):
            raise ValueError("列は区間 (after, until] の重ならない Pulse")
        self.schedule, self.after, self.until = pulses, int(after), int(until)

    def tick(self, view, context):
        if self.schedule is None:
            return self._inner.tick(view, context)
        pulse = context.pulse
        if not (self.after < pulse <= self.until):
            raise RuntimeError(f"Pulse {pulse} は固定の区間 ({self.after}, {self.until}] の外")
        pre = self._inner.export_state()
        if int(pre["refractory_remaining"]) != 0:
            raise RuntimeError(f"Pulse {pulse}：不応の途中で発火の時刻を固定しようとした")
        dyn, state = _dynamics(pre["dynamics"]), _state_of(pre)
        stimulus = sum(d.weight for d in view.drives)
        natural, fired = dyn.advance(state, stimulus, context.delta_time)
        want = pulse in self.schedule
        if (fired is not None) == want:
            step = self._inner.tick(view, context)
            expected = natural
        elif want:
            expected, f = dataclasses.replace(dyn, threshold=-math.inf).advance(state, stimulus, context.delta_time)
            if f is None:
                raise RuntimeError(f"Pulse {pulse}：発火の枝の更新を求められない")
            self._inner.import_state({**pre, "activity": math.inf})
            step = self._inner.tick(view, context)
            self.overrides.append([pulse, "fire"])
        else:
            expected, f = dataclasses.replace(dyn, threshold=math.inf).advance(state, stimulus, context.delta_time)
            if f is not None:
                raise RuntimeError(f"Pulse {pulse}：発火しない枝の更新を求められない")
            self._inner.import_state({**pre, "activity": -math.inf})
            step = self._inner.tick(view, context)
            self._inner.import_state(_as_export(expected, self._inner.export_state()))
            self.overrides.append([pulse, "hold"])
        if (step.activity is not None) != want:
            raise RuntimeError(f"Pulse {pulse}：中の Unit の発火が列と違う")
        if _state_of(self._inner.export_state()) != expected:
            raise RuntimeError(f"Pulse {pulse}：中の Unit の状態が advance の結果と違う")
        return step

    def handle_kernel_result(self, task, result, context):
        return self._inner.handle_kernel_result(task, result, context)

    def export_state(self):
        return self._inner.export_state()

    def import_state(self, state) -> None:
        self._inner.import_state(state)

    def control_state(self) -> dict | None:
        """固定の状態（記録用。Σ には入らない：Σ の Unit の状態は中の Unit の状態）。"""
        if self.schedule is None:
            return None
        return {"schedule": list(self.schedule), "after": self.after, "until": self.until,
                "overrides": [list(x) for x in self.overrides]}


UNIT_WRAPPERS = {"other": OtherFiringControl}


def build_body(protocol: dict, seed: int, *, wrapped: bool = True):
    """本体の組み立て。wrapped が偽なら、他の Unit を包まない（#148 と同じ組み立て。O7 の (a) の rerun_plain）。"""
    world = protocol["world"]
    return A.build(seed, delay=int(world["delay_L"]), multiplicity=world["multiplicity"], respond=bool(world["respond"]),
                   exogenous=(), log=A.AS1Log(keep=body_log_keep(protocol)),
                   unit_wrappers=UNIT_WRAPPERS if wrapped else None)


def control_of(system) -> OtherFiringControl:
    unit = system.app.units.get(system.roles.other)
    if not isinstance(unit, OtherFiringControl):
        raise TypeError("他の Unit が OtherFiringControl で包まれていない")
    return unit


# ---- 記録の形 --------------------------------------------------------------------------------

def _jsonable(x):
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    return x


def sigma_sha256(sigma_json) -> str:
    """Σ（JSON の形）の正規の書き出しの SHA-256（0035 と同じ）。"""
    canonical = json.dumps(json.loads(json.dumps(sigma_json)), separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _sigma(system) -> dict:
    return _jsonable(A.sigma(system))


def _sensory(system) -> list[list]:
    return [[p, r] for p, r in system.log.sensory()]


def _pending(system) -> list:
    return _jsonable(system.world.export_state()["pending"])


def _plastic_weights(system) -> dict[str, float]:
    return {cid: v["weight"] for cid, v in sorted(system.app.connections.export_state().items())}


def _event_at(body, intents_before: int, plan: Plan, delay: int):
    new = body.world.intents[intents_before:]
    if not new or body.pulse > plan.window_last - (delay - 1):
        return None
    (t, delta_id), = new
    e = next(r for r in body.world.pending if r.origin == delta_id)
    if not (plan.window_first <= e.pulse <= plan.window_last):
        return None
    return t, delta_id, e


def _run(system, t: int, censor: int, *, masked_keys=None, frozen: bool = False) -> dict:
    """t の処理の後から、最初の意図か censor まで 1 Pulse ずつ進め、記録を返す。
    τ の検知は道具の advance_until_first_intent を 1 Pulse ずつ使う（0034 と同じ）。介入の証拠は Pulse ごとに残す：
    - 遮断の系：Pulse p の冒頭に伝達へ渡した、対象の 2 本の重み（targets）と、渡した重みが中の重みと違った接続の組（differs）
    - 可塑性を止めた系：分岐の時点の 6 本の重み（baseline_weights）と、Pulse p の末尾の 6 本の重み"""
    tau = None
    masked: list[list] = []
    baseline = _plastic_weights(system) if frozen else None
    pulse_weights: list[list] = []
    for p in range(t, censor):
        found = A.advance_until_first_intent(system, p, p + 1)
        if masked_keys is not None:
            ret, inner = system.connections.last_returned, system.connections.last_inner
            masked.append([p + 1, [ret[k] for k in masked_keys],
                           sorted(_key_text(k) for k in ret if ret[k] != inner.get(k))])
        if frozen:
            pulse_weights.append([p + 1, _plastic_weights(system)])
        if found is not None:
            tau = found
            break
    unit = system.app.units.get(system.roles.other)
    return {
        "tau": tau,
        "stopped_at": system.pulse,
        "censor": censor,
        "firings": [list(x) for x in system.log.activity()],
        "sensory": _sensory(system),
        "pending_stop": _pending(system),
        "sigma_stop_sha256": sigma_sha256(_sigma(system)),
        "control": unit.control_state() if isinstance(unit, OtherFiringControl) else None,
        "interventions": _jsonable(system.connections.export_intervention_state()),
        "history": [[b, label, [[iv.kind, sorted(iv.targets), iv.trace_policy] for iv in active]]
                    for b, label, active in system.connections.history],
        "masked": masked if masked_keys is not None else None,
        "baseline_weights": baseline,
        "pulse_weights": pulse_weights if frozen else None,
    }


def _run_plain(system, t: int, censor: int) -> dict:
    """O7 の (c)：Pulse ごとの記録をせず、道具の advance_until_first_intent を一度だけ呼ぶ。"""
    tau = A.advance_until_first_intent(system, t, censor)
    return {"tau": tau, "stopped_at": system.pulse, "firings": [list(x) for x in system.log.activity()]}


def _other_firings(record: dict, other: str, t: int) -> list[int]:
    return [p for p, u in record["firings"] if u == other and t < p <= record["stopped_at"]]


def _branch_systems(body, e, roles, all_plastic) -> tuple[dict, dict]:
    """Pulse t の境界で、すべての系を作り、介入を宣言する（列は参照を走らせた後に置く）。分岐の時点の予約の列も返す。"""
    n_base = A.clone(body)
    n_base.world.cancel(e.rid)
    targets = frozenset(block_targets(roles))
    made, pending = {}, {}
    for name in SYSTEMS + tuple(f"{n}_plain" for n in PLAIN):
        base = name.removesuffix("_plain")
        s = A.clone(n_base if base in E_CANCELLED else body)
        if name == "N_prime":
            s.log.keep = N_PRIME_LOG_KEEP
        ivs = []
        if base in BLOCKED:
            ivs.append(A.Intervention(A.FB1, targets))
        if base in FROZEN:
            ivs.append(A.Intervention(A.FREEZE, all_plastic, A.ADVANCE))
        if ivs:
            s.declare(ivs, label=base)                   # 一度だけ（declare は全置換：監査 024）
        made[name] = s
        pending[name] = _pending(s)
    return made, {"n_base": n_base, "pending": pending}


def _event_systems(body, t: int, e, roles, plan: Plan, all_plastic) -> tuple[dict, dict, str]:
    made, extra = _branch_systems(body, e, roles, all_plastic)
    n_branch_sha = sigma_sha256(_sigma(extra["n_base"]))
    h = plan.horizon
    masked_keys = block_keys(roles)
    out: dict[str, dict] = {}
    for name in REFERENCE_SYSTEMS:
        out[name] = _run(made[name], t, t + h)
    n2 = made["N_prime"]
    tau = A.advance_until_first_intent(n2, t, t + h)
    out["N_prime"] = {"tau": tau, "stopped_at": n2.pulse, "censor": t + h, "sensory": _sensory(n2),
                      "sigma_stop_sha256": sigma_sha256(_sigma(n2))}
    stops = {name: out[name]["stopped_at"] for name in REFERENCE_SYSTEMS}
    plain: dict[str, dict] = {}
    for name in SYSTEMS:
        if name in out:
            continue
        ref = FORCED.get(name, "absent")
        censor = t + h if ref in (None, "absent") else stops[ref]
        for key in (name, f"{name}_plain") if name in PLAIN else (name,):
            s = made[key]
            if ref != "absent":
                schedule = [] if ref is None else _other_firings(out[ref], roles.other, t)
                control_of(s).force(schedule, after=t, until=censor)
            if key.endswith("_plain"):
                plain[name] = _run_plain(s, t, censor)
            else:
                out[name] = _run(s, t, censor, masked_keys=masked_keys if name in BLOCKED else None,
                                 frozen=name in FROZEN)
    for name in SYSTEMS:
        out[name]["pending_branch"] = extra["pending"][name]
    return out, plain, n_branch_sha


def body_rerun(protocol: dict, seed: int, plan: Plan) -> dict:
    """O7 の (a)：Σ_t の記録・系の分岐・複製をしない本体（本体と同じく他の Unit を包む）。決めた Pulse で Σ を読むだけ。"""
    delay = int(protocol["world"]["delay_L"])
    body = build_body(protocol, seed)
    sigma_at: dict[str, str] = {}
    for pulse in range(1, plan.body_runs_to + 1):
        intents_before = len(body.world.intents)
        A.advance_to(body.app, pulse)
        if pulse in plan.checkpoints or _event_at(body, intents_before, plan, delay) is not None:
            sigma_at[str(pulse)] = sigma_sha256(_sigma(body))
    return {"intents": [list(x) for x in body.world.intents], "sensory": _sensory(body),
            "activity": [list(x) for x in body.log.activity()], "sigma_sha256": sigma_at}


def body_rerun_plain(protocol: dict, seed: int, plan: Plan) -> dict:
    """O7 の (a) の補い：途中で Σ を一度も読まず、分岐も複製もせず、**他の Unit を包まない**本体（#148 と同じ組み立て）。"""
    body = build_body(protocol, seed, wrapped=False)
    A.advance_to(body.app, plan.body_runs_to)
    return {"intents": [list(x) for x in body.world.intents], "sensory": _sensory(body),
            "activity": [list(x) for x in body.log.activity()], "pulse": body.pulse,
            "sigma_end_sha256": sigma_sha256(_sigma(body))}


def measure_seed(protocol: dict, seed: int, plan: Plan | None = None) -> dict:
    plan = plan or formal_plan(protocol)
    world = protocol["world"]
    delay = int(world["delay_L"])
    if world["exogenous"]:
        raise ValueError("0036 は外の刺激を置かない（protocol の world.exogenous は空）")
    body = build_body(protocol, seed)
    roles = body.roles
    birth_units = {u.unit_id: u.export_state() for u in body.app.units.all()}
    all_plastic = frozenset(body.app.connections.export_state())
    events: list[dict] = []
    checkpoints: dict[str, dict] = {}
    checkpoint_sigma: dict[str, str] = {}
    clone_check: dict = {}
    twin = None

    for pulse in range(1, plan.body_runs_to + 1):
        intents_before = len(body.world.intents)
        A.advance_to(body.app, pulse)
        if pulse in plan.checkpoints:
            checkpoints[str(pulse)] = body.app.connections.export_state()
            checkpoint_sigma[str(pulse)] = sigma_sha256(_sigma(body))
        if pulse == plan.clone_check_at:
            twin = A.clone(body)
        if twin is not None and pulse == plan.clone_check_until:
            A.advance_to(twin.app, pulse)
            clone_check = {"at": plan.clone_check_at, "until": pulse,
                           "sigma_body": _sigma(body), "sigma_clone": _sigma(twin),
                           "activity_clone": [list(x) for x in twin.log.activity()]}
            twin = None
        found = _event_at(body, intents_before, plan, delay)
        if found is None:
            continue
        t, delta_id, e = found
        sigma_t = _sigma(body)
        body_pending = _pending(body)
        systems, plain, n_branch_sha = _event_systems(body, t, e, roles, plan, all_plastic)
        events.append({"t": t, "intent_delta_id": delta_id,
                       "e": {"rid": e.rid, "pulse": e.pulse, "receptor": e.receptor_id, "origin": e.origin},
                       "sigma_t": sigma_t, "body_pending": body_pending, "n_branch_sigma_sha256": n_branch_sha,
                       "systems": systems, "plain": plain})

    return {
        "seed": seed,
        "plan": asdict(plan),
        "roles": roles.as_dict(),
        "body": {
            "intents": [list(x) for x in body.world.intents],
            "sensory": _sensory(body),
            "activity": [list(x) for x in body.log.activity()],
            "realized": _jsonable(body.world.export_state()["realized"]),
            "pending_end": _pending(body),
            "checkpoints": checkpoints,
            "checkpoint_sigma_sha256": checkpoint_sigma,
            "birth_units": _jsonable(birth_units),
        },
        "clone_check": clone_check,
        "events": events,
        "rerun": body_rerun(protocol, seed, plan),
        "rerun_plain": body_rerun_plain(protocol, seed, plan),
    }


def expected_n_branch_sigma(sigma_t: dict, e: dict) -> dict:
    """O5 の (a)：Σ_t から、e の予約だけを取り消したときの分岐の時点の Σ（0035 と同じ）。"""
    s = copy.deepcopy(sigma_t)
    w = s["world"]
    row = next(r for r in w["pending"] if r[0] == e["rid"])
    w["pending"] = [r for r in w["pending"] if r[0] != e["rid"]]
    w["cancelled"] = list(w["cancelled"]) + [row]
    return s


def protocol_from_file() -> dict:
    return yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
