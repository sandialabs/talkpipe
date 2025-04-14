import pytest
import logging
from unittest.mock import patch
from talkpipe.util import config  
from talkpipe.app.runscript import main

def test_main_with_env_var(capsys):  # Add capsys fixture here
    test_script = """INPUT FROM echo[data="1,2,3"] | print"""

    with patch('os.environ', {'TEST_VAR': test_script}):
        with patch('argparse.ArgumentParser.parse_args') as mock_args:
            mock_args.return_value.env = 'TEST_VAR'
            mock_args.return_value.config = None
            mock_args.return_value.script = None
            
            main()
            
            # Capture the output
            captured = capsys.readouterr()
            # captured.out contains stdout
            # captured.err contains stderr
            
            # Add your assertions here, for example:
            assert captured.out == "1\n2\n3\n"  # Adjust expected output as needed

config_script = """
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

def test_main_with_config_file(capsys, tmp_path):
    # Create a temporary config file
    config_file = tmp_path / "test_config.py"
    config_file.write_text(config_script)

    test_script = """INPUT FROM echo[data="4,5,6"] | howdy | print"""
    with patch('os.environ', {'TEST_VAR': test_script}):
        with patch('argparse.ArgumentParser.parse_args') as mock_args:
            mock_args.return_value.env = 'TEST_VAR'
            mock_args.return_value.load_module = [str(config_file)]
            mock_args.return_value.script = None
            
            main()
            
            captured = capsys.readouterr()
            assert captured.out == "Howdy, 4!\nHowdy, 5!\nHowdy, 6!\n"

    test_script2 = """INPUT FROM echo[data="Howdy, Howdy, Howdy"] | countHowdy | print"""
    with patch('os.environ', {'TEST_VAR': test_script2}):
        with patch('argparse.ArgumentParser.parse_args') as mock_args:
            mock_args.return_value.env = 'TEST_VAR'
            mock_args.return_value.load_module = [str(config_file)]
            mock_args.return_value.script = None
            
            main()
            
            captured = capsys.readouterr()
            assert captured.out == "1\n1\n1\n"

def test_main_with_exceptions(capsys, tmp_path):
    # Run with no parameters
    with patch('argparse.ArgumentParser.parse_args') as mock_args:
        mock_args.return_value.env = None
        mock_args.return_value.load_module = None
        mock_args.return_value.script = None
        
        with pytest.raises(SystemExit):
            main()
        
        captured = capsys.readouterr()
        assert "Either --script argument or --env" in captured.err

    # Run with env specified but not existin
    with patch('argparse.ArgumentParser.parse_args') as mock_args:
        mock_args.return_value.env = 'NON_EXISTING_ENV_VAR'
        mock_args.return_value.load_module = None
        mock_args.return_value.script = None
        
        with pytest.raises(ValueError):
            main()
        
        captured = capsys.readouterr()
        assert "Environment variable NON_EXISTING_ENV_VAR not found" in captured.err

def test_main_with_script_option(capsys, tmp_path):
    # Create a temporary config file
    config_file = tmp_path / "test_config.py"
    config_file.write_text(config_script)

    test_script = """INPUT FROM echo[data="4,5,6"] | howdy | print"""
    with patch('argparse.ArgumentParser.parse_args') as mock_args:
        mock_args.return_value.env = None
        mock_args.return_value.load_module = [str(config_file)]
        mock_args.return_value.script = test_script
        
        main()
        
        captured = capsys.readouterr()
        assert captured.out == "Howdy, 4!\nHowdy, 5!\nHowdy, 6!\n"

def reset_logging():
    # Get the root logger
    root_logger = logging.getLogger()
    
    # Remove all handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()
    
    # Reset root logger level to default (WARNING)
    root_logger.setLevel(logging.WARNING)
    
    # Clear the logger configuration (for non-root loggers, if needed)
    logging.Logger.manager.loggerDict.clear()


def test_logging_levels(capsys, tmp_path):
    # Create a temporary config file
    config_file = tmp_path / "test_config.py"
    config_file.write_text(config_script)

    test_script = """INPUT FROM echo[data="4,5,6"] | logHowdy | print"""
    with patch('os.environ', {'TEST_VAR': test_script}):
        with patch('argparse.ArgumentParser.parse_args') as mock_args:
            mock_args.return_value.env = 'TEST_VAR'
            mock_args.return_value.load_module = [str(config_file)]
            mock_args.return_value.script = None
            mock_args.return_value.logger_levels = "sillylog:DEBUG"
            
            main()
            
            captured = capsys.readouterr()
            assert captured.out == "4\n5\n6\n"
            assert "DEBUG:sillylog:Howdy, 4!" in captured.err
            assert "DEBUG:sillylog:Howdy, 5!" in captured.err
            assert "DEBUG:sillylog:Howdy, 6!" in captured.err

    reset_logging()

    with patch('os.environ', {'TEST_VAR': test_script}):
        with patch('argparse.ArgumentParser.parse_args') as mock_args:
            mock_args.return_value.env = 'TEST_VAR'
            mock_args.return_value.load_module = [str(config_file)]
            mock_args.return_value.script = None
            mock_args.return_value.logger_levels = "root:DEBUG"
            
            main()
            
            captured = capsys.readouterr()
            assert captured.out == "4\n5\n6\n"
            assert "DEBUG:sillylog:Howdy, 4!" in captured.err
            assert "DEBUG:sillylog:Howdy, 5!" in captured.err
            assert "DEBUG:sillylog:Howdy, 6!" in captured.err

    reset_logging()

    with patch('os.environ', {'TEST_VAR': test_script}):
        with patch('argparse.ArgumentParser.parse_args') as mock_args:
            mock_args.return_value.env = 'TEST_VAR'
            mock_args.return_value.load_module = [str(config_file)]
            mock_args.return_value.script = None
            mock_args.return_value.logger_levels = None
            
            main()
            
            captured = capsys.readouterr()
            assert captured.out == "4\n5\n6\n"
            assert "DEBUG:sillylog:Howdy, 4!" not in captured.err
            assert "DEBUG:sillylog:Howdy, 5!" not in captured.err
            assert "DEBUG:sillylog:Howdy, 6!" not in captured.err

    reset_logging()
    config.reset_config()

    with patch('os.environ', {'TEST_VAR': test_script, 'TALKPIPE_logger_levels': 'sillylog:DEBUG'}):
        with patch('argparse.ArgumentParser.parse_args') as mock_args:
            mock_args.return_value.env = 'TEST_VAR'
            mock_args.return_value.load_module = [str(config_file)]
            mock_args.return_value.script = None
            mock_args.return_value.logger_levels = None
            
            main()
            
            captured = capsys.readouterr()
            assert captured.out == "4\n5\n6\n"
            assert "DEBUG:sillylog:Howdy, 4!" in captured.err
            assert "DEBUG:sillylog:Howdy, 5!" in captured.err
            assert "DEBUG:sillylog:Howdy, 6!" in captured.err


    config.reset_config()
    reset_logging()

    with patch('os.environ', {'TEST_VAR': test_script, 'TALKPIPE_logger_levels': 'sillylog:DEBUG'}):
        with patch('argparse.ArgumentParser.parse_args') as mock_args:
            mock_args.return_value.env = 'TEST_VAR'
            mock_args.return_value.load_module = [str(config_file)]
            mock_args.return_value.script = None
            mock_args.return_value.logger = None
            mock_args.return_value.logger_levels = None
            mock_args.return_value.logger_files = "sillylog:"+str(tmp_path / "sillylog:log.txt")
            
            main()
            
            captured = capsys.readouterr()
            assert captured.out == "4\n5\n6\n"
            assert "DEBUG:sillylog:Howdy, 4!" in captured.err
            assert "DEBUG:sillylog:Howdy, 5!" in captured.err
            assert "DEBUG:sillylog:Howdy, 6!" in captured.err

            with open(tmp_path / "sillylog:log.txt") as file:
                log_content = file.read()
                assert "DEBUG:sillylog:Howdy, 4!" in log_content
                assert "DEBUG:sillylog:Howdy, 5!" in log_content
                assert "DEBUG:sillylog:Howdy, 6!" in log_content
