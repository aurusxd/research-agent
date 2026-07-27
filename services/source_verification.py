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
FORM_RE = re.compile(r"<form\b[^>]*>(.*?)</form\s*>", re.IGNORECASE | re.DOTALL)
MESSAGE_FIELD_RE = re.compile(
    r"<textarea\b|"
    r"<[^>]+contenteditable\s*=\s*[\"']?true|"
    r"<input\b[^>]*(?:name|id)\s*=\s*[\"'][^\"']*"
    r"(?:message|comment|feedback|question|text)[^\"']*[\"']",
    re.IGNORECASE | re.DOTALL,
)
SUBMIT_CONTROL_RE = re.compile(
    r"<(?:button|input)\b[^>]*type\s*=\s*[\"']?submit|"
    r"<button\b[^>]*>.*?(?:отправить|send|submit|написать).*?</button\s*>",
    re.IGNORECASE | re.DOTALL,
)


def has_interactive_contact_form(html: str) -> bool:
    form_blocks = FORM_RE.findall(html)
    return any(
        MESSAGE_FIELD_RE.search(block)
        and SUBMIT_CONTROL_RE.search(block)
        for block in form_blocks
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
            "source_url": url,
            "final_url": url,
            "error": str(error)[:300],
            "emails": [],
            "social_links": [],
            "page_excerpt": "",
            "has_contact_form": False,
        }

    text = response.text
    plain = re.sub(r"<[^>]+>", " ", text)
    plain = " ".join(plain.split())
    return {
        "verified": True,
        "source_url": url,
        "final_url": response.url,
        "error": None,
        "emails": sorted(set(EMAIL_RE.findall(text)))[:10],
        "social_links": sorted(set(SOCIAL_RE.findall(text)))[:10],
        "page_excerpt": plain[:2500],
        "has_contact_form": has_interactive_contact_form(text),
    }
