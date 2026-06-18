# Park opening hours — verification audit (2026-06-17)

**Graph:** `1_data/london_elev_final_tfl.gpickle` (recompiled 17 Jun 2026)  
**Timezone:** `Europe/London` (BST, `+01:00` on audit date)  
**Parser:** `opening-hours-py` via [`4_backend_engine/park_opening_hours.py`](../4_backend_engine/park_opening_hours.py)  
**Full per-string output:** [`park_hours_audit_2026-06-17.txt`](park_hours_audit_2026-06-17.txt) (105 strings × 4 slots)  
**Re-run:** `python 4_backend_engine/park_hours_audit.py`

---

## Baseline coverage

| Metric | Count |
|--------|------:|
| Park directed edges (`is_park=yes`) | 410,952 |
| Park edges with OSM `opening_hours` on edge | 46,911 (11.4%) |
| Park edges without hours (dawn-dusk fallback) | 364,041 (88.6%) |
| Unique `opening_hours` strings in `G.graph["park_opening_hours_unique"]` | 125 (105 before Royal Parks overrides) |
| OSM park polygons in GeoJSON | 4,576 |
| Polygons with `opening_hours` tag | 201 (4.4%) |
| Polygons without tag (fallback at route time) | 4,375 |

**Implication:** Most park routing impact at night comes from the **dawn-dusk fallback** on 364k edges, not from explicit OSM hour strings. Only **`24/7`** (103 polygon occurrences in OSM; 14,874 edges at night) stays open through closed parks at 02:00.

---

## Four test slots (Tuesday 17 June 2026)

Slots chosen to exercise night closure, morning mixture (before many `08:00` opens), midday openness, and evening mixture (after some `18:00` / `19:00` closes, before dusk).

| Slot | Local time (ISO) | Fallback dawn-dusk | Catalog strings open / closed | Park **edges** open / closed | Park **polygons** open / closed |
|------|------------------|--------------------|------------------------------|------------------------------|--------------------------------|
| **Night** | `2026-06-17T02:00:00+01:00` | **Closed** | 1 / 104 (of 105) | **14,874** / **396,078** | 103 / 4,473 |
| **Morning** | `2026-06-17T07:30:00+01:00` | **Open** | 29 / 76 | **401,170** / **9,782** | 4,532 / 44 |
| **Day** | `2026-06-17T14:00:00+01:00` | **Open** | 47 / 58 | **410,750** / **202** | 4,575 / 1 |
| **Evening** | `2026-06-17T19:30:00+01:00` | **Open** | 40 / 65 | **408,102** / **2,850** | 4,564 / 12 |

### Edge breakdown (OSM hours vs fallback)

| Slot | Edges with OSM hours: open / closed | Edges on fallback: open / closed |
|------|-------------------------------------|----------------------------------|
| Night 02:00 | 14,874 / 32,037 | 0 / 364,041 |
| Morning 07:30 | 37,129 / 9,782 | 364,041 / 0 |
| Day 14:00 | 46,709 / 202 | 364,041 / 0 |
| Evening 19:30 | 44,061 / 2,850 | 364,041 / 0 |

---

## Interpretation by slot

### Night (02:00)

- Fallback **closed** → all 364,041 untagged edges **impassable** (`1e9` in routing).
- Only catalog string **open:** `24/7` → **14,874** edges remain traversable (cycle paths through 24h parks).
- **396,078** park edges blocked (96.4% of park edges).
- Polygon view: 103 open (almost all `24/7` or mis-tagged), 4,473 closed.

### Morning (07:30)

- Fallback **open** → 364,041 untagged edges traversable (dawn has passed).
- **9,782** edges with explicit hours still **closed** (e.g. `08:00-dusk`, `Mo-Su 08:00-sunset`, `Mo-Su 09:00-17:00` not yet open at 07:30).
- **Mixture:** 97.6% park edges open, 2.4% closed — mainly early-opening rules.

### Day (14:00)

- **Nearly fully open:** 410,750 / 410,952 edges (99.95%).
- Only **202** edges closed — strings that evaluate closed in June midday (e.g. winter-only month rules misparsed, `24/7 closed`, weekday lunch-only windows).
- **1** polygon closed at polygon level (vs 4,575 open).

### Evening (19:30)

- **Mixture:** 2,850 edges closed — e.g. `Mo-Su 07:30-18:00`, `Mo-Fr 10:00-16:30`, `Mo-Su 09:00-17:00`, `Apr-Sep Mo-Fr 08:00-19:00` (closed after 19:00).
- Solar/sunset strings (`08:00-sunset`, `07:30-dusk`) still **open** (before dusk in mid-June).
- 99.3% edges still open because fallback + long summer hours dominate.

---

## Catalog strings (105 unique on graph)

Most frequent OSM polygon tags (GeoJSON, 201 tagged polygons):

| Count | `opening_hours` string |
|------:|--------------------------|
| 103 | `24/7` |
| 13 | `07:30 - dusk` |
| 8 | `08:00-dusk` |
| 7 | `sunrise-sunset` |
| 4 | `08:00-sunset` |
| 4 | `Mo-Su 08:00-sunset` |
| 3 | `Mo-Su 08:00-dusk` |
| 3 | `09:00-sunset` |
| 3 | `dawn-dusk` |

The graph catalog contains **105** distinct strings (including seasonal/month variants and typos, e.g. `07:30 - 15mins before sunsetoor`). Full sorted list in [`park_hours_audit_2026-06-17.txt`](park_hours_audit_2026-06-17.txt) lines 11–117.

**Always open at all four slots:** `24/7`  
**Always closed at all four slots (June):** winter month rules (`Jan …`, `Dec …`, `Feb …`), `24/7 closed`, `Dec 25,Dec 26,Jan 01 off`, many `Oct-Mar …` variants  
**Open only day/evening:** `Mo-Su 08:00-dusk`, `08:00-sunset`, `Mo-Fr 10:00-16:30`, etc.

---

## Operator checklist

1. **Pipeline (production graph):** use `--pickle-only` (GraphML fails on list catalog attribute):
   ```text
   python tag_attractions_osm.py --input ../1_data/london_elev_final_tfl.gpickle --pickle-only
   python apply_attraction_manual.py --pickle-only
   ```
2. **Backend dependency:** `pip install -r 4_backend_engine/requirements.txt` (`opening-hours-py`).
3. **Restart** `python app.py` after graph reload.
4. **`/route` meta:** `park_hours_at`, `park_fallback_open`, `park_hours_map_size`.

---

## Royal Parks overrides — verified on graph (17 Jun 2026)

After re-running `tag_attractions_osm.py --pickle-only` on `london_elev_final_tfl.gpickle` with [`park_hours_overrides.json`](../3_pipeline/park_hours_overrides.json), Hyde Park and Kensington Gardens hours are present on production edges. Overrides compete via **highest `park_hours_overlap`** (same as OSM hours); winning polygon name is stored in `park_hours_owner`.

| Park | `park_hours_owner` edges | `opening_hours` on graph | Sample `attraction_name` |
|------|-------------------------:|--------------------------|--------------------------|
| **Hyde Park** | 3,698 | `Mo-Su 05:00-24:00` | `Hyde Park` (3,696 edges by name) |
| **Kensington Gardens** | 1,730 | Full seasonal Royal Parks string | `Kensington Gardens` (1,594); 136 edges `Kensington Gardens;Royal Albert Hall` |

Both override strings appear in `G.graph["park_opening_hours_unique"]`. Sample edges show `park_hours_overlap: 1.0`. Hyde Park ranks 11th among parks by `park_hours_owner` count (after Richmond Park, Olympic Park, Bushy Park, etc.).

**Quick re-check (pickle load):**

```powershell
python -c "
import pickle
from collections import Counter
G = pickle.load(open('1_data/london_elev_final_tfl.gpickle','rb'))
own = Counter(d.get('park_hours_owner','') for _,_,d in G.edges(data=True) if str(d.get('is_park','')).lower()=='yes')
print(own['Hyde Park'], own['Kensington Gardens'])
"
# Expected: 3698 1730
```

Details and override strings: [`park_hours_overrides.md`](park_hours_overrides.md).

---

## Open product questions (from audit)

- **88.6% fallback:** Untagged parks use dawn-dusk — effectively open ~07:00–21:30 in June. User may want explicit “always closed at night” parks without OSM tags.
- **`24/7` at night:** 14,874 edges stay routable at 02:00 — verify against ground truth (Royal parks, etc.).
- **GraphML export:** `park_opening_hours_unique` stored as Python `list` breaks `save_graph` GraphML write; pickle-only workaround until catalog serialized as string.
