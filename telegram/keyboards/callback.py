from typing import Literal

from aiogram import F, types
from aiogram.types import CallbackQuery
from aiogram import Router
from aiogram.filters.callback_data import CallbackData
import aiohttp

router = Router()


class ReviewCallback(
    CallbackData,
    prefix="review",
):
    action: Literal[
        "approve",
        "reject",
        "edit",
        "mark_sent",
    ]
    contact_id: int

@router.callback_query(ReviewCallback.filter())
async def review_contact(
    callback: CallbackQuery,
    callback_data: ReviewCallback,
):
    contact_id = callback_data.contact_id

    if callback_data.action == "approve":
        url = f"http://api:8000/contacts/{contact_id}/approve"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url) as response:
                    if response.status != 200:
                        error = await response.text()

                        await callback.answer(
                            f"Ошибка API: {error}",
                            show_alert=True,
                        )
                        return

                    result = await response.json()

                if callback.message is not None:
                    await callback.message.edit_reply_markup(
                        reply_markup=None,
                    )

                await callback.answer(
                    "Контакт одобрен",
                )

        except Exception:
            await callback.answer(
                "Не удалось одобрить контакт",
                show_alert=True,
            )

    elif callback_data.action == "reject":
        url = f"http://api:8000/contacts/{contact_id}/reject"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url) as response:
                    if response.status != 200:
                        error = await response.text()
        
                    await callback.answer(
                        f"Ошибка API: {error}",
                        show_alert=True,
                    )
                    return
        
                result = await response.json()

            if callback.message is not None:
                await callback.message.edit_reply_markup(
                    reply_markup=None,
                )

            await callback.answer(
                "Контакт отклонён",
            )

        except Exception:
            await callback.answer(
                "Не удалось отклонить контакт",
                show_alert=True,
            )

    await callback.answer()