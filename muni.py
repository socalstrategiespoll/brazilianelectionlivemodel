# Municipality layer for the Brazil runoff model.
# First round by state: civicAPI races 130982-131008. Runoff by state: 162829-162855. Both carry one "State" row and one
# "Municipality" row per municipality, keyed by name (no codes). Names were checked identical across rounds on Oct 25.
import json, os, time, urllib.request

R1_IDS = range(130982, 131009)
R2_IDS = range(162829, 162856)
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "muni_r1.json")
UA = {"User-Agent": "socal-strategies-model/1.0"}

def fetch(rid, timeout=20):
    with urllib.request.urlopen(urllib.request.Request(f"https://civicapi.org/api/v2/race/{rid}", headers=UA), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))

def _col(name):
    n = (name or "").lower()
    for k, c in (("bolsonaro", 0), ("lula", 1), ("cury", 2), ("renan", 3), ("caiado", 4), ("zema", 5), ("clariana", 6), ("wilson grassi", 6)):
        if k in n: return c
    return 7      # left minors (UP, PSTU, PCB, PCO) and anything unrecognised

def side(c):
    n = (c.get("name") or "").lower()
    return 0 if "bolsonaro" in n else (1 if "lula" in n else None)

def uf_of(payload):
    return (payload.get("province") or "").replace("BR-", "")

def load_r1(refresh=False, sleep=0.15):
    """{UF: {muni name: [F, L, cury, renan, caiado, zema, other right, left]}}, cached to muni_r1.json."""
    if not refresh and os.path.exists(CACHE):
        return json.load(open(CACHE, encoding="utf-8"))
    out = {}
    for rid in R1_IDS:
        d = fetch(rid); uf = uf_of(d); rows = {}
        for reg in (d.get("region_results") or {}).values():
            if reg.get("type") != "Municipality": continue
            v = [0] * 8
            for c in reg.get("candidates") or []: v[_col(c.get("name"))] += c.get("votes") or 0
            rows[reg["name"]] = v
        out[uf] = rows; time.sleep(sleep)
    json.dump(out, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    return out

def baseline(r1, alloc, state_rows):
    """Two-way runoff baseline per municipality: {UF: {name: (L, F)}}, scaled so each state's municipalities add up to the
    state row in data.json (keeps state and municipality baselines consistent)."""
    s = [1.0, 0.0, alloc["cury"], alloc["renan"], alloc["caiado"], alloc["zema"], alloc["oright"], alloc["left"]]
    out = {}
    for uf, rows in r1.items():
        b = {}
        for name, v in rows.items():
            F = v[0] + sum(x * w for x, w in zip(v[2:], s[2:]))
            L = v[1] + sum(x * (1 - w) for x, w in zip(v[2:], s[2:]))
            if F + L > 0: b[name] = [L, F]
        st = state_rows.get("BR_" + uf)
        if st and b:
            tL, tF = sum(x[0] for x in b.values()), sum(x[1] for x in b.values())
            kL, kF = st[2] / max(tL, 1), st[3] / max(tF, 1)
            b = {k: [x[0] * kL, x[1] * kF] for k, x in b.items()}
        out[uf] = b
    return out

def parse_state(payload, base_uf):
    """From one runoff state race: state totals (F, L, pct 0-1), and per-municipality counted (F, L, pct 0-1).
    Returns (state_tuple or None, munis dict, unmatched names)."""
    st = None; munis = {}; miss = []
    for reg in (payload.get("region_results") or {}).values():
        F = L = 0
        for c in reg.get("candidates") or []:
            sd = side(c)
            if sd == 0: F += c.get("votes") or 0
            elif sd == 1: L += c.get("votes") or 0
        pct = max(0.0, min(1.0, (reg.get("percent_reporting") or 0) / 100.0))
        if reg.get("type") == "State": st = (F, L, pct)
        elif reg.get("type") == "Municipality":
            if reg["name"] not in base_uf: miss.append(reg["name"]); continue
            if F + L > 0: munis[reg["name"]] = (F, L, pct)
    return st, munis, miss

def mix_adjusted(state_base_margin, munis, base_uf):
    """State counted margin corrected for which municipalities (and how much of each) are in:
    state baseline margin + vote-weighted swing of counted votes vs their own municipality's baseline.
    Returns (adjusted margin, raw counted margin, counted votes)."""
    num = n = rawm = 0.0
    for name, (F, L, p) in munis.items():
        bL, bF = base_uf[name]; bm = 100 * (bF - bL) / max(bF + bL, 1)
        v = F + L; m = 100 * (F - L) / v
        num += v * (m - bm); n += v; rawm += F - L
    if n <= 0: return None, None, 0
    return state_base_margin + num / n, 100 * rawm / n, n

def project_munis(base_uf, munis, state_row, ratio, swing):
    """Projected final for each municipality: counted votes plus remaining votes at baseline + the state's projected swing.
    ratio: state turnout ratio vs baseline; swing: projected margin of the state's remaining votes minus its baseline margin."""
    out = []
    for name, (bL, bF) in base_uf.items():
        T = (bL + bF) * ratio; bm = 100 * (bF - bL) / max(bF + bL, 1)
        F, L, p = munis.get(name, (0, 0, 0.0))
        n = F + L; rem = 0.0 if p >= 0.995 else max(T - n, 0.0)
        mrem = max(-100.0, min(100.0, bm + swing))
        fm = (F - L) + rem * mrem / 100; tot = n + rem
        out.append([name, round(p, 3), int(n), int(rem), round(100 * fm / tot, 2) if tot else None,
                    round(100 * (F - L) / n, 2) if n else None, round(bm, 2)])
    out.sort(key=lambda r: -(r[2] + r[3]))
    return out   # [name, pct in, counted, remaining, projected final margin, counted margin, baseline margin]
