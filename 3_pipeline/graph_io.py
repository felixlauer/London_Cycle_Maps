"""
Fast pickle I/O for NetworkX graphs alongside optional GraphML export.

Pipeline: prefer .gpickle for load; write GraphML only when write_graphml=True.
Backends: load_graph(canonical .graphml path) picks fresh .gpickle when present.

Pickle vs GraphML mtime: dual-save writes pickle before GraphML, so GraphML is often
newer by minutes. A 24h skew window avoids false stale warnings; only a large gap
implies an external GraphML edit.
"""
from __future__ import annotations

import os
import pickle
import time

import networkx as nx

FAST_SUFFIX = ".gpickle"
# Max age gap (GraphML newer than pickle) still treated as same build artifact.
GRAPHML_PICKLE_MAX_SKEW_SEC = 86400


def fast_path(graphml_path: str) -> str:
    """Companion fast-load path for a canonical .graphml path."""
    base, _ext = os.path.splitext(graphml_path)
    return base + FAST_SUFFIX


def _mtime(path: str) -> float | None:
    if os.path.isfile(path):
        return os.path.getmtime(path)
    return None


def _resolve_load_path(graphml_path: str) -> tuple[str, str]:
    """
    Return (path_to_load, format_label) where format_label is 'pickle' or 'graphml'.
    """
    graphml_path = os.path.normpath(graphml_path)
    pickle_path = fast_path(graphml_path)
    m_graphml = _mtime(graphml_path)
    m_pickle = _mtime(pickle_path)

    if m_pickle is not None:
        if m_graphml is None:
            return pickle_path, "pickle"
        pickle_time = m_pickle
        graphml_time = m_graphml
        if pickle_time >= graphml_time or (graphml_time - pickle_time) < GRAPHML_PICKLE_MAX_SKEW_SEC:
            return pickle_path, "pickle"
        gap_h = (graphml_time - pickle_time) / 3600
        print(
            f"WARNING: {pickle_path} is older than {graphml_path} by {gap_h:.1f}h "
            f"(>{GRAPHML_PICKLE_MAX_SKEW_SEC // 3600}h); loading GraphML, ignoring pickle."
        )

    if m_graphml is not None:
        return graphml_path, "graphml"

    if m_pickle is not None:
        return pickle_path, "pickle"

    raise FileNotFoundError(
        f"No graph found at {graphml_path} or {pickle_path}"
    )


def load_graph(graphml_path: str) -> nx.DiGraph:
    """Load graph from fresh .gpickle if available, else .graphml."""
    path, fmt = _resolve_load_path(graphml_path)
    t0 = time.perf_counter()
    if fmt == "pickle":
        with open(path, "rb") as f:
            G = pickle.load(f)
    else:
        G = nx.read_graphml(path)
    elapsed = time.perf_counter() - t0
    if not isinstance(G, (nx.DiGraph, nx.MultiDiGraph)):
        G = nx.DiGraph(G)
    print(
        f"Loaded graph from {path} ({fmt}, {G.number_of_nodes()} nodes, "
        f"{G.number_of_edges()} edges) in {elapsed:.1f}s"
    )
    return G


def _atomic_write_bytes(target_path: str, write_fn) -> None:
    """Write via temp file in same directory, then replace target."""
    directory = os.path.dirname(os.path.abspath(target_path)) or "."
    os.makedirs(directory, exist_ok=True)
    tmp_path = target_path + ".tmp"
    try:
        write_fn(tmp_path)
        os.replace(tmp_path, target_path)
    finally:
        if os.path.isfile(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def save_graph(
    G: nx.DiGraph,
    graphml_path: str,
    *,
    write_graphml: bool = False,
    write_fast: bool = True,
) -> None:
    """
    Save graph artifacts for graphml_path basename.

    write_fast: write .gpickle (default True)
    write_graphml: write .graphml (default False; enable at build + final TfL)
    """
    graphml_path = os.path.normpath(graphml_path)
    pickle_path = fast_path(graphml_path)

    if write_fast:
        t0 = time.perf_counter()

        def _write_pickle(path: str) -> None:
            with open(path, "wb") as f:
                pickle.dump(G, f, protocol=pickle.HIGHEST_PROTOCOL)

        _atomic_write_bytes(pickle_path, _write_pickle)
        print(
            f"Saved pickle to {pickle_path} ({G.number_of_nodes()} nodes, "
            f"{G.number_of_edges()} edges) in {time.perf_counter() - t0:.1f}s"
        )

    if write_graphml:
        t0 = time.perf_counter()

        def _write_graphml(path: str) -> None:
            nx.write_graphml(G, path)

        _atomic_write_bytes(graphml_path, _write_graphml)
        print(
            f"Saved GraphML to {graphml_path} in {time.perf_counter() - t0:.1f}s"
        )
