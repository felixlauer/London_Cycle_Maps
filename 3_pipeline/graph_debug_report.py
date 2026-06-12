"""Timestamped graph build debug report paths under 1_data/graph_debug_reports/."""
from __future__ import annotations

import os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "1_data"))
REPORT_SUBDIR = "graph_debug_reports"


def new_debug_report_path(data_dir: str | None = None) -> str:
    """Return a dated path; append time if a report for today already exists."""
    root = data_dir or DEFAULT_DATA_DIR
    report_dir = os.path.join(root, REPORT_SUBDIR)
    os.makedirs(report_dir, exist_ok=True)
    now = datetime.now()
    date_tag = now.strftime("%Y-%m-%d")
    path = os.path.join(report_dir, f"graph_debug_report_{date_tag}.txt")
    if os.path.isfile(path):
        path = os.path.join(
            report_dir,
            f"graph_debug_report_{date_tag}_{now.strftime('%H%M%S')}.txt",
        )
    return os.path.normpath(path)
