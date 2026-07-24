from enum import Enum


class CommunicationStatus(str, Enum):
    CREATED = "created"
    DRAFT = "draft"
    APPROVED = "approved"
    SENT = "sent"
    FAILED = "failed"

class ContactStatus(str, Enum):
    NEW = "new"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SENT = "sent"
    REPLIED = "replied"
    FAILED = "failed"


class SearchRunStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
