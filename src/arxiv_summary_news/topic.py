"""Topic definitions: which categories to fetch and which phrases flag a screening candidate.

A topic is a TOML file. Bundled topics live in this package's ``topics/`` directory and
are loaded by name (``load_topic("causal")``); any other ``.toml`` file can be loaded by path.

Keys:
    title            human-readable name, e.g. "causal inference"
    categories       arXiv categories to fetch
    keywords         regexes (case-insensitive); a match makes a preprint a candidate
    false_positives  regexes removed from the text before keyword matching
    [sections]       relevance label -> report heading, in report order
"""

import re
import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

TOPICS_DIR = "topics"


@dataclass(frozen=True)
class Topic:
    name: str
    title: str
    categories: tuple[str, ...]
    keywords: tuple[re.Pattern[str], ...]
    false_positives: tuple[re.Pattern[str], ...] = ()
    sections: dict[str, str] = field(default_factory=dict)


def available_topics() -> list[str]:
    """Names of the topics bundled with the package."""
    folder = resources.files(__package__) / TOPICS_DIR
    return sorted(
        entry.name.removesuffix(".toml")
        for entry in folder.iterdir()
        if entry.name.endswith(".toml")
    )


def parse_topic(data: dict[str, Any], name: str) -> Topic:
    """Build a Topic from parsed TOML, compiling its regexes."""
    try:
        return Topic(
            name=name,
            title=data.get("title", name),
            categories=tuple(data.get("categories", ())),
            keywords=tuple(re.compile(p, re.IGNORECASE) for p in data["keywords"]),
            false_positives=tuple(
                re.compile(p, re.IGNORECASE) for p in data.get("false_positives", ())
            ),
            sections=dict(data.get("sections", {})),
        )
    except KeyError as exc:
        raise ValueError(f"topic {name!r}: missing key {exc}") from None
    except re.error as exc:
        raise ValueError(f"topic {name!r}: bad regex {exc.pattern!r}: {exc}") from None


def load_topic(name_or_path: str) -> Topic:
    """Load a bundled topic by name, or a topic file by its .toml path."""
    if name_or_path.endswith(".toml"):
        path = Path(name_or_path)
        return parse_topic(tomllib.loads(path.read_text(encoding="utf-8")), path.stem)

    resource = resources.files(__package__) / TOPICS_DIR / f"{name_or_path}.toml"
    if not resource.is_file():
        raise ValueError(
            f"unknown topic {name_or_path!r}; available: {', '.join(available_topics())}"
        )
    return parse_topic(
        tomllib.loads(resource.read_text(encoding="utf-8")), name_or_path
    )
