"""Runoff baseline from first-round state results (civicAPI race 130870).
Flavio + Lula keep their first-round votes; each other candidate's voters split by a prior share to Flavio,
then the right-bloc priors move together on the logit scale until the national two-way result is TARGET.
Left minors (UP, PSTU, PCB, PCO) stay fixed at LEFT_TO_FLAVIO."""
import json, numpy as np, sys
TARGET = float(sys.argv[1]) if len(sys.argv) > 1 else 51.0          # Flavio share of the two-way vote, national
# column order after Flavio, Lula: Cury, Renan, Caiado, Zema, Samara, Hertz, Clariana, Edmilson, Wilson, Rui
PRIOR = np.array([0.65, 0.80, 0.80, 0.85, 0, 0, 0.75, 0, 0.70, 0])
RIGHT = np.array([1, 1, 1, 1, 0, 0, 1, 0, 1, 0], bool)
LEFT_TO_FLAVIO = 0.10
IDS = {"acre":"AC","alagoas":"AL","amapá":"AP","amazonas":"AM","bahia":"BA","ceará":"CE","distrito_federal":"DF","espírito_santo":"ES",
       "goiás":"GO","maranhão":"MA","mato_grosso":"MT","mato_grosso_do_sul":"MS","minas_gerais":"MG","paraná":"PR","paraíba":"PB",
       "pará":"PA","pernambuco":"PE","piauí":"PI","rio_de_janeiro":"RJ","rio_grande_do_norte":"RN","rio_grande_do_sul":"RS",
       "rondônia":"RO","roraima":"RR","santa_catarina":"SC","sergipe":"SE","são_paulo":"SP","tocantins":"TO","abroad":"ZZ"}
rows = [l.split("\t") for l in open("r1.tsv", encoding="utf-8").read().strip().split("\n")]
V = np.array([[int(x) for x in l[2:]] for l in rows], float)
F0, L0, O = V[:, 0], V[:, 1], V[:, 2:]
lg = lambda p: np.log(p / (1 - p)); il = lambda x: 1 / (1 + np.exp(-x))
def alloc(d):
    s = np.where(RIGHT, il(lg(np.clip(PRIOR, .01, .99)) + d), LEFT_TO_FLAVIO)
    F = F0 + O @ s; L = L0 + O @ (1 - s)
    return F, L, s
lo, hi = -6.0, 6.0
for _ in range(60):
    mid = (lo + hi) / 2; F, L, _ = alloc(mid)
    lo, hi = (mid, hi) if 100 * F.sum() / (F.sum() + L.sum()) < TARGET else (lo, mid)
F, L, s = alloc((lo + hi) / 2)
races = [{
    "id": "BR2026PRES2", "label": "BR-Pres", "state": "BR", "type": "President",
    "rep": "Flávio Bolsonaro", "other": "Luiz Inácio Lula da Silva", "name_match": True,
    "method": f"First-round state results (civicAPI 130870) with other candidates' votes allocated to reach Flavio {TARGET:.0f} / Lula {100-TARGET:.0f}. Shares to Flavio: "
              + ", ".join(f"{n} {x:.0%}" for n, x in zip(["Cury","Renan","Caiado","Zema","Samara","Hertz","Clariana","Edmilson","Wilson","Rui"], s)),
    "alloc": {"cury": round(float(s[0]), 4), "renan": round(float(s[1]), 4), "caiado": round(float(s[2]), 4), "zema": round(float(s[3]), 4),
              "oright": round(float((s[6] * O[:, 6].sum() + s[8] * O[:, 8].sum()) / (O[:, 6].sum() + O[:, 8].sum())), 4), "left": LEFT_TO_FLAVIO},
    "headline": round(2 * TARGET - 100, 2), "margin": round(2 * TARGET - 100, 2),
    "counties": [["BR_" + IDS[l[0]], l[1], int(round(L[i])), int(round(F[i]))] for i, l in enumerate(rows)],
}]
json.dump({"races": races}, open("data.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(races[0]["method"])
print(f"national Flavio {100*F.sum()/(F.sum()+L.sum()):.2f}%  total two-way {F.sum()+L.sum():,.0f}")
for i, l in enumerate(rows):
    m1 = 100 * (F0[i] - L0[i]) / (F0[i] + L0[i]); m2 = 100 * (F[i] - L[i]) / (F[i] + L[i])
    print(f"{l[1]:22s} R1 two-way {m1:+6.1f}  runoff base {m2:+6.1f}")
