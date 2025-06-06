import pytest
import logging
import smtplib

from talkpipe.data import email
from talkpipe.chatterlang.compiler import compile
from talkpipe.util.config import get_config, reset_config
from testutils import monkeypatched_env
import imaplib
from email.message import EmailMessage

@pytest.fixture
def monkeypatched_smtp(monkeypatch):
    """Fixture that replaces smtplib.SMTP with a mock SMTP server and stores the instance."""

    class MockSMTP:
        """Mock SMTP class to replace smtplib.SMTP."""
        def __init__(self, smtp_server, port):
            self.messages = []
            logging.debug(f"Mock SMTP initialized for {smtp_server}:{port}")

        def starttls(self):
            logging.debug("Mock TLS encryption started")

        def login(self, sender_email, sender_password):
            logging.debug("Mock SMTP server login successful")

        def send_message(self, msg):
            self.messages.append(msg)
            logging.debug("Mock email sent (no actual email)")

        def __enter__(self):
            return self  # Mimic `with` statement behavior

        def __exit__(self, exc_type, exc_value, traceback):
            logging.debug("Mock SMTP connection closed")

    # Store the last created MockSMTP instance
    mock_smtp_instance = None

    def mock_smtp_init(smtp_server, port):
        nonlocal mock_smtp_instance
        mock_smtp_instance = MockSMTP(smtp_server, port)
        return mock_smtp_instance

    # Replace smtplib.SMTP with the mock class but store instances
    monkeypatch.setattr(smtplib, "SMTP", mock_smtp_init)

    # Return the stored instance so tests can inspect it
    return lambda: mock_smtp_instance

@pytest.fixture
def monkeypatched_imap(monkeypatch):
    """Fixture that replaces imaplib.IMAP4_SSL with a mock IMAP server and stores the instance."""

    class MockIMAP:
        """Mock IMAP class to replace imaplib.IMAP4_SSL."""
        def __init__(self, imap_server):
            self.messages = []
            self.selected_mailbox = None
            self.message_flags = {}  # Store flags for messages
            logging.debug(f"Mock IMAP initialized for {imap_server}")

        def login(self, username, password):
            logging.debug("Mock IMAP server login successful")
            return ('OK', [b'LOGIN completed'])

        def select(self, mailbox):
            self.selected_mailbox = mailbox
            logging.debug(f"Mock mailbox selected: {mailbox}")
            return ('OK', [b'2'])  # 2 messages in mailbox

        def search(self, charset, *criteria):
            criteria_str = ' '.join([c.decode() if isinstance(c, bytes) else c for c in criteria])
            logging.debug(f"Mock search executed with criteria: {criteria_str}")
            return ('OK', [b'1 2'])
        
        def fetch(self, msg_id, data):
            logging.debug(f"Mock fetch executed for message ID: {msg_id}")
            
            # Create a sample email message
            msg = EmailMessage()
            msg['From'] = 'sender@example.com'
            msg['To'] = 'recipient@example.com'
            msg['Subject'] = 'Test Email'
            msg.set_content('This is a test email body')
            
            # Format depends on what was requested in the data parameter
            if data == '(RFC822)':
                return ('OK', [(msg_id, msg.as_bytes())])
            elif data == '(BODY[HEADER])':
                return ('OK', [(msg_id, b'From: sender@example.com\r\nTo: recipient@example.com\r\nSubject: Test Email\r\n\r\n')])
            else:
                return ('OK', [(msg_id, b'Mock email data')])
        
        def store(self, msg_id, command, flags):
            logging.debug(f"Mock store executed for message ID: {msg_id} with command: {command}, flags: {flags}")
            
            # Initialize flags for this message if not already done
            if msg_id not in self.message_flags:
                self.message_flags[msg_id] = set()
                
            # Process the command (e.g., +FLAGS, -FLAGS, FLAGS)
            if command.startswith('+'):
                for flag in flags:
                    self.message_flags[msg_id].add(flag)
            elif command.startswith('-'):
                for flag in flags:
                    if flag in self.message_flags[msg_id]:
                        self.message_flags[msg_id].remove(flag)
            else:  # Replace all flags
                self.message_flags[msg_id] = set(flags)
                
            return ('OK', [f"{msg_id} {command} completed".encode()])
        
        def close(self):
            logging.debug("Mock IMAP connection closed")
            return ('OK', [b'CLOSE completed'])
            
        def logout(self):
            logging.debug("Mock IMAP logout completed")
            return ('OK', [b'LOGOUT completed'])

    # Store the last created MockIMAP instance
    mock_imap_instance = MockIMAP("mock_imap_server")

    def mock_imap_init(imap_server, *args, **kwargs):
        nonlocal mock_imap_instance
        mock_imap_instance = MockIMAP(imap_server)
        return mock_imap_instance

    # Replace imaplib.IMAP4_SSL with the mock class but store instances
    monkeypatch.setattr(imaplib, "IMAP4_SSL", mock_imap_init)

    # Return the stored instance so tests can inspect it
    return lambda: mock_imap_instance

def test_item_to_html():
    item = {
        "name": "John Doe",
        "age": 30,
        "email": "go@gmail.com"
    }
    body_fields = "name:Name,age:Age,email:Email"
    html = email.item_to_html(item, body_fields)
    assert html == "<p><b>Name</b></p><p>John Doe</p><p><b>Age</b></p><p>30</p><p><b>Email</b></p><p>go@gmail.com</p>"

def test_item_to_text():
    item = {
        "name": "John Doe",
        "age": 30,
        "email": "go@gmail.com"
    }
    body_fields = "name:Name,age:Age,email:Email"
    text = email.item_to_text(item, body_fields)
    assert text == "Name: John Doe\n\nAge: 30\n\nEmail: go@gmail.com\n\n"

def test_send_email(monkeypatched_smtp):
    #This one just passes if it doesn't throw an exception. 
    #The method is supposed to send an email, but we don't want to actually send an email in our tests.
    email.send_email(
        sender_email="test@email.com",
        sender_password="password",
        recipient_email="recipient@mail.com",
        smtp_server="smtp.server.com",
        port=587,
        subject="This is a test email",
        body="This is a test email",
        html_body="<h1>This is a test email</h1>"
    )

def test_email_segment(monkeypatched_smtp, monkeypatched_env):
    monkeypatched_env({
        "TALKPIPE_sender_email": "asender@mail.com",
        "TALKPIPE_recipient_email": "areceiver@mail.com",
        "TALKPIPE_smtp_server": "smtp.server.com",
        "TALKPIPE_email_password": "not really my password"
    })

    get_config(reload=True)

    code = """ | sendEmail[subject_field="subject", body_fields="body,body2"] """
    compiled = compile(code)
    f = compiled.asFunction()
    ans = list(f([{
        "subject": "Test email",
        "body": "This is a test email",
        "body2": "howdy do",
        "body3": "excluded"
    }]))

    mock_smtp = monkeypatched_smtp()

    assert len(mock_smtp.messages) == 1
    assert mock_smtp.messages[0]["Subject"] == "Test email"
    assert mock_smtp.messages[0].get_payload()[0].get_payload() == "body: This is a test email\n\nbody2: howdy do\n\n"
    assert mock_smtp.messages[0].get_payload()[1].get_payload() == "<p><b>body</b></p><p>This is a test email</p><p><b>body2</b></p><p>howdy do</p>"
    assert len(ans) == 1

def test_get_email_content():
    # Create a sample email message
    msg = EmailMessage()
    msg['From'] = 'sender@example.com'
    msg['To'] = 'recipient@example.com'
    msg['Subject'] = 'Test Email'
    msg.set_content('This is a test email body')

    plain_text, html_text = email.get_email_content(msg)
    assert plain_text == 'This is a test email body\n'
    assert html_text is None
    # Test with HTML content
    msg.set_content('<html><body>This is a test email body</body></html>', subtype='html')
    plain_text, html_text = email.get_email_content(msg)
    assert plain_text is None
    assert html_text == '<html><body>This is a test email body</body></html>\n'

def test_decode_email_header():
    # Create a sample email message
    msg = EmailMessage()
    msg['From'] = 'sender@example.com'
    msg['To'] = 'recipient@example.com'
    msg['Subject'] = 'Test Email'
    msg.set_content('This is a test email body')
    
    decoded = email.decode_email_header((msg.get('Subject', '')))
    assert decoded == 'Test Email'

def test_fetch_email(monkeypatched_imap, monkeypatched_env):
    # Create a mock IMAP server
    mock_imap = monkeypatched_imap()

    # Mock the login and select methods
    mock_imap.login("username", "password")
    mock_imap.select("INBOX")

    # Fetch emails
    emails = list(email.fetch_emails("imap.server.com", "username", "password", "INBOX", 1, 2))

    assert len(emails) == 2
    assert emails[0]['from'] == 'sender@example.com'
    assert emails[0]['to'] == 'recipient@example.com'
    assert emails[0]['subject'] == 'Test Email'
    assert 'This is a test email body' in emails[0]['plain_text']
    
    # Check second email (should be the same in our mock)
    assert emails[1]['from'] == 'sender@example.com'
    assert emails[1]['subject'] == 'Test Email'

def test_readEmail(monkeypatched_imap, monkeypatched_env):
    monkeypatched_env({
        "TALKPIPE_imap_server": "imap.server.com",
        "TALKPIPE_email_address": "username",
        "TALKPIPE_email_password": "password"
    })
    reset_config()
    get_config(reload=True)

    code = """INPUT FROM readEmail[folder="INBOX", limit=2, poll_interval_minutes=-1] """
    compiled = compile(code)
    f = compiled.asFunction()
    ans = list(f())

    mock_imap = monkeypatched_imap()

    assert len(ans) == 2
