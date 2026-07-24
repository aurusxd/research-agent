import aiohttp
from aiogram import Router
from aiogram.types import CallbackQuery, Message

from api.client import ApiClient, InvalidReviewResponseError
from services.logger import log
from telegram.keyboards.callback_data import ReviewCallback
from telegram.keyboards.main import keyboard_build
from telegram.review import build_review_card

router = Router()


@router.callback_query(ReviewCallback.filter())
async def review_contact(
    callback: CallbackQuery,
    callback_data: ReviewCallback,
    api_client: ApiClient,
) -> None:
    """Обрабатывает решение оператора и показывает следующий контакт."""
    if callback.from_user is None:
        await callback.answer("Не удалось определить оператора", show_alert=True)
        return

    user_id = str(callback.from_user.id)
    action = callback_data.action

    try:
        if action == "send":
            await api_client.send_contact_email(
                user_id=user_id,
                contact_id=callback_data.contact_id,
            )
            contacts = await api_client.get_review_queue(user_id)
        else:
            await api_client.review_contact(
                user_id=user_id,
                contact_id=callback_data.contact_id,
                action=action,
            )

            if action == "approve":
                if isinstance(callback.message, Message):
                    await callback.message.edit_reply_markup(
                        reply_markup=keyboard_build(
                            callback_data.contact_id,
                            approved=True,
                        )
                    )
                await callback.answer(
                    "Контакт одобрен. Подтвердите отправку email."
                )
                return

            contacts = await api_client.get_review_queue(user_id)
    except aiohttp.ClientResponseError as exc:
        log.exception("Ошибка API при проверке контакта")
        await callback.answer(
            (
                f"Ошибка отправки: {exc.message}"
                if action == "send"
                else f"Ошибка API {exc.status}: {exc.message}"
            )[:200],
            show_alert=True,
        )
        return
    except InvalidReviewResponseError:
        await callback.answer(
            "API вернул некорректный ответ",
            show_alert=True,
        )
        return
    except Exception:  # noqa: BLE001
        log.exception("Ошибка обработки контакта")
        await callback.answer(
            "Не удалось обработать контакт",
            show_alert=True,
        )
        return

    if not isinstance(callback.message, Message):
        await callback.answer("Контакт обработан")
        return

    if not contacts:
        await callback.message.edit_text(
            "✅ Все контакты проверены",
            reply_markup=None,
        )
        await callback.answer(
            (
                "Письмо отправлено"
                if action == "send"
                else "Контакт отклонён"
            )
        )
        return

    next_contact = contacts[0]
    next_contact_id = next_contact.get("id")
    if not isinstance(next_contact_id, int):
        await callback.answer(
            "Следующий контакт не содержит корректный ID",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        build_review_card(next_contact),
        reply_markup=keyboard_build(next_contact_id),
    )
    await callback.answer(
        (
            "Письмо отправлено"
            if action == "send"
            else "Контакт отклонён"
        )
    )
