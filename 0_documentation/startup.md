## Main backend (port 5000)

```powershell
cd c:\London_Cycle_Maps\4_backend_engine
python app.py
```

Wait until you see the graph loaded message. First start can take a while (with routing cache v2: ~2–3 min ready).

Optional: `python app.py --day` / `--night` (force light_weight sun gate); `python app.py --no-live` (skip TfL/TomTom; or `$env:SKIP_DISRUPTION_FETCH=1` / `$env:LIVE_DISRUPTIONS=0`).

**Extreme weather QA:** `python app.py --weather-test` — `/weather` returns synthetic extremes (thunderstorm, black ice, heat, etc.) instead of Open-Meteo. A **random scenario is picked each UTC minute** (includes `none` for no warning). Expand the route island to see the warning slot appear/disappear. Frontend polls `/weather` every 60s while this flag is on. Equivalent env: `$env:WEATHER_TEST_MODE=1`.

Kill-switches (default all on): `ARRAY_COSTS=0` → Python weight fns; `CSR_ASTAR=0` → NetworkX uni A*; `NUMBA_ASTAR=0` → pure-Python CSR A*. **Routing cache** (`1_data/london_elev_final_tfl.routing_cache/`, `prebuild_routing_cache.py`): tables/CSR/junctions + lazy geom store. Format v2+. `ROUTING_CACHE=0` forces cold rebuild. Without cache, `GEOM_PREPARSE=background|sync|0` still applies. Requires `numba` for Phase C. Benches: `benchmark_csr_*.py`, `benchmark_geom_preparse.py`, `benchmark_startup_ram.py`.

## Main frontend (port 3000)

```powershell
cd c:\London_Cycle_Maps\5_frontend
npm start

or 

cd c:\London_Cycle_Maps\5_frontend
npm start -- --v2
```

Optional: `npm start -- --day` / `--night` (forces Night Mode theme via `start.js` → `REACT_APP_FORCE_MODE`). Copy `5_frontend/.env.example` → `.env` and set `REACT_APP_MAPBOX_API_KEY`; restart after editing. Opens [http://localhost:3000](http://localhost:3000) → talks to 5000.

## Debug backend (port 5001)

```powershell
cd c:\London_Cycle_Maps\4_backend_engine
python app_debug.py
```



## Debug frontend (port 3001)

```powershell
cd c:\London_Cycle_Maps\8_debug\5_frontend
$env:PORT=3001; npm start
```

