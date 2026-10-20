#!/usr/bin/env python3
"""Export the public results catalog from the private results sheet.

The full results sheet, its curation decisions and per-task evidence live in
the private code repository. This export runs the same publication policy on
them and keeps only what the public pages display, so the public repository
and site never carry the sheet itself.

    python3 scripts/export_public_catalog.py \\
        --sheet PRIVATE/all-hf-model-trajectory-metrics-2026-09-13.csv \\
        --curation PRIVATE/results-curation.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_results_dashboard import without_trajectory_links
from results_catalog import load_catalog
from results_model_metadata import METADATA_PATH

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data/public-catalog.json"
CONFIG = ROOT / "website/config.json"

# Fields the public pages and scripts read. Notes, cost notes and quality flags
# appear only in the internal layout, so they stay private with everything else.
RECORD_FIELDS = (
    "average_output_tokens", "average_time_per_task_sec", "cost_label",
    "cost_range_max_usd", "cost_range_min_usd", "cost_source_url", "cost_unit_prices",
    "cost_usd", "effort", "effort_rank", "entry_id", "entry_name", "frontier",
    "median_time_per_task_sec", "model", "model_metadata", "model_type",
    "performance", "provisional", "qualification_known", "qualifying",
    "reference", "release_date", "row_type", "run_id", "series", "source_archive_url",
    "source_archive_urls", "steps_per_task", "time_per_task_sec",
    "tool_calls_per_task", "turns_per_task", "variant",
)
DATASET_FIELDS = ("name", "label", "href", "task_counts")


def public_url(url: str) -> str:
    """Per-task evidence files are private, and the site never links the trajectory dataset."""
    url = without_trajectory_links(url)
    return url if url.startswith(("https://", "http://")) else ""


def public_catalog(catalog: dict, published: list[str]) -> dict:
    """Keep only the published datasets and the fields their pages display."""
    if set(published) - catalog["datasets"].keys():
        raise ValueError("website/config.json names a dataset the sheet does not have")
    datasets = {}
    for name in published:
        dataset = catalog["datasets"][name]
        records = []
        for record in dataset["records"]:
            public = {key: record[key] for key in RECORD_FIELDS if key in record}
            public["source_archive_url"] = public_url(public.get("source_archive_url", ""))
            public["source_archive_urls"] = [
                url for url in map(public_url, public.get("source_archive_urls", [])) if url
            ]
            public["cost_source_url"] = public_url(public.get("cost_source_url", ""))
            records.append(public)
        datasets[name] = {**{key: dataset[key] for key in DATASET_FIELDS}, "records": records}
    # The site never names the trajectory dataset; the export follows the same rule.
    return without_trajectory_links({
        "datasets": datasets,
        "included_rows": sum(len(dataset["records"]) for dataset in datasets.values()),
        "model_metadata_verified_on": catalog["model_metadata_verified_on"],
        "inventory_utc": catalog["inventory_utc"],
    })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sheet", type=Path, required=True, help="private results sheet (CSV)")
    parser.add_argument("--curation", type=Path, required=True, help="private curation decisions (JSON)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    published = list(json.loads(CONFIG.read_text())["paper_subsets"])
    catalog = public_catalog(load_catalog(args.sheet, METADATA_PATH, args.curation), published)
    args.output.write_text(json.dumps(catalog, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
                           encoding="utf-8")
    print(f"Wrote {args.output} ({catalog['included_rows']} results)")


if __name__ == "__main__":
    main()
