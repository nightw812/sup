import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TicketStatus(str, enum.Enum):
    OPEN = "open"           # новый, ждёт оператора
    IN_PROGRESS = "in_progress"  # взят оператором в работу
    CLOSED = "closed"       # закрыт


class SenderType(str, enum.Enum):
    USER = "user"
    OPERATOR = "operator"


class OperatorRole(str, enum.Enum):
    OPERATOR = "operator"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # id тикета, который сейчас "открыт" для переписки в чате (для роутинга сообщений)
    active_ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), nullable=True)

    tickets: Mapped[list["Ticket"]] = relationship(
        "Ticket", back_populates="user", foreign_keys="Ticket.user_id"
    )


class Operator(Base):
    __tablename__ = "operators"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[OperatorRole] = mapped_column(Enum(OperatorRole), default=OperatorRole.OPERATOR)
    is_active: Mapped[bool] = mapped_column(default=True)  # можно временно отключить оператора
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # id тикета, который оператор сейчас ведёт (для роутинга сообщений)
    active_ticket_id: Mapped[int | None] = mapped_column(ForeignKey("tickets.id"), nullable=True)


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("operators.id"), nullable=True, index=True)

    category: Mapped[str] = mapped_column(String(64))
    subject: Mapped[str] = mapped_column(String(255))
    status: Mapped[TicketStatus] = mapped_column(Enum(TicketStatus), default=TicketStatus.OPEN, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="tickets", foreign_keys=[user_id])
    operator: Mapped["Operator | None"] = relationship("Operator", foreign_keys=[operator_id])
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="ticket", order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    sender_type: Mapped[SenderType] = mapped_column(Enum(SenderType))
    sender_telegram_id: Mapped[int] = mapped_column(BigInteger)

    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachment_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attachment_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # photo/document/video...

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="messages")
