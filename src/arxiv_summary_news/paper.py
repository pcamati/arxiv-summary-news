"""Download one arXiv paper (PDF, metadata, plain text) for close reading.

Files go to ``data/papers/<id>/``:

- ``<id>.pdf``: the paper, from arXiv's ``/pdf/`` endpoint
- ``metadata.json``: same shape as one arxiv-fetch preprint, from the official API
- ``<id>.txt``: text of arXiv's HTML rendering (headings as ``#``, math as ``$LaTeX$``),
  when arXiv has one. Useful for long papers or when the PDF cannot be read in page ranges.

Requests are spaced like arxiv-fetch's.

Examples:
    uv run arxiv-paper 2605.25998
    uv run arxiv-paper arXiv:2605.25998v2 --dir data/papers
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

from arxiv_summary_news.fetch import API_URL, Preprint, RateLimitedClient, parse_feed

# New-style ids (2605.25998, optionally v2) and old-style ids (math.ST/0601001).
ID_PATTERN = re.compile(
    r"(?P<id>\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?P<version>v\d+)?$"
)


def normalize_id(text: str) -> str:
    """Strip prefixes, URLs and version from an arXiv identifier."""
    text = text.strip().removesuffix(".pdf").rstrip("/")
    text = re.sub(
        r"^(arxiv:|https?://(export\.)?arxiv\.org/(abs|pdf|html)/)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    match = ID_PATTERN.fullmatch(text)
    if not match:
        raise ValueError(f"not an arXiv identifier: {text!r}")
    return match["id"]


def metadata_url(arxiv_id: str) -> str:
    return (
        f"{API_URL}?{urllib.parse.urlencode({'id_list': arxiv_id, 'max_results': 1})}"
    )


def pdf_url(preprint: Preprint) -> str:
    """The versioned PDF link from the metadata, over https."""
    url = preprint.get("pdf_url") or f"https://arxiv.org/pdf/{preprint['id']}"
    return url.replace("http://", "https://", 1)


def html_url(preprint: Preprint) -> str:
    version = f"v{preprint['version']}" if preprint.get("version") else ""
    return f"https://arxiv.org/html/{preprint['id']}{version}"


def count_pages(pdf: bytes) -> int | None:
    """Best-effort page count; None when page objects are compressed out of sight."""
    pages = len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", pdf))
    return pages or None


def safe_dirname(arxiv_id: str) -> str:
    return arxiv_id.replace("/", "_")


# --- HTML -> text ------------------------------------------------------------


# Page chrome dropped with its content. Not svg: LaTeXML draws framed boxes as SVG
# with the box text inside <foreignObject>.
SKIP_TAGS = frozenset({"script", "style", "nav", "header", "footer", "button"})
BLOCK_TAGS = frozenset(
    {"p", "div", "li", "tr", "br", "figcaption", "blockquote", "section"}
)
HEADING_LEVELS = {f"h{n}": n for n in range(1, 7)}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        # While suppressing, only the tag that started it is counted, so other tags
        # nested inside (math in a skipped box, a skipped tag in math) cannot unbalance it.
        self._suppressing: str | None = None
        self._depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._suppressing:
            self._depth += tag == self._suppressing
            return
        if tag in SKIP_TAGS or tag == "math":
            self._suppressing, self._depth = tag, 1
            # arXiv's LaTeXML keeps the source formula in alttext.
            alttext = dict(attrs).get("alttext") if tag == "math" else None
            if alttext:
                self.parts.append(f" ${' '.join(alttext.split())}$ ")
        elif tag in HEADING_LEVELS:
            self.parts.append("\n\n" + "#" * HEADING_LEVELS[tag] + " ")
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._suppressing:
            self._depth -= tag == self._suppressing
            if not self._depth:
                self._suppressing = None
        elif tag in HEADING_LEVELS or tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._suppressing:
            # Source line breaks are not paragraph breaks; block tags make those.
            self.parts.append(re.sub(r"\s+", " ", data))


def html_to_text(html: str) -> str:
    """Readable plain text from an arXiv HTML paper."""
    parser = _TextExtractor()
    # The paper is the <article>; what precedes it is site chrome (banners, forms).
    article = html.find("<article")
    parser.feed(html[article:] if article >= 0 else html)
    text = "".join(parser.parts)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


# --- network -----------------------------------------------------------------


def fetch_metadata(client: RateLimitedClient, arxiv_id: str) -> Preprint:
    _, preprints = parse_feed(client.get(metadata_url(arxiv_id)))
    # Unknown ids come back as an empty feed or an entry without a title.
    if not preprints or not preprints[0]["title"] or preprints[0]["id"] != arxiv_id:
        raise LookupError(f"arXiv has no paper {arxiv_id}")
    return preprints[0]


def download_pdf(client: RateLimitedClient, url: str) -> bytes:
    pdf = client.get(url)
    if not pdf.startswith(b"%PDF"):
        raise ValueError(f"{url} did not return a PDF")
    return pdf


def download_html(client: RateLimitedClient, url: str) -> str | None:
    """The HTML rendering, or None when arXiv has none for this paper."""
    try:
        html = client.get(url).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    # Papers without a rendering can also answer with a placeholder page.
    return html if "ltx_document" in html else None


# --- CLI ---------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download an arXiv paper's PDF, metadata and text.",
        epilog="Thank you to arXiv for use of its open access interoperability.",
    )
    parser.add_argument(
        "id", help="arXiv id, e.g. 2605.25998, arXiv:2605.25998v2, or an abs URL"
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path("data/papers"),
        help="parent folder (default: data/papers)",
    )
    parser.add_argument(
        "--force", action="store_true", help="download again even if present"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        arxiv_id = normalize_id(args.id)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    folder = args.dir / safe_dirname(arxiv_id)
    pdf_path = folder / f"{safe_dirname(arxiv_id)}.pdf"
    text_path = folder / f"{safe_dirname(arxiv_id)}.txt"
    meta_path = folder / "metadata.json"

    if args.force or not (pdf_path.exists() and meta_path.exists()):
        client = RateLimitedClient()
        try:
            preprint = fetch_metadata(client, arxiv_id)
            pdf = download_pdf(client, pdf_url(preprint))
            html = download_html(client, html_url(preprint))
        except (
            urllib.error.URLError,
            TimeoutError,
            ET.ParseError,
            LookupError,
            ValueError,
        ) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        folder.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(pdf)
        meta_path.write_text(
            json.dumps(preprint, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if html is not None:
            text_path.write_text(html_to_text(html), encoding="utf-8")
    else:
        preprint = json.loads(meta_path.read_text(encoding="utf-8"))

    pages = count_pages(pdf_path.read_bytes())
    print(f"id:       {arxiv_id}v{preprint.get('version') or '?'}")
    print(f"pdf:      {pdf_path}")
    print(f"pages:    {pages if pages is not None else 'unknown'}")
    print(f"text:     {text_path if text_path.exists() else 'none (no HTML version)'}")
    print(f"metadata: {meta_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
