-- Materialized road segments for build_graph.py (tags from parent way, split geometry).
DROP MATERIALIZED VIEW IF EXISTS planet_osm_line_noded_enriched CASCADE;

CREATE MATERIALIZED VIEW planet_osm_line_noded_enriched AS
SELECT
    n.old_id AS osm_id,
    n.sub_id,
    l.name,
    COALESCE(w.accident_count, l.accident_count, 0)::integer AS accident_count,
    l.highway,
    l.surface,
    l.oneway,
    l.bicycle,
    l.bridge,
    l.tunnel,
    l.junction,
    l.width,
    l.tags,
    n.way
FROM planet_osm_line_noded n
INNER JOIN planet_osm_line l ON l.osm_id = n.old_id
LEFT JOIN ways w ON w.osm_id::bigint = n.old_id
WHERE ST_GeometryType(n.way) IN ('ST_LineString', 'ST_MultiLineString')
  AND ST_Length(ST_Transform(
        CASE WHEN ST_GeometryType(n.way) = 'ST_MultiLineString'
             THEN ST_LineMerge(n.way) ELSE n.way END, 4326)::geography) > 0.5;

CREATE INDEX planet_osm_line_noded_enriched_way_gix
    ON planet_osm_line_noded_enriched USING GIST (way);

CREATE INDEX planet_osm_line_noded_enriched_osm_id
    ON planet_osm_line_noded_enriched (osm_id);
