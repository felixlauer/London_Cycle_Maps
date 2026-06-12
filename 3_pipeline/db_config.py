"""Shared PostgreSQL connection settings for pipeline scripts."""
import os

try:
    from dotenv import load_dotenv
    _env = os.path.join(os.path.dirname(__file__), "..", "4_backend_engine", ".env")
    load_dotenv(_env)
except ImportError:
    pass

DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASS = os.environ.get("DB_PASS", "")
DB_NAME = os.environ.get("DB_NAME", "london_routing")
DB_HOST = os.environ.get("DB_HOST", "localhost")

DEFAULT_ROAD_SOURCE = os.environ.get("GRAPH_ROAD_SOURCE", "planet_osm_line_noded_enriched")


def db_url() -> str:
    return f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:5432/{DB_NAME}"
