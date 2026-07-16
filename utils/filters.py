from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from config import ADMIN_IDS
from database.engine import async_session
from database.models import Operator, OperatorRole

TelegramEvent = Message | CallbackQuery


class IsOperatorFilter(BaseFilter):
    """Пропускает апдейт дальше по router'у, только если отправитель — активный оператор."""

    async def __call__(self, event: TelegramEvent) -> bool:
        async with async_session() as session:
            result = await session.execute(
                select(Operator).where(Operator.telegram_id == event.from_user.id)
            )
            operator = result.scalar_one_or_none()
            return operator is not None and operator.is_active


class IsAdminFilter(BaseFilter):
    """Пропускает апдейт, только если отправитель — активный администратор (по роли в БД)."""

    async def __call__(self, event: TelegramEvent) -> bool:
        async with async_session() as session:
            result = await session.execute(
                select(Operator).where(Operator.telegram_id == event.from_user.id)
            )
            operator = result.scalar_one_or_none()
            return operator is not None and operator.is_active and operator.role == OperatorRole.ADMIN


class IsAdminOrBootstrapFilter(BaseFilter):
    """
    Пропускает, если пользователь либо:
    - указан в ADMIN_IDS в .env (bootstrap-админ, даже если ещё не в таблице operators), либо
    - имеет роль admin в БД.
    """

    async def __call__(self, event: TelegramEvent) -> bool:
        if event.from_user.id in ADMIN_IDS:
            return True

        async with async_session() as session:
            result = await session.execute(
                select(Operator).where(Operator.telegram_id == event.from_user.id)
            )
            operator = result.scalar_one_or_none()
            return operator is not None and operator.is_active and operator.role == OperatorRole.ADMIN
