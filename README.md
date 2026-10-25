# Brazil 2026 runoff live model

Live projection for the Oct 25, 2026 presidential runoff (Flávio Bolsonaro vs Lula), by state and municipality, from civicAPI results.

- Python service (repo root): polls civicAPI every 30s, runs the model, serves JSON. Deployed on Render with `render.yaml`.
- Site (`site/`): static page for Cloudflare Pages that reads the Render API every 20s.

## Deploy

1. **GitHub**: create a new repo and push everything in this folder (keep `render.yaml` at the root).
2. **Render**: Dashboard → New → Blueprint → pick the repo → Apply. It creates the `brazil-runoff-model` web service
   (Starter plan, so it doesn't sleep and stop polling). When it's live, copy its URL from the top of the service page.
   Check `https://<service>.onrender.com/api/status`. `baseline_places` should read 5571 within a minute of starting.
3. **Point the site at Render**: put that URL in `site/config.js` (`window.API_BASE`) and push.
4. **Cloudflare**: Workers & Pages → Create → Pages → Connect to Git → pick the repo.
   Framework preset: None. Build command: leave empty. Build output directory: `site`. Save and Deploy.
   Every push redeploys both the site (Cloudflare) and the service (Render).

## API (Render service)
- `/api/projection`: headline margin, 90% range, win probability, % in
- `/api/states`: per-state table
- `/api/munis/<UF>`: per-municipality projections, e.g. `/api/munis/SP`
- `/api/race`: full engine output
- `/api/status`: feed errors and each state's raw vs municipality-adjusted counted margin
- `/health`

## Changing the baseline
`python build_baseline.py 52` rewrites `data.json` for a Flávio 52 / Lula 48 start. Commit and push; Render redeploys.

Margin everywhere is Flávio minus Lula, two-way, in points. See MODEL_NOTES.md for the method.
