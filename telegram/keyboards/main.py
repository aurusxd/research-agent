from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from telegram.keyboards.callback_data import ReviewCallback


def keyboard_build(
    contact_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Редактировать письмо",
                    callback_data=ReviewCallback(
                        action="edit",
                        contact_id=contact_id,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🕘 История коммуникаций",
                    callback_data=ReviewCallback(
                        action="history",
                        contact_id=contact_id,
                    ).pack(),
                ),
            ],
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
