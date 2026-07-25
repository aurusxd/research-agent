class VkCaptchaRequired(RuntimeError):
    def __init__(self, screenshot_path: str) -> None:
        self.screenshot_path = screenshot_path
        super().__init__(f"VK CAPTCHA требуется ручное решение: {screenshot_path}")


class VkSessionExpired(RuntimeError):
    pass
