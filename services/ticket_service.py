from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Message, Operator, OperatorRole, SenderType, Ticket, TicketStatus, User


async def get_or_create_user(session: AsyncSession, telegram_id: int, username: str | None, full_name: str | None) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(telegram_id=telegram_id, username=username, full_name=full_name)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user


async def get_operator(session: AsyncSession, telegram_id: int) -> Operator | None:
    result = await session.execute(select(Operator).where(Operator.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def create_ticket(session: AsyncSession, user: User, category: str, subject: str) -> Ticket:
    ticket = Ticket(user_id=user.id, category=category, subject=subject, status=TicketStatus.OPEN)
    session.add(ticket)
    await session.flush()

    # сразу делаем этот тикет активным для переписки пользователя
    user.active_ticket_id = ticket.id
    await session.commit()
    await session.refresh(ticket)
    return ticket


async def get_open_queue(session: AsyncSession) -> list[Ticket]:
    """Тикеты, ожидающие оператора."""
    result = await session.execute(
        select(Ticket).where(Ticket.status == TicketStatus.OPEN).order_by(Ticket.created_at)
    )
    return list(result.scalars().all())


async def take_ticket(session: AsyncSession, ticket_id: int, operator: Operator) -> Ticket | None:
    """Оператор берёт тикет в работу. Возвращает None, если тикет уже занят."""
    result = await session.execute(
        select(Ticket).options(selectinload(Ticket.user)).where(Ticket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    if ticket is None or ticket.status != TicketStatus.OPEN:
        return None

    ticket.status = TicketStatus.IN_PROGRESS
    ticket.operator_id = operator.id
    operator.active_ticket_id = ticket.id
    await session.commit()
    await session.refresh(ticket)
    return ticket


async def close_ticket(session: AsyncSession, ticket: Ticket, reason: str | None = None) -> None:
    ticket.status = TicketStatus.CLOSED
    ticket.closed_at = datetime.now(timezone.utc)
    ticket.close_reason = reason

    # снимаем активный тикет у пользователя и оператора, если он был этот
    await session.execute(
        update(User).where(User.active_ticket_id == ticket.id).values(active_ticket_id=None)
    )
    await session.execute(
        update(Operator).where(Operator.active_ticket_id == ticket.id).values(active_ticket_id=None)
    )
    await session.commit()


async def add_message(
    session: AsyncSession,
    ticket_id: int,
    sender_type: SenderType,
    sender_telegram_id: int,
    text: str | None,
    attachment_file_id: str | None = None,
    attachment_type: str | None = None,
) -> Message:
    message = Message(
        ticket_id=ticket_id,
        sender_type=sender_type,
        sender_telegram_id=sender_telegram_id,
        text=text,
        attachment_file_id=attachment_file_id,
        attachment_type=attachment_type,
    )
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return message


async def close_ticket_by_user(session: AsyncSession, ticket_id: int, user: User) -> Ticket | None:
    """Закрытие тикета самим автором. Возвращает None, если тикет чужой или уже закрыт."""
    result = await session.execute(
        select(Ticket).options(selectinload(Ticket.operator)).where(Ticket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    if ticket is None or ticket.user_id != user.id or ticket.status == TicketStatus.CLOSED:
        return None

    await close_ticket(session, ticket, reason="Закрыт пользователем")
    return ticket


async def get_ticket_with_relations(session: AsyncSession, ticket_id: int) -> Ticket | None:
    result = await session.execute(
        select(Ticket)
        .options(selectinload(Ticket.user), selectinload(Ticket.operator))
        .where(Ticket.id == ticket_id)
    )
    return result.scalar_one_or_none()


async def get_user_tickets(session: AsyncSession, user: User) -> list[Ticket]:
    result = await session.execute(
        select(Ticket).where(Ticket.user_id == user.id).order_by(Ticket.created_at.desc())
    )
    return list(result.scalars().all())


async def is_admin(session: AsyncSession, telegram_id: int) -> bool:
    operator = await get_operator(session, telegram_id)
    return operator is not None and operator.role == OperatorRole.ADMIN and operator.is_active


async def list_operators(session: AsyncSession) -> list[Operator]:
    result = await session.execute(select(Operator).order_by(Operator.created_at))
    return list(result.scalars().all())


async def toggle_operator_active(session: AsyncSession, operator_id: int) -> Operator | None:
    result = await session.execute(select(Operator).where(Operator.id == operator_id))
    operator = result.scalar_one_or_none()
    if operator is None:
        return None
    operator.is_active = not operator.is_active
    await session.commit()
    await session.refresh(operator)
    return operator
