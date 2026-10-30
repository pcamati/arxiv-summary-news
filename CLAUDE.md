## Project

`arxiv-summary-news` parses arXiv preprints and summarizes topics.

## Tooling

- Python 3.14, managed with [uv](https://docs.astral.sh/uv/). Use `uv` for everything — don't call `pip` directly.
- Add a dependency: `uv add <package>` (dev-only: `uv add --dev <package>`)
- Sync the environment: `uv sync`
- Lint + format: `uv run ruff check . && uv run ruff format .`
- Tests (offline): `uv run pytest`

## Commands

- `uv run arxiv-fetch -c <category> [<category> ...] [--topic <name>] --from YYYY-MM-DD --to YYYY-MM-DD [-q <terms>] [-o <file>]` —
  fetch all matching preprints into a JSON list (one dict per preprint; default `data/preprints.json`).
  Several categories are OR-ed into one query; `--topic` adds the topic file's categories.
  Splits date ranges into daily queries to stay under arXiv's 30,000-result cap.
  Exits with code 2 and writes nothing when there are no results (often: not announced yet).
  On a network error (exit 1) or Ctrl-C (exit 130) it leaves `-o` untouched and saves what it
  got to `<output stem>.partial.json`.
- `uv run arxiv-screen <pool.json> [--topic causal] [-o <file.md>]` — keyword-shortlist a pool into a
  Markdown worksheet (`<pool stem>_<topic>_candidates.md`); `--ids <id> ...` prints given abstracts.
- `uv run arxiv-topic-md <analysis.json> [--pool <pool.json>] [--topic causal] [-o <file.md>]` —
  render a topic analysis as a Markdown report grouped by relevance.
- `uv run arxiv-md <file.json> [-o <file.md>] [-t <title>]` — render a preprints JSON as Markdown
  (id, title, authors, abstract).
- `uv run arxiv-paper <id> [--force]` — download one paper to `data/papers/<id>/`: PDF, `metadata.json`,
  and `<id>.txt` (text of arXiv's HTML rendering, math as `$LaTeX$`) when available. Cached.
  For individual papers the user asks about, not for bulk downloads.
- The API only lists papers after arXiv announces them (Sunday–Thursday evenings, US Eastern).

## Layout (crude/in-progress)

- `src/arxiv_summary_news/` — package source (src layout, built with `uv_build`)
  - `fetch.py` — arXiv API client, Atom parsing, `arxiv-fetch` CLI
  - `to_markdown.py` — JSON → Markdown, `arxiv-md` CLI
  - `topic.py` + `topics/<name>.toml` — topic definitions (categories, keywords, false positives, sections)
  - `screen.py` — keyword shortlist worksheet, `arxiv-screen` CLI
  - `topic_md.py` — topic analysis JSON → Markdown report, `arxiv-topic-md` CLI
  - `paper.py` — single-paper download and HTML → text, `arxiv-paper` CLI
- `tests/` — offline pytest suite
- `data/` — fetched output (gitignored). Naming: `<category>_<YYYY-MM-DD>.json/.md`;
  topic analyses as `<category>_<YYYY-MM-DD>_<topic>.json/.md`, JSON shaped
  `{"<day>": [{"id", "title", "primary_category", "relevance", "reasoning"}, ...]}`
  (`primary_category` optional). Multi-category pools use `<topic>-sources` as the category,
  e.g. `causal-sources_2026-10-14.json` → `causal-sources_2026-10-14_causal.json/.md`.
  Single papers live in `data/papers/<id>/` with their `summary.md`.
- `.claude/skills/` — project skills available to Claude Code (see `arxiv-search` below)

## Conventions

- Follow Python coding best practices.
- Type-annotate all public functions.
- Prefer the standard library unless a dependency clearly pays for itself.
- Keep network access isolated in small functions so the rest of the code is testable offline.

## arXiv API etiquette

- Use the official API (`http://export.arxiv.org/api/query`), not page scraping.
- In doubt, use the arXiv API user manual (`https://info.arxiv.org/help/api/user-manual.html`)
- Wait at least 3 seconds between consecutive requests and keep single queries to a reasonable size.
- Keep the attribution line in the README: "Thank you to arXiv for use of its open access interoperability."

## Claude Code tools

- `/arxiv-search <query>` — fetches recent papers from the arXiv API and prints a compact list.
  Use it when you need real arXiv data while developing or testing summaries.
- `/read-paper <id> [focus]` — download a paper, read it in full, and write `data/papers/<id>/summary.md`.
- `/causal-day [YYYY-MM-DD]` — full causal inference screening for one day: fetch, shortlist,
  judge relevance, write the analysis JSON and Markdown to `data/`.
