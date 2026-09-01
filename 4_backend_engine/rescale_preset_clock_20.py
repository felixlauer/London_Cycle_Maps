"""Rescale 22 Aug preset Phase B times from 16 km/h moving to 20 km/h.

Paths, counts, and penalty seconds stay. Cruise minutes scale 16/20.
Rewrites:
  0_documentation/testing/presets_aligned_time_compare_phase_b_live.{json,md}
  0_documentation/testing/shortest_fast_safe_metrics_phase_b_live.md
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

FROM_KMH = 16.0
TO_KMH = 20.0
SCALE = FROM_KMH / TO_KMH  # 0.8
WAIT_S = 7.5
CLIMB_S_PER_M = 2.58

REPO = Path(__file__).resolve().parent.parent
TEST = REPO / "0_documentation" / "testing"
JSON_PATH = TEST / "presets_aligned_time_compare_phase_b_live.json"
MD_PATH = JSON_PATH.with_suffix(".md")
SHORT_PATH = TEST / "shortest_fast_safe_metrics_phase_b_live.md"


def r2(x):
    return round(float(x), 2)


def implied(length_m, duration_min):
    if not duration_min:
        return None
    return r2((float(length_m) / 1000.0) / (float(duration_min) / 60.0))


def scale_row(row: dict) -> dict:
    out = dict(row)
    for key in (
        "cruise_min",
        "cruise_flat_min",
        "vf_save_min",
        "phase_a_live_min",
        "stats_duration_min",
        "phase_b_api_min",
        "phase_b_manual_min",
    ):
        if out.get(key) is not None:
            out[key] = r2(float(out[key]) * SCALE)
    cruise = float(out["cruise_min"])
    penalty = float(out["phase_b_penalty_min"])
    out["phase_b_min"] = r2(cruise + penalty)
    out["phase_b_api_min"] = r2(cruise + penalty)
    out["phase_b_manual_min"] = r2(cruise + penalty)
    out["stats_duration_min"] = r2(cruise + penalty)
    length_m = (out.get("core") or {}).get("length_m")
    out["implied_kmh"] = implied(length_m, out["phase_b_min"]) if length_m else None
    return out


def rebuild_h2h(f: dict, s: dict, L: dict) -> dict:
    h2h = {
        "fast_leq_safe_phase_b": f["phase_b_min"] <= s["phase_b_min"],
        "fast_leq_safe_cruise": f["cruise_min"] <= s["cruise_min"],
        "fast_leq_leisure_phase_b": f["phase_b_min"] <= L["phase_b_min"],
        "delta_phase_b_fast_minus_safe": r2(f["phase_b_min"] - s["phase_b_min"]),
        "delta_cruise_fast_minus_safe": r2(f["cruise_min"] - s["cruise_min"]),
        "delta_len_fast_minus_safe": round(
            float(f["core"]["length_m"]) - float(s["core"]["length_m"]), 1
        ),
        "delta_sig_fast_minus_safe": int(f["core"]["signal_count"] or 0)
        - int(s["core"]["signal_count"] or 0),
        "delta_elev_fast_minus_safe": round(
            float(f["core"].get("elevation_gain") or 0)
            - float(s["core"].get("elevation_gain") or 0),
            1,
        ),
        "delta_vf_fast_minus_safe": round(
            float(f["core"].get("vehicular_free_pct") or 0)
            - float(s["core"].get("vehicular_free_pct") or 0),
            1,
        ),
        "why_fast_slower_if_any": None,
    }
    if h2h["fast_leq_safe_phase_b"]:
        return h2h
    reasons = []
    if h2h["delta_len_fast_minus_safe"] > 50:
        reasons.append(
            f"longer path (+{h2h['delta_len_fast_minus_safe']:.0f} m → "
            f"+{h2h['delta_cruise_fast_minus_safe']:.1f} min cruise)"
        )
    sig_save_min = (-h2h["delta_sig_fast_minus_safe"]) * WAIT_S / 60.0
    if h2h["delta_sig_fast_minus_safe"] < 0:
        reasons.append(
            f"fewer signals ({h2h['delta_sig_fast_minus_safe']:+d} → "
            f"~{sig_save_min:.1f} min saved @ {WAIT_S}s) but not enough "
            f"to offset other costs"
        )
    climb_delta_min = h2h["delta_elev_fast_minus_safe"] * CLIMB_S_PER_M / 60.0
    if abs(climb_delta_min) > 0.2:
        reasons.append(f"climb Δ → {climb_delta_min:+.1f} min")
    for key in ("junction", "calming", "barrier", "give_way", "stop_sign"):
        df = f["phase_b_parts_s"].get(key, 0) - s["phase_b_parts_s"].get(key, 0)
        if abs(df) > 30:
            reasons.append(f"{key} penalty Δ {df:+.0f}s")
    if not reasons:
        reasons.append("Phase B sum of penalties outweighs Fast’s signal win")
    h2h["why_fast_slower_if_any"] = "; ".join(reasons)
    return h2h


def main() -> None:
    blob = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    old_speed = float(blob.get("speed_kmh") or FROM_KMH)
    if abs(old_speed - TO_KMH) < 1e-9:
        print("already at 20 km/h — rewriting markdown from current JSON")
        rows = blob["rows"]
    else:
        if abs(old_speed - FROM_KMH) > 1e-6:
            raise SystemExit(f"unexpected speed_kmh={old_speed}")
        rows = [scale_row(r) for r in blob["rows"]]

    by_route: dict[str, dict[str, dict]] = {}
    for r in rows:
        by_route.setdefault(r["route"], {})[r["preset"]] = r
    for route, presets in by_route.items():
        h2h = rebuild_h2h(presets["fast"], presets["safe"], presets["leisure"])
        for p in ("fast", "safe", "leisure"):
            presets[p]["h2h_fast_vs_safe"] = h2h
        presets["fastest"].pop("h2h_fast_vs_safe", None)

    rows_out = []
    for route in sorted(by_route):
        for preset in ("fastest", "fast", "safe", "leisure"):
            rows_out.append(by_route[route][preset])
    rows = rows_out

    def mean_core(preset, key):
        vals = [
            float(r["core"][key])
            for r in rows
            if r["preset"] == preset and r["core"].get(key) is not None
        ]
        return round(mean(vals), 2) if vals else None

    def mean_field(preset, field):
        vals = [
            float(r[field])
            for r in rows
            if r["preset"] == preset and r.get(field) is not None
        ]
        return round(mean(vals), 2) if vals else None

    old_pivot = blob.get("pivot") or {}
    pivot = {}
    for preset in ("fastest", "fast", "safe", "leisure"):
        src = old_pivot.get(preset) or {}
        pivot[preset] = {
            "signal_weight": src.get("signal_weight", 0.0),
            "mean_length_m": mean_core(preset, "length_m"),
            "mean_signals": mean_core(preset, "signal_count"),
            "mean_elev_m": mean_core(preset, "elevation_gain"),
            "mean_vf_pct": mean_core(preset, "vehicular_free_pct"),
            "mean_accidents": mean_core(preset, "accidents"),
            "mean_cruise_min": mean_field(preset, "cruise_min"),
            "mean_phase_a_live_min": mean_field(preset, "phase_a_live_min"),
            "mean_phase_b_min": mean_field(preset, "phase_b_min"),
            "mean_phase_b_penalty_min": mean_field(preset, "phase_b_penalty_min"),
            "mean_implied_kmh": mean_field(preset, "implied_kmh"),
        }

    route_names = sorted(by_route)
    wins_b = wins_cruise = 0
    fail_details = []
    for route in route_names:
        by = by_route[route]
        if by["fast"]["phase_b_min"] <= by["safe"]["phase_b_min"]:
            wins_b += 1
        else:
            fail_details.append(
                {
                    "route": route,
                    **by["fast"]["h2h_fast_vs_safe"],
                    "fast_core": by["fast"]["core"],
                    "safe_core": by["safe"]["core"],
                    "fast_phase_b": by["fast"]["phase_b_min"],
                    "safe_phase_b": by["safe"]["phase_b_min"],
                    "fast_parts_s": by["fast"]["phase_b_parts_s"],
                    "safe_parts_s": by["safe"]["phase_b_parts_s"],
                }
            )
        if by["fast"]["cruise_min"] <= by["safe"]["cruise_min"]:
            wins_cruise += 1

    pivot["fast"]["fast_leq_safe_phase_b"] = f"{wins_b}/{len(route_names)}"
    pivot["fast"]["fast_leq_safe_cruise"] = f"{wins_cruise}/{len(route_names)}"
    pivot["fast"]["target_phase_b"] = "≥8/11"

    old_pivot = blob.get("pivot") or {}
    clock_rescale = {
        "from_kmh": FROM_KMH,
        "to_kmh": TO_KMH,
        "formula": "phase_b_20 = cruise_16 × 16/20 + penalty_min (penalty unchanged)",
        "mean_phase_b": {},
    }
    for preset in ("fastest", "fast", "safe", "leisure"):
        old_b = (old_pivot.get(preset) or {}).get("mean_phase_b_min")
        new_b = pivot[preset]["mean_phase_b_min"]
        if old_b is not None:
            clock_rescale["mean_phase_b"][preset] = {
                "at_16": old_b,
                "at_20": new_b,
                "delta": r2(new_b - old_b),
            }

    vs_previous = blob.get("vs_previous")
    if vs_previous:
        vs_previous = dict(vs_previous)
        vs_previous["fast_leq_safe_now"] = pivot["fast"]["fast_leq_safe_phase_b"]
        vs_previous["note"] = (
            "Previous file used climb 1.0 s/m, flat cruise, and a 16 km/h clock. "
            "The 22 Aug live run (Miotti + Jafari, still 16 km/h) was 7/11. "
            "mean_phase_b_delta.now is that 16 km/h live run, not the 20 km/h "
            "rescaled times in this file. See clock_rescale for 16→20 means. "
            "Fast≤Safe is still 7/11. Do not treat the 20 km/h times as a new routing run."
        )

    now = datetime.now(timezone.utc).isoformat()
    summary = {
        "generated_at": now,
        "speed_kmh": TO_KMH,
        "clock_rescaled_from_kmh": FROM_KMH,
        "clock_rescale_note": (
            "Cruise, Phase A, and VF-save minutes ×16/20. Penalty seconds unchanged. "
            "Paths from 2026-08-22T10:58:57Z live re-route."
        ),
        "paths_generated_at": blob.get("generated_at"),
        "preset_source": blob.get("preset_source"),
        "alignment": blob.get("alignment"),
        "phase_b": blob.get("phase_b"),
        "note": (
            "Paths routed at live SIGNAL_WAIT_SECONDS (22 Aug 2026). "
            "ETA rescaled to 20 km/h moving: Phase B = 0.8×Jafari cruise + stop/climb penalties."
        ),
        "clock_rescale": clock_rescale,
        "vs_previous": vs_previous,
        "pivot": pivot,
        "fast_vs_safe_fails": fail_details,
        "rows": rows,
    }
    JSON_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        "# Presets aligned time compare — live Phase B (Miotti + Jafari VF)",
        "",
        f"Generated: `{now}`",
        "",
        "Climb: **2.58 s/m** · `ROUTE_TIME_MODEL=penalties` · Jafari VF cruise **on** · "
        f"**moving cruise {TO_KMH:.0f} km/h** (rescaled from 16 km/h on frozen 22 Aug paths)",
        "",
        "Baseline to diff: `presets_aligned_time_compare.json` (climb 1.0, no VF uplift, 16 km/h clock)",
        "",
    ]
    if vs_previous:
        lines += [
            "## vs previous baseline (mean Phase B, both on 16 km/h)",
            "",
            "| Preset | July B (climb 1.0) | 22 Aug B @ 16 km/h | Δ |",
            "|--------|-------------------:|-------------------:|--:|",
        ]
        for preset, d in vs_previous["mean_phase_b_delta"].items():
            lines.append(
                f"| {preset} | {d['previous']} | {d['now']} | {d['delta']:+} |"
            )
        lines += [
            "",
            f"Fast<=Safe: was **{vs_previous.get('fast_leq_safe_previous')}** at the "
            f"climb-1.0 file → **7/11** on the 22 Aug 16 km/h live run → still "
            f"**{vs_previous['fast_leq_safe_now']}** after the 20 km/h rescale.",
            "",
            vs_previous["note"],
            "",
            "## Clock rescale 16 → 20 km/h (same 22 Aug paths)",
            "",
            "| Preset | B @ 16 km/h | B @ 20 km/h | Δ |",
            "|--------|------------:|------------:|--:|",
        ]
        for preset, d in clock_rescale["mean_phase_b"].items():
            lines.append(
                f"| {preset} | {d['at_16']} | {d['at_20']} | {d['delta']:+} |"
            )
        lines += ["", "Formula: `phase_b_20 = cruise_16 × 0.8 + penalty_min`.", ""]
    lines += [
        "## Alignment cross-check",
        "",
        "| Constant | Value |",
        "|----------|------:|",
        "| `SIGNAL_WAIT_SECONDS` | 7.5 |",
        "| `PENALTY_SECONDS['signal']` | 7.5 |",
        "| wizard `signal_count` seconds | 7.5 |",
        "| Signal metres @ weight=1 | 33.33 |",
        "| `INTERSECTION_PENALTY_METRES` (1/2 signal) | 16.67 |",
        "| Wait == Penalty == Wizard | YES |",
        "| Displayed moving cruise | **20 km/h** |",
        "",
        f"Preset source: `{blob.get('preset_source')}`",
        "",
        "## Mean metrics + times",
        "",
        "| Preset | Len (m) | Sig | Elev | VF% | Acc | Cruise | Phase A* | Phase B | d2d km/h |",
        "|--------|--------:|----:|-----:|----:|----:|-------:|---------:|--------:|---------:|",
    ]
    for preset in ("fastest", "fast", "safe", "leisure"):
        p = pivot[preset]
        lines.append(
            f"| {preset} | {p['mean_length_m']} | {p['mean_signals']} | {p['mean_elev_m']} | "
            f"{p['mean_vf_pct']} | {p['mean_accidents']} | {p['mean_cruise_min']} | "
            f"{p['mean_phase_a_live_min']} | **{p['mean_phase_b_min']}** | "
            f"{p['mean_implied_kmh']} |"
        )
    lines += [
        "",
        f"**Fast ≤ Safe (Phase B):** {wins_b}/{len(route_names)} "
        f"(target ≥8/11) · **Fast ≤ Safe (cruise only):** {wins_cruise}/{len(route_names)}",
        "",
        "## Per route — Fast vs Safe",
        "",
        "| Route | Fast len/sig/elev | Safe len/sig/elev | Fast B | Safe B | ΔB | Δlen | Δsig | Winner | Fast d2d |",
        "|-------|------------------:|------------------:|-------:|-------:|---:|-----:|-----:|--------|---------:|",
    ]
    for route in route_names:
        by = by_route[route]
        f, s = by["fast"], by["safe"]
        h2h = f["h2h_fast_vs_safe"]
        winner = "Fast" if h2h["fast_leq_safe_phase_b"] else "Safe"
        lines.append(
            f"| {route} | {f['core']['length_m']:.0f}/{f['core']['signal_count']}/"
            f"{f['core'].get('elevation_gain')} | "
            f"{s['core']['length_m']:.0f}/{s['core']['signal_count']}/"
            f"{s['core'].get('elevation_gain')} | "
            f"{f['phase_b_min']} | {s['phase_b_min']} | "
            f"{h2h['delta_phase_b_fast_minus_safe']:+} | "
            f"{h2h['delta_len_fast_minus_safe']:+.0f} | "
            f"{h2h['delta_sig_fast_minus_safe']:+d} | {winner} | "
            f"{f.get('implied_kmh')} |"
        )
    if fail_details:
        lines += ["", "## Why Fast loses (Phase B)", ""]
        for fd in fail_details:
            lines += [
                f"### {fd['route']}",
                "",
                f"- {fd['why_fast_slower_if_any']}",
                f"- Fast B={fd['fast_phase_b']} vs Safe B={fd['safe_phase_b']} "
                f"(Δ {fd['delta_phase_b_fast_minus_safe']:+} min)",
                f"- Cruise Δ {fd['delta_cruise_fast_minus_safe']:+} · "
                f"len Δ {fd['delta_len_fast_minus_safe']:+.0f} m · "
                f"sig Δ {fd['delta_sig_fast_minus_safe']:+d} · "
                f"elev Δ {fd['delta_elev_fast_minus_safe']:+.0f} m · "
                f"VF Δ {fd['delta_vf_fast_minus_safe']:+.1f} pp",
                "",
            ]
    lines += [
        "## How to read",
        "",
        "- **Cruise** = Jafari VF time at **20 km/h** mixed (no Fast 1.35×).",
        "- **Phase A×** = flat cruise at 20 km/h (Fast still ×1.35 only if Phase A is on; live model is Phase B).",
        "- **Phase B** = cruise + metric×`PENALTY_SECONDS` (canonical ETA).",
        "- **d2d km/h** = length / Phase B.",
        "- Paths were not re-routed. Only the duration clock changed.",
        "",
        f"JSON: `{JSON_PATH}`",
        "",
    ]
    MD_PATH.write_text("\n".join(lines), encoding="utf-8")
    write_shortest(by_route, pivot, wins_b, wins_cruise)
    print(f"wrote {JSON_PATH}")
    print(f"wrote {MD_PATH}")
    print(f"wrote {SHORT_PATH}")
    print(f"Fast<=Safe {wins_b}/{len(route_names)} cruise {wins_cruise}/{len(route_names)}")
    for route in route_names:
        f, s = by_route[route]["fast"], by_route[route]["safe"]
        d = f["h2h_fast_vs_safe"]["delta_phase_b_fast_minus_safe"]
        print(
            f"  {route}: Fast {f['phase_b_min']} Safe {s['phase_b_min']} "
            f"Δ {d:+} d2d {f.get('implied_kmh')}"
        )


def cell(v, nd=1):
    if v is None:
        return "—"
    if isinstance(v, float):
        if abs(v - round(v)) < 1e-6 and nd == 0:
            return str(int(round(v)))
        return f"{v:.{nd}f}"
    return str(v)


def write_shortest(by_route, pivot, wins_b, wins_cruise):
    def trio(route, key, nd=1):
        sh = by_route[route]["fastest"]
        f = by_route[route]["fast"]
        s = by_route[route]["safe"]
        if key in ("cruise_min", "phase_b_min", "implied_kmh"):
            a, b, c = sh[key], f[key], s[key]
        else:
            a, b, c = sh["core"][key], f["core"][key], s["core"][key]
        fs = round(float(b) - float(c), nd)
        fsh = round(float(b) - float(a), nd)
        return a, b, c, fs, fsh

    lines = [
        "# Shortest vs Fast vs Safe — full metrics (@ aligned 7.5s, live Phase B, **20 km/h**)",
        "",
        "Generated from `presets_aligned_time_compare_phase_b_live.json`. "
        "Paths **re-routed** 22 Aug 2026 at `SIGNAL_WAIT_SECONDS=7.5`. "
        "Times **rescaled** 16→20 km/h moving (`cruise × 0.8` + unchanged penalties).",
        "",
        "**Clock:** Phase B = Jafari VF cruise at 20 km/h + stop penalties + Miotti climb **2.58 s/m**. "
        "Signal counts are **cluster entries**, not raw OSM nodes.",
        "",
        "**Columns:** `F−S` = Fast minus Safe · `F−sh` = Fast minus shortest.",
        "",
        "**Times:** Cruise = Jafari at 20 km/h · Phase B = cruise + penalties · "
        "Phase A\\* = flat cruise at 20 km/h.",
        "",
        "---",
        "",
        "## Means (11 routes)",
        "",
        "| metric | shortest | fast | safe | F−S | F−sh |",
        "|--------|--------:|-----:|-----:|----:|-----:|",
    ]
    sh, f, s = pivot["fastest"], pivot["fast"], pivot["safe"]

    def mean_row(label, key, nd, bold_safe=False, invert=False):
        a, b, c = sh[key], f[key], s[key]
        fs = round(b - c, nd)
        fsh = round(b - a, nd)
        cs = f"**{c}**" if bold_safe else str(c)
        fs_s = f"**{fs:+}**" if (fs < 0 and not invert) or (fs > 0 and invert) else f"{fs:+}"
        fsh_s = f"**{fsh:+}**" if (fsh < 0 and not invert) or (fsh > 0 and invert) else f"{fsh:+}"
        return f"| {label} | {a} | {b} | {cs} | {fs_s} | {fsh_s} |"

    # Use original non-time means from first JSON-derived pivot (length etc. unchanged)
    lines += [
        f"| length (m) | {int(round(sh['mean_length_m']))} | {int(round(f['mean_length_m']))} | {int(round(s['mean_length_m']))} | **{int(round(f['mean_length_m']-s['mean_length_m'])):+}** | {int(round(f['mean_length_m']-sh['mean_length_m'])):+} |",
        f"| signals | {sh['mean_signals']} | {f['mean_signals']} | {s['mean_signals']} | **{round(f['mean_signals']-s['mean_signals'],1):+}** | **{round(f['mean_signals']-sh['mean_signals'],1):+}** |",
        f"| elev (m) | {sh['mean_elev_m']} | {f['mean_elev_m']} | {s['mean_elev_m']} | **{round(f['mean_elev_m']-s['mean_elev_m']):+}** | **{round(f['mean_elev_m']-sh['mean_elev_m']):+}** |",
        f"| accidents | {sh['mean_accidents']} | {f['mean_accidents']} | **{s['mean_accidents']}** | {round(f['mean_accidents']-s['mean_accidents']):+} | {round(f['mean_accidents']-sh['mean_accidents']):+} |",
        f"| VF % | {sh['mean_vf_pct']} | {f['mean_vf_pct']} | **{s['mean_vf_pct']}** | {round(f['mean_vf_pct']-s['mean_vf_pct']):+} | {round(f['mean_vf_pct']-sh['mean_vf_pct']):+} |",
        f"| cruise (min) | {sh['mean_cruise_min']} | {f['mean_cruise_min']} | {s['mean_cruise_min']} | **{round(f['mean_cruise_min']-s['mean_cruise_min'],1):+}** | {round(f['mean_cruise_min']-sh['mean_cruise_min'],1):+} |",
        f"| **Phase B (min)** | **{sh['mean_phase_b_min']}** | **{f['mean_phase_b_min']}** | **{s['mean_phase_b_min']}** | **{round(f['mean_phase_b_min']-s['mean_phase_b_min'],1):+}** | {round(f['mean_phase_b_min']-sh['mean_phase_b_min'],1):+} |",
        f"| Phase A* (min) | {sh['mean_phase_a_live_min']} | {f['mean_phase_a_live_min']} | {s['mean_phase_a_live_min']} | {round(f['mean_phase_a_live_min']-s['mean_phase_a_live_min'],1):+} | {round(f['mean_phase_a_live_min']-sh['mean_phase_a_live_min'],1):+} |",
        f"| d2d km/h | {sh['mean_implied_kmh']} | {f['mean_implied_kmh']} | {s['mean_implied_kmh']} | {round(f['mean_implied_kmh']-s['mean_implied_kmh'],2):+} | {round(f['mean_implied_kmh']-sh['mean_implied_kmh'],2):+} |",
        "",
        f"Jafari VF cruise save vs flat 20 km/h (means): shortest **{pivot['fastest']['mean_phase_a_live_min']-pivot['fastest']['mean_cruise_min']:.2f}** "
        f"wait that is A*−cruise; vf_save field mean is 0.8× the 16 km/h save.",
        "",
        f"**Fast ≤ Safe (Phase B): {wins_b}/11** · cruise only: {wins_cruise}/11.",
        "",
        "---",
        "",
        "## Per route (times at 20 km/h)",
        "",
    ]

    order = sorted(by_route, key=lambda n: int(re.search(r"route (\d+)", n).group(1)))
    titles = {
        1: "r1 Imperial → Kings Cross — Safe wins Phase B",
        2: "r2 Imperial → Greenwich — Fast wins Phase B",
        3: "r3 Imperial → Spitalfields — Safe wins Phase B (miss grew vs 16 km/h clock)",
        4: "r4 Twickenham → St Pauls — Fast big Phase B win",
        5: "r5 Wembley → KCH — Fast wins Phase B",
        6: "r6 Battersea → Temple — Safe clearly better",
        7: "r7 Putney → Notting Hill — Safe wins Phase B (no longer a 3 s tie)",
        8: "r8 Tottenham → Hampstead — Fast wins Phase B; hills dominate vs shortest",
        9: "r9 Earls Court → Piccadilly — Fast ≈ shortest, beats Safe",
        10: "r10 Bromley → Ealing — Fast wins Phase B via climb",
        11: "r11 Elmers End → Streatham (hills) — Fast wins Phase B",
    }
    for route in order:
        n = int(re.search(r"route (\d+)", route).group(1))
        sh, f, s = by_route[route]["fastest"], by_route[route]["fast"], by_route[route]["safe"]
        dB = r2(f["phase_b_min"] - s["phase_b_min"])
        lines += [
            f"### {titles[n]}",
            "",
            "| metric | shortest | fast | safe | F−S | F−sh |",
            "|--------|--------:|-----:|-----:|----:|-----:|",
            f"| length | {sh['core']['length_m']:.0f} | {f['core']['length_m']:.0f} | {s['core']['length_m']:.0f} | "
            f"{f['core']['length_m']-s['core']['length_m']:+.0f} | {f['core']['length_m']-sh['core']['length_m']:+.0f} |",
            f"| signals | {sh['core']['signal_count']} | {f['core']['signal_count']} | {s['core']['signal_count']} | "
            f"{f['core']['signal_count']-s['core']['signal_count']:+d} | {f['core']['signal_count']-sh['core']['signal_count']:+d} |",
            f"| elev | {sh['core'].get('elevation_gain')} | {f['core'].get('elevation_gain')} | {s['core'].get('elevation_gain')} | "
            f"{(f['core'].get('elevation_gain') or 0)-(s['core'].get('elevation_gain') or 0):+.0f} | "
            f"{(f['core'].get('elevation_gain') or 0)-(sh['core'].get('elevation_gain') or 0):+.0f} |",
            f"| accidents | {sh['core'].get('accidents')} | {f['core'].get('accidents')} | {s['core'].get('accidents')} | "
            f"{(f['core'].get('accidents') or 0)-(s['core'].get('accidents') or 0):+.0f} | "
            f"{(f['core'].get('accidents') or 0)-(sh['core'].get('accidents') or 0):+.0f} |",
            f"| cruise | {sh['cruise_min']} | {f['cruise_min']} | {s['cruise_min']} | "
            f"{r2(f['cruise_min']-s['cruise_min']):+} | {r2(f['cruise_min']-sh['cruise_min']):+} |",
            f"| Phase B | {sh['phase_b_min']} | {f['phase_b_min']} | {s['phase_b_min']} | "
            f"**{dB:+}** | {r2(f['phase_b_min']-sh['phase_b_min']):+} |",
            f"| d2d km/h | {sh.get('implied_kmh')} | {f.get('implied_kmh')} | {s.get('implied_kmh')} | "
            f"{r2((f.get('implied_kmh') or 0)-(s.get('implied_kmh') or 0)):+} | "
            f"{r2((f.get('implied_kmh') or 0)-(sh.get('implied_kmh') or 0)):+} |",
            "",
        ]

    lines += [
        "## Quick “who wins what” (Fast vs Safe)",
        "",
        "| Route | Phase B | Length | Signals | Elev | Accidents | VF/TfL |",
        "|-------|---------|--------|---------|------|-----------|--------|",
        "| r1 KX | Safe | Safe | Fast | Fast | Safe | Safe |",
        "| r2 Greenwich | Fast | Safe | Fast | Fast | Safe | Safe |",
        "| **r3 Spitalfields** | **Safe** | Fast | Fast | Fast | Safe | Safe |",
        "| r4 Twickenham | Fast | Fast | Fast | Fast | Safe | Safe |",
        "| r5 Wembley | Fast | Fast | **Safe** | Fast | Safe | Safe |",
        "| **r6 Battersea** | **Safe** | **Safe** | **Safe** | Fast | **Safe** | ≈ / Safe |",
        "| **r7 Putney** | **Safe** | Fast | Fast | Fast | Safe | Safe |",
        "| r8 Tottenham | Fast | Fast | Fast | Fast | ≈ | Safe |",
        "| r9 Earls Court | Fast | Fast | Fast | Fast | Safe | Safe |",
        "| r10 Bromley | Fast | ≈ | Fast | Fast | Safe | Safe |",
        "| r11 Hills | Fast | Fast | ≈ | Fast | Safe | ≈ |",
        "",
        "Bold Phase B = Fast miss (4/11). Clock rescale did not flip any winner. "
        "Source JSON: `presets_aligned_time_compare_phase_b_live.json`.",
        "",
    ]
    SHORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
