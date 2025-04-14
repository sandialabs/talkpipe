import json, pickle, os
from talkpipe.pipe import io
from talkpipe.util import config
from talkpipe.chatterlang import compiler

def test_echo_operation():
    f = compiler.compile('INPUT FROM echo[data="howdy|do", delimiter="|"]').asFunction(single_in=True, single_out=False)
    ans = f(None)
    assert ans == ["howdy", "do"]

    f = compiler.compile('INPUT FROM echo[data="howdy,do"]').asFunction(single_in=True, single_out=False)
    ans = f(None)
    assert ans == ["howdy", "do"]

    f = io.echo(data="howdy|do", delimiter='|')
    ans = list(f())
    assert ans == ["howdy", "do"]

def test_readJSONL(tmpdir):
    data = [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25},
        {"name": "Charlie", "age": 35}
    ]

    temp_file_path = tmpdir.join("test.jsonl")
    with open(temp_file_path, 'w') as temp_file:
        for entry in data:
            temp_file.write(json.dumps(entry) + '\n')

    f = io.readJsonl()
    ans = list(f([temp_file_path]))
    assert ans == data

def test_dumpsJsonl():
    data = [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25},
        {"name": "Charlie", "age": 35}
    ]

    f = io.dumpsJsonl()
    ans = list(f(data))
    assert ans == [json.dumps(entry) for entry in data]

def test_writePickle(tmpdir):
    data = [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25},
        {"name": "Charlie", "age": 35}
    ]

    temp_file_path = tmpdir.join("test.pickle")
    f = io.writePickle(fname=str(temp_file_path)).asFunction(single_in=False, single_out=True)
    ans = f(data)
    assert ans == data
    with open(temp_file_path, 'rb') as f:
        ans = pickle.load(f)
        assert ans == data

    temp_file_path2 = tmpdir.join("test2.pickle")
    f = compiler.compile('| writePickle[fname="'+str(temp_file_path2)+'"]')
    f = f.asFunction(single_in=False, single_out=True)
    ans = f(data)
    assert ans == data
    with open(tmpdir.join("test2.pickle"), 'rb') as f:
        ans = pickle.load(f)
        assert ans == data

    f = compiler.compile('| firstN | writePickle[fname="'+str(temp_file_path2)+'"]').asFunction()
    f(data)
    with open(tmpdir.join("test2.pickle"), 'rb') as f:
        ans = pickle.load(f)
        assert ans == [data[0]]

    f = compiler.compile('| firstN | writePickle[fname="'+str(temp_file_path2)+'", first_only=True]').asFunction()
    f(data)
    with open(tmpdir.join("test2.pickle"), 'rb') as f:
        ans = pickle.load(f)
        assert ans == data[0]
        
def test_print(capsys):
    f = io.Print()
    ans = list(f(["howdy", "do"]))
    assert ans == ["howdy", "do"]
    captured = capsys.readouterr()
    assert captured.out == "howdy\ndo\n"
    
    f = io.Print(field_list="age")
    ans = list(f([{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]))
    assert ans == [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
    captured = capsys.readouterr()
    assert captured.out == "{'age': 30}\n{'age': 25}\n"

def test_log(capsys, tmpdir):

    config.configure_logger("test.log:INFO")
    f = io.Log(level="DEBUG", log_name="test.log")
    ans = list(f(["howdy", "do"]))
    assert ans == ["howdy", "do"]
    captured = capsys.readouterr()
    assert "howdy" not in captured.out 
    assert "do" not in captured.out

    config.configure_logger("test.log:DEBUG")
    f = io.Log(level="DEBUG", log_name="test.log")
    ans = list(f(["howdy", "do"]))
    assert ans == ["howdy", "do"]
    captured = capsys.readouterr()
    assert "howdy" in captured.err 
    assert "do" in captured.err

    config.configure_logger("test.log:DEBUG", logger_files=f"test.log:{os.path.join(str(tmpdir), 'test.log')}")
    f = io.Log(level="DEBUG", log_name="test.log")
    ans = list(f(["howdy", "do"]))
    assert ans == ["howdy", "do"]
    captured = capsys.readouterr()
    assert "howdy" in captured.err 
    assert "do" in captured.err
    with open(os.path.join(str(tmpdir), 'test.log'), 'r') as f:
        assert "howdy" in f.readline()
        assert "do" in f.readline()

