from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database.engine import async_session
from database.models import SenderType, Ticket, TicketStatus, User
from services.ticket_service import (
    add_message,
    close_ticket_by_user,
    create_ticket,
    get_or_create_user,
    get_user_tickets,
)
from utils.keyboards import (
    TICKET_CATEGORIES,
    categories_keyboard,
    main_menu_keyboard,
    ticket_created_keyboard,
    user_tickets_list_keyboard,
)
from utils.states import TicketCreation

router = Router(name="user")


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    async with async_session() as session:
        await get_or_create_user(
            session, message.from_user.id, message.from_user.username, message.from_user.full_name
        )
    await message.answer(
        "Добро пожаловать в поддержку!\nВыберите действие:",
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query(F.data == "new_ticket")
async def start_new_ticket(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TicketCreation.choosing_category)
    await callback.message.edit_text("Выберите категорию обращения:", reply_markup=categories_keyboard())
    await callback.answer()


@router.callback_query(TicketCreation.choosing_category, F.data.startswith("category:"))
async def category_chosen(callback: CallbackQuery, state: FSMContext) -> None:
    category_key = callback.data.split(":", 1)[1]
    await state.update_data(category=category_key)
    await state.set_state(TicketCreation.entering_subject)
    await callback.message.edit_text(
        f"Категория: {TICKET_CATEGORIES.get(category_key, category_key)}\n\n"
        "Кратко опишите тему обращения (одним сообщением):"
    )
    await callback.answer()


@router.message(TicketCreation.entering_subject)
async def subject_entered(message: Message, state: FSMContext) -> None:
    await state.update_data(subject=message.text)
    data = await state.get_data()

    async with async_session() as session:
        user = await get_or_create_user(
            session, message.from_user.id, message.from_user.username, message.from_user.full_name
        )
        ticket = await create_ticket(session, user, category=data["category"], subject=data["subject"])

    await state.clear()
    await message.answer(
        f"✅ Тикет #{ticket.id} создан!\n"
        "Опишите вашу проблему подробнее — оператор скоро подключится к диалогу.\n\n"
        "Все ваши следующие сообщения будут отправляться в этот тикет, пока он не закрыт. "
        "Закрыть тикет можно в любой момент кнопкой ниже.",
        reply_markup=ticket_created_keyboard(ticket.id),
    )
    # TODO: уведомить операторов о новом тикете (например, в отдельный чат/группу)


@router.callback_query(F.data == "my_tickets")
async def my_tickets(callback: CallbackQuery) -> None:
    async with async_session() as session:
        user = await get_or_create_user(
            session, callback.from_user.id, callback.from_user.username, callback.from_user.full_name
        )
        tickets = await get_user_tickets(session, user)

    if not tickets:
        await callback.message.answer("У вас пока нет тикетов.")
    else:
        lines = [f"#{t.id} [{t.status.value}] — {t.subject}" for t in tickets]
        await callback.message.answer(
            "Ваши тикеты:\n" + "\n".join(lines),
            reply_markup=user_tickets_list_keyboard(tickets),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("user_close:"))
async def user_close_ticket(callback: CallbackQuery) -> None:
    ticket_id = int(callback.data.split(":", 1)[1])

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = result.scalar_one_or_none()
        if user is None:
            await callback.answer("Пользователь не найден.", show_alert=True)
            return

        ticket = await close_ticket_by_user(session, ticket_id, user)
        if ticket is None:
            await callback.answer("Этот тикет уже закрыт или не найден.", show_alert=True)
            return

        operator_telegram_id = ticket.operator.telegram_id if ticket.operator else None

    await callback.answer("Тикет закрыт.")
    await callback.message.answer(f"🔒 Тикет #{ticket_id} закрыт вами.\nЕсли нужна ещё помощь — /start")

    if operator_telegram_id:
        await callback.bot.send_message(
            operator_telegram_id, f"ℹ️ Пользователь закрыл тикет #{ticket_id}."
        )


@router.message(F.text | F.photo | F.document, TicketCreation.entering_description)
async def unused_state_guard(message: Message, state: FSMContext) -> None:
    # состояние-заглушка на будущее расширение (например, запрос вложений при создании тикета)
    await state.clear()


@router.message()
async def route_user_message_to_ticket(message: Message, state: FSMContext) -> None:
    """Любое сообщение вне FSM-сценариев считается репликой в активный тикет."""
    current_state = await state.get_state()
    if current_state is not None:
        return  # мы в середине другого сценария — не мешаем

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
        user = result.scalar_one_or_none()

        if user is None or user.active_ticket_id is None:
            await message.answer(
                "У вас нет активного тикета. Нажмите /start, чтобы создать обращение.",
            )
            return

        ticket_result = await session.execute(
            select(Ticket).options(selectinload(Ticket.operator)).where(Ticket.id == user.active_ticket_id)
        )
        ticket = ticket_result.scalar_one_or_none()
        if ticket is None or ticket.status == TicketStatus.CLOSED:
            user.active_ticket_id = None
            await session.commit()
            await message.answer("Ваш тикет уже закрыт. Нажмите /start, чтобы создать новый.")
            return

        attachment_file_id, attachment_type = _extract_attachment(message)
        await add_message(
            session,
            ticket_id=ticket.id,
            sender_type=SenderType.USER,
            sender_telegram_id=message.from_user.id,
            text=message.text or message.caption,
            attachment_file_id=attachment_file_id,
            attachment_type=attachment_type,
        )

        operator_telegram_id = ticket.operator.telegram_id if ticket.operator else None

    # пересылаем оператору любое содержимое как есть (текст/фото/документ) через copy_to
    if operator_telegram_id:
        await message.copy_to(chat_id=operator_telegram_id)
    else:
        await message.answer(
            "Сообщение сохранено в тикете. Оператор ещё не подключился — ожидайте."
        )


def _extract_attachment(message: Message) -> tuple[str | None, str | None]:
    if message.photo:
        return message.photo[-1].file_id, "photo"
    if message.document:
        return message.document.file_id, "document"
    if message.video:
        return message.video.file_id, "video"
    return None, None
