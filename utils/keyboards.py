from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

TICKET_CATEGORIES = {
    "payment": "Оплата / платежи",
    "order": "Проблема с заказом",
    "account": "Аккаунт",
    "other": "Другое",
}


def categories_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=title, callback_data=f"category:{key}")]
        for key, title in TICKET_CATEGORIES.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📝 Создать тикет", callback_data="new_ticket")],
        [InlineKeyboardButton(text="📋 Мои тикеты", callback_data="my_tickets")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def ticket_created_keyboard(ticket_id: int) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="🔒 Закрыть тикет", callback_data=f"user_close:{ticket_id}")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def user_tickets_list_keyboard(tickets) -> InlineKeyboardMarkup:
    buttons = []
    for t in tickets:
        if t.status.value != "closed":
            buttons.append(
                [InlineKeyboardButton(text=f"🔒 Закрыть #{t.id}", callback_data=f"user_close:{t.id}")]
            )
    return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None


def ticket_queue_item_keyboard(ticket_id: int) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="✅ Взять в работу", callback_data=f"take:{ticket_id}")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def operator_ticket_keyboard(ticket_id: int) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="🔒 Закрыть тикет", callback_data=f"close:{ticket_id}")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить оператора", callback_data="admin:add_operator")],
        [InlineKeyboardButton(text="👥 Операторы", callback_data="admin:list_operators")],
        [InlineKeyboardButton(text="📋 Очередь тикетов", callback_data="admin:queue")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def back_to_admin_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="⬅️ Назад в панель", callback_data="admin:menu")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def operators_list_keyboard(operators) -> InlineKeyboardMarkup:
    buttons = []
    for op in operators:
        status_icon = "🟢" if op.is_active else "🔴"
        role_icon = "👑" if op.role.value == "admin" else "🎧"
        label = f"{status_icon} {role_icon} {op.telegram_id}"
        buttons.append(
            [InlineKeyboardButton(text=label, callback_data=f"admin:toggle_operator:{op.id}")]
        )
    buttons.append([InlineKeyboardButton(text="⬅️ Назад в панель", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
