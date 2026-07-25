import asyncio
import imaplib
import os
import re
import smtplib
import ssl
import time
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr


MAILRU_SMTP_HOST = "smtp.mail.ru"
MAILRU_SMTP_PORT = 465
MAILRU_IMAP_HOST = "imap.mail.ru"
MAILRU_IMAP_PORT = 993
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
            host=MAILRU_SMTP_HOST,
            port=MAILRU_SMTP_PORT,
            timeout=SMTP_TIMEOUT_SECONDS,
            context=context,
        ) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)
    except smtplib.SMTPAuthenticationError as error:
        raise EmailSendError(
            "Mail.ru отклонил авторизацию SMTP. Проверьте адрес почты и "
            "пароль приложения в MAILRU_SMTP_USER/MAILRU_SMTP_PASSWORD"
        ) from error
    except smtplib.SMTPRecipientsRefused as error:
        raise EmailSendError(
            "SMTP Mail.ru отклонил email получателя"
        ) from error
    except smtplib.SMTPSenderRefused as error:
        raise EmailSendError(
            "SMTP Mail.ru отклонил адрес отправителя"
        ) from error
    except smtplib.SMTPDataError as error:
        raise EmailSendError(
            f"SMTP Mail.ru не принял письмо: код {error.smtp_code}"
        ) from error
    except ssl.SSLError as error:
        raise EmailSendError(
            "Не удалось установить защищённое SSL-соединение с SMTP Mail.ru"
        ) from error
    except TimeoutError as error:
        raise EmailSendError(
            "SMTP Mail.ru не ответил за отведённое время"
        ) from error
    except OSError as error:
        raise EmailSendError(
            "Не удалось подключиться к smtp.mail.ru:465"
        ) from error
    except smtplib.SMTPException as error:
        raise EmailSendError(
            f"Ошибка SMTP Mail.ru: {type(error).__name__}"
        ) from error

    sent_copy_saved = _save_sent_copy(
        username=username,
        password=password,
        message=message,
        context=context,
    )
    return {
        "success": True,
        "recipient": recipient,
        "message_id": str(message["Message-ID"]),
        "sent_copy_saved": sent_copy_saved,
    }


def _save_sent_copy(
    *,
    username: str,
    password: str,
    message: EmailMessage,
    context: ssl.SSLContext,
) -> bool:
    """Сохраняет принятую SMTP-сервером копию в IMAP-папке Sent."""
    try:
        with imaplib.IMAP4_SSL(
            MAILRU_IMAP_HOST,
            MAILRU_IMAP_PORT,
            ssl_context=context,
            timeout=SMTP_TIMEOUT_SECONDS,
        ) as imap:
            imap.login(username, password)
            status, mailboxes = imap.list()
            sent_mailbox = "Sent"
            if status == "OK":
                for raw_mailbox in mailboxes or []:
                    if b"\\Sent" not in raw_mailbox:
                        continue
                    decoded = raw_mailbox.decode("ascii", errors="ignore")
                    match = re.search(r'(?:"([^"]+)"|(\S+))$', decoded)
                    if match:
                        sent_mailbox = match.group(1) or match.group(2)
                    break
            status, _ = imap.append(
                sent_mailbox,
                r"(\Seen)",
                imaplib.Time2Internaldate(time.time()),
                message.as_bytes(),
            )
            return status == "OK"
    except (imaplib.IMAP4.error, OSError, ssl.SSLError):
        # SMTP уже принял письмо. Ошибка сохранения копии не должна
        # провоцировать повторную отправку и дубликат у получателя.
        return False


async def send_mailru_email(
    *,
    recipient: str,
    subject: str,
    text: str,
    html: str | None = None,
) -> dict[str, str | bool]:
    """Отправляет одно письмо через SMTP Mail.ru, не блокируя event loop."""
    username = _required_env("MAILRU_SMTP_USER")
    password = _required_env("MAILRU_SMTP_PASSWORD")
    from_name = os.getenv("MAILRU_SMTP_FROM_NAME", "Проект «Корни»").strip()

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
