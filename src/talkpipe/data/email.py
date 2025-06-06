import logging
import datetime
import time
import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from talkpipe.pipe import core
from talkpipe.chatterlang import registry
from talkpipe.util.config import parse_key_value_str
from talkpipe.util.data_manipulation import extract_property
from talkpipe.util.config import get_config


logger = logging.getLogger(__name__)

#############################################################################
# Email sending utility functions
#############################################################################

def send_email(sender_email, sender_password, recipient_email, subject, body, html_body=None, smtp_server='smtp.gmail.com', port=587):
    """
    Send an email using SMTP protocol.
    This function sends an email using SMTP protocol with support for both plain text
    and HTML content. It establishes a secure connection using TLS encryption.
    Args:
        sender_email (str): Email address of the sender
        sender_password (str): Password for the sender's email account
        recipient_email (str): Email address of the recipient
        subject (str): Subject line of the email
        body (str): Plain text content of the email
        html_body (str, optional): HTML content of the email. Defaults to None.
        smtp_server (str, optional): SMTP server address. Defaults to 'smtp.gmail.com'.
        port (int, optional): Port number for SMTP connection. Defaults to 587.
    Raises:
        Exception: If email sending fails for any reason (connection issues, 
                  authentication failure, etc.)
    Example:
        >>> send_email(
        ...     "sender@gmail.com",
        ...     "password123",
        ...     "recipient@email.com",
        ...     "Hello",
        ...     "This is a test email",
        ...     "<h1>This is a test email</h1>"
        ... )
    """
    try:
        logger.info(f"Preparing email to {recipient_email} with subject: {subject}")
        
        # Create the email
        msg = MIMEMultipart("alternative")  # Use "alternative" to support both plain text and HTML
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg['Subject'] = subject

        # Attach plain text content
        msg.attach(MIMEText(body, 'plain'))
        logger.debug("Attached plain text content")

        # Attach HTML content if provided
        if html_body:
            msg.attach(MIMEText(html_body, 'html'))
            logger.debug("Attached HTML content")

        # Connect to the SMTP server
        logger.debug(f"Connecting to SMTP server {smtp_server}:{port}")
        with smtplib.SMTP(smtp_server, port) as server:
            server.starttls()  # Start TLS encryption
            logger.debug("TLS encryption started")
            server.login(sender_email, sender_password)  # Login
            logger.debug("SMTP server login successful")
            server.send_message(msg)  # Send the email
            logger.debug("Email sent successfully")
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")
        raise

def item_to_html(item, body_fields):
    """
    Convert an item's fields into HTML format.

    This function generates HTML content by converting specified fields from an item into
    formatted paragraphs with bold headers followed by values.

    Args:
        item: The source item containing the field values to be converted.
        body_fields (str): A string containing field mappings in key:value format.

    Returns:
        str: An HTML string containing the formatted fields and values.
            Each field is represented as a paragraph with a bold header (<b>)
            followed by its value in a separate paragraph.

    Raises:
        KeyError: If a specified field is missing from the item.

    Example:
        >>> item = {"name": "John", "email": "john@example.com"}
        >>> body_fields = "name:Name,email:Email Address"
        >>> print(item_to_html(item, body_fields))
        <p><b>Name</b></p><p>John</p><p><b>Email Address</b></p><p>john@example.com</p>
    """
    html = ""
    for field, target in parse_key_value_str(body_fields).items():
        value = extract_property(item, field, fail_on_missing=True)
        html += f"<p><b>{target}</b></p><p>{value}</p>"
    return html

def item_to_text(item, body_fields):
    """
    Convert an item's specified fields into formatted text.

    Takes an item dictionary and extracts specified fields according to body_fields mapping,
    formatting them as "target: value" pairs separated by newlines.

    Args:
        item: Dictionary containing the source data fields
        body_fields: String containing field mappings in format "source:target,source2:target2"

    Returns:
        str: Formatted text with each field on new lines, double-spaced

    Raises:
        KeyError: If a specified source field is missing from the item dictionary

    Example:
        >>> item = {"name": "John", "email": "john@example.com"}
        >>> body_fields = "name:Name,email:Email"
        >>> item_to_text(item, body_fields)
        'Name: John\n\nEmail: john@example.com\n\n'
    """
    text = ""
    for field, target in parse_key_value_str(body_fields).items():
        value = extract_property(item, field, fail_on_missing=True)
        text += f"{target}: {value}\n\n"
    return text

@registry.register_segment("sendEmail")
@core.segment(subject_field=None, body_fields=None, sender_email=None, recipient_email=None)
def sendEmail(items, subject_field, body_fields, sender_email, recipient_email, smtp_server=None, port=587):
    """
    Send emails for each item in the input iterable using SMTP.

    This function processes a list of items and sends an email for each one, using the specified
    fields for subject and body content. It supports both HTML and plain text email formats.

    Args:
        subject_field (str): Field name in the item to use as email subject
        body_fields (list[str]): List of field names to include in email body
        sender_email (str, optional): Sender's email address. If None, uses config value
        recipient_email (str, optional): Recipient's email address. If None, uses config value
        smtp_server (str, optional): SMTP server address. Defaults to 'smtp.gmail.com'
        port (int, optional): SMTP server port. Defaults to 587

    Yields:
        item: Returns each processed item after sending its corresponding email

    Raises:
        AssertionError: If subject_field or body_fields are None
        ValueError: If required fields are missing in items

    Example:
        >>> items = [{'title': 'Hello', 'content': 'World'}]
        >>> for item in sendEmail(items, 'title', ['content'], 'sender@email.com', 'recipient@email.com'):
        ...     print(f"Processed {item}")

    Notes:
        - Requires valid SMTP credentials in config
        - Supports HTML formatting in email body
        - Uses TLS encryption for email transmission
    """
    logger.debug(f"Starting sendEmail with subject_field={subject_field}, body_fields={body_fields}")
    assert subject_field is not None, "subject_field is required"
    assert body_fields is not None, "body_fields is required"

    config = get_config()
    logger.debug(f"Loaded config: {config}")
    sender = sender_email or config["sender_email"]
    recipient = recipient_email or config["recipient_email"]
    password = config["email_password"]
    _smtp_server = smtp_server or config.get("smtp_server")
    _port = port or config.get("smtp_port")
    logger.info(f"Using sender {sender} and recipient {recipient}")

    for item in items:
        logger.debug(f"Processing item: {item}")
        subject = extract_property(item, subject_field, fail_on_missing=True)
        body_html = item_to_html(item, body_fields)
        body_text = item_to_text(item, body_fields)
        logger.debug(f"Generated email with subject: {subject}")
        send_email(sender, password, recipient, subject, body_text, body_html, _smtp_server, _port)
        logger.debug("Email sent successfully")
        yield item

##############################################################################
# Email Reading utility functions
##############################################################################


def get_email_content(msg):
    """
    Extract the content from an email message.
    
    Attempts to extract both plain text and HTML content from the email.
    
    Args:
        msg: An email.message.Message object
        
    Returns:
        tuple: (plain_text, html_content) - Both may be None if not present
    """
    plain_text = None
    html_content = None
    
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            
            # Skip attachments
            if "attachment" in content_disposition:
                continue
                
            # Get the payload
            try:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or 'utf-8'
                    decoded_content = payload.decode(charset, errors='replace')
                    
                    if content_type == "text/plain":
                        plain_text = decoded_content
                    elif content_type == "text/html":
                        html_content = decoded_content
            except Exception as e:
                logger.warning(f"Error extracting email content: {str(e)}")
    else:
        # Not multipart - get content directly
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or 'utf-8'
            decoded_content = payload.decode(charset, errors='replace')
            
            content_type = msg.get_content_type()
            if content_type == "text/plain":
                plain_text = decoded_content
            elif content_type == "text/html":
                html_content = decoded_content
    
    return plain_text, html_content

def decode_email_header(header_value):
    """
    Decode an email header which might be encoded.
    
    Args:
        header_value: The header value to decode
        
    Returns:
        str: The decoded header value
    """
    if not header_value:
        return ""
        
    decoded_parts = []
    for value, encoding in decode_header(header_value):
        if isinstance(value, bytes):
            if encoding:
                value = value.decode(encoding, errors='replace')
            else:
                value = value.decode('utf-8', errors='replace')
        decoded_parts.append(value)
    
    return " ".join(decoded_parts)

def fetch_emails(
    imap_server, 
    email_address, 
    password, 
    folder='INBOX', 
    unseen_only=True,
    mark_as_read=True,
    limit=100
):
    """
    Fetch unread emails from the specified IMAP server.
    
    Args:
        imap_server (str): IMAP server address
        email_address (str): Email address
        password (str): Password for the email account
        folder (str, optional): Mailbox folder to fetch from. Defaults to 'INBOX'.
        mark_as_read (bool, optional): Whether to mark emails as read. Defaults to True.
        limit (int, optional): Maximum number of emails to fetch. Defaults to 10.
        
    Yields:
        dict: Email metadata and content
    """
    try:
        logger.info(f"Connecting to IMAP server: {imap_server}")
        # Connect to IMAP server
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(email_address, password)
        
        # Select the mailbox
        mail.select(folder)
        
        # Search for emails
        logger.debug("Searching for emails")
        status, data = mail.search(None, "UNSEEN" if unseen_only else "ALL")
        if status != 'OK':
            logger.error(f"Failed to search emails: {status}")
            return
            
        # Get the list of unread email IDs
        email_ids = data[0].split()
        if not email_ids:
            logger.info("No unread emails found")
            mail.close()
            mail.logout()
            return
            
        # Limit the number of emails to process unless limit is -1
        email_ids = email_ids[:limit] if limit > 0 else email_ids
        
        for email_id in email_ids:
            # Fetch the email data
            status, data = mail.fetch(email_id, '(RFC822)')
            if status != 'OK':
                logger.error(f"Failed to fetch email {email_id}: {status}")
                continue
                
            # Parse the email
            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            # Extract metadata
            message_id = msg.get('Message-ID', '')
            subject = decode_email_header(msg.get('Subject', ''))
            from_addr = decode_email_header(msg.get('From', ''))
            to_addr = decode_email_header(msg.get('To', ''))
            cc_addr = decode_email_header(msg.get('Cc', ''))
            date_str = msg.get('Date', '')
            
            try:
                date_obj = email.utils.parsedate_to_datetime(date_str)
            except:
                date_obj = datetime.datetime.now()
            
            # Extract content
            plain_text, html_content = get_email_content(msg)
            
            # Create email object
            email_obj = {
                'message_id': message_id,
                'subject': subject,
                'from': from_addr,
                'to': to_addr,
                'cc': cc_addr,
                'date': date_obj,
                'date_str': date_str,
                'plain_text': plain_text,
                'html_content': html_content,
                'headers': dict(msg.items()),
                'raw_email': raw_email.decode('utf-8', errors='replace')
            }
            
            # If mark_as_read is True, mark the email as read
            if mark_as_read:
                mail.store(email_id, '+FLAGS', '\\Seen')
                logger.debug(f"Marked email {email_id} as read")
            
            yield email_obj
            
        # Close the connection
        mail.close()
        mail.logout()
        logger.debug("Disconnected from IMAP server")
        
    except Exception as e:
        logger.error(f"Error fetching emails: {str(e)}")
        raise

@registry.register_source("readEmail")
@core.source(poll_interval_minutes=10, folder='INBOX', mark_as_read=True, limit=100, unseen_only=True)
def readEmail(poll_interval_minutes=10, folder='INBOX', mark_as_read=True, limit=100, unseen_only=True, 
             imap_server=None, email_address=None, password=None):
    """
    A source that monitors an email inbox and yields new unread emails.
    
    This source periodically checks for new unread emails, marks them as read,
    and yields their content and metadata. It connects using IMAP and can be
    configured to poll at specific intervals.
    
    Args:
        poll_interval_minutes (int, optional): Minutes between email checks. Defaults to 10.
        folder (str, optional): Mailbox folder to check. Defaults to 'INBOX'.
        mark_as_read (bool, optional): Whether to mark emails as read. Defaults to True.
        limit (int, optional): Maximum number of emails to fetch per check. Defaults to 100. 
            if -1, fetch all.
        imap_server (str, optional): IMAP server address. If None, uses config.
        email_address (str, optional): Email address. If None, uses config.
        password (str, optional): Password. If None, uses config.
        
    Yields:
        dict: Email metadata and content including:
            - message_id: Unique message ID
            - subject: Email subject
            - from: Sender address
            - to: Recipient address(es)
            - cc: CC address(es)
            - date: Datetime object of when email was sent
            - date_str: Date string from email header
            - plain_text: Plain text content if available
            - html_content: HTML content if available
            - headers: Dictionary of all email headers
            - raw_email: Full raw email content
    """
    config = get_config()
    _imap_server = imap_server or config.get("imap_server")
    _email_address = email_address or config.get("email_address")
    _password = password or config.get("email_password")
    
    if not _imap_server or not _email_address or not _password:
        error_msg = "Missing configuration for email. Need imap_server, email_address, and email_password.  Currently have (%s)" % [str((_imap_server, _email_address, "NONE" if _password is None else "Not shown"))]
        logger.error(error_msg)
        raise ValueError(error_msg)
        
    logger.info(f"Starting email monitor for {_email_address} with poll interval of {poll_interval_minutes} minutes")
    
    while True:
        try:
            # Fetch and yield unread emails
            yield from fetch_emails(
                _imap_server, 
                _email_address, 
                _password, 
                folder=folder,
                mark_as_read=mark_as_read,
                limit=limit,
                unseen_only=unseen_only
            )
            
        except Exception as e:
            logger.error(f"Error in email check: {str(e)}")
            
        # If poll_interval_minutes is -1, only check once
        if poll_interval_minutes == -1:
            logger.info("Single email check completed, stopping")
            break
            
        # Wait for the next poll interval
        logger.debug(f"Waiting {poll_interval_minutes} minutes until next email check")
        time.sleep(poll_interval_minutes * 60)