# Brazil runoff live model (Oct 25, 2026)

Units: 27 states plus Abroad, matching civicAPI race 162819 (state-level only).
Margin: Flavio minus Lula, two-way, in points. Positive = Flavio.

Baseline: first-round state results (civicAPI 130870). Flavio and Lula keep their votes; other candidates'
voters are split to land at Flavio 51 / Lula 49 nationally. Rebuild for another target: `python build_baseline.py 52`.

Run:
  pip install numpy
  python server_br.py            # polls every 30s, serves http://localhost:8000/api/projection and /api/race
  python server_br.py --once     # one fetch, prints the projection
Render: same as the midterm service, start command `python server_br.py`.

Brazil changes vs the midterm engine (engine_br.py): PRE_SD President 4.0, no display shrink, state-scale
regional kernel (900 km), size slope off, turnout noise 0.03, partial-state trust starts at 20% counted,
and ORDER_SD 3.0 for a shared counting-order bias on uncounted votes in states already reporting.
test_feed_br.py replays synthetic nights where Northeast states lag and early precincts lean one way.

## Municipality layer (added)
- At startup the server pulls first-round results by state (civicAPI 130982-131008), allocates the other candidates with the
  same shares as the state baseline, scales each state's municipalities to its state row, and caches muni_r1.json.
- Each cycle it pulls the 27 runoff state races (162829-162855). For each state the counted margin is corrected for which
  municipalities are in: state baseline + vote-weighted swing of counted votes against each municipality's own baseline.
  Those states skip the slow trust ramp and use ORDER_SD_ADJ = 1.0 instead of 3.0.
- New routes: /api/states (per-state table), /api/munis/<UF> (per-municipality projections, largest first).
  /api/status shows each state's raw vs mix-adjusted counted margin.
- If the first-round pages can't be fetched, the server falls back to state rows only.
- test_muni_br.py: mocked night where Flavio-leaning places report first.
