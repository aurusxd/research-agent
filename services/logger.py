from pathlib import Path
import sys

from loguru import logger


class AppLogger:
    """
    Класс для настройки и использования логгера
    """

    def __init__(
        self,
        log_dir: str = "./logs",
        log_file: str = "app.log",
        max_size: str = "5 MB",
        retention: int = 5,
        console_level: str = "DEBUG",
        file_level: str = "INFO",
    ):
        """
        Инициализация логгера.

        Args:
            log_dir: Директория для хранения логов
            log_file: Имя файла логов
            max_size: Максимальный размер файла (например, "5 MB", "10 MB")
            retention: Количество хранимых архивных копий
            console_level: Уровень логирования для консоли
            file_level: Уровень логирования для файла
        """
        self.log_dir = Path(log_dir)
        self.log_file = log_file
        self.max_size = max_size
        self.retention = retention
        self.console_level = console_level
        self.file_level = file_level

        logger.remove()

        self._setup_console_handler()
        self._setup_file_handler()

        self.logger = logger

    def _get_log_format(self) -> str:
        """
        Формат строки лога:
        [Дата и время] [Уровень] [Имя файла/модуля:Строка кода] - Сообщение
        """
        return (
            "<green>[{time:YYYY-MM-DD HH:mm:ss.SSS}]</green> "
            "<level>[{level: <8}]</level> "
            "<cyan>[{name}:{line}]</cyan> "
            "- <level>{message}</level>"
        )

    def _setup_console_handler(self) -> None:
        """Настройка консольного обработчика (для Docker/терминала)."""
        logger.add(
            sys.stdout,
            format=self._get_log_format(),
            level=self.console_level,
            colorize=True,
            backtrace=True,
            diagnose=True,
        )

    def _add_file_sink(self, log_dir: Path) -> None:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / self.log_file
        logger.add(
            str(log_path),
            format=self._get_log_format(),
            level=self.file_level,
            rotation=self.max_size,
            retention=self.retention,
            compression="gz",
            encoding="utf-8",
            backtrace=True,
            diagnose=True,
        )

    def _setup_file_handler(self) -> None:
        """Настройка файлового обработчика c ротацией."""
        fallback_dirs = [Path("/tmp/logs")]  # noqa: S108
        candidates = [self.log_dir, *(d for d in fallback_dirs if d != self.log_dir)]

        for log_dir in candidates:
            try:
                self._add_file_sink(log_dir)
                self.log_dir = log_dir
                return
            except OSError:
                continue

        logger.warning("File logging disabled: no writable log directory found")

    def get_logger(self):
        """Возвращает настроенный экземпляр логгера."""
        return self.logger


_logger_instance = None


def setup_logger(**kwargs):
    """Удобная функция для однократной настройки логгера."""
    global _logger_instance  # noqa: PLW0603
    if _logger_instance is None:
        _logger_instance = AppLogger(**kwargs).get_logger()
    return _logger_instance


log = setup_logger(
    log_dir="./logs",
    log_file="app.log",
    max_size="10 MB",
    retention=5,
    console_level="DEBUG",
    file_level="INFO",
)
