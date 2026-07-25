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
    # Test case 1: RequestException when fetching robots.txt
    with patch('requests.get') as mock_requests_get:
        # Set up the mock to raise RequestException
        mock_requests_get.side_effect = requests.exceptions.RequestException("Request Error")
        # Call the function - should return None when RequestException occurs
        result = html.get_robot_parser("https://example.com")
        assert result is None
    
    html.get_robot_parser.cache_clear()

    # Test case 2: ConnectionError when fetching robots.txt
    with patch('requests.get') as mock_requests_get:
        # Set up the mock to raise ConnectionError
        mock_requests_get.side_effect = ConnectionError("Connection Error")
        # Call the function - should return None when ConnectionError occurs
        result = html.get_robot_parser("https://example.com")
        assert result is None
    
    html.get_robot_parser.cache_clear()

    # Test case 3: TimeoutError when fetching robots.txt
    with patch('requests.get') as mock_requests_get:
        # Set up the mock to raise TimeoutError
        mock_requests_get.side_effect = requests.exceptions.Timeout("Timeout Error")
        # Call the function - should return None when TimeoutError occurs
        result = html.get_robot_parser("https://example.com")
        assert result is None
    
    html.get_robot_parser.cache_clear()

    # Test case 4: Successful fetch but robots.txt parsing fails
    mock_response = MagicMock()
    mock_response.content = b"Invalid robots.txt content"
    mock_response.raise_for_status.return_value = None  # No HTTP error
    with patch('requests.get', return_value=mock_response):
        with patch.object(RobotFileParser, 'parse', side_effect=Exception("Parse error")):
            # Even with a parse error, the function should finish and return the RobotFileParser
            result = html.get_robot_parser("https://example.com")
            assert isinstance(result, RobotFileParser)
    
    html.get_robot_parser.cache_clear()

    # Test case 5: Successful fetch and parse
    mock_response = MagicMock()
    mock_response.content = b"User-agent: *\nDisallow: /private/"
    mock_response.raise_for_status.return_value = None  # No HTTP error
    with patch('requests.get', return_value=mock_response):
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
            
    # Test case 4: Timeout exception (retried, then raised once retries are exhausted)
    with patch('talkpipe.data.html.can_fetch', return_value=True):
        with patch('talkpipe.data.html.time.sleep'):
            with patch('requests.get', side_effect=requests.Timeout("Request timed out")):
                # With fail_on_error=True, should raise Exception
                with pytest.raises(Exception):
                    html.downloadURL("https://example.com/timeout", fail_on_error=True, timeout=1)

                # With fail_on_error=False, should return None
                result = html.downloadURL("https://example.com/timeout", fail_on_error=False, timeout=1)
                assert result is None


def _mock_response(status_code=200, text="<html>ok</html>", headers=None,
                   encoding="utf-8", apparent_encoding="utf-8"):
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    response.headers = headers if headers is not None else {}
    response.encoding = encoding
    response.apparent_encoding = apparent_encoding
    return response


def test_downloadURL_retries_transient_connection_error():
    """A connection error is retried and the download succeeds on a later attempt."""
    ok = _mock_response()
    with patch('talkpipe.data.html.can_fetch', return_value=True):
        with patch('talkpipe.data.html.time.sleep') as mock_sleep:
            with patch('requests.get', side_effect=[requests.ConnectionError("reset"), ok]) as mock_get:
                result = html.downloadURL("https://example.com/flaky")
    assert result == "<html>ok</html>"
    assert mock_get.call_count == 2
    assert mock_sleep.call_count == 1


def test_downloadURL_retries_transient_status_codes():
    """A 503 answer is retried and the download succeeds on a later attempt."""
    ok = _mock_response()
    with patch('talkpipe.data.html.can_fetch', return_value=True):
        with patch('talkpipe.data.html.time.sleep'):
            with patch('requests.get', side_effect=[_mock_response(status_code=503), ok]) as mock_get:
                result = html.downloadURL("https://example.com/overloaded")
    assert result == "<html>ok</html>"
    assert mock_get.call_count == 2


def test_downloadURL_honors_retry_after():
    """A Retry-After header longer than the backoff sets the retry delay."""
    throttled = _mock_response(status_code=429, headers={"Retry-After": "7"})
    ok = _mock_response()
    with patch('talkpipe.data.html.can_fetch', return_value=True):
        with patch('talkpipe.data.html.time.sleep') as mock_sleep:
            with patch('requests.get', side_effect=[throttled, ok]):
                result = html.downloadURL("https://example.com/throttled")
    assert result == "<html>ok</html>"
    mock_sleep.assert_called_once_with(7.0)


def test_downloadURL_does_not_retry_permanent_failures():
    """A 404 fails immediately; retrying would not help."""
    with patch('talkpipe.data.html.can_fetch', return_value=True):
        with patch('talkpipe.data.html.time.sleep') as mock_sleep:
            with patch('requests.get', return_value=_mock_response(status_code=404)) as mock_get:
                result = html.downloadURL("https://example.com/gone", fail_on_error=False)
    assert result is None
    assert mock_get.call_count == 1
    mock_sleep.assert_not_called()


def test_downloadURL_exhausts_retries_on_persistent_5xx():
    """Persistent 5xx answers fail after the configured number of attempts."""
    with patch('talkpipe.data.html.can_fetch', return_value=True):
        with patch('talkpipe.data.html.time.sleep'):
            with patch('requests.get', return_value=_mock_response(status_code=500)) as mock_get:
                with pytest.raises(ValueError):
                    html.downloadURL("https://example.com/broken", retries=2)
    assert mock_get.call_count == 3


def test_downloadURL_accepts_any_2xx_status():
    """Non-200 success codes such as 203 still return the content."""
    with patch('talkpipe.data.html.can_fetch', return_value=True):
        with patch('requests.get', return_value=_mock_response(status_code=203)):
            result = html.downloadURL("https://example.com/proxied")
    assert result == "<html>ok</html>"


def test_downloadURL_sends_browser_headers():
    """Requests identify as a browser instead of the bare requests default."""
    with patch('talkpipe.data.html.can_fetch', return_value=True):
        with patch('talkpipe.data.html.get_config', return_value={}):
            with patch('requests.get', return_value=_mock_response()) as mock_get:
                html.downloadURL("https://example.com/")
    headers = mock_get.call_args.kwargs["headers"]
    assert headers["User-Agent"] == html.DEFAULT_USER_AGENT
    assert "Accept" in headers
    assert "Accept-Language" in headers


def test_downloadURL_fixes_undeclared_charset():
    """Without a declared charset, detected encoding replaces the ISO-8859-1 fallback."""
    response = _mock_response(headers={"Content-Type": "text/html"},
                              encoding="ISO-8859-1", apparent_encoding="utf-8")
    with patch('talkpipe.data.html.can_fetch', return_value=True):
        with patch('requests.get', return_value=response):
            html.downloadURL("https://example.com/utf8")
    assert response.encoding == "utf-8"


def test_downloadURL_keeps_declared_charset():
    """A charset declared in the Content-Type header is trusted as-is."""
    response = _mock_response(headers={"Content-Type": "text/html; charset=ISO-8859-1"},
                              encoding="ISO-8859-1", apparent_encoding="utf-8")
    with patch('talkpipe.data.html.can_fetch', return_value=True):
        with patch('requests.get', return_value=response):
            html.downloadURL("https://example.com/latin1")
    assert response.encoding == "ISO-8859-1"

def test_downloadURL(mock_requests_get_completion):


    f = html.downloadURLSegment()
    f = f.as_function(single_in=True, single_out=True)
    ans = f("http://www.example.com")
    assert ans is not None
    assert len(ans) > 0
    assert "example" in ans

    f = html.downloadURLSegment(field="content")
    f = f.as_function(single_in=True, single_out=True)
    ans = f({"content": "http://www.example.com"})
    assert ans is not None
    assert len(ans) > 0
    assert "example" in ans

    f = html.downloadURLSegment(field="content", set_as="text")
    f = f.as_function(single_in=True, single_out=True)
    ans = f({"content": "http://www.example.com"})
    assert "text" in ans
    assert ans["text"] is not None
    assert len(ans["text"]) > 0
    assert "<title>Mocked" in ans["text"]

