from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ContactCreate(BaseModel):
    organization_name: str = Field(min_length=1, max_length=255)

    contact_name: str | None = None
    position: str | None = None
    category: str | None = None

    country: str | None = None
    region: str | None = None
    city: str | None = None

    website: str | None = None
    email: EmailStr | None = None
    phone: str | None = None

    vk_url: str | None = None
    telegram_url: str | None = None
    youtube_url: str | None = None
    rutube_url: str | None = None
    dzen_url: str | None = None

    source: str | None = None

    relevance_score: float = Field(default=0, ge=0, le=100)
    relevance_reason: str | None = None

    preferred_channel: str | None = None
    status: str = "new"

    generated_message: str | None = None
    next_action: str | None = None


class ContactUpdate(BaseModel):
    organization_name: str | None = None
    contact_name: str | None = None
    position: str | None = None
    category: str | None = None

    country: str | None = None
    region: str | None = None
    city: str | None = None

    website: str | None = None
    email: EmailStr | None = None
    phone: str | None = None

    vk_url: str | None = None
    telegram_url: str | None = None
    youtube_url: str | None = None
    rutube_url: str | None = None
    dzen_url: str | None = None

    source: str | None = None

    relevance_score: float | None = Field(default=None, ge=0, le=100)
    relevance_reason: str | None = None

    preferred_channel: str | None = None
    status: str | None = None

    generated_message: str | None = None
    response: str | None = None
    next_action: str | None = None


class ContactRead(ContactCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int