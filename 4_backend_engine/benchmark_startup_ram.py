#!/usr/bin/env python3
"""
Startup time + RAM benchmark for the production routing engine (app.py).

Measures:
  - Wall time per bootstrap phase (from app.py log lines)
  - Process RSS over the full startup → ready → (optional) geom warm → idle hold
  - Peak / end RSS for "hosting" (post-ready idle) and optional one-route smoke

Runs in a fresh child process so RSS is not polluted by a prior import.

  cd c:\\London_Cycle_Maps
  python 4_backend_engine/benchmark_startup_ram.py

Optional env / flags:
  --geom off|background|sync   (default: background = production)
  --hold-s 30                  idle seconds after ready (hosting sample)
  --no-wait-geom               do not wait for background GEOM_PREPARSE
  --no-route                   skip one A* smoke after ready
  --live                       allow TfL/TomTom fetch (default: skip)
  --sample-ms 250              RSS sample interval

Writes:
  0_documentation/testing/startup_ram_report.md
  0_documentation/testing/startup_ram_report.json

Do not run from the agent unless asked — intended for a local manual run
(full warm with GEOM_PREPARSE=background can take ~5+ minutes).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import types
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "4_backend_engine"
REPORT_DIR = REPO_ROOT / "0_documentation" / "testing"
REPORT_MD = REPORT_DIR / "startup_ram_report.md"
REPORT_JSON = REPORT_DIR / "startup_ram_report.json"
RESULT_MARKER = "===STARTUP_RAM_RESULT_JSON==="

# Fallback smoke route if 6_verification/test_routes.txt is missing (central London).
SMOKE_ROUTE = {
    "name": "smoke: Imperial → King's Cross",
    "start_lat": 51.4988,
    "start_lon": -0.1749,
    "end_lat": 51.5308,
    "end_lon": -0.1238,
}

PHASE_PATTERNS: list[tuple[str, re.Pattern[str], float]] = [
    # (phase_id, regex with group 1 = seconds, unit_scale → seconds)
    ("graph_load", re.compile(r"Graph loaded with .+ \(([0-9.]+)s\)"), 1.0),
    ("node_kdtree", re.compile(r"--> Node KD-tree: .+ \(([0-9.]+)s\)"), 1.0),
    ("live_index", re.compile(r"--> Live disruption index: .+ \(([0-9.]+)s\)"), 1.0),
    ("node_xy_stamps", re.compile(r"--> Node XY stamps: .+ \(([0-9.]+)s\)"), 1.0),
    ("bootstrap_early", re.compile(r"--- Bootstrap complete in ([0-9.]+)s ---"), 1.0),
    ("junction_flags", re.compile(r"--> Junction flags: .+ \(([0-9.]+)s\)"), 1.0),
    ("heuristic_floors", re.compile(r"--> Heuristic penalty floors: .+ \(([0-9.]+)s\)"), 1.0),
    (
        "junction_cluster",
        re.compile(r"--> Junction cluster dedup: .+; ([0-9.]+)s\)"),
        1.0,
    ),
    ("edge_cost_arrays", re.compile(r"--> Edge cost arrays: .+ in ([0-9.]+)s"), 1.0),
    ("shared_overlays", re.compile(r"--> Shared overlays: bake ([0-9.]+) ms"), 0.001),
    ("graph_csr", re.compile(r"--> Graph CSR: .+ in ([0-9.]+)s"), 1.0),
    ("numba_warmup", re.compile(r"--> Numba A\* warmup: ([0-9.]+)s"), 1.0),
    (
        "geom_preparse_sync",
        re.compile(r"--> Geometry preparse: .+ in ([0-9.]+)s"),
        1.0,
    ),
]


# ---------------------------------------------------------------------------
# RSS helpers (no psutil required)
# ---------------------------------------------------------------------------

def _rss_bytes(pid: int | None = None) -> int | None:
    """Current working-set / RSS for pid (default: this process)."""
    pid = os.getpid() if pid is None else int(pid)
    if sys.platform == "win32":
        return _rss_bytes_win(pid)
    # Linux / macOS
    try:
        import resource

        if pid == os.getpid():
            # ru_maxrss: Linux = KiB, macOS = bytes
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if sys.platform == "darwin":
                return int(rss)
            return int(rss) * 1024
    except Exception:
        pass
    try:
        with open(f"/proc/{pid}/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
    except Exception:
        pass
    return None


def _rss_bytes_win(pid: int) -> int | None:
    import ctypes
    from ctypes import wintypes

    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_VM_READ = 0x0010
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    OpenProcess = kernel32.OpenProcess
    OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    OpenProcess.restype = wintypes.HANDLE
    CloseHandle = kernel32.CloseHandle
    GetProcessMemoryInfo = psapi.GetProcessMemoryInfo
    GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
        wintypes.DWORD,
    ]
    GetProcessMemoryInfo.restype = wintypes.BOOL

    handle = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not handle:
        return None
    try:
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        if not GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return None
        return int(counters.WorkingSetSize)
    finally:
        CloseHandle(handle)


def _fmt_bytes(n: int | float | None) -> str:
    if n is None:
        return "n/a"
    n = float(n)
    for unit, div in (("GiB", 1024**3), ("MiB", 1024**2), ("KiB", 1024)):
        if abs(n) >= div:
            return f"{n / div:.2f} {unit}"
    return f"{n:.0f} B"


def _fmt_s(s: float | None) -> str:
    if s is None:
        return "n/a"
    if s >= 60:
        return f"{s:.1f}s ({s / 60:.1f} min)"
    return f"{s:.2f}s"


# ---------------------------------------------------------------------------
# Child worker (fresh process)
# ---------------------------------------------------------------------------

def _mock_flask() -> None:
    flask = types.ModuleType("flask")

    class _Flask:
        def __init__(self, *args, **kwargs):
            pass

        def route(self, *args, **kwargs):
            def decorator(fn):
                return fn

            return decorator

        def before_request(self, fn):
            return fn

    flask.Flask = _Flask
    flask.request = types.SimpleNamespace(args={})
    flask.g = types.SimpleNamespace()
    flask.jsonify = lambda x: x
    sys.modules["flask"] = flask

    cors = types.ModuleType("flask_cors")
    cors.CORS = lambda *args, **kwargs: None
    sys.modules["flask_cors"] = cors


class _RssSampler:
    def __init__(self, interval_s: float = 0.25):
        self.interval_s = interval_s
        self.t0 = time.perf_counter()
        self.samples: list[dict] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.labels: list[tuple[float, str]] = []

    def mark(self, label: str) -> None:
        self.labels.append((time.perf_counter() - self.t0, label))

    def start(self) -> None:
        self.t0 = time.perf_counter()
        self._thread = threading.Thread(target=self._run, name="rss-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            rss = _rss_bytes()
            self.samples.append(
                {
                    "t_s": round(time.perf_counter() - self.t0, 3),
                    "rss_bytes": rss,
                }
            )
            self._stop.wait(self.interval_s)

    def peak_in(self, t0: float, t1: float | None = None) -> int | None:
        vals = []
        for s in self.samples:
            if s["t_s"] < t0:
                continue
            if t1 is not None and s["t_s"] > t1:
                continue
            if s["rss_bytes"] is not None:
                vals.append(s["rss_bytes"])
        return max(vals) if vals else None

    def nearest(self, t_s: float) -> int | None:
        best = None
        best_dt = 1e9
        for s in self.samples:
            if s["rss_bytes"] is None:
                continue
            dt = abs(s["t_s"] - t_s)
            if dt < best_dt:
                best_dt = dt
                best = s["rss_bytes"]
        return best


def _parse_phases(log_text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for phase_id, pat, scale in PHASE_PATTERNS:
        m = pat.search(log_text)
        if m:
            out[phase_id] = round(float(m.group(1)) * scale, 3)
    return out


def _pick_smoke_route() -> dict:
    try:
        sys.path.insert(0, str(BACKEND_DIR))
        import benchmark_array_costs as bac

        routes = bac.parse_test_routes()
        if routes:
            return routes[0]
    except Exception:
        pass
    return dict(SMOKE_ROUTE)


def _run_route_smoke(app_mod) -> dict:
    import edge_cost_arrays
    import graph_csr
    import pathfinding
    import pathfinding_numba
    import tfl_live
    from barrier_clusters import BARRIER_HARD_COST
    from routing_heuristic import make_heuristic

    route = _pick_smoke_route()
    start_snap = tfl_live.snap_to_edge(route["start_lat"], route["start_lon"])
    end_snap = tfl_live.snap_to_edge(route["end_lat"], route["end_lon"])
    if not start_snap or not end_snap:
        return {"ok": False, "error": "snap failed", "route": route["name"]}

    bike = "standard"
    try:
        profiles = json.loads((BACKEND_DIR / "user_profiles.json").read_text(encoding="utf-8"))
        bike = str(profiles["profiles"]["preset_fast"]["weights"].get("bike_type", "standard"))
    except Exception:
        pass

    G = app_mod.G
    start_node = start_snap.anchor_node
    end_node = end_snap.anchor_node
    hard = float(BARRIER_HARD_COST)
    scale = 1.0

    csr = graph_csr.get_csr()
    tables = edge_cost_arrays.get_tables()
    shared = edge_cost_arrays.get_shared_overlays()

    t0 = time.perf_counter()
    path = None
    stats: dict = {}
    engine = "nx"

    if (
        pathfinding_numba.numba_astar_enabled()
        and pathfinding_numba.is_available()
        and csr is not None
        and tables is not None
        and shared is not None
    ):
        path, stats = pathfinding_numba.astar_numba_unidirectional(
            csr,
            start_node,
            end_node,
            tables,
            shared,
            mode="fastest",
            cost_per_m=scale,
            hard_cost=hard,
            bike_type=bike,
        )
        engine = "numba"
    elif csr is not None and tables is not None and shared is not None:
        cost_by_eid = edge_cost_arrays.make_array_cost_by_eid_fastest(
            tables, hard, shared, bike_type=bike
        )
        path, stats = pathfinding.astar_csr_unidirectional(
            csr, start_node, end_node, cost_by_eid, cost_per_m=scale
        )
        engine = "csr_py"
    else:
        h = make_heuristic(end_node, G, cost_per_m=scale, csr=csr)
        weight_fn = app_mod.make_weight_fastest({}, True)
        path, stats = pathfinding.astar_unidirectional(
            G, start_node, end_node, h, weight_fn
        )
        engine = "nx"

    elapsed = time.perf_counter() - t0
    return {
        "ok": bool(path),
        "route": route["name"],
        "engine": engine,
        "elapsed_s": round(elapsed, 3),
        "path_nodes": len(path or []),
        "expansions": (stats or {}).get("expansions"),
    }


def child_main(args: argparse.Namespace) -> int:
    os.chdir(BACKEND_DIR)
    sys.path.insert(0, str(BACKEND_DIR))
    sys.path.insert(0, str(REPO_ROOT / "3_pipeline"))

    os.environ["FLASK_USE_RELOADER"] = "0"
    os.environ["GEOM_PREPARSE"] = args.geom
    if args.live:
        os.environ.pop("SKIP_DISRUPTION_FETCH", None)
        os.environ.pop("LIVE_DISRUPTIONS", None)
    else:
        os.environ["SKIP_DISRUPTION_FETCH"] = "1"

    log_lines: list[str] = []

    class _Tee:
        def __init__(self, stream):
            self._stream = stream

        def write(self, s: str) -> int:
            log_lines.append(s)
            self._stream.write(s)
            self._stream.flush()
            return len(s)

        def flush(self) -> None:
            self._stream.flush()

    sys.stdout = _Tee(sys.__stdout__)  # type: ignore[assignment]
    sys.stderr = _Tee(sys.__stderr__)  # type: ignore[assignment]

    sampler = _RssSampler(interval_s=max(args.sample_ms, 50) / 1000.0)
    rss_before = _rss_bytes()
    sampler.start()
    sampler.mark("process_start")

    _mock_flask()
    t_import0 = time.perf_counter()
    sampler.mark("import_app_begin")
    import app as app_mod  # noqa: F401 — full bootstrap

    t_ready = time.perf_counter() - sampler.t0
    sampler.mark("engine_ready")
    import_wall_s = time.perf_counter() - t_import0
    rss_ready = _rss_bytes()

    import edge_cost_arrays
    import graph_csr
    import pathfinding_numba

    geom_mode = edge_cost_arrays.geom_preparse_mode()
    geom_state = edge_cost_arrays.get_geom_preparse_state()
    geom_wait_s = None
    rss_geom_ready = None
    t_geom_ready = None

    if args.wait_geom and geom_mode == "background":
        sampler.mark("geom_wait_begin")
        deadline = time.perf_counter() + max(args.geom_timeout_s, 60)
        while time.perf_counter() < deadline:
            st = edge_cost_arrays.get_geom_preparse_state()
            if st.get("state") in ("ready", "error", "off"):
                geom_state = st
                break
            time.sleep(0.5)
        t_geom_ready = time.perf_counter() - sampler.t0
        geom_wait_s = round(t_geom_ready - t_ready, 3)
        rss_geom_ready = _rss_bytes()
        sampler.mark("geom_ready")
    elif geom_mode == "sync":
        t_geom_ready = t_ready
        rss_geom_ready = rss_ready
        geom_state = edge_cost_arrays.get_geom_preparse_state()

    # Idle hosting hold
    sampler.mark("idle_hold_begin")
    t_hold0 = time.perf_counter() - sampler.t0
    time.sleep(max(args.hold_s, 0.0))
    t_hold1 = time.perf_counter() - sampler.t0
    rss_idle_end = _rss_bytes()
    peak_idle = sampler.peak_in(t_hold0, t_hold1)
    sampler.mark("idle_hold_end")

    route_smoke = None
    rss_after_route = None
    peak_route = None
    if args.route:
        sampler.mark("route_smoke_begin")
        t_r0 = time.perf_counter() - sampler.t0
        try:
            route_smoke = _run_route_smoke(app_mod)
        except Exception as exc:
            route_smoke = {"ok": False, "error": str(exc)}
        t_r1 = time.perf_counter() - sampler.t0
        rss_after_route = _rss_bytes()
        peak_route = sampler.peak_in(t_r0, t_r1)
        sampler.mark("route_smoke_end")

    sampler.stop()
    log_text = "".join(log_lines)
    phases = _parse_phases(log_text)

    # Sum of printed sub-phases (excludes early bootstrap_early which overlaps)
    exclusive_keys = [
        "graph_load",
        "node_kdtree",
        "live_index",
        "node_xy_stamps",
        "junction_flags",
        "heuristic_floors",
        "junction_cluster",
        "edge_cost_arrays",
        "shared_overlays",
        "graph_csr",
        "numba_warmup",
        "geom_preparse_sync",
    ]
    phases_sum = round(sum(phases.get(k, 0.0) for k in exclusive_keys), 3)
    unaccounted = round(import_wall_s - phases_sum, 3)

    G = app_mod.G
    csr = graph_csr.get_csr()
    tables = edge_cost_arrays.get_tables()

    result = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
            "platform": sys.platform,
            "python": sys.version.split()[0],
            "geom_mode": geom_mode,
            "live_fetch": bool(args.live),
            "hold_s": args.hold_s,
            "wait_geom": bool(args.wait_geom),
            "sample_ms": args.sample_ms,
            "array_costs": edge_cost_arrays.array_costs_enabled(),
            "csr_astar": graph_csr.csr_astar_enabled(),
            "numba_astar": pathfinding_numba.numba_astar_enabled()
            and pathfinding_numba.is_available(),
        },
        "graph": {
            "n_nodes": G.number_of_nodes() if G is not None else None,
            "n_edges": G.number_of_edges() if G is not None else None,
            "csr_nodes": getattr(csr, "n_nodes", None),
            "csr_arcs": getattr(csr, "n_edges", None),
            "table_edges": getattr(tables, "n_edges", None),
        },
        "timing_s": {
            "import_wall_to_ready": round(import_wall_s, 3),
            "wall_to_ready": round(t_ready, 3),
            "wall_to_geom_ready": round(t_geom_ready, 3) if t_geom_ready is not None else None,
            "geom_wait_after_ready": geom_wait_s,
            "phases": phases,
            "phases_sum_exclusive": phases_sum,
            "unaccounted_in_import_wall": unaccounted,
        },
        "ram": {
            "rss_before_import_bytes": rss_before,
            "rss_at_ready_bytes": rss_ready,
            "rss_at_geom_ready_bytes": rss_geom_ready,
            "rss_idle_end_bytes": rss_idle_end,
            "rss_after_route_bytes": rss_after_route,
            "peak_startup_to_ready_bytes": sampler.peak_in(0.0, t_ready),
            "peak_ready_to_geom_bytes": (
                sampler.peak_in(t_ready, t_geom_ready)
                if t_geom_ready is not None
                else None
            ),
            "peak_idle_hold_bytes": peak_idle,
            "peak_route_smoke_bytes": peak_route,
            "peak_overall_bytes": sampler.peak_in(0.0, None),
        },
        "geom_preparse": geom_state,
        "route_smoke": route_smoke,
        "labels": [{"t_s": round(t, 3), "label": lab} for t, lab in sampler.labels],
        "rss_samples": sampler.samples,
        "log_excerpt": log_text[-8000:],
    }

    # Emit machine-readable block for parent (also useful standalone).
    print(RESULT_MARKER, flush=True)
    print(json.dumps(result), flush=True)
    return 0


# ---------------------------------------------------------------------------
# Parent: spawn child, write reports
# ---------------------------------------------------------------------------

def _write_reports(result: dict) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")

    meta = result["meta"]
    timing = result["timing_s"]
    ram = result["ram"]
    phases = timing.get("phases") or {}
    graph = result.get("graph") or {}

    phase_rows = [
        ("Graph load (pickle)", "graph_load"),
        ("Node KD-tree", "node_kdtree"),
        ("Live disruption STRtree (+ optional fetch kickoff)", "live_index"),
        ("Node XY stamps", "node_xy_stamps"),
        ("Junction danger flags", "junction_flags"),
        ("Heuristic penalty floors", "heuristic_floors"),
        ("Junction cluster dedup", "junction_cluster"),
        ("Edge cost arrays (VF + tables + _eid)", "edge_cost_arrays"),
        ("Shared overlays bake", "shared_overlays"),
        ("CSR build", "graph_csr"),
        ("Numba A* warmup", "numba_warmup"),
        ("Geometry preparse (sync only)", "geom_preparse_sync"),
    ]

    lines = [
        "# Startup + RAM report",
        "",
        f"Generated: `{meta.get('generated_at')}`  ",
        f"Platform: `{meta.get('platform')}` · Python `{meta.get('python')}`  ",
        f"GEOM_PREPARSE=`{meta.get('geom_mode')}` · live_fetch=`{meta.get('live_fetch')}`  ",
        f"Kill-switches: ARRAY_COSTS=`{meta.get('array_costs')}` · "
        f"CSR_ASTAR=`{meta.get('csr_astar')}` · NUMBA_ASTAR=`{meta.get('numba_astar')}`",
        "",
        "## Graph",
        "",
        f"- Nodes: **{graph.get('n_nodes')}** · edges: **{graph.get('n_edges')}**",
        f"- CSR: {graph.get('csr_nodes')} nodes / {graph.get('csr_arcs')} arcs",
        f"- Cost table edges: {graph.get('table_edges')}",
        "",
        "## Startup wall time",
        "",
        f"| Milestone | Time |",
        f"|-----------|------|",
        f"| Import → engine ready (serve-capable) | **{_fmt_s(timing.get('import_wall_to_ready'))}** |",
        f"| Process wall → ready | {_fmt_s(timing.get('wall_to_ready'))} |",
        f"| Process wall → geom warm ready | {_fmt_s(timing.get('wall_to_geom_ready'))} |",
        f"| Geom wait after ready | {_fmt_s(timing.get('geom_wait_after_ready'))} |",
        "",
        "### Phase breakdown (from app.py log lines)",
        "",
        "| Phase | Seconds | Share of ready |",
        "|-------|---------|----------------|",
    ]
    ready = timing.get("import_wall_to_ready") or 0.0
    for label, key in phase_rows:
        sec = phases.get(key)
        if sec is None:
            lines.append(f"| {label} | — | — |")
            continue
        share = f"{100.0 * sec / ready:.1f}%" if ready > 0 else "—"
        lines.append(f"| {label} | {sec:.2f} | {share} |")
    lines.extend(
        [
            f"| **Sum of exclusive phases** | **{timing.get('phases_sum_exclusive')}** | — |",
            f"| Unaccounted (import overhead / other) | {timing.get('unaccounted_in_import_wall')} | — |",
            "",
            "Notes:",
            "",
            "- `bootstrap_early` in logs is the early block only (graph → XY stamps), "
            "not full engine ready.",
            "- With `GEOM_PREPARSE=background`, geom warm runs **after** ready and is "
            "reported under geom wait / geom_preparse state (not in the ready sum).",
            "- With `GEOM_PREPARSE=sync`, geom time appears in the phase table and is "
            "included in ready.",
            "",
            "## RAM (process working set / RSS)",
            "",
            "| Point | RSS |",
            "|-------|-----|",
            f"| Before import | {_fmt_bytes(ram.get('rss_before_import_bytes'))} |",
            f"| Engine ready | **{_fmt_bytes(ram.get('rss_at_ready_bytes'))}** |",
            f"| Geom warm ready | {_fmt_bytes(ram.get('rss_at_geom_ready_bytes'))} |",
            f"| End of idle hold ({meta.get('hold_s')}s) | **{_fmt_bytes(ram.get('rss_idle_end_bytes'))}** |",
            f"| After route smoke | {_fmt_bytes(ram.get('rss_after_route_bytes'))} |",
            "",
            "| Peak window | RSS |",
            "|-------------|-----|",
            f"| Startup → ready | {_fmt_bytes(ram.get('peak_startup_to_ready_bytes'))} |",
            f"| Ready → geom ready | {_fmt_bytes(ram.get('peak_ready_to_geom_bytes'))} |",
            f"| Idle hold (hosting) | {_fmt_bytes(ram.get('peak_idle_hold_bytes'))} |",
            f"| Route smoke | {_fmt_bytes(ram.get('peak_route_smoke_bytes'))} |",
            f"| Overall | **{_fmt_bytes(ram.get('peak_overall_bytes'))}** |",
            "",
        ]
    )

    geom = result.get("geom_preparse") or {}
    lines.extend(
        [
            "## Geometry preparse",
            "",
            f"- State: `{geom.get('state')}`",
            f"- Parsed: {geom.get('n_parsed')} / {geom.get('n_edges')} "
            f"(already cached {geom.get('n_already_cached')})",
            f"- Elapsed: {_fmt_s(geom.get('elapsed_s'))}",
            "",
        ]
    )

    smoke = result.get("route_smoke")
    if smoke:
        lines.extend(
            [
                "## Route smoke",
                "",
                f"- Route: {smoke.get('route')}",
                f"- OK: {smoke.get('ok')} · engine: `{smoke.get('engine')}`",
                f"- A* wall: {_fmt_s(smoke.get('elapsed_s'))} · "
                f"nodes={smoke.get('path_nodes')} · expansions={smoke.get('expansions')}",
                "",
            ]
        )
        if smoke.get("error"):
            lines.append(f"- Error: `{smoke.get('error')}`")
            lines.append("")

    n_samples = len(result.get("rss_samples") or [])
    lines.extend(
        [
            "## Artifacts",
            "",
            f"- JSON (full RSS series, {n_samples} samples): "
            f"[`startup_ram_report.json`](startup_ram_report.json)",
            f"- Re-run: `python 4_backend_engine/benchmark_startup_ram.py`",
            "",
        ]
    )
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {REPORT_MD}")
    print(f"Wrote {REPORT_JSON}")


def parent_main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Startup time + RAM benchmark for app.py")
    p.add_argument(
        "--geom",
        choices=("off", "background", "sync"),
        default="background",
        help="GEOM_PREPARSE mode (default: background = production)",
    )
    p.add_argument("--hold-s", type=float, default=30.0, help="Idle hosting sample seconds")
    p.add_argument(
        "--no-wait-geom",
        action="store_true",
        help="Do not wait for background geom warm to finish",
    )
    p.add_argument(
        "--geom-timeout-s",
        type=float,
        default=600.0,
        help="Max wait for background geom (default 600s)",
    )
    p.add_argument("--no-route", action="store_true", help="Skip one-route smoke")
    p.add_argument("--live", action="store_true", help="Allow live disruption fetch")
    p.add_argument("--sample-ms", type=int, default=250, help="RSS sample interval")
    p.add_argument(
        "--child",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = p.parse_args(argv)
    args.wait_geom = not args.no_wait_geom
    args.route = not args.no_route

    if args.child:
        return child_main(args)

    cmd = [
        sys.executable,
        "-u",
        str(Path(__file__).resolve()),
        "--child",
        "--geom",
        args.geom,
        "--hold-s",
        str(args.hold_s),
        "--geom-timeout-s",
        str(args.geom_timeout_s),
        "--sample-ms",
        str(args.sample_ms),
    ]
    if args.no_wait_geom:
        cmd.append("--no-wait-geom")
    if args.no_route:
        cmd.append("--no-route")
    if args.live:
        cmd.append("--live")

    print("Spawning fresh process for clean RSS...", flush=True)
    print(f"  geom={args.geom} hold={args.hold_s}s wait_geom={args.wait_geom} route={args.route}")
    print("  (background geom warm can take ~4 min — leave this running)\n", flush=True)

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    # Ensure child does not inherit a conflicting GEOM_PREPARSE from the shell
    # unless user set --geom (we pass it explicitly to the child).
    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    buf: list[str] = []
    capturing = False
    json_lines: list[str] = []
    for line in proc.stdout:
        if RESULT_MARKER in line:
            capturing = True
            # print marker for humans too
            sys.stdout.write(line)
            sys.stdout.flush()
            continue
        if capturing:
            json_lines.append(line)
        else:
            sys.stdout.write(line)
            sys.stdout.flush()
            buf.append(line)

    rc = proc.wait()
    if rc != 0:
        print(f"Child exited with code {rc}", file=sys.stderr)
        return rc
    if not json_lines:
        print("No result JSON from child", file=sys.stderr)
        return 2

    raw = "".join(json_lines).strip()
    # Child may print only one JSON object; take first complete object
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # If trailing noise, find first { ... last }
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end < 0:
            raise
        result = json.loads(raw[start : end + 1])

    _write_reports(result)

    timing = result["timing_s"]
    ram = result["ram"]
    print("\n=== Summary ===")
    print(f"Ready in {_fmt_s(timing.get('import_wall_to_ready'))}")
    if timing.get("wall_to_geom_ready") is not None:
        print(f"Geom warm ready at {_fmt_s(timing.get('wall_to_geom_ready'))}")
    print(f"RSS at ready: {_fmt_bytes(ram.get('rss_at_ready_bytes'))}")
    print(f"RSS idle (hosting): {_fmt_bytes(ram.get('rss_idle_end_bytes'))}")
    print(f"Peak overall: {_fmt_bytes(ram.get('peak_overall_bytes'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(parent_main())
