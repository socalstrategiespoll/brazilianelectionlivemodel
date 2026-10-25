# Offline checks: (1) parser matches every civicAPI state row, (2) replay where Flavio-leaning states and precincts report first.
import json, numpy as np, engine_br as E, civicapi_feed as C
race = json.load(open("data.json", encoding="utf-8"))["races"][0]; P = E.prep(race)
names = [c[1] for c in race["counties"]]
def payload(rows):   # rows: name -> (flavio, lula, pct)
    return {"candidates": [], "region_results": {n.lower(): {"name": n, "type": "Abroad" if n == "Abroad" else "State", "percent_reporting": 100 * v[2],
            "candidates": [{"name": "Flavio Nantes Bolsonaro", "party": "PL", "votes": v[0]}, {"name": "Luiz Inácio Lula da Silva", "party": "PT", "votes": v[1]}]}
            for n, v in rows.items()}}
got = C.parse_counties(payload({n: (100, 90, 0.5) for n in names}), race)
print("parser matched", len(got), "of", len(names)); assert len(got) == len(names)
import sys
SHARED = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
rng = np.random.default_rng(3)
NE = {"BR_AL","BR_BA","BR_CE","BR_MA","BR_PB","BR_PE","BR_PI","BR_RN","BR_SE","BR_AM","BR_PA","BR_AP"}
res = []
for trial in range(60):
    s = rng.normal(0, 4); U = np.linalg.cholesky(P["K"] + 1e-8*np.eye(len(P["T"]))) @ rng.normal(0, 1, len(P["T"]))
    m_true = np.clip(P["b"] + s + U, -99, 99); T = P["T"] * np.exp(rng.normal(0, .03, len(P["T"])))
    final = (T * m_true).sum() / T.sum()
    lag = np.array([0.25 if f in NE else 0.0 for f in P["fips"]]) + rng.uniform(0, .15, len(T))
    sb = rng.normal(0, SHARED); st = rng.normal(0, 4, len(T))
    row = []
    for t in (0.15, 0.3, 0.5, 0.7, 0.9):
        pct = np.clip((t - lag) / 0.6, 0, 1)
        bias = (sb + st) * (1 - pct)  # early precincts lean one way: shared part sb plus a per-state part st, fading to zero at 100%
        cm = np.clip(m_true + bias, -99, 99); n = T * pct
        rows = {names[i]: (n[i] * (1 + cm[i]/100) / 2, n[i] * (1 - cm[i]/100) / 2, pct[i]) for i in range(len(T)) if pct[i] > 0}
        cnt = C.parse_counties(payload(rows), race)
        o = E.project(P, cnt, n_sims=1500, seed=trial)
        raw = 100 * sum(v[0]-v[1] for v in rows.values()) / max(sum(v[0]+v[1] for v in rows.values()), 1)
        row.append((o["reporting"], raw - final, o["margin"] - final, o["p05"] <= final <= o["p95"], (o["win_prob_R"] - (final > 0))**2))
    res.append(row)
a = np.array(res, float)
print("stage  reporting  raw-count err  model err  |model err|  in 90%  Brier")
for k in range(a.shape[1]):
    print(f"{k}     {a[:,k,0].mean():.2f}       {a[:,k,1].mean():+5.2f}        {a[:,k,2].mean():+5.2f}     {np.abs(a[:,k,2]).mean():.2f}       {a[:,k,3].mean():.2f}   {a[:,k,4].mean():.3f}")
