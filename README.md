# arxiv-summary-news

Fetch arXiv preprints, screen them by topic, and summarize them as Markdown.

## Install

Requires Python 3.14 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Usage

Fetch every preprint in some categories for a date range into a JSON list:

```bash
uv run arxiv-fetch -c stat.ME econ.EM --from 2026-10-14 --to 2026-10-14 -o data/pool.json
```

`--topic causal` adds the categories defined in `src/arxiv_summary_news/topics/causal.toml`.
arXiv lists papers only after it announces them (Sunday–Thursday evenings, US Eastern).

Then:

| Command | What it does |
|---|---|
| `uv run arxiv-md data/pool.json` | Render the preprints as Markdown (title, authors, abstract) |
| `uv run arxiv-screen data/pool.json --topic causal` | Keyword-shortlist a pool into a Markdown worksheet |
| `uv run arxiv-topic-md <analysis.json> --pool data/pool.json --topic causal` | Render a topic relevance analysis as a report |
| `uv run arxiv-paper 2605.25998` | Download one paper (PDF, metadata, text) to `data/papers/<id>/` |

Each command takes `--help` for its options.

## Development

```bash
uv run ruff check . && uv run ruff format .
uv run pytest
```

The tests run offline.

Thank you to arXiv for use of its open access interoperability.
