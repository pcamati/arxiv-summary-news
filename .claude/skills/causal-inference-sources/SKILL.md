---
name: causal-inference-sources
description: Where to find causal inference papers on arXiv — which categories to search, which search phrases to use, and which "causal" hits are false positives. Use when the user asks about causal inference, treatment effects, causal discovery, or related topics, or wants to fetch, filter, or summarize causal inference preprints.
argument-hint: [subtopic, e.g. "causal discovery" or "difference-in-differences"]
---

# Causal inference on arXiv

arXiv has no causal inference category, and no category description mentions "causal"
(see `src/arxiv_summary_news/arxiv_taxonomy.json`). The topic is spread across groups, so
pick categories by subtopic, search with phrases, and screen the results.

The user's request: $ARGUMENTS

## Where to look

Core — most causal inference papers have one of these as primary category:

| Category | What lands there |
|---|---|
| `stat.ME` (Methodology) | The main home: estimators, identification, sensitivity analysis, IV, DiD, mediation |
| `econ.EM` (Econometrics) | Program evaluation, IV, RD, synthetic control, panel data |
| `stat.ML` | Double ML, causal forests, heterogeneous effects, causal discovery |
| `cs.LG`, `cs.AI` | Causal discovery, causal representation learning, SCMs, counterfactual explanations, causal RL |

Secondary — mostly applications, worth searching when the subtopic fits:

- `stat.AP` — applied studies in epidemiology, medicine, social science
- `stat.TH` (alias `math.ST`) — asymptotics, efficiency bounds
- `econ.GN` — applied policy evaluation
- `cs.CY` (fairness), `cs.SI` (interference, networks), `cs.IR` (recommender debiasing),
  `cs.CL` (causality in/with language models)
- `q-bio.QM`, `q-bio.PE` — epidemiology, Mendelian randomization
- `q-fin.ST` — rarely

Skip: physics, math (beyond `math.ST`), and EESS. Their "causal" means something else.

## Subtopic → categories and phrases

| Subtopic | Categories | Phrases |
|---|---|---|
| Treatment effects / estimation | `stat.ME`, `econ.EM`, `stat.ML` | "treatment effect", "potential outcomes", "propensity score", "doubly robust" |
| Quasi-experimental designs | `econ.EM`, `stat.ME` | "difference-in-differences", "synthetic control", "regression discontinuity", "instrumental variable" |
| ML for causal effects | `stat.ML`, `cs.LG`, `econ.EM` | "double machine learning", "causal forest", "heterogeneous treatment effect", "uplift" |
| Causal discovery / graphs | `cs.LG`, `stat.ML`, `cs.AI`, `stat.ME` | "causal discovery", "structural causal model", "causal graph", "DAG learning" |
| Representation learning / counterfactuals | `cs.LG`, `cs.AI`, `cs.CV` | "causal representation learning", "counterfactual" |
| Mediation / sensitivity | `stat.ME` | "mediation analysis", "sensitivity analysis", "unmeasured confounding" |
| Epidemiology / health | `stat.AP`, `stat.ME`, `q-bio.QM` | "Mendelian randomization", "target trial", "observational study" |

A general sweep uses `"causal inference"` and `"causal effect"` in the core categories.

## How to search

Both project tools wrap the query in `all:`, so pass a quoted phrase as the query — not
`abs:...` or other field prefixes.

- Quick look with the `arxiv-search` skill, one phrase and one category per call (arXiv asks
  for 3 s between requests):

  ```bash
  uv run python .claude/skills/arxiv-search/scripts/arxiv_search.py '"treatment effect"' --category stat.ME --max 10
  ```

- Bulk fetch over a date range with `arxiv-fetch`. `-c` takes several categories (OR-ed into
  one query, deduplicated), and `--topic causal` adds every category listed above:

  ```bash
  uv run arxiv-fetch -c stat.ME econ.EM --from 2026-10-01 --to 2026-10-07 -q '"causal inference"' -o data/stat_ME_2026-10-07_causal.json
  ```

  For `stat.ME` and `econ.EM` a large share of papers are causal, so fetching the whole
  category without `-q` and screening afterwards misses less.

- For a single day's full screening, use the `causal-day` skill (fetch → `arxiv-screen` →
  judge → `arxiv-topic-md`). Its categories, keywords and false-positive phrases live in
  `src/arxiv_summary_news/topics/causal.toml`. Keep that file in step with this page.

## Screen the results

- **Deduplicate by `id`** — cross-listing (`stat.ME` + `econ.EM` + `stat.ML`) is the norm, so
  runs over several categories overlap. `primary_category` tells you where a paper "belongs".
- **Drop false positives** for "causal":
  - `cs.CL`, `cs.LG`: "causal attention", "causal mask", "causal language model" mean
    autoregressive decoding, not causal inference.
  - `eess.SP`, `eess.SY`: "causal filter/system" means non-anticipative signal processing.
  - Physics (`quant-ph`, `gr-qc`, `hep-th`): causal structure, causal sets, relativistic causality.
- **Watch for false negatives**: papers that never say "causal" but are causal inference
  (e.g. "policy evaluation", "average treatment effect", "confounding"). Add the subtopic
  phrases above when recall matters.
- Judge relevance from the abstract. When saving a topic analysis, follow the CLAUDE.md shape
  `{"<day>": [{"id", "title", "primary_category", "relevance", "reasoning"}, ...]}`
  (`primary_category` optional), and render it with `uv run arxiv-topic-md`.
