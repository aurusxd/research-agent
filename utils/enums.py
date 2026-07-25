from enum import Enum


class CommunicationStatus(str, Enum):
    CREATED = "created"
    DRAFT = "draft"
    APPROVED = "approved"
    SENT = "sent"
    FAILED = "failed"
    DRY_RUN = "dry_run"

class ContactStatus(str, Enum):
    NEW = "new"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    QUEUED = "queued"
    SENDING = "sending"
    REJECTED = "rejected"
    SENT = "sent"
    REPLIED = "replied"
    INTERESTED = "interested"
    FAILED = "failed"
    DRY_RUN = "dry_run"
    REQUIRES_HUMAN = "requires_human"


class SearchRunStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
