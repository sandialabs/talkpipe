import pytest
import pandas as pd
import json
from pydantic import BaseModel

from talkpipe.pipe import core
from talkpipe.pipe import io
from talkpipe.pipe import basic
from talkpipe.llm import chat
from talkpipe.chatterlang import compiler
from talkpipe import util

### Quick start examples

def test_qs_example_1a(capsys):

    pipeline = compiler.compile('INPUT FROM echo[data="1|2|hello|3", delimiter="|"] | cast[cast_type="int"] | print')
    assert list(pipeline()) == [1, 2, 3]

    capsys.readouterr()

    pipeline = compiler.compile('INPUT FROM echo[data="1|2|hello|3", delimiter="|"] | cast[cast_type="int"] | print')
    pipeline = pipeline.asFunction(single_out=False)

    ans = pipeline()

    captured = capsys.readouterr()
    assert captured.out == "1\n2\n3\n"

    assert ans == [1, 2, 3]

    pipeline = io.echo(data="1|2|hello|3", delimiter="|") | basic.Cast(cast_type="int") | io.Print()
    function = pipeline.asFunction(single_out=False)
    ans = function()
    captured = capsys.readouterr()
    assert captured.out == "1\n2\n3\n"
    assert ans == [1, 2, 3]


def test_qs_example_1b(capsys):
    ssp = compiler.compile("""
    INPUT FROM echo[data="1,2,hello,3"] | cast[cast_type="int"] | @a;
    INPUT FROM @a | print
    """)
    ssp = ssp.asFunction(single_out=False)
    ans = ssp()
    

    captured = capsys.readouterr()
    assert captured.out == "1\n2\n3\n"
    assert ans == [1, 2, 3]

def test_qs_example_1c(capsys):
    ssp = compiler.compile('INPUT FROM echo[data="1,2,hello,3"] | cast[cast_type="int"] | @a; INPUT FROM @a | print')
    ssp = ssp.asFunction(single_out=False)
    ans = ssp() 

    captured = capsys.readouterr()
    assert captured.out == "1\n2\n3\n"
    assert ans == [1, 2, 3]

def test_load_jsonl_example(tmpdir):
    data = [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25},
        {"name": "Charlie", "age": 35}
    ]

    temp_file_path = tmpdir.join("test.jsonl")
    with open(temp_file_path, 'w') as temp_file:
        for entry in data:
            temp_file.write(json.dumps(entry) + '\n')

    ssp = compiler.compile(f'| readJsonl | toDataFrame')
    ssp = ssp.asFunction(single_in=True, single_out=True)
    ans = ssp(temp_file_path)
    assert isinstance(ans, pd.DataFrame)
    assert list(ans.name) == ["Alice", "Bob", "Charlie"]
    assert list(ans.age) == [30, 25, 35]

    pipe = io.readJsonl() | basic.ToDataFrame()
    pipe = pipe.asFunction(single_in=True, single_out=True)
    ans = pipe(temp_file_path)
    assert isinstance(ans, pd.DataFrame)
    assert list(ans.name) == ["Alice", "Bob", "Charlie"]
    assert list(ans.age) == [30, 25, 35]

def test_chat_function_example(requires_ollama):
    
    script = """
    | llmPrompt[name="llama3.2", source="ollama", multi_turn=True]  
    """
    f = compiler.compile(script)
    f = f.asFunction(single_in=True, single_out=True)
    ans = f("Good afternoon.  My name is Bob!")
    assert isinstance(ans, str)
    ans = f("What is my name?")
    assert isinstance(ans, str)
    assert "bob" in ans.lower()
    
    f = chat.LLMPrompt(name="llama3.2", source="ollama", multi_turn=True).asFunction(single_in=True, single_out=True)
    ans = f("Good afternoon.  My name is Bob!")
    assert isinstance(ans, str)
    ans = f("What is my names?")
    assert isinstance(ans, str)
    assert "bob" in ans.lower()

    script = """
    | llmPrompt[name="llama3.2", source="ollama", multi_turn=True, pass_prompts=True] | print | accum[reset=False] 
    """    
    f = compiler.compile(script)
    f = f.asFunction(single_in=True, single_out=False)
    f("Good afternoon.  My name is Bob!")
    result = list(f("What is my name?"))
    assert len(result) == 4
    assert "bob" in result[-1].lower()
    
    f = chat.LLMPrompt(name="llama3.2", source="ollama", multi_turn=True, pass_prompts=True) | io.Print() | compiler.Accum(reset=False)
    f = f.asFunction(single_in=True, single_out=False)
    f("Good afternoon.  My name is Bob!")
    result = list(f("What is my name?"))
    assert len(result) == 4
    assert "bob" in result[-1].lower()
    
def test_a_discussion_example(requires_ollama, capsys):

    script = """
    CONST economist_prompt = "You are an economist debating a proposition.  Reply in one sentence.";
    CONST theologian_prompt="You are a reformed theologian debating a proposition. Reply in one sentence.";
    INPUT FROM echo[data="The US should give free puppies to all children."] | @next_utterance | accum[variable=@conv] | print;
    LOOP 3 TIMES {
        INPUT FROM @next_utterance | llmPrompt[system_prompt=economist_prompt] | @next_utterance | accum[variable=@conv] | print;
        INPUT FROM @next_utterance | llmPrompt[system_prompt=theologian_prompt] | @next_utterance | accum[variable=@conv] | print;
    };
    INPUT FROM @conv 
    """

    f = compiler.compile(script)
    f = f.asFunction(single_out=False)
    result = list(f())
    captured = capsys.readouterr()
    assert len(captured.out.strip().split('\n')) >= 7
    assert len(result) == 7    

class Scorer(BaseModel):
    explanation: str
    score: float


def test_a_crawler_example(requires_ollama):
    data = [
        """{
        "ts_visited": "2024-12-18T01:00:02.585795", 
        "link": "https://en.wikipedia.org/wiki/Dog", 
        "title": "Dog", 
        "description": "Dogs have been bred for desired behaviors, sensory capabilities, and physical attributes. Dog breeds vary widely in shape, size, and color. They have the same number of bones (with the exception of the tail), powerful jaws that house around 42 teeth, and well-developed senses of smell, hearing, and sight. Compared to humans, dogs have an inferior visual acuity, a superior sense of smell, and a relatively large olfactory cortex. They perform many roles for humans, such as hunting, herding, pulling loads, protection, companionship, therapy, aiding disabled people, and assisting police and the military. "
        }""",

        """{
        "ts_visited": "2024-12-18T01:00:03.585795", 
        "link": "https://en.wikipedia.org/wiki/Husky", 
        "title": "Husky", 
        "description": "Husky is a general term for a dog used in the polar regions, primarily and specifically for work as sled dogs. It refers to a traditional northern type, notable for its cold-weather tolerance and overall hardiness.[1][2] Modern racing huskies that maintain arctic breed traits (also known as Alaskan huskies) represent an ever-changing crossbreed of the fastest dogs."
        }""",

        """{
        "ts_visited": "2024-12-18T01:00:04.585795", 
        "link": "https://en.wikipedia.org/wiki/Cat", 
        "title": "Cat", 
        "description": "The cat (Felis catus), also referred to as the domestic cat, is a small domesticated carnivorous mammal. It is the only domesticated species of the family Felidae. Advances in archaeology and genetics have shown that the domestication of the cat occurred in the Near East around 7500 BC. It is commonly kept as a pet and farm cat, but also ranges freely as a feral cat avoiding human contact. Valued by humans for companionship and its ability to kill vermin, the cat's retractable claws are adapted to killing small prey such as mice and rats. It has a strong, flexible body, quick reflexes, and sharp teeth, and its night vision and sense of smell are well developed. It is a social species, but a solitary hunter and a crepuscular predator. Cat communication includes vocalizations—including meowing, purring, trilling, hissing, growling, and grunting—as well as body language. It can hear sounds too faint or too high in frequency for human ears, such as those made by small mammals. It secretes and perceives pheromones. "
        }"""
    ]

    script = """
    CONST explainPrompt = "Explain whether the content of the title and description fields in the following json is related to canines.";
    CONST scorePrompt = "On a scale of 1 to 10, how related to canines is the combination of the content in the title, description, and explanation fields?";
    | loadsJsonl | llmScore[system_prompt=scorePrompt, name="llama3.1", append_as="canine", temperature=0.0] | appendAs[field_list="canine.score:canine_score"] | toDataFrame 
    """

    pipeline = compiler.compile(script).asFunction(single_in=False, single_out=True)
    df = pipeline(data)
    assert isinstance(df, pd.DataFrame) 
    scores = list(df.canine_score)
    assert all([scores[0] > 7, scores[1] > 7, scores[2] < 3])
