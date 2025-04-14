import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from talkpipe.pipe import core
from talkpipe.chatterlang import registry
from talkpipe.util.config import parse_key_value_str
from talkpipe.util.data_manipulation import extract_property
from talkpipe.util.config import get_config

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
        logging.info(f"Preparing email to {recipient_email} with subject: {subject}")
        
        # Create the email
        msg = MIMEMultipart("alternative")  # Use "alternative" to support both plain text and HTML
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg['Subject'] = subject

        # Attach plain text content
        msg.attach(MIMEText(body, 'plain'))
        logging.debug("Attached plain text content")

        # Attach HTML content if provided
        if html_body:
            msg.attach(MIMEText(html_body, 'html'))
            logging.debug("Attached HTML content")

        # Connect to the SMTP server
        logging.debug(f"Connecting to SMTP server {smtp_server}:{port}")
        with smtplib.SMTP(smtp_server, port) as server:
            server.starttls()  # Start TLS encryption
            logging.debug("TLS encryption started")
            server.login(sender_email, sender_password)  # Login
            logging.debug("SMTP server login successful")
            server.send_message(msg)  # Send the email
            logging.debug("Email sent successfully")
    except Exception as e:
        logging.error(f"Failed to send email: {str(e)}")
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
    logging.debug(f"Starting sendEmail with subject_field={subject_field}, body_fields={body_fields}")
    assert subject_field is not None, "subject_field is required"
    assert body_fields is not None, "body_fields is required"

    config = get_config()
    logging.debug(f"Loaded config: {config}")
    sender = sender_email or config["sender_email"]
    recipient = recipient_email or config["recipient_email"]
    password = config["email_password"]
    _smtp_server = smtp_server or config.get("smtp_server")
    _port = port or config.get("smtp_port")
    logging.info(f"Using sender {sender} and recipient {recipient}")

    for item in items:
        logging.debug(f"Processing item: {item}")
        subject = extract_property(item, subject_field, fail_on_missing=True)
        body_html = item_to_html(item, body_fields)
        body_text = item_to_text(item, body_fields)
        logging.debug(f"Generated email with subject: {subject}")
        send_email(sender, password, recipient, subject, body_text, body_html, _smtp_server, _port)
        logging.debug("Email sent successfully")
        yield item
