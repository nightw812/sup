from aiogram.fsm.state import State, StatesGroup


class TicketCreation(StatesGroup):
    choosing_category = State()
    entering_subject = State()
    entering_description = State()


class OperatorReply(StatesGroup):
    waiting_close_reason = State()


class AdminPanel(StatesGroup):
    waiting_operator_id = State()