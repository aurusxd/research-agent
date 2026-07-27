from typing import Literal

from pydantic import BaseModel, Field, model_validator

from services.contact_channels import require_usable_contact_channel


class SaveContactToolArgs(BaseModel):
    search_run_id: int | None = Field(
        default=None,
        description="ID текущего поискового запуска, переданный агенту",
    )

    organization_name: str = Field(
        description="Полное название найденной организации"
    )

    contact_name: str | None = Field(
        default=None,
        description="Имя контактного лица, если оно найдено",
    )

    position: str | None = Field(
        default=None,
        description="Должность контактного лица",
    )

    category: str | None = Field(
        default=None,
        description="Сфера деятельности организации",
    )

    country: str | None = None
    region: str | None = None
    city: str | None = None

    website: str | None = Field(
        default=None,
        description="Официальный сайт организации",
    )

    email: str | None = Field(
        default=None,
        description="Публичный email организации",
    )

    phone: str | None = Field(
        default=None,
        description="Публичный телефон организации",
    )

    contact_form_url: str | None = Field(
        default=None,
        description=(
            "Прямая ссылка на интерактивную форму с полем сообщения и "
            "кнопкой отправки. Страница, где опубликован email, "
            "не является contact_form_url"
        ),
    )

    vk_url: str | None = Field(
        default=None,
        description="Ссылка на официальную страницу организации во ВКонтакте",
    )

    telegram_url: str | None = Field(
        default=None,
        description="Ссылка на официальный Telegram-канал, группу или аккаунт организации",
    )

    youtube_url: str | None = Field(
        default=None,
        description="Ссылка на официальный YouTube-канал организации",
    )

    rutube_url: str | None = Field(
        default=None,
        description="Ссылка на официальный RuTube-канал организации",
    )

    dzen_url: str | None = Field(
        default=None,
        description="Ссылка на официальный канал организации в Дзене",
    )

    source: str = Field(
        description="URL или список источников, где найдена информация",
    )

    relevance_score: int = Field(
        ge=0,
        le=100,
        description="Оценка релевантности организации от 0 до 100",
    )

    relevance_reason: str = Field(
        description="Почему организация подходит или не подходит",
    )

    preferred_channel: str | None = Field(
        default=None,
        description=(
            "Предпочтительный канал, выбранный агентом: email, "
            "contact_form, vk, telegram или ok"
        ),
    )

    ok_url: str | None = Field(
        default=None,
        description="Ссылка на официальный профиль или группу в OK.ru",
    )

    generated_message: str = Field(
        min_length=20,
        description=(
            "Обязательный персонализированный черновик приглашения для "
            "проверки человеком"
        ),
    )

    recipient_address: str | None = Field(
        default=None,
        description=(
            "Публичный адрес выбранного получателя: email, ссылка на профиль, "
            "сообщество, канал или официальную форму связи"
        ),
    )

    recipient_external_id: str | None = Field(
        default=None,
        description=(
            "Проверенный ID пользователя или сообщества внутри выбранной "
            "платформы; null, если ID достоверно не определён"
        ),
    )

    @model_validator(mode="after")
    def validate_contact_channel(self) -> "SaveContactToolArgs":
        require_usable_contact_channel(self)
        return self

class SaveContactToolResult(BaseModel):
    success: bool
    status: Literal["created", "duplicate", "updated", "error"]
    contact_id: int | None = None
    message: str
