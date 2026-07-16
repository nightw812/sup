from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select

from database.engine import async_session
from database.models import Operator, OperatorRole, Ticket, TicketStatus
from services.ticket_service import list_operators, toggle_operator_active
from utils.filters import IsAdminOrBootstrapFilter
from utils.keyboards import (
    admin_panel_keyboard,
    back_to_admin_keyboard,
    operators_list_keyboard,
    ticket_queue_item_keyboard,
)
from utils.states import AdminPanel

router = Router(name="admin")
router.message.filter(IsAdminOrBootstrapFilter())
router.callback_query.filter(IsAdminOrBootstrapFilter())


@router.message(Command("admin"))
async def open_admin_panel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("🛠 Панель администратора", reply_markup=admin_panel_keyboard())


@router.callback_query(F.data == "admin:menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("🛠 Панель администратора", reply_markup=admin_panel_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin:add_operator")
async def prompt_add_operator(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminPanel.waiting_operator_id)
    await callback.message.edit_text(
        "Отправьте Telegram ID пользователя, которого нужно назначить оператором.\n"
        "Узнать ID можно, например, через @userinfobot.",
        reply_markup=back_to_admin_keyboard(),
    )
    await callback.answer()


@router.message(AdminPanel.waiting_operator_id)
async def add_operator_finish(message: Message, state: FSMContext) -> None:
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Нужно прислать числовой Telegram ID. Попробуйте ещё раз:")
        return

    new_operator_id = int(message.text.strip())
    async with async_session() as session:
        result = await session.execute(select(Operator).where(Operator.telegram_id == new_operator_id))
        existing = result.scalar_one_or_none()
        if existing:
            await message.answer("Этот пользователь уже оператор.", reply_markup=admin_panel_keyboard())
            await state.clear()
            return

        session.add(Operator(telegram_id=new_operator_id, role=OperatorRole.OPERATOR))
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ Оператор {new_operator_id} добавлен.", reply_markup=admin_panel_keyboard()
    )


@router.callback_query(F.data == "admin:list_operators")
async def show_operators(callback: CallbackQuery) -> None:
    async with async_session() as session:
        operators = await list_operators(session)

    if not operators:
        await callback.message.edit_text(
            "Операторов пока нет.", reply_markup=back_to_admin_keyboard()
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "👥 Операторы (нажмите, чтобы включить/выключить):",
        reply_markup=operators_list_keyboard(operators),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:toggle_operator:"))
async def toggle_operator(callback: CallbackQuery) -> None:
    operator_id = int(callback.data.split(":")[-1])
    async with async_session() as session:
        operator = await toggle_operator_active(session, operator_id)
        operators = await list_operators(session)

    if operator is None:
        await callback.answer("Оператор не найден.", show_alert=True)
        return

    status = "включён" if operator.is_active else "выключен"
    await callback.answer(f"Оператор {operator.telegram_id} {status}.")
    await callback.message.edit_reply_markup(reply_markup=operators_list_keyboard(operators))


@router.callback_query(F.data == "admin:queue")
async def show_queue_from_admin(callback: CallbackQuery) -> None:
    async with async_session() as session:
        result = await session.execute(
            select(Ticket).where(Ticket.status == TicketStatus.OPEN).order_by(Ticket.created_at)
        )
        tickets = list(result.scalars().all())

    if not tickets:
        await callback.message.edit_text("Очередь пуста 🎉", reply_markup=back_to_admin_keyboard())
        await callback.answer()
        return

    await callback.message.edit_text(f"📋 Открытых тикетов: {len(tickets)}")
    for ticket in tickets:
        await callback.message.answer(
            f"#{ticket.id} [{ticket.category}] {ticket.subject}",
            reply_markup=ticket_queue_item_keyboard(ticket.id),
        )
    await callback.answer()


@router.callback_query(F.data == "admin:stats")
async def show_stats(callback: CallbackQuery) -> None:
    async with async_session() as session:
        total = await session.scalar(select(func.count()).select_from(Ticket))
        open_count = await session.scalar(
            select(func.count()).select_from(Ticket).where(Ticket.status == TicketStatus.OPEN)
        )
        in_progress = await session.scalar(
            select(func.count()).select_from(Ticket).where(Ticket.status == TicketStatus.IN_PROGRESS)
        )
        closed = await session.scalar(
            select(func.count()).select_from(Ticket).where(Ticket.status == TicketStatus.CLOSED)
        )

    await callback.message.edit_text(
        "📊 Статистика тикетов:\n"
        f"Всего: {total}\n"
        f"Открыто: {open_count}\n"
        f"В работе: {in_progress}\n"
        f"Закрыто: {closed}",
        reply_markup=back_to_admin_keyboard(),
    )
    await callback.answer()
