from app.application.ports.unit_of_work import UnitOfWorkFactory
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork


def get_uow_factory() -> UnitOfWorkFactory:
    return SqlAlchemyUnitOfWork
