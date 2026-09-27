# Model developer logos

Each file is a single-path SVG used to identify a model's developer in the
homepage chart and race. The logos remain trademarks of their owners; their use
here identifies developers and does not imply endorsement. Retrieved September
26, 2026.

| File | Source | License |
| --- | --- | --- |
| `anthropic.svg`, `googlegemini.svg`, `meta.svg`, `minimax.svg`, `moonshotai.svg` | [Simple Icons](https://simpleicons.org) 16.32.0, `https://cdn.jsdelivr.net/npm/simple-icons@16.32.0/icons/<slug>.svg` | CC0 1.0 |
| `openai.svg`, `zhipu.svg` | [LobeHub Icons](https://github.com/lobehub/lobe-icons), `https://cdn.jsdelivr.net/npm/@lobehub/icons-static-svg@1.95.1/icons/<slug>.svg` | MIT |
| `yutori.svg` | The "Y" mark (first path) from Yutori's own `https://yutori.com/logo-full.svg`, recentered in a square viewBox; wordmark removed | Yutori's trademark |

`website/config.json` (`providers`) maps model-name prefixes to these files.
The build reads each file's viewBox and fill rule and rejects files with more
than one path or any script. A provider without a file can use a letter
`mark` instead.
