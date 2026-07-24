from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from telegram.keyboards.callback_data import ReviewCallback


def keyboard_build(
    contact_id: int,
    *,
    approved: bool = False,
) -> InlineKeyboardMarkup:
    if approved:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📨 Подтвердить отправку email",
                        callback_data=ReviewCallback(
                            action="send",
                            contact_id=contact_id,
                        ).pack(),
                    ),
                ],
            ],
        )

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
