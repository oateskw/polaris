"""Base repository with common CRUD operations."""

from typing import Generic, Optional, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from polaris.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Base repository with common CRUD operations."""

    def __init__(self, session: Session, model_class: type[ModelT]):
        self.session = session
        self.model_class = model_class

    def get(self, id: int) -> Optional[ModelT]:
        """Get a record by ID."""
        return self.session.get(self.model_class, id)

    def get_all(self, limit: int = 100, offset: int = 0) -> list[ModelT]:
        """Get all records with pagination."""
        stmt = select(self.model_class).limit(limit).offset(offset)
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def create(self, **kwargs) -> ModelT:
        """Create a new record."""
        instance = self.model_class(**kwargs)
        self.session.add(instance)
        self.session.flush()
        return instance

    def update(self, id: int, **kwargs) -> Optional[ModelT]:
        """Update a record by ID."""
        instance = self.get(id)
        if instance:
            for key, value in kwargs.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)
            self.session.flush()
        return instance

    def delete(self, id: int) -> bool:
        """Delete a record by ID."""
        instance = self.get(id)
        if instance:
            self.session.delete(instance)
            self.session.flush()
            return True
        return False

    def commit(self) -> None:
        """Commit the current transaction."""
        self.session.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        self.session.rollback()
