# Manual park opening hours overrides

Royal Parks and other venues sometimes need **curated** `opening_hours` that OSM does not carry (or carries incorrectly). Overrides are stored in the pipeline repo and applied every time `tag_attractions_osm.py` runs.

---

## Files

| File | Role |
|------|------|
| [`3_pipeline/park_hours_overrides.json`](../3_pipeline/park_hours_overrides.json) | Committed overrides (`match_names` → `opening_hours` string) |
| [`3_pipeline/park_hours_overrides.py`](../3_pipeline/park_hours_overrides.py) | Load + apply helpers |
| [`3_pipeline/tag_attractions_osm.py`](../3_pipeline/tag_attractions_osm.py) | Applies overrides at polygon tag time (`resolve_polygon_opening_hours`) |

Overrides are written to graph edge attribute **`opening_hours`** (same as OSM). Park display names remain in **`attraction_name`**.

---

## How matching works

1. **Per polygon:** When tagging from `osm_park_polygons.geojson`, if `properties.name` matches a `match_names` entry, that override string is passed as `opening_hours` for the polygon (instead of empty OSM hours).
2. **Per edge (spatial):** [`attraction_spatial.py`](../3_pipeline/attraction_spatial.py) tags each edge with the `opening_hours` of the park polygon with the **highest overlap ratio** (`park_hours_overlap`). Manual overrides participate in the same competition as OSM hours — no post-pass by name.
3. **Ownership:** The winning polygon name is stored on the edge as `park_hours_owner` (for debugging; routing uses `opening_hours` only).

If Hyde Park and Kensington Gardens both tag the same edge, whichever polygon covers more of the edge length sets `opening_hours` (including Royal Parks overrides).

---

## Royal Parks entries (2026-06-17)

### Kensington Gardens

**Match names:** `Kensington Gardens`

**Opening hours (OSM opening_hours format):**

```text
Jan 01-Jan 18 06:00-16:30; Jan 19-Feb 01 06:00-17:00; Feb 02-Feb 22 06:00-17:30; Feb 23-Mar 08 06:00-18:00; Mar 09-Mar 28 06:00-18:30; Mar 29-Apr 12 06:00-20:00; Apr 13-May 03 06:00-20:30; May 04-May 17 06:00-21:00; May 18-Jun 07 06:00-21:30; Jun 08-Jun 28 06:00-21:45; Jun 29-Aug 02 06:00-21:30; Aug 03-Aug 16 06:00-21:00; Aug 17-Aug 30 06:00-20:30; Aug 31-Sep 13 06:00-20:00; Sep 14-Sep 27 06:00-19:30; Sep 28-Oct 04 06:00-19:00; Oct 05-Oct 24 06:00-18:30; Oct 25-Nov 01 06:00-17:00; Nov 02-Dec 31 06:00-16:30
```

**Example check (17 Jun 2026, Europe/London):** open 06:00–21:45; closed at 23:30.

### Hyde Park (including Enclosed Garden polygon)

**Match names:** `Hyde Park`, `Hyde Park Enclosed Garden`

**Opening hours:** `Mo-Su 05:00-24:00` (05:00–midnight daily)

**Example check (17 Jun 2026):** closed 04:00; open 06:00 and 23:30.

---

## Graph verification (`london_elev_final_tfl.gpickle`, 17 Jun 2026)

Confirmed after `tag_attractions_osm.py --pickle-only` + `apply_attraction_manual.py --pickle-only`:

| Check | Result |
|-------|--------|
| Hyde override in catalog | Yes (`Mo-Su 05:00-24:00`) |
| Kensington override in catalog | Yes (seasonal string) |
| Edges with Hyde `opening_hours` | **3,698** (`park_hours_owner`: Hyde Park) |
| Edges with Kensington `opening_hours` | **1,730** (`park_hours_owner`: Kensington Gardens) |
| Catalog size | **125** unique strings (was 105 pre-overrides) |

`attraction_name` counts can differ slightly from `park_hours_owner` (e.g. compound names `Kensington Gardens;Royal Albert Hall`, boundary edges) — routing uses `opening_hours` from overlap winner only.

Full audit context: [`park_hours_verification.md`](park_hours_verification.md) § Royal Parks overrides.

---

## Pipeline commands

Production graph (`london_elev_final_tfl.gpickle`):

```powershell
cd c:\London_Cycle_Maps\3_pipeline
python tag_attractions_osm.py --input ../1_data/london_elev_final_tfl.gpickle --pickle-only
python apply_attraction_manual.py --pickle-only
```

Intermediate graph (`london_elev_final`) during full pipeline:

```powershell
python tag_attractions_osm.py --pickle-only
```

Restart backend after updating the pickle:

```powershell
cd c:\London_Cycle_Maps\4_backend_engine
python app.py
```

Use `--pickle-only` until `park_opening_hours_unique` is stored in a GraphML-safe format (list type currently breaks GraphML export).

---

## Adding another override

1. Edit `3_pipeline/park_hours_overrides.json` — add an object to `overrides`:

```json
{
  "match_names": ["Exact OSM polygon name", "Alternate name"],
  "opening_hours": "Mo-Su 08:00-20:00",
  "source": "Royal Parks website, YYYY-MM-DD"
}
```

2. Validate the string with `opening-hours-py` if non-trivial (solar events, seasonal rules).
3. Re-run `tag_attractions_osm.py` on the target graph (see above).
4. Optionally re-run `park_hours_audit.py` and update [`park_hours_verification.md`](park_hours_verification.md).

---

## Related docs

- [`park_hours_verification.md`](park_hours_verification.md) — audit methodology and baseline stats
- [`GRAPH.md`](GRAPH.md) §3.8 — `opening_hours` edge tag and routing constraint
