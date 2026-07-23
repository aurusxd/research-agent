from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


SEARCH_BUTTON = "🔍 Запустить поиск"
REVIEW_BUTTON = "📋 Проверка"
MAILING_BUTTON = "🚀 Рассылка"
STATISTICS_BUTTON = "📊 Статистика"
SETTINGS_BUTTON = "⚙️ Настройки"

MAIN_MENU_BUTTONS = {
    SEARCH_BUTTON,
    REVIEW_BUTTON,
    MAILING_BUTTON,
    STATISTICS_BUTTON,
    SETTINGS_BUTTON,
}


def build_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=SEARCH_BUTTON), KeyboardButton(text=REVIEW_BUTTON)],
            [KeyboardButton(text=MAILING_BUTTON), KeyboardButton(text=STATISTICS_BUTTON)],
            [KeyboardButton(text=SETTINGS_BUTTON)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие или напишите запрос агенту",
    )


def build_search_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏢 Поиск организаций", callback_data="ui:search:organizations")],
            [InlineKeyboardButton(text="👤 Поиск людей", callback_data="ui:search:people")],
            [InlineKeyboardButton(text="📝 Ввести задачу агенту", callback_data="ui:search:custom")],
        ],
    )


def build_review_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📨 Черновики организаций", callback_data="ui:review:contacts")],
            [InlineKeyboardButton(text="🔎 Найденные обращения", callback_data="ui:review:requests")],
            [InlineKeyboardButton(text="✅ Одобренные", callback_data="ui:review:approved")],
            [InlineKeyboardButton(text="❌ Отклонённые", callback_data="ui:review:rejected")],
        ],
    )


def build_mailing_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="▶️ Начать сейчас", callback_data="ui:mailing:start"),
                InlineKeyboardButton(text="🗓 Запланировать", callback_data="ui:mailing:schedule"),
            ],
            [
                InlineKeyboardButton(text="⏸ Пауза", callback_data="ui:mailing:pause"),
                InlineKeyboardButton(text="⏯ Продолжить", callback_data="ui:mailing:resume"),
            ],
            [InlineKeyboardButton(text="⛔ Остановить рассылку", callback_data="ui:mailing:stop")],
        ],
    )


def build_statistics_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📅 Сегодня", callback_data="ui:statistics:today"),
                InlineKeyboardButton(text="🗓 7 дней", callback_data="ui:statistics:week"),
            ],
            [InlineKeyboardButton(text="📈 За всё время", callback_data="ui:statistics:all")],
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="ui:statistics:refresh")],
        ],
    )


def build_settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏱ Интервал отправки", callback_data="ui:settings:interval")],
            [InlineKeyboardButton(text="📨 Дневной лимит", callback_data="ui:settings:daily_limit")],
            [InlineKeyboardButton(text="🕘 Рабочее время", callback_data="ui:settings:working_hours")],
            [InlineKeyboardButton(text="🌍 Часовой пояс", callback_data="ui:settings:timezone")],
            [InlineKeyboardButton(text="🤖 Автозапуск", callback_data="ui:settings:auto_start")],
            [InlineKeyboardButton(text="🔑 Интеграции и API-ключи", callback_data="ui:settings:integrations")],
        ],
    )
