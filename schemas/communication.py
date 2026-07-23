from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CommunicationCreate(BaseModel):
    contact_id: int
    channel: str = Field(min_length=1, max_length=50)
    direction: Literal["incoming", "outgoing"]
    message: str = Field(min_length=1)
    status: str = "created"


class CommunicationUpdate(BaseModel):
    channel: str | None = None
    message: str | None = None
    status: str | None = None


class CommunicationRead(CommunicationCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int