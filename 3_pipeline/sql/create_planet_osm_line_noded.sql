-- Split highway linework at intersections; preserve parent osm_id on each segment.
-- Run via noded_network.py (pgRouting if installed, else PostGIS ST_Node).
-- Raw planet_osm_line is never modified.

-- Staging: integer gid for pgr_nodeNetwork (old_id in output = gid)
DROP TABLE IF EXISTS _noding_gid_osm CASCADE;
DROP TABLE IF EXISTS _highways_for_noding CASCADE;

CREATE TABLE _highways_for_noding AS
SELECT
    row_number() OVER (ORDER BY osm_id)::integer AS gid,
    osm_id,
    way
FROM planet_osm_line
WHERE highway IS NOT NULL
  AND way IS NOT NULL
  AND ST_IsValid(way);

CREATE INDEX _highways_for_noding_way_gix ON _highways_for_noding USING GIST (way);

CREATE TABLE _noding_gid_osm AS
SELECT gid, osm_id FROM _highways_for_noding;

CREATE UNIQUE INDEX _noding_gid_osm_gid ON _noding_gid_osm (gid);
CREATE INDEX _noding_gid_osm_osm_id ON _noding_gid_osm (osm_id);
