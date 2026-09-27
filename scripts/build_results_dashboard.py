#!/usr/bin/env python3
"""Build the public, static results dashboard from the reviewed CSV."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from html import escape
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from frontier import dashboard_entries
from results_catalog import load_catalog
from results_costs import PRICING_PATH
from results_model_metadata import METADATA_PATH, load_model_metadata, require_model_metadata


REPOSITORY = "Pranjal2041/cua-speed-run"
DATASET_URL = (
    "https://huggingface.co/datasets/anonymousmypcbench/"
    "cua-speedrun-trajectories"
)
HUMAN_BASELINE = {
    "label": "OSWorld human baseline",
    "performance": 0.7236,
    "performance_label": "Human performance · 72.36%",
    "metric_references": {
        "median_time": {
            "value": 111.94,
            "label": "Human median · 111.94s",
            "region_label": "Superhuman performance",
        },
    },
    "note": "full 369-task OSWorld set",
}
REQUIRED_COLUMNS = {
    "model",
    "reasoning_effort",
    "model_type",
    "average_score_percent",
    "time_per_task_seconds",
    "median_time_per_task_seconds",
    "cost_per_task_usd",
    "average_turns_per_task",
    "release_date",
    "average_output_tokens_per_turn",
}
STATIC_ASSETS = (
    "instrument.css",
    "frontier.css",
    "results.css",
    "pareto-surface.js",
    "leaderboard.js",
)


def _number(value: str, *, field: str, row_number: int) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"row {row_number}: {field} must be numeric") from exc


def _optional_number(value: str, *, field: str, row_number: int) -> float | None:
    text = value.strip()
    return _number(text, field=field, row_number=row_number) if text else None


def load_results(path: Path) -> list[dict[str, object]]:
    """Read reviewed aggregate results into the normal dashboard contract."""
    metadata = load_model_metadata()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"missing CSV columns: {', '.join(sorted(missing))}")

        entries = []
        for row_number, row in enumerate(reader, start=2):
            model = row["model"].strip()
            effort = row["reasoning_effort"].strip()
            if not model or not effort:
                raise ValueError(f"row {row_number}: model and effort are required")
            model_metadata = require_model_metadata(metadata, model)
            score = _number(
                row["average_score_percent"],
                field="average_score_percent",
                row_number=row_number,
            )
            if not 0 <= score <= 100:
                raise ValueError(
                    f"row {row_number}: average_score_percent must be 0–100"
                )
            entries.append({
                "entry_id": row_number - 1,
                "entry_name": f"{model} · {effort}",
                "model_family": model,
                "reasoning_effort": effort,
                "model_type": model_metadata["model_type"],
                "mean_score": score / 100,
                "average_task_time_sec": _number(
                    row["time_per_task_seconds"],
                    field="time_per_task_seconds",
                    row_number=row_number,
                ),
                "median_task_time_sec": _number(
                    row["median_time_per_task_seconds"],
                    field="median_time_per_task_seconds",
                    row_number=row_number,
                ),
                "cost_per_task_usd": _optional_number(
                    row["cost_per_task_usd"],
                    field="cost_per_task_usd",
                    row_number=row_number,
                ),
                "average_turns_per_task": _optional_number(
                    row["average_turns_per_task"],
                    field="average_turns_per_task",
                    row_number=row_number,
                ),
                "release_date": model_metadata["release_date"],
                "average_output_tokens": _optional_number(
                    row["average_output_tokens_per_turn"],
                    field="average_output_tokens_per_turn",
                    row_number=row_number,
                ),
                "num_runs": 50,
            })
    if not entries:
        raise ValueError("results CSV is empty")
    records = dashboard_entries(entries)
    for record in records:
        record["model_metadata"] = require_model_metadata(metadata, record["model"])
    return records


def build_site(input_path: Path, output_dir: Path, *, public_context: dict | None = None,
               dataset_scope: dict | None = None, default_variants: tuple = (),
               ablation_variants: tuple = ()) -> Path:
    """Render a deterministic site directory ready for static hosting."""
    repository_root = Path(__file__).resolve().parents[1]
    service_root = repository_root / "results"
    with input_path.open(newline="", encoding="utf-8") as handle:
        is_catalog = "row_type" in next(csv.reader(handle), [])
    if is_catalog:
        return build_catalog_site(input_path, output_dir, service_root,
                                  public_context=public_context, dataset_scope=dataset_scope,
                                  default_variants=default_variants,
                                  ablation_variants=ablation_variants)
    records = load_results(input_path)
    benchmark = "osworld-energy50-representative@0.1"

    environment = Environment(
        loader=FileSystemLoader(service_root / "templates"),
        autoescape=select_autoescape(("html", "xml")),
    )
    html = environment.get_template("leaderboard.html").render(
        static_export=True,
        repository=REPOSITORY,
        dataset_url=DATASET_URL,
        active="frontier",
        user=None,
        login_url="#",
        dataset_options=[{
            "label": "OSWorld Energy50",
            "href": "./",
            "entry_count": len(records),
            "active": True,
        }],
        selected_dataset={
            "label": "OSWorld Energy50",
            "records": records,
            "task_counts": [50],
        },
        benchmark_name=benchmark,
        current=records,
        dashboard_entries=records,
        dashboard_baseline=HUMAN_BASELINE,
        entry_count=len(records),
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    asset_output = output_dir / "static"
    asset_output.mkdir(exist_ok=True)
    (output_dir / "index.html").write_text(html, encoding="utf-8")
    (output_dir / ".nojekyll").touch()
    for asset_name in STATIC_ASSETS:
        shutil.copy2(service_root / "static" / asset_name, asset_output / asset_name)
    return output_dir / "index.html"


def build_catalog_site(input_path: Path, output_dir: Path, service_root: Path,
                       *, public_context: dict | None = None,
                       dataset_scope: dict | None = None,
                       default_variants: tuple = (),
                       ablation_variants: tuple = ()) -> Path:
    repository_root = service_root.parent
    catalog = load_catalog(input_path, METADATA_PATH,
                           repository_root / "data/results-curation.json")
    datasets = catalog["datasets"]
    if dataset_scope is not None:
        if not dataset_scope or set(dataset_scope) - datasets.keys():
            raise ValueError("Publication scope must contain known datasets")
        selected = {}
        for name, subset in dataset_scope.items():
            dataset = datasets[name]
            if dataset["task_counts"] != [subset["selected_tasks"]]:
                raise ValueError(f"Paper task count does not match catalog: {name}")
            selected[name] = {**dataset, "paper_subset": subset,
                              "label": f'{subset["label"]} · {subset["selected_tasks"]} tasks'}
        # Remove only generated dataset pages left by an earlier, broader build.
        for name, dataset in datasets.items():
            if name not in selected and Path(dataset["href"]).name == dataset["href"]:
                (output_dir / dataset["href"]).unlink(missing_ok=True)
        included = sum(len(dataset["records"]) for dataset in selected.values())
        catalog = {**catalog, "datasets": selected, "included_rows": included,
                   "publication_scope": {
                       "datasets": list(selected),
                       "omitted_reviewed_rows": catalog["included_rows"] - included,
                       "note": "Paper task subsets. The source CSV retains the full archive.",
                   }}
        datasets = selected
    # A variant that names the default setting adds no information, so the
    # published record uses the plain model name.
    for dataset in datasets.values():
        for record in (*dataset["records"], *dataset["excluded_evaluations"]):
            if record["variant"] in default_variants:
                record["variant"] = ""
                record["series"] = record["model"]
        # Ablations are shown only when a reader includes them.
        for record in dataset["records"]:
            record["ablation"] = record["variant"] in ablation_variants
        dataset["has_ablations"] = any(record["ablation"] for record in dataset["records"])
    previous_catalog = output_dir / "results-catalog.json"
    old_pages = {}
    if previous_catalog.is_file():
        for name, groups in json.loads(previous_catalog.read_text())["datasets"].items():
            if isinstance(groups, list) and name in datasets:
                for group in groups:
                    href = group["href"]
                    if Path(href).name == href and href.startswith("contract-"):
                        old_pages[href] = datasets[name]["href"]
    template_paths = [service_root / "templates"]
    if public_context:
        template_paths.insert(0, repository_root / "website/templates")
    environment = Environment(
        loader=FileSystemLoader(template_paths),
        autoescape=select_autoescape(("html", "xml")),
    )
    template = environment.get_template("leaderboard.html")
    static_asset_versions = {
        name: hashlib.sha256((service_root / "static" / name).read_bytes()).hexdigest()[:16]
        for name in ("leaderboard.js", "frontier.css")
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    asset_output = output_dir / "static"
    asset_output.mkdir(exist_ok=True)
    for asset_name in STATIC_ASSETS:
        shutil.copy2(service_root / "static" / asset_name, asset_output / asset_name)
    shutil.copy2(input_path, output_dir / "trajectory-metrics.csv")
    shutil.copy2(METADATA_PATH, output_dir / "model-metadata.json")
    shutil.copy2(PRICING_PATH, output_dir / "results-pricing.json")
    evidence_root = repository_root / "data" / "results-evidence"
    if evidence_root.is_dir():
        shutil.copytree(evidence_root, output_dir / "results-evidence", dirs_exist_ok=True)
    cost_fields = (
        "run_id", "model", "effort", "source_cost_usd", "cost_usd", "cost_kind",
        "cost_label", "cost_note", "cost_range_min_usd", "cost_range_max_usd",
        "cost_coverage_tasks", "cost_total_tasks", "cost_source", "cost_source_url",
        "cost_pricing_model", "source_archive_url",
    )
    with (output_dir / "display-costs.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("dataset", *cost_fields))
        writer.writeheader()
        for name, dataset in datasets.items():
            for record in dataset["records"]:
                writer.writerow({"dataset": name, **{key: record[key] for key in cost_fields}})
    (output_dir / "results-catalog.json").write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    default_page = next(iter(datasets.values()))["href"]
    for name, dataset in datasets.items():
        records = dataset["records"]
        html = template.render(
            **(public_context or {}),
            static_export=True, static_catalog=catalog, selected_dataset=dataset,
            static_asset_versions=static_asset_versions,
            repository=REPOSITORY, dataset_url=DATASET_URL,
            active="frontier", user=None, login_url="#",
            dataset_options=[{
                "label": option["label"], "href": option["href"],
                "entry_count": len(option["records"]), "active": key == name,
            } for key, option in datasets.items()],
            current=records, dashboard_entries=records, dashboard_baseline=None,
            entry_count=len(records),
        )
        (output_dir / dataset["href"]).write_text(html, encoding="utf-8")
        if dataset["href"] == default_page:
            (output_dir / "index.html").write_text(html, encoding="utf-8")
    # Existing local preview tabs must not keep showing the rejected split view.
    for old_href, new_href in old_pages.items():
        target = escape(new_href, quote=True)
        (output_dir / old_href).write_text(
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            f'<meta http-equiv="refresh" content="0;url={target}">'
            f'<title>Results moved</title><a href="{target}">View dataset results</a></html>',
            encoding="utf-8",
        )
    (output_dir / ".nojekyll").touch()
    return output_dir / "index.html"


def main() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=repository_root / "data" / "all-hf-model-trajectory-metrics-2026-09-13.csv",
        help="Reviewed trajectory metrics CSV (or legacy aggregate CSV)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=repository_root / "_site",
        help="Static site output directory",
    )
    arguments = parser.parse_args()
    index = build_site(arguments.input.resolve(), arguments.output.resolve())
    print(f"Built {index}")


if __name__ == "__main__":
    main()
