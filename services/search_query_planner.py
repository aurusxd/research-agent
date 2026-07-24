import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


THEMATIC_VARIANTS = {
    "музе": [
        "краеведческие музеи",
        "исторические музеи",
        "школьные музеи",
    ],
    "краевед": [
        "краеведческие сообщества",
        "история региона сообщества",
        "семейная память",
    ],
    "архив": [
        "государственные архивы",
        "муниципальные архивы",
        "архивные сообщества",
    ],
    "генеалог": [
        "генеалогические сообщества",
        "родословная история семьи",
        "семейные архивы",
    ],
    "ветеран": [
        "ветеранские организации",
        "военно-исторические сообщества",
        "поисковые отряды",
    ],
}


def build_search_queries(search_run: Any) -> list[str]:
    explicit_location = next(
        (
            value.strip()
            for value in (
                search_run.city,
                search_run.region,
            )
            if value and value.strip()
        ),
        "",
    )
    location = (
        explicit_location
        or _extract_location(search_run.query)
        or (search_run.country or "").strip()
    )
    candidates: list[str] = [search_run.query.strip()]

    category = (search_run.category or "").strip()
    if category:
        candidates.append(_with_location(category, location))
        category_parts = re.split(
            r"\s+и\s+|[,;/]",
            category,
            flags=re.IGNORECASE,
        )
        candidates.extend(
            _with_location(part.strip(), location)
            for part in category_parts
            if part.strip()
        )

    candidates.extend(
        _with_location(keyword.strip(), location)
        for keyword in search_run.keywords
        if keyword.strip()
    )

    searchable_text = " ".join(
        [search_run.query, category, *search_run.keywords]
    ).casefold()
    for marker, variants in THEMATIC_VARIANTS.items():
        if marker in searchable_text:
            candidates.extend(
                _with_location(variant, location)
                for variant in variants
            )

    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = " ".join(candidate.split())
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        unique.append(normalized)
        if len(unique) >= search_run.search_queries_limit:
            break
    return unique


def merge_search_results(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in results:
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        key = normalize_url(url)
        query = str(item.get("query") or "").strip()
        existing = merged.get(key)
        if existing is None:
            copy = dict(item)
            copy["matched_queries"] = [query] if query else []
            merged[key] = copy
            continue

        if query and query not in existing["matched_queries"]:
            existing["matched_queries"].append(query)
        if len(str(item.get("content") or "")) > len(
            str(existing.get("content") or "")
        ):
            existing["content"] = item.get("content") or ""
    return list(merged.values())


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = parts.netloc.casefold()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/") or "/"
    clean_query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(
                parts.query,
                keep_blank_values=True,
            )
            if not key.casefold().startswith("utm_")
        )
    )
    return urlunsplit(("", host, path, clean_query, ""))


def _with_location(text: str, location: str) -> str:
    return f"{text} {location}".strip()


def _extract_location(query: str) -> str:
    match = re.search(
        (
            r"([А-ЯЁ][а-яё-]+"
            r"(?:\s+[А-ЯЁ][а-яё-]+){0,2}\s+"
            r"(?:области|края|республики|округа))"
        ),
        query,
    )
    return match.group(1) if match else ""
