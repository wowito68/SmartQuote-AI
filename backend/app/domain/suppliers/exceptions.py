from app.domain.shared.exceptions import DomainError


class SupplierError(DomainError):
    """Base error for supplier discovery and review."""


class SupplierNotFound(SupplierError):
    pass


class SupplierDiscoveryNotFound(SupplierError):
    pass


class InvalidSupplierState(SupplierError):
    pass


class SupplierNotApproved(InvalidSupplierState):
    pass


class InvalidSupplierDiscoveryState(SupplierError):
    pass


class SupplierSearchFailure(SupplierError):
    pass


class SupplierDiscoveryQueueFailure(SupplierError):
    pass


class SupplierMergeConflict(SupplierError):
    pass
