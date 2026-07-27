#!/usr/bin/env python3
"""
Leaflet map: Phase-1 signal clusters — bounding boxes + segments (combined).

  cd c:\\London_Cycle_Maps
  python 4_backend_engine/export_signal_cluster_map.py

Writes:
  0_documentation/testing/signal_cluster_map.html
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = Path(
    os.environ.get(
        "ROUTING_CACHE_DIR",
        str(REPO_ROOT / "1_data" / "london_elev_final_tfl.routing_cache"),
    )
)
OUT_HTML = Path(
    os.environ.get(
        "SIGNAL_CLUSTER_MAP_OUT",
        str(REPO_ROOT / "0_documentation" / "testing" / "signal_cluster_map.html"),
    )
)
SIMPLE_CHORDS = os.environ.get("SIGNAL_CLUSTER_MAP_SIMPLE", "0").strip().lower() in (
    "1",
    "true",
    "yes",
)


def _xy_key(xy) -> tuple[float, float]:
    return (float(xy[0]), float(xy[1]))


def _color_for_size(n: int) -> str:
    if n <= 1:
        return "#64748b"
    if n == 2:
        return "#0ea5e9"
    if n <= 4:
        return "#22c55e"
    if n <= 8:
        return "#f59e0b"
    return "#ef4444"


def main() -> int:
    nodes_path = CACHE_DIR / "nodes.npz"
    csr_path = CACHE_DIR / "csr.npz"
    edges_path = CACHE_DIR / "edges.npz"
    offsets_path = CACHE_DIR / "geom_offsets.npy"
    flat_path = CACHE_DIR / "geom_flat.npy"
    for p in (nodes_path, csr_path, edges_path, offsets_path, flat_path):
        if not p.is_file():
            print(f"ERROR: missing {p}")
            return 1

    print("Loading cache arrays…", flush=True)
    nodes = np.load(nodes_path)
    csr = np.load(csr_path)
    edges = np.load(edges_path)
    offsets = np.load(offsets_path)
    flat = np.load(flat_path)

    meta_path = CACHE_DIR / "meta.json"
    formula = ""
    if meta_path.is_file():
        formula = json.loads(meta_path.read_text(encoding="utf-8")).get("formula_id", "")

    cids = nodes["signal_cluster_id"].astype(np.int32)
    idx_to_node = csr["idx_to_node"]
    lon = csr["lon"].astype(np.float64)
    lat = csr["lat"].astype(np.float64)
    edge_u = edges["edge_u"]
    edge_v = edges["edge_v"]
    signal_entry = edges["signal_entry"].astype(np.uint8)
    signal_exit = edges["signal_exit"].astype(np.uint8)
    n_edges = edge_u.shape[0]

    print("Indexing nodes…", flush=True)
    xy_to_cid: dict[tuple[float, float], int] = {}
    cluster_members: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for i, cid in enumerate(cids):
        key = (float(idx_to_node[i, 0]), float(idx_to_node[i, 1]))
        ci = int(cid)
        xy_to_cid[key] = ci
        if ci > 0:
            cluster_members[ci].append((float(lon[i]), float(lat[i])))

    cluster_size = {cid: len(pts) for cid, pts in cluster_members.items()}
    size_hist: dict[int, int] = defaultdict(int)
    for n in cluster_size.values():
        size_hist[n] += 1

    # --- Bounding boxes ---
    print("Building bboxes…", flush=True)
    bbox_features = []
    pad = 0.00011
    for cid, pts in cluster_members.items():
        n = len(pts)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        min_lon, max_lon = min(xs), max(xs)
        min_lat, max_lat = min(ys), max(ys)
        if max_lon - min_lon < pad * 2:
            mid = 0.5 * (min_lon + max_lon)
            min_lon, max_lon = mid - pad, mid + pad
        if max_lat - min_lat < pad * 2:
            mid = 0.5 * (min_lat + max_lat)
            min_lat, max_lat = mid - pad, mid + pad
        color = _color_for_size(n)
        ring = [
            [min_lon, min_lat],
            [max_lon, min_lat],
            [max_lon, max_lat],
            [min_lon, max_lat],
            [min_lon, min_lat],
        ]
        bbox_features.append(
            {
                "type": "Feature",
                "properties": {
                    "cluster_id": cid,
                    "n_nodes": n,
                    "color": color,
                    "kind": "bbox",
                },
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            }
        )

    # --- Segments ---
    print("Scanning edges…", flush=True)
    role_rank = {"internal": 4, "entry": 3, "exit": 2, "incident": 1}
    best: dict[tuple[tuple[float, float], tuple[float, float]], dict] = {}

    def undirected_key(u_xy, v_xy):
        a, b = _xy_key(u_xy), _xy_key(v_xy)
        return (a, b) if a <= b else (b, a)

    def consider(eid: int, role: str, cid: int):
        if cid <= 0:
            return
        u_xy = edge_u[eid]
        v_xy = edge_v[eid]
        key = undirected_key(u_xy, v_xy)
        prev = best.get(key)
        if prev is not None and role_rank[prev["role"]] >= role_rank[role]:
            if role != prev["role"] and role not in prev.get("also", []):
                prev.setdefault("also", []).append(role)
            return
        also = []
        if prev is not None and prev["role"] != role:
            also = [prev["role"]] + list(prev.get("also") or [])
        a, b = int(offsets[eid]), int(offsets[eid + 1])
        if SIMPLE_CHORDS or b <= a:
            coords = [
                [float(u_xy[0]), float(u_xy[1])],
                [float(v_xy[0]), float(v_xy[1])],
            ]
        else:
            chunk = flat[a:b]
            coords = [
                [float(chunk[j, 1]), float(chunk[j, 0])] for j in range(chunk.shape[0])
            ]
            if len(coords) < 2:
                coords = [
                    [float(u_xy[0]), float(u_xy[1])],
                    [float(v_xy[0]), float(v_xy[1])],
                ]
        best[key] = {
            "role": role,
            "also": also,
            "cluster_id": cid,
            "n_nodes": cluster_size.get(cid, 0),
            "coords": coords,
            "eid": eid,
        }

    n_internal = n_entry = n_exit = n_incident = 0
    for eid in range(n_edges):
        u_key = _xy_key(edge_u[eid])
        v_key = _xy_key(edge_v[eid])
        cu = xy_to_cid.get(u_key, 0)
        cv = xy_to_cid.get(v_key, 0)
        if cu > 0 and cu == cv:
            consider(eid, "internal", cu)
            n_internal += 1
        if signal_entry[eid]:
            consider(eid, "entry", cv if cv > 0 else cu)
            n_entry += 1
        if signal_exit[eid]:
            consider(eid, "exit", cu if cu > 0 else cv)
            n_exit += 1
        if cu > 0 or cv > 0:
            consider(eid, "incident", cu if cu > 0 else cv)
            n_incident += 1

    role_color = {
        "internal": "#ef4444",
        "entry": "#7c3aed",
        "exit": "#db2777",
        "incident": None,
    }

    seg_features = []
    role_counts: dict[str, int] = defaultdict(int)
    for rec in best.values():
        role = rec["role"]
        role_counts[role] += 1
        n = rec["n_nodes"]
        color = role_color[role] or _color_for_size(n)
        weight = 4 if role == "internal" else (3 if role in ("entry", "exit") else 2)
        also = rec.get("also") or []
        seg_features.append(
            {
                "type": "Feature",
                "properties": {
                    "cluster_id": rec["cluster_id"],
                    "n_nodes": n,
                    "role": role,
                    "also": ",".join(also) if also else "",
                    "color": color,
                    "weight": weight,
                    "eid": rec["eid"],
                    "kind": "segment",
                },
                "geometry": {"type": "LineString", "coordinates": rec["coords"]},
            }
        )

    bbox_geo = json.dumps(
        {"type": "FeatureCollection", "features": bbox_features}, separators=(",", ":")
    )
    seg_geo = json.dumps(
        {"type": "FeatureCollection", "features": seg_features}, separators=(",", ":")
    )

    n_clusters = len(cluster_members)
    n_nodes = int((cids > 0).sum())
    n_single = size_hist.get(1, 0)
    n_multi = sum(c for n, c in size_hist.items() if n >= 2)
    hist_rows = "".join(
        f"<tr><td>{k}</td><td>{size_hist[k]}</td></tr>" for k in sorted(size_hist)
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Signal clusters — boxes + segments</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    html, body {{ margin: 0; height: 100%; font-family: system-ui, sans-serif; }}
    #map {{ position: absolute; inset: 0; }}
    .panel {{
      position: absolute; z-index: 1000; top: 12px; left: 12px;
      background: rgba(255,255,255,0.94); padding: 12px 14px; border-radius: 8px;
      box-shadow: 0 2px 12px rgba(0,0,0,0.18); max-width: 380px; font-size: 13px;
      line-height: 1.35; max-height: calc(100% - 24px); overflow: auto;
    }}
    .panel h1 {{ margin: 0 0 6px; font-size: 15px; }}
    .panel table {{ border-collapse: collapse; margin-top: 6px; width: 100%; }}
    .panel td, .panel th {{ border-bottom: 1px solid #e2e8f0; padding: 2px 6px; text-align: left; }}
    .swatch {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 4px; vertical-align: middle; }}
    .muted {{ color: #64748b; font-size: 12px; }}
    .row {{ margin-top: 4px; }}
  </style>
</head>
<body>
  <div class="panel">
    <h1>Signal clusters (expand-v2)</h1>
    <div class="muted">{formula or "(no meta)"}</div>
    <div style="margin-top:6px">
      <strong>{n_clusters:,}</strong> clusters · <strong>{n_nodes:,}</strong> cluster nodes
      (incl. expanded interior)
    </div>
    <div class="muted">{n_single:,} size-1 · {n_multi:,} multi-node</div>
    <div class="muted" style="margin-top:6px">
      Segments drawn: <strong>{len(seg_features):,}</strong><br/>
      Directed scan: entry={n_entry:,}, exit={n_exit:,}, both-ends={n_internal:,}, incident={n_incident:,}
    </div>
    <div class="row" style="margin-top:8px"><b>Use the layer control (top-right)</b> to toggle boxes / segments.</div>
    <div class="row" style="margin-top:8px"><b>Boxes</b> — colour by node count</div>
    <div>
      <span class="swatch" style="background:#64748b"></span>1
      <span class="swatch" style="background:#0ea5e9"></span>2
      <span class="swatch" style="background:#22c55e"></span>3–4
      <span class="swatch" style="background:#f59e0b"></span>5–8
      <span class="swatch" style="background:#ef4444"></span>9+
    </div>
    <div class="row" style="margin-top:8px"><b>Segments</b></div>
    <div class="row"><span class="swatch" style="background:#ef4444"></span>internal ·
      <span class="swatch" style="background:#7c3aed"></span>entry ·
      <span class="swatch" style="background:#db2777"></span>exit</div>
    <div class="row"><span class="swatch" style="background:#0ea5e9"></span>incident (size colour)</div>
    <div class="muted">Draw roles: {dict(role_counts)}</div>
    <div class="muted" style="margin-top:6px">
      After expand-v2, footway entries should appear (violet entry on ped mesh).
      Prebuild reported ~2070 footway entry edges.
    </div>
    <details style="margin-top:8px">
      <summary>Cluster size histogram</summary>
      <table><thead><tr><th>nodes</th><th>clusters</th></tr></thead><tbody>
      {hist_rows}
      </tbody></table>
    </details>
  </div>
  <div id="map"></div>
  <script>
    const bboxData = {bbox_geo};
    const segData = {seg_geo};
    const map = L.map("map", {{ preferCanvas: true }}).setView([51.5074, -0.1278], 13);
    const osm = L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap"
    }}).addTo(map);

    const boxes = L.geoJSON(bboxData, {{
      style: (f) => ({{
        color: f.properties.color,
        weight: 1,
        fillColor: f.properties.color,
        fillOpacity: 0.18,
      }}),
      onEachFeature: (f, lyr) => {{
        const p = f.properties;
        lyr.bindPopup(`<b>cluster ${{p.cluster_id}}</b><br/>${{p.n_nodes}} node(s)<br/>bbox`);
      }},
    }});

    const segs = L.geoJSON(segData, {{
      style: (f) => ({{
        color: f.properties.color,
        weight: f.properties.weight || 2,
        opacity: 0.85,
      }}),
      onEachFeature: (f, lyr) => {{
        const p = f.properties;
        const also = p.also ? `<br/>also: ${{p.also}}` : "";
        lyr.bindPopup(
          `<b>cluster ${{p.cluster_id}}</b><br/>` +
          `role: ${{p.role}}${{also}}<br/>` +
          `${{p.n_nodes}} node(s)<br/>eid: ${{p.eid}}`
        );
      }},
    }});

    // Default: both on
    boxes.addTo(map);
    segs.addTo(map);

    L.control.layers(
      {{ "OSM": osm }},
      {{ "Cluster boxes": boxes, "Cluster segments": segs }},
      {{ collapsed: false }}
    ).addTo(map);

    try {{
      map.fitBounds(segs.getBounds(), {{ padding: [24, 24], maxZoom: 14 }});
    }} catch (e) {{
      try {{ map.fitBounds(boxes.getBounds(), {{ padding: [24, 24], maxZoom: 14 }}); }} catch (e2) {{}}
    }}
  </script>
</body>
</html>
"""

    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(html, encoding="utf-8")
    mb = OUT_HTML.stat().st_size / (1024 * 1024)
    print(f"Wrote {OUT_HTML} ({mb:.1f} MB)")
    print(
        f"  formula={formula} clusters={n_clusters:,} nodes={n_nodes:,} "
        f"bboxes={len(bbox_features):,} segs={len(seg_features):,}"
    )
    print(f"  role_counts={dict(role_counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
