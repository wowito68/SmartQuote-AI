class RfqError(Exception):
    """Base RFQ application/domain error."""


class RfqNotFound(RfqError):
    pass


class InvalidRfqState(RfqError):
    pass


class RfqGenerationError(RfqError):
    pass


class AttachmentValidationError(RfqError):
    pass


class EmailTemplateNotFound(RfqError):
    pass


class EmailCompositionError(RfqError):
    pass


class EmailDeliveryError(RfqError):
    pass


class DuplicateRfqSend(RfqError):
    pass
