import io
import json
import urllib.error

import pytest

from arxiv_summary_news import fetch, paper
from arxiv_summary_news.paper import count_pages, html_to_text, normalize_id, pdf_url

HTML = r"""<html><head><style>p {}</style><script>var x;</script></head><body>
<nav>Menu</nav><article class="ltx_document">
<h1>A Paper</h1><h2>1 Introduction</h2>
<p>We estimate <math alttext="\mathbb{E}[Y(a)]"><mi>E</mi><annotation>junk</annotation></math>
from logged   data.</p><p>Second&nbsp;paragraph &amp; more.</p>
</article><footer>Footer</footer></body></html>"""

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <opensearch:totalResults>1</opensearch:totalResults>
  <entry>
    <id>http://arxiv.org/abs/2605.25998v2</id>
    <title>A Paper</title>
    <summary>Abstract.</summary>
    <author><name>A. Author</name></author>
    <arxiv:primary_category term="stat.ME"/>
    <category term="stat.ME"/>
    <link title="pdf" href="http://arxiv.org/pdf/2605.25998v2" rel="related"/>
  </entry>
</feed>"""


@pytest.mark.parametrize(
    "text",
    [
        "2605.25998",
        "arXiv:2605.25998v2",
        "  ARXIV:2605.25998 ",
        "https://arxiv.org/abs/2605.25998v1",
        "https://arxiv.org/pdf/2605.25998v3.pdf",
        "http://export.arxiv.org/abs/2605.25998/",
    ],
)
def test_normalize_id(text: str) -> None:
    assert normalize_id(text) == "2605.25998"


def test_normalize_old_style_id() -> None:
    assert normalize_id("arXiv:math.ST/0601001v1") == "math.ST/0601001"


def test_normalize_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        normalize_id("causal inference")


def test_pdf_url_uses_https() -> None:
    assert (
        pdf_url({"id": "1", "pdf_url": "http://arxiv.org/pdf/1v2"})
        == "https://arxiv.org/pdf/1v2"
    )
    assert pdf_url({"id": "1"}) == "https://arxiv.org/pdf/1"


def test_count_pages() -> None:
    assert count_pages(b"%PDF /Type /Pages /Type /Page /Type/Page") == 2
    assert count_pages(b"%PDF compressed") is None


def test_html_to_text() -> None:
    text = html_to_text(HTML)
    assert text.startswith("# A Paper\n\n## 1 Introduction\n")
    assert r"We estimate $\mathbb{E}[Y(a)]$ from logged data." in text
    assert "Second paragraph & more." in text
    for noise in ("Menu", "Footer", "var x", "junk", "p {}"):
        assert noise not in text


def test_html_to_text_keeps_svg_boxes_and_recovers_after_them() -> None:
    html = (
        '<p>Before.</p><svg><g><foreignObject><span>Box <math alttext="x"><mi>x'
        "</mi></math> text</span></foreignObject></g></svg><nav><math></math></nav>"
        "<p>After the box.</p>"
    )
    text = html_to_text(html)
    assert "Box $x$ text" in text
    assert text.rstrip().endswith("After the box.")


def not_found(url: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, 404, "Not Found", {}, io.BytesIO())


class FakeClient:
    def __init__(self, responses: dict[str, bytes | Exception]) -> None:
        self.responses = responses

    def get(self, url: str) -> bytes:
        body = next(body for key, body in self.responses.items() if key in url)
        if isinstance(body, Exception):
            raise body
        return body


def test_main_downloads_once(tmp_path, monkeypatch, capsys) -> None:
    calls = []

    def client() -> FakeClient:
        calls.append(1)
        return FakeClient(
            {
                "id_list": FEED,
                "/pdf/": b"%PDF-1.7 /Type /Page",
                "/html/": HTML.encode(),
            }
        )

    monkeypatch.setattr(paper, "RateLimitedClient", client)
    assert paper.main(["arXiv:2605.25998", "--dir", str(tmp_path)]) == 0
    folder = tmp_path / "2605.25998"
    assert (folder / "2605.25998.pdf").read_bytes().startswith(b"%PDF")
    assert (
        json.loads((folder / "metadata.json").read_text(encoding="utf-8"))["title"]
        == "A Paper"
    )
    assert "1 Introduction" in (folder / "2605.25998.txt").read_text(encoding="utf-8")
    assert "pages:    1" in capsys.readouterr().out

    assert paper.main(["2605.25998", "--dir", str(tmp_path)]) == 0  # cached
    assert len(calls) == 1


def test_main_rejects_non_pdf(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        paper,
        "RateLimitedClient",
        lambda: FakeClient({"id_list": FEED, "/pdf/": b"<html>", "/html/": b""}),
    )
    assert paper.main(["2605.25998", "--dir", str(tmp_path)]) == 1
    assert not (tmp_path / "2605.25998").exists()


def test_main_without_html_version(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        paper,
        "RateLimitedClient",
        lambda: FakeClient(
            {"id_list": FEED, "/pdf/": b"%PDF", "/html/": not_found("html")}
        ),
    )
    assert paper.main(["2605.25998", "--dir", str(tmp_path)]) == 0
    assert not (tmp_path / "2605.25998" / "2605.25998.txt").exists()
    assert "none (no HTML version)" in capsys.readouterr().out


def test_client_does_not_retry_client_errors(monkeypatch) -> None:
    calls = []

    def urlopen(request, timeout):
        calls.append(request.full_url)
        raise not_found(request.full_url)

    monkeypatch.setattr(fetch.urllib.request, "urlopen", urlopen)
    with pytest.raises(urllib.error.HTTPError):
        fetch.RateLimitedClient(delay_s=0).get("https://arxiv.org/html/x")
    assert len(calls) == 1
