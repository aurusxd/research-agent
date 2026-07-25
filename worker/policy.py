TEMPORARY_ERROR_MARKERS = (
    "timeout",
    "timed out",
    "tempor",
    "429",
    "too many requests",
    "connection",
    "network is unreachable",
    "подключ",
    "соедин",
    "временно",
)


def is_temporary_error(error: Exception) -> bool:
    text = str(error).lower()
    return any(marker in text for marker in TEMPORARY_ERROR_MARKERS)
