"""The tutorial ChatterLang scripts under docs/tutorials must keep compiling,
and the ones that need no LLM must keep running end to end."""

import json
import re
import shutil
from pathlib import Path

import pytest

from talkpipe.chatterlang import compiler
from talkpipe.util.config import load_module_file

TUTORIALS = Path(__file__).resolve().parent.parent / "docs" / "tutorials"
SCRIPTS = sorted(TUTORIALS.rglob("*.script"))
TUTORIAL_1 = TUTORIALS / "Tutorial_1-Document_Indexing"


def _extras_for(script: Path) -> list[Path]:
    """Modules the tutorial's shell runner loads with ``--load-module``."""
    runner = script.with_suffix(".sh")
    if not runner.exists():
        return []
    return [
        script.parent / name
        for name in re.findall(r"--load-module\s+(\S+)", runner.read_text())
    ]


@pytest.mark.skipif(not SCRIPTS, reason="tutorials not present")
@pytest.mark.parametrize(
    "script", SCRIPTS, ids=[str(s.relative_to(TUTORIALS)) for s in SCRIPTS]
)
def test_tutorial_script_compiles(script: Path) -> None:
    for extra in _extras_for(script):
        load_module_file(str(extra), fail_on_missing=True)
    compiler.compile(script.read_text())


@pytest.mark.skipif(not TUTORIAL_1.exists(), reason="tutorial 1 not present")
def test_tutorial_1_index_and_search_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Steps 2 and 3 of tutorial 1 use only the committed stories.json and Whoosh."""
    work = tmp_path / "t1"
    shutil.copytree(TUTORIAL_1, work)
    monkeypatch.chdir(work)

    stories = [
        json.loads(line)
        for line in (work / "stories.json").read_text().splitlines()
        if line.strip()
    ]
    assert stories, "stories.json should contain the pre-generated stories"

    index = compiler.compile((work / "Step_2_IndexStories.script").read_text())
    list(index())
    assert (work / "full_text_index").is_dir()

    search = compiler.compile((work / "Step_3_SearchStories.script").read_text())
    word = next(w for w in stories[0]["title"].split() if len(w) > 4)
    results = list(search([{"query": word}]))
    assert results
    assert any("Title:" in str(r) for r in results)
