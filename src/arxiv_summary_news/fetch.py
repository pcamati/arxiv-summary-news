"""Fetch arXiv preprints with their metadata and save them as a JSON list.

Uses the official arXiv query API: https://info.arxiv.org/help/api/user-manual.html
Results are scoped by a search query, a category, and/or a submission date range.
Date ranges are split into windows so each API query stays well below arXiv's
30,000-result cap, and requests are spaced at least 3 seconds apart.

Examples:
    uv run arxiv-fetch --category cs.CL --from 2026-10-01 --to 2026-10-07 -o data/cs_CL.json
    uv run arxiv-fetch --topic causal --from 2026-10-14 --to 2026-10-14 \\
        -o data/causal-sources_2026-10-14.json
"""

import argparse
import json
import logging
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from arxiv_summary_news.topic import load_topic

API_URL = "http://export.arxiv.org/api/query"
USER_AGENT = "arxiv-summary-news/0.1"
REQUEST_DELAY_S = 3.0
PAGE_SIZE = 500  # arXiv allows up to 2000 per call; smaller pages fail less often
MAX_RESULTS_PER_QUERY = 30_000  # arXiv hard limit on start + max_results
MAX_RETRIES = 4
EXIT_NO_RESULTS = 2
EXIT_INTERRUPTED = 130  # shell convention for SIGINT

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}

log = logging.getLogger("arxiv_fetch")

Preprint = dict[str, Any]


# --- query construction ------------------------------------------------------


def build_search_query(
    query: str | None = None,
    categories: Sequence[str] = (),
    start_day: date | None = None,
    end_day: date | None = None,
) -> str:
    """Combine search terms, categories, and an inclusive date range into an arXiv search_query.

    Several categories are OR-ed, so cross-listed preprints come back once.
    """
    parts = []
    if query:
        parts.append(f"all:({query})")
    if len(categories) == 1:
        parts.append(f"cat:{categories[0]}")
    elif categories:
        parts.append("(" + " OR ".join(f"cat:{c}" for c in categories) + ")")
    if start_day and end_day:
        parts.append(f"submittedDate:[{start_day:%Y%m%d}0000 TO {end_day:%Y%m%d}2359]")
    if not parts:
        raise ValueError("need at least one of query, category, or date range")
    return " AND ".join(parts)


def build_url(search_query: str, start: int, max_results: int) -> str:
    params = {
        "search_query": search_query,
        "start": start,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "ascending",
    }
    return f"{API_URL}?{urllib.parse.urlencode(params)}"


def date_windows(
    start_day: date, end_day: date, days: int
) -> Iterator[tuple[date, date]]:
    """Yield consecutive, non-overlapping inclusive (first, last) day windows."""
    current = start_day
    while current <= end_day:
        last = min(current + timedelta(days=days - 1), end_day)
        yield current, last
        current = last + timedelta(days=1)


# --- network -----------------------------------------------------------------


class RateLimitedClient:
    """HTTP GET with a minimum delay between requests and retry with backoff."""

    def __init__(self, delay_s: float = REQUEST_DELAY_S) -> None:
        self.delay_s = delay_s
        self._last_request = 0.0

    def get(self, url: str) -> bytes:
        for attempt in range(1, MAX_RETRIES + 1):
            wait = self._last_request + self.delay_s - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()
            try:
                request = urllib.request.Request(
                    url, headers={"User-Agent": USER_AGENT}
                )
                with urllib.request.urlopen(request, timeout=60) as response:
                    return response.read()
            except (urllib.error.URLError, TimeoutError) as exc:
                # Client errors (404 etc.) will not go away on retry; 429 might.
                client_error = (
                    isinstance(exc, urllib.error.HTTPError)
                    and 400 <= exc.code < 500
                    and exc.code != 429
                )
                if client_error or attempt == MAX_RETRIES:
                    raise
                backoff = self.delay_s * 2**attempt
                log.warning(
                    "request failed (%s); retry %d in %.0fs", exc, attempt, backoff
                )
                time.sleep(backoff)
        raise AssertionError("unreachable")


# --- parsing -----------------------------------------------------------------


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())


def parse_entry(entry: ET.Element) -> Preprint:
    """Convert one Atom <entry> into a preprint dictionary."""
    abs_url = _clean(entry.findtext("atom:id", None, NS))
    arxiv_id = abs_url.rsplit("/abs/", 1)[-1]
    base_id, _, version = arxiv_id.rpartition("v")
    if not base_id or not version.isdigit():
        base_id, version = arxiv_id, ""

    pdf_url = None
    for link in entry.findall("atom:link", NS):
        if link.get("title") == "pdf":
            pdf_url = link.get("href")

    primary = entry.find("arxiv:primary_category", NS)
    return {
        "id": base_id,
        "version": int(version) if version else None,
        "title": _clean(entry.findtext("atom:title", None, NS)),
        "abstract": _clean(entry.findtext("atom:summary", None, NS)),
        "authors": [
            {
                "name": _clean(author.findtext("atom:name", None, NS)),
                "affiliations": [
                    _clean(a.text) for a in author.findall("arxiv:affiliation", NS)
                ],
            }
            for author in entry.findall("atom:author", NS)
        ],
        "published": _clean(entry.findtext("atom:published", None, NS)),
        "updated": _clean(entry.findtext("atom:updated", None, NS)),
        "primary_category": primary.get("term") if primary is not None else None,
        "categories": [c.get("term") for c in entry.findall("atom:category", NS)],
        "comment": _clean(entry.findtext("arxiv:comment", None, NS)) or None,
        "journal_ref": _clean(entry.findtext("arxiv:journal_ref", None, NS)) or None,
        "doi": _clean(entry.findtext("arxiv:doi", None, NS)) or None,
        "abs_url": abs_url,
        "pdf_url": pdf_url,
    }


def parse_feed(feed: bytes) -> tuple[int, list[Preprint]]:
    """Return (total results reported by the API, preprints on this page)."""
    root = ET.fromstring(feed)
    total = int(root.findtext("opensearch:totalResults", "0", NS))
    return total, [parse_entry(e) for e in root.findall("atom:entry", NS)]


# --- fetching ----------------------------------------------------------------


def fetch_query(client: RateLimitedClient, search_query: str) -> Iterator[Preprint]:
    """Page through every result of one search query."""
    start, total = 0, None
    empty_retries = 0
    while total is None or start < min(total, MAX_RESULTS_PER_QUERY):
        page_size = min(PAGE_SIZE, MAX_RESULTS_PER_QUERY - start)
        total_reported, page = parse_feed(
            client.get(build_url(search_query, start, page_size))
        )
        if total is None:
            total = total_reported
            log.info("%s -> %d results", search_query, total)
            if total > MAX_RESULTS_PER_QUERY:
                log.warning(
                    "query exceeds arXiv's %d-result cap; use a smaller --window-days",
                    MAX_RESULTS_PER_QUERY,
                )
        if not page:
            # The API occasionally returns an empty page mid-stream; retry a couple of times.
            empty_retries += 1
            if empty_retries > 2:
                log.warning("giving up on %s at %d/%d", search_query, start, total)
                return
            continue
        empty_retries = 0
        yield from page
        start += len(page)


def fetch_all(
    client: RateLimitedClient,
    query: str | None,
    categories: Sequence[str],
    start_day: date | None,
    end_day: date | None,
    window_days: int,
) -> Iterator[Preprint]:
    """Fetch every preprint in scope, splitting a date range into windows."""
    if start_day and end_day:
        for first, last in date_windows(start_day, end_day, window_days):
            yield from fetch_query(
                client, build_search_query(query, categories, first, last)
            )
    else:
        yield from fetch_query(client, build_search_query(query, categories))


# --- output ------------------------------------------------------------------


def save_json(preprints: list[Preprint], path: Path) -> None:
    """Write atomically so an interrupted run never leaves a truncated file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(preprints, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    tmp.replace(path)


def partial_path(path: Path) -> Path:
    """Where an incomplete fetch goes, so it never replaces a complete output."""
    return path.with_name(f"{path.stem}.partial{path.suffix}")


def save_partial(preprints: list[Preprint], path: Path) -> None:
    if not preprints:
        log.error("nothing fetched; nothing written")
        return
    partial = partial_path(path)
    save_json(preprints, partial)
    log.error("saved %d preprints fetched so far to %s", len(preprints), partial)


# --- CLI ---------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch arXiv preprints with metadata into a JSON file.",
        epilog="Thank you to arXiv for use of its open access interoperability.",
    )
    parser.add_argument(
        "-q", "--query", help="search terms (matched against all fields)"
    )
    parser.add_argument(
        "-c",
        "--category",
        dest="categories",
        nargs="+",
        default=[],
        help="one or more arXiv categories, e.g. cs.CL quant-ph",
    )
    parser.add_argument(
        "--topic",
        help="also fetch the categories listed in a topic file (name, e.g. causal, or .toml path)",
    )
    parser.add_argument(
        "--from", dest="start_day", type=date.fromisoformat, help="YYYY-MM-DD"
    )
    parser.add_argument(
        "--to", dest="end_day", type=date.fromisoformat, help="YYYY-MM-DD"
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=1,
        help="days per API query when using a date range",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("data/preprints.json"),
        help="output JSON file",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    args = parser.parse_args(argv)

    if (args.start_day is None) != (args.end_day is None):
        parser.error("--from and --to must be given together")
    if args.start_day and args.start_day > args.end_day:
        parser.error("--from must not be after --to")
    if args.window_days < 1:
        parser.error("--window-days must be >= 1")
    if args.topic:
        try:
            topic_categories = load_topic(args.topic).categories
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        args.categories = list(dict.fromkeys([*args.categories, *topic_categories]))
    if not (args.query or args.categories or args.start_day):
        parser.error(
            "give at least one of --query, --category, --topic, or --from/--to"
        )
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    preprints: dict[str, Preprint] = {}
    client = RateLimitedClient()
    try:
        for preprint in fetch_all(
            client,
            args.query,
            args.categories,
            args.start_day,
            args.end_day,
            args.window_days,
        ):
            preprints[preprint["id"]] = preprint
    except KeyboardInterrupt:
        log.error("interrupted")
        save_partial(list(preprints.values()), args.output)
        return EXIT_INTERRUPTED
    except (urllib.error.URLError, TimeoutError, ET.ParseError) as exc:
        log.error("fetch failed: %s", exc)
        save_partial(list(preprints.values()), args.output)
        return 1

    if not preprints:
        # Most often a recent date: the API lists papers only after arXiv announces them.
        log.error(
            "no preprints found; nothing written to %s. For recent dates, arXiv may not "
            "have announced them yet (Sunday-Thursday, 20:00 US Eastern).",
            args.output,
        )
        return EXIT_NO_RESULTS

    save_json(list(preprints.values()), args.output)
    log.info("saved %d preprints to %s", len(preprints), args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
