"""Query the arXiv API and print matching papers.

Standard library only, so it runs without installing project dependencies.
API docs: https://info.arxiv.org/help/api/user-manual.html
"""

import argparse
import json
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

API_URL = "http://export.arxiv.org/api/query"
NS = {"atom": "http://www.w3.org/2005/Atom"}
SORT_BY = {
    "relevance": "relevance",
    "submitted": "submittedDate",
    "updated": "lastUpdatedDate",
}


def build_url(query: str, max_results: int, category: str | None, sort: str) -> str:
    # Parenthesized so every term is matched against all fields, as in arxiv-fetch.
    search = f"all:({query})"
    if category:
        search = f"({search}) AND cat:{category}"
    params = {
        "search_query": search,
        "start": 0,
        "max_results": max_results,
        "sortBy": SORT_BY[sort],
        "sortOrder": "descending",
    }
    return f"{API_URL}?{urllib.parse.urlencode(params)}"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "arxiv-summary-news/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def _text(entry: ET.Element, tag: str) -> str:
    return " ".join((entry.findtext(f"atom:{tag}", "", NS) or "").split())


def parse(feed: bytes) -> list[dict]:
    root = ET.fromstring(feed)
    return [
        {
            "id": _text(entry, "id"),
            "title": _text(entry, "title"),
            "authors": [
                a.findtext("atom:name", "", NS)
                for a in entry.findall("atom:author", NS)
            ],
            "published": _text(entry, "published")[:10],
            "categories": [c.get("term") for c in entry.findall("atom:category", NS)],
            "summary": _text(entry, "summary"),
        }
        for entry in root.findall("atom:entry", NS)
    ]


def format_text(papers: list[dict]) -> str:
    if not papers:
        return "No results."
    lines = []
    for i, p in enumerate(papers, 1):
        authors = ", ".join(p["authors"][:3]) + (
            " et al." if len(p["authors"]) > 3 else ""
        )
        lines += [
            f"{i}. {p['title']}",
            f"   {authors} | {p['published']} | {', '.join(p['categories'][:3])}",
            f"   {p['id']}",
            f"   {p['summary'][:300]}{'...' if len(p['summary']) > 300 else ''}",
            "",
        ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("query", help="search terms")
    parser.add_argument("--max", type=int, default=5, help="number of results (max 50)")
    parser.add_argument("--category", help="arXiv category, e.g. cs.CL")
    parser.add_argument("--sort", choices=SORT_BY, default="submitted")
    parser.add_argument("--json", action="store_true", help="output JSON")
    args = parser.parse_args()

    url = build_url(args.query, max(1, min(args.max, 50)), args.category, args.sort)
    try:
        papers = parse(fetch(url))
    except (OSError, ET.ParseError) as exc:  # URLError is an OSError
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(papers, indent=2, ensure_ascii=False)
        if args.json
        else format_text(papers)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
