"""Tests for the workbench suggestion corpus mining."""

from talkpipe.app.workbench import corpus


def test_mine_simple_pipeline():
    chains = corpus.mine_script('INPUT FROM echo[data="hi"] | cast[cast_type="int"] | print')
    assert chains == [["echo", "cast", "print"]]


def test_mine_multiple_pipelines():
    chains = corpus.mine_script(
        'INPUT FROM echo[data="1"] | @x; INPUT FROM @x | print'
    )
    # @x is a variable, not a component: first chain is just echo, second just print.
    assert ["echo"] in chains
    assert ["print"] in chains


def test_variable_transparency_within_pipeline():
    chains = corpus.mine_script('INPUT FROM echo[data="1"] | @x | print')
    assert chains == [["echo", "print"]]


def test_mine_loop_bodies():
    script = (
        'INPUT FROM range[lower=0, upper=5] | @data;\n'
        'LOOP 3 TIMES { INPUT FROM @data | scale[multiplier=2] | @data };\n'
        'INPUT FROM @data | print'
    )
    chains = corpus.mine_script(script)
    assert ["range"] in chains
    assert ["scale"] in chains
    assert ["print"] in chains


def test_mine_broken_script_regex_fallback():
    # Unquoted string value: the parser rejects this, the regex scan doesn't.
    chains = corpus.mine_script("| llmPrompt[model=llama3.2] | print")
    assert any("llmPrompt" in chain and "print" in chain for chain in chains)


def test_mine_empty():
    assert corpus.mine_script("") == []
    assert corpus.mine_script("# only a comment") == []


def test_build_tables_counts_and_weights():
    tables = corpus.build_tables([
        ("INPUT FROM echo | print", 1),
        ("INPUT FROM echo | print", 1),
        ('INPUT FROM echo | llmPrompt[system_prompt="x"]', 3),
    ])
    assert tables["starts"]["echo"] == 5
    assert tables["bigrams"]["echo"]["print"] == 2
    assert tables["bigrams"]["echo"]["llmPrompt"] == 3


def test_corpus_tables_include_examples_and_seeds(tmp_path):
    tables = corpus.build_corpus_tables([])
    # From EXAMPLE_SCRIPTS ("Web Page Summarizer") and tutorials.
    assert tables["bigrams"].get("downloadURL", {}).get("htmlToText")
    assert tables["scripts_mined"] > 5


def test_corpus_tables_weight_workspace_scripts():
    with_user = corpus.build_corpus_tables(["INPUT FROM echo | firstN[n=1]"])
    without_user = corpus.build_corpus_tables([])
    gained = (with_user["bigrams"]["echo"].get("firstN", 0)
              - without_user["bigrams"].get("echo", {}).get("firstN", 0))
    assert gained == 3  # default workspace weight
