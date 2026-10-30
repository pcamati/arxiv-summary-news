import json

import pytest

from arxiv_summary_news import topic_md
from arxiv_summary_news.topic_md import load_analysis, render_report

SECTIONS = {"core": "Core causal inference", "loose": "Loosely related"}


def entry(arxiv_id: str, relevance: str, **extra: str) -> dict:
    return {
        "id": arxiv_id,
        "title": f"Paper {arxiv_id}",
        "relevance": relevance,
        "reasoning": f"Why {arxiv_id}.",
        **extra,
    }


def test_sections_follow_topic_order_then_others() -> None:
    analysis = {
        "2026-10-14": [entry("1", "loose"), entry("2", "other"), entry("3", "core")]
    }
    text = render_report(analysis, "T", "causal inference", SECTIONS)
    core, loose, other = (
        text.index("## Core causal inference"),
        text.index("## Loosely related"),
        text.index("## Other"),
    )
    assert core < loose < other
    assert "### [3](https://arxiv.org/abs/3) Paper 3\n\nWhy 3." in text


def test_category_from_entry_or_pool() -> None:
    analysis = {
        "d": [entry("1", "core", primary_category="stat.ME"), entry("2", "core")]
    }
    pool = {
        "1": {"id": "1", "primary_category": "math.ST"},
        "2": {"id": "2", "primary_category": "cs.LG"},
        "3": {"id": "3"},
    }
    text = render_report(
        analysis, "T", "causal inference", SECTIONS, pool, "pool.json", ("stat.ME",)
    )
    assert "*stat.ME* — Why 1." in text
    assert "*cs.LG* — Why 2." in text
    assert "2 of 3 preprints in `pool.json`" in text
    assert "Categories searched: `stat.ME`." in text


def test_several_days_get_day_headings() -> None:
    analysis = {"2026-10-13": [entry("1", "core")], "2026-10-14": [entry("2", "core")]}
    text = render_report(analysis, "T", "causal inference", SECTIONS)
    assert "## 2026-10-13" in text
    assert "### Core causal inference" in text
    assert "#### [2](https://arxiv.org/abs/2)" in text


def test_load_analysis_rejects_incomplete_entries(tmp_path) -> None:
    path = tmp_path / "a.json"
    path.write_text(json.dumps({"d": [{"id": "1", "title": "x"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="relevance, reasoning"):
        load_analysis(path)


def test_cli(tmp_path) -> None:
    analysis = tmp_path / "pool_2026-10-14_causal.json"
    analysis.write_text(
        json.dumps({"2026-10-14": [entry("1", "core")]}), encoding="utf-8"
    )
    pool = tmp_path / "pool_2026-10-14.json"
    pool.write_text(
        json.dumps([{"id": "1", "primary_category": "stat.ME"}]), encoding="utf-8"
    )

    assert topic_md.main([str(analysis), "--pool", str(pool), "--topic", "causal"]) == 0
    text = analysis.with_suffix(".md").read_text(encoding="utf-8")
    assert text.startswith("# Causal inference papers, 2026-10-14\n")
    assert "*stat.ME* — Why 1." in text
