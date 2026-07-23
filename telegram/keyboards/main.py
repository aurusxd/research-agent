from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from telegram.keyboards.callback import ReviewCallback


def keyboard_buil(contact_id: int):
    return InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Одобрить",
                callback_data=ReviewCallback(
                    action="approve",
                    contact_id=contact_id,
                ).pack(),
            ),
            InlineKeyboardButton(
                text="❌ Отклонить",
                callback_data=ReviewCallback(
                    action="reject",
                    contact_id=contact_id,
                ).pack(),
            ),
        ],
    ],
)