# Brazil runoff live service. Polls civicAPI race 162819 (state level), runs engine_br, serves JSON.
# Routes: /health, /api/projection (headline), /api/race (full detail incl. per-state table), /api/status
# Run locally: python server_br.py            one-shot: python server_br.py --once
import gzip, json, os, sys, time, threading, hashlib
for _k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"): os.environ.setdefault(_k, "1")
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import engine_br as engine, civicapi_feed, muni
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
RACE_ID = int(os.environ.get("CIVIC_RACE", "162819"))
POLL = int(os.environ.get("POLL_SECONDS", "30"))
OUT = os.path.join(HERE, "projection.json")
LOCK = threading.Lock()
STATE = {"projection": {"updated": None, "mode": "starting"}, "detail": None, "warn": [], "error": None, "munis": {}, "states": [], "muni_status": {}}
BASE = {}      # {UF: {muni: [L, F]}} first-round runoff baseline, built at startup
STATE_RACE = {}  # UF -> runoff state race id
MEM = {}

def cycle(race, P, last):
    err = None; counted = {}
    try:
        payload = civicapi_feed.fetch(RACE_ID)
        counted = civicapi_feed.parse_counties(payload, race)          # state rows from the national race (and Abroad)
        STATE["feed_pct"] = payload.get("percent_reporting"); STATE["feed_updated"] = payload.get("last_updated")
        live_munis = {}
        if BASE:
            with ThreadPoolExecutor(8) as ex:
                got = dict(zip(STATE_RACE, ex.map(lambda rid: _safe(rid), STATE_RACE.values())))
            rows = {c[0]: c for c in race["counties"]}
            for uf, d in got.items():
                if d is None: STATE["muni_status"][uf] = "fetch failed"; continue
                st, ms, miss = muni.parse_state(d, BASE.get(uf, {}))
                live_munis[uf] = ms
                key = "BR_" + uf; r = rows.get(key)
                if st is None or r is None or st[0] + st[1] <= 0:
                    STATE["muni_status"][uf] = "no votes yet"; continue
                bm = 100 * (r[3] - r[2]) / max(r[2] + r[3], 1)
                adj, raw, nm = muni.mix_adjusted(bm, ms, BASE[uf])
                n = st[0] + st[1]
                if adj is None or nm < 0.8 * n:    # municipality rows cover too little of the state count: use the state row as is
                    counted[key] = (st[1], st[0], st[2]); STATE["muni_status"][uf] = "state row only (municipalities cover %.0f%%)" % (100 * nm / n); continue
                adj = max(-99.0, min(99.0, adj))
                counted[key] = (n * (1 - adj / 100) / 2, n * (1 + adj / 100) / 2, st[2], None, None, True)
                STATE["muni_status"][uf] = "ok: raw %+.1f, mix-adjusted %+.1f, %d places in%s" % (raw, adj, len(ms), (", %d unmatched" % len(miss)) if miss else "")
        counted, w = civicapi_feed.sanitize(counted, race, MEM)
        STATE["warn"] = w
    except Exception as e:
        err = str(e)[:150]
        if STATE["detail"] is not None:
            STATE["error"] = err; return last
    key = hashlib.md5(json.dumps(counted, sort_keys=True).encode()).hexdigest()
    if key != last or STATE["detail"] is None:
        res = engine.project(P, counted)
        with LOCK:
            STATE["detail"] = res
            STATE["projection"] = {"updated": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()), "mode": res["state"],
                                   "label": "Brazil President, runoff", "margin_def": "Flavio minus Lula, two-way, points",
                                   "margin": res["margin"], "p05": res["p05"], "p25": res["p25"], "p75": res["p75"], "p95": res["p95"],
                                   "win_prob_flavio": res["win_prob_R"], "reporting": res["reporting"], "call_ready": res["call_ready"],
                                   "shift_vs_baseline": res["shift"], "states_in": sum(1 for c in res["counties"] if c[3] > 0),
                                   "feed_pct_reporting": STATE.get("feed_pct"), "percentiles": res["percentiles"]}
        _munis(res, live_munis if BASE else {}, race)
        with open(OUT + ".tmp", "w") as f: json.dump(STATE["projection"], f, separators=(",", ":"))
        os.replace(OUT + ".tmp", OUT)
    STATE["error"] = err
    return key


def _safe(rid):
    try: return muni.fetch(rid)
    except Exception: return None

def _munis(res, live, race):
    rows = {c[0]: c for c in race["counties"]}; states = []; out = {}
    for c in res["counties"]:
        fips, name, p, n, rem, pm = c[0], c[1], c[2], c[3], c[4], c[5]
        r = rows[fips]; T = r[2] + r[3]; bm = 100 * (r[3] - r[2]) / max(T, 1)
        rmm = c[10]; swing = (rmm - bm) if rmm is not None else ((pm - bm) if pm is not None else 0.0)
        states.append({"id": fips, "name": name, "pct_in": p, "counted": n, "remaining": rem, "projected_margin": pm,
                       "counted_margin": c[11], "baseline_margin": round(bm, 2), "swing": round(swing, 2)})
        uf = fips[3:]
        if uf in BASE:
            out[uf] = muni.project_munis(BASE[uf], live.get(uf, {}), r, (n + rem) / max(T, 1), swing)
    STATE["states"] = states; STATE["munis"] = out

def init_munis(race):
    """Build the municipality baseline and the UF -> runoff race map. Failures leave the model on state rows only."""
    global BASE
    try:
        r1 = muni.load_r1()
        BASE = muni.baseline(r1, race["alloc"], {c[0]: c for c in race["counties"]})
        for rid in muni.R2_IDS:
            d = _safe(rid)
            if d: STATE_RACE[muni.uf_of(d)] = rid
        print("municipality baseline:", sum(len(v) for v in BASE.values()), "places;", len(STATE_RACE), "state races", flush=True)
    except Exception as e:
        BASE = {}; print("municipality layer off:", e, flush=True)

def poller(race, P):
    init_munis(race)          # in the background so the port opens right away (Render health check)
    last = None
    while True:
        t = time.time()
        try: last = cycle(race, P, last)
        except Exception as e: print("cycle failed:", e, flush=True)
        print("cycle", round(time.time() - t, 1), "s", STATE["projection"].get("margin"), STATE["projection"].get("reporting"), flush=True)
        time.sleep(max(1, POLL - (time.time() - t)))

class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        b = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode()
        gz = "gzip" in (self.headers.get("Accept-Encoding") or "") and len(b) > 600
        if gz: b = gzip.compress(b, 5)
        self.send_response(code); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Cache-Control", "public, max-age=10, s-maxage=10")
        if gz: self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/health": return self._send(200, {"ok": True, "updated": STATE["projection"]["updated"]})
        if p == "/api/projection":
            with LOCK: return self._send(200, STATE["projection"])
        if p == "/api/race":
            with LOCK: return self._send(200, STATE["detail"] or {})
        if p == "/api/states":
            with LOCK: return self._send(200, {"updated": STATE["projection"]["updated"], "states": STATE["states"]})
        if p.startswith("/api/munis/"):
            uf = p.rsplit("/", 1)[1].upper()
            with LOCK: rows = STATE["munis"].get(uf)
            return self._send(200 if rows is not None else 404, {"uf": uf, "columns": ["name", "pct_in", "counted", "remaining", "projected_margin", "counted_margin", "baseline_margin"], "rows": rows} if rows is not None else {"error": "unknown state"})
        if p == "/api/status": return self._send(200, {"feed_error": STATE["error"], "guard_warnings": STATE["warn"], "feed_updated": STATE.get("feed_updated"), "municipalities": STATE["muni_status"], "baseline_places": sum(len(v) for v in BASE.values())})
        self._send(404, {"error": "not found"})
    def log_message(self, *a): pass

if __name__ == "__main__":
    race = json.load(open(os.path.join(HERE, "data.json"), encoding="utf-8"))["races"][0]
    P = engine.prep(race)
    if "--once" in sys.argv:
        init_munis(race); cycle(race, P, None); print(json.dumps(STATE["projection"], indent=1), "\nerror:", STATE["error"])
    else:
        threading.Thread(target=poller, args=(race, P), daemon=True).start()
        ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8000"))), H).serve_forever()
