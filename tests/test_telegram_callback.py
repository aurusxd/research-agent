from unittest import TestCase

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageText

from telegram.keyboards.callback import _is_message_not_modified


class TelegramCallbackErrorTest(TestCase):
    def test_recognizes_unchanged_message_response(self) -> None:
        error = TelegramBadRequest(
            method=EditMessageText(
                chat_id=1,
                message_id=1,
                text="без изменений",
            ),
            message=(
                "Bad Request: message is not modified: specified new "
                "message content and reply markup are exactly the same"
            ),
        )

        self.assertTrue(_is_message_not_modified(error))

    def test_does_not_hide_other_bad_requests(self) -> None:
        error = TelegramBadRequest(
            method=EditMessageText(
                chat_id=1,
                message_id=1,
                text="текст",
            ),
            message="Bad Request: message to edit not found",
        )

        self.assertFalse(_is_message_not_modified(error))
