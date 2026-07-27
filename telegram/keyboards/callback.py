from html import escape
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import aiohttp
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from api.client import ApiClient, InvalidReviewResponseError
from services.logger import log
from telegram.keyboards.callback_data import ReviewCallback
from telegram.keyboards.main import keyboard_build
from telegram.keyboards.menu import build_mailing_menu, build_statistics_menu
from telegram.review import build_communication_history, build_review_card
from telegram.statistics import build_statistics_text
from telegram.settings import (
    build_integrations_text,
    build_settings_text,
)
from utils.enums import ContactStatus

router = Router()


class ReviewEditState(StatesGroup):
    waiting_message = State()


class MailingScheduleState(StatesGroup):
    waiting_datetime = State()


class SettingsEditState(StatesGroup):
    waiting_value = State()


def _is_message_not_modified(error: TelegramBadRequest) -> bool:
    return "message is not modified" in str(error).lower()


@router.message(ReviewEditState.waiting_message)
async def save_edited_message(
    message: Message,
    state: FSMContext,
    api_client: ApiClient,
) -> None:
    data = await state.get_data()
    contact_id = data.get("contact_id")
    text = (message.text or "").strip()
    if not isinstance(contact_id, int) or not text:
        await message.answer("Пришлите непустой текст приглашения.")
        return
    try:
        await api_client.update_contact_message(
            str(message.from_user.id),
            contact_id,
            text,
        )
    except Exception:  # noqa: BLE001
        log.exception("Не удалось сохранить отредактированное приглашение")
        await message.answer("Не удалось сохранить текст. Попробуйте ещё раз.")
        return
    await state.clear()
    contacts = await api_client.get_review_queue(str(message.from_user.id))
    contact = next(
        (item for item in contacts if item.get("id") == contact_id),
        None,
    )
    if contact is None:
        await message.answer("Текст сохранён.")
        return
    await message.answer(
        build_review_card(contact),
        reply_markup=keyboard_build(contact_id),
    )


@router.message(MailingScheduleState.waiting_datetime)
async def save_mailing_schedule(
    message: Message,
    state: FSMContext,
    api_client: ApiClient,
) -> None:
    text = (message.text or "").strip()
    try:
        settings = await api_client.get_settings(str(message.from_user.id))
        local_datetime = datetime.strptime(
            text,
            "%d.%m.%Y %H:%M",
        ).replace(tzinfo=ZoneInfo(str(settings["timezone"])))
        result = await api_client.schedule_mailing(
            str(message.from_user.id),
            local_datetime.astimezone(timezone.utc).isoformat(),
        )
    except ValueError:
        await message.answer(
            "Неверный формат. Пришлите дату как ДД.ММ.ГГГГ ЧЧ:ММ."
        )
        return
    except Exception:  # noqa: BLE001
        log.exception("Не удалось запланировать рассылку")
        await message.answer(
            "Не удалось запланировать рассылку. "
            "Убедитесь, что дата находится в будущем."
        )
        return

    await state.clear()
    await message.answer(
        "✅ Рассылка запланирована на "
        f"{result.get('scheduled_at', local_datetime.isoformat())}."
    )


@router.message(SettingsEditState.waiting_value)
async def save_setting(
    message: Message,
    state: FSMContext,
    api_client: ApiClient,
) -> None:
    data = await state.get_data()
    setting = data.get("setting")
    text = (message.text or "").strip()
    try:
        if setting == "interval":
            values = {"interval_seconds": int(text)}
        elif setting == "daily_limit":
            values = {"daily_limit": int(text)}
        elif setting == "working_hours":
            parts = text.replace(":", "").split("-")
            if len(parts) != 2:
                raise ValueError
            values = {
                "work_start_hour": int(parts[0]),
                "work_end_hour": int(parts[1]),
            }
        elif setting == "timezone":
            ZoneInfo(text)
            values = {"timezone": text}
        else:
            raise ValueError
        settings = await api_client.update_settings(
            str(message.from_user.id),
            values,
        )
    except (KeyError, TypeError, ValueError):
        await message.answer(
            "Значение не распознано. Проверьте формат и попробуйте снова."
        )
        return
    except Exception:  # noqa: BLE001
        log.exception("Не удалось сохранить настройку")
        await message.answer(
            "Не удалось сохранить настройку. Проверьте значение."
        )
        return

    await state.clear()
    await message.answer(
        build_settings_text(settings),
        parse_mode="HTML",
    )


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
        f"Принято каналами за запуск: {data.get('sent_in_run', 0)}\n"
        f"Принято каналами сегодня: {data.get('sent_today', 0)}\n"
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
    state: FSMContext,
) -> None:
    if callback.from_user is None or not isinstance(callback.message, Message):
        await callback.answer("Не удалось управлять рассылкой", show_alert=True)
        return

    action = (callback.data or "").rsplit(":", 1)[-1]
    if action == "schedule":
        await state.set_state(MailingScheduleState.waiting_datetime)
        await callback.answer()
        await callback.message.answer(
            "Пришлите дату и время запуска в формате "
            "ДД.ММ.ГГГГ ЧЧ:ММ."
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

    try:
        await callback.message.edit_text(
            _mailing_status_text(data),
            parse_mode="HTML",
            reply_markup=build_mailing_menu(),
        )
    except TelegramBadRequest as error:
        if not _is_message_not_modified(error):
            raise
    await callback.answer("Состояние рассылки актуально")


@router.callback_query(F.data.startswith("ui:settings:"))
async def control_settings(
    callback: CallbackQuery,
    api_client: ApiClient,
    state: FSMContext,
) -> None:
    if callback.from_user is None or not isinstance(
        callback.message,
        Message,
    ):
        await callback.answer(
            "Не удалось открыть настройку",
            show_alert=True,
        )
        return

    action = (callback.data or "").rsplit(":", 1)[-1]
    if action == "auto_start":
        await callback.answer(
            "Автозапуск не изменяется в текущей версии.",
            show_alert=True,
        )
        return

    if action == "integrations":
        try:
            settings = await api_client.get_settings(
                str(callback.from_user.id)
            )
        except Exception:  # noqa: BLE001
            await callback.answer(
                "Не удалось проверить интеграции",
                show_alert=True,
            )
            return
        await callback.message.answer(
            build_integrations_text(settings),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    prompts = {
        "interval": "Введите интервал между отправками в секундах.",
        "daily_limit": "Введите общий дневной лимит сообщений.",
        "working_hours": (
            "Введите рабочие часы в формате 9-19 "
            "(начало-конец, без минут)."
        ),
        "timezone": (
            "Введите часовой пояс IANA, например Asia/Novosibirsk."
        ),
    }
    prompt = prompts.get(action)
    if prompt is None:
        await callback.answer("Неизвестная настройка", show_alert=True)
        return

    await state.set_state(SettingsEditState.waiting_value)
    await state.update_data(setting=action)
    await callback.message.answer(prompt)
    await callback.answer()


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

    if action == "approve_all":
        try:
            result = await api_client.approve_all_contacts(user_id)
        except Exception:  # noqa: BLE001
            log.exception("Не удалось одобрить всю очередь контактов")
            await callback.answer(
                "Не удалось одобрить всю очередь",
                show_alert=True,
            )
            return

        approved = int(result.get("approved", 0))
        failed = int(result.get("failed", 0))
        await callback.message.edit_text(
            "✅ <b>Массовое одобрение завершено</b>\n\n"
            f"Одобрено: {approved}\n"
            f"Пропущено с ошибкой: {failed}",
            parse_mode="HTML",
            reply_markup=None,
        )
        await callback.answer("Очередь обработана")
        return

    if action == "requests":
        await callback.message.edit_text(
            "🔎 <b>Найденные обращения</b>\n\n",
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
        reply_markup=(
            None
            if action == "approved"
            else keyboard_build(contact_id)
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

    try:
        await callback.message.edit_text(
            build_statistics_text(statistics),
            parse_mode="HTML",
            reply_markup=build_statistics_menu(period),
        )
    except TelegramBadRequest as error:
        if not _is_message_not_modified(error):
            raise
    await callback.answer("Статистика обновлена")


@router.callback_query(ReviewCallback.filter())
async def review_contact(
    callback: CallbackQuery,
    callback_data: ReviewCallback,
    api_client: ApiClient,
    state: FSMContext,
) -> None:
    """Обрабатывает решение оператора и показывает следующий контакт."""
    if callback.from_user is None:
        await callback.answer("Не удалось определить оператора", show_alert=True)
        return

    user_id = str(callback.from_user.id)
    action = callback_data.action

    if action == "history":
        try:
            communications = await api_client.get_contact_communications(
                user_id,
                callback_data.contact_id,
                limit=10,
            )
        except Exception:  # noqa: BLE001
            log.exception("Ошибка получения истории коммуникаций")
            await callback.answer(
                "Не удалось получить историю",
                show_alert=True,
            )
            return

        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.answer(
                build_communication_history(communications)
            )
        return

    if action == "edit":
        await state.set_state(ReviewEditState.waiting_message)
        await state.update_data(contact_id=callback_data.contact_id)
        await callback.answer()
        if isinstance(callback.message, Message):
            await callback.message.answer(
                "Пришлите новый текст приглашения одним сообщением."
            )
        return

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
            (
                f"Ошибка API {exc.status}: {exc.message}"
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
                (
                    "Контакт одобрен и добавлен в автоматическую очередь"
                    if action == "approve"
                    else "Контакт отклонён"
                )
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
            (
                "Контакт одобрен и добавлен в автоматическую очередь"
                if action == "approve"
                else "Контакт отклонён"
            )
        )
    )
