"""Static-only adapter for reviewed trajectory metrics; no scoring or inference."""

from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter
from pathlib import Path

from frontier import dashboard_entries
from results_model_metadata import load_model_metadata, require_model_metadata
from results_costs import display_cost, load_pricing


PROVENANCE_FIELDS = (
    "split_dset_name", "benchmark_name", "benchmark_version", "template_name",
    "benchmark_content_hash", "track_name", "measurement_hash", "eval_algorithm",
    "agents_per_evaluation", "timeout_sec_values", "inference_tier", "io_variant", "backend",
    "time_definition", "parallel_evaluations",
)
REQUIRED_COLUMNS = {
    "split_dset_name",
    "row_type", "run_id", "model_name", "reasoning_effort", "n_trajectories",
    "expected_contract_tasks", "score_mean_pct", "score_mean_pct_n",
    "time_per_task_sec", "time_per_task_sec_n", "task_time_sec_median",
    "task_ids", "run_terminal_events", "billing_error_trajectories", "quality_flags",
    "source_archive_url", "cost_per_task_usd", "cost_basis", "notes",
    "avg_steps_per_task", "avg_steps_per_task_n",
    "env_action_items_per_task", "env_action_items_per_task_n",
}


def _number(row: dict[str, str], key: str) -> float | None:
    value = row.get(key, "").strip()
    if not value:
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{row['run_id']}: invalid {key}: {value}")
    return number


def _complete_task_mean(row: dict[str, str], key: str) -> float | None:
    """Only publish a mean when the metric covers the full task population."""
    count = _number(row, "n_trajectories")
    return _number(row, key) if count and _number(row, f"{key}_n") == count else None


def exclusion_reason(row: dict[str, str], *, combined: bool = False,
                     subset_size: int | None = None) -> str | None:
    """Conservative publication policy; all excluded evidence stays in the CSV."""
    if row["row_type"] != "evaluation" and not (
        (combined and row["row_type"] == "published_stitch")
        or (subset_size is not None and row["row_type"] == "published_subset")
    ):
        return row["row_type"]
    if _number(row, "billing_error_trajectories"):
        return "billing-affected"
    # Resuming appends to the same log: an earlier failure is not the final
    # outcome. Keep the ordered history intact, and still require full coverage.
    # A reviewed combination has no execution lifecycle of its own. Its source
    # histories remain provenance, not the final status of the combined data.
    terminal_events = [] if combined else json.loads(row["run_terminal_events"])
    if terminal_events[-1:] == ["run_failed"]:
        return "run-failed"
    if terminal_events[-1:] == ["run_cancelled"]:
        return "run-cancelled"
    if "publisher_reports_thinking_off_label_incorrect" in json.loads(row["quality_flags"]):
        return "superseded configuration label"
    count = _number(row, "n_trajectories")
    expected = subset_size if subset_size is not None else _number(row, "expected_contract_tasks")
    if not count or expected != count or any(_number(row, key) != count for key in (
        "score_mean_pct_n", "time_per_task_sec_n",
    )):
        return "incomplete task coverage"
    if any(_number(row, key) is None for key in (
        "score_mean_pct", "time_per_task_sec", "task_time_sec_median",
    )):
        return "missing score or timing"
    return None


def reviewed_subsets(rows: list[dict[str, str]], decisions: list[dict]) -> dict:
    """Publish pinned dataset slices without relabeling their parent contracts."""
    reviewed = {}
    for decision in decisions:
        key = (decision["run_id"], decision["dataset"])
        candidates = [r for r in rows if (r["run_id"], r["split_dset_name"]) == key
                      and r["row_type"] == "published_subset"]
        if len(candidates) != 1 or key in reviewed:
            raise ValueError(f"{key}: ambiguous reviewed subset")
        row = candidates[0]
        task_ids = json.loads(row["task_ids"])
        parents = [r for r in rows if r["row_type"] == "evaluation"
                   and r["run_id"] == row["run_id"] and r["archive_sha256"] == row["archive_sha256"]]
        anchors = [r for r in rows if r["row_type"] == "evaluation"
                   and r["split_dset_name"] == row["split_dset_name"] and not exclusion_reason(r)]
        if (row["archive_sha256"] != decision["archive_sha256"]
                or row["selected_task_seed_set_sha256"] != decision["task_seed_sha256"]
                or len(task_ids) != len(set(task_ids)) or len(task_ids) != decision["task_count"]
                or exclusion_reason(row, subset_size=decision["task_count"])
                or len(parents) != 1 or exclusion_reason(parents[0])
                or any(row[k] != parents[0][k] for k in (
                    "model_name", "reasoning_effort", "expected_contract_tasks", "benchmark_content_hash"))
                or not set(task_ids) < set(json.loads(parents[0]["task_ids"]))
                or not anchors or any(set(task_ids) != set(json.loads(r["task_ids"])) for r in anchors)):
            raise ValueError(f"{key}: invalid reviewed subset identity or coverage")
        reviewed[key] = decision["task_count"]
    return reviewed


def combined_sources(rows: list[dict[str, str]], decisions: dict) -> dict[str, str]:
    """Resolve reviewed combined rows and suppress only their pinned components."""
    primary = {row["run_id"]: row for row in rows
               if row["row_type"] in {"evaluation", "published_stitch"}}
    replaced = {}
    for run_id, decision in decisions.items():
        sources = decision.get("replaces", [])
        if not sources:
            continue
        row = primary[run_id]
        if (row["row_type"] != "published_stitch" or len(set(sources)) != len(sources)
                or run_id in sources or decision.get("exclude_reason")
                or exclusion_reason(row, combined=True)):
            raise ValueError(f"{run_id}: invalid combined result")
        components = [primary[source] for source in sources]
        hashes = " | ".join(component["archive_sha256"] for component in components)
        if row["archive_sha256"] != hashes or decision["archive_sha256"] != hashes:
            raise ValueError(f"{run_id}: combined archive identity changed")
        for component in components:
            if component["row_type"] != "evaluation" or any(
                component[key] != row[key] for key in
                ("split_dset_name", "model_name", "reasoning_effort", "benchmark_content_hash")
            ):
                raise ValueError(f"{run_id}: incompatible combined source")
            source = component["run_id"]
            if source in replaced:
                raise ValueError(f"{source}: used by multiple combined results")
            replaced[source] = run_id
    return replaced


def dataset_label(name: str) -> str:
    # Display only; unknown datasets require no code changes to be published.
    words = {"osworld": "OSWorld", "osworld2": "OSWorld2", "cua": "CUA",
             "mypcbench": "MyPCBench", "energy38": "Energy38",
             "energy50": "Energy50", "k52": "K52", "k26": "K26"}
    return " ".join(words.get(word, word.capitalize()) for word in name.split("-"))


def load_catalog(path: Path, metadata_path: Path, curation_path: Path | None = None) -> dict:
    # Reviewed publication decisions are data, never model-specific code.
    curation = json.loads(curation_path.read_text()) if curation_path else {"runs": {}}
    metadata = load_model_metadata(metadata_path)
    pricing = load_pricing()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"missing CSV columns: {', '.join(sorted(missing))}")
        rows = list(reader)

    replacements = combined_sources(rows, curation["runs"])
    subsets = reviewed_subsets(rows, curation.get("subsets", []))
    # A completed resume keeps its original run ID. Pin both snapshots so the
    # historical CSV bytes survive without showing an obsolete failure twice.
    for run_id, decision in curation["runs"].items():
        previous = decision.get("supersedes_archive_sha256", [])
        if not previous:
            continue
        snapshots = [row for row in rows if row["run_id"] == run_id and row["row_type"] == "evaluation"]
        current = [row for row in snapshots if row["archive_sha256"] == decision["archive_sha256"]]
        if (len(current) != 1 or exclusion_reason(current[0]) or
                set(previous) != {row["archive_sha256"] for row in snapshots if row is not current[0]} or
                any(row[key] != current[0][key] for row in snapshots for key in
                    ("model_name", "reasoning_effort", "run_plan_hash", "selected_task_seed_set_sha256"))):
            raise ValueError(f"{run_id}: invalid superseded snapshot identity")
    datasets = {}
    excluded = Counter()
    supporting = []
    for row_number, row in enumerate(rows, start=2):
        model_metadata = require_model_metadata(metadata, row["model_name"])
        decision = curation["runs"].get(row["run_id"], {})
        if (row["row_type"] == "evaluation" and
                row["archive_sha256"] in decision.get("supersedes_archive_sha256", [])):
            excluded["superseded snapshot"] += 1
            supporting.append(row)
            continue
        combined = bool(decision.get("replaces")) and row["row_type"] == "published_stitch"
        subset_size = subsets.get((row["run_id"], row["split_dset_name"])) if row["row_type"] == "published_subset" else None
        reason = exclusion_reason(row, combined=combined, subset_size=subset_size)
        if (row["row_type"] != "evaluation" and not combined and subset_size is None) or row["run_id"] in replacements:
            excluded["combined source" if row["run_id"] in replacements else reason] += 1
            supporting.append(row)
            continue
        if decision and decision["archive_sha256"] != row.get("archive_sha256"):
            raise ValueError(f"{row['run_id']}: curated archive identity changed")
        reason = reason or decision.get("exclude_reason")
        variant = decision.get("variant", "")
        series = row["model_name"] + (f" · {variant}" if variant else "")
        name = row["split_dset_name"].strip()
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        if not slug:
            raise ValueError(f"row {row_number}: dataset name is required")
        dataset = datasets.setdefault(name, {
            "name": name, "label": dataset_label(name),
            "href": f"dataset-{slug}.html", "records": [],
            "excluded_evaluations": [], "supporting_rows": 0,
        })
        if reason:
            excluded[reason] += 1
            dataset["excluded_evaluations"].append({
                "model": row["model_name"], "effort": row["reasoning_effort"],
                "run_id": row["run_id"], "reason": reason,
                "source_archive_url": row["source_archive_url"],
                "variant": variant, "series": series,
                "model_type": model_metadata["model_type"],
                "release_date": model_metadata["release_date"],
                "model_metadata": model_metadata,
            })
            continue
        score = _number(row, "score_mean_pct")
        if score > 100:
            raise ValueError(f"{row['run_id']}: score exceeds 100")
        responses = _number(row, "model_responses_per_task")
        usage_responses = _number(row, "usage_response_records_per_task")
        tokens = _number(row, "generated_tokens_per_task")
        cost = display_cost(row, pricing)
        record = dashboard_entries([{
            "entry_id": row_number,
            "entry_name": f"{row['model_name']} · {row['reasoning_effort']} · {row['run_id']}",
            "model_family": row["model_name"],
            "reasoning_effort": row["reasoning_effort"],
            "model_type": model_metadata["model_type"],
            "release_date": model_metadata["release_date"],
            "mean_score": score / 100,
            "average_task_time_sec": _number(row, "time_per_task_sec"),
            "median_task_time_sec": _number(row, "task_time_sec_median"),
            "cost_per_task_usd": cost["cost_usd"],
            "average_turns_per_task": responses,
            # Usage-only rejected responses must not inflate tokens/response.
            "average_output_tokens": (
                tokens / responses
                if tokens is not None and responses and responses == usage_responses else None
            ),
        }])[0]
        record.update({key: row.get(key, "") for key in (
            "run_id", "source_archive_url", "cost_basis", "notes", "quality_flags",
            "selected_task_seed_set_sha256", "run_terminal_events",
        )})
        record["row_type"] = row["row_type"]
        record.update(cost)
        record["model_metadata"] = model_metadata
        record["source_run_ids"] = decision.get("replaces", [row["run_id"]])
        record["source_archive_urls"] = row["source_archive_url"].split(" | ")
        if decision.get("notes"):
            record["notes"] += " " + decision["notes"]
        record["effort_rank"] = {"thinking_off": 0, "thinking_on": 6}.get(
            record["effort"], record["effort_rank"]
        )
        record["task_count"] = int(row["n_trajectories"])
        # One logged environment step is one action batch, not one response,
        # observation, or individual action within that batch.
        record["steps_per_task"] = _complete_task_mean(row, "avg_steps_per_task")
        # Count each recorded environment action inside a batch separately.
        # Provider-native tool calls can themselves wrap many actions and are
        # not interchangeable with this count (nor are model responses).
        record["tool_calls_per_task"] = _complete_task_mean(row, "env_action_items_per_task")
        record["model_responses_per_task"] = responses
        record["variant"] = variant
        record["series"] = series
        record["source_metadata"] = {key: row.get(key, "") for key in PROVENANCE_FIELDS}
        dataset["records"].append(record)

    if not datasets:
        raise ValueError("results CSV is empty")
    for row in supporting:
        dataset = datasets.get(row["split_dset_name"]) or datasets.get(row.get("benchmark_name"))
        if dataset is not None:
            dataset["supporting_rows"] += 1
    if len({dataset["href"] for dataset in datasets.values()}) != len(datasets):
        raise ValueError("dataset names must produce distinct page names")
    for dataset in datasets.values():
        dataset["records"].sort(key=lambda record: (-record["performance"], record["time_per_task_sec"]))
        dataset["task_counts"] = sorted({record["task_count"] for record in dataset["records"]})
    return {
        "datasets": dict(sorted(datasets.items(), key=lambda item: (
            -len(item[1]["records"]), item[0],
        ))),
        "excluded": dict(sorted(excluded.items())),
        "source_rows": len(rows),
        "model_metadata_verified_on": max(item["verified_on"] for item in metadata.values()),
        "curation_evidence": curation.get("evidence"),
        "included_rows": sum(len(dataset["records"]) for dataset in datasets.values()),
        "inventory_utc": max(row.get("inventory_utc", "") for row in rows),
    }
