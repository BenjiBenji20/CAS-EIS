from typing import Any, Generic, Optional, Sequence, Type, TypeVar
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

ModelType = TypeVar("ModelType")


class BaseRepository(Generic[ModelType]):
    """Base repository providing minimal abstraction for standard CRUD operations.

    Designed for scalability, maintainability, and ease of development.
    """

    def __init__(self, db: AsyncSession, model: Type[ModelType]):
        self.db = db
        self.model = model

    @property
    def pk_column(self) -> Any:
        """Dynamically retrieves the primary key column of the model."""
        mapper_inspection = inspect(self.model)
        if not mapper_inspection or not mapper_inspection.primary_key:
            raise ValueError(f"Model {self.model.__name__} must define at least one primary key.")
        return mapper_inspection.primary_key[0]


    async def get_by_id(self, id: Any) -> Optional[ModelType]:
        """Fetch a single record by its primary key."""
        return await self.db.get(self.model, id)


    async def get_by_ids(self, ids: Sequence[Any]) -> Sequence[ModelType]:
        """Efficiently batch-fetch multiple records by a list of primary keys.

        Uses SQLAlchemy `.in_` operator on the primary key column.
        """
        if not ids:
            return []
        stmt = select(self.model).where(self.pk_column.in_(ids))
        result = await self.db.execute(stmt)
        return result.scalars().all()


    async def get_all(self, *, limit: int = 100, offset: int = 0) -> Sequence[ModelType]:
        """Fetch a paginated list of records."""
        stmt = select(self.model).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return result.scalars().all()


    async def create(self, data: dict, *, commit: bool = True) -> ModelType:
        """Create a new model instance and save it to the database."""
        db_obj = self.model(**data)
        self.db.add(db_obj)
        if commit:
            await self.db.commit()
            await self.db.refresh(db_obj)
        else:
            await self.db.flush()
        return db_obj


    async def update(self, db_obj: ModelType, data: dict, *, commit: bool = True) -> ModelType:
        """Update fields of an existing model instance."""
        for field, value in data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)
        self.db.add(db_obj)
        if commit:
            await self.db.commit()
            await self.db.refresh(db_obj)
        else:
            await self.db.flush()
        return db_obj


    async def delete(self, db_obj: ModelType, *, commit: bool = True) -> None:
        """Delete an existing model instance from the database."""
        await self.db.delete(db_obj)
        if commit:
            await self.db.commit()
        else:
            await self.db.flush()
