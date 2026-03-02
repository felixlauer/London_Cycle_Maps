"""
Tag graph edges with TfL cycle route data (Cycleways, Quietways, Cycle Superhighways).
Reads: 1_data/tfl_raw/routes/Cycle_routes.json (GeoJSON)
Reads: 1_data/london_elev_final.graphml (or --input path)
Writes: new graph with _tfl before .graphml and edge attributes tfl_cycle_programme, tfl_cycle_route.

Strategy (avoid over-tagging, fill gaps where OSM has no cycleway tags):
- TfL data: one feature per route (e.g. C40), geometry = MultiLineString. We explode to segments; same route can have many segments.
- Pass 1 (strict): only cycle infrastructure (highway=cycleway or cycleway* tags), excluding footway/pedestrian/steps. Alignment: >=50% of edge length in corridor; angularity: edge must be roughly parallel to TfL segment (rejects perpendicular crossings/side streets).
- Coverage: target matched length >= 1.8× segment length (one-way); cap at 3× so we don't over-tag. Iterative relaxed pass(es) until all segments reach >= 1.8× or no progress.
- Angularity only for very short edges (<20 m); longer edges skip angular check to avoid dropping valid segments.
- Relaxed pass: for segments still under 1.8×, consider non-cycle edges (excluding motorway/trunk/pedestrian); cap so no segment exceeds 3×.
- Debug: print TfL network length vs identified length (and ratio vs 2× one-way).

When changing inputs or tag names, update 0_documentation/GRAPH.md (TfL section).
"""
import json
import math
import os
import argparse
import networkx as nx
from shapely.wkt import loads as wkt_loads
from shapely.geometry import LineString
from shapely.strtree import STRtree

# --- CONFIGURATION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "1_data")
TFL_ROUTES_PATH = os.path.join(DATA_DIR, "tfl_raw", "routes", "Cycle_routes.json")
DEFAULT_INPUT_GRAPH = os.path.join(DATA_DIR, "london_elev_final.graphml")

# Corridor width: ~10m at London (~51.5°N). Smaller = stricter, fewer false matches.
BUFFER_DEGREES = 0.0001
# Fraction of edge length that must lie inside the TfL corridor to tag (0.5 = 50%). Side streets have low ratio.
ALIGNMENT_THRESHOLD = 0.5
# Reject edges that are not roughly parallel to the TfL segment (e.g. perpendicular crossings). Max angle (deg) from parallel.
MAX_ANGLE_DEG = 45.0
# Per-segment coverage: keep adding (relaxed pass) until matched >= TARGET_RATIO * segment_length (one-way).
TARGET_RATIO = 1.8  # matched_length >= 1.8 * segment_length
# Cap: do not add edges that would push segment matched length over CAP_RATIO * segment_length (avoid over-tagging).
CAP_RATIO = 3.0
# Angularity check only for short edges (length < this in metres); longer edges are assumed aligned.
ANGULAR_MAX_LENGTH_M = 20.0
# Approximate degrees to km for debug (at London latitude).
DEG_TO_KM = 111.0

# Edge types we never consider as cycle infrastructure (pedestrian-only).
EXCLUDE_PEDESTRIAN = ("footway", "pedestrian", "steps")
# For relaxed pass: exclude these from the wider candidate set (motorways/trunks stay excluded).
EXCLUDE_RELAXED = ("motorway", "motorway_link", "trunk", "trunk_link", "footway", "pedestrian", "steps")

# Programme (from TfL) -> short tag for graph
PROGRAMME_TO_TAG = {
    "Cycleways": "cycleway",
    "Quietways": "quietway",
    "Cycle Superhighways": "superhighway",
}


def is_cycle_infrastructure(data):
    """True if edge is a cycleway or has cycleway infrastructure. Excludes pedestrian-only and plain roads."""
    t = str(data.get("type", "")).strip().lower()
    if t in EXCLUDE_PEDESTRIAN:
        return False
    if t == "cycleway":
        return True
    for k in ("cycleway", "cycleway_left", "cycleway_right", "cycleway_both"):
        if str(data.get(k, "")).strip():
            return True
    return False


def is_relaxed_candidate(data):
    """True if edge has geometry and is not motorway/trunk/pedestrian-only. Used for under-covered segment fallback."""
    t = str(data.get("type", "")).strip().lower()
    if t in EXCLUDE_RELAXED:
        return False
    return True


def angle_deg_between_lines(line_a, line_b):
    """Angle in [0, 180] between the directions of two LineStrings (first-to-last bearing)."""
    coords_a = list(line_a.coords)
    coords_b = list(line_b.coords)
    if len(coords_a) < 2 or len(coords_b) < 2:
        return 0.0
    dx_a = coords_a[-1][0] - coords_a[0][0]
    dy_a = coords_a[-1][1] - coords_a[0][1]
    dx_b = coords_b[-1][0] - coords_b[0][0]
    dy_b = coords_b[-1][1] - coords_b[0][1]
    len_a = math.hypot(dx_a, dy_a)
    len_b = math.hypot(dx_b, dy_b)
    if len_a < 1e-12 or len_b < 1e-12:
        return 0.0
    dot = dx_a * dx_b + dy_a * dy_b
    cos_a = dot / (len_a * len_b)
    cos_a = max(-1.0, min(1.0, cos_a))
    return math.degrees(math.acos(cos_a))


def is_roughly_parallel(edge_geom, tfl_line, max_angle_deg=MAX_ANGLE_DEG):
    """True if edge direction is within max_angle_deg of parallel or anti-parallel to TfL segment."""
    angle = angle_deg_between_lines(edge_geom, tfl_line)
    dev = min(angle, 180.0 - angle)
    return dev <= max_angle_deg


def _length_m_float(data):
    """Edge length in metres from graph data (GraphML may store as string)."""
    try:
        return float(data.get("length") or 0)
    except (TypeError, ValueError):
        return 0.0


def passes_angular_if_needed(edge_geom, tfl_line, length_m):
    """Apply angularity check only for short edges (< ANGULAR_MAX_LENGTH_M). Long edges are accepted."""
    try:
        m = float(length_m) if length_m is not None else 0.0
    except (TypeError, ValueError):
        m = 0.0
    if m >= ANGULAR_MAX_LENGTH_M:
        return True
    return is_roughly_parallel(edge_geom, tfl_line)


def load_tfl_segments(path):
    """Load TfL GeoJSON and return list of (programme_tag, label, Shapely LineString)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    features = data.get("features", [])
    segments = []
    for feat in features:
        props = feat.get("properties", {})
        programme = (props.get("Programme") or "").strip()
        label = (props.get("Label") or "").strip()
        if not programme or programme not in PROGRAMME_TO_TAG:
            continue
        tag = PROGRAMME_TO_TAG[programme]
        geom = feat.get("geometry")
        if not geom or geom.get("type") != "MultiLineString":
            continue
        coords_list = geom.get("coordinates", [])
        for coords in coords_list:
            if len(coords) < 2:
                continue
            # GeoJSON: [lon, lat]
            line = LineString([(c[0], c[1]) for c in coords])
            if line.is_empty:
                continue
            segments.append((tag, label, line))
    return segments


def main():
    parser = argparse.ArgumentParser(description="Tag graph edges with TfL cycle routes")
    parser.add_argument("--input", default=DEFAULT_INPUT_GRAPH, help="Input GraphML path")
    parser.add_argument("--output", default=None, help="Output GraphML path (default: input name with _tfl before .graphml)")
    parser.add_argument("--tfl", default=TFL_ROUTES_PATH, help="TfL Cycle_routes.json path")
    args = parser.parse_args()
    input_path = os.path.normpath(os.path.join(SCRIPT_DIR, args.input))
    if args.output:
        output_path = os.path.normpath(os.path.join(SCRIPT_DIR, args.output))
    else:
        base, ext = os.path.splitext(input_path)
        output_path = base + "_tfl" + ext
    tfl_path = os.path.normpath(os.path.join(SCRIPT_DIR, args.tfl))

    if not os.path.isfile(tfl_path):
        print(f"ERROR: TfL routes file not found: {tfl_path}")
        return 1
    if not os.path.isfile(input_path):
        print(f"ERROR: Graph not found: {input_path}")
        return 1

    print("--- TfL CYCLE ROUTE TAGGING ---")
    print(f"1. Loading TfL routes from {tfl_path}...")
    tfl_segments = load_tfl_segments(tfl_path)
    print(f"   -> {len(tfl_segments)} TfL segment lines loaded.")

    print(f"2. Loading graph from {input_path}...")
    G = nx.read_graphml(input_path)
    n_edges = G.number_of_edges()
    print(f"   -> {G.number_of_nodes()} nodes, {n_edges} edges.")

    def _coverage_debug(segment_matched_length, tfl_segments, label_prefix="   "):
        total_tfl_deg = sum(tfl_segments[k][2].length for k in range(len(tfl_segments)))
        total_matched_deg = sum(segment_matched_length)
        total_tfl_km = total_tfl_deg * DEG_TO_KM
        total_matched_km = total_matched_deg * DEG_TO_KM
        two_way_tfl_km = 2.0 * total_tfl_km
        ratio_oneway = total_matched_deg / total_tfl_deg if total_tfl_deg > 1e-12 else 0.0
        ratio_twoway = total_matched_km / two_way_tfl_km if two_way_tfl_km > 1e-9 else 0.0
        print(f"{label_prefix}TfL network (one-way): {total_tfl_km:.2f} km. Matched: {total_matched_km:.2f} km.")
        print(f"{label_prefix}Ratio matched/one-way: {ratio_oneway:.3f}. Ratio matched/(2×one-way): {ratio_twoway:.3f}.")

    print("3. Building spatial index of cycle-infrastructure edges only...")
    edge_list = []  # [(u, v, geom, length_m), ...]
    for u, v, data in G.edges(data=True):
        if not is_cycle_infrastructure(data):
            continue
        wkt = data.get("geometry")
        if not wkt or not str(wkt).strip():
            continue
        try:
            geom = wkt_loads(str(wkt))
            if geom.is_empty:
                continue
            length_m = _length_m_float(data)
            edge_list.append((u, v, geom, length_m))
        except Exception:
            continue
    geoms = [e[2] for e in edge_list]
    tree = STRtree(geoms)
    print(f"   -> Indexed {len(edge_list)} cycle-infrastructure edges (of {n_edges} total).")

    print("4. Pass 1: matching TfL segments to cycle-infrastructure edges (alignment; angularity only for edges <20 m)...")
    from collections import defaultdict
    edge_tags = defaultdict(set)
    segment_matched_length = [0.0] * len(tfl_segments)
    segment_edges = [set() for _ in tfl_segments]  # segment_edges[i] = set of (u,v) already counted for segment i
    for i, (tag, label, tfl_line) in enumerate(tfl_segments):
        buf = tfl_line.buffer(BUFFER_DEGREES)
        idx = tree.query(buf)
        try:
            indices = list(idx)
        except TypeError:
            indices = [idx]
        for j in indices:
            u, v, edge_geom, length_m = edge_list[j]
            edge_len = edge_geom.length
            if edge_len < 1e-12:
                continue
            if not passes_angular_if_needed(edge_geom, tfl_line, length_m):
                continue
            try:
                overlap = edge_geom.intersection(buf)
                overlap_len = overlap.length if overlap else 0.0
            except Exception:
                overlap_len = 0.0
            ratio = overlap_len / edge_len
            if ratio >= ALIGNMENT_THRESHOLD:
                edge_tags[(u, v)].add((tag, label))
                segment_matched_length[i] += overlap_len
                segment_edges[i].add((u, v))
        if (i + 1) % 500 == 0:
            print(f"   -> Processed {i + 1}/{len(tfl_segments)} TfL segments...")
    print("   Coverage after Pass 1:")
    _coverage_debug(segment_matched_length, tfl_segments)

    # Under-covered: matched < TARGET_RATIO * segment_length (one-way). Iterate until all >= 1.8× or no progress.
    under_covered = []
    for i in range(len(tfl_segments)):
        seg_len = tfl_segments[i][2].length
        if seg_len < 1e-12:
            continue
        if segment_matched_length[i] < TARGET_RATIO * seg_len:
            under_covered.append(i)
    print(f"   -> {len(under_covered)} segments under {TARGET_RATIO}× (will try relaxed edge set in loop).")

    # Iterative relaxed pass: keep adding until all segments >= 1.8× or no progress; cap at 3× per segment
    if under_covered:
        print("5. Building spatial index of relaxed edges...")
        relaxed_list = []  # [(u, v, geom, length_m), ...]
        for u, v, data in G.edges(data=True):
            if not is_relaxed_candidate(data):
                continue
            wkt = data.get("geometry")
            if not wkt or not str(wkt).strip():
                continue
            try:
                geom = wkt_loads(str(wkt))
                if geom.is_empty:
                    continue
                length_m = _length_m_float(data)
                relaxed_list.append((u, v, geom, length_m))
            except Exception:
                continue
        relaxed_geoms = [e[2] for e in relaxed_list]
        relaxed_tree = STRtree(relaxed_geoms)
        print(f"   -> Indexed {len(relaxed_list)} relaxed edges.")
        iteration = 0
        while under_covered:
            iteration += 1
            added_any = False
            for idx_seg in under_covered:
                tag, label, tfl_line = tfl_segments[idx_seg]
                seg_len = tfl_line.length
                if seg_len < 1e-12:
                    continue
                if segment_matched_length[idx_seg] >= CAP_RATIO * seg_len:
                    continue  # already at cap, skip
                buf = tfl_line.buffer(BUFFER_DEGREES)
                idx = relaxed_tree.query(buf)
                try:
                    indices = list(idx)
                except TypeError:
                    indices = [idx]
                for j in indices:
                    u, v, edge_geom, length_m = relaxed_list[j]
                    if (u, v) in segment_edges[idx_seg]:
                        continue
                    edge_len = edge_geom.length
                    if edge_len < 1e-12:
                        continue
                    if not passes_angular_if_needed(edge_geom, tfl_line, length_m):
                        continue
                    try:
                        overlap = edge_geom.intersection(buf)
                        overlap_len = overlap.length if overlap else 0.0
                    except Exception:
                        overlap_len = 0.0
                    ratio = overlap_len / edge_len
                    if ratio < ALIGNMENT_THRESHOLD:
                        continue
                    cap_limit = CAP_RATIO * seg_len
                    if segment_matched_length[idx_seg] + overlap_len > cap_limit:
                        continue
                    edge_tags[(u, v)].add((tag, label))
                    segment_matched_length[idx_seg] += overlap_len
                    segment_edges[idx_seg].add((u, v))
                    added_any = True
            under_covered = []
            for i in range(len(tfl_segments)):
                seg_len = tfl_segments[i][2].length
                if seg_len < 1e-12:
                    continue
                if segment_matched_length[i] < TARGET_RATIO * seg_len:
                    under_covered.append(i)
            if not added_any:
                break
            print(f"   Relaxed iteration {iteration}: {len(under_covered)} segments still under {TARGET_RATIO}×.")
        print(f"   Relaxed pass finished after {iteration} iteration(s).")
        print("   Coverage after relaxed pass(es):")
        _coverage_debug(segment_matched_length, tfl_segments)
    else:
        print("5. No under-covered segments; skipping relaxed pass.")

    print("7. Writing tags to graph edges...")
    tagged = 0
    for u, v, data in G.edges(data=True):
        pairs = edge_tags.get((u, v), set())
        if pairs:
            programmes = sorted(set(p for p, _ in pairs))
            labels = sorted(set(l for _, l in pairs))
            data["tfl_cycle_programme"] = ";".join(programmes)
            data["tfl_cycle_route"] = ";".join(labels)
            tagged += 1
        else:
            data["tfl_cycle_programme"] = ""
            data["tfl_cycle_route"] = ""

    print(f"   -> Tagged {tagged} edges with TfL routes.")

    print(f"8. Saving graph to {output_path}...")
    nx.write_graphml(G, output_path)
    print("SUCCESS! TfL cycle route tags added (tfl_cycle_programme, tfl_cycle_route).")
    return 0


if __name__ == "__main__":
    exit(main())
