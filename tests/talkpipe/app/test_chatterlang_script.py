import pytest
import logging
from unittest.mock import patch
from talkpipe.util import config  
from talkpipe.app.chatterlang_script import main


extra_module = """
import logging
import re                                                                                  
from talkpipe.pipe import core                                                             
from talkpipe.chatterlang import registry                                                  
                                                                                           
@registry.register_segment("howdy")                                                      
@core.field_segment()           
def howdy(item):
    return "Howdy, " + item + "!"

@registry.register_segment("countHowdy")
@core.field_segment()
def countHowdy(item):
    return len(re.findall(r'Howdy', item))    

@registry.register_segment("logHowdy")
@core.field_segment()
def logHowdy(item):
    logging.getLogger("sillylog").debug("Howdy, " + item + "!")
    return item
"""

def test_main_with_extra_module(capsys, tmp_path):
    # Create a temporary config file
    config_file = tmp_path / "test_config.py"
    config_file.write_text(extra_module)

    test_script = """INPUT FROM echo[data="4,5,6"] | howdy | print"""
    with patch('argparse.ArgumentParser.parse_known_args') as mock_args:
        mock_namespace = type('MockNamespace', (), {})()
        mock_namespace.script = test_script
        mock_namespace.load_module = [str(config_file)]
        mock_namespace.logger_levels = None
        mock_namespace.logger_files = None
        
        # Return the parsed args and no unknown args
        mock_args.return_value = (mock_namespace, [])
        
        main()
        
        captured = capsys.readouterr()
        assert captured.out == "Howdy, 4!\nHowdy, 5!\nHowdy, 6!\n"


def test_main_with_constant_injection(capsys):
    test_script = """INPUT FROM echo[data=$TEST] | print"""
    
    with patch('argparse.ArgumentParser.parse_known_args') as mock_args:
        # Mock the return value of parse_known_args to simulate --script "INPUT FROM echo[data=TEST] | print" --TEST "hello"
        mock_namespace = type('MockNamespace', (), {})()
        mock_namespace.script = test_script
        mock_namespace.load_module = []
        mock_namespace.logger_levels = None
        mock_namespace.logger_files = None
        
        # Return the parsed args and unknown args (the constant)
        mock_args.return_value = (mock_namespace, ['--TEST', 'hello'])
        
        main()
        
        captured = capsys.readouterr()
        assert captured.out == "hello\n"



