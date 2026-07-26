from unittest import TestCase

from services.vk_service import _looks_like_login_page


class VkSessionDetectionTest(TestCase):
    def test_login_word_alone_does_not_expire_session(self) -> None:
        self.assertFalse(
            _looks_like_login_page(
                "https://vk.com/museum",
                "Войти Новости Сообщения",
                password_visible=False,
                login_form_visible=False,
            )
        )

    def test_visible_password_is_strong_login_signal(self) -> None:
        self.assertTrue(
            _looks_like_login_page(
                "https://vk.com/museum",
                "",
                password_visible=True,
                login_form_visible=False,
            )
        )

    def test_identity_provider_url_is_login_page(self) -> None:
        self.assertTrue(
            _looks_like_login_page(
                "https://id.vk.com/auth?return_auth_hash=abc",
                "",
                password_visible=False,
                login_form_visible=False,
            )
        )

    def test_visible_login_form_requires_matching_text(self) -> None:
        self.assertFalse(
            _looks_like_login_page(
                "https://vk.com/museum",
                "Страница музея",
                password_visible=False,
                login_form_visible=True,
            )
        )
        self.assertTrue(
            _looks_like_login_page(
                "https://vk.com/museum",
                "Войти по номеру телефона",
                password_visible=False,
                login_form_visible=True,
            )
        )
