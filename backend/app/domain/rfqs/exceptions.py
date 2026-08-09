from app.domain.shared.exceptions import DomainError


class RfqError(DomainError):
    """Base RFQ application/domain error."""


class RfqNotFound(RfqError):
    pass


class InvalidRfqState(RfqError):
    pass


class RfqGenerationError(RfqError):
    pass


class DuplicateRfqRequest(RfqGenerationError):
    pass


class AttachmentValidationError(RfqError):
    pass


class EmailTemplateNotFound(RfqError):
    pass


class EmailCompositionError(RfqError):
    pass


class EmailDeliveryError(RfqError):
    """Base outbound transport error. It is not automatically retryable."""

    retryable = False
    delivery_ambiguous = False


class RetryableEmailDeliveryError(EmailDeliveryError):
    """Transient provider/network error that can be retried safely by policy."""

    retryable = True


class AmbiguousEmailDeliveryError(EmailDeliveryError):
    """The provider may have accepted the message; automatic retry is unsafe."""

    delivery_ambiguous = True


class PermanentEmailDeliveryError(EmailDeliveryError):
    """Permanent validation/authentication/provider rejection."""


class DuplicateRfqSend(RfqError):
    pass
