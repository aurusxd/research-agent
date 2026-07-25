import re
from typing import Any

import requests


EMAIL_RE = re.compile(
    r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-zА-Яа-я]{2,}(?![\w.-])"
)
SOCIAL_RE = re.compile(
    r"https?://(?:vk\.com|ok\.ru|t\.me|telegram\.me)/[A-Za-z0-9_.+/-]+",
    re.IGNORECASE,
)


def verify_source(url: str) -> dict[str, Any]:
    try:
        response = requests.get(
            url,
            timeout=15,
            allow_redirects=True,
            headers={"User-Agent": "VkorniResearchAgent/1.0"},
        )
        response.raise_for_status()
    except requests.RequestException as error:
        return {
            "verified": False,
            "final_url": url,
            "error": str(error)[:300],
            "emails": [],
            "social_links": [],
            "page_excerpt": "",
        }

    text = response.text
    plain = re.sub(r"<[^>]+>", " ", text)
    plain = " ".join(plain.split())
    return {
        "verified": True,
        "final_url": response.url,
        "error": None,
        "emails": sorted(set(EMAIL_RE.findall(text)))[:10],
        "social_links": sorted(set(SOCIAL_RE.findall(text)))[:10],
        "page_excerpt": plain[:2500],
    }
