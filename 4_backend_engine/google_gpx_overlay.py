"""Leaflet overlay: Google GPX on top of Fast / Safe / Leisure."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path


def write_debug_html(
    out_path: Path,
    *,
    title: str,
    note: str = "",
    stats: list[str] | None = None,
    layers: list[dict],
) -> Path:
    """Minimal Leaflet debug map. Each layer: name, color, weight, pts, optional dash/on."""
    payload = {
        "title": title,
        "note": note,
        "stats": stats or [],
        "layers": [
            {
                "name": layer["name"],
                "color": layer["color"],
                "weight": int(layer.get("weight") or 5),
                "dash": layer.get("dash") or "",
                "on": bool(layer.get("on", True)),
                "pts": layer.get("pts") or [],
            }
            for layer in layers
        ],
    }
    safe_title = title.replace("&", "and")
    html = _DEBUG_HTML.replace("__TITLE__", safe_title).replace(
        "__PAYLOAD__", json.dumps(payload, separators=(",", ":"))
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path


def write_overlay_html(
    out_path: Path,
    *,
    title: str,
    gpx: list[list[float]],
    snapped: list[list[float]] | None,
    fast: list[list[float]] | None,
    safe: list[list[float]] | None,
    leisure: list[list[float]] | None,
    meta: dict | None = None,
) -> Path:
    payload = {
        "title": title,
        "meta": meta or {},
        "gpx": gpx or [],
        "snapped": snapped or [],
        "fast": fast or [],
        "safe": safe or [],
        "leisure": leisure or [],
    }
    safe_title = title.replace("&", "and")
    html = _HTML.replace("__TITLE__", safe_title).replace(
        "__PAYLOAD__", json.dumps(payload, separators=(",", ":"))
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return out_path


def extract_payload(html: str) -> dict | None:
    key = "const data = "
    idx = html.find(key)
    if idx >= 0:
        blob = html[idx + len(key) :]
        try:
            data, _end = json.JSONDecoder().raw_decode(blob)
            return data
        except json.JSONDecodeError:
            pass
    marker = '<script type="application/json" id="route-data">'
    start = html.find(marker)
    if start >= 0:
        start += len(marker)
        end = html.find("</script>", start)
        if end > start:
            return json.loads(html[start:end])
    return None


def gpx_latlon(path: Path) -> list[list[float]]:
    pts: list[list[float]] = []
    for el in ET.parse(path).getroot().iter():
        if el.tag.rsplit("}", 1)[-1] != "trkpt":
            continue
        pts.append([float(el.attrib["lat"]), float(el.attrib["lon"])])
    return pts


def notes_meta(path: Path) -> dict:
    meta: dict = {}
    if not path.is_file():
        return meta
    for raw in path.read_text(encoding="utf-8").splitlines():
        if ":" not in raw or raw.strip().startswith("#"):
            continue
        k, v = raw.split(":", 1)
        k, v = k.strip(), v.strip()
        if not v:
            continue
        if k == "google_duration_min":
            meta["maps_min"] = float(v)
        elif k == "google_distance_km":
            meta["maps_km"] = float(v)
        elif k == "via":
            meta["via"] = v
    return meta


_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>__TITLE__</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    html, body { margin: 0; height: 100%; width: 100%; }
    #map { position: absolute; top: 0; right: 0; bottom: 0; left: 0; z-index: 0; }
    .panel {
      position: absolute; z-index: 1000; top: 12px; left: 12px;
      background: rgba(255,255,255,0.95); padding: 12px 14px; border-radius: 8px;
      box-shadow: 0 2px 12px rgba(0,0,0,0.18); max-width: 340px; font-size: 13px;
      line-height: 1.4; max-height: calc(100% - 24px); overflow: auto;
    }
    .panel h1 { margin: 0 0 6px; font-size: 15px; }
    .muted { color: #64748b; font-size: 12px; }
    .row { display: flex; align-items: center; gap: 8px; margin: 5px 0; }
    .swatch { width: 18px; height: 4px; border-radius: 2px; flex: 0 0 18px; }
    .swatch.dash { background: repeating-linear-gradient(90deg,#6b7280 0 6px,transparent 6px 10px); height: 3px; }
    label { cursor: pointer; user-select: none; }
  </style>
</head>
<body>
  <div class="panel">
    <h1 id="heading"></h1>
    <div class="muted" id="meta"></div>
    <div class="muted" style="margin:8px 0 4px">Magenta Google GPX is on top. Uncheck the others to isolate it.</div>
    <div id="toggles"></div>
  </div>
  <div id="map"></div>
  <script type="application/json" id="route-data">__PAYLOAD__</script>
  <script>
    const data = JSON.parse(document.getElementById("route-data").textContent);
    document.title = data.title || "Google vs presets";
    document.getElementById("heading").textContent = data.title || "Google vs presets";
    const m = data.meta || {};
    const bits = [];
    if (m.maps_km != null && m.maps_km !== "") bits.push(m.maps_km + " km");
    if (m.maps_min != null && m.maps_min !== "") bits.push(m.maps_min + " min Maps");
    if (m.gpx_m != null) bits.push("GPX " + Math.round(m.gpx_m) + " m");
    if (m.via) bits.push("via " + m.via);
    document.getElementById("meta").textContent = bits.join(" · ");

    const map = L.map("map").setView([51.5074, -0.1278], 13);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap"
    }).addTo(map);

    const spec = [
      { key: "leisure", name: "Leisure", color: "#16a34a", weight: 5 },
      { key: "safe", name: "Safe", color: "#2563eb", weight: 5 },
      { key: "fast", name: "Fast", color: "#f59e0b", weight: 5 },
      { key: "snapped", name: "Google snapped (graph)", color: "#4b5563", weight: 4, dash: "7 7" },
      { key: "gpx", name: "Google GPX", color: "#ff0061", weight: 5 },
    ];

    const layers = {};
    const bounds = L.latLngBounds([]);

    spec.forEach((s) => {
      const pts = data[s.key] || [];
      pts.forEach((p) => {
        if (Array.isArray(p) && p.length >= 2) bounds.extend(L.latLng(p[0], p[1]));
      });
      const opts = {
        color: s.color,
        weight: s.weight,
        opacity: 1,
        lineJoin: "round",
        lineCap: "round",
      };
      if (s.dash) opts.dashArray = s.dash;
      const group = L.layerGroup();
      if (pts.length >= 2) {
        L.polyline(pts, opts).addTo(group);
      }
      layers[s.key] = group;
      group.addTo(map);
    });

    const gpx = data.gpx || [];
    if (gpx.length) {
      L.circleMarker(gpx[0], {
        radius: 8, color: "#111", fillColor: "#22c55e", fillOpacity: 1, weight: 2
      }).addTo(map);
      L.circleMarker(gpx[gpx.length - 1], {
        radius: 8, color: "#111", fillColor: "#ef4444", fillOpacity: 1, weight: 2
      }).addTo(map);
    }

    const box = document.getElementById("toggles");
    spec.forEach((s) => {
      const n = (data[s.key] || []).length;
      const row = document.createElement("div");
      row.className = "row";
      const sw = document.createElement("span");
      sw.className = "swatch" + (s.dash ? " dash" : "");
      if (!s.dash) sw.style.background = s.color;
      const lab = document.createElement("label");
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = true;
      cb.addEventListener("change", () => {
        if (cb.checked) layers[s.key].addTo(map);
        else map.removeLayer(layers[s.key]);
      });
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(" " + s.name + " (" + n + " pts)"));
      row.appendChild(sw);
      row.appendChild(lab);
      box.appendChild(row);
    });

    map.whenReady(function () {
      map.invalidateSize();
      if (bounds.isValid()) {
        map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
      }
    });
  </script>
</body>
</html>
"""

_DEBUG_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>__TITLE__</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    html, body { margin: 0; height: 100%; width: 100%; }
    #map { position: absolute; top: 0; right: 0; bottom: 0; left: 0; z-index: 0; }
    .panel {
      position: absolute; z-index: 1000; top: 12px; left: 12px;
      background: rgba(255,255,255,0.95); padding: 12px 14px; border-radius: 8px;
      box-shadow: 0 2px 12px rgba(0,0,0,0.18); max-width: 380px; font-size: 13px;
      line-height: 1.4; max-height: calc(100% - 24px); overflow: auto;
    }
    .panel h1 { margin: 0 0 6px; font-size: 15px; }
    .muted { color: #64748b; font-size: 12px; }
    .row { display: flex; align-items: center; gap: 8px; margin: 5px 0; }
    .swatch { width: 18px; height: 4px; border-radius: 2px; flex: 0 0 18px; }
    .swatch.dash { background: repeating-linear-gradient(90deg,#6b7280 0 6px,transparent 6px 10px); height: 3px; }
    label { cursor: pointer; user-select: none; }
    .stats { margin-top: 8px; font-family: ui-monospace, monospace; font-size: 11px;
      white-space: pre-wrap; }
  </style>
</head>
<body>
  <div class="panel">
    <h1 id="heading"></h1>
    <div class="muted" id="note"></div>
    <div id="toggles"></div>
    <div class="stats" id="stats"></div>
  </div>
  <div id="map"></div>
  <script type="application/json" id="route-data">__PAYLOAD__</script>
  <script>
    const data = JSON.parse(document.getElementById("route-data").textContent);
    document.title = data.title || "debug";
    document.getElementById("heading").textContent = data.title || "debug";
    document.getElementById("note").textContent = data.note || "";
    document.getElementById("stats").textContent = (data.stats || []).join("\n");

    const map = L.map("map").setView([51.5074, -0.1278], 13);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap"
    }).addTo(map);

    const layers = {};
    const bounds = L.latLngBounds([]);
    (data.layers || []).forEach((s, idx) => {
      const pts = s.pts || [];
      pts.forEach((p) => {
        if (Array.isArray(p) && p.length >= 2) bounds.extend(L.latLng(p[0], p[1]));
      });
      const opts = {
        color: s.color,
        weight: s.weight,
        opacity: 1,
        lineJoin: "round",
        lineCap: "round",
      };
      if (s.dash) opts.dashArray = s.dash;
      const group = L.layerGroup();
      if (pts.length >= 2) L.polyline(pts, opts).addTo(group);
      layers[idx] = group;
      if (s.on !== false) group.addTo(map);

      const row = document.createElement("div");
      row.className = "row";
      const sw = document.createElement("span");
      sw.className = "swatch" + (s.dash ? " dash" : "");
      if (!s.dash) sw.style.background = s.color;
      const lab = document.createElement("label");
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = s.on !== false;
      cb.addEventListener("change", () => {
        if (cb.checked) layers[idx].addTo(map);
        else map.removeLayer(layers[idx]);
      });
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(" " + s.name + " (" + pts.length + " pts)"));
      row.appendChild(sw);
      row.appendChild(lab);
      document.getElementById("toggles").appendChild(row);
    });

    const firstOn = (data.layers || []).find((s) => s.on !== false && (s.pts || []).length);
    const gpx = firstOn ? firstOn.pts : [];
    if (gpx.length) {
      L.circleMarker(gpx[0], {
        radius: 8, color: "#111", fillColor: "#22c55e", fillOpacity: 1, weight: 2
      }).addTo(map);
      L.circleMarker(gpx[gpx.length - 1], {
        radius: 8, color: "#111", fillColor: "#ef4444", fillOpacity: 1, weight: 2
      }).addTo(map);
    }

    map.whenReady(function () {
      map.invalidateSize();
      if (bounds.isValid()) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
    });
  </script>
</body>
</html>
"""
