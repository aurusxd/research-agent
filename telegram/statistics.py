from typing import Any


PERIOD_LABELS = {
    "today": "Сегодня",
    "week": "Последние 7 дней",
    "all": "За всё время",
}


def build_statistics_text(data: dict[str, Any]) -> str:
    period = str(data.get("period") or "all")
    return (
        "📊 <b>Статистика</b>\n"
        f"Период: <b>{PERIOD_LABELS.get(period, period)}</b>\n\n"
        f"🔎 Поисковых запусков: {data.get('search_runs', 0)}\n"
        f"🌐 Уникальных страниц: {data.get('pages_found', 0)}\n"
        f"🏢 Найдено контактов: {data.get('contacts_found', 0)}\n\n"
        f"⏳ Ожидают проверки: {data.get('pending_review', 0)}\n"
        f"✅ Одобрено: {data.get('approved', 0)}\n"
        f"❌ Отклонено: {data.get('rejected', 0)}\n"
        f"📨 Отправлено email: {data.get('emails_sent', 0)}\n"
        f"💬 Получено ответов: {data.get('replies', 0)}\n"
        f"⚠️ Ошибок: {data.get('errors', 0)}"
    )
