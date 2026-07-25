from typing import Literal

from pydantic import BaseModel


class StatisticsRead(BaseModel):
    period: Literal["today", "week", "all"]
    search_runs: int
    pages_found: int
    contacts_found: int
    pending_review: int
    approved: int
    rejected: int
    emails_sent: int
    replies: int
    positive_replies: int
    queued: int
    messages_sent: int
    errors: int
