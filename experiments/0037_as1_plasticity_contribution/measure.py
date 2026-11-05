"""実験 0037 の測定（確定した事前登録 v0.2：README §2・§8・§9、protocol.yaml。#168 merge `1c71f3c`）。

seed ごとに measure_seed：
1. **S0**：本体 M（閉ループ、可塑性あり、介入なし）を、AS1 の道具の build で組み立て、P_E まで進める。M の重み・痕跡を
   checkpoints の Pulse で記録する。P_E で、再生の予定（成立した感覚の出来事 S^ext と、持ち越しの予約）を取り出す
   （AS1 の道具の replay_schedule）
2. Y（同じ seed、出口あり、世界は意図に応じない、再生の予定を受ける、境界 0 で 6 本の FREEZE）・Y^ON（Y と同じで介入なし）・
   K（閉ループ、境界 0 で 6 本の FREEZE）・M′（M と同じ組み立てで、途中の記録をしない）を、P_E まで進める
3. **S1〜S5**（README §2.4。このあいだに Pulse を進めない）
   - S1：Y・K の E の FREEZE を解除する（clear）
   - S2：M から M[W_0]・M[W_M] を、Y から Y[W_M] を複製する（M1）
   - S3：複製に移植する（M[W_0] ← W_0、M[W_M] ← W_M、Y[W_M] ← W_M）。介入の状態が空なので、transplant の検査に掛からない
   - Σ の書き出し (a)
   - S4：Y・Y[W_M] の世界を閉ループの規則に切り替える（AS1 の道具の switch_world）
   - S5：6 系のそれぞれで、U の介入（6 本の FREEZE、advance）を一度だけ宣言する
   - Σ の書き出し (b)
4. **S6**：6 系を P_E ＋ |U| まで進める。Pulse ごとの 6 本の重み、Pulse P_E ＋ 1 の処理の後の Σ（O15）、終わりの Σ の SHA-256
境界の記録（boundary.steps）には、S0〜S6 の各段の系ごとの Pulse の番号と操作を、行った順に残す（O6 で照合する）。

生の記録だけを返す。適格・構造上の恒等・I_U・T1〜T3・対比・P_i・J_C などの量は計算しない（analyze.py）。
Core・設計図・Unit の力学・可塑性の規則・確定したパラメータは変えない。FREEZE 中の移植を許す変更もしない。
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


A = _load("as1_tools_for_0037", REPO / "experiments" / "as1_closed_loop" / "as1.py")


@dataclass(frozen=True)
class Plan:
    """測定の区間。本番の値は protocol の式から（formal_plan）。契約テストだけが小さい Plan を使う。"""

    p_e: int                              # 経験の区間 E ＝ [1, p_e] の終わり
    u_length: int                         # 試しの区間 U ＝ [p_e + 1, p_e + u_length] の長さ
    checkpoints: tuple[int, ...]          # M の 6 本の重み・痕跡を記録する Pulse（R2。p_e 以下）


# protocol.yaml の式の文字列（alignment.py が protocol と同じか確かめる）
P_E = "6 * adaptation_tau_pulses"
U_LENGTH = "adaptation_tau_pulses"
RUNS_TO = "P_E + U_length"

U_SYSTEMS = ("M", "M_W0", "M_WM", "Y", "Y_WM", "K")      # U を走らせる 6 系（protocol の systems.run_in_U と同じ順）
E_ONLY = ("Y_on", "M_rerun")                             # E だけ走らせる確かめの系
TRANSPLANTS = {"M_W0": ("M", "W_0"), "M_WM": ("M", "W_M"), "Y_WM": ("Y", "W_M")}   # 複製 → (元の系, 移植の先)
FROZEN_VALUE = {"M": "W_M", "M_W0": "W_0", "M_WM": "W_M", "Y": "W_0", "Y_WM": "W_M", "K": "W_0"}   # S5 の FREEZE の値（O9）
SWITCHED = ("Y", "Y_WM")                                 # S4 で世界を閉ループの規則に切り替える系
E_FROZEN = ("Y", "K")                                    # E で 6 本を止める系（境界 0 で宣言、S1 で解除）
S0_ORDER = ("M", "Y", "Y_on", "K", "M_rerun")            # S0 で P_E まで進める順（境界の記録の順）
HORIZONTAL = (("M", "M_W0"), ("Y", "Y_WM"))              # SE-6・O15 の横の対
LOG_KEEP = frozenset({A.RuntimeEventType.SENSORY, A.RuntimeEventType.ACTIVITY})   # 来歴のログは感覚と発火だけ
E_LABEL, S1_LABEL, S4_LABEL, S5_LABEL = "E", "S1", "S4", "S5"


def formal_plan(protocol: dict) -> Plan:
    tau = int(protocol["brain"]["adaptation_tau_pulses"])
    p_e, u_length = 6 * tau, tau
    checkpoints = tuple(protocol["auxiliary"]["R2_weights"]["M_checkpoints"]["pulses"])
    return Plan(p_e, u_length, checkpoints)


def manifest_raw() -> dict:
    return A.as1_manifest_raw()


# ---- 記録の形 --------------------------------------------------------------------------------

def _jsonable(x):
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    return x


def sigma_sha256(sigma_json) -> str:
    """Σ（JSON の形）の正規の書き出しの SHA-256（0035・0036 と同じ）。"""
    canonical = json.dumps(json.loads(json.dumps(sigma_json)), separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _sigma(system) -> dict:
    return _jsonable(A.sigma(system))


def _weights(system) -> dict[str, float]:
    return {cid: v["weight"] for cid, v in sorted(system.app.connections.export_state().items())}


def _history(system) -> list:
    return [[b, label, [[iv.kind, sorted(iv.targets), iv.trace_policy] for iv in active]]
            for b, label, active in system.connections.history]


def _switches(system) -> list:
    return [list(x) for x in system.meta.get("world_switches", [])]


def _world(system) -> dict:
    return _jsonable(system.world.export_state())


def build_system(protocol: dict, seed: int, *, respond: bool = True, exogenous=()) -> "A.AS1System":
    """AS1 の個体と世界を、protocol の閉ループの規則（L・多重度）で組み立てる。respond と行動に依らない予定だけを変えられる。"""
    world = protocol["world"]["closed_loop"]
    return A.build(seed, delay=int(world["delay_L"]), multiplicity=world["multiplicity"], respond=respond,
                   exogenous=exogenous, log=A.AS1Log(keep=LOG_KEEP))


def _freeze_six(six: frozenset[str]) -> list:
    return [A.Intervention(A.FREEZE, six, A.ADVANCE)]


def _advance_recording(system, until: int) -> list[list]:
    """1 Pulse ずつ until まで進め、各 Pulse の処理の後の 6 本の重みを [Pulse, {接続: 重み}] で返す（O5・O9 の証拠）。"""
    rows = []
    for pulse in range(system.pulse + 1, until + 1):
        A.advance_to(system.app, pulse)
        rows.append([pulse, _weights(system)])
    return rows


def _e_record(system, p_e: int) -> dict:
    return {"activity": [list(x) for x in system.log.activity() if x[0] <= p_e],
            "sensory": [list(x) for x in system.log.sensory() if x[0] <= p_e],
            "intents": [list(x) for x in system.world.intents if x[0] <= p_e]}


def measure_seed(protocol: dict, seed: int, plan: Plan | None = None) -> dict:
    plan = plan or formal_plan(protocol)
    if protocol["world"]["closed_loop"]["exogenous"]:
        raise ValueError("0037 の閉ループの世界は外の刺激を置かない（protocol の world.closed_loop.exogenous は空）")
    if any(c > plan.p_e for c in plan.checkpoints):
        raise ValueError("checkpoints は p_e 以下")
    p_e, end = plan.p_e, plan.p_e + plan.u_length

    # ---- S0：M ----
    m = build_system(protocol, seed)
    roles = m.roles
    birth_units = {u.unit_id: u.export_state() for u in m.app.units.all()}
    w_0 = _weights(m)                                     # 出生時の値（経験の前の値）
    six = frozenset(w_0)
    checkpoints = {}
    for c in sorted(plan.checkpoints):
        A.advance_to(m.app, c)
        checkpoints[str(c)] = m.app.connections.export_state()
    A.advance_to(m.app, p_e)
    schedule = A.replay_schedule(m)                       # S^ext と持ち越し
    m_e = _e_record(m, p_e) | {"schedule": [list(x) for x in schedule],
                               "pending_at_p_e": _jsonable(m.world.export_state()["pending"]),
                               "checkpoints": _jsonable(checkpoints)}

    # ---- S0：Y・Y^ON・K・M′ ----
    y = build_system(protocol, seed, respond=False, exogenous=schedule)
    y.declare(_freeze_six(six), label=E_LABEL)
    y_weights = _advance_recording(y, p_e)
    y_on = build_system(protocol, seed, respond=False, exogenous=schedule)
    A.advance_to(y_on.app, p_e)
    k = build_system(protocol, seed)
    k.declare(_freeze_six(six), label=E_LABEL)
    k_weights = _advance_recording(k, p_e)
    m_rerun = build_system(protocol, seed)
    A.advance_to(m_rerun.app, p_e)
    e_records = {
        "Y": _e_record(y, p_e) | {"pulse_weights": y_weights},
        "K": _e_record(k, p_e) | {"pulse_weights": k_weights},
        "Y_on": _e_record(y_on, p_e) | {"sigma_p_e": _sigma(y_on)},
        "M_rerun": _e_record(m_rerun, p_e) | {"sigma_p_e": _sigma(m_rerun), "sigma_p_e_sha256": sigma_sha256(_sigma(m_rerun))},
    }

    # ---- S1〜S5（このあいだに Pulse を進めない） ----
    systems = {"M": m, "Y": y, "K": k}
    advanced = {"M": m, "Y": y, "Y_on": y_on, "K": k, "M_rerun": m_rerun}
    steps: list[list] = [["S0", name, advanced[name].pulse, "advance_to", {"from": 0}] for name in S0_ORDER]

    def step(name: str, system_name: str, op: str, detail=None) -> None:
        steps.append([name, system_name, systems[system_name].pulse, op, _jsonable(detail)])

    for name in E_FROZEN:                                                    # S1
        systems[name].clear(label=S1_LABEL)
        step("S1", name, "clear")
    for name, (source, _) in TRANSPLANTS.items():                            # S2
        systems[name] = A.clone(systems[source])
        step("S2", name, "clone", {"from": source})
    w_m = _weights(m)
    targets = {"W_0": w_0, "W_M": w_m}
    for name, (_, key) in TRANSPLANTS.items():                               # S3
        state_before = _jsonable(systems[name].connections.export_intervention_state())
        systems[name].transplant(targets[key])
        step("S3", name, "transplant", {"to": key, "intervention_state_at_transplant": state_before})
    sigma_a = {name: _sigma(systems[name]) for name in U_SYSTEMS}
    switch_to = protocol["world"]["switch"]["to"]
    if switch_to != "closed_loop" or tuple(protocol["world"]["switch"]["systems"]) != SWITCHED:
        raise ValueError("0037 の S4 は、Y・Y[W_M] を閉ループの規則に切り替える（TC-1）")
    for name in SWITCHED:                                                    # S4
        systems[name].switch_world(True, label=S4_LABEL)
        step("S4", name, "switch_world", {"respond": True})
    for name in U_SYSTEMS:                                                   # S5
        systems[name].declare(_freeze_six(six), label=S5_LABEL)
        step("S5", name, "declare", {"FREEZE": sorted(six), "trace_policy": A.ADVANCE})
    sigma_b = {name: _sigma(systems[name]) for name in U_SYSTEMS}

    # ---- S6：U ----
    u_records = {}
    for name in U_SYSTEMS:
        s = systems[name]
        A.advance_to(s.app, p_e + 1)
        first_weights = [[p_e + 1, _weights(s)]]
        sigma_first = _sigma(s)                                              # Pulse P_E + 1 の処理の後（O15）
        rows = first_weights + _advance_recording(s, end)
        u_records[name] = {
            "activity": [list(x) for x in s.log.activity() if x[0] > p_e],
            "sensory": [list(x) for x in s.log.sensory() if x[0] > p_e],
            "intents": [list(x) for x in s.world.intents if x[0] > p_e],
            "pulse_weights": rows,
            "sigma_after_first": sigma_first,
            "sigma_end_sha256": sigma_sha256(_sigma(s)),
            "world_end": _world(s),
            "history": _history(s),
            "world_switches": _switches(s),
            "pulse_end": s.pulse,
        }
        steps.append(["S6", name, s.pulse, "advance_to", {"from": p_e}])

    return {
        "seed": seed,
        "plan": asdict(plan),
        "roles": roles.as_dict(),
        "birth_units": _jsonable(birth_units),
        "W_0": w_0,
        "M_E": m_e,
        "E": e_records,
        "boundary": {"steps": steps, "W_M": w_m, "sigma_a": sigma_a, "sigma_b": sigma_b},
        "U": u_records,
    }


def protocol_from_file() -> dict:
    return yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
