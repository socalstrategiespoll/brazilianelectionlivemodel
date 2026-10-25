# End-to-end offline test of server_br.cycle with mocked civicAPI: municipalities that lean Flavio report first.
import json, numpy as np, server_br as S, muni, civicapi_feed as C, os
rng = np.random.default_rng(5)
race = json.load(open("data.json", encoding="utf-8"))["races"][0]; P = S.engine.prep(race)
UFS = [c[0][3:] for c in race["counties"] if c[0] != "BR_ZZ"]
# fake first round: 40 municipalities per state around the state's two-way margin
r1 = {}
for c in race["counties"]:
    uf = c[0][3:]
    if uf == "ZZ": continue
    m0 = 100 * (c[3] - c[2]) / (c[2] + c[3]); sz = rng.lognormal(0, 1.2, 40); sz *= (c[2] + c[3]) / sz.sum()
    mm = np.clip(m0 + rng.normal(0, 15, 40), -90, 90)
    r1[uf] = {f"{uf} place {i}": [int(sz[i] * (1 + mm[i] / 100) / 2), int(sz[i] * (1 - mm[i] / 100) / 2), 0, 0, 0, 0, 0, 0] for i in range(40)}
json.dump(r1, open("muni_r1.json", "w"))
S.BASE = muni.baseline(r1, race["alloc"], {c[0]: c for c in race["counties"]})
S.STATE_RACE = {uf: 162829 + i for i, uf in enumerate(UFS)}
ID2UF = {v: k for k, v in S.STATE_RACE.items()}
def make_truth(shift):
    t = {}
    for uf, b in S.BASE.items():
        for name, (L, F) in b.items():
            m = 100 * (F - L) / (F + L) + shift + rng.normal(0, 3)
            t[(uf, name)] = ((F + L), m)
    return t
def snapshot(truth, tt):
    st = {}; mu = {}
    for uf, b in S.BASE.items():
        names = list(b); bm = np.array([100 * (b[n][1] - b[n][0]) / sum(b[n]) for n in names])
        order = np.argsort(np.argsort(-bm)) / len(names)          # Flavio-leaning places first
        for k, n in enumerate(names):
            p = float(np.clip((tt - 0.6 * order[k]) / 0.4, 0, 1)); T, m = truth[(uf, n)]
            v = T * p; mu[(uf, n)] = (v * (1 + m / 100) / 2, v * (1 - m / 100) / 2, p)
        F = sum(mu[(uf, n)][0] for n in names); L = sum(mu[(uf, n)][1] for n in names)
        tot = sum(truth[(uf, n)][0] for n in names); st[uf] = (F, L, (F + L) / tot)
    return st, mu
def cand(F, L): return [{"name": "Flavio Nantes Bolsonaro", "votes": int(F)}, {"name": "Luiz Inácio Lula da Silva", "votes": int(L)}]
for shift in (-3.0, 2.0):
    truth = make_truth(shift)
    final = sum(T * m for T, m in truth.values()) / sum(T for T, m in truth.values())
    print(f"\ntrue final margin {final:+.2f}")
    print(" time  reporting  raw count  model    80% range         win_F")
    for tt in (0.15, 0.3, 0.5, 0.75, 0.95):
        st, mu = snapshot(truth, tt)
        def fake_state(rid):
            uf = ID2UF[rid]; F, L, p = st[uf]
            rr = {uf.lower(): {"name": uf, "type": "State", "percent_reporting": 100 * p, "candidates": cand(F, L)}}
            for n in S.BASE[uf]:
                a = mu[(uf, n)]; rr[n] = {"name": n, "type": "Municipality", "percent_reporting": 100 * a[2], "candidates": cand(a[0], a[1])}
            return {"province": "BR-" + uf, "region_results": rr}
        names = {c[0][3:]: c[1] for c in race["counties"]}
        nat = {"candidates": [], "region_results": {u: {"name": names[u], "type": "State", "percent_reporting": 100 * st[u][2], "candidates": cand(*st[u][:2])} for u in st}}
        muni.fetch = fake_state; C.fetch = lambda rid: nat; S.MEM.clear()
        S.cycle(race, P, None); pr = S.STATE["projection"]
        F = sum(v[0] for v in st.values()); L = sum(v[1] for v in st.values())
        d = S.STATE["detail"]
        print(f" {tt:.2f}   {pr['reporting']:.2f}      {100*(F-L)/(F+L):+6.2f}    {pr['margin']:+6.2f}  [{pr['p05']:+.1f}, {pr['p95']:+.1f}]  {pr['win_prob_flavio']:.3f}")
print("\nstatus sample:", list(S.STATE["muni_status"].items())[:2])
print("SP munis top 2:", S.STATE["munis"]["SP"][:2])
os.remove("muni_r1.json")
