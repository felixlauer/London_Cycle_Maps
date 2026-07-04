"""
Generate dependency-matrix visualizations from weight_dependencies JSON.

Run from repo root:
  python 4_backend_engine/weight_dependencies/visualizations/generate_plots.py

Outputs PNG and interactive HTML files in this directory (visualizations/).
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import networkx as nx
import numpy as np
import plotly.graph_objects as go

HERE = Path(__file__).resolve().parent
DEPS = HERE.parent
OUT = HERE

WSE_PATH = DEPS / "weight_stat_effects.json"
WC_PATH = DEPS / "weight_couplings.json"
MECH_PATH = DEPS / "mechanisms.json"

HTML_CONFIG = {"displayModeBar": True, "scrollZoom": True}

MODES = ("fast", "safe", "leisure")
MODE_LABELS = {"fast": "Fast", "safe": "Safe", "leisure": "Leisure"}

# Friendly short labels for plots
SHORT = {
    "signal_weight": "Traffic lights",
    "speed_weight": "Fast traffic",
    "junction_weight": "Junctions",
    "risk_weight": "Safety",
    "hill_weight": "Hills",
    "light_weight": "Lighting",
    "calming_weight": "Speed bumps",
    "barrier_weight": "Barriers",
    "green_weight": "Green / scenic",
    "surface_weight": "Smooth surface",
    "tfl_cycleway_weight": "TfL cycleways",
    "tfl_quietway_weight": "TfL quietways",
    "vehicular_free_weight": "Car-free",
    "tfl_live_weight": "Live disruptions",
    "width_weight": "Path width",
}


def _load() -> tuple[dict, dict, dict]:
    wse = json.loads(WSE_PATH.read_text(encoding="utf-8"))
    wc = json.loads(WC_PATH.read_text(encoding="utf-8"))
    mech = json.loads(MECH_PATH.read_text(encoding="utf-8"))
    return wse, wc, mech


def _short(weight_key: str) -> str:
    return SHORT.get(weight_key, weight_key.replace("_weight", ""))


def _write_html(fig: go.Figure, path: Path) -> Path:
    fig.write_html(
        path,
        include_plotlyjs="cdn",
        full_html=True,
        config=HTML_CONFIG,
    )
    return path


def _mode_dominant(coupling: dict, mode: str) -> str | None:
    md = coupling.get("mode_dominant") or {}
    dom = md.get(mode)
    if dom and dom in coupling.get("weights", []):
        return dom
    return None


def _radial_layout(weights: list[str], conflict_degree: dict[str, int]) -> dict[str, np.ndarray]:
    """Fixed node positions — independent of which edges exist (stable across modes)."""
    pos: dict[str, np.ndarray] = {}
    if "risk_weight" in weights:
        pos["risk_weight"] = np.array([0.0, 0.0])
    for w in weights:
        if w == "risk_weight":
            continue
        angle = hash(w) % 360
        r = 1.2 + 0.15 * conflict_degree.get(w, 0)
        pos[w] = np.array([
            r * np.cos(np.radians(angle)),
            r * np.sin(np.radians(angle)),
        ])
    return pos


def _build_coupling_graph(
    wse: dict,
    wc: dict,
    mode: str,
    layout_degree: dict[str, int] | None = None,
) -> tuple[nx.DiGraph, dict, dict[str, int], list[str]]:
    """Build directed graph, layout positions, and conflict counts for one preset mode."""
    weights = list(wse["weights"].keys())
    G = nx.DiGraph()
    G.add_nodes_from(weights)

    conflict_degree: dict[str, int] = {w: 0 for w in weights}
    drawn_undirected: set[tuple[str, str]] = set()

    for c in wc["couplings"]:
        wts = c["weights"]
        if len(wts) != 2:
            continue
        a, b = wts
        ctype = c["type"]

        if ctype in ("antagonistic", "floor"):
            conflict_degree[a] += 1
            conflict_degree[b] += 1
            dom = _mode_dominant(c, mode)
            if dom:
                sub = b if dom == a else a
                G.add_edge(sub, dom, coupling_id=c["id"], ctype=ctype, coupling=c)
            else:
                key = tuple(sorted(wts))
                if key not in drawn_undirected:
                    G.add_edge(a, b, coupling_id=c["id"], ctype=ctype, coupling=c)
                    G.add_edge(b, a, coupling_id=c["id"], ctype=ctype, coupling=c)
                    drawn_undirected.add(key)
        elif ctype in ("synergistic", "ui_merge"):
            key = tuple(sorted(wts))
            if key not in drawn_undirected:
                G.add_edge(a, b, coupling_id=c["id"], ctype=ctype, coupling=c)
                G.add_edge(b, a, coupling_id=c["id"], ctype=ctype, coupling=c)
                drawn_undirected.add(key)

    pos = _radial_layout(weights, layout_degree if layout_degree is not None else conflict_degree)
    return G, pos, conflict_degree, weights


def _max_conflict_degree(wse: dict, wc: dict) -> dict[str, int]:
    """Node size uses max conflict count across all modes."""
    merged: dict[str, int] = {w: 0 for w in wse["weights"]}
    for mode in MODES:
        _, _, deg, _ = _build_coupling_graph(wse, wc, mode)
        for w, n in deg.items():
            merged[w] = max(merged[w], n)
    return merged


def _draw_network_axes(ax, G: nx.DiGraph, pos: dict, conflict_degree: dict, weights: list[str], title: str) -> None:
    ax.set_title(title, fontsize=11, fontweight="bold", pad=8)
    ax.axis("off")

    sizes = [300 + 180 * conflict_degree.get(w, 0) for w in weights]
    node_colors = ["#3498db" if conflict_degree.get(w, 0) > 0 else "#bdc3c7" for w in weights]

    nx.draw_networkx_nodes(
        G, pos, nodelist=weights, node_size=sizes, node_color=node_colors,
        alpha=0.92, edgecolors="#2c3e50", linewidths=1.2, ax=ax,
    )

    for u, v, data in G.edges(data=True):
        ctype = data.get("ctype", "")
        if ctype == "synergistic":
            color, style, width = "#27ae60", "solid", 2.0
        elif ctype == "ui_merge":
            color, style, width = "#8e44ad", "dashed", 1.8
        else:
            color, style, width = "#c0392b", "solid", 1.5
        ax.annotate(
            "",
            xy=pos[v], xytext=pos[u],
            arrowprops=dict(
                arrowstyle="-|>", color=color, lw=width, linestyle=style,
                connectionstyle="arc3,rad=0.12", shrinkA=18, shrinkB=18,
            ),
        )

    nx.draw_networkx_labels(
        G, pos,
        labels={w: _short(w) for w in weights},
        font_size=6, font_weight="bold", ax=ax,
    )


def _distance_rows(wse: dict) -> list[dict]:
    rows = []
    for key, data in wse["weights"].items():
        if data["ui"].get("shape") == "hidden":
            continue
        de = data.get("distance_effects", {})
        explosions = de.get("distance_explosion_routes", [])
        max_expl = max((e.get("delta_km", 0) or 0 for e in explosions), default=0.0)
        max_shipped = max(
            (e.get("delta_km", 0) or 0 for e in explosions if "rejected" not in str(e.get("at", ""))),
            default=0.0,
        )
        agg_avg = de.get("aggressive_avg_delta_km") or 0.0
        mod_avg = de.get("moderate_avg_delta_km") or 0.0
        rows.append({
            "key": key,
            "label": _short(key),
            "max_explosion": max_expl,
            "max_shipped": max_shipped if max_shipped else agg_avg,
            "agg_avg": agg_avg,
            "mod_avg": mod_avg,
            "has_explosion": len(explosions) > 0,
        })
    rows.sort(key=lambda r: r["max_explosion"], reverse=True)
    return rows


def plot_network_graph(wse: dict, wc: dict) -> Path:
    """Web of conflict: one panel per preset mode (fast / safe / leisure)."""
    max_conflict = _max_conflict_degree(wse, wc)
    weights = list(wse["weights"].keys())

    fig, axes = plt.subplots(1, 3, figsize=(22, 8))
    fig.suptitle("Weight coupling network — Web of conflict (by preset mode)", fontsize=14, fontweight="bold", y=1.02)

    for ax, mode in zip(axes, MODES):
        G, pos, _, _ = _build_coupling_graph(wse, wc, mode, layout_degree=max_conflict)
        _draw_network_axes(ax, G, pos, max_conflict, weights, f"{MODE_LABELS[mode]} mode")

    legend_handles = [
        mpatches.Patch(color="#c0392b", label="Antagonistic / floor (arrow → mode winner)"),
        mpatches.Patch(color="#27ae60", label="Synergistic (bidirectional)"),
        mpatches.Patch(color="#8e44ad", label="UI merge (quietway → cycleway)"),
    ]
    fig.legend(handles=legend_handles, loc="lower center", ncol=3, fontsize=9, framealpha=0.95, bbox_to_anchor=(0.5, -0.02))

    out = OUT / "network_graph.png"
    fig.tight_layout()
    fig.savefig(out, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def _plotly_arrow(u: str, v: str, pos: dict, color: str, width: float) -> dict:
    """Plotly annotation: arrow from u (loser) toward v (mode winner)."""
    x0, y0 = float(pos[u][0]), float(pos[u][1])
    x1, y1 = float(pos[v][0]), float(pos[v][1])
    shrink = 0.10
    return dict(
        x=x1 - shrink * (x1 - x0),
        y=y1 - shrink * (y1 - y0),
        ax=x0 + shrink * (x1 - x0),
        ay=y0 + shrink * (y1 - y0),
        xref="x", yref="y", axref="x", ayref="y",
        showarrow=True, arrowhead=2, arrowsize=1.4, arrowwidth=width,
        arrowcolor=color, opacity=0.9,
    )


def _network_mode_traces(
    wse: dict,
    wc: dict,
    mode: str,
    pos: dict,
    max_conflict: dict[str, int],
    weights: list[str],
) -> tuple[list, list[dict]]:
    """Plotly edge traces + arrow annotations for one mode."""
    G, _, _, _ = _build_coupling_graph(wse, wc, mode, layout_degree=max_conflict)
    traces: list = []
    annotations: list[dict] = []

    edge_styles = {
        "antagonistic": ("#c0392b", "solid", 2),
        "floor": ("#c0392b", "solid", 2),
        "synergistic": ("#27ae60", "solid", 2.5),
        "ui_merge": ("#8e44ad", "dash", 2),
    }

    for ctype, (color, dash, width) in edge_styles.items():
        ex, ey = [], []
        for u, v, data in G.edges(data=True):
            if data.get("ctype") != ctype:
                continue
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            ex.extend([x0, x1, None])
            ey.extend([y0, y1, None])
            if ctype in ("antagonistic", "floor"):
                annotations.append(_plotly_arrow(u, v, pos, color, width))
        if ex:
            traces.append(go.Scatter(
                x=ex, y=ey, mode="lines",
                line=dict(color=color, width=width, dash=dash),
                hoverinfo="skip", showlegend=False,
            ))

    traces.append(go.Scatter(
        x=[pos[w][0] for w in weights],
        y=[pos[w][1] for w in weights],
        mode="markers+text",
        text=[_short(w) for w in weights],
        textposition="top center",
        textfont=dict(size=9, color="#2c3e50"),
        marker=dict(
            size=[14 + 4 * max_conflict.get(w, 0) for w in weights],
            color=["#3498db" if max_conflict.get(w, 0) else "#bdc3c7" for w in weights],
            line=dict(color="#2c3e50", width=1.5),
        ),
        customdata=[[w, max_conflict.get(w, 0)] for w in weights],
        hovertemplate=(
            "<b>%{text}</b><br>"
            "Key: %{customdata[0]}<br>"
            "Conflict count (max across modes): %{customdata[1]}<extra></extra>"
        ),
        showlegend=False,
    ))

    return traces, annotations


def plot_network_graph_html(wse: dict, wc: dict) -> Path:
    """Interactive network graph with mode dropdown (fast / safe / leisure)."""
    weights = list(wse["weights"].keys())
    max_conflict = _max_conflict_degree(wse, wc)
    pos = _radial_layout(weights, max_conflict)

    fig = go.Figure()
    mode_trace_ranges: dict[str, tuple[int, int]] = {}
    mode_annotations: dict[str, list[dict]] = {}
    legend_added = False

    for mode in MODES:
        start = len(fig.data)
        traces, annotations = _network_mode_traces(wse, wc, mode, pos, max_conflict, weights)
        for tr in traces:
            fig.add_trace(tr)
        mode_trace_ranges[mode] = (start, len(fig.data))
        mode_annotations[mode] = annotations

        if not legend_added:
            for label, color, dash in [
                ("Antagonistic / floor (arrow → mode winner)", "#c0392b", "solid"),
                ("Synergistic", "#27ae60", "solid"),
                ("UI merge", "#8e44ad", "dash"),
            ]:
                fig.add_trace(go.Scatter(
                    x=[None], y=[None], mode="lines",
                    line=dict(color=color, width=2, dash=dash),
                    name=label,
                ))
            legend_added = True

    n_traces = len(fig.data)
    default = "safe"

    def _visibility(active: str) -> list[bool]:
        vis = [False] * n_traces
        start, end = mode_trace_ranges[active]
        for i in range(start, end):
            vis[i] = True
        for i in range(n_traces - 3, n_traces):
            vis[i] = True
        return vis

    buttons = []
    for mode in MODES:
        buttons.append(dict(
            label=MODE_LABELS[mode],
            method="update",
            args=[
                {"visible": _visibility(mode)},
                {
                    "title": f"Weight coupling network — {MODE_LABELS[mode]} mode",
                    "annotations": mode_annotations[mode],
                },
            ],
        ))

    fig.update_layout(
        title=f"Weight coupling network — {MODE_LABELS[default]} mode",
        annotations=mode_annotations[default],
        updatemenus=[dict(
            type="dropdown", direction="down", x=0.01, y=1.12, xanchor="left", yanchor="top",
            buttons=buttons, showactive=True,
        )],
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, scaleanchor="x", scaleratio=1),
        plot_bgcolor="white",
        height=750,
        legend=dict(orientation="h", yanchor="bottom", y=-0.08, x=0),
    )
    fig.update_traces(visible=False)
    for i in range(*mode_trace_ranges[default]):
        fig.data[i].visible = True
    for i in range(n_traces - 3, n_traces):
        fig.data[i].visible = True

    return _write_html(fig, OUT / "network_graph.html")


def plot_distance_cost_matrix(wse: dict) -> Path:
    """Max detour km per weight — budget chart for Detour Budget Bar."""
    rows = _distance_rows(wse)
    labels = [r["label"] for r in rows]
    max_vals = [r["max_explosion"] for r in rows]
    shipped = [r["max_shipped"] for r in rows]
    agg = [r["agg_avg"] for r in rows]

    y = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(11, 8))
    ax.set_title("Distance cost matrix — max detour per weight", fontsize=14, fontweight="bold", pad=12)
    ax.set_xlabel("Extra distance added (km)", fontsize=11)
    ax.set_ylabel("Routing weight", fontsize=11)

    ax.barh(y, shipped, height=0.55, color="#2980b9", alpha=0.85, label="Max at shipped cap / avg aggressive")
    for i, r in enumerate(rows):
        if r["max_explosion"] > r["max_shipped"] + 0.01:
            ax.barh(
                y[i], r["max_explosion"] - r["max_shipped"], left=r["max_shipped"],
                height=0.55, color="#e74c3c", alpha=0.45, label="_nolegend_",
            )

    ax.scatter(agg, y, color="#f39c12", zorder=5, s=40, label="Avg aggressive (all routes)")

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    ax.axvline(1.5, color="#c0392b", linestyle="--", linewidth=1, alpha=0.7, label="Explosion threshold (+1.5 km)")
    ax.axvline(0.8, color="#e67e22", linestyle=":", linewidth=1, alpha=0.6, label="Strong avg threshold (+0.8 km)")

    for i, r in enumerate(rows):
        if r["max_explosion"] > 0:
            ax.text(
                r["max_explosion"] + 0.08, y[i],
                f"{r['max_explosion']:.1f} km max",
                va="center", fontsize=7, color="#555",
            )

    handles, leg_labels = ax.get_legend_handles_labels()
    by_label = dict(zip(leg_labels, handles))
    ax.legend(by_label.values(), by_label.keys(), loc="lower right", fontsize=8)
    ax.set_xlim(0, max(max_vals) * 1.25 if max_vals else 5)
    ax.grid(axis="x", alpha=0.3)

    out = OUT / "distance_cost_matrix.png"
    fig.tight_layout()
    fig.savefig(out, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def plot_distance_cost_matrix_html(wse: dict) -> Path:
    """Interactive distance budget chart with hover detail."""
    rows = _distance_rows(wse)
    labels = [r["label"] for r in rows]

    shipped = [r["max_shipped"] for r in rows]
    rejected_extra = [max(0.0, r["max_explosion"] - r["max_shipped"]) for r in rows]
    agg = [r["agg_avg"] for r in rows]
    mod = [r["mod_avg"] for r in rows]
    keys = [r["key"] for r in rows]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=labels, x=shipped, orientation="h", name="Max at shipped cap",
        marker_color="#2980b9",
        customdata=np.stack([keys, agg, mod, [r["max_explosion"] for r in rows]], axis=-1),
        hovertemplate=(
            "<b>%{y}</b> (%{customdata[0]})<br>"
            "Shipped cap max: %{x:.2f} km<br>"
            "Avg aggressive: %{customdata[1]:.2f} km<br>"
            "Avg moderate: %{customdata[2]:.2f} km<br>"
            "Absolute max: %{customdata[3]:.2f} km<extra></extra>"
        ),
    ))
    fig.add_trace(go.Bar(
        y=labels, x=rejected_extra, orientation="h", name="Rejected-only extension",
        marker_color="#e74c3c", opacity=0.55,
        hovertemplate="Rejected sweep extra: %{x:.2f} km<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        y=labels, x=agg, mode="markers", name="Avg aggressive",
        marker=dict(color="#f39c12", size=10, symbol="circle"),
        hovertemplate="Avg aggressive: %{x:.2f} km<extra></extra>",
    ))

    fig.update_layout(
        title="Distance cost matrix — max detour per weight",
        barmode="stack",
        xaxis_title="Extra distance added (km)",
        yaxis=dict(autorange="reversed"),
        height=max(500, 36 * len(labels)),
        plot_bgcolor="white",
        shapes=[
            dict(type="line", x0=1.5, x1=1.5, y0=-0.5, y1=len(labels) - 0.5,
                 line=dict(color="#c0392b", dash="dash", width=1)),
            dict(type="line", x0=0.8, x1=0.8, y0=-0.5, y1=len(labels) - 0.5,
                 line=dict(color="#e67e22", dash="dot", width=1)),
        ],
        annotations=[
            dict(x=1.5, y=1.04, xref="x", yref="paper", text="+1.5 km explosion", showarrow=False,
                 font=dict(size=10, color="#c0392b")),
            dict(x=0.8, y=1.04, xref="x", yref="paper", text="+0.8 km strong avg", showarrow=False,
                 font=dict(size=10, color="#e67e22")),
        ],
    )
    return _write_html(fig, OUT / "distance_cost_matrix.html")


def _stat_arrow(stat: str, direction: str) -> str:
    arrow = "↑" if direction in ("increase", "up") else "↓" if direction in ("decrease", "down") else "—"
    name = stat.replace("_pct", "%").replace("_", " ")
    return f"{name} {arrow}"


CONSEQ_GOOD = "#d5f5e3"
CONSEQ_BAD = "#fadbd8"

# Undesirable route-stat moves for preset / UX design (red on the right column).
_BAD_CONSEQUENCES = frozenset({
    ("accidents", "increase"),
    ("illumination_pct", "decrease"),
    ("vehicular_free_pct", "decrease"),
    ("calming_count", "increase"),
    ("dist_km", "increase"),
    ("green_pct", "decrease"),
    ("rough_pct", "increase"),
    ("barrier_count", "increase"),
    ("barrier_penalty_count", "increase"),
    ("speed_stress_pct", "increase"),
    ("elevation_gain", "increase"),
})


def _normalize_direction(direction: str) -> str:
    if direction in ("increase", "up"):
        return "increase"
    if direction in ("decrease", "down"):
        return "decrease"
    return direction


def _is_bad_consequence(stat: str, direction: str) -> bool:
    return (stat, _normalize_direction(direction)) in _BAD_CONSEQUENCES


def _consequence_color(stat: str, direction: str) -> str:
    return CONSEQ_BAD if _is_bad_consequence(stat, direction) else CONSEQ_GOOD


def _mechanism_flow_data(mech: dict) -> tuple[list[str], list[str], list[int], list[int], list[int], list[str], list[float], list[float]]:
    """Build Sankey node/link arrays (left: weight, middle: mechanism, right: stat)."""
    mechanisms = mech["mechanisms"]
    node_labels: list[str] = []
    node_colors: list[str] = []
    node_cols: list[int] = []
    node_index: dict[str, int] = {}

    def _add_node(nid: str, label: str, col: int, color: str) -> int:
        if nid not in node_index:
            node_index[nid] = len(node_labels)
            node_labels.append(label)
            node_colors.append(color)
            node_cols.append(col)
        return node_index[nid]

    sources: list[int] = []
    targets: list[int] = []
    values: list[int] = []
    link_colors: list[str] = []

    for mid, m in mechanisms.items():
        if mid in ("inert_weight", "distance_wall"):
            continue
        mlabel = m.get("label", mid)
        mech_idx = _add_node(f"mech:{mid}", mlabel, 1, "#fdebd0")
        triggers = m.get("trigger_weights", [])
        is_signal_mech = "signal_weight" in triggers

        for tw in triggers:
            w_idx = _add_node(f"w:{tw}", _short(tw), 0, "#d6eaf8")
            sources.append(w_idx)
            targets.append(mech_idx)
            values.append(2 if tw == "signal_weight" else 1)
            link_colors.append(
                "rgba(231,76,60,0.55)" if tw == "signal_weight" else "rgba(149,165,166,0.35)"
            )

        sig = m.get("stat_signature", {})
        for bucket in ("primary", "secondary"):
            for stat, direction in (sig.get(bucket) or {}).items():
                if direction in ("stable_or_decrease", "none", ""):
                    continue
                stat_label = _stat_arrow(stat, direction)
                c_idx = _add_node(
                    f"c:{stat_label}", stat_label, 2,
                    _consequence_color(stat, direction),
                )
                sources.append(mech_idx)
                targets.append(c_idx)
                values.append(2 if is_signal_mech else 1)
                link_colors.append(
                    "rgba(231,76,60,0.55)" if is_signal_mech else "rgba(149,165,166,0.35)"
                )

    col_x = {0: 0.01, 1: 0.5, 2: 0.99}
    node_x: list[float] = [0.0] * len(node_labels)
    node_y: list[float] = [0.0] * len(node_labels)
    for col in (0, 1, 2):
        col_nodes = [i for i, c in enumerate(node_cols) if c == col]
        for rank, idx in enumerate(col_nodes):
            node_x[idx] = col_x[col]
            node_y[idx] = (rank + 1) / (len(col_nodes) + 1)

    return node_labels, node_colors, sources, targets, values, link_colors, node_x, node_y


def plot_mechanism_flow(mech: dict) -> Path:
    """Three-column flow: trigger weight → mechanism → stat consequence."""
    mechanisms = mech["mechanisms"]

    weight_nodes: list[str] = []
    mech_nodes: list[str] = []
    cons_nodes: list[str] = []
    cons_color: dict[str, str] = {}
    links: list[tuple[str, str, str, str]] = []

    for mid, m in mechanisms.items():
        if mid in ("inert_weight", "distance_wall"):
            continue
        mlabel = m.get("label", mid)
        mech_nodes.append(mlabel)
        for tw in m.get("trigger_weights", []):
            if tw not in weight_nodes:
                weight_nodes.append(tw)
            links.append(("weight", tw, "mech", mlabel))
        sig = m.get("stat_signature", {})
        for bucket in ("primary", "secondary"):
            for stat, direction in (sig.get(bucket) or {}).items():
                if direction in ("stable_or_decrease", "none", ""):
                    continue
                node = _stat_arrow(stat, direction)
                if node not in cons_nodes:
                    cons_nodes.append(node)
                    cons_color[node] = _consequence_color(stat, direction)
                links.append(("mech", mlabel, "cons", node))

    x_w, x_m, x_c = 0.0, 0.45, 0.95
    col_h = 0.08

    def _layout(nodes: list[str], x: float) -> dict[str, tuple[float, float]]:
        pos = {}
        n = len(nodes)
        for i, node in enumerate(nodes):
            y = 1.0 - (i + 1) / (n + 1)
            pos[node] = (x, y)
        return pos

    pos_w = _layout(weight_nodes, x_w)
    pos_m = _layout(mech_nodes, x_m)
    pos_c = _layout(cons_nodes, x_c)

    fig, ax = plt.subplots(figsize=(16, 10))
    ax.set_xlim(-0.12, 1.12)
    ax.set_ylim(0, 1.05)
    ax.axis("off")
    ax.set_title("Mechanism flow — user intent → escape route → side effect", fontsize=14, fontweight="bold", pad=14)

    ax.text(x_w, 1.02, "User raises weight", ha="center", fontsize=11, fontweight="bold", color="#2c3e50")
    ax.text(x_m, 1.02, "Routing mechanism", ha="center", fontsize=11, fontweight="bold", color="#2c3e50")
    ax.text(x_c, 1.02, "Route stat consequence", ha="center", fontsize=11, fontweight="bold", color="#2c3e50")

    def _draw_box(pos_dict: dict, key: str, color: str, fontsize: int = 7):
        x, y = pos_dict[key]
        label = _short(key) if key.endswith("_weight") else key
        if len(label) > 22:
            label = label[:20] + "…"
        box = mpatches.FancyBboxPatch(
            (x - 0.11, y - col_h / 2), 0.22, col_h,
            boxstyle="round,pad=0.02", linewidth=1, edgecolor="#2c3e50",
            facecolor=color, alpha=0.9, transform=ax.transData,
        )
        ax.add_patch(box)
        ax.text(x, y, label, ha="center", va="center", fontsize=fontsize, wrap=True)

    for w in weight_nodes:
        _draw_box(pos_w, w, "#d6eaf8", 7)
    for m in mech_nodes:
        _draw_box(pos_m, m, "#fdebd0", 6)
    for c in cons_nodes:
        _draw_box(pos_c, c, cons_color[c], 6)

    for src_col, src, tgt_col, tgt in links:
        if src_col == "weight":
            x0, y0 = pos_w[src]
            x1, y1 = pos_m[tgt]
        else:
            x0, y0 = pos_m[src]
            x1, y1 = pos_c[tgt]
        is_signal = src == "signal_weight" or (src_col == "mech" and any(
            l[1] == "signal_weight" and l[3] == src for l in links
        ))
        color = "#e74c3c" if is_signal else "#95a5a6"
        alpha = 0.55 if is_signal else 0.22
        lw = 1.8 if is_signal else 0.8
        ax.annotate(
            "",
            xy=(x1 - 0.11 if tgt_col == "cons" else x1 - 0.11, y1),
            xytext=(x0 + 0.11, y0),
            arrowprops=dict(
                arrowstyle="-|>", color=color, lw=lw, alpha=alpha,
                connectionstyle="arc3,rad=0.08", shrinkA=2, shrinkB=2,
            ),
        )

    ax.text(
        0.5, -0.03,
        "Red flows: paths from signal_weight (arterial bypass vs rat run split). "
        "Gray: all other weight→mechanism→stat paths.",
        ha="center", fontsize=8, color="#555", transform=ax.transAxes,
    )

    out = OUT / "mechanism_flow.png"
    fig.tight_layout()
    fig.savefig(out, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def plot_mechanism_flow_html(mech: dict) -> Path:
    """Interactive Sankey: trigger weight → mechanism → stat consequence."""
    labels, colors, src, tgt, val, link_colors, node_x, node_y = _mechanism_flow_data(mech)

    fig = go.Figure(data=[go.Sankey(
        arrangement="snap",
        node=dict(
            pad=18,
            thickness=18,
            line=dict(color="#2c3e50", width=0.5),
            label=labels,
            color=colors,
            x=node_x,
            y=node_y,
        ),
        link=dict(
            source=src,
            target=tgt,
            value=val,
            color=link_colors,
            hovertemplate="%{source.label} → %{target.label}<extra></extra>",
        ),
    )])

    fig.update_layout(
        title="Mechanism flow — user intent → escape route → side effect",
        font=dict(size=11),
        height=800,
        annotations=[
            dict(x=0.01, y=1.06, xref="paper", yref="paper", text="User raises weight",
                 showarrow=False, font=dict(size=12, color="#2c3e50")),
            dict(x=0.5, y=1.06, xref="paper", yref="paper", text="Routing mechanism",
                 showarrow=False, font=dict(size=12, color="#2c3e50")),
            dict(x=0.99, y=1.06, xref="paper", yref="paper", text="Route stat consequence",
                 showarrow=False, font=dict(size=12, color="#2c3e50")),
            dict(x=0.5, y=-0.06, xref="paper", yref="paper",
                 text="Red flows: signal_weight paths (arterial bypass vs rat run). Hover any band for detail.",
                 showarrow=False, font=dict(size=10, color="#555")),
        ],
    )
    return _write_html(fig, OUT / "mechanism_flow.html")


def main() -> None:
    wse, wc, mech = _load()
    paths = [
        plot_network_graph(wse, wc),
        plot_network_graph_html(wse, wc),
        plot_distance_cost_matrix(wse),
        plot_distance_cost_matrix_html(wse),
        plot_mechanism_flow(mech),
        plot_mechanism_flow_html(mech),
    ]
    print("Wrote:")
    for p in paths:
        print(f"  {p}")


if __name__ == "__main__":
    main()
