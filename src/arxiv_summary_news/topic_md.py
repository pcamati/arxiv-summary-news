"""Render a topic analysis JSON as a Markdown report.

The analysis is shaped ``{"<day>": [{"id", "title", "relevance", "reasoning"}, ...]}``;
entries may also carry ``primary_category``. Entries are grouped by relevance, in the
order of the topic's ``[sections]`` table, then any other labels in order of appearance.

Example:
    uv run arxiv-topic-md data/causal-sources_2026-10-14_causal.json \\
        --pool data/causal-sources_2026-10-14.json --topic causal
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from arxiv_summary_news.to_markdown import Preprint, load_preprints
from arxiv_summary_news.topic import load_topic

Entry = dict[str, Any]
Analysis = dict[str, list[Entry]]
REQUIRED_KEYS = ("id", "title", "relevance", "reasoning")


def load_analysis(path: Path) -> Analysis:
    """Read and validate an analysis JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(
        isinstance(v, list) for v in data.values()
    ):
        raise TypeError(f"{path}: expected {{day: [entries]}}")
    for day, entries in data.items():
        for n, entry in enumerate(entries):
            missing = [k for k in REQUIRED_KEYS if k not in entry]
            if missing:
                raise ValueError(f"{path}: {day} entry {n} lacks {', '.join(missing)}")
    return data


def section_order(entries: list[Entry], sections: dict[str, str]) -> list[str]:
    """Relevance labels to render: the topic's order first, then any others."""
    present = list(dict.fromkeys(e["relevance"] for e in entries))
    return [r for r in sections if r in present] + [
        r for r in present if r not in sections
    ]


def render_entry(entry: Entry, pool: dict[str, Preprint], level: int) -> str:
    arxiv_id = entry["id"]
    primary = entry.get("primary_category") or pool.get(arxiv_id, {}).get(
        "primary_category"
    )
    prefix = f"*{primary}* — " if primary else ""
    return (
        f"{'#' * level} [{arxiv_id}](https://arxiv.org/abs/{arxiv_id}) {entry['title']}\n\n"
        f"{prefix}{entry['reasoning']}"
    )


def render_sections(
    entries: list[Entry],
    sections: dict[str, str],
    pool: dict[str, Preprint],
    level: int,
) -> list[str]:
    blocks = []
    for label in section_order(entries, sections):
        blocks.append(f"{'#' * level} {sections.get(label, label.capitalize())}")
        blocks += [
            render_entry(e, pool, level + 1) for e in entries if e["relevance"] == label
        ]
    return blocks


def render_report(
    analysis: Analysis,
    title: str,
    topic_title: str,
    sections: dict[str, str],
    pool: dict[str, Preprint] | None = None,
    pool_name: str | None = None,
    categories: tuple[str, ...] = (),
) -> str:
    """Render the whole analysis as one Markdown document."""
    pool = pool or {}
    total = sum(len(entries) for entries in analysis.values())
    scope = f" of {len(pool)} preprints in `{pool_name}`" if pool_name else " preprints"
    intro = f"{total}{scope} judged related to {topic_title}, based on title and abstract only."
    if categories:
        intro += (
            " Categories searched: " + ", ".join(f"`{c}`" for c in categories) + "."
        )
    blocks = [f"# {title}", intro]

    if len(analysis) == 1:
        blocks += render_sections(next(iter(analysis.values())), sections, pool, 2)
    else:
        for day, entries in analysis.items():
            blocks.append(f"## {day}")
            blocks += render_sections(entries, sections, pool, 3)
    return "\n\n".join(blocks) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a topic analysis JSON as a Markdown report."
    )
    parser.add_argument("input", type=Path, help="analysis JSON file")
    parser.add_argument(
        "--pool", type=Path, help="screened preprints JSON (for counts and categories)"
    )
    parser.add_argument(
        "--topic", help="topic name or .toml path (for section headings and wording)"
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="output Markdown file (default: input path with .md extension)",
    )
    parser.add_argument("-t", "--title", help="document heading")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        analysis = load_analysis(args.input)
        topic = load_topic(args.topic) if args.topic else None
        pool = {p["id"]: p for p in load_preprints(args.pool)} if args.pool else None
    except (OSError, TypeError, ValueError) as exc:  # JSONDecodeError is a ValueError
        print(f"error: {exc}", file=sys.stderr)
        return 1

    topic_title = topic.title if topic else "the topic"
    days = ", ".join(analysis)
    title = args.title or (
        f"{topic.title[0].upper()}{topic.title[1:]} papers, {days}"
        if topic
        else args.input.stem
    )
    output = args.output or args.input.with_suffix(".md")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        render_report(
            analysis,
            title,
            topic_title,
            topic.sections if topic else {},
            pool,
            args.pool.name if args.pool else None,
            topic.categories if topic and args.pool else (),
        ),
        encoding="utf-8",
    )
    print(f"wrote {sum(len(e) for e in analysis.values())} entries to {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
