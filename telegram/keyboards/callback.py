from html import escape

import aiohttp
from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from api.client import ApiClient, InvalidReviewResponseError
from services.logger import log
from telegram.keyboards.callback_data import ReviewCallback
from telegram.keyboards.main import keyboard_build
from telegram.keyboards.menu import build_mailing_menu, build_statistics_menu
from telegram.review import build_review_card
from telegram.statistics import build_statistics_text
from utils.enums import ContactStatus

router = Router()


def _mailing_status_text(data: dict) -> str:
    labels = {
        "running": "работает",
        "paused": "на паузе",
        "stopped": "остановлена",
        "idle": "ожидает одобренные письма",
        "limit_reached": "достигнут дневной лимит",
    }
    state = str(data.get("state") or "stopped")
    text = (
        "📨 <b>Автоматическая рассылка</b>\n\n"
        f"Статус: <b>{labels.get(state, state)}</b>\n"
        f"В очереди: {data.get('approved_pending', 0)}\n"
        f"Отправлено за запуск: {data.get('sent_in_run', 0)}\n"
        f"Отправлено сегодня: {data.get('sent_today', 0)}\n"
        f"Ошибок за запуск: {data.get('failed_in_run', 0)}\n"
        f"Интервал: {data.get('interval_seconds', 0)} сек.\n"
        f"Лимит: {data.get('daily_limit', 0)} писем\n"
        f"Часовой пояс: {escape(str(data.get('timezone', '—')))}"
    )
    if data.get("last_error"):
        text += f"\n\nПоследняя ошибка: {escape(str(data['last_error']))}"
    return text


@router.callback_query(F.data.startswith("ui:mailing:"))
async def control_mailing(
    callback: CallbackQuery,
    api_client: ApiClient,
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer("Не удалось управлять рассылкой", show_alert=True)
        return

    action = (callback.data or "").rsplit(":", 1)[-1]
    if action == "schedule":
        await callback.answer(
            "Расписание появится после MVP. Используйте «Начать сейчас».",
            show_alert=True,
        )
        return
    try:
        data = await api_client.control_mailing(
            str(callback.from_user.id),
            action,
        )
    except Exception:  # noqa: BLE001
        log.exception("Не удалось выполнить действие рассылки {}", action)
        await callback.answer(
            "Не удалось изменить состояние рассылки",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        _mailing_status_text(data),
        parse_mode="HTML",
        reply_markup=build_mailing_menu(),
    )
    await callback.answer("Состояние рассылки обновлено")


@router.callback_query(F.data.startswith("ui:review:"))
async def open_review_submenu(
    callback: CallbackQuery,
    api_client: ApiClient,
) -> None:
    """Обрабатывает второй уровень меню «Проверка»."""
    if callback.from_user is None or not isinstance(
        callback.message,
        Message,
    ):
        await callback.answer("Не удалось открыть очередь", show_alert=True)
        return

    action = (callback.data or "").rsplit(":", 1)[-1]
    user_id = str(callback.from_user.id)

    if action == "requests":
        await callback.message.edit_text(
            "🔎 <b>Найденные обращения</b>\n\n"
            "Эта очередь относится к ТЗ №2 и не входит в текущий MVP.",
            parse_mode="HTML",
            reply_markup=None,
        )
        await callback.answer()
        return

    status_by_action = {
        "contacts": ContactStatus.PENDING_REVIEW.value,
        "approved": ContactStatus.APPROVED.value,
        "rejected": ContactStatus.REJECTED.value,
    }
    status = status_by_action.get(action)
    if status is None:
        await callback.answer("Неизвестная очередь", show_alert=True)
        return

    try:
        contacts = await api_client.get_contacts(
            user_id,
            status=status,
            limit=20,
        )
    except Exception:  # noqa: BLE001
        log.exception("Не удалось загрузить очередь {}", action)
        await callback.answer(
            "Не удалось получить контакты",
            show_alert=True,
        )
        return

    if not contacts:
        await callback.message.edit_text(
            "В выбранной очереди пока нет контактов.",
            reply_markup=None,
        )
        await callback.answer()
        return

    if action == "rejected":
        lines = [
            "❌ <b>Отклонённые контакты</b>",
            "",
        ]
        lines.extend(
            f"{index}. {escape(str(contact.get('organization_name') or 'Без названия'))} "
            f"({contact.get('relevance_score', 0)}/100)"
            for index, contact in enumerate(contacts[:10], start=1)
        )
        await callback.message.edit_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=None,
        )
        await callback.answer()
        return

    contact = contacts[0]
    contact_id = contact.get("id")
    if not isinstance(contact_id, int):
        await callback.answer(
            "У контакта отсутствует корректный ID",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        build_review_card(contact),
        reply_markup=keyboard_build(
            contact_id,
            approved=action == "approved",
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ui:statistics:"))
async def show_statistics(
    callback: CallbackQuery,
    api_client: ApiClient,
) -> None:
    """Показывает статистику после выбора периода в подменю."""
    if callback.from_user is None or not isinstance(
        callback.message,
        Message,
    ):
        await callback.answer(
            "Не удалось показать статистику",
            show_alert=True,
        )
        return

    parts = (callback.data or "").split(":")
    action = parts[2] if len(parts) > 2 else "all"
    period = (
        parts[3]
        if action == "refresh" and len(parts) > 3
        else action
    )
    if period not in {"today", "week", "all"}:
        period = "all"

    try:
        statistics = await api_client.get_statistics(
            str(callback.from_user.id),
            period=period,
        )
    except Exception:  # noqa: BLE001
        log.exception("Не удалось получить статистику")
        await callback.answer(
            "Не удалось получить статистику",
            show_alert=True,
        )
        return

    await callback.message.edit_text(
        build_statistics_text(statistics),
        parse_mode="HTML",
        reply_markup=build_statistics_menu(period),
    )
    await callback.answer("Статистика обновлена")


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
                    "Контакт одобрен и добавлен в автоматическую очередь."
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
