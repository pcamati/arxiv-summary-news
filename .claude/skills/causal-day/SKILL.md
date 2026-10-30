---
name: causal-day
description: Collect all causal inference preprints submitted to arXiv on one day and save them as a topic analysis (JSON + Markdown) in data/. Use when the user asks for causal inference papers for a given day, "today", or "yesterday".
argument-hint: [YYYY-MM-DD]
allowed-tools: Bash(uv run *)
---

# Causal inference papers for one day

Fetch, shortlist, judge, and render. The tools do the mechanical steps; you make the
relevance call by reading abstracts. Screening rules (false positives, what counts) are
in the `causal-inference-sources` skill; read it before judging.

Date requested: $ARGUMENTS (empty means today). Below, `D` is the date and
`P = data/causal-sources_D` is the file prefix.

## 1. Fetch the pool

```bash
uv run arxiv-fetch --topic causal --from D --to D -o P.json
```

One OR query over every category in `src/arxiv_summary_news/topics/causal.toml`,
deduplicated by id. **Exit code 2 means arXiv returned nothing for D.** For today or
yesterday this almost always means the papers are not announced yet
(Sunday–Thursday, 20:00 US Eastern). Stop and ask the user whether to use the previous
day instead. Do not guess. Dates are submission dates, which is also how `data/` files are named.
Exit code 1 (network error) or 130 (interrupted) means the fetch is incomplete: `P.json` is
left as it was and what was fetched goes to `P.partial.json`. Retry the fetch; do not screen
the partial file.

## 2. Shortlist

```bash
uv run arxiv-screen P.json --topic causal
```

This writes the worksheet `P_causal_candidates.md`. Read all of it:

- **Keyword matches**: read every abstract and judge it. Many will be noise (e.g. "spurious minima",
  "intervention" in the human-in-the-loop sense).
- **Only false-positive phrases**: glance at the titles. These are usually autoregressive "causal" uses.
- **Other titles**: scan every title for causal work that avoids the vocabulary (peer
  effects, policy evaluation, mechanism identification, "observation cannot tell these apart").
  Pull the abstracts of the suspicious ones:

  ```bash
  uv run arxiv-screen P.json --ids <id> <id> ...
  ```

## 3. Write the analysis

Write `P_causal.json` with the Write tool, shaped:

```json
{"D": [{"id": "...", "title": "...", "primary_category": "...", "relevance": "core", "reasoning": "..."}]}
```

- `relevance`: `core` (causal inference proper: estimands, identification, estimators,
  designs, discovery), `methods` (counterfactual or interventional methods applied
  elsewhere, e.g. to ML models or agents), `loose` (causal in spirit, not causal inference).
- `reasoning`: 1–3 sentences from the abstract on *why* it is causal: the estimand,
  the design, the intervention. Do not just restate the title.
- Copy `title` and `primary_category` exactly from the pool. Order core → methods → loose.

## 4. Render and report

```bash
uv run arxiv-topic-md P_causal.json --pool P.json --topic causal
```

Tell the user the count (N of M), a one-line gist per core paper, and the two file paths.
Mention anything you were unsure about. If the pool looked unusually small, say so: the API sometimes lags
behind the announcement, and re-running later may add papers.

## Tuning

If a paper you judged relevant was not a keyword match, and a phrase would have caught
it without adding much noise, propose adding it to `keywords` in `causal.toml`. Do the same for
recurring false positives and `false_positives`. Ask before editing.
