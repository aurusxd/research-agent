import asyncio
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr


YANDEX_SMTP_HOST = "smtp.yandex.ru"
YANDEX_SMTP_PORT = 465
SMTP_TIMEOUT_SECONDS = 30


class EmailConfigurationError(RuntimeError):
    """Не заполнены обязательные настройки SMTP."""


class EmailSendError(RuntimeError):
    """SMTP-сервер не смог отправить письмо."""


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise EmailConfigurationError(
            f"Не задана обязательная переменная окружения {name}"
        )
    return value


def _validate_recipient(recipient: str) -> str:
    _, address = parseaddr(recipient)
    if address != recipient.strip() or "@" not in address:
        raise ValueError("Некорректный email получателя")
    return address


def _send_email_sync(
    *,
    username: str,
    password: str,
    from_name: str,
    recipient: str,
    subject: str,
    text: str,
    html: str | None,
) -> dict[str, str | bool]:
    message = EmailMessage()
    message["From"] = formataddr((from_name, username))
    message["To"] = recipient
    message["Subject"] = subject.strip()
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=username.rsplit("@", 1)[-1])
    message.set_content(text)

    if html:
        message.add_alternative(html, subtype="html")

    context = ssl.create_default_context()

    try:
        with smtplib.SMTP_SSL(
            host=YANDEX_SMTP_HOST,
            port=YANDEX_SMTP_PORT,
            timeout=SMTP_TIMEOUT_SECONDS,
            context=context,
        ) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        raise EmailSendError("Не удалось отправить письмо через SMTP Яндекса") from error

    return {
        "success": True,
        "recipient": recipient,
        "message_id": str(message["Message-ID"]),
    }


async def send_yandex_email(
    *,
    recipient: str,
    subject: str,
    text: str,
    html: str | None = None,
) -> dict[str, str | bool]:
    """Отправляет одно письмо через SMTP Яндекса, не блокируя event loop."""
    username = _required_env("YANDEX_SMTP_USER")
    password = _required_env("YANDEX_SMTP_PASSWORD")
    from_name = os.getenv("YANDEX_SMTP_FROM_NAME", "Проект «Корни»").strip()

    recipient = _validate_recipient(recipient)
    subject = subject.strip()
    text = text.strip()

    if not subject:
        raise ValueError("Тема письма не может быть пустой")
    if not text:
        raise ValueError("Текст письма не может быть пустым")

    return await asyncio.to_thread(
        _send_email_sync,
        username=username,
        password=password,
        from_name=from_name,
        recipient=recipient,
        subject=subject,
        text=text,
        html=html,
    )
