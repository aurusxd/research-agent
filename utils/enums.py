from enum import Enum


class CommunicationStatus(str, Enum):
    CREATED = "created"

class ContactStatus(str, Enum):
    NEW = "new"