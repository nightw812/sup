from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.engine import async_session
from database.models import Operator, SenderType, Ticket, TicketStatus
from services.ticket_service import add_message, close_ticket, get_open_queue, get_operator, take_ticket
from utils.keyboards import operator_ticket_keyboard, ticket_queue_item_keyboard
from utils.states import OperatorReply
from utils.filters import IsOperatorFilter

router = Router(name="operator")


async def _require_operator(session: AsyncSession, telegram_id: int) -> Operator | None:
    operator = await get_operator(session, telegram_id)
    if operator is None or not operator.is_active:
        return None
    return operator


@router.message(Command("queue"))
async def show_queue(message: Message) -> None:
    async with async_session() as session:
        operator = await _require_operator(session, message.from_user.id)
        if operator is None:
            return  # не оператор — молча игнорируем в этом роутере

        tickets = await get_open_queue(session)

    if not tickets:
        await message.answer("Очередь пуста 🎉")
        return

    for ticket in tickets:
        await message.answer(
            f"#{ticket.id} [{ticket.category}] {ticket.subject}",
            reply_markup=ticket_queue_item_keyboard(ticket.id),
        )


@router.callback_query(F.data.startswith("take:"))
async def take_ticket_handler(callback: CallbackQuery) -> None:
    ticket_id = int(callback.data.split(":", 1)[1])

    async with async_session() as session:
        operator = await _require_operator(session, callback.from_user.id)
        if operator is None:
            await callback.answer("Вы не оператор.", show_alert=True)
            return

        ticket = await take_ticket(session, ticket_id, operator)
        if ticket is None:
            await callback.answer("Тикет уже взят другим оператором.", show_alert=True)
            return

        user_telegram_id = ticket.user.telegram_id if ticket.user else None

    await callback.message.edit_text(f"✅ Тикет #{ticket_id} взят в работу вами.")
    await callback.message.answer(
        f"Диалог по тикету #{ticket_id} открыт. Пишите сообщение — оно уйдёт пользователю.",
        reply_markup=operator_ticket_keyboard(ticket_id),
    )
    await callback.answer()

    if user_telegram_id:
        await callback.bot.send_message(
            user_telegram_id, f"👤 Оператор подключился к тикету #{ticket_id}."
        )


@router.callback_query(F.data.startswith("close:"))
async def close_ticket_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    ticket_id = int(callback.data.split(":", 1)[1])
    await state.update_data(closing_ticket_id=ticket_id)
    await state.set_state(OperatorReply.waiting_close_reason)
    await callback.message.answer("Укажите причину закрытия (или отправьте '-' чтобы пропустить):")
    await callback.answer()


@router.message(OperatorReply.waiting_close_reason)
async def close_ticket_finish(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    ticket_id = data["closing_ticket_id"]
    reason = None if message.text.strip() == "-" else message.text

    async with async_session() as session:
        result = await session.execute(
            select(Ticket).options(selectinload(Ticket.user)).where(Ticket.id == ticket_id)
        )
        ticket = result.scalar_one_or_none()
        if ticket is None:
            await message.answer("Тикет не найден.")
            await state.clear()
            return

        user_telegram_id = ticket.user.telegram_id if ticket.user else None
        await close_ticket(session, ticket, reason)

    await state.clear()
    await message.answer(f"🔒 Тикет #{ticket_id} закрыт.")
    if user_telegram_id:
        await message.bot.send_message(
            user_telegram_id, f"Ваш тикет #{ticket_id} закрыт оператором.\nЕсли нужна ещё помощь — /start"
        )


@router.message(IsOperatorFilter())
async def route_operator_message_to_user(message: Message, state: FSMContext) -> None:
    """Сообщение оператора вне FSM-сценариев уходит пользователю по активному тикету."""
    current_state = await state.get_state()
    if current_state is not None:
        return

    async with async_session() as session:
        operator = await _require_operator(session, message.from_user.id)
        if operator is None or operator.active_ticket_id is None:
            return  # не оператор либо нет активного тикета — пропускаем

        ticket_result = await session.execute(
            select(Ticket).options(selectinload(Ticket.user)).where(Ticket.id == operator.active_ticket_id)
        )
        ticket = ticket_result.scalar_one_or_none()
        if ticket is None or ticket.status == TicketStatus.CLOSED:
            return

        await add_message(
            session,
            ticket_id=ticket.id,
            sender_type=SenderType.OPERATOR,
            sender_telegram_id=message.from_user.id,
            text=message.text or message.caption,
        )
        user_telegram_id = ticket.user.telegram_id if ticket.user else None

    if user_telegram_id:
        await message.bot.send_message(user_telegram_id, f"💬 Оператор: {message.text}")
