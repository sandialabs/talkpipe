import pytest
from unittest.mock import patch, MagicMock
import requests
import urllib.error
from urllib.robotparser import RobotFileParser
from talkpipe.data import html
from testutils import mock_requests_get_completion

def test_htmlToText():
    html_content = """
    <html>
        <head>
            <title>Test HTML</title>
        </head>
        <body>
            <p>This is a test of the HTML extraction function.</p>
            <p>It should return a string with basic formatting preserved.</p>
            <p>It should also remove any HTML tags.</p>
        </body>
    </html>
    """
    extracted = html.htmlToText(html_content, cleanText=False)
    assert extracted == "Test HTML\nThis is a test of the HTML extraction function.\nIt should return a string with basic formatting preserved.\nIt should also remove any HTML tags."

    extracted = html.htmlToText(html_content)
    assert extracted == "This is a test of the HTML extraction function.\nIt should return a string with basic formatting preserved.\nIt should also remove any HTML tags."

def test_htmlToText_edge_cases(caplog):
    # Test when html is None
    extracted = html.htmlToText(None)
    assert extracted == ""
    assert "No HTML content" in caplog.text
    caplog.clear()
    
    # Test with empty string
    extracted = html.htmlToText("")
    assert extracted == ""
    assert "empty html content" in caplog.text.lower()
    caplog.clear()
    
    # Test with whitespace-only string
    extracted = html.htmlToText("  \n\t  ")
    assert extracted == ""
    assert "whitespace" in caplog.text.lower() or "empty" in caplog.text.lower()
    caplog.clear()
    
    # Test with None and cleanText=False
    extracted = html.htmlToText(None, cleanText=False)
    assert extracted == ""
    assert "No HTML content" in caplog.text
    caplog.clear()
    
    # Test with empty string and cleanText=False
    extracted = html.htmlToText("", cleanText=False)
    assert extracted == ""
    assert "empty html content" in caplog.text.lower()

def test_htmlToTextSegment():
    html_content = [
        {"content": """
        <html>
            <head>
                <title>Test HTML</title>
            </head>
            <body>
                <p>This is a test of the HTML extraction function.</p>
                <p>It should return a string with basic formatting preserved.</p>
                <p>It should also remove any HTML tags.</p>
            </body>
        </html>
        """},
        {"content": """
        <html>
            <head>
                <title>Test HTML</title>
            </head>
            <body>
                <p>This is a test of the HTML extraction function.</p>
                <p>It should return a string with basic formatting preserved.</p>
                <p>It should also remove any HTML tags.</p>
            </body>
        </html>
        """},
    ]
    segment = html.htmlToTextSegment(field="content", cleanText=False)
    extracted = list(segment(html_content))
    assert extracted == [
        "Test HTML\nThis is a test of the HTML extraction function.\nIt should return a string with basic formatting preserved.\nIt should also remove any HTML tags.",
        "Test HTML\nThis is a test of the HTML extraction function.\nIt should return a string with basic formatting preserved.\nIt should also remove any HTML tags."
    ]

    segment = html.htmlToTextSegment(field="content", cleanText=True)
    extracted = list(segment(html_content))
    assert extracted == [
        "This is a test of the HTML extraction function.\nIt should return a string with basic formatting preserved.\nIt should also remove any HTML tags.",
        "This is a test of the HTML extraction function.\nIt should return a string with basic formatting preserved.\nIt should also remove any HTML tags."
    ]

@pytest.fixture(autouse=True)
def clear_robot_parser_cache():
    """Clear the robot parser cache before each test."""
    html.get_robot_parser.cache_clear()
    yield

def test_get_robot_parser_exceptions():
    """Test exception handling in get_robot_parser function."""
    # Test case 1: URLError when fetching robots.txt
    with patch('urllib.request.urlopen') as mock_urlopen:
        # Set up the mock to raise URLError
        mock_urlopen.side_effect = urllib.error.URLError("URL Error")
        # Call the function - should return None when URLError occurs
        result = html.get_robot_parser("https://example.com")
        assert result is None
    
    html.get_robot_parser.cache_clear()

    # Test case 2: ConnectionError when fetching robots.txt
    with patch('urllib.request.urlopen') as mock_urlopen:
        # Set up the mock to raise ConnectionError
        mock_urlopen.side_effect = ConnectionError("Connection Error")
        # Call the function - should return None when ConnectionError occurs
        result = html.get_robot_parser("https://example.com")
        assert result is None
    
    html.get_robot_parser.cache_clear()

    # Test case 3: TimeoutError when fetching robots.txt
    with patch('urllib.request.urlopen') as mock_urlopen:
        # Set up the mock to raise TimeoutError
        mock_urlopen.side_effect = TimeoutError("Timeout Error")
        # Call the function - should return None when TimeoutError occurs
        result = html.get_robot_parser("https://example.com")
        assert result is None
    
    html.get_robot_parser.cache_clear()

    # Test case 4: Successful fetch but robots.txt parsing fails
    mock_response = MagicMock()
    mock_response.read.return_value = b"Invalid robots.txt content"
    mock_response.__enter__.return_value = mock_response
    with patch('urllib.request.urlopen', return_value=mock_response):
        with patch.object(RobotFileParser, 'parse', side_effect=Exception("Parse error")):
            # Even with a parse error, the function should finish and return the RobotFileParser
            result = html.get_robot_parser("https://example.com")
            assert isinstance(result, RobotFileParser)
    
    html.get_robot_parser.cache_clear()

    # Test case 5: Successful fetch and parse
    mock_response = MagicMock()
    mock_response.read.return_value = b"User-agent: *\nDisallow: /private/"
    mock_response.__enter__.return_value = mock_response
    with patch('urllib.request.urlopen', return_value=mock_response):
        # Function should return a configured RobotFileParser
        result = html.get_robot_parser("https://example.com")
        assert isinstance(result, RobotFileParser)

def test_downloadURL_exceptions():
    """Test exception handling in downloadURL function."""
    
    # Test case 1: URL disallowed by robots.txt
    with patch('talkpipe.data.html.can_fetch', return_value=False):
        # With fail_on_error=True, should raise PermissionError
        with pytest.raises(PermissionError):
            html.downloadURL("https://example.com/disallowed", fail_on_error=True)
        
        # With fail_on_error=False, should return None
        result = html.downloadURL("https://example.com/disallowed", fail_on_error=False)
        assert result is None

    # Test case 2: Non-200 HTTP status code
    mock_response = MagicMock()
    mock_response.status_code = 404
    
    with patch('talkpipe.data.html.can_fetch', return_value=True):
        with patch('requests.get', return_value=mock_response):
            # With fail_on_error=True, should raise ValueError
            with pytest.raises(ValueError):
                html.downloadURL("https://example.com/not-found", fail_on_error=True)
            
            # With fail_on_error=False, should return None
            result = html.downloadURL("https://example.com/not-found", fail_on_error=False)
            assert result is None

    # Test case 3: Request throws an exception
    with patch('talkpipe.data.html.can_fetch', return_value=True):
        with patch('requests.get', side_effect=requests.RequestException("Connection error")):
            # With fail_on_error=True, should raise Exception
            with pytest.raises(Exception):
                html.downloadURL("https://example.com/error", fail_on_error=True)
            
            # With fail_on_error=False, should return None
            result = html.downloadURL("https://example.com/error", fail_on_error=False)
            assert result is None
            
    # Test case 4: Timeout exception
    with patch('talkpipe.data.html.can_fetch', return_value=True):
        with patch('requests.get', side_effect=requests.Timeout("Request timed out")):
            # With fail_on_error=True, should raise Exception
            with pytest.raises(Exception):
                html.downloadURL("https://example.com/timeout", fail_on_error=True, timeout=1)
            
            # With fail_on_error=False, should return None
            result = html.downloadURL("https://example.com/timeout", fail_on_error=False, timeout=1)
            assert result is None

def test_downloadURL(mock_requests_get_completion):


    f = html.downloadURLSegment()
    f = f.asFunction(single_in=True, single_out=True)
    ans = f("http://www.example.com")
    assert ans is not None
    assert len(ans) > 0
    assert "example" in ans

    f = html.downloadURLSegment(field="content")
    f = f.asFunction(single_in=True, single_out=True)
    ans = f({"content": "http://www.example.com"})
    assert ans is not None
    assert len(ans) > 0
    assert "example" in ans

    f = html.downloadURLSegment(field="content", append_as="text")
    f = f.asFunction(single_in=True, single_out=True)
    ans = f({"content": "http://www.example.com"})
    assert "text" in ans
    assert ans["text"] is not None
    assert len(ans["text"]) > 0
    assert "<title>Mocked" in ans["text"]

