"""0012 の事後の解析：なぜ重み（ConnectionState）までは届いて、活動（H1）までは届かなかったか。

範囲外の seed（1001〜1020、generate.py）のデータだけを使う。判定の seed 1〜20 は使わない。
使い方（リポジトリ直下で）: python experiments/0012_passive_world/post/why.py <generate.py の出力フォルダ> [parts]
"""

import gzip
import importlib.util
import itertools
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from replay import replay  # noqa: E402

from anima_ll.adapter.config.yaml_config_source import parse_neuroarchitecture  # noqa: E402

EXP = Path("experiments/0012_passive_world")
PROTOCOL = yaml.safe_load((EXP / "protocol.yaml").read_text(encoding="utf-8"))
SPEC = parse_neuroarchitecture(yaml.safe_load((EXP / "neuroarchitecture.yaml").read_text(encoding="utf-8"))).plasticity
W0 = SPEC.w_max / 2
UNITS = ("s1", "s2", "s3")
END = PROTOCOL["timeline"]["total_pulses"]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A = load("analyze_0012", EXP / "analyze.py")
W = A.W


def spikes(run: dict) -> dict[str, list[int]]:
    out = {u: [] for u in UNITS}
    for p, u in run["activity"]:
        out[u].append(p)
    return out


def rp(pre, post, classify=None, end=END):
    return replay(pre, post, w0=W0, w_max=SPEC.w_max, amplitude=SPEC.amplitude,
                  tau=SPEC.trace_tau_seconds, dt=PROTOCOL["timeline"]["pulse_interval_seconds"],
                  end=end, classify=classify)


# ---- 0. 範囲外でも同じ傾向か ----------------------------------------------------------

def replication(runs: list[dict]) -> dict:
    d, w = defaultdict(dict), defaultdict(dict)
    for r in runs:
        d[r["seed"]][r["condition"]] = A.d_value(r)
        w[r["seed"]][r["condition"]] = A.w_value(r)
    h1, _ = A.count_all_three(d)
    m, _ = A.count_all_three(w)
    return {"h1_like": h1, "m_like": m, "n": len(d),
            "W_ordered_positive": sum(v["ordered"] > 0 for v in w.values()),
            "D_sd": {c: st.pstdev(v[c] for v in d.values()) for c in ("ordered", "shuffled", "silent")},
            "W_mean": {c: st.fmean(v[c] for v in w.values()) for c in ("ordered", "shuffled", "silent")},
            "W_sd": {c: st.pstdev(v[c] for v in w.values()) for c in ("ordered", "shuffled", "silent")}}


# ---- C. A→B・A→C の変化の内訳（順序あり） ------------------------------------------------

def trial_classifier(run: dict):
    """経験の各試行（A を t、B・C を t＋2）を基準に、組を分類する。"""
    starts = set(W.trial_starts(PROTOCOL))
    label_at = {t: lab for t, lab in run["stimuli"]}
    exp_lo, exp_hi = PROTOCOL["timeline"]["trials"]["first"], PROTOCOL["timeline"]["post_probes"]["first"] - 1

    def classify(kind: str, p: int, pk: int) -> str:
        if not exp_lo <= min(p, pk) and max(p, pk) <= exp_hi:
            return f"{kind}:経験の外"
        if kind == "pot":   # S（s_A）が pk、T が p
            t = pk - 1
            if t in starts:
                follow = label_at.get(t + 2)
                if p == t + 2:
                    return "pot:試行内 d=1（s_A の駆動で t＋2 に発火）"
                if p == t + 3:
                    return f"pot:試行内 d=2（{follow} の刺激の試行で t＋3 に発火）"
                return "pot:試行の s_A とのそのほかの組"
            return "pot:経験中のそのほか（自発どうし）"
        t_dep = p - 1       # S（s_A）が p に発火：試行の s_A なら p ＝ t＋1
        if t_dep in starts:
            return "dep:試行の s_A の発火（受け手が先に発火していた）"
        return "dep:経験中のそのほか（自発どうし）"
    return classify


def a_to_bc_parts(runs: list[dict]) -> dict:
    out = {}
    for target in ("B", "C"):
        totals = defaultdict(list)
        for r in runs:
            if r["condition"] != "ordered":
                continue
            u = r["role_units"]
            sp = spikes(r)
            _, parts = rp(sp[u["A"]], sp[u[target]], classify=trial_classifier(r), end=W.probe_times(PROTOCOL, "post")[0] - 1)
            for k in set(parts) | set(totals):
                totals[k].append(parts.get(k, 0.0))
        out[f"A->{target}"] = {k: st.fmean(v) for k, v in sorted(totals.items())}
    return out


def trial_firing_counts(runs: list[dict]) -> dict:
    """順序ありの各試行で、s_B・s_C が t＋2（s_A の駆動）と t＋3（感覚）に発火した割合。"""
    c = defaultdict(int)
    n = defaultdict(int)
    for r in runs:
        if r["condition"] != "ordered":
            continue
        u = r["role_units"]
        fired = defaultdict(set)
        for p, x in r["activity"]:
            fired[p].add(x)
        label_at = {t: lab for t, lab in r["stimuli"]}
        for t in W.trial_starts(PROTOCOL):
            lab = label_at[t + 2]
            n[lab] += 1
            for role in ("B", "C"):
                c[(lab, role, 2)] += u[role] in fired.get(t + 2, ())
                c[(lab, role, 3)] += u[role] in fired.get(t + 3, ())
    return {f"{lab} の試行: s_{role} が t＋{k}": c[(lab, role, k)] / n[lab] for (lab, role, k) in sorted(c)}


# ---- B. 刺激なしでの重みのドリフト ----------------------------------------------------------

def silent_drift(runs: list[dict]) -> dict:
    """刺激なしで、各接続 S→T の重みの変化と、「S の 1 Pulse 後に T が発火した」回数の偏りの関係。"""
    rows = []
    for r in runs:
        if r["condition"] != "silent":
            continue
        sp = spikes(r)
        sets = {u: set(v) for u, v in sp.items()}
        end = W.probe_times(PROTOCOL, "post")[0] - 1
        for a, b in itertools.permutations(UNITS, 2):
            dw = r["weights_after_experience"][f"{a}.main->{b}"] - W0
            follow_ab = sum(1 for p in sets[a] if p + 1 in sets[b] and p + 1 <= end)
            follow_ba = sum(1 for p in sets[b] if p + 1 in sets[a] and p + 1 <= end)
            _, parts = rp(sp[a], sp[b], end=end)
            d1 = sum(v for k, v in parts.items() if k in ("pot d=1", "dep d=1"))
            rows.append({"seed": r["seed"], "conn": f"{a}->{b}", "dw": dw,
                         "net_follow": follow_ab - follow_ba, "d1_part": d1,
                         "rate_diff": (len(sp[a]) - len(sp[b])) / end})
    def corr(x, y):
        return st.correlation(x, y) if len(set(x)) > 1 and len(set(y)) > 1 else None
    dws = [r["dw"] for r in rows]
    return {
        "n_connections": len(rows),
        "sd_dw": st.pstdev(dws),
        "share_of_dw_from_d1_pairs": sum(abs(r["d1_part"]) for r in rows) / sum(abs(r["dw"]) for r in rows),
        "corr_dw_vs_d1_part": corr(dws, [r["d1_part"] for r in rows]),
        "corr_dw_vs_net_follow": corr(dws, [r["net_follow"] for r in rows]),
        "corr_dw_vs_rate_diff": corr(dws, [r["rate_diff"] for r in rows]),
    }


def main() -> None:
    folder = Path(sys.argv[1])
    data = json.load(gzip.open(folder / "post_runs.json.gz", "rt"))
    runs = data["runs"]
    parts = sys.argv[2].split(",") if len(sys.argv) > 2 else ["rep", "C", "B"]
    report = {"git_commit": data["meta"]["git_commit"], "seeds": data["meta"]["seeds"]}
    if "rep" in parts:
        report["replication"] = replication(runs)
    if "C" in parts:
        report["C_a_to_bc_parts"] = a_to_bc_parts(runs)
        report["C_trial_firing"] = trial_firing_counts(runs)
    if "B" in parts:
        report["B_silent_drift"] = silent_drift(runs)
    print(json.dumps(report, ensure_ascii=False, indent=1))
    (folder / f"why_{'_'.join(parts)}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
