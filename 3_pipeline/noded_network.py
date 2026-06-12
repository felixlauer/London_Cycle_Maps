"""
Split planet_osm_line highways at intersections (PostGIS / pgRouting).
Creates planet_osm_line_noded + materialized view planet_osm_line_noded_enriched.

Run before build_graph.py (also wired in run_graph_pipeline.py).

When changing tables or tolerance, update 0_documentation/GRAPH.md.
"""
from __future__ import annotations

import os
import sys
import time

from sqlalchemy import create_engine, text

from db_config import db_url

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SQL_DIR = os.path.join(SCRIPT_DIR, "sql")

# ~0.11 m at London latitude in degrees (WGS84)
NODING_TOLERANCE = float(os.environ.get("NODING_TOLERANCE", "0.000001"))


def _read_sql(name: str) -> str:
    path = os.path.join(SQL_DIR, name)
    with open(path, encoding="utf-8") as f:
        return f.read()


def _run_sql_file(conn, name: str) -> None:
    conn.execute(text(_read_sql(name)))
    conn.commit()


def check_extensions(conn) -> dict[str, str]:
    rows = conn.execute(text(
        "SELECT extname, extversion FROM pg_extension "
        "WHERE extname IN ('pgrouting', 'postgis') ORDER BY extname"
    )).fetchall()
    return {r[0]: r[1] for r in rows}


def ensure_pgrouting(conn, exts: dict[str, str]) -> dict[str, str]:
    if "pgrouting" in exts:
        return exts
    print("   -> Attempting CREATE EXTENSION pgrouting...")
    try:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgrouting"))
        conn.commit()
        exts = check_extensions(conn)
        if "pgrouting" in exts:
            print(f"   -> pgRouting enabled ({exts['pgrouting']}).")
    except Exception as err:
        conn.rollback()
        print(f"   WARN: Could not enable pgRouting ({err}).")
    return exts


def check_way_srid(conn) -> int | None:
    row = conn.execute(text(
        "SELECT DISTINCT ST_SRID(way) AS srid FROM planet_osm_line "
        "WHERE highway IS NOT NULL AND way IS NOT NULL LIMIT 1"
    )).fetchone()
    return int(row[0]) if row else None


def _drop_pgr_artifacts(conn) -> None:
    for tbl in (
        "planet_osm_line_noded",
        "planet_osm_line_noded_vertices_pgr",
        "highways_pgr_noding",
        "highways_pgr_after_cross",
        "highways_pgr_after_touch",
    ):
        conn.execute(text(f"DROP TABLE IF EXISTS {tbl} CASCADE"))
    conn.commit()


def pgr_separate_available(conn) -> bool:
    n = conn.execute(text("""
        SELECT COUNT(*) FROM pg_proc
        WHERE proname IN ('pgr_separatecrossing', 'pgr_separatetouching')
    """)).scalar()
    return n >= 2


def run_pgrouting(conn) -> None:
    """pgRouting 4+: split crossings then touching endpoints (replaces pgr_nodeNetwork)."""
    tol = NODING_TOLERANCE
    print(f"2. Running pgRouting separateCrossing + separateTouching (tolerance={tol})...")
    _drop_pgr_artifacts(conn)
    conn.execute(text("""
        CREATE TABLE highways_pgr_noding AS
        SELECT gid AS id, osm_id, ST_Transform(way, 4326) AS geom
        FROM _highways_for_noding;
        CREATE INDEX highways_pgr_noding_geom_gix ON highways_pgr_noding USING GIST (geom);
    """))
    conn.commit()

    conn.execute(text(f"""
        CREATE TABLE highways_pgr_after_cross AS
        SELECT seq, id, sub_id, geom
        FROM pgr_separateCrossing('highways_pgr_noding', {tol}, dryrun := false);
    """))
    conn.commit()
    cross_cnt = conn.execute(text("SELECT COUNT(*) FROM highways_pgr_after_cross")).scalar()
    print(f"   -> separateCrossing: {cross_cnt:,} segments.", flush=True)

    conn.execute(text(f"""
        CREATE TABLE highways_pgr_after_touch AS
        SELECT seq, id, sub_id, geom
        FROM pgr_separateTouching('highways_pgr_after_cross', {tol}, dryrun := false);
    """))
    conn.commit()

    conn.execute(text("""
        CREATE TABLE planet_osm_line_noded AS
        SELECT
            row_number() OVER ()::integer AS id,
            m.osm_id AS old_id,
            t.sub_id::integer AS sub_id,
            ST_Transform(t.geom, 3857) AS way,
            NULL::bigint AS source,
            NULL::bigint AS target
        FROM highways_pgr_after_touch t
        INNER JOIN _noding_gid_osm m ON m.gid = t.id
        WHERE ST_GeometryType(t.geom) = 'ST_LineString'
          AND ST_Length(t.geom::geography) > 0.5;
    """))
    conn.commit()
    cnt = conn.execute(text("SELECT COUNT(*) FROM planet_osm_line_noded")).scalar()
    print(f"   -> separateTouching -> planet_osm_line_noded: {cnt:,} segments.", flush=True)


def run_postgis_noding(conn) -> None:
    """Split each way at OSM vertices (fast; covers most T-junctions on shared vertices)."""
    print("2. Running PostGIS vertex split (per-way segments)...", flush=True)
    conn.execute(text("DROP TABLE IF EXISTS planet_osm_line_noded CASCADE"))
    conn.execute(text("""
        CREATE TABLE planet_osm_line_noded AS
        WITH dumped AS (
            SELECT
                h.gid,
                h.osm_id,
                (dp).path[1]::integer AS pt_order,
                (dp).geom AS pt_geom
            FROM _highways_for_noding h,
            LATERAL ST_DumpPoints(h.way) AS dp
        ),
        segments AS (
            SELECT
                d1.osm_id,
                ST_MakeLine(d1.pt_geom, d2.pt_geom) AS way,
                ROW_NUMBER() OVER (PARTITION BY d1.gid ORDER BY d1.pt_order) AS sub_id
            FROM dumped d1
            INNER JOIN dumped d2
                ON d1.gid = d2.gid AND d2.pt_order = d1.pt_order + 1
            WHERE ST_Length(
                ST_Transform(ST_MakeLine(d1.pt_geom, d2.pt_geom), 4326)::geography
            ) > 0.5
        )
        SELECT
            row_number() OVER ()::integer AS id,
            osm_id AS old_id,
            sub_id::integer AS sub_id,
            way,
            NULL::bigint AS source,
            NULL::bigint AS target
        FROM segments
        WHERE ST_GeometryType(way) = 'ST_LineString'
          AND ST_Length(ST_Transform(way, 4326)::geography) > 0.5;
    """))
    conn.commit()
    cnt = conn.execute(text("SELECT COUNT(*) FROM planet_osm_line_noded")).scalar()
    print(f"   -> PostGIS vertex split produced {cnt:,} segments.", flush=True)


def ensure_accident_columns(conn) -> None:
    conn.execute(text(
        "ALTER TABLE planet_osm_line ADD COLUMN IF NOT EXISTS accident_count INTEGER DEFAULT 0"
    ))
    conn.commit()


def propagate_risk(conn) -> None:
    """Copy ways.accident_count onto planet_osm_line (parent ways for enriched join)."""
    print("4. Propagating accident_count from ways -> planet_osm_line...")
    ensure_accident_columns(conn)
    conn.execute(text("UPDATE planet_osm_line SET accident_count = 0"))
    conn.execute(text("""
        UPDATE planet_osm_line p
        SET accident_count = w.accident_count
        FROM ways w
        WHERE w.osm_id::bigint = p.osm_id
    """))
    conn.commit()
    matched = conn.execute(text(
        "SELECT COUNT(*) FROM planet_osm_line WHERE COALESCE(accident_count, 0) > 0"
    )).scalar()
    print(f"   -> {matched:,} planet_osm_line rows with accident_count > 0.")


def build_enriched(conn) -> None:
    print("3. Building materialized view planet_osm_line_noded_enriched...")
    conn.execute(text("DROP MATERIALIZED VIEW IF EXISTS planet_osm_line_noded_enriched CASCADE"))
    _run_sql_file(conn, "create_enriched_noded_view.sql")
    cnt = conn.execute(text(
        "SELECT COUNT(*) FROM planet_osm_line_noded_enriched"
    )).scalar()
    print(f"   -> Enriched segments: {cnt:,}")


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Node planet_osm_line at intersections.")
    parser.add_argument(
        "--postgis-only",
        action="store_true",
        help="Skip pgRouting (slow on full London; for testing only)",
    )
    args = parser.parse_args()

    print("--- NODED HIGHWAY NETWORK (planet_osm_line) ---", flush=True)
    t0 = time.perf_counter()
    engine = create_engine(db_url())

    with engine.connect() as conn:
        print("1. Checking database...")
        exts = check_extensions(conn)
        exts = ensure_pgrouting(conn, exts)
        print(f"   -> Extensions: {exts or '(none found)'}", flush=True)
        srid = check_way_srid(conn)
        if srid is not None:
            print(f"   -> planet_osm_line.way SRID: {srid}")
        hw = conn.execute(text(
            "SELECT COUNT(*) FROM planet_osm_line WHERE highway IS NOT NULL"
        )).scalar()
        print(f"   -> Highway ways (raw): {hw:,}")

        print("1b. Creating staging table _highways_for_noding...")
        _run_sql_file(conn, "create_planet_osm_line_noded.sql")

        use_pgr = (
            "pgrouting" in exts
            and not args.postgis_only
            and pgr_separate_available(conn)
        )
        if args.postgis_only:
            print("   -> --postgis-only: vertex split only (no pgRouting).", flush=True)
        elif "pgrouting" in exts and not pgr_separate_available(conn):
            print("   WARN: pgRouting missing separateCrossing/Touching; using PostGIS.", flush=True)

        if use_pgr:
            try:
                with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as pgr_conn:
                    run_pgrouting(pgr_conn)
            except Exception as err:
                print(f"   WARN: pgRouting noding failed ({err}); falling back to PostGIS.", flush=True)
                use_pgr = False
                conn.rollback()

        if not use_pgr:
            if "postgis" not in exts:
                print("ERROR: postgis extension required.")
                return 1
            cnt = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'planet_osm_line_noded'
            """)).scalar()
            seg_count = 0
            if cnt:
                seg_count = conn.execute(text(
                    "SELECT COUNT(*) FROM planet_osm_line_noded"
                )).scalar() or 0
            if seg_count > 0:
                print(f"   -> Reusing planet_osm_line_noded ({seg_count:,} segments).", flush=True)
            else:
                run_postgis_noding(conn)

        propagate_risk(conn)
        build_enriched(conn)

        final = conn.execute(text(
            "SELECT COUNT(*) FROM planet_osm_line_noded_enriched"
        )).scalar()
        print(f"   -> Final enriched row count: {final:,}")

    elapsed = time.perf_counter() - t0
    print(f"\nSUCCESS! Noded network ready ({elapsed:.1f}s).")
    print("   Next: python build_graph.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
