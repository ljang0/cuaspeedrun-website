# cuaspeedrun.com

Source for [cuaspeedrun.com](https://cuaspeedrun.com), the public site for
*CUA-Speedrun: Standardized Benchmarking of the Speed of Computer-Use Agents*.
It is a static site built with Python and Jinja, served by a Cloudflare Worker.
The evaluator code lives in the separate code repository; this repository only
needs the published results data.

## Preview

Requires Python 3.10+ and Node.js 22+.

```sh
pip install -r requirements.txt
python3 scripts/build_public_site.py
npx --yes wrangler@4.141.0 dev --port 8787 --local
```

Open <http://localhost:8787>. Rebuild after every edit; the preview serves
`output/public-site/`. Run the checks with `python3 -m pytest tests`.

## Where to edit

| What | File |
| --- | --- |
| Documentation page | `website/templates/docs.html` |
| Homepage, research article, run page | `website/templates/home.html`, `paper.html`, `run.html` |
| Leaderboard page layout and table | `results/templates/leaderboard.html` |
| Leaderboard record board and reading note | `website/templates/results-records.html`, `results-note.html` |
| Leaderboard behavior (sorting, plots, 3D) | `results/static/leaderboard.js`; public-only extras in `website/assets/leaderboard-plus.js` |
| Colors, fonts, layout, animation | `website/assets/site.css` |
| Authors, code repository link, task sets, race lineup, developer logos | `website/config.json` |
| Results data | `data/all-hf-model-trajectory-metrics-2026-09-13.csv` with `data/results-curation.json`, `results-pricing.json`, `model-metadata.json` |
| Paper figures and provenance | `website/assets/figures/` |

`website/config.json` sets `repository`, the GitHub repository behind every
"Code" link. Point it at the public code repository once it exists.

The build validates the data: every published model needs a developer entry
in `providers`, every race runner must match exactly one result, and the task
counts must match `paper_subsets`. `website/NOTES.md` has the longer design and
data notes, including the hosted-evaluation proxy in `website/worker.js`.

## Deploy

The site is a Cloudflare Worker named `cuaspeedrun` with custom domains
`cuaspeedrun.com` and `www.cuaspeedrun.com` (see `wrangler.jsonc`).

Production is deployed from `main`. Make website changes on a branch, open a pull
request, and merge it into `main`. Every push to `main` runs the **Deploy** workflow
(`.github/workflows/deploy.yml`), which tests and builds the site before deploying
to Cloudflare. Verify that the workflow's deploy step succeeds after merging.

This website repository is public. Its standard GitHub-hosted Actions runners
are free; GitHub still applies workflow runtime and concurrency limits.
Do not publish unmerged local changes directly with Wrangler: a later deployment
from `main` would replace them.

To redeploy the current `main` without a code change, choose **Actions → Deploy →
Run workflow** and select `main`, or run:

```sh
gh workflow run deploy.yml --ref main
```

The workflow needs `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` repository
secrets from the account that owns the domain (the token uses the "Edit Cloudflare
Workers" template). Both are configured as of September 29, 2026. A run without
them skips deployment with a notice; a green run alone does not prove publication,
so check that **Deploy to Cloudflare** ran successfully.
