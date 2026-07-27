import smtplib
import time
from email.message import EmailMessage as StandardEmailMessage
from email.utils import formataddr

from app.application.ports.attachment_provider import AttachmentContent
from app.application.ports.email_sender import EmailSender, EmailSendResult
from app.domain.rfqs.entities import EmailMessage
from app.domain.rfqs.exceptions import EmailDeliveryError


class SMTPEmailSender(EmailSender):
    provider_name = "smtp"

    def __init__(
        self,
        *,
        host: str,
        port: int,
        sender_email: str,
        sender_name: str,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
        use_ssl: bool = False,
        timeout_seconds: float = 30.0,
        message_id_domain: str = "smartquote.local",
    ) -> None:
        self._host = host
        self._port = port
        self._sender_email = sender_email
        self.sender_address = sender_email
        self._sender_name = sender_name
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._use_ssl = use_ssl
        self._timeout_seconds = timeout_seconds
        self._message_id_domain = message_id_domain

    @property
    def sender_email(self) -> str:
        return self._sender_email

    def send(
        self,
        message: EmailMessage,
        attachments: tuple[AttachmentContent, ...],
    ) -> EmailSendResult:
        payload = StandardEmailMessage()
        payload["From"] = formataddr((self._sender_name, self._sender_email))
        payload["To"] = ", ".join(message.to_recipients)
        if message.cc_recipients:
            payload["Cc"] = ", ".join(message.cc_recipients)
        if message.bcc_recipients:
            payload["Bcc"] = ", ".join(message.bcc_recipients)
        payload["Subject"] = message.subject
        external_message_id = f"<{message.idempotency_key}@{self._message_id_domain}>"
        payload["Message-ID"] = external_message_id
        payload["X-SmartQuote-RFQ-ID"] = str(message.rfq_id)
        payload["X-SmartQuote-Idempotency-Key"] = message.idempotency_key
        payload.set_content(message.body)
        for attachment in attachments:
            payload.add_attachment(
                attachment.content,
                maintype="application",
                subtype="pdf",
                filename=attachment.metadata.original_file_name,
            )

        started = time.perf_counter()
        client_class = smtplib.SMTP_SSL if self._use_ssl else smtplib.SMTP
        try:
            with client_class(self._host, self._port, timeout=self._timeout_seconds) as client:
                if self._use_tls and not self._use_ssl:
                    client.starttls()
                if self._username:
                    client.login(self._username, self._password or "")
                refused = client.send_message(payload)
                if refused:
                    raise EmailDeliveryError(
                        f"SMTP provider refused {len(refused)} recipient(s)."
                    )
        except EmailDeliveryError:
            raise
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailDeliveryError("SMTP delivery failed.") from exc
        duration_ms = round((time.perf_counter() - started) * 1000)
        return EmailSendResult(self.provider_name, external_message_id, duration_ms)
