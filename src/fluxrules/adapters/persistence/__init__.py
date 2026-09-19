"""SQLAlchemy persistence adapter - isolates ORM imports from core."""

from fluxrules.adapters.persistence.sqlalchemy_adapter import (
    SQLAlchemyPersistenceAdapter,
)

__all__ = ["SQLAlchemyPersistenceAdapter"]
