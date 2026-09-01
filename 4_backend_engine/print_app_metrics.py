"""
Print aggregate product metrics and all reported bugs.

Each run appends a snapshot to:
  0_documentation/app_metrics_history.jsonl  (plottable time series)
and rewrites:
  0_documentation/app_metrics.md             (human-readable + deltas)

Usage (from 4_backend_engine, with env loaded as usual):
  python print_app_metrics.py

Uses Supabase when SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY are set;
otherwise reads local app_metrics.json / bug_reports.json.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

import app_metrics
import bug_reports
import ride_reports

_DOCS_DIR = Path(__file__).resolve().parent.parent / "0_documentation"
_HISTORY_PATH = _DOCS_DIR / "app_metrics_history.jsonl"
_MARKDOWN_PATH = _DOCS_DIR / "app_metrics.md"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fmt_delta(n: float | int, *, as_int: bool = False) -> str:
    if as_int:
        n = int(round(n))
        return f"{n:+,}" if n != 0 else "0"
    if abs(n) < 0.05:
        return "0"
    return f"{n:+,.1f}"


def _ride_report_week() -> tuple[int, dict[str, int], str | None]:
    """
    Counts only. Ride reports carry rider locations, so nothing here reads
    lat/lon or payload — a metrics dump must not become a movement log.
    """
    since = datetime.now(timezone.utc) - timedelta(days=7)
    rows, err = ride_reports.list_ride_reports(since=since)
    if err:
        return 0, {}, err
    by_category: dict[str, int] = {}
    for row in rows:
        key = str(row.get("category") or "unknown")
        by_category[key] = by_category.get(key, 0) + 1
    return len(rows), by_category, None


def _fmt_categories(by_category: dict[str, int]) -> str:
    if not by_category:
        return "(none)"
    return ", ".join(f"{k} {v:,}" for k, v in sorted(by_category.items()))


def _load_history() -> list[dict]:
    if not _HISTORY_PATH.exists():
        return []
    rows: list[dict] = []
    try:
        for line in _HISTORY_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
    except OSError:
        return []
    return rows


def _append_history(row: dict) -> None:
    _DOCS_DIR.mkdir(parents=True, exist_ok=True)
    with _HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_markdown(history: list[dict], bugs: list[dict], bugs_err: str | None) -> None:
    latest = history[-1] if history else None
    prev = history[-2] if len(history) >= 2 else None
    lines = [
        "# TUNE app metrics history",
        "",
        "Updated by `4_backend_engine/print_app_metrics.py`.",
        f"Machine-readable series: [`app_metrics_history.jsonl`](app_metrics_history.jsonl).",
        "",
    ]
    if latest:
        dist_km = float(latest["optimized_distance_m"]) / 1000.0
        lines.extend(
            [
                "## Latest",
                "",
                f"- **recorded_at:** {latest.get('recorded_at') or '—'}",
                f"- **backend:** {latest.get('backend') or '—'}",
                f"- **sessions:** {int(latest['sessions']):,}",
                f"- **routes_computed:** {int(latest['routes_computed']):,}",
                f"- **unique_route_clients:** "
                f"{int(latest.get('unique_route_clients') or 0):,}"
                f" (distinct hashed IPs that committed a route; IPs are not stored)",
                f"- **optimized_distance:** {dist_km:,.1f} km "
                f"({float(latest['optimized_distance_m']):,.0f} m)",
                f"- **bug_reports:** {int(latest.get('bug_reports') or 0):,}",
                f"- **ride_reports (last 7 days):** "
                f"{int(latest.get('ride_reports_7d') or 0):,} — "
                f"{_fmt_categories(latest.get('ride_reports_7d_by_category') or {})}",
                "",
            ]
        )
        if prev:
            d = latest.get("delta") or {}
            lines.extend(
                [
                    f"### Delta since previous run ({prev.get('recorded_at') or '—'})",
                    "",
                    f"- sessions: {_fmt_delta(d.get('sessions', 0), as_int=True)}",
                    f"- routes_computed: {_fmt_delta(d.get('routes_computed', 0), as_int=True)}",
                    f"- unique_route_clients: "
                    f"{_fmt_delta(d.get('unique_route_clients', 0), as_int=True)}",
                    f"- optimized_distance_km: "
                    f"{_fmt_delta(float(d.get('optimized_distance_m', 0)) / 1000.0)}",
                    f"- bug_reports: {_fmt_delta(d.get('bug_reports', 0), as_int=True)}",
                    "",
                ]
            )
        else:
            lines.extend(["### Delta", "", "_First snapshot — no previous run._", ""])

    lines.extend(
        [
            "## Progression",
            "",
            "| recorded_at (UTC) | sessions | Δ | routes | Δ | unique | Δ | distance km | Δ km | bugs | Δ |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in reversed(history):
        d = row.get("delta") or {}
        dist_km = float(row.get("optimized_distance_m") or 0) / 1000.0
        d_km = float(d.get("optimized_distance_m") or 0) / 1000.0
        lines.append(
            "| {at} | {s:,} | {ds} | {r:,} | {dr} | {u:,} | {du} | {km:,.1f} | {dkm} | {b:,} | {db} |".format(
                at=row.get("recorded_at") or "—",
                s=int(row.get("sessions") or 0),
                ds=_fmt_delta(d.get("sessions", 0), as_int=True) if d else "—",
                r=int(row.get("routes_computed") or 0),
                dr=_fmt_delta(d.get("routes_computed", 0), as_int=True) if d else "—",
                u=int(row.get("unique_route_clients") or 0),
                du=_fmt_delta(d.get("unique_route_clients", 0), as_int=True) if d else "—",
                km=dist_km,
                dkm=_fmt_delta(d_km) if d else "—",
                b=int(row.get("bug_reports") or 0),
                db=_fmt_delta(d.get("bug_reports", 0), as_int=True) if d else "—",
            )
        )

    lines.extend(["", "## Bug reports (current)", ""])
    if bugs_err:
        lines.append(f"_Error loading bugs: {bugs_err}_")
    elif not bugs:
        lines.append("_(none)_")
    else:
        for i, row in enumerate(bugs, start=1):
            created = row.get("created_at") or "—"
            msg = (row.get("message") or "").strip() or "(empty)"
            page = row.get("page_url") or "—"
            uid = row.get("user_id") or "anon"
            lines.append(f"{i}. **{created}** — user `{uid}` — {page}")
            lines.append(f"   - {msg}")
            lines.append("")

    _DOCS_DIR.mkdir(parents=True, exist_ok=True)
    _MARKDOWN_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _print_bugs(rows: list[dict], err: str | None) -> None:
    print()
    print(f"Bug reports ({len(rows)})")
    if err:
        print(f"  error: {err}")
        return
    if not rows:
        print("  (none)")
        return
    for i, row in enumerate(rows, start=1):
        created = row.get("created_at") or "—"
        msg = (row.get("message") or "").strip() or "(empty)"
        page = row.get("page_url") or "—"
        uid = row.get("user_id") or "anon"
        theme = row.get("theme") or "—"
        viewport = row.get("viewport") or "—"
        version = row.get("app_version") or "—"
        print(f"  [{i}] {created}")
        print(f"      id:       {row.get('id') or '—'}")
        print(f"      user:     {uid}")
        print(f"      page:     {page}")
        print(f"      theme:    {theme}  viewport: {viewport}  version: {version}")
        print(f"      message:  {msg}")


def main() -> None:
    snap = app_metrics.snapshot()
    bugs, bugs_err = bug_reports.list_bug_reports()

    sessions = int(snap.get("sessions") or 0)
    routes = int(snap.get("routes_computed") or 0)
    unique_clients = int(snap.get("unique_route_clients") or 0)
    dist_m = float(snap.get("optimized_distance_m") or 0.0)
    dist_km = dist_m / 1000.0
    backend = snap.get("backend") or ("error" if snap.get("error") else "?")
    updated = snap.get("updated_at") or "—"
    bug_n = len(bugs)
    ride_n, ride_by_category, ride_err = _ride_report_week()

    history = _load_history()
    prev = history[-1] if history else None
    delta = None
    if prev:
        delta = {
            "sessions": sessions - int(prev.get("sessions") or 0),
            "routes_computed": routes - int(prev.get("routes_computed") or 0),
            "unique_route_clients": unique_clients
            - int(prev.get("unique_route_clients") or 0),
            "optimized_distance_m": dist_m - float(prev.get("optimized_distance_m") or 0),
            "bug_reports": bug_n - int(prev.get("bug_reports") or 0),
            "since": prev.get("recorded_at"),
        }

    row = {
        "recorded_at": _utc_now(),
        "backend": backend,
        "sessions": sessions,
        "routes_computed": routes,
        "unique_route_clients": unique_clients,
        "optimized_distance_m": dist_m,
        "bug_reports": bug_n,
        # Rolling window, not cumulative — deliberately out of the delta table.
        "ride_reports_7d": ride_n,
        "ride_reports_7d_by_category": ride_by_category,
        "source_updated_at": updated,
    }
    if snap.get("error"):
        row["error"] = str(snap["error"])
    if delta is not None:
        row["delta"] = delta

    _append_history(row)
    history.append(row)
    _write_markdown(history, bugs, bugs_err)

    print("TUNE app metrics")
    print(f"  backend:              {backend}")
    if snap.get("path"):
        print(f"  path:                 {snap['path']}")
    if snap.get("error"):
        print(f"  error:                {snap['error']}")
        err_s = str(snap["error"])
        if "app_metrics" in err_s and (
            "PGRST205" in err_s or "schema cache" in err_s or "does not exist" in err_s
        ):
            print(
                "  hint:                 Run supabase_sql/migrations/004_app_metrics.sql "
                "in the Supabase SQL editor, then restart Flask."
            )
        if "unique_route_clients" in err_s:
            print(
                "  hint:                 Run supabase_sql/migrations/"
                "006_app_metrics_unique_clients.sql in the Supabase SQL editor, "
                "then restart Flask."
            )
    print(f"  sessions:             {sessions:,}")
    print(f"  routes_computed:      {routes:,}")
    print(f"  unique_route_clients:  {unique_clients:,}")
    print(f"  optimized_distance:   {dist_km:,.1f} km ({dist_m:,.0f} m)")
    print(f"  bug_reports:          {bug_n:,}")
    if ride_err:
        print(f"  ride_reports (7d):    error: {ride_err}")
    else:
        print(f"  ride_reports (7d):    {ride_n:,}  [{_fmt_categories(ride_by_category)}]")
    print(f"  updated_at:           {updated}")

    if delta is None:
        print()
        print("Delta since previous run")
        print("  (first snapshot — no previous run)")
    else:
        print()
        print(f"Delta since previous run ({delta.get('since') or '—'})")
        print(f"  sessions:             {_fmt_delta(delta['sessions'], as_int=True)}")
        print(f"  routes_computed:      {_fmt_delta(delta['routes_computed'], as_int=True)}")
        print(
            f"  unique_route_clients:  "
            f"{_fmt_delta(delta['unique_route_clients'], as_int=True)}"
        )
        print(
            f"  optimized_distance:   "
            f"{_fmt_delta(delta['optimized_distance_m'] / 1000.0)} km"
        )
        print(f"  bug_reports:          {_fmt_delta(delta['bug_reports'], as_int=True)}")

    print()
    print(f"Saved → {_MARKDOWN_PATH}")
    print(f"Append → {_HISTORY_PATH}")

    _print_bugs(bugs, bugs_err)


if __name__ == "__main__":
    main()
