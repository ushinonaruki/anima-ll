"""実験 0035 の測定（確定した事前登録 v0.3：README §1〜§2・§6〜§8、protocol.yaml。#156 merge `b71d6fc`）。

seed ごとに measure_seed：
1. AS1 の本体を、AS1 の道具（experiments/as1_closed_loop/as1.py、#148）の build で、protocol の値（L ＝ 2・1 予約に 1 出来事・
   外の刺激なし・respond）で組み立て、Pulse を 1 つずつ進める。本体には介入をしない
2. 本体で意図が Pulse t に生まれ、その結果の予約 e の Pulse t ＋ 1 が区間 W に入れば（出来事）、Pulse t の処理の後で：
   - **Σ_t**：本体の `sigma` の書き出しを保存する（読み出すだけ。README §2.4）
   - **系 N**：本体の複製から、e の識別子の予約だけを取り消したもの。分岐の時点の Σ の SHA-256 を残し、t の後の最初の意図
     （源の発火の数で検知）か t ＋ H まで進める。感覚の出来事と、**すべての Unit の発火**を保存する（O5。監査 028 を N について閉じる）
   - **系 N′**：同じ分岐の時点からの、もう一つの系 N。来歴のログに感覚の出来事だけを残す（追加の発火の記録をしない）。
     τ・止まった Pulse・感覚の出来事と、止まった Pulse での Σ の SHA-256 を残す（O7 の (b)）
3. 本体を最後（body_runs_to）まで進める。Pulse clone_check.at の処理の後で作った介入なしの複製を clone_check.until まで進め、
   本体と Σ を比べるための写しを残す（O3）
4. **O7 の (a)**：同じ seed の本体を、Σ_t の記録・系 N の分岐・複製をしない形でもう一度走らせる。意図・感覚の出来事・発火の列と、
   Pulse 300・600・…・2099 と各出来事の t での Σ の SHA-256 を残す（比べるために Σ を読むだけ。rerun）
5. **O7 の (a) の補い（監査 034）**：上の走り直しも Σ を読むので、両方で読むだけでは読み出しそのものの副作用を検出できない。
   そこで、途中で Σ を一度も読まず、分岐も複製もしない走り直しをもう一つ行い、意図・感覚の出来事・発火の列と、最後の Pulse
   （body_runs_to）での Σ の SHA-256 を残す（rerun_plain）。最後の Σ だけで途中のすべての状態の一致を証明したとは言わない

生の記録だけを返す。予測（二経路近似）・判定の量（s_e・Q_i・J_S）と補助の量は計算しない（analyze.py）。
"""

import copy
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


A = _load("as1_tools_for_0035", REPO / "experiments" / "as1_closed_loop" / "as1.py")


@dataclass(frozen=True)
class Plan:
    """測定の区間。本番の値は protocol の式から（formal_plan）。契約テストだけが小さい Plan を使う。"""

    window_first: int          # 結果の刺激 e の Pulse の最初
    window_last: int           # 同じく最後
    horizon: int               # H
    body_runs_to: int          # 本体を進める最後の Pulse
    checkpoints: tuple[int, ...]   # R7：接続の状態を残す Pulse（O7 の (a) で Σ を比べる Pulse でもある）
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
    checkpoints = tuple(protocol["auxiliary"]["R7_weights"]["pulses"])
    return Plan(first, last, horizon, body, checkpoints, clone_check_at=300, clone_check_until=600)


def body_log_keep(protocol: dict) -> frozenset[str]:
    """protocol の records.body_log_keep（RuntimeEventType の名前）を、来歴の出来事の種類の値にする。"""
    return frozenset(getattr(A.RuntimeEventType, name) for name in protocol["records"]["body_log_keep"])


# 系 N′ の来歴のログ：感覚の出来事だけ（O4 に要るもの。τ は源の発火の数で検知するのでログに依らない）
N_PRIME_LOG_KEEP = frozenset({A.RuntimeEventType.SENSORY})


def manifest_raw() -> dict:
    return A.as1_manifest_raw()


def _jsonable(x):
    """sigma などの写しを JSON の形（タプル → リスト、鍵は文字列）にそろえる。"""
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    return x


def sigma_sha256(sigma_json) -> str:
    """Σ（JSON の形）の正規の書き出しの SHA-256。保存して読み直した形と同じになるよう、先に JSON を一度通す。"""
    canonical = json.dumps(json.loads(json.dumps(sigma_json)), separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _sigma(system) -> dict:
    return _jsonable(A.sigma(system))


def _sensory(system) -> list[list]:
    return [[p, r] for p, r in system.log.sensory()]


def _event_at(body, intents_before: int, plan: Plan, delay: int):
    """本体の今の Pulse に生まれた意図が出来事なら (t, delta_id, e) を返す。"""
    new = body.world.intents[intents_before:]
    if not new or body.pulse > plan.window_last - (delay - 1):
        return None
    (t, delta_id), = new
    e = next(r for r in body.world.pending if r.origin == delta_id)
    if not (plan.window_first <= e.pulse <= plan.window_last):
        return None
    return t, delta_id, e


def _run_n(system, t: int, horizon: int, *, record_firings: bool) -> dict:
    """t の処理の後から、最初の意図か t ＋ H まで 1 Pulse ずつ進める（τ の検知は道具の advance_until_first_intent）。"""
    tau = A.advance_until_first_intent(system, t, t + horizon)
    out = {"tau": tau, "stopped_at": system.pulse, "sensory": _sensory(system),
           "sigma_stop_sha256": sigma_sha256(_sigma(system))}
    if record_firings:
        out["firings"] = [list(x) for x in system.log.activity()]
    return out


def body_rerun(protocol: dict, seed: int, plan: Plan) -> dict:
    """O7 の (a)：Σ_t の記録・系 N の分岐・複製をしない本体。比べるために、決めた Pulse で Σ を読むだけ。"""
    world = protocol["world"]
    delay = int(world["delay_L"])
    body = A.build(seed, delay=delay, multiplicity=world["multiplicity"], respond=bool(world["respond"]),
                   exogenous=(), log=A.AS1Log(keep=body_log_keep(protocol)))
    sigma_at: dict[str, str] = {}
    for pulse in range(1, plan.body_runs_to + 1):
        intents_before = len(body.world.intents)
        A.advance_to(body.app, pulse)
        if pulse in plan.checkpoints or _event_at(body, intents_before, plan, delay) is not None:
            sigma_at[str(pulse)] = sigma_sha256(_sigma(body))
    return {"intents": [list(x) for x in body.world.intents], "sensory": _sensory(body),
            "activity": [list(x) for x in body.log.activity()], "sigma_sha256": sigma_at}


def body_rerun_plain(protocol: dict, seed: int, plan: Plan) -> dict:
    """O7 の (a) の補い（監査 034）：途中で Σ を一度も読まず、分岐も複製もしない本体。最後の Pulse の後で一度だけ Σ を読む。"""
    world = protocol["world"]
    body = A.build(seed, delay=int(world["delay_L"]), multiplicity=world["multiplicity"], respond=bool(world["respond"]),
                   exogenous=(), log=A.AS1Log(keep=body_log_keep(protocol)))
    A.advance_to(body.app, plan.body_runs_to)
    return {"intents": [list(x) for x in body.world.intents], "sensory": _sensory(body),
            "activity": [list(x) for x in body.log.activity()], "pulse": body.pulse,
            "sigma_end_sha256": sigma_sha256(_sigma(body))}


def measure_seed(protocol: dict, seed: int, plan: Plan | None = None) -> dict:
    plan = plan or formal_plan(protocol)
    world = protocol["world"]
    delay = int(world["delay_L"])
    if world["exogenous"]:
        raise ValueError("0035 は外の刺激を置かない（protocol の world.exogenous は空）")
    body = A.build(seed, delay=delay, multiplicity=world["multiplicity"], respond=bool(world["respond"]),
                   exogenous=(), log=A.AS1Log(keep=body_log_keep(protocol)))
    roles = body.roles
    birth_units = {u.unit_id: u.export_state() for u in body.app.units.all()}   # Pulse 0（沈黙の理由の記録：R2）
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
        sigma_t = _sigma(body)                                   # 分岐の時点の状態（読み出すだけ）
        body_pending = _jsonable(body.world.export_state()["pending"])
        n = A.clone(body)
        n.world.cancel(e.rid)
        n_prime = A.clone(n)
        n_prime.log.keep = N_PRIME_LOG_KEEP                       # N′：追加の発火の記録をしない（O7 の (b)）
        n_pending = _jsonable(n.world.export_state()["pending"])
        n_branch_sha = sigma_sha256(_sigma(n))
        n_out = _run_n(n, t, plan.horizon, record_firings=True)
        n_prime_out = _run_n(n_prime, t, plan.horizon, record_firings=False)
        events.append({"t": t, "intent_delta_id": delta_id,
                       "e": {"rid": e.rid, "pulse": e.pulse, "receptor": e.receptor_id, "origin": e.origin},
                       "sigma_t": sigma_t, "body_pending": body_pending, "n_pending": n_pending,
                       "n_branch_sigma_sha256": n_branch_sha, "N": n_out, "N_prime": n_prime_out})

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
            "checkpoint_sigma_sha256": checkpoint_sigma,
            "birth_units": _jsonable(birth_units),
        },
        "clone_check": clone_check,
        "events": events,
        "rerun": body_rerun(protocol, seed, plan),
        "rerun_plain": body_rerun_plain(protocol, seed, plan),
    }


def expected_n_branch_sigma(sigma_t: dict, e: dict) -> dict:
    """O5 の (a)：Σ_t から、e の予約だけを取り消したときの系 N の分岐の時点の Σ を作る（pending から e を除き、cancelled に足す）。"""
    s = copy.deepcopy(sigma_t)
    world = s["world"]
    row = next(r for r in world["pending"] if r[0] == e["rid"])
    world["pending"] = [r for r in world["pending"] if r[0] != e["rid"]]
    world["cancelled"] = list(world["cancelled"]) + [row]
    return s


def protocol_from_file() -> dict:
    return yaml.safe_load((HERE / "protocol.yaml").read_text(encoding="utf-8"))
