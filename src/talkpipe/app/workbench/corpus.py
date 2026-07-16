"""Co-occurrence mining over ChatterLang scripts for workbench suggestions.

Builds simple statistical tables from a corpus of scripts (built-in examples,
shipped seed scripts, and the user's saved pipelines):

- ``starts``:  how often each component opens a pipeline
- ``bigrams``: for each component, how often each other component follows it

Scripts are parsed with the real ChatterLang parser when possible; broken or
in-progress scripts fall back to a regex scan so the user's own drafts still
contribute signal.
"""

import logging
import re
from pathlib import Path
from typing import Dict, Iterable, List

from parsy import ParseError

from talkpipe.chatterlang.compiler import remove_comments
from talkpipe.chatterlang.parsers import (
    ForkNode,
    ParsedLoop,
    ParsedPipeline,
    SegmentNode,
    script_parser,
)

logger = logging.getLogger(__name__)

SEED_SCRIPTS_DIR = Path(__file__).parent.parent / "workbench_data" / "seed_scripts"

_KEYWORDS = {"INPUT", "FROM", "NEW", "CONST", "SET", "LOOP", "TIMES", "True", "False"}


def _chains_from_parsed(parsed) -> List[List[str]]:
    """Ordered component-name chains, one per pipeline (loops flattened)."""
    chains = []

    def walk_pipeline(pipeline):
        if isinstance(pipeline, ParsedLoop):
            for inner in pipeline.pipelines:
                walk_pipeline(inner)
            return
        if not isinstance(pipeline, ParsedPipeline):
            return
        chain = []
        node = pipeline.input_node
        if node is not None and not isinstance(node.source, str) and not node.is_variable:
            chain.append(node.source.name)
        for transform in pipeline.transforms:
            if isinstance(transform, SegmentNode):
                chain.append(transform.operation.name)
            elif isinstance(transform, ForkNode):
                for branch in transform.branches:
                    if isinstance(branch, (ParsedPipeline, ParsedLoop)):
                        walk_pipeline(branch)
            # VariableName nodes are skipped but keep chain continuity:
            # `a | @x | b` still records the (a, b) adjacency.
        if chain:
            chains.append(chain)

    for pipeline in parsed.pipelines:
        walk_pipeline(pipeline)
    return chains


def _chains_from_regex(script: str) -> List[List[str]]:
    """Crude fallback for scripts the parser rejects."""
    chains = []
    text = remove_comments(script)
    text = re.sub(r'"(?:[^"\\]|\\.)*"', '""', text)  # drop string contents
    for statement in text.split(";"):
        chain = []
        for stage in statement.split("|"):
            match = re.search(r"\b(?!INPUT\b|FROM\b|NEW\b|LOOP\b)([A-Za-z_]\w*)", stage)
            if match and match.group(1) not in _KEYWORDS:
                chain.append(match.group(1))
        if len(chain) > 1 or (chain and "|" in statement):
            chains.append(chain)
    return chains


def mine_script(script: str) -> List[List[str]]:
    """Component-name chains for one script (parser first, regex fallback)."""
    if not script or not script.strip():
        return []
    try:
        parsed = script_parser.parse(remove_comments(script))
        return _chains_from_parsed(parsed)
    except ParseError:
        return _chains_from_regex(script)
    except Exception:  # pragma: no cover - any parser hiccup falls back too
        return _chains_from_regex(script)


def build_tables(weighted_scripts: Iterable[tuple]) -> Dict:
    """Aggregate (script_text, weight) pairs into suggestion tables."""
    starts: Dict[str, int] = {}
    bigrams: Dict[str, Dict[str, int]] = {}
    mined = 0
    for script, weight in weighted_scripts:
        chains = mine_script(script)
        if chains:
            mined += 1
        for chain in chains:
            starts[chain[0]] = starts.get(chain[0], 0) + weight
            for prev, nxt in zip(chain, chain[1:]):
                bigrams.setdefault(prev, {})[nxt] = bigrams.get(prev, {}).get(nxt, 0) + weight
    return {"starts": starts, "bigrams": bigrams, "scripts_mined": mined}


def _example_scripts() -> List[str]:
    # Imported lazily: chatterlang_workbench imports this package at load time.
    from talkpipe.app.chatterlang_workbench import EXAMPLE_SCRIPTS
    return [
        example["code"]
        for examples in EXAMPLE_SCRIPTS.values()
        for example in examples
    ]


def _seed_scripts() -> List[str]:
    if not SEED_SCRIPTS_DIR.is_dir():
        return []
    return [path.read_text(encoding="utf-8")
            for path in sorted(SEED_SCRIPTS_DIR.glob("*.script"))]


def build_corpus_tables(workspace_scripts: List[str],
                        workspace_weight: int = 3) -> Dict:
    """The full suggestion tables: examples + seed scripts + user pipelines.

    The user's own pipelines are weighted higher so their habits dominate
    the built-in corpus.
    """
    weighted = [(script, 1) for script in _example_scripts()]
    weighted += [(script, 1) for script in _seed_scripts()]
    weighted += [(script, workspace_weight) for script in workspace_scripts]
    return build_tables(weighted)
