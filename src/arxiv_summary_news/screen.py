"""Shortlist preprints for a topic so that relevance can be judged by reading.

Keyword matching only narrows the pile; it does not decide relevance. The output is a
Markdown worksheet: matching preprints with their abstracts (strongest matches first),
preprints whose only match was a known false-positive phrase, and the remaining titles
so that papers that never use the topic's vocabulary can still be spotted.

Examples:
    uv run arxiv-screen data/causal-sources_2026-10-14.json --topic causal
    uv run arxiv-screen data/causal-sources_2026-10-14.json --ids 2610.20045 2610.20095
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from arxiv_summary_news.to_markdown import Preprint, load_preprints
from arxiv_summary_news.topic import Topic, load_topic


@dataclass(frozen=True)
class Screened:
    preprint: Preprint
    terms: tuple[str, ...]  # keyword matches, lowercased
    false_positives: tuple[str, ...]  # false-positive phrases found


def _matches(patterns: tuple[re.Pattern[str], ...], text: str) -> tuple[str, ...]:
    return tuple(
        sorted({m.group(0).lower() for p in patterns for m in p.finditer(text)})
    )


def screen_preprint(preprint: Preprint, topic: Topic) -> Screened:
    """Match a preprint's title and abstract against the topic's keywords."""
    text = f"{preprint['title']} {preprint.get('abstract') or ''}"
    false_positives = _matches(topic.false_positives, text)
    for pattern in topic.false_positives:
        text = pattern.sub(" ", text)
    return Screened(preprint, _matches(topic.keywords, text), false_positives)


def _categories(preprint: Preprint) -> str:
    primary = preprint.get("primary_category") or "?"
    others = [c for c in preprint.get("categories", []) if c != primary]
    return f"`{primary}`" + (f" (also {', '.join(others)})" if others else "")


def render_abstract(preprint: Preprint, terms: tuple[str, ...] = ()) -> str:
    """One preprint as a worksheet entry: heading, categories, terms, abstract."""
    lines = [
        f"### {preprint['id']} {preprint['title']}",
        "",
        _categories(preprint),
    ]
    if terms:
        lines[-1] += " · terms: " + ", ".join(terms)
    lines += ["", preprint.get("abstract") or "_No abstract._"]
    return "\n".join(lines)


def render_worksheet(screened: list[Screened], topic: Topic, source: str) -> str:
    """Render the screening worksheet as Markdown."""
    hits = sorted((s for s in screened if s.terms), key=lambda s: -len(s.terms))
    fp_only = [s for s in screened if not s.terms and s.false_positives]
    rest = [s for s in screened if not s.terms and not s.false_positives]

    out = [
        f"# Screening worksheet: {topic.title}, `{source}`",
        "",
        (
            f"{len(screened)} preprints: {len(hits)} keyword matches, "
            f"{len(fp_only)} with only false-positive phrases, {len(rest)} others. "
            "Keyword matches are candidates, not verdicts."
        ),
        "",
        f"## Keyword matches ({len(hits)})",
    ]
    out += ["", "\n\n".join(render_abstract(s.preprint, s.terms) for s in hits)]
    out += ["", f"## Only false-positive phrases ({len(fp_only)})", ""]
    out += [
        f"- {s.preprint['id']} `{s.preprint.get('primary_category')}` "
        f"{s.preprint['title']} — {', '.join(s.false_positives)}"
        for s in fp_only
    ]
    out += ["", f"## Other titles ({len(rest)})", ""]
    out += [
        f"- {s.preprint['id']} `{s.preprint.get('primary_category')}` {s.preprint['title']}"
        for s in rest
    ]
    return "\n".join(out) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Shortlist preprints for a topic into a Markdown worksheet."
    )
    parser.add_argument("input", type=Path, help="preprints JSON file")
    parser.add_argument(
        "--topic", default="causal", help="topic name or .toml path (default: causal)"
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="worksheet path (default: <input stem>_<topic>_candidates.md next to input)",
    )
    parser.add_argument(
        "--ids",
        nargs="+",
        metavar="ID",
        help="instead of screening, print the abstracts of these preprints",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    # Abstracts contain characters a Windows console code page cannot encode.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        preprints = load_preprints(args.input)
        topic = load_topic(args.topic)
    except (OSError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.ids:
        by_id = {p["id"]: p for p in preprints}
        missing = [i for i in args.ids if i not in by_id]
        print("\n\n".join(render_abstract(by_id[i]) for i in args.ids if i in by_id))
        if missing:
            print(f"error: not in {args.input}: {', '.join(missing)}", file=sys.stderr)
            return 1
        return 0

    screened = [screen_preprint(p, topic) for p in preprints]
    output = args.output or args.input.with_name(
        f"{args.input.stem}_{topic.name}_candidates.md"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        render_worksheet(screened, topic, args.input.name), encoding="utf-8"
    )
    hits = sum(1 for s in screened if s.terms)
    print(
        f"{hits} of {len(screened)} preprints match {topic.name} keywords; wrote {output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
