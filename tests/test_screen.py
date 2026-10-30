import json

from arxiv_summary_news import screen
from arxiv_summary_news.screen import render_worksheet, screen_preprint
from arxiv_summary_news.topic import load_topic, parse_topic


def preprint(arxiv_id: str, title: str, abstract: str = "") -> dict:
    return {
        "id": arxiv_id,
        "title": title,
        "abstract": abstract,
        "primary_category": "stat.ME",
        "categories": ["stat.ME", "econ.EM"],
    }


TOPIC = parse_topic(
    {
        "title": "causal inference",
        "keywords": ["causal", "treatment effects?", r"\bmediat(ion|or)\b"],
        "false_positives": ["causal attention"],
    },
    "causal",
)


def test_keywords_match_title_and_abstract() -> None:
    s = screen_preprint(
        preprint("1", "Treatment effects", "A causal estimator."), TOPIC
    )
    assert s.terms == ("causal", "treatment effects")


def test_false_positive_phrases_do_not_count() -> None:
    s = screen_preprint(preprint("1", "Sparse causal attention for LLMs"), TOPIC)
    assert s.terms == ()
    assert s.false_positives == ("causal attention",)


def test_real_match_survives_alongside_false_positive() -> None:
    s = screen_preprint(
        preprint("1", "Causal attention", "We estimate a causal effect."), TOPIC
    )
    assert s.terms == ("causal",)


def test_word_boundaries_skip_intermediate() -> None:
    s = screen_preprint(
        preprint("1", "Intermediate states", "mediation analysis"), TOPIC
    )
    assert s.terms == ("mediation",)


def test_worksheet_sections_and_order() -> None:
    screened = [
        screen_preprint(preprint("a", "Unrelated"), TOPIC),
        screen_preprint(preprint("b", "Causal mediation"), TOPIC),
        screen_preprint(preprint("c", "Causal attention"), TOPIC),
        screen_preprint(preprint("d", "Causal treatment effects", "mediation"), TOPIC),
    ]
    text = render_worksheet(screened, TOPIC, "pool.json")
    assert "## Keyword matches (2)" in text
    assert text.index("### d ") < text.index("### b ")  # more terms first
    assert "- c `stat.ME` Causal attention — causal attention" in text
    assert "- a `stat.ME` Unrelated" in text
    assert "`stat.ME` (also econ.EM)" in text


def test_bundled_causal_topic_loads() -> None:
    topic = load_topic("causal")
    assert "stat.ME" in topic.categories
    assert "core" in topic.sections
    s = screen_preprint(
        preprint("1", "A causal language model", "Peer effects in panels."), topic
    )
    assert s.terms == ("peer effects",)


def test_cli_writes_worksheet_and_prints_ids(tmp_path, capsys) -> None:
    pool = tmp_path / "pool_2026-10-14.json"
    pool.write_text(
        json.dumps(
            [preprint("1", "Causal forests", "Abstract ε."), preprint("2", "Other")]
        ),
        encoding="utf-8",
    )
    assert screen.main([str(pool)]) == 0
    assert (tmp_path / "pool_2026-10-14_causal_candidates.md").exists()

    assert screen.main([str(pool), "--ids", "1"]) == 0
    assert "Abstract ε." in capsys.readouterr().out
    assert screen.main([str(pool), "--ids", "1", "missing"]) == 1
