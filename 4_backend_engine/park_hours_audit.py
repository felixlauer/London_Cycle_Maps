"""
One-off audit: park opening_hours coverage at four London local times.
Run: python park_hours_audit.py
"""
from __future__ import annotations

import json
import os
import pickle
import sys
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(SCRIPT_DIR, ".."))
GRAPH_PATH = os.path.join(REPO, "1_data", "london_elev_final_tfl.gpickle")
GEOJSON_PATH = os.path.join(REPO, "1_data", "osm_park_polygons.geojson")

sys.path.insert(0, SCRIPT_DIR)
import park_opening_hours as poh  # noqa: E402

LONDON = ZoneInfo("Europe/London")

SLOTS = [
    ("night", datetime(2026, 6, 17, 2, 0, tzinfo=LONDON)),
    ("morning", datetime(2026, 6, 17, 7, 30, tzinfo=LONDON)),
    ("day", datetime(2026, 6, 17, 14, 0, tzinfo=LONDON)),
    ("evening", datetime(2026, 6, 17, 19, 30, tzinfo=LONDON)),
]


def _is_park(d: dict) -> bool:
    return str(d.get("is_park", "")).strip().lower() == "yes"


def _eval_polygon_hours(expr: str, at_time: datetime, fallback: bool) -> bool:
    expr = str(expr or "").strip()
    if not expr:
        return fallback
    try:
        oh = poh._opening_hours_parser(expr)
        if oh.is_open(time=at_time):
            return True
        if oh.is_closed(time=at_time):
            return False
        return fallback
    except Exception:
        return fallback


def main() -> None:
    print("Loading graph...")
    with open(GRAPH_PATH, "rb") as f:
        G = pickle.load(f)

    catalog = list(G.graph.get("park_opening_hours_unique") or [])
    park_edges = [(u, v, d) for u, v, d in G.edges(data=True) if _is_park(d)]
    with_hours = sum(1 for _, _, d in park_edges if str(d.get("opening_hours", "")).strip())
    without_hours = len(park_edges) - with_hours

    with open(GEOJSON_PATH, encoding="utf-8") as f:
        polygons = json.load(f).get("features", [])
    poly_with_hours = [
        p for p in polygons
        if str((p.get("properties") or {}).get("opening_hours", "")).strip()
    ]
    poly_without_hours = len(polygons) - len(poly_with_hours)

    print("=== GRAPH BASELINE ===")
    print(f"Graph: {GRAPH_PATH}")
    print(f"Park directed edges: {len(park_edges):,}")
    print(f"  with OSM opening_hours on edge: {with_hours:,}")
    print(f"  without (dawn-dusk fallback at route time): {without_hours:,}")
    print(f"Unique opening_hours strings in catalog: {len(catalog)}")
    print(f"OSM park polygons: {len(polygons):,}")
    print(f"  polygons with opening_hours tag: {len(poly_with_hours)}")
    print(f"  polygons without tag: {poly_without_hours}")

    print("\n=== ALL UNIQUE CATALOG STRINGS (105) ===")
    for i, s in enumerate(sorted(catalog), 1):
        print(f"  {i:3}. {s}")

    for slot_name, at_time in SLOTS:
        hours_map, fallback_open = poh.build_request_hours_context(catalog, at_time)
        edge_open = edge_closed = 0
        edge_open_has_hours = edge_closed_has_hours = 0
        edge_open_fallback = edge_closed_fallback = 0

        for _, _, d in park_edges:
            open_ = poh.is_park_edge_open(d, hours_map, fallback_open)
            if open_:
                edge_open += 1
                if str(d.get("opening_hours", "")).strip():
                    edge_open_has_hours += 1
                else:
                    edge_open_fallback += 1
            else:
                edge_closed += 1
                if str(d.get("opening_hours", "")).strip():
                    edge_closed_has_hours += 1
                else:
                    edge_closed_fallback += 1

        poly_open = poly_closed = 0
        for feat in polygons:
            props = feat.get("properties") or {}
            oh = str(props.get("opening_hours", "")).strip()
            if _eval_polygon_hours(oh, at_time, fallback_open):
                poly_open += 1
            else:
                poly_closed += 1

        strings_open = sum(1 for v in hours_map.values() if v)
        strings_closed = sum(1 for v in hours_map.values() if not v)

        print(f"\n=== SLOT: {slot_name.upper()} — {at_time.isoformat()} ===")
        print(f"Fallback (dawn-dusk) open: {fallback_open}")
        print(f"Catalog strings: {strings_open} open / {strings_closed} closed (of {len(hours_map)})")
        print(f"Park EDGES: {edge_open:,} open / {edge_closed:,} closed (of {len(park_edges):,})")
        print(f"  edges with OSM hours: {edge_open_has_hours:,} open, {edge_closed_has_hours:,} closed")
        print(f"  edges on fallback:    {edge_open_fallback:,} open, {edge_closed_fallback:,} closed")
        print(f"Park POLYGONS: {poly_open} open / {poly_closed} closed (of {len(polygons)})")
        print(f"  polygons with OSM tag: open/closed counted above includes fallback for untagged")

        print("  Per-string evaluation:")
        for s in sorted(hours_map.keys()):
            status = "OPEN" if hours_map[s] else "CLOSED"
            print(f"    [{status}] {s}")


if __name__ == "__main__":
    main()
