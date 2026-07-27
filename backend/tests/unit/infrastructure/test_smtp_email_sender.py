from uuid import uuid4

from app.application.ports.attachment_provider import AttachmentContent
from app.domain.rfqs.entities import EmailAttachment, EmailMessage
from app.infrastructure.email.smtp_email_sender import SMTPEmailSender


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_args = None
        self.payload = None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, payload):
        self.payload = payload
        return {}


def test_smtp_adapter_composes_multiple_recipients_and_pdf_attachment(monkeypatch) -> None:
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    sender = SMTPEmailSender(
        host="smtp.example.mx",
        port=587,
        sender_email="compras@example.mx",
        sender_name="Compras",
        username="user",
        password="secret",
        use_tls=True,
        message_id_domain="example.mx",
    )
    message = EmailMessage(
        rfq_id=uuid4(),
        rfq_version=1,
        attempt_number=1,
        idempotency_key="d" * 64,
        provider_name="smtp",
        from_address="compras@example.mx",
        to_recipients=("uno@example.mx", "dos@example.mx"),
        cc_recipients=("copia@example.mx",),
        bcc_recipients=(),
        subject="Solicitud",
        body="Contenido",
        attachment_snapshot=(),
    )
    attachment = EmailAttachment(
        rfq_id=message.rfq_id,
        document_id=uuid4(),
        original_file_name="licitacion.pdf",
        file_hash="e" * 64,
        file_size=8,
        mime_type="application/pdf",
    )
    result = sender.send(message, (AttachmentContent(attachment, b"%PDF-1"),))
    client = FakeSMTP.instances[-1]
    assert client.started_tls is True
    assert client.login_args == ("user", "secret")
    assert client.payload["To"] == "uno@example.mx, dos@example.mx"
    assert client.payload["Cc"] == "copia@example.mx"
    assert list(client.payload.iter_attachments())[0].get_filename() == "licitacion.pdf"
    assert result.external_message_id == f"<{message.idempotency_key}@example.mx>"
