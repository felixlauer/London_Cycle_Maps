"""
Cycleway infrastructure clusters for the debug overlay.

Classifies meaningful cycleway* tag values (see cost_function_tags_and_modes.md Appendix A).
Excludes negatives and non-infrastructure values (no, crossing, sidewalk, opposite, …).
Does NOT use OSM segregated=yes — that tag often means a parallel facility exists elsewhere.

Clusters:
  1 segregated  — track, separate, sidepath; highway type=cycleway
  2 bus_shared  — share_busway (bus lane, not general car traffic)
  3 car_shared  — lane, shared_lane, shared, advisory, opposite_lane
"""
from __future__ import annotations

CLUSTER_SEGREGATED = 1
CLUSTER_BUS_SHARED = 2
CLUSTER_CAR_SHARED = 3

CLUSTER_KEYS = {
    CLUSTER_SEGREGATED: "segregated",
    CLUSTER_BUS_SHARED: "bus_shared",
    CLUSTER_CAR_SHARED: "car_shared",
}

CLUSTER_LABELS = {
    CLUSTER_SEGREGATED: "Segregated / track",
    CLUSTER_BUS_SHARED: "Bus lane shared",
    CLUSTER_CAR_SHARED: "Car lane shared",
}

CLUSTER_COLORS = {
    CLUSTER_SEGREGATED: "#1B5E20",
    CLUSTER_BUS_SHARED: "#00838F",
    CLUSTER_CAR_SHARED: "#EF6C00",
}

CYCLEWAY_TAG_KEYS = ("cycleway", "cycleway_left", "cycleway_right", "cycleway_both")

# Not meaningful on-edge cycle infrastructure (cost doc: cycleway=no is 14–89% of tagged edges).
_EXCLUDED_VALUES = frozenset({
    "",
    "none",
    "nan",
    "no",
    "nolane",
    "n",
    "bo",
    "crossing",
    "traffic_island",
    "link",
    "sidewalk",
    "dismount",
    "asphalt",
    "paving_stones",
    "segregated",
    "customers",
    "shoulder",
    "right",
    "left",
    "sideway",
    "cycleway",
    "opposite",
    "m",
    "yes",
    "2",
    "separateanes=2",
    "sseparate",
    "lne",
})

_SEGREGATED_VALUES = frozenset({
    "track",
    "separate",
    "separate track",
    "sidepath",
})

_BUS_SHARED_VALUES = frozenset({
    "share_busway",
})

_CAR_SHARED_VALUES = frozenset({
    "lane",
    "shared_lane",
    "shared",
    "advisory",
    "opposite_lane",
    "permissive",
})

_CLUSTER_BY_VALUE = {
    **{v: CLUSTER_SEGREGATED for v in _SEGREGATED_VALUES},
    **{v: CLUSTER_BUS_SHARED for v in _BUS_SHARED_VALUES},
    **{v: CLUSTER_CAR_SHARED for v in _CAR_SHARED_VALUES},
}

# Best (most segregated) wins when multiple tags are present on one edge.
_CLUSTER_PRIORITY = (
    CLUSTER_SEGREGATED,
    CLUSTER_BUS_SHARED,
    CLUSTER_CAR_SHARED,
)


def _norm_val(val) -> str:
    return str(val or "").strip().lower()


def _classify_value(val: str) -> int | None:
    if not val or val in _EXCLUDED_VALUES:
        return None
    return _CLUSTER_BY_VALUE.get(val)


def classify_cycleway_edge(edge_data: dict) -> dict | None:
    """
    Return overlay metadata for this directed edge, or None if no meaningful cycle infra.
    """
    best_cluster = None
    best_tag = ""
    best_key = ""

    if _norm_val(edge_data.get("type")) == "cycleway":
        best_cluster = CLUSTER_SEGREGATED
        best_tag = "highway:cycleway"
        best_key = "type"

    for key in CYCLEWAY_TAG_KEYS:
        val = _norm_val(edge_data.get(key))
        cluster = _classify_value(val)
        if cluster is None:
            continue
        if best_cluster is None:
            best_cluster = cluster
            best_tag = val
            best_key = key
            continue
        if _CLUSTER_PRIORITY.index(cluster) < _CLUSTER_PRIORITY.index(best_cluster):
            best_cluster = cluster
            best_tag = val
            best_key = key

    if best_cluster is None:
        return None

    return {
        "cluster": best_cluster,
        "cluster_key": CLUSTER_KEYS[best_cluster],
        "cluster_label": CLUSTER_LABELS[best_cluster],
        "cluster_color": CLUSTER_COLORS[best_cluster],
        "tag": best_tag,
        "tag_key": best_key,
    }


def cluster_legend() -> list[dict]:
    return [
        {
            "cluster": CLUSTER_KEYS[c],
            "label": CLUSTER_LABELS[c],
            "color": CLUSTER_COLORS[c],
        }
        for c in _CLUSTER_PRIORITY
    ]
