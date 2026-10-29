"""実験 0034 の測定（確定した事前登録 v0.2：README §1〜§2・§6〜§8、protocol.yaml）。

seed ごとに measure_seed：
1. AS1 の本体を、②の道具（experiments/as1_closed_loop/as1.py、#148）の build で、protocol の値（L ＝ 2・1 予約に 1 出来事・
   外の刺激なし・respond）で組み立て、Pulse を 1 つずつ進める。本体には介入をしない
2. 本体で意図が Pulse t に生まれ、その結果の予約 e の Pulse t ＋ 1 が区間 W に入れば（出来事）、Pulse t の処理の後で分岐する：
   - 系 N ＝ 本体の複製から、e の識別子の予約だけを取り消したもの
   - 補助の系：F_CF ＝ 本体の複製、N_CF ＝ N の複製に、すべての可塑的な接続の FREEZE（advance）を一度だけ宣言する。
     F_FB ＝ 本体の複製、N_FB ＝ N の複製に、受 → 源 の FB-1 を一度だけ宣言する（解除しない。介入を重ねない）
   - それぞれを、t の後の最初の意図（源の発火の数で検知）か t ＋ H まで、1 Pulse ずつ進める
3. 本体を最後（body_runs_to）まで進める。Pulse clone_check.at の処理の後で作った介入なしの複製を clone_check.until まで進め、
   本体と Σ を比べるための写しを残す（O3）

生の記録だけを返す。判定の量（s_e・d_e・n₊・n₋・P_i・m・J_A）と補助の量（B・d^FB・中央値など）は計算しない（analyze.py）。
"""

import importlib.util
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


A = _load("as1_tools_for_0034", REPO / "experiments" / "as1_closed_loop" / "as1.py")


@dataclass(frozen=True)
class Plan:
    """測定の区間。本番の値は protocol の式から（formal_plan）。契約テストだけが小さい Plan を使う。"""

    window_first: int          # 結果の刺激 e の Pulse の最初
    window_last: int           # 同じく最後
    horizon: int               # H
    body_runs_to: int          # 本体を進める最後の Pulse
    checkpoints: tuple[int, ...]   # R5：接続の状態を残す Pulse
    clone_check_at: int        # O3：介入なしの複製を作る Pulse（その処理の後）
    clone_check_until: int     # O3：比べる Pulse


# protocol.yaml の式の文字列。ここに書いた式を実装している（alignment.py が protocol と同じか確かめる）
WINDOW_FIRST = "adaptation_tau_pulses + 1"
WINDOW_LAST = "6 * adaptation_tau_pulses"
BRANCH_PULSE = "e.pulse - (delay_L - 1)"
HORIZON = "adaptation_tau_pulses"
BODY_RUNS_TO = "event_window.last - (delay_L - 1) + horizon_H"


def formal_plan(protocol: dict) -> Plan:
    tau = int(protocol["brain"]["adaptation_tau_pulses"])
    delay = int(protocol["world"]["delay_L"])
    first, last, horizon = tau + 1, 6 * tau, tau
    body = last - (delay - 1) + horizon
    checkpoints = tuple(protocol["auxiliary"]["R5_weights"]["pulses"])
    return Plan(first, last, horizon, body, checkpoints, clone_check_at=300, clone_check_until=600)


def body_log_keep(protocol: dict) -> frozenset[str]:
    """protocol の records.body_log_keep（RuntimeEventType の名前）を、来歴の出来事の種類の値にする。"""
    return frozenset(getattr(A.RuntimeEventType, name) for name in protocol["records"]["body_log_keep"])


def manifest_raw() -> dict:
    return A.as1_manifest_raw()


def _sensory(system) -> list[list]:
    return [[p, r] for p, r in system.log.sensory()]


def _plastic_weights(system) -> dict[str, float]:
    return {cid: v["weight"] for cid, v in system.app.connections.export_state().items()}


def _jsonable(x):
    """sigma などの写しを JSON の形（タプル → リスト）にそろえる。"""
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    return x


def _run_branch(system, t: int, horizon: int, *, masked_key=None, record_weights: bool = False) -> dict:
    """t の処理の後から、最初の意図か t ＋ H まで 1 Pulse ずつ進め、記録を返す（τ の検知は道具の advance_until_first_intent）。

    介入の証拠は Pulse ごとに残す（監査 026、#150 のレビューの必須 2）：
    - FB の系：Pulse p の冒頭に伝達へ渡した 受 → 源 の重みを [p, w] で、t ＋ 1 から止まった Pulse まで欠けなく
    - CF の系：分岐の時点（t の末尾）の 6 本の重み（baseline_weights）と、Pulse p の末尾の 6 本の重みを [p, {接続: w}] で、
      t ＋ 1 から止まった Pulse まで欠けなく
    """
    tau = None
    masked_weights: list[list] = []
    baseline = _plastic_weights(system) if record_weights else None
    pulse_weights: list[list] = []
    for p in range(t, t + horizon):
        found = A.advance_until_first_intent(system, p, p + 1)
        if masked_key is not None:
            masked_weights.append([p + 1, system.connections.last_returned[masked_key]])
        if record_weights:
            pulse_weights.append([p + 1, _plastic_weights(system)])
        if found is not None:
            tau = found
            break
    return {
        "tau": tau,
        "stopped_at": system.pulse,
        "sensory": _sensory(system),
        "interventions": _jsonable(system.connections.export_intervention_state()),
        "history": [[b, label, [[iv.kind, sorted(iv.targets), iv.trace_policy] for iv in active]]
                    for b, label, active in system.connections.history],
        "masked_weights": masked_weights if masked_key is not None else None,
        "baseline_weights": baseline,
        "pulse_weights": pulse_weights if record_weights else None,
    }


def measure_seed(protocol: dict, seed: int, plan: Plan | None = None) -> dict:
    plan = plan or formal_plan(protocol)
    world = protocol["world"]
    delay = int(world["delay_L"])
    if world["exogenous"]:
        raise ValueError("0034 は外の刺激を置かない（protocol の world.exogenous は空）")
    body = A.build(seed, delay=delay, multiplicity=world["multiplicity"], respond=bool(world["respond"]),
                   exogenous=(), log=A.AS1Log(keep=body_log_keep(protocol)))
    roles = body.roles
    birth_units = {u.unit_id: u.export_state() for u in body.app.units.all()}   # Pulse 0（沈黙の理由の記録：R4）
    all_plastic = frozenset(body.app.connections.export_state())
    feedback = f"{roles.receiver}.main->{roles.source}"
    feedback_key = (roles.receiver, "main", roles.source)
    events: list[dict] = []
    checkpoints: dict[str, dict] = {}
    clone_check: dict = {}
    twin = None

    last_event_t = plan.window_last - (delay - 1)
    for pulse in range(1, plan.body_runs_to + 1):
        intents_before = len(body.world.intents)
        A.advance_to(body.app, pulse)
        if pulse in plan.checkpoints:
            checkpoints[str(pulse)] = body.app.connections.export_state()
        if pulse == plan.clone_check_at:
            twin = A.clone(body)
        if twin is not None and pulse == plan.clone_check_until:
            A.advance_to(twin.app, pulse)
            clone_check = {"at": plan.clone_check_at, "until": pulse,
                           "sigma_body": _jsonable(A.sigma(body)), "sigma_clone": _jsonable(A.sigma(twin)),
                           "activity_clone": [list(x) for x in twin.log.activity()]}
            twin = None
        new = body.world.intents[intents_before:]
        if not new or pulse > last_event_t:
            continue
        (t, delta_id), = new
        e = next(r for r in body.world.pending if r.origin == delta_id)
        if not (plan.window_first <= e.pulse <= plan.window_last):
            continue
        body_pending = _jsonable(body.world.export_state()["pending"])
        n = A.clone(body)
        n.world.cancel(e.rid)
        n_pending = _jsonable(n.world.export_state()["pending"])
        systems = {}
        f_cf, n_cf = A.clone(body), A.clone(n)
        f_fb, n_fb = A.clone(body), A.clone(n)
        for s in (f_cf, n_cf):
            s.declare([A.Intervention(A.FREEZE, all_plastic, A.ADVANCE)], label="CF-2")
        for s in (f_fb, n_fb):
            s.declare([A.Intervention(A.FB1, frozenset({feedback}))], label="FB-1")
        systems["N"] = _run_branch(n, t, plan.horizon)
        systems["F_CF"] = _run_branch(f_cf, t, plan.horizon, record_weights=True)
        systems["N_CF"] = _run_branch(n_cf, t, plan.horizon, record_weights=True)
        systems["F_FB"] = _run_branch(f_fb, t, plan.horizon, masked_key=feedback_key)
        systems["N_FB"] = _run_branch(n_fb, t, plan.horizon, masked_key=feedback_key)
        events.append({"t": t, "intent_delta_id": delta_id,
                       "e": {"rid": e.rid, "pulse": e.pulse, "receptor": e.receptor_id, "origin": e.origin},
                       "body_pending": body_pending, "n_pending": n_pending, "systems": systems})

    return {
        "seed": seed,
        "plan": asdict(plan),
        "roles": roles.as_dict(),
        "body": {
            "intents": [list(x) for x in body.world.intents],
            "sensory": _sensory(body),
            "activity": [list(x) for x in body.log.activity()],
            "realized": _jsonable(body.world.export_state()["realized"]),
            "pending_end": _jsonable(body.world.export_state()["pending"]),
            "checkpoints": checkpoints,
            "birth_units": _jsonable(birth_units),
        },
        "clone_check": clone_check,
        "events": events,
    }


def protocol_from_file() -> dict:
    return yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
