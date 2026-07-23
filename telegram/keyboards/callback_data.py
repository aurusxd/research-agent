from typing import Literal

from aiogram.filters.callback_data import CallbackData


class ReviewCallback(
    CallbackData,
    prefix="review",
):
    action: Literal["approve", "reject"]
    contact_id: int
