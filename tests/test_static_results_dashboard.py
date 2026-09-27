from __future__ import annotations

import csv
from collections import Counter
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from bs4 import BeautifulSoup
import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def catalog_site(tmp_path_factory):
    output = tmp_path_factory.mktemp("dataset-site")
    subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / "scripts/build_results_dashboard.py"),
         "--output", str(output)],
        cwd=REPOSITORY_ROOT, check=True,
    )
    catalog = json.loads((output / "results-catalog.json").read_text())
    return output, catalog


def test_catalog_has_one_complete_view_per_dataset(catalog_site):
    output, catalog = catalog_site
    assert set(catalog["datasets"]) == {
        "osworld", "osworld-energy50-representative", "osworld2-k52",
        "osworld-unanimous-295", "osworld-pareto-48", "cua-world-long-k26",
        "mypcbench-energy38",
    }
    assert catalog["source_rows"] == 146
    assert catalog["included_rows"] == 96
    assert sum(catalog["excluded"].values()) == 50
    assert '[data-results-dashboard][data-static="true"] .results-table tbody tr { animation: none; }' in (output / "static/frontier.css").read_text()
    assert '[data-results-dashboard][data-static="true"] .results-volume .volume-point { animation: none; }' in (output / "static/frontier.css").read_text()
    source = REPOSITORY_ROOT / "data/all-hf-model-trajectory-metrics-2026-09-13.csv"
    assert (output / "trajectory-metrics.csv").read_bytes() == source.read_bytes()
    with source.open(newline="") as handle:
        originals = {i: row for i, row in enumerate(csv.DictReader(handle), start=2)}
    seen = set()
    assert len(list(output.glob("dataset-*.html"))) == 7
    assert not list(output.glob("contract-*.html"))
    for name, dataset in catalog["datasets"].items():
        soup = BeautifulSoup((output / dataset["href"]).read_text(), "html.parser")
        records = json.loads(soup.select_one("[data-results-data]").string)
        assert records == dataset["records"]
        version = hashlib.sha256((output / "static/leaderboard.js").read_bytes()).hexdigest()[:16]
        assert soup.select_one(f'script[src="static/leaderboard.js?v={version}"]')
        css_version = hashlib.sha256((output / "static/frontier.css").read_bytes()).hexdigest()[:16]
        assert soup.select_one(f'link[href="static/frontier.css?v={css_version}"]')
        assert json.loads(soup.select_one("[data-results-baseline]").string) is None
        assert not soup.select(".track-tab, .scope-bar, #season-select, [data-static-contract], select")
        assert "evaluation contract" not in soup.get_text().lower()
        assert len(soup.select(".dataset-tab")) == 7
        assert soup.select_one('.dataset-tab[aria-current="true"]')["href"] == dataset["href"]
        assert len(soup.select("[data-results-body] tr")) == len(records)
        assert len(soup.select("[data-excluded-run]")) == len(dataset["excluded_evaluations"])
        assert not soup.select(".status-cell")
        for link in soup.select(".dataset-tab"):
            assert (output / link["href"]).is_file()
        for record in records:
            assert record["entry_id"] not in seen
            seen.add(record["entry_id"])
            original = originals[record["entry_id"]]
            assert original["row_type"] in {"evaluation", "published_stitch", "published_subset"}
            assert record["row_type"] == original["row_type"]
            assert record["model"] == original["model_name"]
            assert original["split_dset_name"] == name
            if original["row_type"] == "published_subset":
                assert int(original["n_trajectories"]) < int(original["expected_contract_tasks"])
            else:
                assert original["n_trajectories"] == original["expected_contract_tasks"]
            terminal_events = json.loads(original["run_terminal_events"])
            if original["row_type"] == "evaluation":
                assert not terminal_events or terminal_events[-1] not in {"run_failed", "run_cancelled"}
            assert record["run_terminal_events"] == original["run_terminal_events"]
            assert int(original["billing_error_trajectories"]) == 0
            for key, value in record["source_metadata"].items():
                assert original[key] == value
            assert record["performance"] == float(original["score_mean_pct"]) / 100
            assert record["time_per_task_sec"] == float(original["time_per_task_sec"])
            assert record["median_time_per_task_sec"] == float(original["task_time_sec_median"])
            assert original["avg_steps_per_task_n"] == original["n_trajectories"]
            assert record["steps_per_task"] == float(original["avg_steps_per_task"])
            assert original["env_action_items_per_task_n"] == original["n_trajectories"]
            assert record["tool_calls_per_task"] == float(original["env_action_items_per_task"])
            assert record["model_responses_per_task"] == (float(original["model_responses_per_task"]) if original["model_responses_per_task"] else None)
            assert record["source_cost_usd"] == (float(original["cost_per_task_usd"]) if original["cost_per_task_usd"] else None)
            if record["source_cost_usd"] is not None:
                assert record["cost_usd"] == record["source_cost_usd"]
            assert record["source_archive_url"] == original["source_archive_url"]
            assert not record["qualification_known"]
        # Every real evaluation is displayed, named below, or linked as a
        # component of an explicitly reviewed combined result.
        source_runs = {row["run_id"] for row in originals.values()
                       if row["split_dset_name"] == name and row["row_type"] in {"evaluation", "published_subset"}}
        assert source_runs == ({source for r in records for source in r["source_run_ids"]}
                               | {r["run_id"] for r in dataset["excluded_evaluations"]})
    assert len(seen) == 96


def test_all_datasets_include_reviewed_results_without_configuration_partitions(catalog_site):
    _, catalog = catalog_site
    datasets = catalog["datasets"]
    assert {name: len(dataset["records"]) for name, dataset in datasets.items()} == {
        "osworld-energy50-representative": 58, "osworld2-k52": 21,
        "osworld": 3, "osworld-unanimous-295": 6, "cua-world-long-k26": 2,
        "osworld-pareto-48": 2,
        "mypcbench-energy38": 4,
    }
    records = [record for dataset in datasets.values() for record in dataset["records"]]
    by_run = {record["run_id"]: record for record in records}
    assert {"svc_59_708d1b", "svc_60_8db123", "svc_61_1ec4be",
            "svc_87_ed8093", "svc_88_3a6bc6"} <= by_run.keys()
    assert by_run["svc_88_3a6bc6"]["cost_kind"] == "reference_estimate"
    assert by_run["svc_88_3a6bc6"]["cost_usd"] > 0
    assert by_run["svc_88_3a6bc6"]["effort"] == "thinking_off"
    assert "svc_50_592ed5" not in by_run  # Superseded configuration label.
    assert "svc_68_bca75f" not in by_run  # Represented by the combined result.
    assert {r["model"] for r in datasets["osworld2-k52"]["records"]} == {
        "GPT-6 Astra", "Gemini 3.8 Flash", "Claude Opus 5", "Claude Sonnet 5",
        "GLM-5V Turbo", "MiniMax M3", "Meta Muse Spark 1.3", "Kimi K3",
    }
    assert len(datasets["osworld2-k52"]["excluded_evaluations"]) == 0
    energy = datasets["osworld-energy50-representative"]["records"]
    assert {"svc_151_181620", "svc_122_93c9c5", "svc_59_708d1b", "svc_61_1ec4be"} <= {r["run_id"] for r in energy}
    assert len({r["source_metadata"]["track_name"] for r in energy}) > 1
    astra = by_run["svc_151_181620"]
    assert astra["average_output_tokens"] is None
    assert astra["turns_per_task"] is None
    assert "not_subscription_bill" in astra["cost_basis"]
    assert astra["release_date"] == "2026-09-03"
    assert astra["model_type"] == "closed"


def test_steps_count_action_batches_without_changing_response_metrics(catalog_site):
    output, catalog = catalog_site
    for dataset in catalog["datasets"].values():
        soup = BeautifulSoup((output / dataset["href"]).read_text(), "html.parser")
        assert soup.select_one('[data-curve="steps"]').get_text() == "Steps"
        assert not soup.select('[data-curve="turns"]')
        assert "one step call counts once" in soup.get_text()
        assert "Output tokens per model response" in soup.get_text()
        assert all(r["steps_per_task"] is not None for r in dataset["records"])
    energy = {r["run_id"]: r for r in catalog["datasets"]["osworld-energy50-representative"]["records"]}
    for run_id, steps in {
        "svc_122_93c9c5": 5.90, "svc_151_181620": 6.30,
        "svc_152_8d02f4": 6.52, "svc_121_b4bca3": 7.14,
        "svc_127_422895": 7.52,
    }.items():
        assert energy[run_id]["steps_per_task"] == steps
        assert energy[run_id]["model_responses_per_task"] is None
        assert energy[run_id]["average_output_tokens"] is None
    assert energy["svc_51_121311"]["steps_per_task"] == 34.32
    assert energy["svc_51_121311"]["model_responses_per_task"] == 35.14
    # Token lengths remain per model response, never per action batch.
    with (output / "trajectory-metrics.csv").open(newline="") as handle:
        originals = {i: row for i, row in enumerate(csv.DictReader(handle), start=2)}
    for dataset in catalog["datasets"].values():
        for record in dataset["records"]:
            source = originals[record["entry_id"]]
            responses, tokens = source["model_responses_per_task"], source["generated_tokens_per_task"]
            usage = source["usage_response_records_per_task"]
            expected = (
                float(tokens) / float(responses)
                if tokens and responses and float(responses) and usage
                and float(responses) == float(usage) else None
            )
            assert record["average_output_tokens"] == expected


def test_tool_calls_count_individual_actions_on_every_dataset(catalog_site):
    output, catalog = catalog_site
    for dataset in catalog["datasets"].values():
        soup = BeautifulSoup((output / dataset["href"]).read_text(), "html.parser")
        assert soup.select_one('[data-curve="tool_calls"]').get_text() == "Tool calls"
        assert soup.select_one('[data-curve="steps"]').get_text() == "Steps"
        assert "a batch of five actions counts as five, not one" in soup.get_text()
        assert "Separate observation and task-completion requests are not included" in soup.get_text()
        assert all(r["tool_calls_per_task"] is not None for r in dataset["records"])
    energy = {r["run_id"]: r for r in catalog["datasets"]["osworld-energy50-representative"]["records"]}
    # Real archived measurements: CLI harnesses still have environment-action
    # counts, even where their model tool-call/response trace is unavailable.
    for run_id, steps, calls in (
        ("svc_122_93c9c5", 5.90, 16.22),
        ("svc_153_795ea7", 7.22, 26.44),
        ("svc_13_01885e", 17.56, 48.16),
    ):
        record = energy[run_id]
        assert (record["steps_per_task"], record["tool_calls_per_task"]) == (steps, calls)
    assert energy["svc_153_795ea7"]["model_responses_per_task"] is None
    osworld2 = {r["run_id"]: r for r in catalog["datasets"]["osworld2-k52"]["records"]}
    assert osworld2["svc_145_4091f6"]["tool_calls_per_task"] == pytest.approx(350.0576923076923)
    assert osworld2["svc_147_d5291e"]["tool_calls_per_task"] == pytest.approx(386.5576923076923)


@pytest.mark.parametrize("withheld", [
    {"env_action_items_per_task": ""},
    {"env_action_items_per_task_n": ""},
    {"env_action_items_per_task_n": "49"},
    {"env_action_items_per_task_n": "0"},
])
def test_tool_call_means_require_complete_coverage(withheld):
    sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))
    from results_catalog import _complete_task_mean

    with (REPOSITORY_ROOT / "data/all-hf-model-trajectory-metrics-2026-09-13.csv").open(newline="") as handle:
        source = next(row for row in csv.DictReader(handle) if row["run_id"] == "svc_13_01885e")
    assert _complete_task_mean(source, "env_action_items_per_task") == 48.16
    # Withholding measurement/coverage from a real row must not fall back to
    # a model wrapper count, a batch count, an observed mean, or zero.
    source.update(withheld)
    assert _complete_task_mean(source, "env_action_items_per_task") is None
    assert _complete_task_mean(source, "avg_steps_per_task") == 17.56


def test_costs_use_source_evidence_and_label_every_estimate(catalog_site):
    output, catalog = catalog_site
    records = [r for d in catalog["datasets"].values() for r in d["records"]]
    assert Counter(r["cost_kind"] for r in records) == {
        "recorded": 10, "source_estimate": 50, "reference_estimate": 21,
        "standard_rate_proxy": 7, "coverage_estimate": 2, "unavailable": 6,
    }
    assert sum(r["cost_usd"] is not None for r in records) == 90
    with (output / "trajectory-metrics.csv").open(newline="") as handle:
        originals = {i: row for i, row in enumerate(csv.DictReader(handle), start=2)}
    registry = json.loads((output / "results-pricing.json").read_text())
    assert registry == json.loads((REPOSITORY_ROOT / "data/results-pricing.json").read_text())
    for record in records:
        source = originals[record["entry_id"]]
        assert record["cost_source_url"].startswith("https://")
        assert record["cost_note"]
        assert record["cost_total_tasks"] == int(source["n_trajectories"])
        if record["cost_kind"] == "reference_estimate":
            assert record["source_cost_usd"] is None
            assert record["cost_usd"] == float(source["reference_cost_no_input_cached_usd_per_task"])
            assert record["cost_range_min_usd"] == float(source["reference_cost_all_input_cached_usd_per_task"])
            assert record["cost_range_max_usd"] == record["cost_usd"]
            assert record["cost_coverage_tasks"] == int(source["reference_cost_no_input_cached_usd_per_task_n"])
            assert record["cost_source"] == source["reference_cost_source"]
        elif record["cost_kind"] == "standard_rate_proxy":
            price = registry["models"][record["model"]]
            input_tokens, output_tokens = float(source["input_tokens_per_task"]), float(source["generated_tokens_per_task"])
            assert record["cost_usd"] == pytest.approx((input_tokens * price["input"] + output_tokens * price["output"]) / 1e6)
            assert record["cost_range_min_usd"] == pytest.approx((input_tokens * price["cached_input"] + output_tokens * price["output"]) / 1e6)
            assert record["cost_coverage_tasks"] == int(source["input_tokens_per_task_n"]) == int(source["generated_tokens_per_task_n"])
            assert "proxy" in record["cost_label"] and "proxy" in record["cost_note"]
            assert price["note"] in record["cost_note"]
        elif record["cost_kind"] == "coverage_estimate":
            assert record["cost_usd"] == float(source["cost_per_task_usd_observed_mean"])
            assert record["cost_usd"] == pytest.approx(float(source["cost_usd_observed_total"]) / record["cost_coverage_tasks"])
            assert (record["cost_coverage_tasks"], record["cost_total_tasks"]) in {(46, 48), (293, 295)}
            assert "unknown, not zero" in record["cost_note"]
        elif record["cost_kind"] == "unavailable":
            assert record["model"] == "MiniMax M3"
            assert record["cost_usd"] is None
            assert not source["input_tokens_per_task"] and not source["generated_tokens_per_task"]
            assert record["cost_unit_prices"]["input"] == 0.30
            assert record["cost_unit_prices"]["output"] == 1.20
        else:
            assert record["cost_usd"] == float(source["cost_per_task_usd"])
    for dataset in catalog["datasets"].values():
        soup = BeautifulSoup((output / dataset["href"]).read_text(), "html.parser")
        assert soup.select_one('a[href="display-costs.csv"]')
        assert soup.select_one('a[href="results-pricing.json"]')
        for record in dataset["records"]:
            cell = soup.select_one(f'[data-entry-id="{record["entry_id"]}"] .cost-cell')
            assert record["cost_label"] in cell.get_text()
            assert cell["title"] == record["cost_note"]
            if record["cost_usd"] is None:
                assert "per 1M tokens" in cell.get_text()
                assert not cell.get_text().strip().startswith("$")
    with (output / "display-costs.csv").open(newline="") as handle:
        exported = {(r["dataset"], r["run_id"]): r for r in csv.DictReader(handle)}
    assert len(exported) == 96
    for record in records:
        for key, value in exported[(record["source_metadata"]["split_dset_name"], record["run_id"])].items():
            if key != "dataset":
                assert value == ("" if record[key] is None else str(record[key]))


def test_all_model_metadata_is_sourced_and_visible(catalog_site):
    output, catalog = catalog_site
    metadata_path = REPOSITORY_ROOT / "data/model-metadata.json"
    assert (output / "model-metadata.json").read_bytes() == metadata_path.read_bytes()
    registry = json.loads(metadata_path.read_text())
    expected = {
        "Claude Opus 5": ("closed", "2026-07-24"),
        "Claude Sonnet 5": ("closed", "2026-06-30"),
        "GLM-5V Turbo": ("closed", "2026-04-01"),
        "GPT-5.6 Luna": ("closed", "2026-07-09"),
        "GPT-5.6 Sol": ("closed", "2026-07-09"),
        "GPT-6 Astra": ("closed", "2026-09-03"),
        "Gemini 3 Flash Preview": ("closed", "2025-12-17"),
        "Gemini 3.6 Flash": ("closed", "2026-07-21"),
        "Gemini 3.7 Flash": ("closed", "2026-08-13"),
        "Gemini 3.8 Flash": ("closed", "2026-09-02"),
        "Kimi K3": ("open", "2026-07-16"),
        "Meta Muse Spark": ("closed", None),
        "Meta Muse Spark 1.1": ("closed", "2026-07-09"),
        "Meta Muse Spark 1.2": ("closed", "2026-08-05"),
        "Meta Muse Spark 1.3": ("closed", "2026-09-02"),
        "MiniMax M3": ("open", "2026-06-01"),
        "Qwen3.5-9B-Thinking": ("open", "2026-03-02"),
        "Yutori n2": ("closed", "2026-08-26"),
    }
    assert set(registry["models"]) == set(expected)
    for model, values in registry["models"].items():
        assert (values["model_type"], values["release_date"]) == expected[model]
        assert values["access_source"].startswith("https://")
        if values["release_date"]:
            assert values["release_source"].startswith("https://")
        else:
            assert "Version unverified" in values["notes"]
    unknown = []
    for dataset in catalog["datasets"].values():
        soup = BeautifulSoup((output / dataset["href"]).read_text(), "html.parser")
        assert soup.select_one('a[href="model-metadata.json"]')
        for record in dataset["records"] + dataset["excluded_evaluations"]:
            assert (record["model_type"], record["release_date"]) == expected[record["model"]]
            values = record["model_metadata"]
            assert values["verified_on"] == registry["models"][record["model"]].get("verified_on", registry["verified_on"])
            assert values["model"] == record["model"]
            if "entry_id" not in record:
                assert soup.select_one(f'[data-excluded-run="{record["run_id"]}"] .model-metadata')
                continue
            label = soup.select_one(f'[data-entry-id="{record["entry_id"]}"] .model-metadata')
            assert label["title"] == values["notes"]
            assert label.select_one("a")["href"] == values["access_source"]
            if record["release_date"]:
                assert f'Released {record["release_date"]}' in label.get_text()
                assert label.select("a")[1]["href"] == values["release_source"]
            else:
                unknown.append(record["run_id"])
                assert "Release unverified (version unknown)" in label.get_text()
    assert unknown == ["svc_16_409b44", "svc_16_409b44"]


def test_missing_model_metadata_fails_build_instead_of_silently_mislabeling(tmp_path):
    # Exercise the real source CSV and registry, withholding one reviewed entry.
    registry = json.loads((REPOSITORY_ROOT / "data/model-metadata.json").read_text())
    del registry["models"]["GPT-6 Astra"]
    path = tmp_path / "metadata.json"
    path.write_text(json.dumps(registry))
    result = subprocess.run(
        [sys.executable, "-c",
         "import sys; from pathlib import Path; sys.path.insert(0, 'scripts'); "
         "from results_catalog import load_catalog; "
         "load_catalog(Path('data/all-hf-model-trajectory-metrics-2026-09-13.csv'), "
         "Path(sys.argv[1]), Path('data/results-curation.json'))", str(path)],
        cwd=REPOSITORY_ROOT, capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "GPT-6 Astra: missing reviewed model metadata" in result.stderr


def test_completed_resumes_keep_failure_history_without_being_excluded(catalog_site):
    output, catalog = catalog_site
    dataset = catalog["datasets"]["osworld2-k52"]
    by_run = {record["run_id"]: record for record in dataset["records"]}
    # Real terminal sequences from the published archive events.jsonl files.
    histories = {
        "svc_82_a48586": ["run_done", "run_done", "run_failed", "run_done", "run_done"],
        "svc_83_03ee99": ["run_done", "run_failed", "run_done", "run_done", "run_done"],
        "svc_84_e2ef21": ["run_failed", "run_done", "run_done", "run_done", "run_failed", "run_done"],
        "svc_146_518434": ["run_failed", "run_done"],
    }
    soup = BeautifulSoup((output / dataset["href"]).read_text(), "html.parser")
    for run_id, history in histories.items():
        record = by_run[run_id]
        assert json.loads(record["run_terminal_events"]) == history
        assert record["task_count"] == 52
        assert "Resumed after earlier interruptions" in record["notes"]
        assert not soup.select(f'[data-excluded-run="{run_id}"]')
        row = soup.select_one(f'[data-entry-id="{record["entry_id"]}"]')
        assert "final archived event is run_done" in row.get_text()
    assert by_run["svc_146_518434"]["performance"] == pytest.approx(0.19190740246556306)
    assert by_run["svc_146_518434"]["time_per_task_sec"] == pytest.approx(1860.850342020019)
    assert not dataset["excluded_evaluations"]
    assert catalog["excluded"]["superseded snapshot"] == 2
    with (REPOSITORY_ROOT / "data/all-hf-model-trajectory-metrics-2026-09-13.csv").open(newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    for run_id, history in histories.items():
        linked_rows = [r for r in source_rows if r["run_id"] == run_id]
        assert {r["row_type"] for r in linked_rows} == {"evaluation", "retained_extra_attempts"}
        assert all(json.loads(r["run_terminal_events"]) == history for r in linked_rows)
    # Combining recovery data does not rewrite an original execution's history.
    original = next(r for r in source_rows if r["run_id"] == "svc_68_bca75f")
    assert json.loads(original["run_terminal_events"])[-1] == "run_failed"


def test_reviewed_variants_and_exclusions_preserve_source_identity(catalog_site):
    output, catalog = catalog_site
    energy = catalog["datasets"]["osworld-energy50-representative"]
    included = {r["run_id"]: r for r in energy["records"]}
    excluded = {r["run_id"]: r for r in energy["excluded_evaluations"]}
    assert len(excluded) == 8
    assert "svc_61_1ec4be" in included and "svc_97_82e253" in excluded
    assert "Older reference" in excluded["svc_97_82e253"]["reason"]
    assert "Not a failed run" in excluded["svc_97_82e253"]["reason"]
    contributor = {"svc_58_38520a", "svc_60_72500b", "svc_59_d8a6d4",
                   "svc_61_96ce3f", "svc_69_41f88a"}
    assert {r["run_id"] for r in energy["records"] if r["model"] == "Meta Muse Spark 1.1"} == contributor
    for run_id in ("svc_29_8c9590", "svc_31_c00240", "svc_30_d46514",
                   "svc_34_8c4108", "svc_32_109178"):
        assert "Rate-limited playground contrast" in excluded[run_id]["reason"]
    expected_variants = {
        "svc_122_93c9c5": "Normal I/O", "svc_127_422895": "Fast I/O",
        "svc_121_b4bca3": "Normal I/O", "svc_151_181620": "Normal I/O",
        "svc_152_8d02f4": "Normal I/O",
        "svc_89_b4886a": "Single tool call", "svc_90_357e81": "Single tool call",
        "svc_143_e8d33d": "Batched tool calls", "svc_144_1f26e4": "Batched tool calls",
        "svc_141_f28fed": "Batched tool calls",
        "svc_20_9456b8": "Direct API", "svc_21_00be0a": "Direct API", "svc_63_ccb407": "Direct API",
        "svc_153_795ea7": "Codex", "svc_154_323b97": "Codex",
        "svc_155_7fbf62": "Codex", "svc_156_2bc119": "Codex",
    }
    soup = BeautifulSoup((output / energy["href"]).read_text(), "html.parser")
    for run_id, label in expected_variants.items():
        record = included[run_id]
        assert record["variant"] == label
        assert record["series"] == f"{record['model']} · {label}"
        row = soup.select_one(f'[data-entry-id="{record["entry_id"]}"]')
        assert row.select_one(".model-cell a").get_text() == record["series"]
    assert len({(r["series"], r["effort"]) for r in energy["records"]}) == 58
    decisions = json.loads((REPOSITORY_ROOT / "data/results-curation.json").read_text())
    with (REPOSITORY_ROOT / "data/all-hf-model-trajectory-metrics-2026-09-13.csv").open(newline="") as handle:
        originals = {r["run_id"]: r for r in csv.DictReader(handle)
                     if r["row_type"] in {"evaluation", "published_stitch"}}
    for run_id, decision in decisions["runs"].items():
        assert decision["archive_sha256"] == originals[run_id]["archive_sha256"]
        dataset = catalog["datasets"][originals[run_id]["split_dset_name"]]
        assert run_id in {r["run_id"] for r in dataset["records"] + dataset["excluded_evaluations"]}
    assert catalog["curation_evidence"] == decisions["evidence"]


def test_recovery_replaces_three_tasks_in_one_combined_result(catalog_site):
    output, catalog = catalog_site
    dataset = catalog["datasets"]["osworld-energy50-representative"]
    records = [r for r in dataset["records"]
               if r["model"] == "Meta Muse Spark 1.3" and r["effort"] == "xhigh"]
    assert len(records) == 1
    record = records[0]
    assert record["run_id"] == "svc_68 + rerun3_xhigh13"
    assert record["task_count"] == 50
    assert record["performance"] == pytest.approx(0.7761904360085809)
    assert record["time_per_task_sec"] == pytest.approx(612.07638625182)
    assert record["median_time_per_task_sec"] == pytest.approx(368.3002541610001)
    assert record["cost_kind"] == "reference_estimate"
    assert record["cost_usd"] > 0
    assert record["source_run_ids"] == ["svc_68_bca75f", "rerun3_xhigh13"]
    assert record["source_metadata"]["parallel_evaluations"] == "8 | 3"
    assert "47 original tasks plus three rerun replacements" in record["notes"]
    assert "concurrency 3" in record["notes"]
    soup = BeautifulSoup((output / dataset["href"]).read_text(), "html.parser")
    row = soup.select_one(f'[data-entry-id="{record["entry_id"]}"]')
    assert row.select_one(".model-cell > span > a")["href"] == record["source_archive_urls"][0]
    assert [a["href"] for a in row.select(".row-provenance a")] == record["source_archive_urls"]
    for source in record["source_run_ids"]:
        assert not soup.select(f'[data-excluded-run="{source}"]')
    assert catalog["excluded"]["combined source"] == 2


def test_jy_sol_luna_low_append_preserves_history_and_separates_retry(catalog_site):
    output, catalog = catalog_site
    source = output / "trajectory-metrics.csv"
    # All 124 previous rows, including their earlier reviewed corrections,
    # remain byte-identical. The append adds two evaluations and one attempt.
    assert hashlib.sha256(source.read_bytes()[:956538]).hexdigest() == "a7913930945e95c725a49f1792f536205b39506fd1ceec44a1d75d12a661588e"
    with source.open(newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        assert len(reader.fieldnames) == 218 and len(rows) == 146
    new = rows[124:127]
    assert Counter(r["row_type"] for r in new) == {"evaluation": 2, "retained_extra_attempts": 1}
    expected = {
        "svc_62_9b9e92": ("GPT-5.6 Sol", 65.81298513479518, 100.09055964158, 11.2, 0.3190882, 608),
        "svc_63_ccb407": ("GPT-5.6 Luna", 61.812985134795184, 73.63877297137999, 10.12, 0.0106699, 553),
    }
    records = {r["run_id"]: r for r in catalog["datasets"]["osworld-energy50-representative"]["records"]}
    for row in new:
        assert row["source_revision"] == "5d04d3b4b91dceb4c90e8592ce3235c1965c9db2"
        assert json.loads(row["current_pr_refs"]) == ["refs/pr/21"]
        assert json.loads(row["response_reasoning_efforts"]) == ["low"]
        assert row["track_name"] == "api-cpu-agents1-no-preload"
        assert row["inference_tier"] == "default"
        if row["row_type"] != "evaluation":
            assert row["run_id"] == "svc_62_9b9e92" and row["n_trajectories"] == "1"
            assert float(row["model_responses_observed_total"]) == 18
            assert float(row["cost_usd_observed_total"]) == pytest.approx(0.476522)
            assert row["score_mean_pct"] == row["avg_steps_per_task"] == ""
            continue
        model, score, seconds, steps, cost, responses = expected[row["run_id"]]
        record = records[row["run_id"]]
        assert record["model"] == model and record["effort"] == "low"
        assert record["performance"] == pytest.approx(score / 100)
        assert record["time_per_task_sec"] == pytest.approx(seconds)
        assert record["steps_per_task"] == steps
        assert record["cost_usd"] == pytest.approx(cost)
        assert record["model_responses_per_task"] == responses / 50
        assert record["cost_kind"] == "source_estimate"
        for field in ("score_mean_pct", "time_per_task_sec", "avg_steps_per_task", "cost_per_task_usd",
                      "input_tokens_per_task", "cached_input_tokens_per_task", "cache_write_input_tokens_per_task",
                      "generated_tokens_per_task", "thinking_tokens_per_trajectory", "model_responses_per_task"):
            assert row[field + "_n"] == "50"
        assert json.loads(row["run_terminal_events"])[-1] == "run_done"
        assert json.loads(row["quality_flags"]) == {}


def test_luna_codex_append_preserves_history_and_all_four_efforts(catalog_site):
    output, catalog = catalog_site
    source = output / "trajectory-metrics.csv"
    assert hashlib.sha256(source.read_bytes()[:976657]).hexdigest() == "5da15fb7ce06557060cd155a02d9ba9fe15011d38eb4790dfa5b2b4cc94d8c23"
    with source.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    added = rows[127:131]
    assert len(added) == 4 and {r["row_type"] for r in added} == {"evaluation"}
    expected = {
        "svc_153_795ea7": ("low", 75.61904360085809, 144.77467869182, 7.22, 0.025388204, 36),
        "svc_154_323b97": ("medium", 67.61904360085809, 188.84819598838, 9.5, 0.0353048576, 32),
        "svc_155_7fbf62": ("high", 79.61904360085809, 324.83747465096, 15.58, 0.075945944, 38),
        "svc_156_2bc119": ("xhigh", 77.61904360085809, 297.23008968142, 13.88, 0.0631331888, 37),
    }
    records = {r["run_id"]: r for r in catalog["datasets"]["osworld-energy50-representative"]["records"]}
    assert records["svc_63_ccb407"]["series"] == "GPT-5.6 Luna · Direct API"
    assert {r["series"] for r in records.values() if r["model"] == "GPT-5.6 Luna"} == {
        "GPT-5.6 Luna · Direct API", "GPT-5.6 Luna · Codex",
    }
    for row in added:
        effort, score, seconds, steps, cost, passes = expected[row["run_id"]]
        record = records[row["run_id"]]
        assert row["template_name"] == "codex_cli" and row["family"] == "codex"
        assert row["reasoning_effort"] == effort and record["effort"] == effort
        assert record["series"] == "GPT-5.6 Luna · Codex"
        assert row["source_revision"] == "ac8db5465e7efaef62b38376760a9e70c459f99f"
        assert json.loads(row["current_pr_refs"]) == ["refs/pr/22"]
        assert row["track_name"] == "api-cpu-agents1-no-preload"
        assert row["eval_algorithm"] == "shared-agent-no-preload@1"
        assert record["performance"] == pytest.approx(score / 100)
        assert record["time_per_task_sec"] == pytest.approx(seconds)
        assert record["steps_per_task"] == steps and record["cost_usd"] == pytest.approx(cost)
        assert int(row["perfect_pass_count"]) == int(row["recorded_boolean_pass_count"]) == passes
        assert "not_subscription_bill" in record["cost_basis"]
        assert record["model_responses_per_task"] is record["average_output_tokens"] is None
        assert row["avg_tool_calls_per_step"] == row["model_tool_calls_per_task"] == ""
        assert row["cache_write_input_tokens_per_task"] == "0.0"
        assert row["extra_retained_attempts"] == "0"
        assert row["metadata_only_infrastructure_attempts"] == "0"
        assert json.loads(row["run_terminal_events"]) == ["run_done"]
        assert json.loads(row["quality_flags"]) == {
            "codex_model_response_count_and_full_tool_calls_unavailable": 50,
            "Luna_cost_excludes_per_request_long_context_fast_mode_and_tool_adjustments": 50,
        }
        for field in ("score_mean_pct", "time_per_task_sec", "avg_steps_per_task", "cost_per_task_usd",
                      "input_tokens_per_task", "cached_input_tokens_per_task", "cache_write_input_tokens_per_task",
                      "generated_tokens_per_task", "thinking_tokens_per_trajectory"):
            assert row[field + "_n"] == "50"
        reasons = json.loads(row["termination_reason_counts"])
        assert reasons == ({"done": 49, "agent_error": 1} if effort == "medium" else {"done": 50})
        if effort == "medium":
            assert "agent_error" in record["notes"] and "zero score" in record["notes"]


def test_kimi_completed_snapshots_and_yutori_preserve_all_previous_csv_bytes(catalog_site):
    output, catalog = catalog_site
    source = output / "trajectory-metrics.csv"
    assert hashlib.sha256(source.read_bytes()[:1011510]).hexdigest() == "f4d68f44b4c59705c4f413bd6a59b412990a06a3ec3bcaf8aa294799a15a557e"
    with source.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    added = rows[131:141]
    assert Counter(r["row_type"] for r in added) == {"evaluation": 6, "retained_extra_attempts": 4}
    records = {r["run_id"]: r for d in catalog["datasets"].values() for r in d["records"]}
    expected = {
        "svc_145_4091f6": ("high", 52, 22.59537286565601, 3733.9232542997497, 4.517302015384615),
        "svc_147_d5291e": ("max", 52, 28.506236962992634, 4825.08071171677, 5.624738163461539),
        "svc_10_cd0ed2": ("none", 50, 75.61904360085809, 298.49816499184, 0.081063778),
        "svc_11_0dddb1": ("low", 50, 77.61904360085809, 331.04671879148003, 0.156928266),
        "svc_12_026ed7": ("medium", 50, 67.61904360085809, 265.43294287585996, 0.109996612),
        "svc_13_01885e": ("xhigh", 50, 79.61904360085809, 224.9677141393, 0.103612176),
    }
    for row in added:
        if row["row_type"] != "evaluation":
            continue
        effort, count, score, seconds, cost = expected[row["run_id"]]
        record = records[row["run_id"]]
        assert record["effort"] == effort and record["task_count"] == count
        assert record["performance"] == pytest.approx(score / 100)
        assert record["time_per_task_sec"] == pytest.approx(seconds)
        assert record["cost_usd"] == pytest.approx(cost)
        assert row["billing_error_trajectories"] == "0"
        assert json.loads(row["run_terminal_events"])[-1] == "run_done"
        assert row["score_mean_pct_n"] == row["time_per_task_sec_n"] == row["cost_per_task_usd_n"] == str(count)
        if row["family"] == "kimi":
            assert record["cost_kind"] == "recorded"
            assert row["source_revision"] == "00d7d65cb6459aaf02767e8ab6b3ad419f2c66b1"
            assert json.loads(row["current_pr_refs"]) == ["refs/pr/24"]
            assert row["perfect_pass_count"] == "4"
            history = [r for r in rows[:131] if r["run_id"] == row["run_id"] and r["row_type"] == "evaluation"]
            assert len(history) == 1 and int(history[0]["billing_error_trajectories"]) > 0
            assert history[0]["run_plan_hash"] == row["run_plan_hash"]
            assert history[0]["selected_task_seed_set_sha256"] == row["selected_task_seed_set_sha256"]
            assert history[0]["archive_sha256"] != row["archive_sha256"]
        else:
            assert row["family"] == "yutori" and record["model"] == "Yutori n2"
            assert row["source_revision"] == "61a43287ed7d5eb5aa625e0daa11157dbb5004e1"
            assert row["track_name"] == "api-cpu-agents1-no-preload"
            assert row["thinking_tokens_per_trajectory"] == ""
            assert row["generated_tokens_per_task_n"] == row["cached_input_tokens_per_task_n"] == "50"
            assert record["cost_label"] == "API estimate · logged usage"
            assert record["cost_kind"] == "source_estimate"
            computed = ((float(row["input_tokens_per_task"]) - float(row["cached_input_tokens_per_task"])) * .50
                        + float(row["cached_input_tokens_per_task"]) * .05 + float(row["generated_tokens_per_task"]) * 4) / 1e6
            assert cost == pytest.approx(computed)
    max_row = next(r for r in added if r["run_id"] == "svc_147_d5291e" and r["row_type"] == "evaluation")
    assert json.loads(max_row["quality_flags"])["thinking_exceeds_generated"] == 1
    assert max_row["nonthinking_generated_tokens_per_task"] == ""
    assert max_row["nonthinking_generated_tokens_per_task_n"] == "51"


def test_mypcbench_astra_append_preserves_history_and_separates_dataset(catalog_site):
    output, catalog = catalog_site
    source = output / "trajectory-metrics.csv"
    assert hashlib.sha256(source.read_bytes()[:1072673]).hexdigest() == "f8b6aa3b3a1c1171dbefdda61abc3453cd9446a9c2a33659c714972d0fef6c35"
    with source.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    added = rows[141:145]
    assert len(added) == 4 and all(r["row_type"] == "evaluation" for r in added)
    dataset = catalog["datasets"]["mypcbench-energy38"]
    assert dataset["label"] == "MyPCBench Energy38"
    assert dataset["task_counts"] == [38]
    assert not dataset["excluded_evaluations"] and dataset["supporting_rows"] == 0
    records = {r["run_id"]: r for r in dataset["records"]}
    expected = {
        "svc_93_cbb0ad": ("low", 89.86842105263158, 514.2687531146843, 27, 1387, 3554, 4.574090263157895, 2),
        "svc_94_2d132c": ("medium", 88.34210526315789, 495.36015863834217, 25, 1395, 3701, 4.332102315789474, 3),
        "svc_95_5ae456": ("high", 88.63157894736842, 568.3168793826579, 26, 1534, 4261, 4.812435210526315, 1),
        "svc_96_fee517": ("xhigh", 93.55263157894737, 619.1620519224474, 29, 1601, 4696, 4.809898789473684, 0),
    }
    assert set(records) == set(expected)
    for row in added:
        effort, score, seconds, perfect, steps, actions, cost, no_response = expected[row["run_id"]]
        record = records[row["run_id"]]
        assert record["model"] == "GPT-6 Astra" and record["variant"] == "Codex"
        assert record["effort"] == effort and record["task_count"] == 38
        assert record["performance"] == pytest.approx(score / 100)
        assert record["time_per_task_sec"] == pytest.approx(seconds)
        assert record["steps_per_task"] == pytest.approx(steps / 38)
        assert record["tool_calls_per_task"] == pytest.approx(actions / 38)
        assert int(row["perfect_pass_count"]) == int(row["recorded_boolean_pass_count"]) == perfect
        assert row["source_revision"] == "447ff4cd77230ee06ee5b0e864873c43ceb0138c"
        assert json.loads(row["current_pr_refs"]) == ["refs/pr/25"]
        assert row["benchmark_version"] == "0.2"
        assert row["track_name"] == "api-cpu-agents1-no-preload"
        assert row["eval_algorithm"] == "shared-agent-no-preload@1"
        assert row["parallel_evaluations"] == "8" and row["agents_per_evaluation"] == "1"
        assert row["run_plan_hash"] == "d47ef5c19bafd271ad373fd4f45ae6710a4e5d420d7273305f2be17835c0c2f5"
        assert row["billing_error_trajectories"] == "0"
        assert json.loads(row["termination_reason_counts"]) == {"done": 38}
        assert json.loads(row["run_terminal_events"])[-1] == "run_done"
        assert row["extra_retained_attempts"] == "0"
        for metric in ("score_mean_pct", "time_per_task_sec", "avg_steps_per_task", "env_action_items_per_task",
                       "input_tokens_per_task", "cached_input_tokens_per_task", "generated_tokens_per_task",
                       "thinking_tokens_per_trajectory", "cost_per_task_usd"):
            assert row[metric + "_n"] == "38"
        # A completed CLI session is not one model response. Keep its total
        # tokens in the CSV without inventing tokens/response for the graph.
        assert record["model_responses_per_task"] is None and record["average_output_tokens"] is None
        assert row["model_tool_calls_per_task"] == row["model_responses_per_task"] == ""
        assert record["cost_kind"] == "source_estimate"
        assert record["cost_label"] == "API estimate · logged usage"
        assert record["cost_usd"] == pytest.approx(cost)
        inp, cached, write, out = [float(row[k]) for k in (
            "input_tokens_per_task", "cached_input_tokens_per_task", "cache_write_input_tokens_per_task", "generated_tokens_per_task")]
        assert cost == pytest.approx(((inp - cached - write) * 10 + cached + write * 12.5 + out * 50) / 1e6)
        assert "not Codex-plan spending" in record["notes"]
        assert json.loads(row["quality_flags"]).get("judge_did_not_receive_final_response_text", 0) == no_response
    assert "run_failed" in records["svc_93_cbb0ad"]["run_terminal_events"]
    assert "32 completed records retained" in records["svc_93_cbb0ad"]["notes"]
    assert "original score of 43" in records["svc_94_2d132c"]["notes"]
    for name, other in catalog["datasets"].items():
        if name != "mypcbench-energy38":
            assert not set(expected) & {r["run_id"] for r in other["records"]}


def test_superseded_snapshot_requires_pinned_matching_contract(catalog_site, tmp_path):
    sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))
    from results_catalog import load_catalog
    decisions = json.loads((REPOSITORY_ROOT / "data/results-curation.json").read_text())
    decisions["runs"]["svc_147_d5291e"]["supersedes_archive_sha256"] = ["wrong-archive"]
    path = tmp_path / "invalid-curation.json"
    path.write_text(json.dumps(decisions))
    with pytest.raises(ValueError, match="invalid superseded snapshot identity"):
        load_catalog(REPOSITORY_ROOT / "data/all-hf-model-trajectory-metrics-2026-09-13.csv",
                     REPOSITORY_ROOT / "data/model-metadata.json", path)


def test_reviewed_subsets_preserve_parent_results_and_exact_dataset_membership(catalog_site):
    output, catalog = catalog_site
    with (output / "trajectory-metrics.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    subsets = [r for r in rows if r["row_type"] == "published_subset"]
    assert len(subsets) == 4
    for subset in subsets:
        dataset = catalog["datasets"][subset["split_dset_name"]]
        record, = [r for r in dataset["records"] if r["run_id"] == subset["run_id"]]
        parent, = [r for r in rows if r["row_type"] == "evaluation" and r["run_id"] == subset["run_id"]]
        assert set(json.loads(subset["task_ids"])) < set(json.loads(parent["task_ids"]))
        assert subset["expected_contract_tasks"] == parent["expected_contract_tasks"]
        assert record["task_count"] == len(json.loads(subset["task_ids"]))
        assert record["row_type"] == "published_subset"
        assert record["performance"] == float(subset["score_mean_pct"]) / 100
        assert any(r["run_id"] == parent["run_id"] for r in catalog["datasets"][parent["split_dset_name"]]["records"])
    energy = catalog["datasets"]["osworld-energy50-representative"]["records"]
    kimi, = [r for r in energy if r["run_id"] == "svc_56_9e002a"]
    assert kimi["variant"] == "Single tool call" and kimi["effort"] == "max"
    assert kimi["steps_per_task"] == 12.18 and kimi["tool_calls_per_task"] == 61.24
    assert kimi["time_per_task_sec"] == pytest.approx(606.2705898115)


@pytest.mark.parametrize("field,value", [
    ("archive_sha256", "wrong"), ("task_seed_sha256", "wrong"), ("task_count", 49),
])
def test_reviewed_subsets_require_pinned_identity_and_complete_coverage(field, value):
    sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))
    from results_catalog import reviewed_subsets
    with (REPOSITORY_ROOT / "data/all-hf-model-trajectory-metrics-2026-09-13.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    decisions = json.loads((REPOSITORY_ROOT / "data/results-curation.json").read_text())["subsets"]
    decisions[0][field] = value
    with pytest.raises(ValueError, match="invalid reviewed subset"):
        reviewed_subsets(rows, decisions)


def test_single_action_result_has_recomputable_public_task_evidence(catalog_site):
    output, catalog = catalog_site
    source = output / "trajectory-metrics.csv"
    assert hashlib.sha256(source.read_bytes()[:1099256]).hexdigest() == "1e93b3d7166d8a4037a86c5ee52c8065116e48434583aebc8267a51912b06b0d"
    with source.open(newline="") as handle:
        row, = [r for r in csv.DictReader(handle) if r["run_id"] == "svc_157_c2dbaf"]
    record, = [r for r in catalog["datasets"]["osworld-energy50-representative"]["records"]
               if r["run_id"] == row["run_id"]]
    evidence_path = output / record["source_archive_url"]
    assert evidence_path.read_bytes() == (REPOSITORY_ROOT / "data" / record["source_archive_url"]).read_bytes()
    evidence = json.loads(evidence_path.read_text())
    assert evidence["source_result_sha256"] == "fd04eb5b16eab91b57991bde1f31908b38fbde73dc875d26754764757ece0092"
    assert evidence["run_plan_hash"] == row["run_plan_hash"]
    tasks = evidence["tasks"]
    assert len(tasks) == len({t["task_id"] for t in tasks}) == 50
    for metric, key in {
        "score_mean_pct": "score", "time_per_task_sec": "task_time_sec", "env_time_per_task_sec": "env_time_sec",
        "agent_time_per_task_sec": "agent_time_sec", "avg_steps_per_task": "num_steps",
        "env_action_items_per_task": "environment_action_items", "generated_tokens_per_task": "generated_tokens",
        "thinking_tokens_per_trajectory": "thinking_tokens", "cost_per_task_usd": "cost_usd",
    }.items():
        assert float(row[metric]) == pytest.approx(sum(t[key] for t in tasks) / 50)
    assert all(t["num_steps"] == t["environment_action_items"] for t in tasks)
    assert sum(t["num_steps"] for t in tasks) == 825
    assert sum(t["generated_tokens"] for t in tasks) == 127948
    assert record["variant"] == "Single action"
    assert record["cost_kind"] == "source_estimate"
    assert record["model_responses_per_task"] is None and record["average_output_tokens"] is None
    assert row["archive_sha256"] == row["source_hf_repo"] == ""


def test_catalog_build_is_deterministic(catalog_site, tmp_path):
    output, _ = catalog_site
    second = tmp_path / "second-build"
    subprocess.run(
        [sys.executable, str(REPOSITORY_ROOT / "scripts/build_results_dashboard.py"),
         "--output", str(second)],
        cwd=REPOSITORY_ROOT, check=True,
    )
    assert sorted(p.name for p in output.iterdir()) == sorted(p.name for p in second.iterdir())
    for path in output.iterdir():
        if path.is_file():
            assert path.read_bytes() == (second / path.name).read_bytes()

