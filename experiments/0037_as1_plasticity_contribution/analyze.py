"""実験 0037 の記録の解析（確定した事前登録 v0.2 に従う。正本は README・protocol.yaml。#168 merge `1c71f3c`）。

0036 の解析の契約（記録の確認、生の記録からの操作の確認、invalid なら判定しない、一度だけの report、解析の道具の HEAD ＝
測定の commit、smoke の盲検、O1 の記録の確かめ、結果の写しの照合）を引き継ぐ（ほかの実験の analyze.py は読み込まない）。

0. 解析する道具の commit（このリポジトリの HEAD）が、保存した測定の commit と同じで、作業ツリーがきれいなことを確かめる
1. 実行の記録（guard.py）を確かめる。未完了なら解析しない。失敗・中断・破損・範囲の外・別の測定の commit なら invalid
2. 操作の確認 O2〜O15（README §8）を、保存した生の記録から seed ごとに再検証する（D2）。一つでも成り立たなければ invalid で、
   判定の量を計算・表示しない。O1 は、run.py が seed に触れる前に測定の commit で走らせた契約テストの記録を確かめる（o1_check）
3. 判定（README §3〜§6）：本番・合成で、すべての seed が completed で invalid がないときだけ計算する
   - 個体ごと：適格（n_E(M) ≥ m_E。M の E の記録だけで決まる）、適格外の札（(a) E で源の発火が 0、(b) 源が P_E にだけ発火）、
     構造上の恒等（W_M ＝ W_0）、6 系の I_U と T1〜T3、§3.3 のすべての対比、P_i ＝ [I_U(M) ≠ I_U(M[W_0])]
   - J_C：m ＜ 10 なら判定不能。P_i の数 ≥ k(m) で成立。Clopper–Pearson の 95% は、J_C に依らず m ≥ 1 で計算する
   - §6.1 の記述の対照と、§6.2 の R1〜R8（判定に使わない）
4. report は一度だけ書く（既にあれば上書きしない。analysis_log.jsonl に開始・完了と入力の SHA-256 を残す）

使い方（リポジトリ直下で、測定の commit を checkout したきれいな作業ツリーで）:
  python experiments/0037_as1_plasticity_contribution/analyze.py                    # 本番（data/experiments/0037）
  python experiments/0037_as1_plasticity_contribution/analyze.py <フォルダ> --smoke   # smoke（操作の確認だけ）
  python experiments/0037_as1_plasticity_contribution/analyze.py --verify-copy <写し>   # 本番の出力先と写しの照合
"""

import argparse
import dataclasses
import gzip
import importlib.util
import json
import math
import re
import statistics
from collections.abc import Mapping
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent.relative_to(REPO)
PROTOCOL_PATH = HERE / "protocol.yaml"
PROTOCOL = yaml.safe_load((REPO / PROTOCOL_PATH).read_text(encoding="utf-8"))
EXPERIMENT, KIND = PROTOCOL["experiment"], PROTOCOL["kind"]
OUT_DIR = Path("data/experiments/0037")
SEED_RANGES = {"formal": "seeds", "smoke": "smoke_seeds", "synthetic": "synthetic_seeds"}
CHECK_NAMES = ("structure",) + tuple(f"O{i}" for i in range(2, 16))
REPORT, LOG = "report.json", "analysis_log.jsonl"
CONTRACT_TESTS = ("tests/integration/test_as1_contract.py", "tests/integration/test_as1_plasticity_contribution_0037.py")
O1_FILE = "o1_contract_tests.json"
O1_KEYS = {"measurement_commit", "command", "exit_code", "summary", "test_files_sha256", "at"}
BLIND_KEYS = {"checks", "raw_sha256"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
F1_TOLERANCE = 1e-15          # O14：組の和と w_max の差（浮動小数の誤差の範囲。AS1 の契約テスト i5 と同じ）


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


G = load(f"guard_{EXPERIMENT}_analyze", REPO / HERE / "guard.py")
M = load(f"measure_{EXPERIMENT}_analyze", REPO / HERE / "measure.py")
ALIGN = load(f"alignment_{EXPERIMENT}_analyze", REPO / HERE / "alignment.py")
A = M.A
M_E = int(PROTOCOL["judgment"]["per_individual"]["m_E"])
W_MAX = float(PROTOCOL["brain"]["w_max"])
W0 = float(PROTOCOL["brain"]["initial_weight_w0"])

# §3.3 の対比：名前 → (a, b)。数の量は T(a) − T(b)、存在は I_U(a) ≠ I_U(b)（protocol の quantities.contrasts と同じ）
CONTRASTS = {"C_tr": ("M", "M_W0"), "C_tr_rev": ("Y_WM", "Y"), "C_rep": ("M", "Y"), "H_ext": ("Y", "K"),
             "C_PC1": ("M", "K"), "S_WM": ("M", "Y_WM"), "S_W0": ("M_W0", "Y")}
REQUIRED_CONTROLS = ("C_tr_rev", "C_rep", "H_ext")
ALSO_CONTROLS = ("C_PC1", "S_WM", "S_W0")
HORIZONTAL_PATTERNS = ("equal under both states", "differs only under M's state", "differs only under Y's state",
                       "differs under both states")


def expected_seeds(mode: str) -> list[int]:
    s = PROTOCOL[SEED_RANGES[mode]]
    return list(range(s["first"], s["last"] + 1))


def read_raw(path: Path) -> dict:
    return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))


# ---- 量（README §3） -------------------------------------------------------------------------------

def sign(x: int) -> str:
    return "+" if x > 0 else ("-" if x < 0 else "0")


def t_values(intents: list[int], p_e: int) -> dict:
    """T1・T2・T3（README §3.1）。T2 は U に意図がなければ None（打ち切り）、T3 は意図が 2 つ以上のときだけ。"""
    xs = sorted(intents)
    gaps = [b - a for a, b in zip(xs, xs[1:])]
    return {"T1": len(xs), "T2": (xs[0] - p_e) if xs else None, "T3": statistics.median(gaps) if gaps else None}


def t2_sign(a: int | None, b: int | None) -> str:
    """T2(a) − T2(b) の符号（README §3.2）。打ち切りの方が大きい。両方が打ち切りなら ？。"""
    if a is not None and b is not None:
        return sign(a - b)
    if a is None and b is not None:
        return "+"
    if a is not None and b is None:
        return "-"
    return "?"


def _by_pulse(activity: list, lo: int, hi: int) -> dict[int, list[str]]:
    out: dict[int, list[str]] = {p: [] for p in range(lo, hi + 1)}
    for p, u in activity:
        if lo <= p <= hi:
            out[p].append(u)
    return {p: sorted(us) for p, us in out.items()}


def first_divergence(act_a: list, act_b: list, lo: int, hi: int) -> int | None:
    """区間 [lo, hi] で、全 Unit の発火の集まりが最初に違った Pulse（違わなければ None）。"""
    a, b = _by_pulse(act_a, lo, hi), _by_pulse(act_b, lo, hi)
    return next((p for p in range(lo, hi + 1) if a[p] != b[p]), None)


def first_intent_divergence(ia: list[int], ib: list[int], lo: int, hi: int) -> int | None:
    sa, sb = set(ia), set(ib)
    return next((p for p in range(lo, hi + 1) if (p in sa) != (p in sb)), None)


def _role_names(roles: Mapping) -> dict[str, str]:
    return {roles["source"]: "source", roles["receiver"]: "receiver", roles["other"]: "other"}


def _ends(cid: str) -> tuple[str, str]:
    src, tgt = cid.split(".main->")
    return src, tgt


def pair_sums(weights: Mapping[str, float]) -> dict[str, float]:
    sums: dict[str, float] = {}
    for cid, w in sorted(weights.items()):
        key = "|".join(sorted(_ends(cid)))
        sums[key] = sums.get(key, 0.0) + w
    return sums


def individual(run: Mapping) -> dict:
    """1 個体の量（README §3・§4.1・§4.2・§6）。生の記録だけから計算する。"""
    roles, plan = run["roles"], run["plan"]
    p_e, end = plan["p_e"], plan["p_e"] + plan["u_length"]
    source = roles["source"]
    names = _role_names(roles)
    src_e = {"M": sum(1 for _, u in run["M_E"]["activity"] if u == source),
             **{n: sum(1 for _, u in run["E"][n]["activity"] if u == source) for n in ("Y", "K")}}
    cons_e = {"M": len(run["M_E"]["sensory"]), **{n: len(run["E"][n]["sensory"]) for n in ("Y", "K")}}
    n_e_m = cons_e["M"]
    eligible = n_e_m >= M_E
    kind = None if eligible else ("a" if src_e["M"] == 0 else "b")
    w_0, w_m = run["W_0"], run["boundary"]["W_M"]
    identity = w_m == w_0
    i_u = {n: sorted(p for p, _ in run["U"][n]["intents"]) for n in M.U_SYSTEMS}
    tv = {n: t_values(i_u[n], p_e) for n in M.U_SYSTEMS}
    contrasts = {}
    for name, (a, b) in CONTRASTS.items():
        ta, tb = tv[a], tv[b]
        contrasts[name] = {
            "exists": i_u[a] != i_u[b],
            "T1_diff": ta["T1"] - tb["T1"], "T1_sign": sign(ta["T1"] - tb["T1"]),
            "T2_sign": t2_sign(ta["T2"], tb["T2"]),
            "T2_diff": (ta["T2"] - tb["T2"]) if ta["T2"] is not None and tb["T2"] is not None else None,
            "T3_diff": (ta["T3"] - tb["T3"]) if ta["T3"] is not None and tb["T3"] is not None else None,
            "first_divergence_firing": first_divergence(run["U"][a]["activity"], run["U"][b]["activity"], p_e + 1, end),
            "first_divergence_intent": first_intent_divergence(i_u[a], i_u[b], p_e + 1, end),
        }
    activity = {n: {names[u]: sum(1 for _, x in run["U"][n]["activity"] if x == u) for u in names} for n in M.U_SYSTEMS}
    role_cid = {cid: f"{names[_ends(cid)[0]]}->{names[_ends(cid)[1]]}" for cid in w_0}
    return {
        "eligible": eligible,
        "ineligible_kind": kind,
        "n_E_M": n_e_m,
        "source_firings_E": src_e,
        "consequences_E": cons_e,
        "structural_identity": identity,
        "I_U": i_u,
        "T": tv,
        "contrasts": contrasts,
        "P_i": eligible and contrasts["C_tr"]["exists"],
        "delta_w": {role_cid[cid]: w_m[cid] - w_0[cid] for cid in sorted(w_0)},
        "W_M": {role_cid[cid]: w_m[cid] for cid in sorted(w_0)},
        "pair_sums_W_M": pair_sums(w_m),
        # R2：M の記録の Pulse（本番は 300〜1800）の 6 本の重み・痕跡・組の和（0036 の R10 と同じ形）
        "M_checkpoints": {p: {"weights": {role_cid[c]: v["weight"] for c, v in sorted(st.items())},
                              "traces": {role_cid[c]: {"pre_trace": v["pre_trace"], "post_trace": v["post_trace"]}
                                         for c, v in sorted(st.items())},
                              "pair_sums": pair_sums({c: v["weight"] for c, v in st.items()})}
                          for p, st in sorted(run["M_E"]["checkpoints"].items(), key=lambda x: int(x[0]))},
        "activity_U": activity,
    }


# ---- 判定（README §4・§5） -----------------------------------------------------------------------------

def binom_upper_tail(m: int, k: int) -> float:
    return sum(math.comb(m, j) for j in range(k, m + 1)) / 2 ** m


def k_of_m(m: int, alpha: float) -> int:
    return next(k for k in range(m + 2) if k > m or binom_upper_tail(m, k) <= alpha)


def clopper_pearson(x: int, n: int, level: float = 0.95) -> tuple[float, float]:
    """二項の和の二分法（0036 と同じ）。"""
    a = 1 - level

    def cdf(k: int, p: float) -> float:
        return sum(math.comb(n, j) * p ** j * (1 - p) ** (n - j) for j in range(0, k + 1))

    def solve(f, lo=0.0, hi=1.0) -> float:
        for _ in range(200):
            mid = (lo + hi) / 2
            if f(mid):
                hi = mid
            else:
                lo = mid
        return (lo + hi) / 2

    lower = 0.0 if x == 0 else solve(lambda p: 1 - cdf(x - 1, p) >= a / 2)
    upper = 1.0 if x == n else solve(lambda p: cdf(x, p) <= a / 2)
    return lower, upper


def interval(x: int, n: int) -> dict:
    """§5.2：m ≥ 1 なら必ず計算する（判定に使わない）。m ＝ 0 なら計算できない。"""
    if n < 1:
        return {"computed": False, "interval": None, "numerator": x, "denominator": n, "reason": "m = 0"}
    return {"computed": True, "interval": list(clopper_pearson(x, n)), "numerator": x, "denominator": n}


def judge(individuals: Mapping[str, Mapping]) -> dict:
    """J_C（README §4.3）と、同じ分母の Clopper–Pearson（§5.2。J_C の成立・不成立・判定不能に依らない）。"""
    j = PROTOCOL["judgment"]["J_C"]
    eligible = [s for s, v in individuals.items() if v["eligible"]]
    m = len(eligible)
    holds = sum(1 for s in eligible if individuals[s]["P_i"])
    iv = interval(holds, m)
    if m < j["min_population"]:
        return {"J_C": {"m": m, "count_P_i": holds, "k": None, "status": "inconclusive"}, "interval": iv}
    k = j["k_of_m"][m]
    if k != k_of_m(m, j["alpha"]):
        raise ValueError(f"protocol の k({m}) ＝ {k} が二項の計算と違う")
    return {"J_C": {"m": m, "count_P_i": holds, "k": k, "tail_probability": binom_upper_tail(m, k),
                    "status": "established" if holds >= k else "not_established"},
            "interval": iv}


def five_numbers(values: list) -> dict | None:
    """最小・四分位・最大（statistics.quantiles の inclusive。値が 1 つならすべてその値、0 なら null。0036 と同じ）。"""
    if not values:
        return None
    xs = sorted(values)
    q = statistics.quantiles(xs, n=4, method="inclusive") if len(xs) >= 2 else [xs[0]] * 3
    return {"count": len(xs), "min": xs[0], "q1": q[0], "median": q[1], "q3": q[2], "max": xs[-1]}


def descriptive_controls(individuals: Mapping[str, Mapping]) -> dict:
    """README §6.1：記述の対照（検定しない）。分母は J_C と同じ適格な個体。適格外は (a)・(b) の別の表。"""
    eligible = [v for v in individuals.values() if v["eligible"]]
    m = len(eligible)
    out = {"m": m, "contrasts": {}}
    for name in REQUIRED_CONTROLS + ALSO_CONTROLS:
        count = sum(1 for v in eligible if v["contrasts"][name]["exists"])
        out["contrasts"][name] = {"required": name in REQUIRED_CONTROLS, "count": count,
                                  "proportion": count / m if m else None, "interval": interval(count, m)}
    out["contrasts"]["C_tr_rev"]["structural_identity_label"] = sum(1 for v in eligible if v["structural_identity"])
    patterns = dict.fromkeys(HORIZONTAL_PATTERNS, 0)
    for v in eligible:
        a, b = v["contrasts"]["C_tr"]["exists"], v["contrasts"]["C_tr_rev"]["exists"]
        key = {(False, False): 0, (True, False): 1, (False, True): 2, (True, True): 3}[(a, b)]
        patterns[HORIZONTAL_PATTERNS[key]] += 1
    out["horizontal_pattern"] = patterns
    out["ineligible"] = {}
    for kind in ("a", "b"):
        group = [v for v in individuals.values() if v["ineligible_kind"] == kind]
        out["ineligible"][kind] = {"count": len(group),
                                   "contrasts": {name: sum(1 for v in group if v["contrasts"][name]["exists"])
                                                 for name in CONTRASTS}}
    return out


def auxiliary(individuals: Mapping[str, Mapping]) -> dict:
    """README §6.2 の R1〜R7 の全体の数（判定に使わない。R8 は judgment の interval）。分母は適格な個体。"""
    vals = list(individuals.values())
    eligible = [v for v in vals if v["eligible"]]
    out = {"R1": {"individuals": len(vals), "eligible": len(eligible),
                  "ineligible_a": sum(1 for v in vals if v["ineligible_kind"] == "a"),
                  "ineligible_b": sum(1 for v in vals if v["ineligible_kind"] == "b"),
                  "structural_identity_eligible": sum(1 for v in eligible if v["structural_identity"])}}
    roles_cid = sorted(eligible[0]["delta_w"]) if eligible else []
    out["R2"] = {"delta_w": {c: five_numbers([v["delta_w"][c] for v in eligible]) for c in roles_cid},
                 "delta_w_over_w0": {c: five_numbers([v["delta_w"][c] / W0 for v in eligible]) for c in roles_cid},
                 "pair_sum_max_abs_deviation": max((abs(s - W_MAX) for v in eligible for s in v["pair_sums_W_M"].values()),
                                                   default=None)}
    out["R4"], out["R5"], out["R6"] = {}, {}, {}
    for name in CONTRASTS:
        cs = [v["contrasts"][name] for v in eligible]
        out["R4"][name] = {"T1": {s: sum(1 for c in cs if c["T1_sign"] == s) for s in ("+", "-", "0")},
                           "T2": {s: sum(1 for c in cs if c["T2_sign"] == s) for s in ("+", "-", "0", "?")}}
        out["R5"][name] = {"T1_diff": five_numbers([c["T1_diff"] for c in cs]),
                           "T2_diff": five_numbers([c["T2_diff"] for c in cs if c["T2_diff"] is not None]),
                           "T3_diff": five_numbers([c["T3_diff"] for c in cs if c["T3_diff"] is not None])}
        out["R6"][name] = {}
        for key in ("first_divergence_firing", "first_divergence_intent"):
            got = [c[key] for c in cs if c[key] is not None]
            out["R6"][name][key] = {"none": sum(1 for c in cs if c[key] is None), "pulses": five_numbers(got)}
    out["R7"] = {n: {role: five_numbers([v["activity_U"][n][role] for v in eligible]) for role in ("source", "receiver", "other")}
                 for n in M.U_SYSTEMS}
    return out


# ---- 操作の確認（README §8） -----------------------------------------------------------------------------

RUN_KEYS = {"seed", "plan", "roles", "birth_units", "W_0", "M_E", "E", "boundary", "U"}
M_E_KEYS = {"activity", "sensory", "intents", "schedule", "pending_at_p_e", "checkpoints"}
E_BASE = {"activity", "sensory", "intents"}
E_KEYS = {"Y": E_BASE | {"pulse_weights"}, "K": E_BASE | {"pulse_weights"}, "Y_on": E_BASE | {"sigma_p_e"},
          "M_rerun": E_BASE | {"sigma_p_e_sha256"}}
BOUNDARY_KEYS = {"steps", "W_M", "sigma_a", "sigma_b"}
U_KEYS = {"activity", "sensory", "intents", "pulse_weights", "sigma_after_first", "sigma_end_sha256", "world_end",
          "history", "world_switches", "pulse_end"}
EMPTY_INTERVENTIONS = {"active": [], "frozen": {}}


def _six(run) -> list[str]:
    return sorted(run["W_0"])


def _freeze(run) -> list:
    return [["FREEZE", _six(run), A.ADVANCE]]


def _pending_pr(world: Mapping) -> list[list]:
    """予約の列の、これからの軌道に効く部分：(Pulse, Receptor) の集まり（README §8 の O7 (b)）。"""
    return sorted([row[3], row[2]] for row in world["pending"])


def _weights_of(sigma: Mapping) -> dict[str, float]:
    return {cid: v["weight"] for cid, v in sorted(sigma["connections"].items())}


def check_seed(data: Mapping, mode: str, seed: int, plan: "M.Plan | None" = None) -> dict[str, list[str]]:
    """1 個体の操作の確認。確認の名前 → 成り立たなかった理由（空なら成り立った）。"""
    out = {k: [] for k in CHECK_NAMES}
    try:
        run = data["run"]
        _structure(data, mode, seed, plan, out["structure"])
        if not out["structure"]:
            for name, f in (("O2", _o2), ("O3", _o3), ("O4", _o4), ("O5", _o5), ("O6", _o6), ("O7", _o7),
                            ("O8", _o8), ("O9", _o9), ("O10", _o10), ("O11", _o11), ("O13", _o13), ("O14", _o14),
                            ("O15", _o15)):
                try:
                    f(run, out[name])
                except Exception as e:                       # 記録の形が壊れていても止めずに、その確認を不成立にする
                    out[name].append(f"記録を読めない：{e!r}")
        _o12(seed, mode, out["O12"])
    except Exception as e:
        out["structure"].append(f"記録を読めない：{e!r}")
    return out


def _structure(data, mode, seed, plan, out) -> None:
    run = data.get("run", {})
    if set(data) != {"meta", "run"}:
        out.append(f"raw の最上位の欄が {sorted(data)}")
    if set(run) != RUN_KEYS:
        out.append(f"run の欄が {sorted(run)}（判定の量の欄を raw に入れない）")
        return
    if set(run["M_E"]) != M_E_KEYS or set(run["E"]) != set(E_KEYS) \
            or any(set(run["E"][n]) != keys for n, keys in E_KEYS.items()):
        out.append("M_E・E の欄が違う")
    if set(run["boundary"]) != BOUNDARY_KEYS or set(run["U"]) != set(M.U_SYSTEMS) \
            or any(set(run["U"][n]) != U_KEYS for n in M.U_SYSTEMS) \
            or set(run["boundary"]["sigma_a"]) != set(M.U_SYSTEMS) or set(run["boundary"]["sigma_b"]) != set(M.U_SYSTEMS):
        out.append("boundary・U の欄・系の組が違う")
    if run["seed"] != seed:
        out.append(f"seed が {run['seed']}")
    want = plan or M.formal_plan(PROTOCOL)
    if mode in ("formal", "smoke") and plan is not None and plan != M.formal_plan(PROTOCOL):
        out.append("本番・smoke では protocol の Plan だけを使う")
    if run["plan"] != json.loads(json.dumps(dataclasses.asdict(want))):
        out.append("raw の plan が使う Plan と違う")
    if run["roles"] != A.assign_roles(seed).as_dict():
        out.append("役の割り当てが assign_roles と違う")
    if len(run["W_0"]) != 6 or set(run["W_0"].values()) != {W0}:
        out.append("W_0 が出生時の値（6 本とも w0）ではない")
    meta = data.get("meta", {})
    for k, v in (("experiment", EXPERIMENT), ("kind", KIND), ("mode", mode), ("seed", seed)):
        if meta.get(k) != v:
            out.append(f"meta の {k} が {meta.get(k)}")
    if meta.get("manifest") != M.manifest_raw():
        out.append("meta の設計図が AS1 の設計図と違う")
    want_blind = {"smoke": True, "formal": False}.get(mode)
    if not isinstance(meta.get("blind"), bool) or (want_blind is not None and meta["blind"] is not want_blind):
        out.append(f"meta の blind が {meta.get('blind')}（smoke は盲検、本番は盲検でない）")


def _ic1(activity, intents, source, lo, hi) -> bool:
    return [p for p, u in activity if u == source and lo <= p <= hi] == [p for p, _ in intents if lo <= p <= hi]


def _o2(run, out) -> None:
    """閉ループの契約（0034 の O2：IC-1・WC-2・K1・W-2）。E の M・K と、U の 6 系。U の WC-2 は O8 で確かめる。"""
    roles, plan = run["roles"], run["plan"]
    p_e, end = plan["p_e"], plan["p_e"] + plan["u_length"]
    src, cons, src_r = roles["source"], roles["consequence_receptor"], roles["source_receptor"]
    for name, rec in (("M", run["M_E"]), ("K", run["E"]["K"])):
        intents = [p for p, _ in rec["intents"]]
        if not _ic1(rec["activity"], rec["intents"], src, 1, p_e):
            out.append(f"{name}：E の意図の列が、源の発火の列と違う（IC-1）")
        if rec["sensory"] != [[p + 1, cons] for p in intents if p + 1 <= p_e]:
            out.append(f"{name}：E の感覚の出来事が、意図ごとに t + 1 の結果の Receptor へ 1 つ、だけになっていない（WC-2）")
    for name in ("Y", "Y_on"):
        if not _ic1(run["E"][name]["activity"], run["E"][name]["intents"], src, 1, p_e):
            out.append(f"{name}：E の意図の列が、源の発火の列と違う（IC-1。出口はある）")
    for name in M.U_SYSTEMS:
        u = run["U"][name]
        if not _ic1(u["activity"], u["intents"], src, p_e + 1, end):
            out.append(f"{name}：U の意図の列が、源の発火の列と違う（IC-1）")
        if any(r == src_r for _, r in u["sensory"]):
            out.append(f"{name}：U で源の Receptor に刺激がある（K1）")
        if any(len(rids) != 1 or n != 1 for _, _, rids, n in u["world_end"]["realized"]):
            out.append(f"{name}：予約が同じ Pulse に重なった（W-2）")
    if any(r == src_r for _, r in run["M_E"]["sensory"] + run["E"]["K"]["sensory"]):
        out.append("E で源の Receptor に刺激がある（K1）")


def _o3(run, out) -> None:
    """再生の忠実さ（CT-PC1 の (i)・(ii)）。"""
    m_e = run["M_E"]
    want = sorted([list(x) for x in m_e["sensory"]] + _pending_pr({"pending": m_e["pending_at_p_e"]}))
    if sorted(m_e["schedule"]) != want or m_e["schedule"][:len(m_e["sensory"])] != m_e["sensory"]:
        out.append("再生の予定が、M の E の感覚の出来事と P_E の予約（持ち越し）になっていない")
    for name in ("Y", "Y_on"):
        if run["E"][name]["sensory"] != m_e["sensory"]:
            out.append(f"{name}：E に受けた感覚の出来事が、M の S^ext と違う")
    worlds = {"Y": run["boundary"]["sigma_a"]["Y"]["world"], "Y_on": run["E"]["Y_on"]["sigma_p_e"]["world"]}
    for name, w in worlds.items():
        if w["next_rid"] != len(m_e["schedule"]) or any(row[1] != "exogenous" for row in w["pending"]) \
                or w["rule"]["respond"] is not False:
            out.append(f"{name}：E の意図が予約を作った（開いたループではない）")
        if _pending_pr(w) != _pending_pr({"pending": m_e["pending_at_p_e"]}):
            out.append(f"{name}：P_E の予定の残りが、M の持ち越しと違う")


def _o4(run, out) -> None:
    """命題 G-2（SE-1）：Y^ON は P_E まで M と同じ。M は S1〜S3 で変わらないので、Σ (a) の M が P_E の M。"""
    y_on, m = run["E"]["Y_on"], run["M_E"]
    if y_on["activity"] != m["activity"] or y_on["intents"] != m["intents"]:
        out.append("Y^ON の E の発火・意図が M と違う")
    sm, sy = run["boundary"]["sigma_a"]["M"], y_on["sigma_p_e"]
    for key in ("units", "connections", "drives"):
        if sm[key] != sy[key]:
            out.append(f"Y^ON の P_E の {key} が M と違う（G-2）")


def _o5(run, out) -> None:
    """E の FREEZE（CT-PC3）：Y・K の 6 本の重みが、E のすべての Pulse で W_0。"""
    p_e = run["plan"]["p_e"]
    for name in M.E_FROZEN:
        rows = run["E"][name]["pulse_weights"]
        if [p for p, _ in rows] != list(range(1, p_e + 1)):
            out.append(f"{name}：E の Pulse ごとの重みの記録が 1〜P_E にそろっていない")
        if any(w != run["W_0"] for _, w in rows):
            out.append(f"{name}：E のある Pulse で、6 本の重みが W_0 と違う")


def expected_steps(run) -> list:
    p_e, six = run["plan"]["p_e"], _six(run)
    end = p_e + run["plan"]["u_length"]
    steps = [["S0", n, p_e, "advance_to", {"from": 0}] for n in M.S0_ORDER]
    steps += [["S1", n, p_e, "clear", None] for n in M.E_FROZEN]
    steps += [["S2", n, p_e, "clone", {"from": src}] for n, (src, _) in M.TRANSPLANTS.items()]
    steps += [["S3", n, p_e, "transplant", {"to": key, "intervention_state_at_transplant": EMPTY_INTERVENTIONS}]
              for n, (_, key) in M.TRANSPLANTS.items()]
    steps += [["S4", n, p_e, "switch_world", {"respond": True}] for n in M.SWITCHED]
    steps += [["S5", n, p_e, "declare", {"FREEZE": six, "trace_policy": A.ADVANCE}] for n in M.U_SYSTEMS]
    steps += [["S6", n, end, "advance_to", {"from": p_e}] for n in M.U_SYSTEMS]
    return steps


def expected_history(run, name: str) -> list:
    p_e, freeze = run["plan"]["p_e"], _freeze(run)
    lineage = M.TRANSPLANTS.get(name, (name,))[0]
    if lineage in M.E_FROZEN:
        return [[0, M.E_LABEL, freeze], [p_e, M.S1_LABEL, []], [p_e, M.S5_LABEL, freeze]]
    return [[p_e, M.S5_LABEL, freeze]]


def _o6(run, out) -> None:
    """境界の順序（CT-PC4 の (iv)〜(vi)）：S0〜S6 の記録、介入の履歴、世界の切り替えの記録。"""
    if run["boundary"]["steps"] != expected_steps(run):
        out.append("S0〜S6 の記録が、決めた順序・Pulse・操作と違う（移植の時の介入の状態が空でないものを含む）")
    p_e, end = run["plan"]["p_e"], run["plan"]["p_e"] + run["plan"]["u_length"]
    for name in M.U_SYSTEMS:
        u = run["U"][name]
        if u["history"] != expected_history(run, name):
            out.append(f"{name}：介入の宣言・解除の履歴が、決めたもの（U の FREEZE の宣言は一度だけ）と違う")
        want_switch = [[p_e, M.S4_LABEL, True]] if name in M.SWITCHED else []
        if u["world_switches"] != want_switch:
            out.append(f"{name}：世界の規則の切り替えの記録が違う")
        if u["pulse_end"] != end:
            out.append(f"{name}：U の終わりの Pulse が {u['pulse_end']}")
    for key in ("sigma_a", "sigma_b"):
        if any(run["boundary"][key][n]["pulse"] != p_e for n in M.U_SYSTEMS):
            out.append(f"{key} の Pulse の番号が P_E ではない（S1〜S5 のあいだに Pulse を進めた）")


ALLOWED_TOP_M_Y = {"units", "connections", "drives", "deltas", "issuer", "world"}
ALLOWED_WORLD_M_Y = {"rule", "intents", "realized", "pending", "next_rid", "cancelled"}


def _o7(run, out) -> None:
    """差の目録（CT-PC5）。(a) S3 の直後、(b) S5 の直後。"""
    sa, sb = run["boundary"]["sigma_a"], run["boundary"]["sigma_b"]
    w_0, w_m = run["W_0"], run["boundary"]["W_M"]
    targets = {"W_0": w_0, "W_M": w_m}
    for name, (src, key) in M.TRANSPLANTS.items():
        diff = A.sigma_diff(sa[src], sa[name])
        want = [("connections", cid, "weight") for cid in sorted(w_0) if _weights_of(sa[src])[cid] != targets[key][cid]]
        if sorted(tuple(d) for d in diff) != sorted(want):
            out.append(f"(a) {src} と {name} の Σ の違いが、移植した重みだけではない")
        if _weights_of(sa[name]) != targets[key]:
            out.append(f"(a) {name} の重みが移植の先（{key}）と違う")
        if sa[name]["interventions"] != EMPTY_INTERVENTIONS or sa[src]["interventions"] != EMPTY_INTERVENTIONS:
            out.append(f"(a) {src}・{name} の介入の状態が空ではない")
    if _weights_of(sa["M"]) != w_m:
        out.append("(a) M の重みが記録した W_M と違う")
    for path in A.sigma_diff(sa["M"], sa["Y"]):
        top = path[0]
        if top not in ALLOWED_TOP_M_Y or (top == "world" and (len(path) < 2 or path[1] not in ALLOWED_WORLD_M_Y)) \
                or (top == "world" and path[1] == "rule" and tuple(path) != ("world", "rule", "respond")):
            out.append(f"(a) M と Y の Σ の違いに、決めた欄の外のもの（{list(path)}）がある")
            break
    for name in M.U_SYSTEMS:
        s = sb[name]
        frozen = s["interventions"]["frozen"]
        if s["interventions"]["active"] != _freeze(run) or set(frozen) != set(w_0):
            out.append(f"(b) {name} の U の介入が 6 本の FREEZE（advance）ではない")
            continue
        for cid, v in s["connections"].items():
            if frozen[cid] != {"weight": v["weight"], "pre_trace": v["pre_trace"], "post_trace": v["post_trace"],
                               "policy": A.ADVANCE}:
                out.append(f"(b) {name} の FREEZE の値が、宣言の時点の重み・痕跡と違う")
                break
    ref = sb["M"]["world"]
    for name in ("M_W0", "M_WM", "Y", "Y_WM"):
        w = sb[name]["world"]
        if _pending_pr(w) != _pending_pr(ref) or w["rule"] != ref["rule"]:
            out.append(f"(b) {name} の、これからの軌道を決める世界の状態（予約の Pulse・Receptor と規則）が M と違う")


def _o8(run, out) -> None:
    """持ち越しと、U の WC-2（CT-PC2）。"""
    roles, plan = run["roles"], run["plan"]
    p_e, end = plan["p_e"], plan["p_e"] + plan["u_length"]
    cons = roles["consequence_receptor"]
    carry_m = _pending_pr({"pending": run["M_E"]["pending_at_p_e"]})
    if _pending_pr(run["boundary"]["sigma_b"]["M"]["world"]) != carry_m:
        out.append("M の S5 の直後の予約が、P_E の予約（持ち越し）と違う")
    for name in M.U_SYSTEMS:
        u = run["U"][name]
        carry = carry_m if name != "K" else _pending_pr(run["boundary"]["sigma_b"]["K"]["world"])
        want = sorted(carry + [[t + 1, cons] for t, _ in u["intents"] if t + 1 <= end])
        if sorted(u["sensory"]) != want:
            out.append(f"{name}：U の感覚の出来事が、持ち越しと、U の意図ごとの t + 1 の結果だけになっていない")
        if any(p <= p_e for p, _ in u["sensory"]):
            out.append(f"{name}：U の記録に P_E 以前の感覚の出来事がある")


def _o9(run, out) -> None:
    """U の FREEZE と同じ規則（CT-PC7）。"""
    p_e, end = run["plan"]["p_e"], run["plan"]["p_e"] + run["plan"]["u_length"]
    targets = {"W_0": run["W_0"], "W_M": run["boundary"]["W_M"]}
    rules = set()
    for name in M.U_SYSTEMS:
        rows = run["U"][name]["pulse_weights"]
        if [p for p, _ in rows] != list(range(p_e + 1, end + 1)):
            out.append(f"{name}：U の Pulse ごとの重みの記録がそろっていない")
        if any(w != targets[M.FROZEN_VALUE[name]] for _, w in rows):
            out.append(f"{name}：U のある Pulse で、6 本の重みが宣言の値（{M.FROZEN_VALUE[name]}）と違う")
        for w in (run["boundary"]["sigma_b"][name]["world"], run["U"][name]["world_end"]):
            rules.add(json.dumps(w["rule"], sort_keys=True))
    want = {json.dumps(dict(json.loads(next(iter(rules))), respond=True), sort_keys=True)} if rules else set()
    if len(rules) != 1 or rules != want:
        out.append("U の 6 系の世界の規則が同じ閉ループの規則ではない")


def _o10(run, out) -> None:
    """恒等（SE-3・SE-4）。"""
    u = run["U"]
    pairs = [("M", "M_WM")]
    if run["boundary"]["W_M"] == run["W_0"]:
        pairs += [("M", "M_W0"), ("Y", "Y_WM")]
    for a, b in pairs:
        for key in ("activity", "intents", "sensory", "sigma_end_sha256"):
            if u[a][key] != u[b][key]:
                out.append(f"{b} が U で {a} と違う（{key}）")
                break


def _o11(run, out) -> None:
    """T の計算：U の意図を、源の発火から計算し直し、世界の意図の記録と照らす。"""
    src, p_e = run["roles"]["source"], run["plan"]["p_e"]
    for name in M.U_SYSTEMS:
        u = run["U"][name]
        fires = sorted(p for p, x in u["activity"] if x == src)
        recorded = [p for p, _ in u["intents"]]
        world = [p for p, _ in u["world_end"]["intents"] if p > p_e]
        if not (fires == recorded == world):
            out.append(f"{name}：源の発火から計算した U の意図が、記録・世界の意図の記録と違う")


def _o12(seed, mode, out) -> None:
    if seed not in expected_seeds(mode):
        out.append(f"seed {seed} は {mode} の範囲の外")
    if seed in ALIGN.SEEN:
        out.append(f"seed {seed} はこれまでに走らせた seed と重なる（D5）")


def _o13(run, out) -> None:
    """記録の非干渉：M′ の E が M と同じ。"""
    r, m = run["E"]["M_rerun"], run["M_E"]
    if (r["activity"], r["intents"], r["sensory"]) != (m["activity"], m["intents"], m["sensory"]):
        out.append("M′ の E の発火・意図・感覚が M と違う")
    if r["sigma_p_e_sha256"] != M.sigma_sha256(run["boundary"]["sigma_a"]["M"]):
        out.append("M′ の P_E の Σ が M と違う")


def _o14(run, out) -> None:
    """F1：組の和。"""
    sa = run["boundary"]["sigma_a"]
    sums = {n: pair_sums(_weights_of(sa[n])) for n in ("M", "M_W0", "M_WM", "Y_WM")}
    if len(sums["M"]) != 3 or any(abs(s - W_MAX) > F1_TOLERANCE for s in sums["M"].values()):
        out.append("M の P_E の組の和が w_max から離れている")
    if any(s != 2 * W0 for s in sums["M_W0"].values()):
        out.append("M[W_0] の組の和が 2 w0 ではない")
    if sums["M_WM"] != sums["M"] or sums["Y_WM"] != sums["M"]:
        out.append("M[W_M]・Y[W_M] の組の和が M と違う")


def _o15(run, out) -> None:
    """Pulse P_E ＋ 1 の一致（SE-6）。保存した Pulse P_E ＋ 1 の処理の後の Σ から照合する。"""
    p_e, end = run["plan"]["p_e"], run["plan"]["p_e"] + run["plan"]["u_length"]
    first = p_e + 1
    for a, b in M.HORIZONTAL:
        ua, ub = run["U"][a], run["U"][b]
        fa = sorted(u for p, u in ua["activity"] if p == first)
        fb = sorted(u for p, u in ub["activity"] if p == first)
        if fa != fb or [p for p, _ in ua["intents"] if p == first] != [p for p, _ in ub["intents"] if p == first]:
            out.append(f"(a) {a} と {b} の Pulse P_E ＋ 1 の発火・意図が違う")
        sa, sb = ua["sigma_after_first"], ub["sigma_after_first"]
        if sa["pulse"] != first or sb["pulse"] != first:
            out.append(f"(a) {a}・{b} の保存した Σ が Pulse P_E ＋ 1 の処理の後ではない")
        if sa["units"] != sb["units"]:
            out.append(f"(a) {a} と {b} の Pulse P_E ＋ 1 の Unit の内部の状態が違う")
        wa, wb = _weights_of(run["boundary"]["sigma_b"][a]), _weights_of(run["boundary"]["sigma_b"][b])
        da, db = sa["drives"], sb["drives"]
        if len(da) != len(db):
            out.append(f"(b) {a} と {b} の届く途中の駆動の数が違う")
        else:
            for x, y in zip(da, db):
                if x[0] != y[0] or x[1] != y[1] or x[3] != y[3]:
                    out.append(f"(b) {a} と {b} の届く途中の駆動の送り手・受け手・Pulse が違う")
                    break
                if x[2] != y[2]:
                    cid = f"{x[0]}.main->{x[1]}"
                    if not (cid in wa and wa[cid] != wb[cid] and x[0] in fa and x[3] == first
                            and x[2] == wa[cid] and y[2] == wb[cid]):
                        out.append(f"(b) {a} と {b} の駆動が、重みの差のある接続の送り手の発火の分の外で違う")
                        break
        for key, fd in (("firing", first_divergence(ua["activity"], ub["activity"], first, end)),
                        ("intent", first_intent_divergence([p for p, _ in ua["intents"]], [p for p, _ in ub["intents"]],
                                                           first, end))):
            if fd is not None and fd < p_e + 2:
                out.append(f"(c) {a} と {b} の最初に分かれた Pulse（{key}）が P_E ＋ 2 より前")


# ---- 記録の確認・前提・report（0036 と同じ） ----------------------------------------------------------

def verify_records(out: Path, mode: str, seeds: list[int]) -> dict:
    found = G.scan(out)
    problems = list(found["anomalies"])
    statuses = {s: st for s, (st, _) in found["seeds"].items()}
    for s, (st, why) in found["seeds"].items():
        if s not in seeds:
            problems.append(f"範囲の外・余分な seed {s}（{st}）がある")
        if st in ("failed", "started", "broken"):
            problems.append(f"seed {s} が {st}" + (f"（{'; '.join(why)}）" if why else ""))
    missing = [s for s in seeds if statuses.get(s, "absent") == "absent"]
    commits, shas = set(), set()
    for s in sorted(statuses):
        try:
            st = G.read_seed(out, s)["start"]
        except (OSError, ValueError):
            st = None
        if isinstance(st, dict):
            commits.add(st.get("measurement_commit"))
            shas.add(st.get("protocol_sha256"))
    for s in seeds:
        if statuses.get(s) != "completed":
            continue
        r = G.read_seed(out, s)
        st, fin = r["start"], r["finish"]
        if any(x.get(k) != v for x in (st, fin) for k, v in (("experiment", EXPERIMENT), ("kind", KIND), ("mode", mode))):
            problems.append(f"seed {s} の開始・終了の記録の experiment・kind・mode が {EXPERIMENT}・{KIND}・{mode} ではない")
        if not G.SHA_RE.match(str(st.get("measurement_commit"))) or fin.get("measurement_commit_end") != st.get("measurement_commit"):
            problems.append(f"seed {s} の測定の commit が 40 桁でないか、開始と終了で違う")
    if len(commits) > 1:
        problems.append(f"seed によって測定の commit が違う（{sorted(map(str, commits))}）")
    if shas and shas != {G.sha256_file(REPO / PROTOCOL_PATH)}:
        problems.append("開始の記録の protocol.yaml の SHA-256 が今のものと違う")
    state = "failed" if problems else ("incomplete" if missing else "complete")
    commit = next(iter(commits)) if len(commits) == 1 else None
    return {"state": state, "problems": problems, "missing": missing,
            "measurement_commit": commit if G.SHA_RE.match(str(commit)) else None}


def check_blinded(data: Mapping, seed: int, mode: str = "smoke") -> dict[str, str]:
    """smoke の盲検の記録の確かめ（0036 と同じ）。O12（seed の範囲）は記録に頼らずここで確かめ直す。"""
    status = {k: "fail" for k in CHECK_NAMES}
    try:
        meta, blind = data["meta"], data["blind"]
        ok_shape = (set(data) == {"meta", "blind"} and set(blind) == BLIND_KEYS
                    and set(blind["checks"]) == set(CHECK_NAMES)
                    and all(v in ("ok", "fail") for v in blind["checks"].values())
                    and bool(SHA256_RE.match(str(blind["raw_sha256"])))
                    and all(meta.get(k) == v for k, v in (("experiment", EXPERIMENT), ("kind", KIND), ("mode", mode),
                                                          ("seed", seed)))
                    and meta.get("blind") is True
                    and meta.get("manifest") == M.manifest_raw())
    except (KeyError, TypeError, AttributeError):
        ok_shape = False
    if not ok_shape:
        return status
    status = dict(blind["checks"])
    o12: list[str] = []
    _o12(seed, mode, o12)
    if o12:
        status["O12"] = "fail"
    return status


def o1_check(out: Path, commit: str | None, repo: Path | None = None) -> list[str]:
    """O1 の証拠（0036 と同じ）。テストのファイルの SHA-256 は repo（省略したときは呼んだ時点の REPO）のものと比べる。"""
    repo = REPO if repo is None else repo
    path = out / O1_FILE
    if not path.exists():
        return [f"{O1_FILE} がない（測定の commit で契約テストを走らせた記録がない）"]
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [f"{O1_FILE} を読めない（{e!r}）"]
    problems = []
    if not isinstance(rec, dict) or set(rec) != O1_KEYS:
        return [f"{O1_FILE} の欄が違う"]
    if rec["measurement_commit"] != commit:
        problems.append("契約テストを走らせた commit が測定の commit と違う")
    if rec["exit_code"] != 0:
        problems.append(f"契約テストの終了コードが {rec['exit_code']}")
    summary = str(rec["summary"])
    if " passed" not in summary or any(w in summary for w in (" failed", " error")):
        problems.append(f"契約テストの結果の行が、すべて通ったことを示していない（{summary}）")
    if list(rec["command"])[-len(CONTRACT_TESTS):] != list(CONTRACT_TESTS):
        problems.append("走らせた契約テストの組が違う")
    files = rec["test_files_sha256"]
    if not isinstance(files, dict) or set(files) != set(CONTRACT_TESTS):
        problems.append("テストのファイルの SHA-256 の組が違う")
    else:
        for f, sha in files.items():
            if sha != G.sha256_file(repo / f):
                problems.append(f"{f} の SHA-256 が、測定の commit のものと違う")
    return problems


def analyze_runs(runs: Mapping[int, dict], mode: str, plan: "M.Plan | None" = None, *, o1: list[str]) -> dict:
    """記録（seed → 本番・合成なら生の記録、smoke なら盲検の記録）と O1 の確かめの結果から、report の中身を作る。"""
    o1_status = "fail" if o1 else "ok"
    if mode == "smoke":
        checks = {str(s): check_blinded(data, s) for s, data in sorted(runs.items())}
        return {"mode": "smoke", "O1": o1_status, "checks": checks,
                "valid": not o1 and all(v == "ok" for c in checks.values() for v in c.values())}
    checks = {s: check_seed(data, mode, s, plan) for s, data in sorted(runs.items())}
    failed = {s: {k: v for k, v in c.items() if v} for s, c in checks.items() if any(c.values())}
    if failed or o1:
        return {"mode": mode, "valid": False, "O1": {"status": o1_status, "problems": o1},
                "failed_checks": {str(s): v for s, v in failed.items()}, "judgment": None}
    individuals = {str(s): individual(data["run"]) for s, data in sorted(runs.items())}
    j = judge(individuals)
    return {"mode": mode, "valid": True, "O1": {"status": o1_status, "problems": o1},
            "judgment": {"J_C": j["J_C"]}, "interval": j["interval"],
            "descriptive_controls": descriptive_controls(individuals),
            "individuals": individuals, "auxiliary": auxiliary(individuals)}


def verify_results_copy(src: Path, dst: Path) -> list[str]:
    """出力先 src と写し dst の照合（0036 と同じ）。鍵のファイル（run.lock）は写さない。"""
    def files(root: Path) -> dict[str, str]:
        return {str(p.relative_to(root)): G.sha256_file(p) for p in sorted(root.rglob("*"))
                if p.is_file() and p.name != G.LOCK}
    problems = []
    a, b = files(src), files(dst)
    if set(a) != set(b):
        problems.append(f"ファイルの組が違う（元だけ：{sorted(set(a) - set(b))}、写しだけ：{sorted(set(b) - set(a))}）")
    problems += [f"{f} の SHA-256 が元と違う" for f in sorted(set(a) & set(b)) if a[f] != b[f]]
    found = G.scan(dst)
    problems += found["anomalies"]
    commits = set()
    for s, (st, _) in sorted(found["seeds"].items()):
        rec = G.read_seed(dst, s)
        if st != "completed":
            problems.append(f"写しの seed {s} が {st}")
            continue
        commits.add(rec["start"].get("measurement_commit"))
        if G.sha256_file(G.seed_dir(dst, s) / G.RAW) != rec["finish"].get("raw_file_sha256"):
            problems.append(f"写しの seed {s} の raw が終了の記録の SHA-256 と違う")
    if (dst / REPORT).exists():
        rep = json.loads((dst / REPORT).read_text(encoding="utf-8"))
        if commits != {rep.get("measurement_commit")}:
            problems.append("report の測定の commit が、記録の測定の commit と違う")
    else:
        problems.append("写しに report がない")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", nargs="?", type=Path, default=None)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--verify-copy", type=Path, default=None, help="本番の出力先とその写し（results/）を照合するだけ")
    args = parser.parse_args()
    if args.verify_copy is not None:
        problems = verify_results_copy(REPO / OUT_DIR, args.verify_copy)
        if problems:
            raise SystemExit("写しが元と違う：\n- " + "\n- ".join(problems))
        print(f"写しは元と同じ：{args.verify_copy}")
        return
    ALIGN.check(PROTOCOL)
    mode = "smoke" if args.smoke else "formal"
    out = (args.out if args.smoke else REPO / OUT_DIR)
    if args.smoke and args.out is None:
        raise SystemExit("--smoke のときは作業用のフォルダを指定する")
    if not args.smoke and args.out is not None:
        raise SystemExit(f"本番の出力先は {OUT_DIR} に固定")
    seeds = expected_seeds(mode)
    records = verify_records(out, mode, seeds)
    if records["state"] == "incomplete":
        raise SystemExit(f"未完了（まだ始めていない seed：{records['missing']}）。集計しない")
    if records["measurement_commit"] is None:
        raise SystemExit("測定の commit が 1 つに定まらない。解析しない")
    G.verify_clean_commit(REPO, records["measurement_commit"])
    if (out / REPORT).exists():
        raise SystemExit("report は既にある（上書きしない）")
    shas = {}
    runs = {}
    if records["state"] == "complete":
        for s in seeds:
            raw = G.seed_dir(out, s) / G.RAW
            shas[str(s)] = G.sha256_file(raw)
            runs[s] = read_raw(raw)
    with open(out / LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"event": "start", "at": G.now_iso(), "inputs": shas}) + "\n")
    o1 = o1_check(out, records["measurement_commit"])
    if records["state"] == "failed":
        report = {"mode": mode, "valid": False, "record_problems": records["problems"],
                  "O1": ("fail" if o1 else "ok") if mode == "smoke" else {"status": "fail" if o1 else "ok", "problems": o1},
                  "judgment": None}
    else:
        report = analyze_runs(runs, mode, o1=o1)
    G.verify_clean_commit(REPO, records["measurement_commit"])
    report["measurement_commit"] = records["measurement_commit"]
    G.write_once(out / REPORT, json.dumps(report, ensure_ascii=False, indent=1).encode("utf-8"))
    with open(out / LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"event": "complete", "at": G.now_iso(), "inputs": shas}) + "\n")
    print(f"report: {out / REPORT}")


if __name__ == "__main__":
    main()
