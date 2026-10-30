from datetime import date

import pytest

from arxiv_summary_news import fetch
from arxiv_summary_news.fetch import build_search_query, parse_args


def test_query_single_category() -> None:
    assert build_search_query(categories=["stat.ME"]) == "cat:stat.ME"


def test_query_several_categories_are_ored() -> None:
    query = build_search_query(
        '"causal effect"',
        ["stat.ME", "econ.EM"],
        date(2026, 10, 14),
        date(2026, 10, 14),
    )
    assert query == (
        'all:("causal effect") AND (cat:stat.ME OR cat:econ.EM) '
        "AND submittedDate:[202610140000 TO 202610142359]"
    )


def test_query_needs_something() -> None:
    with pytest.raises(ValueError):
        build_search_query()


def test_topic_categories_are_merged_without_duplicates() -> None:
    args = parse_args(["-c", "quant-ph", "stat.ME", "--topic", "causal"])
    assert args.categories[:2] == ["quant-ph", "stat.ME"]
    assert args.categories.count("stat.ME") == 1
    assert "econ.EM" in args.categories


def test_unknown_topic_is_a_usage_error() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--topic", "no-such-topic"])


def test_empty_result_writes_nothing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(fetch, "fetch_all", lambda *args: iter(()))
    output = tmp_path / "pool.json"
    code = fetch.main(
        [
            "-c",
            "stat.ME",
            "--from",
            "2026-10-15",
            "--to",
            "2026-10-15",
            "-o",
            str(output),
        ]
    )
    assert code == fetch.EXIT_NO_RESULTS
    assert not output.exists()


def _failing_fetch(exc: BaseException):
    def fetch_all(*args):
        yield {"id": "2610.00001", "title": "Fetched before the failure"}
        raise exc

    return fetch_all


@pytest.mark.parametrize(
    ("exc", "expected_code"),
    [
        (TimeoutError("timed out"), 1),
        (KeyboardInterrupt(), fetch.EXIT_INTERRUPTED),
    ],
)
def test_incomplete_fetch_keeps_existing_output(
    tmp_path, monkeypatch, exc, expected_code
) -> None:
    monkeypatch.setattr(fetch, "fetch_all", _failing_fetch(exc))
    output = tmp_path / "pool.json"
    output.write_text("[]", encoding="utf-8")
    code = fetch.main(["-c", "stat.ME", "-o", str(output)])
    assert code == expected_code
    assert output.read_text(encoding="utf-8") == "[]"
    partial = fetch.partial_path(output)
    assert partial.name == "pool.partial.json"
    assert '"2610.00001"' in partial.read_text(encoding="utf-8")


def test_interrupt_before_any_result_is_not_no_results(tmp_path, monkeypatch) -> None:
    def fetch_all(*args):
        raise KeyboardInterrupt
        yield

    monkeypatch.setattr(fetch, "fetch_all", fetch_all)
    output = tmp_path / "pool.json"
    code = fetch.main(["-c", "stat.ME", "-o", str(output)])
    assert code == fetch.EXIT_INTERRUPTED
    assert not output.exists()
    assert not fetch.partial_path(output).exists()
