#!/usr/bin/env python3
"""Build the public research site from the existing reviewed results catalog.

This is an offline publication build. It never imports the evaluator API,
accesses a database, provisions environments, or starts evaluations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, select_autoescape

import build_results_dashboard as renderer
from build_results_dashboard import build_site, REPOSITORY

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data/all-hf-model-trajectory-metrics-2026-09-13.csv"
NAV = [("home", "Overview", "index.html"), ("paper", "Research", "paper.html"),
       ("results", "Leaderboard", "results.html"), ("docs", "Documentation", "docs.html"),
       ("run", "Run", "submit")]


def configuration(path: Path) -> dict:
    config = json.loads(path.read_text())
    for key in ("site_url", "paper_url"):
        value = config.get(key, "").rstrip("/")
        parsed = urlsplit(value)
        if value and (parsed.scheme != "https" or not parsed.hostname
                      or parsed.username or parsed.password or parsed.fragment
                      or (key != "paper_url" and (parsed.query or parsed.path))):
            raise ValueError(f"{key} must be a public HTTPS URL without credentials"
                             + ("" if key == "paper_url" else " or a path"))
        config[key] = value
    if not config["site_url"]:
        raise ValueError("site_url is required")
    return config


def clock(seconds: float) -> str:
    minutes, rest = divmod(seconds, 60)
    return f"{int(minutes)}:{rest:04.1f}"


def provider(model: str, providers: list[dict]) -> str:
    matches = [p["slug"] for p in providers if model.startswith(p["prefix"])]
    if len(matches) != 1:
        raise ValueError(f"model must match exactly one provider prefix: {model}")
    return matches[0]


def logo_sprite(providers: list[dict], logos: Path) -> str:
    """One hidden SVG sprite: vendored single-path logos, or a letter mark."""
    symbols = []
    for p in providers:
        if p.get("logo"):
            svg = (logos / p["logo"]).read_text()
            paths = re.findall(r'<path d="([^"]+)"', svg)
            if len(paths) != 1 or "<script" in svg:
                raise ValueError(f"logo must be a single-path SVG: {p['logo']}")
            view_box = re.search(r'viewBox="([^"]+)"', svg).group(1)
            rule = ' fill-rule="evenodd"' if 'fill-rule="evenodd"' in svg else ""
            body = f'<path d="{paths[0]}"{rule}/>'
        else:
            view_box = "0 0 24 24"
            body = ('<circle cx="12" cy="12" r="10.5" fill="none" stroke="currentColor" '
                    'stroke-width="1.8"/><text x="12" y="16.6" text-anchor="middle" '
                    f'font-size="13" font-weight="700">{p["mark"]}</text>')
        symbols.append(f'<symbol id="logo-{p["slug"]}" viewBox="{view_box}">'
                       f'<title>{p["name"]}</title>{body}</symbol>')
    return ('<svg class="logo-sprite" aria-hidden="true" width="0" height="0">'
            + "".join(symbols) + "</svg>")


def race_data(race: dict, catalog: dict, providers: list[dict]) -> dict:
    """Resolve the homepage race lineup to published records; fail if one is missing."""
    dataset = catalog["datasets"][race["subset"]]
    runners = []
    for want in race["runners"]:
        matches = [r for r in dataset["records"]
                   if all((r[k] or "") == want[k] for k in ("model", "effort", "variant"))]
        if len(matches) != 1:
            raise ValueError(f"race runner must match one published record: {want}")
        r = matches[0]
        runners.append({"model": r["model"], "provider": provider(r["model"], providers),
                        "effort": r["effort"], "variant": r["variant"] or "",
                        "time": r["time_per_task_sec"], "clock": clock(r["time_per_task_sec"]),
                        "score": r["performance"], "steps": r["steps_per_task"]})
    fastest = min(r["time"] for r in runners)
    for r in runners:
        r["place"] = 1 + sum(o["time"] < r["time"] for o in runners)
        r["fastest"] = r["time"] == fastest
    return {"label": dataset["paper_subset"]["label"],
            "tasks": dataset["paper_subset"]["selected_tasks"],
            "speed": race["speed"], "href": dataset["href"], "runners": runners}


def build_public_site(output: Path, config_path: Path, paper: Path | None = None) -> Path:
    config = configuration(config_path)
    # "Code" links on every page, including the results renderer, use this repository.
    repository = config.get("repository", REPOSITORY)
    renderer.REPOSITORY = repository
    assets = ROOT / "website/assets"
    version = hashlib.sha256(b"".join(p.read_bytes() for p in sorted(assets.rglob("*"))
                                     if p.is_file())).hexdigest()[:12]
    context = {"site": config, "nav": NAV, "repository": repository,
               "asset_version": version,
               "public_layout": "public-results-layout.html", "page": "results",
               "logo_sprite": logo_sprite(config["providers"], assets / "logos"),
               "provider_prefixes": [{k: p[k] for k in ("prefix", "slug", "name")}
                                     for p in config["providers"]]}
    build_site(
        DEFAULT_INPUT, output, dataset_scope=config["paper_subsets"],
        default_variants=tuple(config.get("default_variants", ())),
        ablation_variants=tuple(config.get("ablation_variants", ())),
        public_context={k: v for k, v in context.items()
                        if k != "repository"},
    )
    # The results entry point uses the first published subset.
    shutil.copy2(output / "index.html", output / "results.html")
    catalog = json.loads((output / "results-catalog.json").read_text())
    datasets = list(catalog["datasets"].values())
    shutil.copytree(assets, output / "assets", dirs_exist_ok=True)
    # Existing run/account pages use this script through the same-origin proxy.
    shutil.copy2(ROOT / "results/static/app.js", output / "static/app.js")
    if paper:
        if not paper.is_file() or not paper.read_bytes().startswith(b"%PDF-"):
            raise ValueError("--paper must reference a real PDF")
        shutil.copy2(paper, output / "paper.pdf")
        config["paper_url"] = "paper.pdf"
    elif (output / "paper.pdf").exists():
        # Do not accidentally republish a draft left from an earlier build.
        (output / "paper.pdf").unlink()
    env = Environment(loader=FileSystemLoader(ROOT / "website/templates"),
                      autoescape=select_autoescape(("html", "xml")))
    overview_data = [{"name": d["name"], "href": d["href"], **d["paper_subset"],
                      "records": [{key: r[key] for key in (
                          "run_id", "model", "effort", "variant", "performance",
                          "time_per_task_sec", "cost_usd", "cost_label")}
                                  | {"provider": provider(r["model"], config["providers"])}
                                  for r in d["records"]]} for d in datasets]
    figures = {f["name"]: f for f in json.loads(
        (assets / "figures/sources.json").read_text())["figures"]}
    context.update(catalog=catalog, datasets=datasets, overview_data=overview_data, figures=figures,
                   race=race_data(config["race"], catalog, config["providers"]),
                   providers={p["slug"]: p["name"] for p in config["providers"]})
    for page, _, filename in NAV:
        if page == "results":
            continue
        html = env.get_template(f"{page}.html").render(**{**context, "page": page})
        destination = output / ("submit/index.html" if page == "run" else filename)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(html)
    (output / "404.html").write_text(env.get_template("404.html").render(**{**context, "page": "404"}))
    (output / "robots.txt").write_text(f'User-agent: *\nAllow: /\nSitemap: {config["site_url"]}/sitemap.xml\n')
    pages = [filename for _, _, filename in NAV] + [d["href"] for d in datasets]
    (output / "sitemap.xml").write_text(env.get_template("sitemap.xml").render(site=config, pages=pages))
    (output / "_headers").write_text(
        "/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n"
        "  X-Frame-Options: DENY\n  Permissions-Policy: camera=(), microphone=(), geolocation=()\n"
    )
    print(f"Built {output / 'index.html'} ({catalog['included_rows']} reviewed results)")
    return output / "index.html"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/public-site")
    parser.add_argument("--config", type=Path, default=ROOT / "website/config.json")
    parser.add_argument("--paper", type=Path, help="Release-approved PDF to include in this build")
    args = parser.parse_args()
    build_public_site(args.output.resolve(), args.config.resolve(), args.paper)
