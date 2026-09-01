#!/usr/bin/env python3
"""
Production vs local HTTP /route latency, compared to 22 Jul 2026 in-process Numba A*.

Hits GET /route for test_routes.txt × fast/safe (purpose=prefetch). Dual-leg A*
seconds = (timing_ms.fastest_astar + timing_ms.optimized_astar) / 1000 — the
server-side quantity comparable to local A* benches (Table H).

  cd c:\\London_Cycle_Maps
  python 4_backend_engine/bench_prod_vs_local_route.py

Writes:
  0_documentation/testing/prod_vs_local_route_latency.json
  0_documentation/testing/prod_vs_local_route_latency.md

Does not start Flask or load the graph. Local http://127.0.0.1:5000 is optional.
"""
from __future__ import annotations

import json
import socket
import ssl
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "4_backend_engine"
REPORT_DIR = REPO_ROOT / "0_documentation" / "testing"
REPORT_MD = REPORT_DIR / "prod_vs_local_route_latency.md"
REPORT_JSON = REPORT_DIR / "prod_vs_local_route_latency.json"
JULY_JSON = REPORT_DIR / "csr_astar_phase_c_report.json"
JULY_MD = REPORT_DIR / "csr_astar_phase_c_report.md"

sys.path.insert(0, str(BACKEND_DIR))
from benchmark_array_costs import parse_test_routes  # noqa: E402

PROD_BASE = "https://app.tunedcycling.online/api"
LOCAL_BASE = "http://127.0.0.1:5000"
USER_AGENT = "thesis-route-bench/1.0"
TIMEOUT_S = 180.0
SLEEP_BETWEEN_S = 2.2
RETRY_429_SLEEP_S = 20.0
RETRY_429_MAX = 3
PRESETS = (("fast", "preset_fast"), ("safe", "preset_safe"))
HEADLINE_ROUTE_NUMS = (1, 10)


def _jsonable(x):
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (str, int, float, bool)) or x is None:
        return x
    return str(x)


def _route_num(name: str) -> int | None:
    parts = name.strip().split()
    if len(parts) >= 2 and parts[0].lower() == "route":
        digits = "".join(c for c in parts[1] if c.isdigit())
        if digits:
            return int(digits)
    return None


def _tcp_open(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _ssl_context(unverified: bool = False) -> ssl.SSLContext:
    if unverified:
        return ssl._create_unverified_context()
    ctx = ssl.create_default_context()
    try:
        import certifi

        ctx.load_verify_locations(certifi.where())
    except ImportError:
        pass
    return ctx


def load_july_baselines(path: Path) -> tuple[dict, dict]:
    """Map (preset, route_num) -> {numba_s, numba_exp, route, legs}."""
    if not path.is_file():
        raise FileNotFoundError(f"22 Jul Numba report missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    by_key: dict[tuple[str, int], dict] = {}
    for row in payload.get("rows") or []:
        n = _route_num(str(row.get("route") or ""))
        preset = str(row.get("preset") or "")
        if n is None or preset not in ("fast", "safe"):
            continue
        rec = by_key.setdefault(
            (preset, n),
            {
                "route": row.get("route"),
                "numba_s": 0.0,
                "numba_exp": 0,
                "legs": {},
            },
        )
        rec["numba_s"] += float(row.get("numba_s") or 0.0)
        rec["numba_exp"] += int(row.get("numba_exp") or 0)
        rec["legs"][str(row.get("leg") or "")] = row
    return payload, by_key


def _extract_meta(body: dict) -> dict:
    meta = body.get("meta") if isinstance(body, dict) else None
    if not isinstance(meta, dict):
        meta = {}
    timing = meta.get("timing_ms") if isinstance(meta.get("timing_ms"), dict) else {}
    stats = meta.get("search_stats") if isinstance(meta.get("search_stats"), dict) else {}
    snap_ms = timing.get("snap")
    fast_ms = timing.get("fastest_astar")
    opt_ms = timing.get("optimized_astar")
    total_ms = timing.get("total")
    exp_fast = stats.get("fastest_expansions")
    exp_opt = stats.get("optimized_expansions")
    dual_ms = None
    if isinstance(fast_ms, (int, float)) and isinstance(opt_ms, (int, float)):
        dual_ms = float(fast_ms) + float(opt_ms)
    dual_s = None if dual_ms is None else dual_ms / 1000.0
    exp_sum = None
    if isinstance(exp_fast, (int, float)) and isinstance(exp_opt, (int, float)):
        exp_sum = int(exp_fast) + int(exp_opt)
    return {
        "snap_ms": None if snap_ms is None else float(snap_ms),
        "fastest_astar_ms": None if fast_ms is None else float(fast_ms),
        "optimized_astar_ms": None if opt_ms is None else float(opt_ms),
        "total_ms": None if total_ms is None else float(total_ms),
        "dual_leg_astar_s": dual_s,
        "fastest_expansions": None if exp_fast is None else int(exp_fast),
        "optimized_expansions": None if exp_opt is None else int(exp_opt),
        "expansions_sum": exp_sum,
        "numba_astar": meta.get("numba_astar"),
        "csr_astar": meta.get("csr_astar"),
        "array_costs": meta.get("array_costs"),
        "live_applied": meta.get("live_applied"),
        "geom_preparse": _jsonable(meta.get("geom_preparse")),
        "heuristic_epsilon": meta.get("heuristic_epsilon"),
        "fastest_heuristic_epsilon": meta.get("fastest_heuristic_epsilon"),
        "algorithm": meta.get("algorithm"),
        "preset": meta.get("preset"),
        "active_profile_id": meta.get("active_profile_id"),
        "purpose": meta.get("purpose"),
        "navigate": meta.get("navigate"),
    }


def _is_conn_refused(exc: BaseException) -> bool:
    if isinstance(exc, ConnectionRefusedError):
        return True
    reason = getattr(exc, "reason", None)
    if isinstance(reason, ConnectionRefusedError):
        return True
    errno = getattr(reason, "errno", None) or getattr(exc, "errno", None)
    return errno in (10061, 111, 61)  # Win refused, Linux, macOS


def http_get_json(
    url: str,
    *,
    timeout: float,
    ssl_ctx: ssl.SSLContext | None,
) -> dict:
    """GET url. Returns status/body/wall; does not retry."""
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
        method="GET",
    )
    kwargs: dict = {"timeout": timeout}
    if url.startswith("https://") and ssl_ctx is not None:
        kwargs["context"] = ssl_ctx
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, **kwargs) as resp:
            raw = resp.read()
            status = int(resp.status)
            try:
                body = json.loads(raw.decode("utf-8")) if raw else None
            except json.JSONDecodeError as exc:
                wall = time.perf_counter() - t0
                return {
                    "ok": False,
                    "status": status,
                    "body": None,
                    "wall_s": wall,
                    "error": f"JSON decode failed: {exc}",
                    "error_kind": "json",
                }
            wall = time.perf_counter() - t0
            return {
                "ok": status == 200 and isinstance(body, dict) and body.get("status") == "success",
                "status": status,
                "body": body,
                "wall_s": wall,
                "error": None
                if status == 200
                else f"HTTP {status}",
                "error_kind": None if status == 200 else "http",
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read() if exc.fp is not None else b""
        try:
            body = json.loads(raw.decode("utf-8")) if raw else None
        except (json.JSONDecodeError, UnicodeDecodeError):
            body = None
        wall = time.perf_counter() - t0
        kind = "http_429" if exc.code == 429 else "http"
        return {
            "ok": False,
            "status": int(exc.code),
            "body": body,
            "wall_s": wall,
            "error": f"HTTP {exc.code}",
            "error_kind": kind,
        }
    except TimeoutError as exc:
        return {
            "ok": False,
            "status": None,
            "body": None,
            "wall_s": time.perf_counter() - t0,
            "error": f"timeout: {exc}",
            "error_kind": "timeout",
        }
    except urllib.error.URLError as exc:
        wall = time.perf_counter() - t0
        kind = "conn_refused" if _is_conn_refused(exc) else "url"
        if isinstance(getattr(exc, "reason", None), TimeoutError) or isinstance(
            getattr(exc, "reason", None), socket.timeout
        ):
            kind = "timeout"
        return {
            "ok": False,
            "status": None,
            "body": None,
            "wall_s": wall,
            "error": str(exc.reason if exc.reason is not None else exc),
            "error_kind": kind,
        }
    except (ssl.SSLError, socket.timeout) as exc:
        kind = "timeout" if isinstance(exc, socket.timeout) else "ssl"
        return {
            "ok": False,
            "status": None,
            "body": None,
            "wall_s": time.perf_counter() - t0,
            "error": f"{type(exc).__name__}: {exc}",
            "error_kind": kind,
        }


def route_url(base: str, route: dict, profile_id: str) -> str:
    qs = urllib.parse.urlencode(
        {
            "start_lat": route["start_lat"],
            "start_lon": route["start_lon"],
            "end_lat": route["end_lat"],
            "end_lon": route["end_lon"],
            "profile_id": profile_id,
            "bike_type": "standard",
            "purpose": "prefetch",
        }
    )
    return f"{base.rstrip('/')}/route?{qs}"


def fetch_with_retries(
    url: str,
    *,
    ssl_ctx: ssl.SSLContext | None,
    label: str,
) -> dict:
    last = None
    retries_429 = 0
    for attempt in range(1 + RETRY_429_MAX):
        last = http_get_json(url, timeout=TIMEOUT_S, ssl_ctx=ssl_ctx)
        last["attempt"] = attempt + 1
        last["retries_429"] = retries_429
        if last.get("error_kind") != "http_429":
            return last
        retries_429 += 1
        if attempt >= RETRY_429_MAX:
            last["retries_429"] = retries_429
            print(f"    {label}: HTTP 429 after {retries_429} retries", flush=True)
            return last
        print(
            f"    {label}: HTTP 429 — sleep {RETRY_429_SLEEP_S:.0f}s "
            f"(retry {retries_429}/{RETRY_429_MAX})",
            flush=True,
        )
        time.sleep(RETRY_429_SLEEP_S)
    return last or {
        "ok": False,
        "status": None,
        "body": None,
        "wall_s": 0.0,
        "error": "no attempt",
        "error_kind": "internal",
        "attempt": 0,
        "retries_429": retries_429,
    }


def _pack_row(
    *,
    base_id: str,
    base: str,
    route: dict,
    preset: str,
    profile_id: str,
    measured: bool,
    result: dict,
    july: dict | None,
) -> dict:
    meta = _extract_meta(result.get("body") or {}) if result.get("body") else _extract_meta({})
    dual = meta.get("dual_leg_astar_s")
    july_s = None if not july else float(july["numba_s"])
    july_exp = None if not july else int(july["numba_exp"])
    ratio = None
    if isinstance(dual, (int, float)) and july_s and july_s > 0:
        ratio = float(dual) / july_s
    return {
        "base_id": base_id,
        "base": base,
        "measured": measured,
        "route": route["name"],
        "route_num": _route_num(route["name"]),
        "preset": preset,
        "profile_id": profile_id,
        "ok": bool(result.get("ok")),
        "http_status": result.get("status"),
        "http_wall_s": result.get("wall_s"),
        "error": result.get("error"),
        "error_kind": result.get("error_kind"),
        "attempt": result.get("attempt"),
        "retries_429": result.get("retries_429") or 0,
        "prod_dual_leg_astar_s": dual if base_id == "production" else None,
        "dual_leg_astar_s": dual,
        "july_numba_dual_leg_s": july_s,
        "ratio_prod_over_july": ratio if base_id == "production" else None,
        "ratio_http_over_july": ratio,
        "expansions_sum": meta.get("expansions_sum"),
        "july_numba_expansions": july_exp,
        "snap_ms": meta.get("snap_ms"),
        "timing_ms": {
            "snap": meta.get("snap_ms"),
            "fastest_astar": meta.get("fastest_astar_ms"),
            "optimized_astar": meta.get("optimized_astar_ms"),
            "total": meta.get("total_ms"),
        },
        "search_stats": {
            "fastest_expansions": meta.get("fastest_expansions"),
            "optimized_expansions": meta.get("optimized_expansions"),
        },
        "numba_astar": meta.get("numba_astar"),
        "csr_astar": meta.get("csr_astar"),
        "array_costs": meta.get("array_costs"),
        "live_applied": meta.get("live_applied"),
        "geom_preparse": meta.get("geom_preparse"),
        "heuristic_epsilon": meta.get("heuristic_epsilon"),
        "fastest_heuristic_epsilon": meta.get("fastest_heuristic_epsilon"),
        "algorithm": meta.get("algorithm"),
        "meta_preset": meta.get("preset"),
        "active_profile_id": meta.get("active_profile_id"),
        "purpose": meta.get("purpose"),
        "navigate": meta.get("navigate"),
    }


def _run_base(
    *,
    base_id: str,
    base: str,
    routes: list[dict],
    july_by_key: dict,
    ssl_ctx: ssl.SSLContext | None,
) -> tuple[list[dict], list[dict]]:
    """Warmup (route 1 safe) then 11×2 measured. Returns (warmup_rows, measured_rows)."""
    warmup_rows: list[dict] = []
    measured: list[dict] = []
    warm_route = routes[0]
    warm_preset, warm_pid = "safe", "preset_safe"
    warm_url = route_url(base, warm_route, warm_pid)
    print(f"  warmup {base_id}: {warm_route['name']} {warm_preset}", flush=True)
    warm_res = fetch_with_retries(
        warm_url, ssl_ctx=ssl_ctx, label=f"{base_id} warmup"
    )
    if warm_res.get("error_kind") == "conn_refused":
        print(f"  {base_id}: connection refused during warmup", flush=True)
        raise ConnectionRefusedError(warm_res.get("error") or "connection refused")
    july = july_by_key.get((warm_preset, _route_num(warm_route["name"]) or 1))
    warmup_rows.append(
        _pack_row(
            base_id=base_id,
            base=base,
            route=warm_route,
            preset=warm_preset,
            profile_id=warm_pid,
            measured=False,
            result=warm_res,
            july=july,
        )
    )
    if warm_res.get("error_kind") == "ssl":
        raise ssl.SSLError(warm_res.get("error") or "TLS failed")
    dual = warmup_rows[-1].get("dual_leg_astar_s")
    wall = warm_res.get("wall_s") or 0.0
    dual_txt = "n/a" if dual is None else f"{dual:.3f}s"
    print(
        f"    warmup ok={warm_res.get('ok')} wall={wall:.3f}s dualA*={dual_txt}",
        flush=True,
    )
    time.sleep(SLEEP_BETWEEN_S)

    jobs = [(rt, p, pid) for rt in routes for p, pid in PRESETS]
    for i, (rt, preset, pid) in enumerate(jobs, start=1):
        url = route_url(base, rt, pid)
        print(f"  [{i}/{len(jobs)}] {base_id} {preset} {rt['name']}", flush=True)
        res = fetch_with_retries(url, ssl_ctx=ssl_ctx, label=f"{base_id} {preset}")
        if res.get("error_kind") == "conn_refused":
            raise ConnectionRefusedError(res.get("error") or "connection refused")
        n = _route_num(rt["name"])
        july = july_by_key.get((preset, n)) if n is not None else None
        row = _pack_row(
            base_id=base_id,
            base=base,
            route=rt,
            preset=preset,
            profile_id=pid,
            measured=True,
            result=res,
            july=july,
        )
        measured.append(row)
        dual = row.get("dual_leg_astar_s")
        july_s = row.get("july_numba_dual_leg_s")
        ratio = row.get("ratio_http_over_july")
        dual_txt = "n/a" if dual is None else f"{dual:.3f}s"
        july_txt = "n/a" if july_s is None else f"{july_s:.3f}s"
        ratio_txt = "n/a" if ratio is None else f"{ratio:.2f}"
        wall = row.get("http_wall_s") or 0.0
        print(
            f"    ok={row['ok']} dualA*={dual_txt} july={july_txt} "
            f"ratio={ratio_txt} wall={wall:.3f}s exp={row['expansions_sum']}",
            flush=True,
        )
        if i < len(jobs):
            time.sleep(SLEEP_BETWEEN_S)
    return warmup_rows, measured


def _fmt(v, digits=3, dash="—"):
    if v is None:
        return dash
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int) and not isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def _uniq(values: list) -> list:
    out = []
    for v in values:
        if v not in out:
            out.append(v)
    return out


def _write_reports(payload: dict) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(
        json.dumps(_jsonable(payload), indent=2), encoding="utf-8"
    )

    prod_rows = [r for r in payload["rows"] if r["base_id"] == "production" and r["measured"]]
    local_http = [
        r for r in payload["rows"] if r["base_id"] == "local" and r["measured"]
    ]
    summary = payload["summary"]
    flags = payload["production_flags"]

    def table_rows(rows: list[dict]) -> list[str]:
        lines = [
            "| Route | Preset | Prod dual-leg A* s | 22 Jul Numba dual-leg A* s | Ratio prod/local | Prod exp (fast+opt) | 22 Jul exp | HTTP wall s | Snap ms |",
            "|-------|--------|-------------------:|---------------------------:|-----------------:|--------------------:|-----------:|------------:|--------:|",
        ]
        for r in rows:
            lines.append(
                f"| {r['route']} | {r['preset']} | "
                f"{_fmt(r.get('dual_leg_astar_s'))} | "
                f"{_fmt(r.get('july_numba_dual_leg_s'))} | "
                f"{_fmt(r.get('ratio_http_over_july'), 2)} | "
                f"{_fmt(r.get('expansions_sum'), dash='—')} | "
                f"{_fmt(r.get('july_numba_expansions'), dash='—')} | "
                f"{_fmt(r.get('http_wall_s'))} | "
                f"{_fmt(r.get('snap_ms'), 1)} |"
            )
        return lines

    headlines = [
        r
        for r in prod_rows
        if r.get("route_num") in HEADLINE_ROUTE_NUMS
    ]
    headlines.sort(key=lambda r: (r.get("route_num") or 0, 0 if r["preset"] == "fast" else 1))

    lines = [
        "# Production vs local HTTP `/route` latency",
        "",
        f"Generated: {payload['generated_at']}",
        f"Production base: `{payload['prod_base']}`",
        f"Local Flask base: `{payload['local_base']}` "
        f"({'skipped — connection refused / not listening' if payload['local_skipped'] else 'reached'})",
        f"22 Jul Numba report: `{JULY_JSON.relative_to(REPO_ROOT).as_posix()}` "
        f"(generated {payload['july_generated_at']})",
        f"Warmup: one discarded GET (fixture 1, preset safe) per reached base; "
        f"then 22 measured requests (11 routes × fast/safe), repeats=1.",
        f"purpose=`prefetch` (not `commit`); bike_type=`standard`; no vias, no depart_at, navigate unset.",
        "",
        "## Production flags",
        "",
        f"- `numba_astar`: {flags['numba_astar']}",
        f"- `csr_astar`: {flags['csr_astar']}",
        f"- `array_costs`: {flags['array_costs']}",
        f"- `live_applied`: {flags['live_applied']}",
        f"- `algorithm`: {flags['algorithm']}",
        f"- `heuristic_epsilon` (optimized): {flags['heuristic_epsilon']}",
        f"- `fastest_heuristic_epsilon`: {flags['fastest_heuristic_epsilon']}",
        f"- `geom_preparse`: {flags['geom_preparse']}",
        f"- TLS: {payload['tls_note']}",
        "",
        "## Headline fixtures",
        "",
        "Fixture 1 Imperial→King's Cross and fixture 10 Bromley→Ealing, Fast and Safe.",
        "",
    ]
    lines.extend(table_rows(headlines))
    lines.extend(
        [
            "",
            "## Summary (production HTTP A* vs 22 Jul in-process Numba)",
            "",
            f"- Measured production rows: **{summary['prod_ok_n']}/{summary['prod_n']}** ok",
            f"- Mean prod/local A* ratio: **{_fmt(summary['mean_ratio'], 3)}**",
            f"- Median prod/local A* ratio: **{_fmt(summary['median_ratio'], 3)}**",
            f"- HTTP 429 events (including retried): {summary['n_429']}",
            f"- Timeouts: {summary['n_timeout']}",
            f"- Other failures: {summary['n_fail_other']}",
            f"- Local Flask skipped: {str(payload['local_skipped']).lower()}",
            "",
            "## All 22 production rows",
            "",
        ]
    )
    lines.extend(table_rows(prod_rows))
    lines.extend(
        [
            "",
            "## Comparability",
            "",
            "HTTP `meta.timing_ms.fastest_astar` and `meta.timing_ms.optimized_astar` are "
            "server-side A* wall times. Their sum (converted to seconds) is the quantity "
            "compared to the 22 Jul in-process Numba dual-leg times. That comparison is "
            "valid as an A*-only metric.",
            "",
            "Client `http_wall_s` is not comparable to the Numba benches. It includes RTT, "
            "TLS, JSON serialisation of full path geometry, snap, overlay assembly, and "
            "response download.",
            "",
            "The 22 Jul Phase C run used `SKIP_DISRUPTION_FETCH=1` (no live closures in the "
            "cost overlay). Production typically has `live_applied=true`, so expansion counts "
            "need not match. Expansion mismatches are documented, not treated as a bench bug, "
            "when live closures are on.",
            "",
            "The 22 Jul numbers are in-process Numba CSR A* (`benchmark_csr_numba.py`), not "
            "Flask HTTP. ε_opt=0.75, ε_fast=0, repeats=1. This script does not start Flask "
            "and does not load the graph locally.",
            "",
        ]
    )
    if local_http:
        lines.extend(
            [
                "## Local Flask HTTP (optional, not the 22 Jul baseline)",
                "",
                "These rows are live `http://127.0.0.1:5000` `/route` timings if the process "
                "was already listening. They are not the 22 Jul Numba column.",
                "",
            ]
        )
        lines.extend(table_rows(local_http))
        lines.append("")
    lines.append(f"JSON: `{REPORT_JSON.relative_to(REPO_ROOT).as_posix()}`")
    lines.append("")
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT_MD}", flush=True)
    print(f"Wrote {REPORT_JSON}", flush=True)


def main() -> int:
    july_payload, july_by_key = load_july_baselines(JULY_JSON)
    routes = parse_test_routes()
    if len(routes) != 11:
        print(f"WARNING: expected 11 fixtures, got {len(routes)}", flush=True)

    generated_at = datetime.now(timezone.utc).isoformat()
    local_skipped = not _tcp_open("127.0.0.1", 5000)
    tls_unverified = False
    tls_note = "default SSL context"
    ssl_ctx = _ssl_context(unverified=False)

    all_rows: list[dict] = []
    warmup_all: list[dict] = []
    n_429 = 0
    n_timeout = 0
    n_fail_other = 0

    print(f"Production: {PROD_BASE}", flush=True)
    print(
        f"Local Flask: {LOCAL_BASE} "
        f"{'(skipped)' if local_skipped else '(listening)'}",
        flush=True,
    )

    try:
        w, m = _run_base(
            base_id="production",
            base=PROD_BASE,
            routes=routes,
            july_by_key=july_by_key,
            ssl_ctx=ssl_ctx,
        )
        warmup_all.extend(w)
        all_rows.extend(m)
    except ssl.SSLError as exc:
        err = str(exc)
        print(f"Production TLS error: {err} — retrying unverified", flush=True)
        tls_unverified = True
        tls_note = f"default SSL failed ({err}); retried with unverified context"
        ssl_ctx = _ssl_context(unverified=True)
        w, m = _run_base(
            base_id="production",
            base=PROD_BASE,
            routes=routes,
            july_by_key=july_by_key,
            ssl_ctx=ssl_ctx,
        )
        warmup_all.extend(w)
        all_rows.extend(m)
    except (ConnectionRefusedError, urllib.error.URLError) as exc:
        print(f"Production unreachable: {exc}", flush=True)
        tls_note = f"{tls_note}; production error: {exc}"

    # If the first production request failed on SSL inside fetch (not raised),
    # retry the whole production suite unverified when every row is ssl-failed.
    prod_measured = [r for r in all_rows if r["base_id"] == "production"]
    if (
        prod_measured
        and all(r.get("error_kind") == "ssl" for r in prod_measured)
        and not tls_unverified
    ):
        print("All production rows SSL-failed — retrying unverified", flush=True)
        tls_unverified = True
        tls_note = "verified TLS failed on requests; reran with unverified context"
        all_rows = [r for r in all_rows if r["base_id"] != "production"]
        warmup_all = [r for r in warmup_all if r["base_id"] != "production"]
        ssl_ctx = _ssl_context(unverified=True)
        w, m = _run_base(
            base_id="production",
            base=PROD_BASE,
            routes=routes,
            july_by_key=july_by_key,
            ssl_ctx=ssl_ctx,
        )
        warmup_all.extend(w)
        all_rows.extend(m)

    if not local_skipped:
        print("\nLocal Flask reachable — running the same 1+22 protocol", flush=True)
        try:
            w, m = _run_base(
                base_id="local",
                base=LOCAL_BASE,
                routes=routes,
                july_by_key=july_by_key,
                ssl_ctx=None,
            )
            warmup_all.extend(w)
            all_rows.extend(m)
        except ConnectionRefusedError:
            local_skipped = True
            print("Local Flask refused mid-run — remaining local requests skipped", flush=True)

    prod_rows = [r for r in all_rows if r["base_id"] == "production" and r["measured"]]
    for r in prod_rows:
        kind = r.get("error_kind")
        if r.get("retries_429"):
            n_429 += int(r["retries_429"])
        if kind == "http_429":
            n_429 += 1
        elif kind == "timeout":
            n_timeout += 1
        elif not r.get("ok"):
            n_fail_other += 1

    ratios = [
        r["ratio_http_over_july"]
        for r in prod_rows
        if r.get("ok") and isinstance(r.get("ratio_http_over_july"), (int, float))
    ]
    ok_flags = [r for r in prod_rows if r.get("ok")]

    def flag_summary(key: str):
        vals = _uniq([r.get(key) for r in ok_flags])
        if not vals:
            return "n/a (no successful production rows)"
        if len(vals) == 1:
            v = vals[0]
            if isinstance(v, bool):
                return "true" if v else "false"
            return v
        return vals

    mean_ratio = round(statistics.mean(ratios), 3) if ratios else None
    median_ratio = round(statistics.median(ratios), 3) if ratios else None

    payload = {
        "generated_at": generated_at,
        "prod_base": PROD_BASE,
        "local_base": LOCAL_BASE,
        "local_skipped": local_skipped,
        "local_reachable": not local_skipped,
        "tls_unverified": tls_unverified,
        "tls_note": tls_note,
        "user_agent": USER_AGENT,
        "timeout_s": TIMEOUT_S,
        "sleep_between_s": SLEEP_BETWEEN_S,
        "repeats": 1,
        "purpose": "prefetch",
        "bike_type": "standard",
        "warmup": "route 1 safe, discarded",
        "july_report": str(JULY_JSON.as_posix()),
        "july_generated_at": july_payload.get("generated_at"),
        "july_eps": july_payload.get("eps"),
        "july_eps_fast": july_payload.get("eps_fast"),
        "july_repeats": july_payload.get("repeats"),
        "production_flags": {
            "numba_astar": flag_summary("numba_astar"),
            "csr_astar": flag_summary("csr_astar"),
            "array_costs": flag_summary("array_costs"),
            "live_applied": flag_summary("live_applied"),
            "algorithm": flag_summary("algorithm"),
            "heuristic_epsilon": flag_summary("heuristic_epsilon"),
            "fastest_heuristic_epsilon": flag_summary("fastest_heuristic_epsilon"),
            "geom_preparse": flag_summary("geom_preparse"),
        },
        "summary": {
            "prod_n": len(prod_rows),
            "prod_ok_n": sum(1 for r in prod_rows if r.get("ok")),
            "mean_ratio": mean_ratio,
            "median_ratio": median_ratio,
            "n_429": n_429,
            "n_timeout": n_timeout,
            "n_fail_other": n_fail_other,
            "ratios_n": len(ratios),
        },
        "warmup_rows": warmup_all,
        "rows": all_rows,
    }
    _write_reports(payload)

    print("\n=== Headline (production dual-leg A* vs 22 Jul Numba) ===", flush=True)
    for r in prod_rows:
        if r.get("route_num") in HEADLINE_ROUTE_NUMS:
            print(
                f"  r{r.get('route_num')} {r['preset']}: "
                f"prod={_fmt(r.get('dual_leg_astar_s'))}s  "
                f"july={_fmt(r.get('july_numba_dual_leg_s'))}s  "
                f"ratio={_fmt(r.get('ratio_http_over_july'), 2)}",
                flush=True,
            )
    print(
        f"Mean ratio={_fmt(mean_ratio, 3)}  median={_fmt(median_ratio, 3)}  "
        f"numba_astar={payload['production_flags']['numba_astar']}  "
        f"live_applied={payload['production_flags']['live_applied']}",
        flush=True,
    )
    return 0 if payload["summary"]["prod_ok_n"] == payload["summary"]["prod_n"] else 1


if __name__ == "__main__":
    sys.exit(main())
