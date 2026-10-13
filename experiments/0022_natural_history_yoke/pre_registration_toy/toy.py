"""0022 案の §3.2・§3.3 の主張の確かめ（玩具の 3 Unit。seed・runtime・実験の記録は使わない。乱数なし）。
runtime の順序：Pulse t の冒頭で w(t−1) を固定 → Unit（t に届く駆動）→ 発火 → t+1 へ届く駆動を w(t−1) と s(t) で作る → 終わりに可塑性。
自然な 2 個体 O・S を、同じ出生から違う入力の列（ordered と、固定の並べ替え）で進め、t0 で複製を作る。"""
import math, itertools
LAM, ALPHA, TAU, A, WMAX = 0.85, 0.01, 300.0, 0.01, 0.01
GAM, KAP = math.exp(-1/TAU), 0.85
N = 3
def new(theta, c):
    return {"a": [0.0]*N, "h": [0.0]*N, "d": [0.0]*N, "X": [0.0]*N,
            "w": [[0.0 if i == j else WMAX/2 for j in range(N)] for i in range(N)], "theta": theta, "c": c}
def copy(s):
    return {"a": s["a"][:], "h": s["h"][:], "d": s["d"][:], "X": s["X"][:], "w": [r[:] for r in s["w"]],
            "theta": s["theta"], "c": s["c"]}
def units(s, u):
    fired, pre = [], []
    for j in range(N):
        at = LAM*s["a"][j] + s["d"][j] + u[j] + s["c"][j]
        ht = GAM*s["h"][j]
        f = at >= s["theta"][j] + ht
        pre.append(at)
        s["a"][j] = 0.0 if f else at
        s["h"][j] = ht + (ALPHA if f else 0.0)
        fired.append(1 if f else 0)
    return fired, pre
def drive(s, fired):   # w(t−1)（まだ更新前）と s(t) から、t+1 に届く駆動
    s["d"] = [sum(s["w"][i][j]*fired[i] for i in range(N) if i != j) for j in range(N)]
def plast(s, p):
    X = s["X"]
    for i in range(N):
        for j in range(N):
            if i == j: continue
            sig = 1 - A*(X[i]*p[j] + X[j]*p[i])
            beta = A*X[i]*p[j]*WMAX
            s["w"][i][j] = sig*s["w"][i][j] + beta
    s["X"] = [KAP*X[u] + p[u] for u in range(N)]
def pulse(s, u, plast_input=None):
    fired, pre = units(s, u)
    drive(s, fired)
    plast(s, fired if plast_input is None else plast_input)
    return fired, pre

def run_case(theta, c, perm, t0=1200, T=2400, every=60):
    O, S = new(theta, c), new(theta, c)
    for t in range(1, t0+1):
        k = (t-1) % every
        uo = [0.0]*N; us = [0.0]*N
        trial = (t-1)//every
        for idx, off in enumerate((0, 2, 30)):
            if k == off:
                uo[idx] = 1.0
                us[perm[(trial + idx) % 3]] = 1.0   # 固定の並べ替え（乱数なし）
        pulse(O, uo); pulse(S, us)
    arms = {"O": O, "S": S, "YOS": copy(O), "YSO": copy(S), "YOO": copy(O)}
    tr = {k: [] for k in arms}; st = {k: [] for k in arms}; pre = {k: [] for k in arms}; wh = {k: [] for k in arms}
    zero = [0.0]*N
    for t in range(t0+1, T+1):
        fo, po = pulse(arms["O"], zero); fs, ps = pulse(arms["S"], zero)
        fy, py = pulse(arms["YOS"], zero, fs); fz, pz = pulse(arms["YSO"], zero, fo); fq, pq = pulse(arms["YOO"], zero, fo)
        for k, f, p in (("O", fo, po), ("S", fs, ps), ("YOS", fy, py), ("YSO", fz, pz), ("YOO", fq, pq)):
            tr[k].append(f); pre[k].append(p)
            st[k].append((tuple(arms[k]["a"]), tuple(arms[k]["h"])))
            wh[k].append([r[:] for r in arms[k]["w"]])
    def first(x, y):
        for n, (p, q) in enumerate(zip(tr[x], tr[y])):
            if p != q: return n
        return None
    tOS, tYO, tYS = first("O", "S"), first("O", "YOS"), first("S", "YSO")
    out = {"tOS": tOS, "tYO": tYO, "tYS": tYS, "viol": []}
    if tr["YOO"] != tr["O"] or st["YOO"] != st["O"] or wh["YOO"] != wh["O"]: out["viol"].append("self-yoke")
    for base, y, tY in (("O", "YOS", tYO), ("S", "YSO", tYS)):
        lim = len(tr[base]) - 1 if tOS is None else tOS + 1
        if tr[base][:lim+1] != tr[y][:lim+1]: out["viol"].append(f"spikes {y}")
        if st[base][:lim+1] != st[y][:lim+1]: out["viol"].append(f"units {y}")
        wl = len(wh[base]) if tOS is None else tOS   # 接続は tOS − 1 まで（index tOS−1 まで）
        if wh[base][:wl] != wh[y][:wl]: out["viol"].append(f"weights {y}")
        if tY is not None and (tOS is None or tY < tOS + 2): out["viol"].append(f"bound {y}")
        if tY is not None:   # 分解の恒等式（index で書く：Pulse t0+1+n）
            common = tr[base]
            for j in range(N):
                r = -1
                for n in range(tY):
                    if common[n][j]: r = n
                K = 0.0
                for k in range(max(r+1, tOS+2), tY+1):
                    for i in range(N):
                        if i == j: continue
                        dw = wh[base][k-2][i][j] - wh[y][k-2][i][j]
                        K += LAM**(tY-k) * dw * common[k-1][i]
                if abs(K - (pre[base][tY][j] - pre[y][tY][j])) > 1e-12: out["viol"].append(f"K {y} j{j}")
    return out

res = []
perms = [(1, 2, 0), (2, 0, 1), (0, 2, 1)]
for th in itertools.product((0.45, 0.5, 0.55), repeat=1):
    for c in (0.072, 0.08, 0.088):
        for perm in perms:
            for shift in ((0, 0, 0), (0.02, -0.03, 0.01), (-0.04, 0.0, 0.03)):
                theta = [th[0] + s for s in shift]; cc = [c, c*1.05, c*0.95]
                res.append(((th[0], c, perm, shift), run_case(theta, cc, perm)))
viol = [r for r in res if r[1]["viol"]]
print("cases", len(res), "violations", len(viol))
cats = {}
for _, o in res:
    k = ("tOS" if o["tOS"] is not None else "-", "tYO" if o["tYO"] is not None else "-", "tYS" if o["tYS"] is not None else "-")
    cats[k] = cats.get(k, 0) + 1
print(cats)
for v in viol[:5]: print(v)
