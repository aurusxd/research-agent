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
        await api_client.review_contact(
            user_id=user_id,
            contact_id=callback_data.contact_id,
            action=action,
        )
        contacts = await api_client.get_review_queue(user_id)
    except aiohttp.ClientResponseError as exc:
        log.exception("Ошибка API при проверке контакта")
        await callback.answer(
            f"Ошибка API {exc.status}",
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
            "Контакт одобрен" if action == "approve" else "Контакт отклонён"
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
        "Контакт одобрен" if action == "approve" else "Контакт отклонён"
    )
