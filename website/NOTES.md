# Website notes

The public site publishes the repository's reviewed results catalog and an
original article based on manuscript revision `128fef0`. The homepage introduces the
software and the paper's measured results, with a runnable Modal example below.
The research article uses the manuscript's original figures. It uses an Xbox 360–inspired green palette and self-hosted Barlow typography. It does not recreate a console dashboard or use Microsoft logos.
Modal sponsorship appears in the header and footer, with independent execution
instructions in the developer guide.
The Modal logo in `assets/modal-logo.png` comes from the public modal.com homepage
(`/_app/immutable/assets/logo.lottie.CgmMXf1s.png`, retrieved September 26, 2026).

## Build and preview

See the repository [README](../README.md) for preview, test, and deploy commands.

## Research figures and interactions

`assets/figures/` contains three original manuscript figure PDFs and SVG renders:
the OSWorld/OSWorld 2.0 comparison, the Gemini reasoning-effort study, and the
latency study. `sources.json` records the manuscript revision, source filenames,
and SHA-256 checksums. These figures use the paper's plotting population; the
interactive explorer retains its separately curated, unchanged results catalog.

To update a figure, obtain the approved export from the manuscript and render it
with `pdftocairo -svg SOURCE.pdf OUTPUT.svg`. Update the manifest checksums and
review the rendered figure and caption. Builds consume the checked-in assets and
do not require access to the manuscript repository.

Figures support an accessible enlargement dialog, zoom/pan, Escape dismissal,
and direct PDF links. Page and section entrance motion preserves text contrast
and respects reduced-motion preferences. Results open to a responsive plot, with
optional filters, a dataset selector, table sorting, and a 3D view. These public
layout changes do not alter the evaluator dashboard's default view.

## Cloudflare publication

`wrangler.jsonc` deploys a Worker with static assets at `cuaspeedrun.com` and
`www.cuaspeedrun.com`. The Worker serves `/submit` and proxies evaluation routes
only when an operator explicitly sets `EVALUATOR_ORIGIN`. With no origin,
`/site-api/status` reports `configured: false`, the submission form stays hidden and disabled,
a command-line guide is shown, and evaluation API routes return 503. No credentials are collected.

```sh
npx --yes wrangler@4.141.0 login --scopes \
  account:read user:read workers:write workers_scripts:write \
  workers_routes:write zone:read
npx --yes wrangler@4.141.0 deploy
```

Publication is independent of GitHub. Repository rules still prohibit pushing a
branch or creating a remote PR without explicit permission.

## Connecting a hosted evaluator

The Worker does not run Python or own the database, artifact store, or executor.
Choose an existing persistent installation or provision one using the repository's
operator instructions. Its deployment location is an operator choice. It must
have the API and worker from this revision, persistent database/artifact storage,
installed benchmark assets, and its actual runnable catalog.

1. Serve the evaluator at an HTTPS origin and set that origin as the Worker's
   `EVALUATOR_ORIGIN` variable. The origin must not be the public Worker itself.
   No credentials may appear in the URL. The browser only communicates with the
   public site; the Worker forwards the same-origin API requests to this origin.
2. On the evaluator, set `CS_PUBLIC_ORIGIN=https://cuaspeedrun.com`, a strong
   `CS_SECRET_KEY` of at least 32 characters, and `CS_GITHUB_CLIENT_ID` and
   `CS_GITHUB_CLIENT_SECRET`. Disable `CS_DEV_LOGIN`. The API refuses a public
   configuration with the default session secret or developer login enabled.
   Register the OAuth callback as
   `https://cuaspeedrun.com/auth/github/callback`.
3. Configure invitations/quotas for the intended public audience. Confirm that
   the owning worker is running before opening submissions. Keep the same
   `CS_SECRET_KEY` for the API and worker so stored secrets can be decrypted.
4. Verify GitHub sign-in, credential connection, queued-run status, cancellation,
   export, and explicit publication on that installation. A real paid evaluation
   requires separate authorization under this repository's execution rules.

When enabling the service, redirect the `www` host to the canonical site (the
Worker does this) so OAuth and session cookies stay on one hostname. The proxy
forwards only known public application routes; developer login is never exposed.
Writes with a foreign Origin are refused. API responses are never cached.

Users choose the benchmark and maintainer track, upload `agent.py` and optionally
`init.py` or choose a compatible starter, and explicitly agree to their own Modal
and model-provider charges before launching. Individual files are packaged into
the established two-file ZIP contract without importing or executing them. The
omitted initializer is a documented no-op. ZIP/template clients remain supported.

Modal credentials use the existing encrypted account storage. Model variables are
attached to the evaluation through the existing encrypted secret store. Neither is
saved in browser storage, placed in a URL, nor embedded in the generated site.
Run inspection, cancellation, export and card publication use the existing service
pages and permission checks. A card link is unlisted and shareable, not private.

## Current release limits

An evaluator origin and GitHub OAuth configuration have not yet been supplied.
The website's unavailable-service state is verified; a real hosted submission has
not been run. The documented CLI examples were checked against source but not
executed as part of the website work. Public results contain 85 reviewed
configurations across the paper's four task subsets. The full archive exporter
still contains 96 configurations across seven datasets; its source CSV is
preserved in the public downloads. Neither view claims live synchronization
with the internal dashboard.
Modal blog collaboration is an editorial follow-up; this site does not send or
publish a partner-authored announcement.

## Interactive overview and publication scope

`config.json` declares the paper task subsets, their display names, and the
selected/eligible task counts from manuscript revision `128fef0`,
`sections/method.tex`. The public build validates the selected counts against
the reviewed catalog, scopes navigation and downloads, and removes generated
pages for datasets outside this scope. The shared archive exporter is unchanged
when no publication scope is supplied.

The overview on the homepage and research page derives its points directly from
those published records. Task squares encode counts, not task identities.
Benchmark buttons, time/cost controls, and the agent selector update the figure;
related reasoning settings are highlighted. Unknown costs stay out of cost plots.
Keyboard users can select an agent from the native select or use arrow keys on a
focused point. Motion honors reduced-motion preferences. Original paper figures
remain in the research article, with a static figure fallback when JavaScript is
disabled. Configuration coverage in the explorer is curated separately from the
paper's figure population.

The homepage race (`templates/race.html`, `assets/race.js`) replays the mean task
time of the configurations listed under `race` in `config.json`. Each entry must
match exactly one published record by model, effort, and variant, or the build
fails. Change the lineup there, not in the template.

The Barlow fonts are self-hosted under `assets/fonts/`, with their upstream source
and SIL Open Font License included. No third-party font requests are needed.

## September 28, 2026: author email links

The owner requested public email links for Pranjal, Lawrence, and Jing Yu and
then explicitly requested deployment of this change in the standalone website.
Use `pranjala@cmu.edu`, `ljang@cmu.edu`, and `jykoh@cmu.edu` (the supplied domain
is `cmu.edu`, rather than `cs.cmu.edu` in an earlier manuscript draft). The shared
author component displays these links on the homepage and research article.

Deployed this change from commit `c03cc16` with Wrangler 4.141.0 to the existing
`cuaspeedrun` Worker on `cuaspeedrun.com` and `www.cuaspeedrun.com`. Cloudflare
version: `b4cc43b7-1207-46c1-98e1-71ab95de5fc4`. All 30 website tests passed;
browser verification confirmed the three visible `mailto:` links on the live
homepage and research page. Source is on local branch `codex/author-email-links`;
no Git push or remote PR was performed.
