#!/usr/bin/env python3
"""
Re-score Phase B climb rates on paths from presets_aligned_time_compare.json
(no re-route — geometries fixed at SIGNAL_WAIT=7.5).

Compares climb s/m:
  1.0   — former Phase B default
  2.58  — Miotti & Hellweg standard bike (SSRN 5050670)
  1.54  — Miotti & Hellweg e-bike

Also reports cruise at bike-type speeds (standard 20 / ebike 25 km/h) with
matching climb rates (full bike-aware Phase B sketch).

  cd c:\\London_Cycle_Maps
  python 4_backend_engine/compare_phase_b_climb_rates.py

Writes:
  0_documentation/testing/phase_b_climb_rates_compare.{md,json}
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "4_backend_engine"
REPORT_DIR = REPO_ROOT / "0_documentation" / "testing"
SRC_JSON = REPORT_DIR / "presets_aligned_time_compare.json"
REPORT_MD = REPORT_DIR / "phase_b_climb_rates_compare.md"
REPORT_JSON = REPORT_DIR / "phase_b_climb_rates_compare.json"

sys.path.insert(0, str(BACKEND_DIR))

import route_time_estimate as rte  # noqa: E402
from user_profiles import BIKE_SPEEDS_KMH  # noqa: E402

# Fixed cruise speed used in the aligned compare (for apples-to-apples climb-only Δ).
ALIGNED_SPEED_KMH = 20.0
CLIMB_RATES = {
    "legacy_1.0": 1.0,
    "miotti_standard_2.58": 2.58,
    "miotti_ebike_1.54": 1.54,
}


def phase_b(length_m, core, speed_kmh, climb_s_per_m: float) -> dict:
    cruise = rte.cruise_duration_min(length_m, speed_kmh, 1.0)
    ps = rte.PENALTY_SECONDS
    parts = {
        "signal": float(core.get("signal_count") or 0) * ps["signal"],
        "give_way": float(core.get("give_way_count") or 0) * ps["give_way"],
        "stop_sign": float(core.get("stop_sign_count") or 0) * ps["stop_sign"],
        "junction": float(core.get("junction_count") or 0) * ps["junction"],
        "calming": float(core.get("calming_count") or 0) * ps["calming"],
        "barrier": float(core.get("barrier_penalty_count") or 0) * ps["barrier"],
        "climb": float(core.get("elevation_gain") or 0) * climb_s_per_m,
    }
    pen_s = sum(parts.values())
    total = cruise + pen_s / 60.0
    api = rte.estimate_duration_min_phase_b(
        length_m,
        speed_kmh,
        signal_count=int(core.get("signal_count") or 0),
        give_way_count=int(core.get("give_way_count") or 0),
        stop_sign_count=int(core.get("stop_sign_count") or 0),
        junction_count=int(core.get("junction_count") or 0),
        calming_count=int(core.get("calming_count") or 0),
        barrier_penalty_count=int(core.get("barrier_penalty_count") or 0),
        elevation_gain=float(core.get("elevation_gain") or 0),
        climb_s_per_m=climb_s_per_m,
    )
    return {
        "cruise_min": round(cruise, 2),
        "penalty_min": round(pen_s / 60.0, 2),
        "climb_min": round(parts["climb"] / 60.0, 2),
        "duration_min": round(total, 2),
        "api_min": round(api, 2),
        "match": abs(api - total) <= 0.02,
        "parts_s": {k: round(v, 1) for k, v in parts.items()},
    }


def main() -> int:
    if not SRC_JSON.is_file():
        raise SystemExit(f"Missing {SRC_JSON} — run compare_presets_aligned_time.py first")

    src = json.loads(SRC_JSON.read_text(encoding="utf-8"))
    rows_in = [r for r in src["rows"] if r["preset"] in ("fastest", "fast", "safe", "leisure")]

    # Climb-only sensitivity @ 16 km/h (same cruise as aligned compare)
    scored = []
    for r in rows_in:
        core = r["core"]
        length = float(core["length_m"])
        entry = {
            "route": r["route"],
            "preset": r["preset"],
            "length_m": length,
            "elevation_gain": float(core.get("elevation_gain") or 0),
            "signal_count": int(core.get("signal_count") or 0),
            "by_climb": {},
        }
        for label, rate in CLIMB_RATES.items():
            entry["by_climb"][label] = phase_b(length, core, ALIGNED_SPEED_KMH, rate)
            if not entry["by_climb"][label]["match"]:
                raise SystemExit(f"API mismatch {r['route']} {r['preset']} {label}")
        scored.append(entry)

    def mean_b(preset: str, climb_label: str) -> float:
        vals = [
            e["by_climb"][climb_label]["duration_min"]
            for e in scored
            if e["preset"] == preset
        ]
        return round(mean(vals), 2)

    def wins(climb_label: str) -> tuple[int, int]:
        routes = sorted({e["route"] for e in scored})
        n_ok = 0
        for route in routes:
            by = {e["preset"]: e for e in scored if e["route"] == route}
            if (
                by["fast"]["by_climb"][climb_label]["duration_min"]
                <= by["safe"]["by_climb"][climb_label]["duration_min"]
            ):
                n_ok += 1
        return n_ok, len(routes)

    pivot = {}
    for label in CLIMB_RATES:
        w, n = wins(label)
        pivot[label] = {
            "climb_s_per_m": CLIMB_RATES[label],
            "mean_phase_b": {
                p: mean_b(p, label) for p in ("fastest", "fast", "safe", "leisure")
            },
            "fast_leq_safe": f"{w}/{n}",
            "mean_climb_min_fast": round(
                mean(
                    e["by_climb"][label]["climb_min"]
                    for e in scored
                    if e["preset"] == "fast"
                ),
                2,
            ),
            "mean_climb_min_safe": round(
                mean(
                    e["by_climb"][label]["climb_min"]
                    for e in scored
                    if e["preset"] == "safe"
                ),
                2,
            ),
        }

    # Flips: Fast loses @1.0 but wins @2.58 (or reverse)
    flips = []
    for route in sorted({e["route"] for e in scored}):
        by = {e["preset"]: e for e in scored if e["route"] == route}
        leg = (
            by["fast"]["by_climb"]["legacy_1.0"]["duration_min"]
            <= by["safe"]["by_climb"]["legacy_1.0"]["duration_min"]
        )
        mio = (
            by["fast"]["by_climb"]["miotti_standard_2.58"]["duration_min"]
            <= by["safe"]["by_climb"]["miotti_standard_2.58"]["duration_min"]
        )
        if leg != mio:
            flips.append(
                {
                    "route": route,
                    "fast_leq_safe_at_1.0": leg,
                    "fast_leq_safe_at_2.58": mio,
                    "delta_b_fast_minus_safe_1.0": round(
                        by["fast"]["by_climb"]["legacy_1.0"]["duration_min"]
                        - by["safe"]["by_climb"]["legacy_1.0"]["duration_min"],
                        2,
                    ),
                    "delta_b_fast_minus_safe_2.58": round(
                        by["fast"]["by_climb"]["miotti_standard_2.58"]["duration_min"]
                        - by["safe"]["by_climb"]["miotti_standard_2.58"]["duration_min"],
                        2,
                    ),
                    "elev_fast": by["fast"]["elevation_gain"],
                    "elev_safe": by["safe"]["elevation_gain"],
                }
            )

    # Bike-aware: cruise speed + climb rate together
    bike_cases = {
        "standard_15kmh_climb2.58": {
            "speed_kmh": BIKE_SPEEDS_KMH["standard"],
            "climb_s_per_m": 2.58,
            "bike_type": "standard",
        },
        "ebike_18kmh_climb1.54": {
            "speed_kmh": BIKE_SPEEDS_KMH["ebike"],
            "climb_s_per_m": 1.54,
            "bike_type": "ebike",
        },
        "road_21kmh_climb2.58": {
            "speed_kmh": BIKE_SPEEDS_KMH["road"],
            "climb_s_per_m": 2.58,
            "bike_type": "road",
        },
    }
    bike_pivot = {}
    for case, cfg in bike_cases.items():
        case_rows = []
        for r in rows_in:
            if r["preset"] not in ("fastest", "fast", "safe"):
                continue
            b = phase_b(
                float(r["core"]["length_m"]),
                r["core"],
                cfg["speed_kmh"],
                cfg["climb_s_per_m"],
            )
            case_rows.append({"preset": r["preset"], "route": r["route"], **b})
        means = {
            p: round(
                mean(x["duration_min"] for x in case_rows if x["preset"] == p),
                2,
            )
            for p in ("fastest", "fast", "safe")
        }
        routes = sorted({x["route"] for x in case_rows})
        w = sum(
            1
            for route in routes
            if next(x["duration_min"] for x in case_rows if x["route"] == route and x["preset"] == "fast")
            <= next(x["duration_min"] for x in case_rows if x["route"] == route and x["preset"] == "safe")
        )
        bike_pivot[case] = {
            **cfg,
            "mean_phase_b": means,
            "fast_leq_safe": f"{w}/{len(routes)}",
            "mean_fast_minus_safe": round(means["fast"] - means["safe"], 2),
            "mean_fast_minus_shortest": round(means["fast"] - means["fastest"], 2),
        }

    # Per-route table @ Miotti 2.58 / 16 km/h
    per_route = []
    for route in sorted({e["route"] for e in scored}, key=lambda s: int(s.split()[1].rstrip(":"))):
        by = {e["preset"]: e for e in scored if e["route"] == route}
        row = {"route": route}
        for p in ("fastest", "fast", "safe"):
            b1 = by[p]["by_climb"]["legacy_1.0"]
            b258 = by[p]["by_climb"]["miotti_standard_2.58"]
            row[p] = {
                "elev": by[p]["elevation_gain"],
                "B_1.0": b1["duration_min"],
                "B_2.58": b258["duration_min"],
                "climb_min_1.0": b1["climb_min"],
                "climb_min_2.58": b258["climb_min"],
                "delta_B_2.58_minus_1.0": round(b258["duration_min"] - b1["duration_min"], 2),
            }
        row["delta_fast_minus_safe_1.0"] = round(
            row["fast"]["B_1.0"] - row["safe"]["B_1.0"], 2
        )
        row["delta_fast_minus_safe_2.58"] = round(
            row["fast"]["B_2.58"] - row["safe"]["B_2.58"], 2
        )
        row["fast_leq_safe_1.0"] = row["fast"]["B_1.0"] <= row["safe"]["B_1.0"]
        row["fast_leq_safe_2.58"] = row["fast"]["B_2.58"] <= row["safe"]["B_2.58"]
        per_route.append(row)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_paths": str(SRC_JSON),
        "note": (
            "Paths frozen from aligned 7.5s compare. Climb rates only (and optional "
            "bike cruise speeds) change. Miotti & Hellweg SSRN 5050670: "
            "https://ssrn.com/abstract=5050670 — downhill does not significantly "
            "increase bike speed (no descent bonus)."
        ),
        "aligned_speed_kmh": ALIGNED_SPEED_KMH,
        "climb_rates": CLIMB_RATES,
        "citation": {
            "authors": "Miotti, Marco and Hellweg, Stefanie",
            "title": "Estimating Representative Door-to-Door Travel Times Using Open Network Data",
            "ssrn": "https://ssrn.com/abstract=5050670",
            "doi": "http://dx.doi.org/10.2139/ssrn.5050670",
            "climb_s_per_m_standard": 2.58,
            "climb_s_per_m_ebike": 1.54,
            "downhill_note": "Elevation loss does not lead to significantly higher travel speeds by bike",
        },
        "pivot_climb_at_16kmh": pivot,
        "flips_1.0_vs_2.58": flips,
        "bike_aware_phase_b": bike_pivot,
        "per_route_1.0_vs_2.58": per_route,
        "code_defaults": {
            "PENALTY_SECONDS.climb_per_metre": rte.PENALTY_SECONDS["climb_per_metre"],
            "CLIMB_SECONDS_PER_METRE_BY_BIKE": dict(rte.CLIMB_SECONDS_PER_METRE_BY_BIKE),
        },
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        "# Phase B climb rates — 1.0 vs Miotti 2.58 / 1.54",
        "",
        f"Generated: `{summary['generated_at']}`",
        "",
        "**Paths:** frozen from [`presets_aligned_time_compare.json`](presets_aligned_time_compare.json) "
        "(routed @ `SIGNAL_WAIT_SECONDS=7.5`).",
        "",
        "**Citation:** Miotti & Hellweg, *Estimating Representative Door-to-Door Travel Times "
        "Using Open Network Data*, SSRN [5050670](https://ssrn.com/abstract=5050670) "
        "([doi](http://dx.doi.org/10.2139/ssrn.5050670)).",
        "",
        "- Standard bike: **2.58 s** per metre elevation **gain**",
        "- E-bike: **1.54 s/m**",
        "- **Downhill:** elevation loss does **not** significantly raise bike speed → no descent bonus",
        "",
        "## Means @ 16 km/h (climb rate only)",
        "",
        "| Climb s/m | Fastest B | Fast B | Safe B | Leisure B | Fast≤Safe | Fast climb min | Safe climb min |",
        "|----------:|----------:|-------:|-------:|----------:|----------:|---------------:|---------------:|",
    ]
    for label, rate in CLIMB_RATES.items():
        p = pivot[label]
        m = p["mean_phase_b"]
        lines.append(
            f"| {rate} ({label}) | {m['fastest']} | **{m['fast']}** | {m['safe']} | "
            f"{m['leisure']} | {p['fast_leq_safe']} | {p['mean_climb_min_fast']} | "
            f"{p['mean_climb_min_safe']} |"
        )

    lines += [
        "",
        f"Δ Fast B (2.58 − 1.0) mean: "
        f"**{pivot['miotti_standard_2.58']['mean_phase_b']['fast'] - pivot['legacy_1.0']['mean_phase_b']['fast']:+.2f} min**",
        f"Δ Safe B (2.58 − 1.0) mean: "
        f"**{pivot['miotti_standard_2.58']['mean_phase_b']['safe'] - pivot['legacy_1.0']['mean_phase_b']['safe']:+.2f} min**",
        f"Δ (Fast−Safe) lead grows by "
        f"**{(pivot['legacy_1.0']['mean_phase_b']['fast'] - pivot['legacy_1.0']['mean_phase_b']['safe']) - (pivot['miotti_standard_2.58']['mean_phase_b']['fast'] - pivot['miotti_standard_2.58']['mean_phase_b']['safe']):+.2f} min** "
        f"(Fast’s relative advantage vs Safe increases because Fast climbs less).",
        "",
        "## Fast ≤ Safe flips (1.0 → 2.58)",
        "",
    ]
    if not flips:
        lines.append("None — same win set.")
    else:
        for f in flips:
            lines.append(
                f"- **{f['route']}**: Fast≤Safe {f['fast_leq_safe_at_1.0']} → "
                f"{f['fast_leq_safe_at_2.58']} "
                f"(ΔB F−S {f['delta_b_fast_minus_safe_1.0']:+} → "
                f"{f['delta_b_fast_minus_safe_2.58']:+}; "
                f"elev F/S {f['elev_fast']}/{f['elev_safe']})"
            )

    lines += [
        "",
        "## Per route — Phase B @ 16 km/h",
        "",
        "| Route | F elev | S elev | Fast B@1 | Safe B@1 | Fast B@2.58 | Safe B@2.58 | Δ(F−S)@1 | Δ(F−S)@2.58 |",
        "|-------|-------:|-------:|---------:|---------:|------------:|------------:|---------:|------------:|",
    ]
    for row in per_route:
        lines.append(
            f"| {row['route']} | {row['fast']['elev']} | {row['safe']['elev']} | "
            f"{row['fast']['B_1.0']} | {row['safe']['B_1.0']} | "
            f"{row['fast']['B_2.58']} | {row['safe']['B_2.58']} | "
            f"{row['delta_fast_minus_safe_1.0']:+} | {row['delta_fast_minus_safe_2.58']:+} |"
        )

    lines += [
        "",
        "## Bike-aware Phase B (cruise speed + Miotti climb)",
        "",
        "Uses `user_profiles.BIKE_SPEEDS_KMH` with matching climb rates.",
        "",
        "| Case | Fastest | Fast | Safe | Fast≤Safe | Fast−Safe | Fast−shortest |",
        "|------|--------:|-----:|-----:|----------:|----------:|--------------:|",
    ]
    for case, p in bike_pivot.items():
        m = p["mean_phase_b"]
        lines.append(
            f"| {case} | {m['fastest']} | {m['fast']} | {m['safe']} | "
            f"{p['fast_leq_safe']} | {p['mean_fast_minus_safe']:+} | "
            f"{p['mean_fast_minus_shortest']:+} |"
        )

    lines += [
        "",
        "## Verdict",
        "",
        "- Moving climb **1.0 → 2.58** increases absolute Phase B for everyone, but **more for Safe** "
        "(higher elev) → Fast’s mean lead vs Safe widens; Fast≤Safe stays strong / may flip r1.",
        "- **1.54 (e-bike)** sits between legacy and standard; still rewards Fast’s flatter paths.",
        "- Cost-function hills (~8 s/m equivalent at Fast `hill_weight=1.8`) remain **stronger** than "
        "Miotti 2.58 — A* still over-weights climb vs this literature display model.",
        "- Code default `PENALTY_SECONDS['climb_per_metre']` is now **2.58**; use "
        "`climb_seconds_per_metre_for_bike(bike_type)` for e-bike **1.54**.",
        "",
        f"JSON: `{REPORT_JSON}`",
        "",
    ]
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {REPORT_MD}")
    for label, p in pivot.items():
        print(
            f"  {label}: Fast B={p['mean_phase_b']['fast']} Safe={p['mean_phase_b']['safe']} "
            f"Fast<=Safe {p['fast_leq_safe']}"
        )
    print("Flips:", flips)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
