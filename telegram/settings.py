from typing import Any


def build_settings_text(settings: dict[str, Any]) -> str:
    return (
        "⚙️ <b>Настройки агента</b>\n\n"
        f"Интервал: {settings.get('interval_seconds', '—')} сек.\n"
        f"Дневной лимит: {settings.get('daily_limit', '—')}\n"
        f"Рабочее время: "
        f"{settings.get('work_start_hour', '—')}:00–"
        f"{settings.get('work_end_hour', '—')}:00\n"
        f"Часовой пояс: {settings.get('timezone', '—')}\n\n"
        "Выберите параметр для изменения."
    )


def build_integrations_text(settings: dict[str, Any]) -> str:
    integrations = settings.get("integrations") or {}
    labels = {
        "deepseek": "DeepSeek",
        "tavily": "Tavily",
        "email": "Email",
        "telegram": "Telegram",
        "vk": "VK",
        "ok": "Одноклассники",
    }
    lines = ["🔑 <b>Интеграции</b>", ""]
    lines.extend(
        f"{'✅' if integrations.get(key) else '❌'} {label}"
        for key, label in labels.items()
    )
    lines.extend(
        [
            "",
            "Ключи не показываются в Telegram. "
            "Для изменения используйте .env.",
        ]
    )
    return "\n".join(lines)
