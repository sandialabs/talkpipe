import pytest
from unittest.mock import patch, Mock, MagicMock
import urllib.error
import requests
from urllib.robotparser import RobotFileParser
import logging

from talkpipe.data import html
from talkpipe.data.html import downloadURL, htmlToText, downloadURLSegment, htmlToTextSegment

class TestHtmlModuleExceptions:
    """Tests for exceptions in html.py module."""

    @patch('talkpipe.data.html.can_fetch')
    def test_downloadURL_disallowed_by_robots(self, mock_can_fetch):
        """Test that downloadURL raises PermissionError when disallowed by robots.txt."""
        # Mock can_fetch to return False (disallowed)
        mock_can_fetch.return_value = False
        
        # Test with fail_on_error=True
        with pytest.raises(PermissionError, match="disallowed by robots.txt"):
            downloadURL("https://example.com", fail_on_error=True)
        
        # Test with fail_on_error=False
        result = downloadURL("https://example.com", fail_on_error=False)
        assert result is None
        
        # Verify can_fetch was called correctly
        mock_can_fetch.assert_called_with("https://example.com", "*")
    
    @patch('talkpipe.data.html.can_fetch')
    @patch('requests.get')
    def test_downloadURL_request_exception(self, mock_get, mock_can_fetch):
        """Test that downloadURL handles request exceptions."""
        # Mock can_fetch to return True (allowed)
        mock_can_fetch.return_value = True
        
        # Mock requests.get to raise an exception
        mock_get.side_effect = requests.exceptions.RequestException("Connection error")
        
        # Test with fail_on_error=True
        with pytest.raises(Exception, match="Failed to download URL"):
            downloadURL("https://example.com", fail_on_error=True)
        
        # Test with fail_on_error=False
        result = downloadURL("https://example.com", fail_on_error=False)
        assert result is None
    
    @patch('talkpipe.data.html.can_fetch')
    @patch('requests.get')
    def test_downloadURL_non_200_status(self, mock_get, mock_can_fetch):
        """Test that downloadURL handles non-200 status codes."""
        # Mock can_fetch to return True (allowed)
        mock_can_fetch.return_value = True
        
        # Mock requests.get to return a 404 response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        # Test with fail_on_error=True
        with pytest.raises(ValueError, match="Failed to download URL.*with status code 404"):
            downloadURL("https://example.com", fail_on_error=True)
        
        # Test with fail_on_error=False
        result = downloadURL("https://example.com", fail_on_error=False)
        assert result is None
    
    @patch('urllib.request.urlopen')
    def test_get_robot_parser_timeout(self, mock_urlopen):
        """Test get_robot_parser handles timeout exceptions."""
        # Mock urlopen to raise a timeout error
        mock_urlopen.side_effect = TimeoutError("Connection timed out")
        
        # it gets caught and handled, so even though it is thrown, it keeps going
        assert html.get_robot_parser("https://example.com", timeout=0.1) is None
        # Verify the warning was logged
        mock_urlopen.assert_called_once()

    
    @patch('urllib.request.urlopen')
    def test_get_robot_parser_urlerror(self, mock_urlopen):
        """Test get_robot_parser handles URLError exceptions."""
        # Mock urlopen to raise a URLError
        mock_urlopen.side_effect = urllib.error.URLError("No host")
        
        # This should return None, which is handled in can_fetch
        result = html.get_robot_parser("https://example.com")
        assert result is None
    
    def test_htmlToText_with_none(self):
        """Test htmlToText with None input."""
        result = htmlToText(None)
        assert result == ""
    
    def test_htmlToText_with_empty_string(self):
        """Test htmlToText with empty string input."""
        result = htmlToText("")
        assert result == ""

    @patch('talkpipe.data.html.Document')
    def test_htmlToText_readability_exception(self, mock_document):
        """Test htmlToText handles readability.Document exceptions."""
        # Mock Document to raise an exception
        mock_document.side_effect = Exception("Parsing error")
        
        # Test with cleanText=True
        result = htmlToText("<html><body>Test</body></html>", cleanText=True)
        assert result == ""  # Should return empty string on error

    @patch('requests.get')
    def test_downloadURLSegment_exception(self, mock_get):
        """Test downloadURLSegment handles exceptions from downloadURL."""
        # Mock requests.get to return a response with status_code 200
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        
        # Create segment
        segment = downloadURLSegment()
        
        # Process with fail_on_error=True
        with pytest.raises(ValueError, match="Failed to download URL: https://example.com with status code 404"):
            list(segment(["https://example.com"]))
        
        # Process with fail_on_error=False
        segment = downloadURLSegment(fail_on_error=False)
        result = list(segment(["https://example.com"]))
        assert result == [None]  # Should yield None on error with fail_on_error=False
    
    @patch('talkpipe.data.html.get_robot_parser')
    @patch('talkpipe.data.html.logger.warning')
    def test_can_fetch_without_robots_txt(self, mock_logger, mock_get_robot_parser):
        """Test can_fetch when robots.txt doesn't exist."""
        
        # Patch get_robot_parser to return None (no robots.txt)
        mock_get_robot_parser.return_value = None
        
        # This should return True (assume allowed) when no robots.txt
        result = html.can_fetch("https://example.com")
        assert result is True
        
        # Verify warning was logged
        mock_logger.assert_called_once()
        assert "Cannot check can_fetch" in mock_logger.call_args[0][0]
    
    @patch('talkpipe.data.html.get_robot_parser')
    def test_can_fetch_with_robots_txt_exception(self, mock_get_robot_parser):
        """Test can_fetch handles exceptions from RobotFileParser.can_fetch."""
        # Create a mock RobotFileParser that raises an exception
        mock_parser = Mock(spec=RobotFileParser)
        mock_parser.can_fetch.side_effect = Exception("Parser error")
        mock_get_robot_parser.return_value = mock_parser
        
        # This should return True (assume allowed) when there's an error
        result = html.can_fetch("https://example.com")
        assert result is True
        
        # Verify can_fetch was called
        mock_parser.can_fetch.assert_called_once_with("*", "https://example.com")
    
    @patch('talkpipe.data.html.get_robot_parser')
    def test_can_fetch_timeout_handling(self, mock_get_robot_parser):
        """Test can_fetch properly handles TimeoutError from get_robot_parser."""
        # Make get_robot_parser raise a TimeoutError
        mock_get_robot_parser.side_effect = TimeoutError("Connection timed out")
        
        # This should return True (assume allowed) when there's a timeout
        result = html.can_fetch("https://example.com")
        assert result is True

    def test_htmlToTextSegment_with_invalid_html(self):
        """Test htmlToTextSegment with invalid HTML."""
        segment = htmlToTextSegment(cleanText=True, field="content")
        
        # Process an item with invalid HTML
        item = {"content": "<html><body>Incomplete tag"}
        result = list(segment([item]))
        
        # It should still return a result, although potentially with warnings
        assert len(result) == 1
        assert result[0] is not None