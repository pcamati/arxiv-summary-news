---
name: arxiv-search
description: Search the arXiv API for preprints and list titles, authors, dates, links, and abstracts. Use when the user asks to find, fetch, or look up arXiv papers, or when real arXiv data is needed for development or testing.
argument-hint: <query> [--max N] [--category cs.CL]
allowed-tools: Bash(uv run *)
---

# arXiv search

Fetch papers from the public arXiv API with the bundled script and summarize the results for the user.

## How to run

```bash
uv run python .claude/skills/arxiv-search/scripts/arxiv_search.py "<query>" --max 5
```

Options:

- `--max N` — number of results (default 5, capped at 50)
- `--category CAT` — restrict to an arXiv category, e.g. `cs.CL`, `quant-ph`, `astro-ph.CO`
- `--sort {relevance,submitted,updated}` — sort order (default `submitted`, newest first)
- `--json` — emit JSON instead of text (useful for feeding into package code or tests)

The user's arguments: $ARGUMENTS

## Steps

1. Turn the user's request into a query and, if obvious, a category.
2. Run the script. If you need more than one query, run them one at a time (arXiv asks for 3 s between requests).
3. Report back a short list: title, first authors, date, and link, plus a one-sentence gist of each abstract.
4. If the script fails (network error, no results), say so plainly and suggest a broader query.
