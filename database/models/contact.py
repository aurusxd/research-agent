from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    String,
    Text,
    Float,
    DateTime,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.models.base import Base
from utils.enums import ContactStatus


if TYPE_CHECKING:
    from database.models.communication import Communication

class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Основная информация
    organization_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(255))
    position: Mapped[str | None] = mapped_column(String(255))

    category: Mapped[str | None] = mapped_column(String(100))

    # География
    country: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100))

    # Контакты
    website: Mapped[str | None] = mapped_column(String(500))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    contact_form_url: Mapped[str | None] = mapped_column(String(500))

    vk_url: Mapped[str | None] = mapped_column(String(500))
    telegram_url: Mapped[str | None] = mapped_column(String(500))
    youtube_url: Mapped[str | None] = mapped_column(String(500))
    rutube_url: Mapped[str | None] = mapped_column(String(500))
    dzen_url: Mapped[str | None] = mapped_column(String(500))

    # Откуда найдено
    source: Mapped[str | None] = mapped_column(String(255))

    # Анализ ИИ
    relevance_score: Mapped[float] = mapped_column(Float, default=0)
    relevance_reason: Mapped[str | None] = mapped_column(Text)

    # Коммуникация
    preferred_channel: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(
        String(50),
        default=ContactStatus.NEW,
    )

    generated_message: Mapped[str | None] = mapped_column(Text)
    response: Mapped[str | None] = mapped_column(Text)
    next_action: Mapped[str | None] = mapped_column(Text)

    # Даты
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now()
    )

    updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime)


    communications: Mapped[list["Communication"]] = relationship(
        back_populates="contact",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Communication.created_at",
    )
