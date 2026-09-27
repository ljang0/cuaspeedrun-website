"""Auditable static-display cost estimates; never rewrite archived measurements."""

from __future__ import annotations

import json
import math
from pathlib import Path


PRICING_PATH = Path(__file__).resolve().parents[1] / "data/results-pricing.json"


def load_pricing(path: Path = PRICING_PATH) -> dict:
    registry = json.loads(path.read_text())
    for model, price in registry["models"].items():
        if not price["source_url"].startswith("https://") or not price["note"]:
            raise ValueError(f"{model}: pricing requires a source and assumptions")
        for key in ("input", "cached_input", "output"):
            if not math.isfinite(price[key]) or price[key] < 0:
                raise ValueError(f"{model}: invalid {key} price")
        if price["cached_input"] > price["input"]:
            raise ValueError(f"{model}: cached input exceeds regular input price")
    return registry


def _number(row: dict, key: str) -> float | None:
    value = row.get(key, "")
    if value in (None, ""):
        return None
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{row['run_id']}: invalid {key}: {value}")
    return number


def display_cost(row: dict, registry: dict) -> dict:
    """Prefer original cost, full-coverage API estimates, then coverage estimates."""
    count = int(row["n_trajectories"])
    source = _number(row, "cost_per_task_usd")
    price = registry["models"].get(row["model_name"])
    result = {
        "source_cost_usd": source, "cost_usd": source,
        "cost_kind": "unavailable", "cost_label": "Usage not logged",
        "cost_note": "No complete token usage or recorded cost is available.",
        "cost_range_min_usd": None, "cost_range_max_usd": None,
        "cost_coverage_tasks": 0, "cost_total_tasks": count,
        "cost_source": "", "cost_source_url": "", "cost_pricing_model": "",
        "cost_unit_prices": price,
    }
    if source is not None:
        recorded = row["cost_basis"] == "recorded_provider_usage_cost"
        reconstructed = row["cost_basis"].startswith("published_API_rate_estimate_")
        result.update(
            cost_kind="recorded" if recorded else "source_estimate",
            cost_label="Recorded usage" if recorded else ("API estimate · logged usage" if reconstructed else "Logged estimate"),
            cost_note=f"{row['cost_basis']}. {row.get('cost_exclusions', '')}",
            cost_coverage_tasks=count,
            cost_source=row.get("cost_pricing_source") or row["cost_basis"],
            cost_source_url=row.get("cost_pricing_source_url") or row["source_archive_url"].split(" | ")[0],
        )
        return result

    low_key = "reference_cost_all_input_cached_usd_per_task"
    high_key = "reference_cost_no_input_cached_usd_per_task"
    low, high = _number(row, low_key), _number(row, high_key)
    if high is not None and _number(row, high_key + "_n") == count:
        if low is not None and _number(row, low_key + "_n") != count:
            low = None
        if low is not None and low > high:
            raise ValueError(f"{row['run_id']}: inverted reference-cost interval")
        result.update(
            cost_usd=high, cost_kind="reference_estimate",
            cost_label="API estimate · no cache",
            cost_note=("API-equivalent estimate using recorded tokens and no input caching; "
                       "not historical billing. " + row["reference_cost_basis"]),
            cost_range_min_usd=low, cost_range_max_usd=high,
            cost_coverage_tasks=count, cost_source=row["reference_cost_source"],
            cost_source_url=row["reference_cost_source"].split(" ")[0],
            cost_pricing_model=row["reference_cost_model_id"],
        )
        return result

    input_tokens = _number(row, "input_tokens_per_task")
    output_tokens = _number(row, "generated_tokens_per_task")
    if (price and price["estimate_from_usage"] and input_tokens is not None
            and output_tokens is not None
            and _number(row, "input_tokens_per_task_n") == count
            and _number(row, "generated_tokens_per_task_n") == count):
        high = (input_tokens * price["input"] + output_tokens * price["output"]) / 1e6
        low = (input_tokens * price["cached_input"] + output_tokens * price["output"]) / 1e6
        result.update(
            cost_usd=high, cost_kind="standard_rate_proxy",
            cost_label="Standard-price proxy · no cache",
            cost_note=(f"{price['note']} Recorded input/output tokens; no input caching assumed. "
                       f"Rates verified {registry['verified_on']}; excludes other charges."),
            cost_range_min_usd=low, cost_range_max_usd=high,
            cost_coverage_tasks=count,
            cost_source=f"{price['source_url']} (verified {registry['verified_on']})",
            cost_source_url=price["source_url"], cost_pricing_model=price["model_id"],
        )
        return result

    observed = _number(row, "cost_per_task_usd_observed_mean")
    covered = _number(row, "cost_per_task_usd_n") or 0
    if observed is not None and 0 < covered < count:
        result.update(
            cost_usd=observed, cost_kind="coverage_estimate",
            cost_label=f"Estimate · {int(covered)}/{count} tasks",
            cost_note=(f"Mean cost of {int(covered)}/{count} tasks with logged costs, used as a "
                       "per-task estimate for the result. Assumes missing tasks have the same "
                       "mean cost; their actual cost is unknown, not zero. " + row["cost_basis"]),
            cost_coverage_tasks=int(covered),
            cost_source=row.get("cost_pricing_source") or row["cost_basis"],
            cost_source_url=row.get("cost_pricing_source_url") or row["source_archive_url"].split(" | ")[0],
        )
    elif price:
        result.update(
            cost_note=price["note"], cost_source_url=price["source_url"],
            cost_source=f"{price['source_url']} (verified {registry['verified_on']})",
            cost_pricing_model=price["model_id"],
        )
    return result
