from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession

from retos.persistence.database import SessionFactory
from retos.persistence.repositories import DomainRepository, SourceRepository


class SQLAlchemyUnitOfWork:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self.session: AsyncSession | None = None
        self.domains: DomainRepository
        self.sources: SourceRepository

    async def __aenter__(self) -> SQLAlchemyUnitOfWork:
        self.session = self._session_factory()
        self.domains = DomainRepository(self.session)
        self.sources = SourceRepository(self.session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.session is None:
            return
        if exc_type is not None:
            await self.session.rollback()
        await self.session.close()

    async def commit(self) -> None:
        if self.session is None:
            raise RuntimeError("Unit of work has not been entered")
        await self.session.commit()

    async def rollback(self) -> None:
        if self.session is None:
            raise RuntimeError("Unit of work has not been entered")
        await self.session.rollback()
