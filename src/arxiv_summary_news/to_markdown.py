"""Convert a preprints JSON file (as written by arxiv-fetch) into a Markdown file.

Example:
    uv run arxiv-md data/quant-ph_2026-10-08.json
    uv run arxiv-md data/quant-ph_2026-10-08.json -o reports/quant-ph.md
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

Preprint = dict[str, Any]


def load_preprints(path: Path) -> list[Preprint]:
    """Read a JSON list of preprint dictionaries."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise TypeError(f"{path}: expected a JSON list of preprints")
    return data


def format_authors(authors: list[dict[str, Any]]) -> str:
    return ", ".join(author["name"] for author in authors) or "Unknown"


def render_preprint(preprint: Preprint) -> str:
    """Render one preprint as a Markdown section."""
    arxiv_id = preprint["id"]
    abs_url = preprint.get("abs_url") or f"https://arxiv.org/abs/{arxiv_id}"
    return "\n".join(
        [
            f"## {preprint['title']}",
            "",
            f"- **arXiv ID:** [{arxiv_id}]({abs_url})",
            f"- **Authors:** {format_authors(preprint.get('authors', []))}",
            "",
            preprint.get("abstract") or "_No abstract._",
        ]
    )


def render_document(preprints: list[Preprint], title: str) -> str:
    """Render all preprints as one Markdown document."""
    header = [
        f"# {title}",
        "",
        f"{len(preprints)} preprints.",
        "",
        "_Thank you to arXiv for use of its open access interoperability._",
    ]
    sections = [render_preprint(p) for p in preprints]
    return "\n\n".join(["\n".join(header), *sections]) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert a preprints JSON file into Markdown."
    )
    parser.add_argument("input", type=Path, help="preprints JSON file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="output Markdown file (default: input path with .md extension)",
    )
    parser.add_argument(
        "-t", "--title", help="document heading (default: input file name)"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output = args.output or args.input.with_suffix(".md")
    title = args.title or args.input.stem

    try:
        preprints = load_preprints(args.input)
    except (OSError, TypeError, ValueError) as exc:  # JSONDecodeError is a ValueError
        print(f"error: {exc}", file=sys.stderr)
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_document(preprints, title), encoding="utf-8")
    print(f"wrote {len(preprints)} preprints to {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
