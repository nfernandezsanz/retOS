from sqlalchemy.exc import IntegrityError

from retos.core.config import Settings
from retos.persistence.database import SessionFactory
from retos.persistence.unit_of_work import SQLAlchemyUnitOfWork


async def bootstrap_admin_user(
    *,
    settings: Settings,
    session_factory: SessionFactory,
) -> None:
    bootstrap = settings.bootstrap_admin
    if bootstrap is None:
        return

    uow = SQLAlchemyUnitOfWork(session_factory)
    async with uow:
        existing = await uow.admin_users.get_by_email(str(bootstrap.email))
        if existing is not None:
            return
        await uow.admin_users.add(
            email=str(bootstrap.email),
            password_hash=bootstrap.password_hash,
        )
        try:
            await uow.commit()
        except IntegrityError:
            await uow.rollback()
