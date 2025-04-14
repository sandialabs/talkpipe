import pytest
import logging
import smtplib

from talkpipe.data import email
from talkpipe.chatterlang.compiler import compile
from talkpipe.util.config import get_config
from testutils import monkeypatched_env

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